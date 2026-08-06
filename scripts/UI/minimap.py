import pygame

# from terrain import Terrain

margin_x, margin_y = 20, 20
display_size = 200
minimap_r = 2000
scale = display_size / (minimap_r * 2)


def map_coordinates(coords, reference, map_center=(0, 0)):
    return (coords[0] - reference[0]) * scale + map_center[0], (coords[1] - reference[1]) * scale + map_center[1]


class Minimap:
    def __init__(self, world_width, world_height):
        self.player_x, self.player_y = 0, 0
        self.nests = []
        self.world_width, self.world_height = world_width, world_height

    def update(self, player, terrain):
        self.player_x, self.player_y = player.x, player.y
        self.nests = terrain._nests_touching_rect(pygame.Rect(self.player_x - minimap_r, self.player_y - minimap_r, minimap_r * 2, minimap_r * 2))

    def draw(self, surface: pygame.Surface, color):
        h = surface.get_height()
        left = margin_x
        top = h - display_size - margin_y
        cx, cy = left + display_size / 2, top + display_size / 2
        for nest in self.nests:
            if nest.stage == nest.max_stage:
                x, y, nest_color = *map_coordinates((nest.x, nest.y), (self.player_x, self.player_y)), nest.color
                if 0 < x + display_size / 2 < display_size and 0 < y + display_size / 2 < display_size:
                    pygame.draw.circle(surface, nest_color, (x + cx, y + cy), 3)

        pygame.draw.line(surface, color, (cx - display_size / 20, cy), (cx + display_size / 20, cy), 1)
        pygame.draw.line(surface, color, (cx, cy - display_size / 20), (cx, cy + display_size / 20), 1)

        pygame.draw.rect(surface, color, pygame.Rect(left, top, display_size, display_size), 1)
        # pygame.draw.circle(surface, color, (cx, cy), display_size / 2, 1)

        # y
        # pygame.draw.line(surface, color, (left, top), (left + display_size / 10, top), 2)
        # pygame.draw.line(surface, color, (left, top + display_size), (left + display_size / 10, top + display_size), 2)
        # pygame.draw.line(surface, color, (left, top + display_size * self.player_y / self.world_height), (left + display_size / 10, top + display_size * self.player_y / self.world_height), 6)
        # pygame.draw.line(surface, color, (left + + display_size / 20, top), (left + display_size / 20, top + display_size), 2)

        # x
        # pygame.draw.line(surface, color, (left, top), (left + display_size / 10, margin_y), 2)
        # pygame.draw.line(surface, color, (left, margin_y + display_size), (left + display_size / 10, margin_y + display_size), 2)
        # pygame.draw.line(surface, color, (left, margin_y + display_size * self.player_y / self.world_height), (left + display_size / 10, margin_y + display_size * self.player_y / self.world_height), 6)
        # pygame.draw.line(surface, color, (left + 7, margin_y), (left + 7, margin_y + display_size), 2)
