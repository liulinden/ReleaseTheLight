import random
from scripts.enemies._enemy import Enemy

class BasicFlying(Enemy):
    def __init__(self, default_zooms, color, size, nest_health, x, y):
        health = nest_health * 0.5
        damage = nest_health * 1

        super().__init__(default_zooms, "1", color, x, y, size, health, damage, 0.3)

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
    
    def tick(self, frame_length, _terrain, player):
        if self.mode != "Spawn":
            if self.tick_damage_and_knockback(frame_length, _terrain, player): return True
            self.tick_enemy_behavior(frame_length, player)
            self.attempt_movement(frame_length, _terrain)
            self.handle_attack(player)
            if self.check_despawn(player): return True
        self.update_costume(frame_length, player)
        return False