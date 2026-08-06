import pygame

from scripts.UI.interaction_display import InteractionDisplay
from scripts.util import about_equal, dist, get_bounced_vector, normalize_1d


def validate_cell_coords(_terrain, coords):
    x, y = coords
    rect = pygame.Rect(x - Cell.width / 2, y - Cell.height / 2, Cell.width, Cell.height)
    return not _terrain.collide_rect(rect)

class Cell:
    width = 10
    height = 20
    def __init__(self, coords, velocities):
        self.w = Cell.width
        self.h = Cell.height
        self.x, self.y = coords
        self.x_speed, self.y_speed = velocities
        self.rect = pygame.Rect(self.x - self.w / 2, self.y - self.h / 2, self.w, self.h)
        self.r = dist(self.w, self.h)
        self.interaction_display = InteractionDisplay((self.x, self.y + self.h / 2), (pygame.K_e, ""))
        self.frames_since_moved = 0

    def tick_knockback(self, frame_length, _terrain, player):
        affected = False
        for knockback_circle in _terrain.knockback_circles:
            pow, x, y, r, falloff = knockback_circle

            dx = self.x - x
            dy = self.y - y
            d = dist(dx, dy)
            if player.laser:
                if player.laser.laser_target is self:
                    self.x_speed += frame_length * dx / d * pow / 30
                    self.y_speed += frame_length * dy / d * pow / 30
                    affected = True
                elif d < r + self.r:
                    self.x_speed += frame_length * dx / d * pow * falloff / 30
                    self.y_speed += frame_length * dy / d * pow * falloff / 30
                    affected = True
            elif d < r + self.r:
                self.x_speed += frame_length * dx / d * pow * falloff / 30
                self.y_speed += frame_length * dy / d * pow * falloff / 30
                affected = True
        return affected

    def tick_gravity(self, frame_length):
        self.y_speed = min(2, self.y_speed + 0.0015 * frame_length)

    def _resolve_collision(self, velocity, normal, elasticity, friction, frame_length, bounce_threshold=0.05):
        vx, vy = velocity
        mag = dist(*normal)
        if mag == 0:
            return vx, vy  # degenerate normal, shouldn't happen but guard anyway

        nx, ny = normal[0] / mag, normal[1] / mag
        normal_speed = vx * nx + vy * ny

        if normal_speed >= 0:
            return vx, vy  # already moving away from / tangent to surface
        if abs(normal_speed) > bounce_threshold:
            return get_bounced_vector((vx, vy), (nx, ny), elasticity)

        # resting/sliding contact: cancel the into-surface component,
        # leaving only the tangential (sliding) velocity
        tx = vx - normal_speed * nx
        ty = vy - normal_speed * ny

        # apply friction as a linear deceleration along the tangent
        speed = dist(tx, ty)
        if speed > 0:
            new_speed = max(0.0, speed - friction * frame_length)
            scale = new_speed / speed
            tx *= scale
            ty *= scale

        return tx, ty

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
            print("started stuck")
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

            self.x += dx
            self.y += dy

            self.update_rect()
            collision = self.colliding_with_terrain(_terrain)
            if collision:
                if not self._find_clearance(_terrain, vx, vy):
                    self.x, self.y = ox, oy

                    collide_x, collide_y = collision
                    normal = _terrain.get_normal(collide_x - normalize_1d(dx), collide_y - normalize_1d(dy))

                    mag = dist(*normal)
                    if mag == 0:
                        print("something's fishy")
                        return
                    nx, ny = normal[0] / mag, normal[1] / mag

                    scalar = nx * vx + ny * vy
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

    def tick(self, frame_length, _terrain, player):
        if self.tick_knockback(frame_length, _terrain, player) or self.frames_since_moved <= 2:
            last_x, last_y = self.x, self.y
            self.tick_gravity(frame_length)
            self.attempt_movement(frame_length, _terrain)

            if not (about_equal(last_x, self.x) and about_equal(last_y, self.y)):
                self.interaction_display.update_coordinates((self.x, self.y + self.h / 2))
                self.frames_since_moved = 0
            self.frames_since_moved += 1

    def update_rect(self):
        self.rect.x, self.rect.y = self.x - self.w / 2, self.y - self.h / 2

    def colliding_with_terrain(self, _terrain):
        return _terrain.collide_rect(self.rect)

    def draw(self, surface, frame, hitbox=False, offset_x=0, offset_y=0):
        cam_x, cam_y, zoom = frame

        self.update_rect()
        vis_rect = (self.rect.left - cam_x) * zoom + offset_x, (self.rect.top - cam_y) * zoom + offset_y, self.w * zoom, self.h * zoom
        pygame.draw.rect(surface, (0, 0, 0), vis_rect, 2)

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
