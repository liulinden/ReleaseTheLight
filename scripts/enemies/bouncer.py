import math
import random

from scripts.enemies._enemy import Enemy
from scripts.util import dist, normalize_1d


class Bouncer(Enemy):
    size_range = (20, 40)
    costume = "1"
    health_factor = 0.05

    def __init__(self, default_zooms, nest, color, size, nest_health, x, y):
        super().__init__(default_zooms, nest, Bouncer.costume, color, x, y, size, nest_health * Bouncer.health_factor)
        self.knockback = 0.3
        self.damage = nest_health * 0.5
        self.knockback_resistance = 0.5
        self.gravity_multiplier = 0.1
        self.speed = 0.5
        self.elasticity = 1  # independent of cells.py's elasticity -- bouncer stays fully elastic, no friction/drag

    def attempt_movement(self, frame_length, _terrain):
        self.on_ground = False

        self.update_rect()
        if self.colliding_with_terrain(_terrain):
            return  # already embedded -- matches cells.py's guard

        vx, vy = self.x_speed, self.y_speed
        dx, dy = frame_length * vx, frame_length * vy
        orig_xy = self.x, self.y

        self.x += dx
        self.y += dy
        self.update_rect()
        if not self.colliding_with_terrain(_terrain):
            return

        self.x, self.y = orig_xy
        self.update_rect()

        # ported from cells.py's attempt_movement: distance-capped substeps (never more
        # than 1px per step) so a fast bounce can't skip clean through thin terrain, plus
        # a mid-substep check whenever a step would cross a pixel boundary on both axes at
        # once -- otherwise the endpoint-only check can miss a pixel it skipped diagonally.
        remaining = frame_length
        while remaining > 0:
            speed = dist(vx, vy)
            if speed == 0:
                return
            tick_length = min(remaining, 1 / speed)

            dx, dy = vx * tick_length, vy * tick_length
            ox, oy = self.x, self.y

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
                self.x, self.y = ox, oy
                self.update_rect()

                collide_x, collide_y = collision
                normal = _terrain.get_normal(collide_x - normalize_1d(dx), collide_y - normalize_1d(dy))

                mag = dist(*normal)
                if mag == 0:
                    return  # degenerate normal -- leave speed/position as-is

                # same reflection math as cells.py's substep loop, minus friction/absorption
                # (bouncer has neither -- it always bounces elastically on real contact)
                nx, ny = normal[0] / mag, normal[1] / mag
                scalar = nx * vx + ny * vy
                new_x_speed = vx - scalar * nx
                new_y_speed = vy - scalar * ny
                new_x_speed -= scalar * nx * self.elasticity
                new_y_speed -= scalar * ny * self.elasticity

                self.x_speed, self.y_speed = new_x_speed, new_y_speed
                self.on_ground = True
                return

            remaining -= tick_length

        self.x_speed, self.y_speed = vx, vy

    def tick_enemy_behavior(self, frame_length, player):
        if self.mode == "walk":
            if abs(player.x - self.x) > self.size / 2 or abs(player.y - self.y) > self.size / 2:
                if self.on_ground and random.randint(1, 50) < frame_length:
                    self.y_speed = -0.2
                    rand = random.randint(0, 3)
                    if (player.x < self.x and rand != 3) or rand == 0:
                        self.x_speed -= 0.2
                    else:
                        self.x_speed += 0.2
                else:
                    rand = random.randint(0, 3)
                    if (player.x < self.x and rand != 3) or rand == 0:
                        if self.on_ground:
                            self.x_speed -= 0.001 * frame_length * self.speed
                        else:
                            self.x_speed -= 0.0003 * frame_length * self.speed
                    else:
                        if self.on_ground:
                            self.x_speed += 0.001 * frame_length * self.speed
                        else:
                            self.x_speed += 0.0003 * frame_length * self.speed
            else:
                self.mode = "attack"
                self.animation_timer = 0

            if self.on_ground:
                self.x_speed *= 0.98**frame_length
            # else:
            #    self.x_speed *= 0.993**frame_length
