import pygame

class Element:
    """Base class for all world elements (decorations, fire, bouncepads).
    Subclasses must implement draw() and getHitboxSurface()."""

    def __init__(self, defaultZooms, x, y, attachedX, attachedY, attachedR, laserCollides:bool, playerCollides:bool):
        self.x = x
        self.y = y

        #attachedx,attachedy, and attachedr represent a circular hitbox that can be hit to remove the element
        self.attachedX = attachedX
        self.attachedY = attachedY
        self.attachedR = attachedR

        self.laserCollides=laserCollides
        self.playerCollides=playerCollides

        self.defaultZooms = defaultZooms

    def getHitboxSurface(self, zoom):
        """Return the SRCALPHA hitbox surface for this structure at the given zoom.
        White pixels = solid, transparent = passable.
        Subclasses must override this."""
        raise NotImplementedError
    
    def draw(self, zoom):
        """Return the SRCALPHA hitbox surface for this structure at the given zoom.
        White pixels = solid, transparent = passable.
        Subclasses must override this."""
        raise NotImplementedError