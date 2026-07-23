import math
import random

from scripts.enemies._enemy import Enemy
from scripts.util import dist, get_bounced_vector


class Bouncer(Enemy):
    size_range = (20, 40)
    costume = "1"
    health_factor = 0.2

    def __init__(self, default_zooms, color, size, nest_health, x, y):
        super().__init__(default_zooms, Bouncer.costume, color, x, y, size, nest_health * Bouncer.health_factor)
        self.knockback = 0.3
        self.damage = nest_health * 0.5
        self.knockback_resistance = 0.5
        self.gravity_multiplier = 0.1
        self.speed = 0.5

    def attempt_movement(self, frame_length, _terrain):
        self.on_ground = False
        self.x += frame_length * self.x_speed
        self.y += frame_length * self.y_speed
        self.update_rect()
        if self.colliding_with_terrain(_terrain):
            self.x -= frame_length * self.x_speed
            self.y -= frame_length * self.y_speed
            backs = int(math.ceil(frame_length * dist(self.x_speed, self.y_speed)))
            for i in range(backs):
                self.x += frame_length * self.x_speed / backs
                self.y += frame_length * self.y_speed / backs
                self.update_rect()
                collision = self.colliding_with_terrain(_terrain)
                if collision:
                    collision_x, collision_y = collision

                    self.x -= frame_length * self.x_speed / backs
                    self.y -= frame_length * self.y_speed / backs
                    self.update_rect()

                    normal = _terrain.get_normal(collision_x, collision_y)
                    self.x_speed, self.y_speed = get_bounced_vector((self.x_speed, self.y_speed), normal)
                    # self.x_speed *= 0.9
                    # self.y_speed *= 0.99
                    self.on_ground = True

                    return
            self.x_speed = 0

    def tick_enemy_behavior(self, frame_length, player):
        if self.mode == "Walk":
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
                self.mode = "Attack"
                self.animation_timer = 0

            if self.on_ground:
                self.x_speed *= 0.98**frame_length
            # else:
            #    self.x_speed *= 0.993**frame_length
