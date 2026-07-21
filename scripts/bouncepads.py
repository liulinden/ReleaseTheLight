from scripts.elements import Element

class BouncePad(Element):
    def __init__(self, default_zooms, x, y, size):
        super().__init__(x, y, x, y + size / 2, size / 4, True, False, default_zooms)

    def get_hitbox_surface(self, zoom):
        pass

    def draw(self, zoom):
        pass
