import pygame


class Structure:
    """Base class for all world structures (gateways, future structures).
    Subclasses must implement draw(), drawBack(), tick(), and getHitboxSurface().
    All structures are axis-aligned rectangles in world space, sized in multiples
    of visual_chunk_size, and are baked into chunkHitboxes at generation time."""

    def __init__(self, x, y, width, height, default_zooms):
        self.x = x  # world-space centre x
        self.y = y  # world-space centre y
        self.width = width
        self.height = height
        self.left = x - width / 2
        self.top = y - height / 2
        self.default_zooms = default_zooms

    def get_rect(self):
        return pygame.Rect(self.left, self.top, self.width, self.height)

    def get_hitbox_surface(self, zoom):
        """Return the SRCALPHA hitbox surface for this structure at the given zoom.
        White pixels = solid, transparent = passable.
        Subclasses must override this."""
        raise NotImplementedError

    def get_erase_surface(self, zoom):
        """Return the SRCALPHA surface for this structure's erased air at the given zoom.
        White pixels = air, transparent = passable.
        Subclasses must override this."""
        raise NotImplementedError

    def get_erase_hitbox_surface(self, zoom):
        """Return the SRCALPHA hitbox surface for this structure's erased air at the given zoom.
        White pixels = air, transparent = passable.
        Subclasses must override this."""
        raise NotImplementedError

    def draw(self, surface, frame, offset_x=0, offset_y=0):
        """Draw the front-facing visual (renders after terrain)."""
        raise NotImplementedError

    def draw_back(self, surface, frame, offset_x=0, offset_y=0):
        """Draw the back-facing visual (renders before terrain, behind player)."""
        raise NotImplementedError

    def tick(self, frame_length, terrain, player):
        """Update structure state. Returns True if something changed requiring
        a chunk reblit (e.g. a gateway tile opening)."""
        raise NotImplementedError
