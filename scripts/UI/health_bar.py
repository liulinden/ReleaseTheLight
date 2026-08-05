import pygame

from scripts.util import draw_rounded_line


class HealthBar:
    targeted = None

    def __init__(self, max_health, thickness=9):
        self.last_triggered = 0
        self.max_health = max_health
        self.thickness = thickness // 2 * 2 + 1  # thickness must be odd
        self.scale = 15 / max_health**0.8
        self.width = self.max_health * self.scale + self.thickness
        self.surface = pygame.Surface((self.width, self.thickness), pygame.SRCALPHA)

    def trigger(self, direct=False):
        self.last_triggered = pygame.time.get_ticks()
        if direct:
            HealthBar.targeted = self

    def draw(self, surface, color, coords, health, time=None):
        if time is None:
            time = pygame.time.get_ticks()
        opacity = max(0, 255 - (time - self.last_triggered - 500) / 2)
        if opacity > 0:
            self.surface.fill((0, 0, 0, 0))
            x, y = coords
            if HealthBar.targeted is self:
                draw_rounded_line(self.surface, color, (self.thickness // 2, self.thickness // 2), (self.width - self.thickness // 2, self.thickness // 2), self.thickness)
                draw_rounded_line(self.surface, (0, 0, 0), (self.thickness // 2, self.thickness // 2), (self.width - self.thickness // 2, self.thickness // 2), self.thickness - 4)
            else:
                draw_rounded_line(self.surface, (0, 0, 0), (self.thickness // 2, self.thickness // 2), (self.width - self.thickness // 2, self.thickness // 2), self.thickness)
            draw_rounded_line(self.surface, color, (self.thickness // 2, self.thickness // 2), (self.thickness // 2 + self.scale * health, self.thickness // 2), self.thickness - 4)

            left = x - self.scale * self.max_health / 2 - self.thickness / 2
            top = y - self.thickness / 2
            self.surface.set_alpha(opacity)

            surface.blit(self.surface, (left, top))
