import pygame

import scripts.elements as elements
from scripts.global_assets import get_asset

# world-space width/height range every spike variant is drawn into -- source
# art is square (2048x2048), so width and height always match. Sizes are
# snapped to _SIZE_SNAP buckets so live-generated spikes reuse cached scaled
# images/masks instead of each triggering a fresh pygame.transform.scale --
# same approach as nest.py's _snap_nest_size.
SIZE_MIN = 90
SIZE_MAX = 220
DEFAULT_SIZE = 150
_SIZE_SNAP = 10

# anchor: a thin strip spanning the full width of the image, at the very
# bottom -- where the spike is hypothetically rooted into the terrain it's
# standing on. Deliberately unrelated to the hitbox art's actual shape
# (see Element's anchor-vs-footprint split in elements.py). Given as
# fractions of size so it scales with whatever size a given spike gets.
ANCHOR_LEFT_FRAC = 0
ANCHOR_TOP_FRAC = 4 / 5
ANCHOR_WIDTH_FRAC = 1
ANCHOR_HEIGHT_FRAC = 1 / 5

MIN_DAMAGE_Y_SPEED = 0.3  # abs(player.y_speed) must be at least this fast to take spike damage
DAMAGE = 40

VARIANTS = ["1"]  # future: "2", "3", ...

_raw_front_imgs = {}
_raw_hitbox_imgs = {}

_scaled_front_cache = {}   # (variant, size, zoom) -> Surface
_scaled_hitbox_cache = {}  # (variant, size, zoom) -> Surface
_hitbox_mask_cache = {}    # (variant, size) -> Mask, native (zoom=1) resolution


def init():
    global _raw_front_imgs, _raw_hitbox_imgs
    _raw_front_imgs = {}
    _raw_hitbox_imgs = {}
    for variant in VARIANTS:
        _raw_front_imgs[variant] = get_asset("element_spike_" + variant)
        _raw_hitbox_imgs[variant] = get_asset("element_spike_" + variant + "_hitbox")


def _snap_size(size):
    return max(_SIZE_SNAP, int(round(size / _SIZE_SNAP) * _SIZE_SNAP))


def _anchor_geometry(size):
    return (size * ANCHOR_LEFT_FRAC, size * ANCHOR_TOP_FRAC, size * ANCHOR_WIDTH_FRAC, size * ANCHOR_HEIGHT_FRAC)


def _get_scaled_front(variant, size, zoom):
    key = (variant, size, zoom)
    cached = _scaled_front_cache.get(key)
    if cached is None:
        side = max(1, int(size * zoom))
        cached = pygame.transform.smoothscale(_raw_front_imgs[variant], (side, side))
        _scaled_front_cache[key] = cached
    return cached


def _get_scaled_hitbox(variant, size, zoom):
    key = (variant, size, zoom)
    cached = _scaled_hitbox_cache.get(key)
    if cached is None:
        side = max(1, int(size * zoom))
        cached = pygame.transform.scale(_raw_hitbox_imgs[variant], (side, side))
        _scaled_hitbox_cache[key] = cached
    return cached


def _get_hitbox_mask(variant, size):
    key = (variant, size)
    cached = _hitbox_mask_cache.get(key)
    if cached is None:
        cached = pygame.mask.from_surface(_get_scaled_hitbox(variant, size, 1))
        _hitbox_mask_cache[key] = cached
    return cached


def prewarm_cache(default_zooms):
    """Pre-builds every (variant, size bucket, zoom) image/mask combo so
    live placement never scales an image on the main thread."""
    for variant in VARIANTS:
        size = _snap_size(SIZE_MIN)
        max_snapped = _snap_size(SIZE_MAX)
        while size <= max_snapped:
            for zoom in default_zooms:
                _get_scaled_front(variant, size, zoom)
                _get_scaled_hitbox(variant, size, zoom)
            _get_scaled_hitbox(variant, size, 1)  # zoom=1 always needed for the hitbox mask
            _get_hitbox_mask(variant, size)
            size += _SIZE_SNAP


class Spike(elements.Element):
    """Solid hazard: blocks movement like terrain, and deals damage on
    touch if the player is moving fast enough vertically. Front-only
    visual (element_spike_N.png); element_spike_N_hitbox.png doubles as
    both the collide and interaction hitbox -- unrelated to the anchor,
    which is just the bottom strip of the image (see module docstring)."""

    def __init__(self, default_zooms, x, y, variant="1", size=DEFAULT_SIZE):
        size = _snap_size(size)
        anchor_left, anchor_top, anchor_width, anchor_height = _anchor_geometry(size)
        super().__init__(default_zooms, x, y, size, size, anchor_left, anchor_top, anchor_width, anchor_height)
        self.variant = variant
        self.size = size

    @classmethod
    def get_placement_geometry(cls, variant="1", size=DEFAULT_SIZE):
        size = _snap_size(size)
        anchor_left, anchor_top, anchor_width, anchor_height = _anchor_geometry(size)
        return size, size, anchor_left, anchor_top, anchor_width, anchor_height

    def get_collide_hitbox_surface(self, zoom):
        return _get_scaled_hitbox(self.variant, self.size, zoom)

    def get_interaction_hitbox_surface(self, zoom):
        return _get_scaled_hitbox(self.variant, self.size, zoom)

    def get_front_surface(self, zoom):
        return _get_scaled_front(self.variant, self.size, zoom)

    # both hitboxes share one prewarmed asset -- reuse it instead of each
    # instance lazily building its own redundant copy
    def get_collide_hitbox_mask(self):
        return _get_hitbox_mask(self.variant, self.size)

    def get_interaction_hitbox_mask(self):
        return _get_hitbox_mask(self.variant, self.size)

    def on_touch(self, player, _terrain):
        # Called by Player.move_vertical only after both a broad-phase
        # rect check and a precise interaction_hitbox mask overlap already
        # passed -- this just decides whether that contact hurts.
        if player.immunity_timer == 0 and abs(player.y_speed) >= MIN_DAMAGE_Y_SPEED:
            player.immunity_timer = player.immunity_time
            player.take_enemy_hit(DAMAGE)
