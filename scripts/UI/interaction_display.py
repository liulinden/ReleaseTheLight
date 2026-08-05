import math

import pygame

from scripts.util import safe_append, safe_remove


def init():
    InteractionDisplay.font = pygame.font.SysFont("maiandragd", InteractionDisplay.font_size)

class InteractionDisplayManager:
    def __init__(self):
        self.on_screen_displays = []
        self.in_range_displays = []

    def tick(self, frame_length, keys_down):
        active_display = None
        if self.in_range_displays:
            active_display = self.in_range_displays[-1]
        for display in self.on_screen_displays:
            display.tick(frame_length, display is active_display, keys_down)

    def draw(self, surface, frame, time=None, offset_x=0, offset_y=0):
        for i in range(len(self.on_screen_displays) - 1, -1, -1):
            display = self.on_screen_displays[i]
            if not (display.draw(surface, frame, time=time, offset_x=offset_x, offset_y=offset_y) or display in self.in_range_displays):
                self.on_screen_displays.remove(display)

    def display_in_range(self, display):
        safe_append(self.in_range_displays, display)
        safe_append(self.on_screen_displays, display)

    def display_out_range(self, display, complete=False):
        safe_remove(self.in_range_displays, display)
        if not complete:
            display.post_active = False


class InteractionDisplay:
    font = None
    font_size = 16
    outline_thickness = 1
    keys_to_characters = {pygame.K_e: "E"}
    cached_displays = {}

    def __init__(self, coords, display, color=(255, 255, 255), align="centered"):  # text is tuple of str and pygame key objects - e.g. ("Hold", pygame.K_e, "to drain")
        self.x, self.y = coords
        self.color = color
        self.align = align
        outline_thickness = InteractionDisplay.outline_thickness

        if display in InteractionDisplay.cached_displays:
            self.w, self.h, self.text, self.surface, circles = InteractionDisplay.cached_displays[display]
            self.circles = {key: value.copy() for key, value in circles.items()}
        else:
            self.w = 0
            segments = []
            self.circles = {}
            for segment in display:
                if segment in self.keys_to_characters:
                    character = self.keys_to_characters[segment]
                    font = InteractionDisplay.font.render("  " + character + "  ", True, (255, 255, 255))
                    font_black = InteractionDisplay.font.render("  " + character + "  ", True, (0, 0, 0))
                    width = font.get_width() + 2 * outline_thickness
                    self.circles[segment] = [self.w + width / 2, 0]
                else:
                    font = InteractionDisplay.font.render(segment, True, (255, 255, 255))
                    font_black = InteractionDisplay.font.render(segment, True, (0, 0, 0))
                    width = font.get_width() + 2 * outline_thickness
                segments.append((font, font_black, self.w))
                self.w += width

            self.h = segments[0][0].get_height() + 2 * outline_thickness
            self.surface = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            self.text = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            for segment in segments:
                for offset_x, offset_y in ((0, outline_thickness), (outline_thickness, 0), (0, -outline_thickness), (-outline_thickness, 0)):
                    self.text.blit(segment[1], (outline_thickness + offset_x + segment[2], outline_thickness + offset_y))
                self.text.blit(segment[0], (outline_thickness + segment[2], outline_thickness))
            for circle in self.circles:
                x, y, r = self.circles[circle][0], self.h / 2, self.h / 2 - outline_thickness
                pygame.draw.circle(self.text, (0, 0, 0), (x, y), r + 2 * outline_thickness, 4 * outline_thickness)
                pygame.draw.circle(self.text, (255, 255, 255), (x, y), r + outline_thickness, 2 * outline_thickness)

            InteractionDisplay.cached_displays[display] = self.w, self.h, self.text, self.surface, {key: value.copy() for key, value in self.circles.items()}

        self.opacity = 0
        self.active = False
        self.post_active = False  # active but remains True for duration of fading
        self.rise = 0
        self.key_released = False

    def update_coordinates(self, coords):
        self.x, self.y = coords

    def tick(self, frame_length, primary, keys_down):
        if primary:
            self.active = True
            for circle in self.circles:
                if keys_down[circle]:
                    if self.key_released:
                        self.circles[circle][1] = 255  # min(self.circles[circle][1]+frame_length,255)
                        self.opacity = max(160, self.opacity)
                    else:
                        self.active = False
                else:
                    self.circles[circle][1] = max(self.circles[circle][1] - frame_length, 0)
                    self.active = False
                    self.key_released = True
            self.opacity = min(self.opacity + frame_length / 5, 255 if self.active else 160)
            self.post_active = self.active
        else:
            self.opacity = max(self.opacity - frame_length / 3, 0)
            self.active = False
            self.key_released = False

        if self.post_active:
            self.rise += (0.8 - self.rise) * frame_length / 100
        else:
            self.rise += (0 - self.rise) * frame_length / 300

    def draw(self, surface, frame, time=None, offset_x=0, offset_y=0):
        if self.opacity > 0:
            left, top, zoom = frame
            if self.align == "screen":
                x, y = self.x + offset_x, self.y + offset_y
            else:
                x, y = (self.x - left) * zoom + offset_x, (self.y - top) * zoom + offset_y
                if time is None:
                    time = pygame.time.get_ticks()
                y += (math.sin(time / 500) / 8 - self.rise) * self.h

            self.surface.fill((0, 0, 0, 0))
            self.surface.set_alpha(self.opacity)

            for circle in self.circles:
                c_x, c_y, r, o = self.circles[circle][0], self.h / 2, self.h / 2 - InteractionDisplay.outline_thickness, self.circles[circle][1]
                if self.circles[circle][1] > 0:
                    pygame.draw.circle(self.surface, (255, 255, 255, o), (c_x, c_y), r)
            self.surface.blit(self.text, (0, 0))
            self.surface.fill(self.color, special_flags=pygame.BLEND_RGB_MULT)

            if self.align == "centered":
                surface.blit(self.surface, (x - self.w / 2, y - self.h / 2))
            elif self.align == "top_centered":
                surface.blit(self.surface, (x - self.w / 2, y))
            return True
        return False
