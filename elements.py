class Element:
    """Base class for all world elements (decorations, fire, bouncepads).
    Subclasses must implement draw() and getHitboxSurface()."""

    def __init__(self, default_zooms, x, y, attached_x, attached_y, attached_r, laser_collides: bool, player_collides: bool):
        self.x = x
        self.y = y

        # attachedx,attachedy, and attachedr represent a circular hitbox that can be hit to remove the element
        self.attached_x = attached_x
        self.attached_y = attached_y
        self.attached_r = attached_r

        self.laser_collides = laser_collides
        self.player_collides = player_collides

        self.default_zooms = default_zooms

    def get_hitbox_surface(self, zoom):
        """Return the SRCALPHA hitbox surface for this structure at the given zoom.
        White pixels = solid, transparent = passable.
        Subclasses must override this."""
        raise NotImplementedError

    def draw(self, zoom):
        """Return the SRCALPHA hitbox surface for this structure at the given zoom.
        White pixels = solid, transparent = passable.
        Subclasses must override this."""
        raise NotImplementedError
