import math

import pygame

import scripts.terrain as terrain
from config import CHUNK_SIZE


def _circle_overlaps_rect(rect, cx, cy, r):
    """Plain circle-vs-rect distance check, no pixel sampling. Shared by
    Element.anchor_destroyed and attempt_place_element's pre-construction
    grounded check so both use the exact same test."""
    closest_x = max(rect.left, min(cx, rect.right))
    closest_y = max(rect.top, min(cy, rect.bottom))
    return math.dist((cx, cy), (closest_x, closest_y)) < r


class Element:
    """Base class for all world elements (spikes, fire, vines, decorative
    terrain, etc). Distinct from Structure: elements are destructible --
    the whole element is destroyed when its anchor rect overlaps an
    explosion (any post-generation air-pocket carve, player- or
    enemy-caused) -- but, like structures, they can't be regularly
    carved/mined by the player.

    An element has its own (width, height) footprint -- what its images
    (back/front/hitbox layers) are drawn into, top-left at (left, top) --
    and a separate anchor rect, given as its own (left, top, width, height)
    relative to the footprint's top-left. The anchor is NOT expected to be
    centered on, or shaped like, the visible art: it's purely the region
    whose overlap with an explosion destroys the element (see
    anchor_destroyed / attempt_place_element).

    Layers are all optional: a subclass only needs to override the
    get_*_surface hook(s) for the layers it actually uses -- draw_back /
    draw_front / draw_hitbox are no-ops for any hook that returns None,
    so callers never need to special-case a missing layer. Hitbox images
    are assumed to be opaque white on a fully transparent background,
    same convention as nest/structure hitbox images.
    """

    def __init__(self, default_zooms, x, y, width, height, anchor_left, anchor_top, anchor_width, anchor_height):
        self.x = x
        self.y = y
        self.default_zooms = default_zooms

        # footprint: the box every layer image is drawn into. Centered on (x, y).
        self.width = width
        self.height = height
        self.left = x - width / 2
        self.top = y - height / 2

        # anchor: the rect region whose overlap with an explosion destroys
        # the whole element. anchor_left/anchor_top are given relative to
        # the footprint's own (left, top), then stored here as absolute
        # world coordinates.
        self.anchor_width = anchor_width
        self.anchor_height = anchor_height
        self.anchor_left = self.left + anchor_left
        self.anchor_top = self.top + anchor_top

        self._collide_hitbox_mask = None
        self._interaction_hitbox_mask = None

    @classmethod
    def get_placement_geometry(cls, *args, **kwargs):
        """Cheaply return (width, height, anchor_left, anchor_top,
        anchor_width, anchor_height) for an instance that would be built
        with these same extra args/kwargs (everything __init__ takes after
        default_zooms/x/y) -- WITHOUT actually constructing it, so
        attempt_place_element can test whether a placement is grounded
        before paying for any image loading/scaling the real construction
        might do. Base implementation assumes these six values are passed
        straight through as the first six extra args, matching
        Element.__init__'s own signature; subclasses with a different
        signature (e.g. deriving geometry from a variant id or a prewarmed
        asset) must override this."""
        return args[0], args[1], args[2], args[3], args[4], args[5]

    def get_footprint_rect(self):
        return pygame.Rect(self.left, self.top, self.width, self.height)

    def get_anchor_rect(self):
        return pygame.Rect(self.anchor_left, self.anchor_top, self.anchor_width, self.anchor_height)

    def get_registration_rect(self):
        """Bounding box of footprint + anchor -- what chunk registration/
        removal iterates over, since the two rects aren't required to
        overlap at all."""
        return self.get_footprint_rect().union(self.get_anchor_rect())

    def anchor_destroyed(self, air_x, air_y, air_r):
        """True if a circular air-pocket carve (an "explosion") centered at
        (air_x, air_y) with radius air_r overlaps this element's anchor
        rect, checked against the air pocket's own x/y/r."""
        return _circle_overlaps_rect(self.get_anchor_rect(), air_x, air_y, air_r)

    # ------------------------------------------------------------------
    # Layers -- subclasses override whichever of these hooks they need.
    # Each should return an SRCALPHA surface sized to (width, height) at
    # the given zoom, or None if this element doesn't use that layer.
    # ------------------------------------------------------------------

    def get_collide_hitbox_surface(self, zoom):
        """Opaque-white-on-transparent surface baked into chunk.mask for
        real player/laser collision. None if this element has no solid
        collision footprint."""
        return None

    def get_interaction_hitbox_surface(self, zoom):
        """Opaque-white-on-transparent surface for non-collision detection
        (e.g. interact prompts, custom hit-testing). None if unused."""
        return None

    def get_back_surface(self, zoom):
        """Visual drawn before terrain, behind the player. None if unused."""
        return None

    def get_front_surface(self, zoom):
        """Visual drawn after terrain, in front of the player. None if unused."""
        return None

    # ------------------------------------------------------------------
    # Hitbox masks -- native (zoom=1) resolution only, since collision/
    # touch detection is never sampled at any other resolution. Lazily
    # built and cached per-instance by default; subclasses backed by a
    # shared prewarmed asset cache (e.g. Spike) should override these to
    # return the shared mask instead of building a redundant per-instance one.
    # ------------------------------------------------------------------

    def get_collide_hitbox_mask(self):
        if self._collide_hitbox_mask is None:
            surf = self.get_collide_hitbox_surface(1)
            if surf is not None:
                self._collide_hitbox_mask = pygame.mask.from_surface(surf)
        return self._collide_hitbox_mask

    def get_interaction_hitbox_mask(self):
        if self._interaction_hitbox_mask is None:
            surf = self.get_interaction_hitbox_surface(1)
            if surf is not None:
                self._interaction_hitbox_mask = pygame.mask.from_surface(surf)
        return self._interaction_hitbox_mask

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw_back(self, surface, frame, offset_x=0, offset_y=0):
        cam_x, cam_y, zoom = frame
        img = self.get_back_surface(zoom)
        if img:
            surface.blit(img, ((self.left - cam_x) * zoom + offset_x, (self.top - cam_y) * zoom + offset_y))

    def draw_front(self, surface, frame, offset_x=0, offset_y=0):
        cam_x, cam_y, zoom = frame
        img = self.get_front_surface(zoom)
        if img:
            surface.blit(img, ((self.left - cam_x) * zoom + offset_x, (self.top - cam_y) * zoom + offset_y))

    def draw_hitbox(self, surface, frame, offset_x=0, offset_y=0):
        """Dev debug view: collide_hitbox is drawn first (its own white),
        interaction_hitbox is drawn on top tinted a different color."""
        cam_x, cam_y, zoom = frame
        dest = ((self.left - cam_x) * zoom + offset_x, (self.top - cam_y) * zoom + offset_y)

        collide_img = self.get_collide_hitbox_surface(zoom)
        if collide_img:
            surface.blit(collide_img, dest)

        interaction_img = self.get_interaction_hitbox_surface(zoom)
        if interaction_img:
            tinted = interaction_img.copy()
            tinted.fill((60, 200, 255, 255), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(tinted, dest)

    # ------------------------------------------------------------------
    # Touch reaction -- no-op by default. Overridden by elements that need
    # to react to the player physically touching them (e.g. Spike's touch
    # damage). Called from Player.move_vertical once a broad-phase rect
    # check AND a precise interaction_hitbox mask check both hit -- see
    # player.py.
    # ------------------------------------------------------------------

    def on_touch(self, player, _terrain):
        pass


# ------------------------------------------------------------------
# Placement -- module-level since it needs Terrain access (chunks, air
# pockets), not just Element state. Mirrors how
# enemies._enemy_handling.get_enemy spawns against terrain truth data.
# ------------------------------------------------------------------


def _anchor_search_radius(anchor_width, anchor_height):
    # generous enough to catch every air pocket that could possibly reach
    # the anchor, regardless of which chunk(s) its truth data lives in
    return math.dist((0, 0), (anchor_width, anchor_height)) / 2 + terrain.max_air_pocket_radius * terrain.rim_pocket_ratio


def _find_blocking_air_pocket(_terrain, rect, cx, cy, search_radius):
    """First nearby air pocket whose own (x, y, r) overlaps rect, or None.
    Plain distance check, no pixel sampling."""
    for chunk in _terrain._chunks_near(cx, cy, search_radius):
        for air_pocket in chunk.air_pockets:
            if _circle_overlaps_rect(rect, air_pocket.x, air_pocket.y, air_pocket.r):
                return air_pocket
    return None


def attempt_place_element(_terrain, element_cls, x, y, *args, **kwargs):
    """Try to place an element of type element_cls at (x, y). "Grounded"
    means the element's anchor rect overlaps NO air pockets at all --
    checked purely against each nearby air pocket's own (x, y, r), no
    pixel sampling. The candidate anchor rect is built via
    element_cls.get_placement_geometry (cheap, no instantiation) so a
    rejected placement never pays for the real object's construction
    (image loads/scales, etc). On success the element is constructed for
    real, registered into every chunk its footprint+anchor touch (mirrors
    Terrain.generate_nest), and returned; on failure, False."""
    width, height, anchor_left, anchor_top, anchor_width, anchor_height = element_cls.get_placement_geometry(*args, **kwargs)
    left = x - width / 2
    top = y - height / 2
    footprint_rect = pygame.Rect(left, top, width, height)
    anchor_rect = pygame.Rect(left + anchor_left, top + anchor_top, anchor_width, anchor_height)

    search_radius = _anchor_search_radius(anchor_width, anchor_height)
    if _find_blocking_air_pocket(_terrain, anchor_rect, x, y, search_radius) is not None:
        return False

    # reject placements that overlap an already-placed element's footprint --
    # without this, many candidates funneling to the same grounded spot (e.g.
    # attempt_place_element_below_air_pocket's recursive descent bottoming
    # out at the same local floor from several different starting pockets)
    # would silently stack duplicates on top of each other instead of
    # occupying the space once, same as generate_nest rejects overlapping nests.
    for existing in _terrain._elements_touching_rect(footprint_rect):
        if footprint_rect.colliderect(existing.get_footprint_rect()):
            return False

    element = element_cls(_terrain.default_zooms, x, y, *args, **kwargs)
    registration_rect = element.get_registration_rect()

    for row, col in _terrain._chunks_in_rect(registration_rect.left, registration_rect.top, registration_rect.width, registration_rect.height, pad=1):
        chunk = _terrain.get_or_create_chunk(row, col)
        chunk.elements.append(element)
        if chunk.built and chunk.mask is not None:
            collide_mask = element.get_collide_hitbox_mask()
            if collide_mask is not None:
                left_c, top_c = chunk.col * CHUNK_SIZE, chunk.row * CHUNK_SIZE
                offset = (int(element.left - left_c), int(element.top - top_c))
                chunk.mask.draw(collide_mask, offset)

    return element


# pygame.Rect truncates float coordinates to int, so placing the anchor at
# the exact analytic tangent point (top == air_pocket.y + air_pocket.r) can
# get truncated back onto the wrong side of that boundary and register as
# overlapping the very pocket it was solved to clear. A little explicit
# clearance keeps it unambiguously outside even after truncation.
_ANCHOR_CLEARANCE = 20.0


def _attempt_place_element_adjacent_to_air_pocket(_terrain, element_cls, air_pocket, side, *args, max_steps=8, **kwargs):
    """Shared implementation for attempt_place_element_below_air_pocket and
    attempt_place_element_above_air_pocket. side=1 solves for the anchor's
    top edge just clearing the pocket's bottom (element pokes UP into the
    pocket, e.g. a spike); side=-1 solves for the anchor's bottom edge just
    clearing the pocket's top (element hangs DOWN into the pocket, e.g. a
    vine). Both walk through whichever pocket blocks the candidate and
    retry from there -- descending for side=1, ascending for side=-1 --
    until they find an actual boundary (or max_steps is hit). Every step is
    solved purely from element_cls.get_placement_geometry, so nothing is
    constructed unless a placement finally succeeds."""
    width, height, anchor_left, anchor_top, anchor_width, anchor_height = element_cls.get_placement_geometry(*args, **kwargs)
    search_radius = _anchor_search_radius(anchor_width, anchor_height)

    for _ in range(max_steps + 1):
        x = air_pocket.x + width / 2 - anchor_left - anchor_width / 2
        if side > 0:
            y = air_pocket.y + air_pocket.r + _ANCHOR_CLEARANCE + height / 2 - anchor_top
        else:
            y = air_pocket.y - air_pocket.r - _ANCHOR_CLEARANCE + height / 2 - anchor_top - anchor_height
        rect = pygame.Rect(x - width / 2 + anchor_left, y - height / 2 + anchor_top, anchor_width, anchor_height)

        blocker = _find_blocking_air_pocket(_terrain, rect, x, y, search_radius)
        if blocker is None:
            return attempt_place_element(_terrain, element_cls, x, y, *args, **kwargs)
        air_pocket = blocker

    return False


def attempt_place_element_below_air_pocket(_terrain, element_cls, air_pocket, *args, max_descend=8, **kwargs):
    """Places element_cls so its anchor rect is horizontally centered under
    air_pocket and just clears its bottom edge, so the bulk of the element
    above the anchor pokes up into the pocket's open space (e.g. a spike
    growing up off the floor). See _attempt_place_element_adjacent_to_air_pocket
    for the shared descend/ascend walk."""
    return _attempt_place_element_adjacent_to_air_pocket(_terrain, element_cls, air_pocket, 1, *args, max_steps=max_descend, **kwargs)


def attempt_place_element_above_air_pocket(_terrain, element_cls, air_pocket, *args, max_ascend=8, **kwargs):
    """Mirror of attempt_place_element_below_air_pocket: places element_cls
    so its anchor rect is horizontally centered above air_pocket and just
    clears its top edge, so the bulk of the element below the anchor hangs
    down into the pocket's open space (e.g. a vine dangling off a
    ceiling). Walks UP through whichever pocket blocks the candidate,
    instead of down."""
    return _attempt_place_element_adjacent_to_air_pocket(_terrain, element_cls, air_pocket, -1, *args, max_steps=max_ascend, **kwargs)


def attempt_place_neighbors(_terrain, element, spacing=None, count=2, *args, randomize_kwargs=None, **kwargs):
    """Given an already-placed element, try count more placements on each
    side of it (so 2*count attempts total) at increasing multiples of
    spacing, same y -- e.g. to grow a lone grounded spike into a short row
    along the floor it landed on. Each attempt is a single plain
    attempt_place_element call (same grounded + no-overlap checks as any
    other placement, no recursive descent) -- so a side that isn't grounded
    there, or would overlap something else, just doesn't spawn, no retrying.

    *args/**kwargs are forwarded to element_cls the same way they were for
    the original placement, and should normally just be the original call's
    own args -- except randomize_kwargs, if given: a zero-arg callable
    invoked fresh for every single neighbor attempt, whose returned dict is
    merged over kwargs for that attempt only. Use it to re-roll anything
    that shouldn't be identical across the row (e.g. size), while leaving
    everything else (variant pool, etc) matching the original call.

    Returns the list of newly placed neighbors (0 to 2*count elements)."""
    if spacing is None:
        spacing = element.width * 2 / 3
    placed = []
    for i in range(1, count + 1):
        for dx in (-spacing * i, spacing * i):
            call_kwargs = {**kwargs, **randomize_kwargs()} if randomize_kwargs is not None else kwargs
            neighbor = attempt_place_element(_terrain, type(element), element.x + dx, element.y, *args, **call_kwargs)
            if neighbor:
                placed.append(neighbor)
    return placed
