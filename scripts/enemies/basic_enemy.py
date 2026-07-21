from scripts.enemies._enemy import Enemy

class BasicEnemy(Enemy):
    def __init__(self, default_zooms, color, size, nest_health, x, y):
        health = nest_health * 0.5
        damage = nest_health * 1

        super().__init__(default_zooms, "1", color, x, y, size, health, damage, 0.3)