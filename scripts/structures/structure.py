import pygame


class Structure:
    """Base class for all world structures (gateways, future structures).
    Distinct from Element: structures are permanent set-pieces baked into
    chunkHitboxes at generation time, not destructible props scattered
    through generation like spikes/vines (see elements.Element).

    All structures are axis-aligned rectangles in world space, sized in
    multiples of visual_chunk_size, with a footprint centered on (x, y) --
    same footprint convention as Element.

    A structure may also carve open space around itself (e.g. a gateway's
    corridor interior) via erase_rects: a list of rects, each given as its
    own (left, top, width, height) relative to the footprint's own (left,
    top), then stored here as absolute world-space pygame.Rects. These
    aren't pixel masks and aren't expected to match the visual art exactly
    -- carving is delegated to Terrain.carve_structure_erase_rects, which
    lines each rect's border with air pockets and carves its interior as a
    plain rect, so a structure just needs to say roughly where it wants
    air, not draw it. A structure with no erase_rects (the default, empty
    list) doesn't carve anything. Generation always places structures
    before elements, so elements spawned afterwards already treat
    erase_rects as ungrounded, same as an air pocket (see
    elements.attempt_place_element).

    Surfaces, masks, and drawing are the exact same set as Element's, and
    behave identically: get_*_surface hooks all return None by default, a
    subclass only overrides the layer(s) it actually uses, and
    draw_back()/draw_front()/draw_hitbox() are no-ops for any hook that
    returns None so callers never need to special-case a missing layer. A
    subclass that draws something other than a static image (e.g. a tile
    whose art depends on open/closed state) can just override
    draw_back()/draw_front() directly instead of the get_*_surface hooks,
    same escape hatch Element offers. tick() defaults to a no-op returning
    False.
    """

    def __init__(self, x, y, width, height, default_zooms, erase_rects=()):
        self.x = x  # world-space centre x
        self.y = y  # world-space centre y
        self.default_zooms = default_zooms

        # footprint: the box this structure's hitbox/visuals are sized to. Centered on (x, y).
        self.width = width
        self.height = height
        self.left = x - width / 2
        self.top = y - height / 2

        # erase_rects: given relative to the footprint's own (left, top),
        # stored here as absolute world coordinates -- see class docstring.
        self.erase_rects = [pygame.Rect(self.left + left, self.top + top, width, height) for left, top, width, height in erase_rects]

        self._collide_hitbox_mask = None
        self._interaction_hitbox_mask = None

    def get_footprint_rect(self):
        return pygame.Rect(self.left, self.top, self.width, self.height)

    def get_erase_rects(self):
        return self.erase_rects

    def get_registration_rect(self):
        """Bounding box of footprint + all erase_rects -- what chunk
        registration/removal should iterate over, since erase_rects aren't
        required to overlap the footprint at all (mirrors
        Element.get_registration_rect)."""
        rect = self.get_footprint_rect()
        return rect.unionall(self.erase_rects) if self.erase_rects else rect

    # ------------------------------------------------------------------
    # Layers -- subclasses override whichever of these hooks they need.
    # Each should return an SRCALPHA surface sized to (width, height) at
    # the given zoom, or None if this structure doesn't use that layer.
    # ------------------------------------------------------------------

    def get_collide_hitbox_surface(self, zoom):
        """Opaque-white-on-transparent surface baked into chunk.mask for
        real player/laser collision. None if this structure has no solid
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
    # shared prewarmed asset cache should override these to return the
    # shared mask instead of building a redundant per-instance one.
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

    def _footprint_screen_pos(self, frame, offset_x=0, offset_y=0):
        """World->screen conversion for the footprint's own top-left --
        shared by draw_back/draw_front so they don't each repeat it."""
        cam_x, cam_y, zoom = frame
        return (self.left - cam_x) * zoom + offset_x, (self.top - cam_y) * zoom + offset_y

    def draw_back(self, surface, frame, offset_x=0, offset_y=0):
        img = self.get_back_surface(frame[2])
        if img:
            surface.blit(img, self._footprint_screen_pos(frame, offset_x, offset_y))

    def draw_front(self, surface, frame, offset_x=0, offset_y=0):
        img = self.get_front_surface(frame[2])
        if img:
            surface.blit(img, self._footprint_screen_pos(frame, offset_x, offset_y))

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
    # Reactions
    # ------------------------------------------------------------------

    def tick(self, frame_length, terrain, player):
        """Update structure state. Returns True if something changed
        requiring a chunk reblit (e.g. a gateway tile opening). No-op by
        default, same convention as Element.tick."""
        return False
