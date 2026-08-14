"""
bloom.py — Single-function bloom effect for Pygame.

get_bloom(surface, threshold=200, downscale=4, blur_passes=2, intensity=1.0)

Pass in a fully-rendered scene surface (with occlusion already correct,
since it's your actual scene) and get back a surface containing just the
blurred glow, ready to blit on top with BLEND_RGB_ADD.

Usage:
    from bloom import get_bloom

    # ... draw your whole scene onto `screen` as normal ...
    bloom_surface = get_bloom(screen)
    screen.blit(bloom_surface, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    pygame.display.flip()
"""

import numpy as np
import pygame

scratch_surfaces = {}
scratch_second_surfaces = {}


def get_surface(size):
    if size not in scratch_surfaces:
        scratch_surfaces[size] = pygame.Surface(size, pygame.SRCALPHA)
    return scratch_surfaces[size]

def get_second_surface(size):
    if size not in scratch_second_surfaces:
        scratch_second_surfaces[size] = pygame.Surface(size, pygame.SRCALPHA)
    return scratch_second_surfaces[size]

def get_bloom(surface, threshold=30, downscale=30, blur_passes=2, intensity=0.8):
    """
    surface:     the pygame.Surface to extract bloom from (e.g. your full
                 rendered scene, or a specific layer).
    threshold:   0-255 luminance cutoff; only pixels brighter than this
                 contribute to the glow.
    downscale:   factor to shrink the surface by before blurring. Higher =
                 much faster and softer glow. This is what keeps the
                 pixel manipulation cheap — all the numpy work happens on
                 a small image, not the full-res surface.
    blur_passes: number of shrink/grow blur iterations at small size.
                 More passes = smoother glow, still cheap since the image
                 is already small.
    intensity:   multiplier for how strong the final glow looks.

    Returns a pygame.Surface (SRCALPHA, same size as input) containing
    only the blurred bright areas, meant to be additively blitted on top
    of the original surface.
    """
    full_size = surface.get_size()
    small_size = (max(1, full_size[0] // downscale), max(1, full_size[1] // downscale))
    shrink_size = (max(1, small_size[0] // 2), max(1, small_size[1] // 2))

    big = get_surface(full_size)
    small = get_surface(small_size)
    tiny = get_surface(shrink_size)

    # --- 1. Downscale FIRST — this is the key to speed. All the numpy
    #        pixel work below runs on a small image instead of the full
    #        resolution surface, which is what keeps this fast enough
    #        for a real-time game loop. ---
    pygame.transform.smoothscale(surface, small_size, small)

    # --- 2. Extract bright pixels (per-pixel threshold via numpy) on the
    #        small image only. ---
    rgb = pygame.surfarray.array3d(small).astype(np.float32)  # (sw, sh, 3)
    try:
        alpha = pygame.surfarray.array_alpha(small).astype(np.float32)
    except pygame.error:
        alpha = np.full(small_size, 255, dtype=np.float32)

    luminance = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    mask = luminance >= threshold

    bright_rgb = np.where(mask[..., None], rgb, 0).astype(np.uint8)
    bright_alpha = np.where(mask, alpha, 0).astype(np.uint8)

    pygame.surfarray.blit_array(small, bright_rgb)
    pygame.surfarray.pixels_alpha(small)[:] = bright_alpha

    # --- 3. Blur at small resolution (shrink/grow passes = cheap box blur) ---
    for _ in range(blur_passes):
        pygame.transform.smoothscale(small, shrink_size, tiny)
        pygame.transform.smoothscale(tiny, small_size, small)

    # --- 4. Upscale back to full size ---
    pygame.transform.smoothscale(small, full_size, big)

    # --- 5. Apply intensity ---
    if intensity > 1.0:
        for _ in range(int(intensity) - 1):
            big.blit(big, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    elif intensity < 1.0:
        shade = max(0, min(255, int(255 * intensity)))
        dim = get_second_surface(full_size)
        dim.fill((shade, shade, shade, 255))
        big.blit(dim, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

    return big
