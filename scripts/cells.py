import math

import pygame

import scripts.laser_properties as laser_properties
from scripts.global_assets import get_asset
from scripts.UI.interaction_display import InteractionDisplay
from scripts.util import ImageCache, about_equal, charges_to_color, dist, normalize_1d

CELL_CHARGE_CAPACITY = 25  # matches player.CELL_CHARGE_COST -- a thrown cell always holds exactly this much

CELL_EXPLODE_NORMAL_SPEED = 0.15  # world units/ms -- normal-component impact speed needed to detonate a cell

cell_imgs = None
animation_fps = 12

NOMINAL_FRAME_MS = 1000 / 60  # knockback circles are one-shot impulses, not continuous forces --
# baked to a 60fps frame instead of scaling with actual frame_length, or the "instant" kick becomes
# framerate-dependent and gets crushed to near-zero during hit-stop (see player.py for the full story)

NUDGE_RADIUS = 10  # world units -- cells gently push away from other dynamic objects within this range
NUDGE_STRENGTH = 0.00003  # a continuous, gentle force -- not rigid-body physics, just enough to avoid stacking


def validate_cell_coords(_terrain, coords):
    x, y = coords
    rect = pygame.Rect(x - Cell.width / 2, y - Cell.height / 2, Cell.width, Cell.height)
    return not _terrain.collide_rect(rect)


def init():
    global cell_imgs
    cell_imgs = {
        "shell": get_asset("cell_basic_shell"),
        **{"crackle_" + str(i + 1): get_asset("cell_basic_crackle_" + str(i + 1)) for i in range(5)},
    }


class Cell:
    width = 10
    height = 18
    size = 30
    cell_imgs_cache = ImageCache()

    def __init__(self, default_zooms, coords, velocities, charges=None, filter_type="white"):
        self.w = Cell.width
        self.h = Cell.height
        self.size = Cell.size
        self.x, self.y = coords
        self.x_speed, self.y_speed = velocities
        self.rect = pygame.Rect(self.x - self.w / 2, self.y - self.h / 2, self.w, self.h)
        self.r = dist(self.w, self.h)
        self.interaction_display = InteractionDisplay((self.x, self.y + self.h / 2), (pygame.K_e, ""))
        self.frames_since_moved = 0
        self.animation_timer = 0
        self.frame = 1

        # charge this cell holds -- restored to the player if picked back up. Only ever
        # unset for a cell created outside the normal throw path, hence the safe default.
        self.charges = charges if charges is not None else {"white": CELL_CHARGE_CAPACITY, "blue": 0, "red": 0}
        # filter the player was using when this cell was thrown -- used only to reproduce
        # the same red-dmg_range bonus set_laser_attributes applies when exploding on impact
        self.filter_type = filter_type
        # same convention as the charge display: charges_to_color(w, b, r, 25)
        self.color = charges_to_color(self.charges["white"], self.charges["blue"], self.charges["red"], CELL_CHARGE_CAPACITY)

        self.cell_imgs = {}
        self._draw_filter = {}
        for zoom in default_zooms:
            self.cell_imgs[zoom] = {}
            for id in cell_imgs:
                self.cell_imgs[zoom][id] = Cell.cell_imgs_cache.get_resized_image(cell_imgs[id], id, (Cell.size * zoom, Cell.size * zoom))
            self._draw_filter[zoom] = pygame.Surface((Cell.size * zoom, Cell.size * zoom), flags=pygame.SRCALPHA)

    def explode(self, _terrain, x, y):
        # "max stats" laser attributes for this cell's own charge composition -- normalize
        # the cell's 25-charge pool up to a full 500 (set_laser_attributes' own max_charge
        # convention, matching how the player's own laser_attributes are computed) so the
        # interpolation reads as fully charged in whichever color(s) the cell was holding
        scale = 500 / CELL_CHARGE_CAPACITY
        normalized_charges = {color: amount * scale for color, amount in self.charges.items()}

        attrs = laser_properties.LaserAttributes(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, {"white": (0, False), "blue": (0, False), "red": (0, False)})
        laser_properties.set_laser_attributes(attrs, normalized_charges, self.filter_type, 500)
        attrs.area_dmg_falloff = 1.0
        attrs.area_kb_falloff = 1.0

        damage = laser_properties.get_laser_dmg(attrs, False, 0)
        knockback = laser_properties.get_laser_kb(attrs, False, 0)
        explosion_size = laser_properties.get_laser_expl(attrs, False, 0)

        _terrain.add_air_pocket_clump(x, y, explosion_size, player_made=True, spreading=1 / 5, spawn_particles=True)
        _terrain.new_player_damage_circles.append([damage, x, y, attrs.dmg_range, attrs.area_dmg_falloff])
        _terrain.new_knockback_circles.append([knockback, x, y, attrs.kb_range, attrs.area_kb_falloff])

        # same weighting the player's own laser hits use (base_xpl/8), and the same
        # dmg_range/kb_range pulse pair, just colored by this cell's own stored charge
        _terrain.add_screen_shake(explosion_size / 8)
        _terrain.particles.spawn_pulse_particle(self.color, attrs.dmg_range, x, y)
        _terrain.particles.spawn_pulse_particle(self.color, attrs.kb_range, x, y)

    def tick_knockback(self, frame_length, _terrain, player):
        affected = False
        for knockback_circle in _terrain.knockback_circles:
            pow, x, y, r, falloff = knockback_circle

            dx = self.x - x
            dy = self.y - y
            if dx == 0 and dy == 0:
                dy = -1  # circle acts as if it's one pixel below
            d = dist(dx, dy)
            if player.laser:
                if player.laser.laser_target is self:
                    self.x_speed += NOMINAL_FRAME_MS * dx / d * pow / 30
                    self.y_speed += NOMINAL_FRAME_MS * dy / d * pow / 30
                    affected = True
                elif d < r + self.r:
                    self.x_speed += NOMINAL_FRAME_MS * dx / d * pow * falloff / 30
                    self.y_speed += NOMINAL_FRAME_MS * dy / d * pow * falloff / 30
                    affected = True
            elif d < r + self.r:
                self.x_speed += NOMINAL_FRAME_MS * dx / d * pow * falloff / 30
                self.y_speed += NOMINAL_FRAME_MS * dy / d * pow * falloff / 30
                affected = True
        return affected

    def tick_gravity(self, frame_length):
        self.y_speed = min(2, self.y_speed + 0.0015 * frame_length)

    def _find_clearance(self, _terrain, vx, vy, max_wiggle=2):
        speed = dist(vx, vy)
        if speed == 0:
            tx, ty = 0, 1  # arbitrary tangent, doesn't matter if not moving
        else:
            tx, ty = -vy / speed, vx / speed  # perpendicular to velocity

        orig_x, orig_y = self.x, self.y

        for offset in range(1, max_wiggle + 1):
            for direction in (1, -1):
                self.x = orig_x + tx * offset * direction
                self.y = orig_y + ty * offset * direction
                self.update_rect()
                if not self.colliding_with_terrain(_terrain):
                    return True

        self.x, self.y = orig_x, orig_y
        self.update_rect()
        return False

    def attempt_movement(self, frame_length, _terrain):
        elasticity = 0.4
        friction = 0.97
        drag = 0.993
        absorption = 0.2

        # temporary
        self.update_rect()
        collision = self.colliding_with_terrain(_terrain)
        if collision:
            return

        vx, vy = self.x_speed, self.y_speed
        dx, dy = frame_length * vx, frame_length * vy
        orig_xy = self.x, self.y

        self.x += dx
        self.y += dy

        self.update_rect()
        collision = self.colliding_with_terrain(_terrain)
        if collision:
            if not self._find_clearance(_terrain, vx, vy):
                self.x, self.y = orig_xy
            else:
                return
        else:
            return

        remaining = frame_length
        while remaining > 0:
            speed = dist(vx, vy)
            if speed == 0:
                return
            tick_length = min(remaining, 1 / speed)

            dx, dy = vx * tick_length, vy * tick_length
            ox, oy = self.x, self.y

            # tick_length already caps dist(dx, dy) <= 1, so this substep can cross at
            # most one integer boundary per axis -- but it can still cross both axes'
            # boundaries at once (e.g. starting near a corner and moving diagonally),
            # which lets the endpoint-only check below skip clean past a solid pixel
            # without ever landing on it. When that happens, stop and check collision
            # at the earlier of the two crossings first, exactly on the ox/oy->dx/dy
            # line (linear interpolation by t, not an axis-only step), so self.x/self.y
            # is never advanced more than one pixel boundary at a time in either axis.
            crossing_ts = []
            if dx != 0:
                next_ix = math.floor(ox) + (1 if dx > 0 else 0)
                t_x = (next_ix - ox) / dx
                if 0 < t_x < 1:
                    crossing_ts.append(t_x)
            if dy != 0:
                next_iy = math.floor(oy) + (1 if dy > 0 else 0)
                t_y = (next_iy - oy) / dy
                if 0 < t_y < 1:
                    crossing_ts.append(t_y)

            collision = False
            if len(crossing_ts) > 1:
                mid_t = min(crossing_ts)
                self.x, self.y = ox + mid_t * dx, oy + mid_t * dy
                self.update_rect()
                collision = self.colliding_with_terrain(_terrain)

            if not collision:
                self.x, self.y = ox + dx, oy + dy
                self.update_rect()
                collision = self.colliding_with_terrain(_terrain)
            if collision:
                if not self._find_clearance(_terrain, vx, vy):
                    self.x, self.y = ox, oy

                    collide_x, collide_y = collision
                    normal = _terrain.get_normal(collide_x - normalize_1d(dx), collide_y - normalize_1d(dy))

                    mag = dist(*normal)
                    if mag == 0:
                        return
                    nx, ny = normal[0] / mag, normal[1] / mag

                    scalar = nx * vx + ny * vy

                    if -scalar > CELL_EXPLODE_NORMAL_SPEED:
                        self.explode(_terrain, collide_x, collide_y)
                        return True

                    vx -= scalar * nx
                    vy -= scalar * ny
                    vx *= friction**tick_length
                    vy *= friction**tick_length
                    if -scalar > absorption:
                        vx -= scalar * nx * elasticity
                        vy -= scalar * ny * elasticity
                    continue
            vx *= drag**tick_length
            vy *= drag**tick_length

            remaining -= tick_length
        self.x_speed, self.y_speed = vx, vy
        return

    def tick_nudge(self, frame_length, dynamic_objects):
        # gentle continuous repulsion (not a one-shot impulse, so it's correctly
        # scaled by frame_length, unlike the knockback circles above) -- just enough
        # to keep cells from visibly stacking on top of the player/enemies/each other
        for ox, oy, obj in dynamic_objects:
            if obj is self:
                continue
            dx, dy = self.x - ox, self.y - oy
            if dx == 0 and dy == 0:
                continue
            d = dist(dx, dy)
            if d < NUDGE_RADIUS:
                push = (NUDGE_RADIUS - d) * NUDGE_STRENGTH * frame_length
                self.x_speed += dx / d * push
                self.y_speed += dy / d * push

    def tick(self, frame_length, _terrain, player, dynamic_objects=()):
        self.animation_timer = (self.animation_timer + frame_length) % (1000 / animation_fps * 5)
        self.frame = math.floor(self.animation_timer / (1000 / animation_fps)) + 1
        if self.tick_knockback(frame_length, _terrain, player) or self.frames_since_moved <= 2:
            last_x, last_y = self.x, self.y
            self.tick_gravity(frame_length)
            if dynamic_objects:
                self.tick_nudge(frame_length, dynamic_objects)
            if self.attempt_movement(frame_length, _terrain):
                return True  # exploded -- caller is responsible for removing this cell

            if not (about_equal(last_x, self.x, frame_length) and about_equal(last_y, self.y, frame_length)):
                self.interaction_display.update_coordinates((self.x, self.y + self.h / 2))
                self.frames_since_moved = 0
            self.frames_since_moved += 1
        return False

    def update_rect(self):
        # pygame.Rect rounds float assignment to the nearest int rather than flooring it,
        # which doesn't match terrain._sample_chunk's floor-based pixel grid (or the
        # floor-based boundary math in attempt_movement's substep loop) -- floor explicitly
        # so self.rect.x/y always lands on the same pixel grid the rest of collision uses.
        self.rect.x, self.rect.y = math.floor(self.x - self.w / 2), math.floor(self.y - self.h / 2)

    def colliding_with_terrain(self, _terrain):
        return _terrain.collide_rect(self.rect)

    def draw(self, surface, frame, hitbox=False, offset_x=0, offset_y=0):
        cam_x, cam_y, zoom = frame

        self.update_rect()

        if hitbox:
            vis_rect = (self.rect.left - cam_x) * zoom + offset_x, (self.rect.top - cam_y) * zoom + offset_y, self.w * zoom, self.h * zoom
            pygame.draw.rect(surface, (0, 0, 0), vis_rect, 2)
        else:
            dest = ((self.x - self.size / 2 - cam_x) * zoom + offset_x, (self.y - self.size / 2 - cam_y) * zoom + offset_y)
            shell = self.cell_imgs[zoom]["shell"]
            crackle = self.cell_imgs[zoom]["crackle_" + str(self.frame)]

            filt = self._draw_filter[zoom]
            filt.fill(self.color)
            filt.blit(shell, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(filt, dest)

            filt.fill(self.color)
            filt.blit(crackle, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(filt, dest)

    def within_interaction_radius(self, coords):
        x, y = coords
        radius = 50
        dx = x - self.x
        dy = y - self.y
        return dist(dx, dy) < radius

    def close(self, window_size, frame):
        left, top, zoom = frame
        w_width, w_height = window_size
        x_margin = min(500, w_width / zoom / 2 + self.r)
        y_margin = min(400, w_height / zoom / 2 + self.r)
        x, y = left + w_width / zoom / 2, top + w_height / zoom / 2
        dx = x - self.x
        dy = y - self.y
        return abs(dx) < x_margin and abs(dy) < y_margin
