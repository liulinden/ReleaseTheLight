from elements import Element


class Bouncepad(Element):
    def __init__(self, defaultZooms, x, y, size):
        super().__init__(x, y, x, y + size / 2, size / 4, True, False, defaultZooms)

    def getHitboxSurface(self, zoom):
        pass

    def draw(self, zoom):
        pass
