import random, pygame

from scripts.enemies import basic_enemy, basic_flying
from scripts.enemies._enemy import Enemy, costume_dimensions

light_gradient = None
enemy_animations = {}

enemy_sizes = {basic_enemy.BasicEnemy: (40, 70), basic_flying.BasicFlying: (20,50)}
enemy_costumes = {basic_enemy.BasicEnemy: "1", basic_flying.BasicFlying: "1"}

eligible_enemies = {
    "white": [basic_enemy.BasicEnemy], 
    "blue": [basic_enemy.BasicEnemy, basic_flying.BasicFlying], 
    "red": [basic_enemy.BasicEnemy]}

def get_enemy(_terrain, player, nest_type, color, nest_health, nest_x, nest_y, nest_size):
    for i in range(20):
        x, y = random.randint(int(nest_x - 10 - nest_size / 2), int(nest_x + 10 + nest_size / 2)), random.randint(int(nest_y - 10 - nest_size / 2), int(nest_y + 10 + nest_size / 2))
        
        eligible = eligible_enemies[nest_type]
        variant = eligible[random.randint(0, len(eligible)-1)]
        
        size_min, size_max = enemy_sizes[variant]
        size = random.randint(size_min, size_max)
        width = size * costume_dimensions[enemy_costumes[variant]][0]
        height = size * costume_dimensions[enemy_costumes[variant]][1]

        new_enemy_rect = pygame.Rect(x - width / 2, y - height / 2, width, height)
        if not (_terrain.collide_rect(new_enemy_rect) or new_enemy_rect.colliderect(player.rect)):
            new_enemy = variant(_terrain.default_zooms, color, size, nest_health, x, y)
            new_enemy.spawn_particles(_terrain)
            return new_enemy
    return False