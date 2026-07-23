import random

from scripts.enemies._enemy import Enemy


class BasicFlying(Enemy):
    size_range = (20, 50)
    costume = "1"
    health_factor = 0.5

    def __init__(self, default_zooms, color, size, nest_health, x, y):
        super().__init__(default_zooms, BasicFlying.costume, color, x, y, size, nest_health * BasicFlying.health_factor)
        self.knockback = 0.1
        self.speed = 1.5
        self.knockback_resistance = 0.8
        self.gravity_multiplier = 0

    def tick_enemy_behavior(self, frame_length, player):
        if self.mode == "Walk":
            if abs(player.x - self.x) > self.size / 2 or abs(player.y - self.y) > self.size / 2:
                rand = random.randint(0, 3)
                if (player.x < self.x and rand != 3) or rand == 0:
                    self.x_speed -= 0.0003 * frame_length * self.speed
                else:
                    self.x_speed += 0.0003 * frame_length * self.speed
                rand = random.randint(0, 3)
                if (player.y < self.y and rand != 3) or rand == 0:
                    self.y_speed -= 0.0003 * frame_length * self.speed
                else:
                    self.y_speed += 0.0003 * frame_length * self.speed
                self.x_speed *= 0.995**frame_length
                self.y_speed *= 0.995**frame_length
            else:
                self.mode = "Attack"
                self.animation_timer = 0
