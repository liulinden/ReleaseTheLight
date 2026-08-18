from scripts.enemies._enemy import Enemy


class BasicEnemy(Enemy):
    size_range = (20, 70)
    costume = "1"
    health_factor = 0.2

    def __init__(self, default_zooms, nest, color, size, nest_health, x, y):
        super().__init__(default_zooms, nest, BasicEnemy.costume, color, x, y, size, nest_health * BasicEnemy.health_factor)
