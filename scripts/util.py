import math
import numpy as np
import random

import pygame


class ImageCache:
    def __init__(self):
        self.cache = {}

    def get_resized_image(self, image:pygame.Surface, id, size, smoothscale = True):
        if (id, size, smoothscale) not in self.cache:
            if smoothscale:
                self.cache[(id, size, smoothscale)] = pygame.transform.smoothscale(image, size)
            else:
                self.cache[(id, size, smoothscale)] = pygame.transform.scale(image, size)
        return self.cache[(id, size, smoothscale)]


def draw_rounded_line(surface, color, start, end, thickness):
    pygame.draw.line(surface, color, start, end, thickness)
    pygame.draw.circle(surface, color, start, thickness // 2)
    pygame.draw.circle(surface, color, end, thickness // 2)


def safe_remove(list, item):
    if item in list:
        list.remove(item)
        return True
    return False


def safe_append(list, item):
    if item not in list:
        list.append(item)
        return True
    else:
        return False


def dist(x, y):
    return math.dist((0, 0), (x, y))


def frame_random(frame_length, expected_per_second):
    return random.random() < min(1, frame_length / 1000 * expected_per_second)


def poisson_count(expected):
    """Random non-negative integer count whose long-run average, across
    many calls with the same `expected`, converges to `expected` -- e.g. a
    per-chunk spawn count that should vary chunk-to-chunk but average out
    over the whole world."""
    return int(np.random.poisson(expected))


def normalize_1d(n):
    if n > 0:
        return 1
    elif n < 0:
        return -1
    else:
        return 0


def about_equal(a, b, frame_length=60, threshold=0.01):
    diff = a - b
    return diff < threshold * frame_length/60 and diff > -threshold * frame_length/60


def polar_to_rect(r, angle, center=(0, 0)):
    return r * math.cos(angle) + center[0], r * math.sin(angle) + center[1]


def multiply_tuple(tuple_, factor):
    return tuple(entry * factor for entry in tuple_)


def rotate_and_get_offset(surface, cx, cy, angle, degrees=False):
    # Rotate the surface
    rotated_surface = pygame.transform.rotate(surface, math.degrees(angle))
    rect = surface.get_rect()
    rotated_rect = rotated_surface.get_rect()

    # Pivot offset before rotation
    pivot_x = cx - rect.centerx
    pivot_y = cy - rect.centery

    # Apply rotation transformation
    rotated_pivot_x = pivot_x * math.cos(angle) - pivot_y * math.sin(angle)
    rotated_pivot_y = pivot_x * math.sin(angle) + pivot_y * math.cos(angle)

    # Compute new top-left position
    offset_x = rect.centerx + rotated_pivot_x - rotated_rect.width / 2
    offset_y = rect.centery + rotated_pivot_y - rotated_rect.height / 2

    return rotated_surface, (offset_x), (offset_y)


def rgb_bound(color):
    r, g, b = color
    return (channel_bound(r), channel_bound(g), channel_bound(b))


def channel_bound(value):
    return min(255, max(0, value))


def charges_to_color(cw, cb, cr, max_charge=500, maximize=False):
    r = cr + cw / 3
    g = cw / 3 + cb / 8 + cr / 8
    b = cw / 3 + cb
    med = sorted((r, g, b))[1]
    sum = r + g + b
    if sum == 0:
        return (0,0,0)
    r = max(sum/20, r + 2 * (r - med)) * 255 / sum
    g = max(sum/20, g + 2 * (g - med)) * 255 / sum
    b = max(sum/20, b + 2 * (b - med)) * 255 / sum
    frac = ((cw + cb + cr) / max_charge) ** 0.5
    factor = frac * 5
    if maximize:
        factor = max(factor, 3)

    # factor = 255 / dominant
    # charge = cw + cb + cr
    # if charge < max_charge / 8:
    #    if not maximize:
    #        factor *= charge / (max_charge / 8) * 0.8
    # elif charge < max_charge / 2:
    #    frac = (charge/max_charge - 1/8)/(1/2 - 1/8)
    #    factor *= 0.8 + 2 * frac
    # else:
    #    frac = (charge/max_charge - 1/2)/(1/2)
    #    factor *= 2.8 + 4 * frac
    # if maximize:
    #    factor *= 1.25
    return rgb_bound((r * factor, g * factor, b * factor))
