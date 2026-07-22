from scripts.enemies._enemy import Enemy

class BasicEnemy(Enemy):
    size_range = (40,70)
    costume = "1"
    health_factor = 0.5

    def __init__(self, default_zooms, color, size, nest_health, x, y):
        super().__init__(default_zooms, BasicEnemy.costume, color, x, y, size, nest_health * BasicEnemy.health_factor)
        