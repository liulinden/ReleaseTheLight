import math

import pygame


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
    r = cr + cw
    g = cw + cb / 4
    b = cw + cb
    dominant = max(r, g, b)
    if dominant == 0:
        return (0, 0, 0)
    factor = 255 / dominant
    charge = cw + cb + cr
    if charge < max_charge / 8:
        if not maximize:
            factor *= charge / (max_charge / 8) * 0.8
    else:
        factor *= 0.8 * (1 + (2 * (8 * charge - max_charge) / (max_charge * 8)))
    if maximize:
        factor *= 1.25
    return rgb_bound((r * factor, g * factor, b * factor))
