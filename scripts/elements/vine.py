import random

import pygame

import scripts.elements.elements as elements
from scripts.global_assets import get_asset

# source art is 1536x2048 (portrait, not square like spike's) -- width is
# derived from height by this fixed aspect ratio rather than being its own
# independent size, so vines never stretch/squish. SIZE_MIN/SIZE_MAX/
# DEFAULT_SIZE all refer to height; snapped to _SIZE_SNAP buckets so
# live-generated vines reuse cached scaled images instead of each
# triggering a fresh pygame.transform.scale -- same approach as
# spike.py's/nest.py's own size snapping.
ASPECT = 1536 / 2048
SIZE_MIN = 60
SIZE_MAX = 150
DEFAULT_SIZE = 120
_SIZE_SNAP = 10

# anchor: a thin strip spanning the full width, at the very top -- where
# the vine is hypothetically rooted into the ceiling it hangs from.
# Mirrors spike.py's bottom-rooted anchor vertically; deliberately
# unrelated to the art's actual shape (see Element's anchor-vs-footprint
# split in elements.py). Given as fractions so they scale with whatever
# size a given vine gets -- left/width are fractions of width, top/height
# are fractions of height.
ANCHOR_LEFT_FRAC = 0
ANCHOR_TOP_FRAC = 0
ANCHOR_WIDTH_FRAC = 1
ANCHOR_HEIGHT_FRAC = 1 / 16

VARIANTS = ["1", "2", "3", "4", "5"]

_raw_front_imgs = {}

_scaled_front_cache = {}  # (variant, size, zoom) -> Surface


def init():
    global _raw_front_imgs
    _raw_front_imgs = {}
    for variant in VARIANTS:
        _raw_front_imgs[variant] = get_asset("vine_" + variant)


def _snap_size(size):
    return max(_SIZE_SNAP, int(round(size / _SIZE_SNAP) * _SIZE_SNAP))


def _dimensions(size):
    height = size
    width = size * ASPECT
    return width, height


def _anchor_geometry(width, height):
    return (width * ANCHOR_LEFT_FRAC, height * ANCHOR_TOP_FRAC, width * ANCHOR_WIDTH_FRAC, height * ANCHOR_HEIGHT_FRAC)


def _get_scaled_front(variant, size, zoom):
    key = (variant, size, zoom)
    cached = _scaled_front_cache.get(key)
    if cached is None:
        width, height = _dimensions(size)
        cached = pygame.transform.smoothscale(_raw_front_imgs[variant], (max(1, int(width * zoom)), max(1, int(height * zoom))))
        _scaled_front_cache[key] = cached
    return cached


def prewarm_cache(default_zooms, loading_screen=None):
    """Pre-builds every (variant, size bucket, zoom) front image so live
    placement never scales an image on the main thread. No hitbox mask to
    build -- vines have no collide/interaction layer at all."""
    size_min, size_max = _snap_size(SIZE_MIN), _snap_size(SIZE_MAX)
    steps_per_variant = (size_max - size_min) // _SIZE_SNAP + 1
    total_steps = len(VARIANTS) * steps_per_variant
    done = 0
    for variant in VARIANTS:
        size = size_min
        while size <= size_max:
            for zoom in default_zooms:
                _get_scaled_front(variant, size, zoom)
            size += _SIZE_SNAP
            done += 1
            if loading_screen is not None:
                loading_screen.put(done / total_steps, f"Pre-building vine cache (size {size})")


class Vine(elements.Element):
    """Purely decorative: front-layer visual only (vine_N.png), no
    collide/interaction hitbox at all (so it never blocks movement and
    never reacts to touch), destroyed only when an explosion overlaps its
    anchor. Anchor is a thin strip across the top -- where the vine is
    hypothetically rooted into the ceiling above it, unrelated to the
    art's own shape (see module docstring).

    variant picks which of vine_1..vine_5's art to use; leave it None to
    pick uniformly at random (same convention as Spike/Nest). Anchor
    geometry never depends on variant, only on size, so this is always
    safe to leave random even for the cheap pre-construction check in
    get_placement_geometry."""

    def __init__(self, default_zooms, x, y, variant=None, size=DEFAULT_SIZE):
        if variant is None:
            variant = random.choice(VARIANTS)
        size = _snap_size(size)
        width, height = _dimensions(size)
        anchor_left, anchor_top, anchor_width, anchor_height = _anchor_geometry(width, height)
        super().__init__(default_zooms, x, y, width, height, anchor_left, anchor_top, anchor_width, anchor_height)
        self.variant = variant
        self.size = size

    @classmethod
    def get_placement_geometry(cls, variant=None, size=DEFAULT_SIZE):
        # variant is accepted only for signature symmetry with __init__ --
        # geometry never depends on it, so there's nothing to resolve here.
        size = _snap_size(size)
        width, height = _dimensions(size)
        anchor_left, anchor_top, anchor_width, anchor_height = _anchor_geometry(width, height)
        return width, height, anchor_left, anchor_top, anchor_width, anchor_height

    def get_front_surface(self, zoom):
        return _get_scaled_front(self.variant, self.size, zoom)
