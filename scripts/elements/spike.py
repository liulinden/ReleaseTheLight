import random

import pygame

import scripts.elements.elements as elements
from scripts.global_assets import get_asset

# world-space width/height range every spike variant is drawn into -- source
# art is square (2048x2048), so width and height always match. Sizes are
# snapped to _SIZE_SNAP buckets so live-generated spikes reuse cached scaled
# images/masks instead of each triggering a fresh pygame.transform.scale --
# same approach as nest.py's _snap_nest_size.
SIZE_MIN = 30
SIZE_MAX = 100
DEFAULT_SIZE = 60
_SIZE_SNAP = 10

# anchor: a thin strip spanning the full width of the image, at the very
# bottom -- where the spike is hypothetically rooted into the terrain it's
# standing on. Deliberately unrelated to the hitbox art's actual shape
# (see Element's anchor-vs-footprint split in elements.py). Given as
# fractions of size so it scales with whatever size a given spike gets.
ANCHOR_LEFT_FRAC = 1 / 4
ANCHOR_TOP_FRAC = 7 / 8
ANCHOR_WIDTH_FRAC = 1 / 2
ANCHOR_HEIGHT_FRAC = 1 / 8
# UpsideDownSpike's anchor: same strip, mirrored to the top instead of the
# bottom (rooted in the ceiling it hangs from) -- derived rather than
# hand-picked so it always stays the exact vertical mirror of the strip
# above, even if that one's fractions change.
UPSIDE_DOWN_ANCHOR_TOP_FRAC = 1 - ANCHOR_TOP_FRAC - ANCHOR_HEIGHT_FRAC

MIN_DAMAGE_Y_SPEED = 0.3  # abs(player.y_speed) must be at least this fast to take spike damage
DAMAGE = 15

VARIANTS = ["1", "2", "3", "4"]

_raw_front_imgs = {}
_raw_hitbox_imgs = {}

_scaled_front_cache = {}   # (variant, size, zoom, flipped) -> Surface
_scaled_hitbox_cache = {}  # (variant, size, zoom, flipped) -> Surface
_hitbox_mask_cache = {}    # (variant, size, flipped) -> Mask, native (zoom=1) resolution


def init():
    global _raw_front_imgs, _raw_hitbox_imgs
    _raw_front_imgs = {}
    _raw_hitbox_imgs = {}
    for variant in VARIANTS:
        _raw_front_imgs[variant] = get_asset("spike_" + variant)
        _raw_hitbox_imgs[variant] = get_asset("spike_" + variant + "_hitbox")


def _snap_size(size):
    return max(_SIZE_SNAP, int(round(size / _SIZE_SNAP) * _SIZE_SNAP))


def _anchor_geometry(size, top_frac=ANCHOR_TOP_FRAC):
    return (size * ANCHOR_LEFT_FRAC, size * top_frac, size * ANCHOR_WIDTH_FRAC, size * ANCHOR_HEIGHT_FRAC)


def _get_scaled_front(variant, size, zoom, flipped=False):
    key = (variant, size, zoom, flipped)
    cached = _scaled_front_cache.get(key)
    if cached is None:
        side = max(1, int(size * zoom))
        cached = pygame.transform.smoothscale(_raw_front_imgs[variant], (side, side))
        if flipped:
            cached = pygame.transform.flip(cached, False, True)
        _scaled_front_cache[key] = cached
    return cached


def _get_scaled_hitbox(variant, size, zoom, flipped=False):
    key = (variant, size, zoom, flipped)
    cached = _scaled_hitbox_cache.get(key)
    if cached is None:
        side = max(1, int(size * zoom))
        cached = pygame.transform.scale(_raw_hitbox_imgs[variant], (side, side))
        if flipped:
            cached = pygame.transform.flip(cached, False, True)
        _scaled_hitbox_cache[key] = cached
    return cached


def _get_hitbox_mask(variant, size, flipped=False):
    key = (variant, size, flipped)
    cached = _hitbox_mask_cache.get(key)
    if cached is None:
        cached = pygame.mask.from_surface(_get_scaled_hitbox(variant, size, 1, flipped))
        _hitbox_mask_cache[key] = cached
    return cached


def prewarm_cache(default_zooms, loading_screen=None):
    """Pre-builds every (variant, size bucket, zoom, orientation) image/mask
    combo -- both upright (Spike) and flipped (UpsideDownSpike) -- so live
    placement never scales or flips an image on the main thread."""
    size_min, size_max = _snap_size(SIZE_MIN), _snap_size(SIZE_MAX)
    steps_per_variant = (size_max - size_min) // _SIZE_SNAP + 1
    total_steps = len(VARIANTS) * steps_per_variant * 2  # x2 for upright + flipped
    done = 0
    for variant in VARIANTS:
        for flipped in (False, True):
            size = size_min
            while size <= size_max:
                for zoom in default_zooms:
                    _get_scaled_front(variant, size, zoom, flipped)
                    _get_scaled_hitbox(variant, size, zoom, flipped)
                _get_scaled_hitbox(variant, size, 1, flipped)  # zoom=1 always needed for the hitbox mask
                _get_hitbox_mask(variant, size, flipped)
                size += _SIZE_SNAP
                done += 1
                if loading_screen is not None:
                    loading_screen.put(done / total_steps, f"Pre-building spike cache (size {size})")


class Spike(elements.Element):
    """Solid hazard: blocks movement like terrain, and deals damage on
    touch if the player is moving fast enough vertically. Front-only
    visual (spike_N.png); spike_N_hitbox.png doubles as both the collide
    and interaction hitbox -- unrelated to the anchor, which is just the
    bottom strip of the image (see module docstring).

    variant picks which of spike_1..spike_4's art/hitbox to use; leave it
    None to pick uniformly at random (same convention as Nest randomizing
    its own variant_id internally). Anchor geometry never depends on
    variant, only on size, so this is always safe to leave random even for
    the cheap pre-construction check in get_placement_geometry."""

    def __init__(self, default_zooms, x, y, variant=None, size=DEFAULT_SIZE):
        if variant is None:
            variant = random.choice(VARIANTS)
        size = _snap_size(size)
        anchor_left, anchor_top, anchor_width, anchor_height = _anchor_geometry(size)
        super().__init__(default_zooms, x, y, size, size, anchor_left, anchor_top, anchor_width, anchor_height)
        self.variant = variant
        self.size = size

    @classmethod
    def get_placement_geometry(cls, variant=None, size=DEFAULT_SIZE):
        # variant is accepted only for signature symmetry with __init__ --
        # geometry never depends on it, so there's nothing to resolve here.
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
        if player.immunity_timer == 0 and (player.y_speed) >= MIN_DAMAGE_Y_SPEED:
            player.immunity_timer = player.immunity_time
            player.take_enemy_hit(DAMAGE * (2+(abs(player.y_speed)-MIN_DAMAGE_Y_SPEED)), _terrain)


class UpsideDownSpike(Spike):
    """Mirror of Spike, both visually and logically: same spike_N.png art
    and hitbox, just flipped vertically, rooted into a ceiling instead of a
    floor (anchor strip at the top instead of the bottom -- see
    UPSIDE_DOWN_ANCHOR_TOP_FRAC), placed via
    attempt_place_element_above_air_pocket instead of ..._below_..., and
    hurts the player on a fast enough UPWARD hit (jumping into it) instead
    of a downward one. Everything else -- size range, hitbox convention,
    variant randomization, damage formula -- is identical to Spike."""

    def __init__(self, default_zooms, x, y, variant=None, size=DEFAULT_SIZE):
        if variant is None:
            variant = random.choice(VARIANTS)
        size = _snap_size(size)
        anchor_left, anchor_top, anchor_width, anchor_height = _anchor_geometry(size, top_frac=UPSIDE_DOWN_ANCHOR_TOP_FRAC)
        # bypass Spike.__init__ (it always uses the upright anchor) and go
        # straight to Element.__init__ with the mirrored anchor computed above
        elements.Element.__init__(self, default_zooms, x, y, size, size, anchor_left, anchor_top, anchor_width, anchor_height)
        self.variant = variant
        self.size = size

    @classmethod
    def get_placement_geometry(cls, variant=None, size=DEFAULT_SIZE):
        size = _snap_size(size)
        anchor_left, anchor_top, anchor_width, anchor_height = _anchor_geometry(size, top_frac=UPSIDE_DOWN_ANCHOR_TOP_FRAC)
        return size, size, anchor_left, anchor_top, anchor_width, anchor_height

    def get_collide_hitbox_surface(self, zoom):
        return _get_scaled_hitbox(self.variant, self.size, zoom, flipped=True)

    def get_interaction_hitbox_surface(self, zoom):
        return _get_scaled_hitbox(self.variant, self.size, zoom, flipped=True)

    def get_front_surface(self, zoom):
        return _get_scaled_front(self.variant, self.size, zoom, flipped=True)

    def get_collide_hitbox_mask(self):
        return _get_hitbox_mask(self.variant, self.size, flipped=True)

    def get_interaction_hitbox_mask(self):
        return _get_hitbox_mask(self.variant, self.size, flipped=True)

    def on_touch(self, player, _terrain):
        if player.immunity_timer == 0 and (-player.y_speed) >= MIN_DAMAGE_Y_SPEED:
            player.immunity_timer = player.immunity_time
            player.take_enemy_hit(DAMAGE * (2 + (abs(player.y_speed) - MIN_DAMAGE_Y_SPEED)), _terrain)
