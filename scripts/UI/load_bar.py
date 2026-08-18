import pygame

from scripts.util import draw_rounded_line


class LoadBar:
    """Generic vertical charge/loading bar. Visually matches HealthBar (dark
    outline, lights up when full) but oriented vertically, fills bottom-up,
    and is driven purely by an external 0-1 fraction plus an active/inactive
    flag -- it doesn't know or care what it's measuring. Positioning is also
    left entirely to the caller (draw() just takes a center coordinate),
    so this stays reusable for any future "hold to charge something" UI.
    """

    FADE_MS = 120  # quick fade in on activate / fade out on deactivate

    def __init__(self, length, thickness=9):
        self.length = length
        self.thickness = thickness // 2 * 2 + 1  # must be odd, same convention as HealthBar
        self.height = self.length + self.thickness
        self.surface = pygame.Surface((self.thickness, self.height), pygame.SRCALPHA)

        self.active = False
        self.last_change = 0
        self.lit = False  # fraction >= 1 -- mirrors HealthBar's "targeted" glow, driven by fullness instead

    def set_active(self, active):
        if active != self.active:
            self.active = active
            self.last_change = pygame.time.get_ticks()

    def draw(self, surface, color, coords, fraction, time=None):
        if time is None:
            time = pygame.time.get_ticks()

        elapsed = time - self.last_change
        progress = 1 if self.FADE_MS <= 0 else max(0, min(1, elapsed / self.FADE_MS))
        opacity = 255 * (progress if self.active else 1 - progress)
        if opacity <= 0:
            return

        fraction = max(0, min(1, fraction))
        self.lit = fraction >= 1

        self.surface.fill((0, 0, 0, 0))

        cx = self.thickness // 2
        top = (cx, self.thickness // 2)
        bottom = (cx, self.height - self.thickness // 2)

        if self.lit:
            draw_rounded_line(self.surface, color, top, bottom, self.thickness)
            draw_rounded_line(self.surface, (0, 0, 0), top, bottom, self.thickness - 4)
        else:
            draw_rounded_line(self.surface, (0, 0, 0), top, bottom, self.thickness)

        fill_top = (cx, bottom[1] - self.length * fraction)
        draw_rounded_line(self.surface, color, fill_top, bottom, self.thickness - 4)

        x, y = coords
        left = x - self.thickness / 2
        top_pos = y - self.height / 2
        self.surface.set_alpha(int(opacity))

        surface.blit(self.surface, (left, top_pos))
