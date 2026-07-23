import math

import pygame


def dist(x, y):
    return math.dist((0, 0), (x, y))


def polar_to_rect(r, angle, center=(0, 0)):
    return r * math.cos(angle) + center[0], r * math.sin(angle) + center[1]


def get_bounced_vector(vector, normal, elasticity = 1):
    ax, ay = vector
    bx, by = normal
    factor = dist(bx, by)
    if factor == 0:
        return 0, 0
    bx /= factor
    by /= factor

    s = bx**2 - by**2
    p = 2 * bx * by

    bounced_x = -ax * s - p * ay
    bounced_y = ay * s - p * ax
    # bounced x and y are now already equal to bounced vector assuming elasticity = 1

    factor = (elasticity + 1)/2

    return bounced_x * factor + ax * (1-factor), bounced_y * factor + ay * (1-factor)


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
