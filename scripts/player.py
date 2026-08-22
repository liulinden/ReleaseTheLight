import math
import random

import pygame

import scripts.laser as laser
import scripts.laser_properties as laser_properties
import scripts.terrain as terrain
from scripts.global_assets import get_asset
from scripts.UI.health_bar import HealthBar
from scripts.UI.load_bar import LoadBar
from scripts.util import channel_bound, charges_to_color, dist, frame_random, rotate_and_get_offset

SPRITE_WIDTH = 40
SPRITE_HEIGHT = 40
ARM_PIVOT_X = 20
ARM_PIVOT_Y = 21

COYOTE_TIME = 120  # ms — grace window to jump after walking off a ledge
GROUND_ACCEL = 0.005
GROUND_MAX_SPEED = 0.2
AIR_ACCEL = 0.0015
AIR_FRICTION = 0.993

NOMINAL_FRAME_MS = 1000 / 60  # knockback circles are one-shot impulses, not continuous forces --
# baked to a 60fps frame instead of scaling with actual frame_length, which made the "instant"
# kick framerate-dependent and let it get crushed to near-zero during hit-stop

HIT_STOP_DURATION = 50  # ms — freeze requested when an enemy lands a hit
LASER_HIT_STOP_DURATION = 45  # ms — freeze on the first hit of each laser cast (not every ramp tick)

CELL_CHARGE_COST = 25  # one cell's worth of charge -- matches charge_capacity's n_cells*25 and the charge display's own per-cell unit
CELL_THROW_CHARGE_TIME = 500  # ms -- max hold duration before the throw speed caps out
CELL_THROW_MIN_SPEED = 0.1  # speed on a bare tap
CELL_THROW_MAX_SPEED = 0.8  # speed after holding for CELL_THROW_CHARGE_TIME

CELL_CHARGE_BAR_LENGTH = 40  # px, unscaled by zoom -- same convention as HealthBar
CELL_CHARGE_BAR_SIDE_OFFSET = 10  # px to the side of the player the bar sits, beyond SPRITE_WIDTH/2

IMPACT_SIZE = 100  # world-space size in px — easy to change
IMPACT_FPS = 24
IMPACT_FRAMES = 7

PLAYER_IMGS = {}
LASER_IMPACT_IMGS_RAW = []  # raw unscaled images, loaded in init()
ANIMATION_LENGTHS = {"idle": 8, "run": 8, "backpedal": 8, "fall": 1, "jump": 1}
ANIMATION_FPS = 13


def filter_charges(filter_type, charges):
    match filter_type:
        case "white":
            return charges
        case "blue":
            return {"white": 0, "blue": charges["white"] / 2 + charges["blue"], "red": 0}
        case "red":
            return {"white": 0, "blue": 0, "red": charges["white"] / 2 + charges["red"]}


filter_feeds = {"white": {"white": (1, 0, 0), "blue": (0, 1, 0), "red": (0, 0, 1)}, "blue": {"white": (0, 0.5, 0), "blue": (0, 1, 0), "red": (0, 0, 0)}, "red": {"white": (0, 0, 0.5), "blue": (0, 0, 0), "red": (0, 0, 1)}}


def init():
    global PLAYER_IMGS, LASER_IMPACT_IMGS_RAW

    img_set = []
    for i in range(5):
        img_set.append(get_asset("player_idle_" + str(i + 1)))
    for i in range(3):
        img_set.append(get_asset("player_idle_" + str(4 - i)))
    PLAYER_IMGS["idle"] = img_set

    img_set = []
    for i in range(8):
        img_set.append(get_asset("player_run_" + str(i + 1)))
    PLAYER_IMGS["run"] = img_set

    # TEMPORARY ANIMATION
    img_set = []
    for i in range(8):
        img_set.append(get_asset("player_run_" + str(8 - i)))
    PLAYER_IMGS["backpedal"] = img_set

    PLAYER_IMGS["fall"] = [get_asset("player_fall")]
    PLAYER_IMGS["jump"] = [get_asset("player_jump")]
    # playerIMGs["Sliding"]=[get_asset("PlayerSliding")]
    PLAYER_IMGS["arm"] = [get_asset("player_arm")]

    LASER_IMPACT_IMGS_RAW = []
    for i in range(1, IMPACT_FRAMES + 1):
        LASER_IMPACT_IMGS_RAW.append(get_asset(f"laser_impact_{i}"))


class LaserImpact:
    """Single impact animation instance. Follows the live laser endpoint while
    the laser is active, then freezes at its last known position."""

    _frame_duration = 1000 / IMPACT_FPS

    def __init__(self, x, y, angle, source_laser, scaled_im_gs):
        self.x = x
        self.y = y
        self.angle = angle
        self.source_laser = source_laser  # reference to spawning Laser; set to None when gone
        self.scaled_im_gs = scaled_im_gs  # pre-scaled images for all zooms
        self.timer = 0.0
        # reused draw scratch surfaces -- resized if the image size changes (e.g. zoom change)
        self._tinted_surface = None
        self._color_surf = None
        self._scratch_size = None

    def tick(self, frame_length, active_laser):
        # update position if source laser is still active
        if self.source_laser is not None:
            if self.source_laser is active_laser:
                lase = self.source_laser
                self.x = lase.start_x + math.cos(lase.angle) * lase.length
                self.y = lase.start_y + math.sin(lase.angle) * lase.length
                self.angle = lase.angle
            else:
                self.source_laser = None  # laser gone — freeze position

        self.timer += frame_length
        return self.timer >= self._frame_duration * IMPACT_FRAMES  # True = finished

    def draw(self, surface, frame, color, zoom, offset_x=0, offset_y=0):
        left, top, _ = frame
        frame_index = min(IMPACT_FRAMES - 1, int(self.timer / self._frame_duration))
        img = self.scaled_im_gs[zoom][frame_index]

        size = img.get_size()
        if self._scratch_size != size:
            self._tinted_surface = pygame.Surface(size, pygame.SRCALPHA)
            self._color_surf = pygame.Surface(size, pygame.SRCALPHA)
            self._scratch_size = size
        tinted = self._tinted_surface
        tinted.fill((0, 0, 0, 0))
        tinted.blit(img, (0, 0))
        color_surf = self._color_surf
        color_surf.fill((color[0], color[1], color[2], 255))
        tinted.blit(color_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

        cx = size[0] / 2
        cy = size[1] / 2
        rot_angle = math.pi - self.angle
        rotated, off_x, off_y = rotate_and_get_offset(tinted, cx, cy, rot_angle)

        half_h = size[1] / 2
        screen_x = (self.x - left) * zoom - cx + off_x - math.cos(self.angle) * half_h + offset_x
        screen_y = (self.y - top) * zoom - cy + off_y - math.sin(self.angle) * half_h + offset_y
        surface.blit(rotated, (screen_x, screen_y))


class Player:
    def __init__(self, default_zooms, x, y, dimensions=(10, 30)):
        self.spawn_x = x
        self.spawn_y = y
        self.x = x
        self.y = y
        self.x_speed = 0
        self.y_speed = 0
        self.width, self.height = dimensions
        self.rect = pygame.Rect(self.x - self.width / 2, self.y - self.height / 2, self.width, self.height)
        self.on_ground = False
        self.coyote_timer = 0
        self.color = (255, 0, 0)
        self.default_zooms = default_zooms
        self.facing = "right"
        self.animation_timer = 0
        self.animation_type = "idle"
        self.animation_frame = 0
        self.arm_angle = 0
        self.arm_offset_x = 0
        self.arm_offset_y = 0

        self.filter_type = "white"
        self.filter_change_right = True
        self.laser_timer = 0
        self.laser_ramps = 0
        self.laser_first_hit = False
        self.laser = None
        self.impacts = []  # active LaserImpact instances
        self.laser_attributes = laser_properties.LaserAttributes(18, 1, 0.2, 10, 400, 1, 20, 0.3, 1, 20, 20, 0.5, 2, 0.5, {"white": (0, False), "blue": (0, False), "red": (0, False)})

        self.ability_timer = 0
        self.ability_cooldown = 800

        self.cell_throw_hold_timer = 0  # ms right_mouse has been held this charge-up, capped at CELL_THROW_CHARGE_TIME
        self.cell_charge_bar = LoadBar(CELL_CHARGE_BAR_LENGTH)

        self.n_cells = 15
        self.charge_capacity = self.n_cells * 25
        self.charges = {"white": 100, "blue": 0, "red": 0}
        self.practical_charges = {"white": 100, "blue": 0, "red": 0}
        self.max_charge = 500
        self.immunity_timer = 0
        self.immunity_time = 500
        self.queued_damage = 0
        self.queued_drain_damage = 0
        self.pending_hit_stop = 0  # ms of freeze requested by the last enemy hit; consumed by the main loop
        self.pending_laser_flash = False  # set on the laser's first hit; consumed by the main loop
        self.pending_laser_ramp_flash = False  # set on later damage frames of the same cast -- slighter than the first hit
        self.pending_damage_flash = False  # set when an enemy lands a hit; consumed by the main loop

        self.player_im_gs = {}
        for zoom in self.default_zooms:
            zoom_img_sets = {}
            for direction in ["left", "right"]:
                direction_set = {}
                for animation_type in PLAYER_IMGS:
                    direction_set[animation_type] = []
                    for img in PLAYER_IMGS[animation_type]:
                        resized_img = pygame.transform.smoothscale(img, (SPRITE_WIDTH * zoom, SPRITE_HEIGHT * zoom))
                        if direction == "left":
                            resized_img = pygame.transform.flip(resized_img, True, False)
                        direction_set[animation_type].append(resized_img)
                zoom_img_sets[direction] = direction_set
            self.player_im_gs[zoom] = zoom_img_sets

        # reuse pre-allocated draw surfaces every frame instead of allocating in draw()
        self._player_draw_surface = {}
        for zoom in self.default_zooms:
            self._player_draw_surface[zoom] = pygame.Surface((SPRITE_WIDTH * zoom, SPRITE_HEIGHT * zoom), flags=pygame.SRCALPHA)
        # arm's rotated bounding box size changes every frame with arm_angle, so it can't
        # be pre-sized per zoom -- resize-if-needed instead of allocating fresh each frame
        self._arm_draw_surface = None
        self._arm_draw_surface_size = None

        # pre-scale impact images for each zoom — done here since defaultZooms is available
        self._impact_im_gs = {}
        for zoom in self.default_zooms:
            size = int(IMPACT_SIZE * zoom)
            self._impact_im_gs[zoom] = [pygame.transform.smoothscale(img, (size, size)) for img in LASER_IMPACT_IMGS_RAW]

    def reset_player(self):
        self.x = self.spawn_x
        self.y = self.spawn_y
        self.x_speed = 0
        self.y_speed = 0
        self.set_charges(max(100, 25 * int(self.n_cells * 2 / 3)), 0, 0)
        self.filter_type = "white"
        self.practical_charges = filter_charges(self.filter_type, self.charges)
        self.laser = None

    def update_costume(self, frame_length, mouse_pos):
        self.animation_timer = (self.animation_timer + frame_length) % (1000 / ANIMATION_FPS * (ANIMATION_LENGTHS[self.animation_type]))
        previous_animation_type = self.animation_type

        target_x, target_y = mouse_pos

        if self.x < target_x:
            self.facing = "right"
        elif self.x > target_x:
            self.facing = "left"

        start_x, start_y = self.get_laser_start()
        self.arm_angle = -math.atan2(target_y - start_y, target_x - start_x)

        if not self.on_ground:
            if self.y_speed > 0.2:
                self.animation_type = "fall"
            elif self.y_speed < -0.2:
                self.animation_type = "jump"
        else:
            if abs(self.x_speed) > 0.1:
                if (self.x_speed > 0 and self.facing == "right") or (self.x_speed < 0 and self.facing == "left"):
                    self.animation_type = "run"
                else:
                    self.animation_type = "backpedal"
            else:
                self.animation_type = "idle"

        if self.animation_type != previous_animation_type:
            self.animation_timer = 0

        animation_length = ANIMATION_LENGTHS[self.animation_type]
        if animation_length == 1:
            self.animation_frame = 0
        else:
            self.animation_frame = math.floor(self.animation_timer / (1000 / ANIMATION_FPS))

    def update_rect(self):
        # pygame.Rect rounds float assignment to the nearest int rather than flooring it,
        # which doesn't match terrain._sample_chunk's floor-based pixel grid -- floor
        # explicitly so self.rect.x/y always lands on the same pixel grid collision uses.
        self.rect.x, self.rect.y = math.floor(self.x - self.width / 2), math.floor(self.y - self.height / 2)

    def update_color(self):
        cw, cb, cr = self.practical_charges.values()
        self.color = charges_to_color(cw, cb, cr, self.max_charge)

    def update_charge_capacity(self):
        self.charge_capacity = self.n_cells * 25
        total_charge = sum(self.charges.values())
        overflow = 0
        if total_charge > self.charge_capacity:
            overflow = total_charge - self.charge_capacity

        self.lose_charge(overflow)

        self.practical_charges = filter_charges(self.filter_type, self.charges)

    def restore_charge(self, charges):
        # returns a picked-up cell's stored charge exactly as-is -- unlike add_charge,
        # this doesn't run it through filter_feeds' conversion rates, since it's not being
        # fed in fresh through the current filter, it's the same charge the cell was holding
        for color in self.charges:
            self.charges[color] += charges[color]

        total_charge = sum(self.charges.values())
        overflow = 0
        if total_charge > self.charge_capacity:
            overflow = total_charge - self.charge_capacity

        self.lose_charge(overflow)

        self.practical_charges = filter_charges(self.filter_type, self.charges)

    def update_laser_stats(self):
        laser_properties.set_laser_attributes(self.laser_attributes, self.practical_charges, self.filter_type, self.max_charge)

    def set_charges(self, white, blue, red):
        self.charges["white"] = white
        self.charges["blue"] = blue
        self.charges["red"] = red

    def add_charge(self, added_charge, charge_distribution):

        sum_added = 0
        for color in self.charges:
            add = charge_distribution[color] * added_charge

            addw = add * filter_feeds[self.filter_type][color][0]
            addb = add * filter_feeds[self.filter_type][color][1]
            addr = add * filter_feeds[self.filter_type][color][2]

            self.charges["white"] += addw
            self.charges["blue"] += addb
            self.charges["red"] += addr

            sum_added += addw + addb + addr

        total_charge = sum(self.charges.values())
        overflow = 0
        if total_charge > self.charge_capacity:
            overflow = total_charge - self.charge_capacity

        self.lose_charge(overflow)

        self.practical_charges = filter_charges(self.filter_type, self.charges)

        return sum_added - overflow

    def lose_charge(self, loss):
        if self.filter_type == "white":
            n_split = 3
            while n_split > 0:
                split_loss = loss / n_split
                underflowed = False
                for charge in self.charges:
                    if 0 < self.charges[charge] < split_loss:
                        loss -= self.charges[charge]
                        self.charges[charge] = 0
                        n_split -= 1
                        underflowed = True
                        break
                if not underflowed:
                    for charge in self.charges:
                        if self.charges[charge] > 0:
                            self.charges[charge] -= split_loss
                    break
        else:
            if loss < self.charges[self.filter_type]:
                self.charges[self.filter_type] -= loss
            else:
                loss -= self.charges[self.filter_type]
                self.charges[self.filter_type] = 0
                if loss < self.charges["white"]:
                    self.charges["white"] -= loss
                else:
                    loss -= self.charges["white"]
                    self.charges["white"] = 0
                    self.filter_type = "white"
                    return self.lose_charge(loss)

        self.practical_charges = filter_charges(self.filter_type, self.charges)
        if sum(self.charges.values()) > 0:
            return False
        self.reset_player()
        return True

    def get_cell_throw_charges(self):
        """Exact charge composition a thrown cell would take right now, or None if
        the player can't currently afford one -- shared by the actual throw and by
        the charge-up bar, so the bar never promises a throw the player can't make."""
        if self.n_cells <= 1:
            return None
        if self.filter_type == "white":
            # proportionate blend of current charges -- white does count toward itself here
            total = sum(self.charges.values())
            if total < CELL_CHARGE_COST:
                return None
            return {color: CELL_CHARGE_COST * self.charges[color] / total for color in self.charges}
        # blue/red: exclusive to that color -- white does NOT count toward it
        if self.charges[self.filter_type] < CELL_CHARGE_COST:
            return None
        cell_charges = {"white": 0, "blue": 0, "red": 0}
        cell_charges[self.filter_type] = CELL_CHARGE_COST
        return cell_charges

    def deal_damage(self, damage):
        self.queued_damage += damage

    def take_enemy_hit(self, damage, _terrain):
        self.deal_damage(damage)
        self.pending_hit_stop = HIT_STOP_DURATION
        self.pending_damage_flash = True
        _terrain.particles.spawn_light_particles(int(damage/4), self.color, 20, self.x, self.y)

    def drain_damage(self, damage):
        self.queued_drain_damage += damage

    def get_laser_start(self):
        return self.x - SPRITE_WIDTH / 2 + ARM_PIVOT_X, self.y - SPRITE_HEIGHT / 2 + ARM_PIVOT_Y + 3

    def tick(self, frame_length, _terrain: terrain.Terrain, mouse_pos, keys_down, events):
        if self.lose_charge(self.queued_damage) or self.lose_charge(self.queued_drain_damage):
            return True
        self.queued_damage = 0
        self.queued_drain_damage = 0

        self.y_speed = min(1, self.y_speed + 0.0015 * frame_length)
        if self.immunity_timer > 0:
            self.immunity_timer -= frame_length
            if self.immunity_timer < 0:
                self.immunity_timer = 0

        if events[pygame.K_RIGHT]:
            self.filter_change_right = True
            match self.filter_type:
                case "white":
                    self.filter_type = "blue"
                case "blue":
                    self.filter_type = "red"
                case "red":
                    self.filter_type = "white"

        if events[pygame.K_LEFT]:
            self.filter_change_right = False
            match self.filter_type:
                case "white":
                    self.filter_type = "red"
                case "blue":
                    self.filter_type = "white"
                case "red":
                    self.filter_type = "blue"

        if events[pygame.K_SPACE] and self.ability_timer == 0 and self.laser_attributes.passed_thresholds[self.filter_type][1]:
            match self.filter_type:
                case "white":
                    mx, my = mouse_pos
                    dx, dy = mx - self.x, my - self.y
                    d = dist(dx, dy)
                    self.x_speed = dx / d / 1.2
                    self.y_speed = dy / d / 2
                    self.ability_timer = self.ability_cooldown
                    _terrain.particles.spawn_pulse_particle(self.color, 40, self.x, self.y)
                case "blue":
                    self.y_speed -= 0.3
                    _terrain.new_knockback_circles.append([self.laser_attributes.base_kb * 5, self.x, self.y, self.laser_attributes.kb_range * 3, 1])
                    _terrain.particles.spawn_pulse_particle(self.color, self.laser_attributes.kb_range * 3, self.x, self.y, 800)
                    self.ability_timer = self.ability_cooldown
                case "red":
                    self.y_speed -= 0.3
                    # explosionSize=self.laserAttributes.baseXPL*3
                    # cTerrain.addAirPocketClump(self.x, self.y, explosionSize, layerIndex=cTerrain._layerForY(self.y), playerMade=True, spreading=1/5)
                    # should detect ground and spawn particles if detected

                    _terrain.new_player_damage_circles.append([self.laser_attributes.base_dmg, self.x, self.y, self.laser_attributes.dmg_range * 2, 1])
                    _terrain.particles.spawn_pulse_particle(self.color, self.laser_attributes.dmg_range * 2, self.x, self.y, 800)
                    self.ability_timer = self.ability_cooldown

        if keys_down["left_mouse"] and self.laser is None and self.laser_timer <= self.laser_attributes.cooldown / 4:
            new_laser = laser.Laser()
            self.laser = new_laser
            self.laser_ramps = 0
            self.laser_first_hit = True

        if events["left_mouse_up"] and self.laser is not None:
            self.laser_timer = self.laser.timer
            self.laser = None

        if events["right_mouse_up"]:
            hold_time = self.cell_throw_hold_timer
            self.cell_throw_hold_timer = 0

            cell_charges = self.get_cell_throw_charges()
            if cell_charges is not None:
                for color in self.charges:
                    self.charges[color] -= cell_charges[color]
                self.practical_charges = filter_charges(self.filter_type, self.charges)

                mx, my = mouse_pos
                dx, dy = mx - self.x, my - self.y
                d = dist(dx, dy)
                hold_fraction = min(1, hold_time / CELL_THROW_CHARGE_TIME)
                throw_speed = CELL_THROW_MIN_SPEED + (CELL_THROW_MAX_SPEED - CELL_THROW_MIN_SPEED) * hold_fraction
                _terrain.add_cell((self.x, self.y), (self.x_speed + dx / d * throw_speed, self.y_speed + dy / d * throw_speed), charges=cell_charges, filter_type=self.filter_type)
                self.n_cells -= 1
                self.update_charge_capacity()
        elif keys_down["right_mouse"]:
            self.cell_throw_hold_timer = min(self.cell_throw_hold_timer + frame_length, CELL_THROW_CHARGE_TIME)
        else:
            self.cell_throw_hold_timer = 0

        # bar only shows up if a throw would actually be affordable right now -- gated by
        # the same check the real throw uses, so it never promises a throw the player can't make
        self.cell_charge_bar.set_active(keys_down["right_mouse"] and self.get_cell_throw_charges() is not None)

        self.ability_timer -= frame_length
        self.ability_timer = max(0, self.ability_timer)

        self.laser_timer -= frame_length
        self.laser_timer = max(0, self.laser_timer)

        if self.laser:
            start_x, start_y = self.get_laser_start()
            locked = self.laser.update_laser(
                _terrain,
                start_x + 10 * math.cos(self.arm_angle),
                start_y + 10 * math.sin(-self.arm_angle),
                -self.arm_angle,
                self.laser_attributes.distance,
                self.laser_attributes.cooldown,
            )
            self.laser.tick(frame_length)
            if self.laser.damage_frame:
                if not locked:
                    self.laser_ramps = 0
                if self.laser.collision:
                    if self.laser_first_hit:
                        self.pending_hit_stop = max(self.pending_hit_stop, LASER_HIT_STOP_DURATION)
                        self.pending_laser_flash = True
                    else:
                        self.pending_laser_ramp_flash = True
                    point = self.laser.collision[0]
                    x, y = point
                    explosion_size = laser_properties.get_laser_expl(self.laser_attributes, self.laser_first_hit, self.laser_ramps)
                    _terrain.add_air_pocket_clump(x, y, explosion_size, player_made=True, spreading=1 / 5, spawn_particles=self.laser.collision[1] == "ground")
                    if self.laser.collision[1] == "ground":
                        HealthBar.targeted = None

                    _terrain.new_knockback_circles.append(
                        [laser_properties.get_laser_kb(self.laser_attributes, self.laser_first_hit, self.laser_ramps), x, y, self.laser_attributes.kb_range, self.laser_attributes.area_kb_falloff]
                    )
                    _terrain.new_player_damage_circles.append(
                        [laser_properties.get_laser_dmg(self.laser_attributes, self.laser_first_hit, self.laser_ramps), x, y, self.laser_attributes.dmg_range, self.laser_attributes.area_dmg_falloff]
                    )
                    _terrain.particles.spawn_pulse_particle(self.color, self.laser_attributes.dmg_range, x, y)
                    _terrain.particles.spawn_pulse_particle(self.color, self.laser_attributes.kb_range, x, y)

                else:
                    HealthBar.targeted = None

                self.laser_first_hit = False
                self.laser_ramps += 1

                if self.lose_charge(0.5):
                    return True

                # spawn impact — position follows live laser, freezes when laser released
                end_x = self.laser.start_x + math.cos(self.laser.angle) * self.laser.length
                end_y = self.laser.start_y + math.sin(self.laser.angle) * self.laser.length
                self.impacts.append(LaserImpact(end_x, end_y, self.laser.angle, self.laser, self._impact_im_gs))

        # tick impacts, passing current active lasers so they can track position
        for i in range(len(self.impacts) - 1, -1, -1):
            if self.impacts[i].tick(frame_length, self.laser):
                del self.impacts[i]

        for knockback_circle in _terrain.knockback_circles:
            dx = self.x - knockback_circle[1]
            dy = self.y - knockback_circle[2]
            if dx == 0 and dy == 0:
                dy = -1  # circle acts as if it's one pixel below
            distance = dist(dx, dy)
            knockback = knockback_circle[0]

            self.x_speed += NOMINAL_FRAME_MS * dx / distance * knockback / 60
            self.y_speed += NOMINAL_FRAME_MS * dy / distance * knockback / 60

        for nest in _terrain._nests_near(self.x, self.y, 400):
            if nest.stage == nest.max_stage and self.charge_capacity > self.charges[nest.nest_type] and nest.within_effect_radius(self.x, self.y) and nest.charge > 0:
                _terrain.add_interaction_display(nest.interaction_display)
                if nest.interaction_display.active:
                    charge_gain = self.add_charge(nest.charge_rate * frame_length, nest.charging)
                    nest.lose_charge(charge_gain)
                    _terrain.particles.spawn_light_particles(frame_random(frame_length, 30), nest.color, random.randint(5, 20), nest.x, nest.y, target=(self.x, self.y))
            else:
                _terrain.remove_interaction_display(nest.interaction_display, nest.charge == 0 or self.charge_capacity == self.charges[nest.nest_type])
        for chunk in _terrain._chunks_near(self.x, self.y, 400, 0):
            cells = chunk.cells
            for i in range(len(cells) - 1, -1, -1):
                cell = cells[i]
                if cell.within_interaction_radius((self.x, self.y)):
                    _terrain.add_interaction_display(cell.interaction_display)
                    if cell.interaction_display.active:  # should be triggered by an event not a key down
                        _terrain.remove_interaction_display(cell.interaction_display, True)
                        cells.remove(cell)
                        self.n_cells += 1
                        self.restore_charge(cell.charges)
                else:
                    _terrain.remove_interaction_display(cell.interaction_display)

        self.update_charge_capacity()
        self.update_laser_stats()

        if self.on_ground:
            self.coyote_timer = COYOTE_TIME
        else:
            self.coyote_timer = max(0, self.coyote_timer - frame_length)

        if keys_down[pygame.K_w] and self.coyote_timer > 0:
            self.y_speed = -0.4
            self.coyote_timer = 0

        moving_left = keys_down[pygame.K_a]
        moving_right = keys_down[pygame.K_d]

        if self.on_ground:
            # snappy ground control: instant turnaround and instant stop, no coasting
            if moving_left and self.x_speed > 0:
                self.x_speed = 0
            if moving_right and self.x_speed < 0:
                self.x_speed = 0
            if moving_left:
                self.x_speed = max(-GROUND_MAX_SPEED, self.x_speed - GROUND_ACCEL * frame_length)
            if moving_right:
                self.x_speed = min(GROUND_MAX_SPEED, self.x_speed + GROUND_ACCEL * frame_length)
            if not (moving_left or moving_right):
                self.x_speed = 0
        else:
            if moving_left:
                self.x_speed -= AIR_ACCEL * frame_length
            if moving_right:
                self.x_speed += AIR_ACCEL * frame_length
            self.x_speed *= AIR_FRICTION**frame_length

        if self.x < 50:
            self.x_speed += (50 - self.x) / 10000 * frame_length
        elif self.x > _terrain.world_width - 50:
            self.x_speed -= (self.x - _terrain.world_width + 50) / 10000 * frame_length

        self.move_vertical(frame_length, _terrain)
        self.move_horizontal(frame_length, _terrain)

        self.update_color()
        self.update_costume(frame_length, mouse_pos)

        if self.laser:
            start_x, start_y = self.get_laser_start()
            self.laser.update_laser(
                _terrain,
                start_x + 10 * math.cos(self.arm_angle),
                start_y + 10 * math.sin(-self.arm_angle),
                -self.arm_angle,
                self.laser_attributes.distance,
                self.laser_attributes.cooldown,
            )
        return False

    def move_horizontal(self, frame_length, _terrain: terrain.Terrain):

        # TODO - add slope platforming

        self.x += frame_length * self.x_speed
        self.update_rect()
        if self.colliding_with_terrain(_terrain):
            slope_tolerance = math.ceil(3 * abs(frame_length * self.x_speed))
            for i in range(slope_tolerance):
                self.y -= 1
                self.update_rect()
                if not self.colliding_with_terrain(_terrain):
                    self.x_speed -= self.x_speed * i / slope_tolerance
                    return
            self.y += slope_tolerance
            self.x -= frame_length * self.x_speed
            backs = math.ceil(abs(frame_length * self.x_speed / 1))
            for i in range(backs):
                self.x += frame_length * self.x_speed / backs
                self.update_rect()
                if self.colliding_with_terrain(_terrain):
                    self.x -= frame_length * self.x_speed / backs
                    self.update_rect()
                    break
            self.x_speed = 0

    def move_vertical(self, frame_length, _terrain: terrain.Terrain):
        self.on_ground = False
        self.y += frame_length * self.y_speed
        self.update_rect()
        if self.colliding_with_terrain(_terrain):
            self.check_element_touch(_terrain)
            if self.y_speed > 0:
                self.on_ground = True
                if not _terrain.nests_collide_rect(self.rect):
                    _terrain.particles.spawn_mining_particles(
                        int(abs((abs(max(0.005 * frame_length, abs(self.x_speed)) - 0.005 * frame_length) + 3 * (self.y_speed - 0.0015 * frame_length)) * 12)), (0, 0, 0), 20, self.x, self.y + self.height / 2
                    )
            if self.y_speed < 0:
                slope_tolerance = math.ceil(abs(0.5 * frame_length * self.y_speed))
                for i in range(slope_tolerance):
                    self.x -= 1
                    self.update_rect()
                    if not self.colliding_with_terrain(_terrain):
                        return
                self.x += slope_tolerance
                for i in range(slope_tolerance):
                    self.x += 1
                    self.update_rect()
                    if not self.colliding_with_terrain(_terrain):
                        return
                self.x -= slope_tolerance
            self.y -= frame_length * self.y_speed
            backs = math.ceil(abs(frame_length * self.y_speed / 1))
            for i in range(backs):
                self.y += frame_length * self.y_speed / backs
                self.update_rect()
                if self.colliding_with_terrain(_terrain):
                    self.y -= frame_length * self.y_speed / backs
                    self.update_rect()
                    break
            self.y_speed = 0

    def draw(self, surface, frame, hitboxes=False, offset_x=0, offset_y=0, tilt=0):
        cam_x, cam_y, zoom = frame
        if hitboxes:
            self.update_rect()
            l = float(self.rect.left)
            r = float(self.rect.right - 1)
            t = float(self.rect.top)
            b = float(self.rect.bottom - 1)
            pygame.draw.line(surface, self.color, ((l - cam_x) * zoom + offset_x, (t - cam_y) * zoom + offset_y), ((l - cam_x) * zoom + offset_x, (b - cam_y) * zoom + offset_y))
            pygame.draw.line(surface, self.color, ((r - cam_x) * zoom + offset_x, (t - cam_y) * zoom + offset_y), ((r - cam_x) * zoom + offset_x, (b - cam_y) * zoom + offset_y))
            pygame.draw.line(surface, self.color, ((l - cam_x) * zoom + offset_x, (t - cam_y) * zoom + offset_y), ((r - cam_x) * zoom + offset_x, (t - cam_y) * zoom + offset_y))
            pygame.draw.line(surface, self.color, ((l - cam_x) * zoom + offset_x, (b - cam_y) * zoom + offset_y), ((r - cam_x) * zoom + offset_x, (b - cam_y) * zoom + offset_y))
            if self.laser:
                self.laser.draw(surface, frame, self.color, hitboxes=hitboxes, offset_x=offset_x, offset_y=offset_y)
        else:
            boosted_color = (channel_bound(self.color[0] + 30), channel_bound(self.color[1] + 30), channel_bound(self.color[2] + 30))
            player_surface = self._player_draw_surface[zoom]
            player_surface.fill((boosted_color[0], boosted_color[1], boosted_color[2], 255))
            player_surface.blit(self.player_im_gs[zoom][self.facing][self.animation_type][self.animation_frame], (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

            if tilt != 0:
                player_surface = pygame.transform.rotate(player_surface, tilt)

            adjusted_arm_angle = self.arm_angle
            if self.facing == "left":
                adjusted_arm_angle += math.pi
            arm, arm_offset_x, arm_offset_y = rotate_and_get_offset(self.player_im_gs[zoom][self.facing]["arm"][0], zoom * ARM_PIVOT_X, zoom * ARM_PIVOT_Y, adjusted_arm_angle)
            width, height = arm.get_size()
            if self._arm_draw_surface_size != (width, height):
                self._arm_draw_surface = pygame.Surface((width, height), flags=pygame.SRCALPHA)
                self._arm_draw_surface_size = (width, height)
            arm_surface = self._arm_draw_surface
            arm_surface.fill((boosted_color[0], boosted_color[1], boosted_color[2], 255))
            arm_surface.blit(arm, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

            surface.blit(player_surface, ((self.x - SPRITE_WIDTH / 2 - cam_x) * zoom + offset_x, (3 + self.rect.bottom - SPRITE_HEIGHT - cam_y) * zoom + offset_y))
            surface.blit(arm_surface, ((self.x - SPRITE_WIDTH / 2 - cam_x) * zoom + arm_offset_x + offset_x, (3 + self.rect.bottom - SPRITE_HEIGHT - cam_y) * zoom + arm_offset_y + offset_y))
            if self.laser:
                self.laser.draw(surface, frame, boosted_color, offset_x=offset_x, offset_y=offset_y)
            # draw impact animations — rendered after laser so they appear on top
            for impact in self.impacts:
                impact.draw(surface, frame, boosted_color, zoom, offset_x=offset_x, offset_y=offset_y)

    def draw_cell_charge_bar(self, surface, frame, offset_x=0, offset_y=0):
        cam_x, cam_y, zoom = frame
        side = 1 if self.facing == "right" else -1
        bar_x = self.x + side * CELL_CHARGE_BAR_SIDE_OFFSET
        hold_fraction = self.cell_throw_hold_timer / CELL_THROW_CHARGE_TIME
        self.cell_charge_bar.draw(surface, self.color, ((bar_x - cam_x) * zoom + offset_x, (self.y - cam_y) * zoom + offset_y), hold_fraction)

    def colliding_with_terrain(self, _terrain):
        return _terrain.collide_rect(self.rect)

    def check_element_touch(self, _terrain):
        """Broad-phase: elements near self.rect via chunk lookup, filtered
        down by an AABB check against each candidate's own (bigger) footprint
        rect. Narrow-phase: a precise pixel mask overlap against the
        element's interaction_hitbox -- needed because e.g. Spike's hitbox
        art is a few thin, jagged peaks inside a mostly-empty square
        footprint, so the AABB alone would fire touch reactions from a
        player nowhere near the actual art."""
        for e in _terrain._elements_touching_rect(self.rect):
            if not self.rect.colliderect(e.get_footprint_rect()):
                continue
            interaction_mask = e.get_interaction_hitbox_mask()
            if interaction_mask is None:
                continue
            player_mask = pygame.mask.Mask((self.rect.width, self.rect.height), fill=True)
            offset = (int(self.rect.left - e.left), int(self.rect.top - e.top))
            if interaction_mask.overlap(player_mask, offset) is not None:
                e.on_touch(self, _terrain)
