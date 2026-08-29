from scripts.structures.structure import Structure
import pygame

WIDTH = 150
HEIGHT = 100


class Checkpoint(Structure):
    """Guaranteed structure placed once per world, directly below the
    player's spawn point (see Terrain.generate_structures). No images yet
    -- just a single erase_rect covering its whole footprint, so it carves
    a safe air pocket to spawn into regardless of what cave generation
    happened to put there."""

    def __init__(self, x, y, default_zooms):
        super().__init__(x, y, WIDTH, HEIGHT, default_zooms, erase_rects=[(0, 0, WIDTH, HEIGHT)])

    def draw_back(self, surface, frame, offset_x=0, offset_y=0):
        left, top, zoom = frame
        struct_left, struct_top = self._footprint_screen_pos(frame)
        rect = pygame.Rect(struct_left,struct_top, WIDTH*zoom, HEIGHT*zoom)
        pygame.draw.rect(surface, (255,255,255), rect)

    def draw_front(self, surface, frame, offset_x=0, offset_y=0):
        left, top, zoom = frame
        struct_left, struct_top = self._footprint_screen_pos(frame)
        rect = pygame.Rect(struct_left,struct_top + HEIGHT*zoom*3/4, WIDTH*zoom, HEIGHT*zoom*1/4)
        pygame.draw.rect(surface, (255,0,0), rect)

    def get_collide_hitbox_surface(self, zoom):
        t_s = pygame.Surface((WIDTH,HEIGHT))
        pygame.draw.rect(t_s, (255,255,255), pygame.Rect(0, HEIGHT*zoom*3/4, WIDTH*zoom, HEIGHT*zoom*1/4))
        return t_s
