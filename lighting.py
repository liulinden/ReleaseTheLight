import pygame, random, copy, os

from asset_manager import get_asset

# FIX 2: images loaded in init() after display exists
mistParticleIMGs = []
lightGradient = None
thickGradient = None

def init():
    global mistParticleIMGs, lightGradient, thickGradient
    mistParticleIMGs = []
    for i in range(5):
        mistParticleIMGs.append(get_asset("MistParticle" + str(i + 1)))
    lightGradient = get_asset("LightGradient")
    thickGradient= get_asset("ThickGradient")


class Lighting:
    def __init__(self, defaultZooms=[0.1, 2]):
        self.particles = []
        self.resizedLightIMGs = {}
        self.resizedLightIMGs["MistParticles"] = []
        for lightIMG in mistParticleIMGs:
            for size in [110, 130, 150]:
                IMGs = {}
                for zoom in defaultZooms:
                    IMGs[zoom] = pygame.transform.scale(lightIMG, (zoom * size, zoom * size))
                self.resizedLightIMGs["MistParticles"].append(IMGs)
        for size in [400, 600, 800]:
            self.resizedLightIMGs["Gradient" + str(size)] = {}
            for zoom in defaultZooms:
                self.resizedLightIMGs["Gradient" + str(size)][zoom] = pygame.transform.scale(lightGradient, (zoom * size, zoom * size))
        size=300
        self.resizedLightIMGs["ThickGradient"]={}
        for zoom in defaultZooms:
            self.resizedLightIMGs["ThickGradient"][zoom] = pygame.transform.scale(thickGradient, (zoom * size, zoom * size))

        # FIX 1: pre-allocate gradient filter surfaces keyed by (zoom, gradient_size)
        # so drawGradient never allocates a Surface per call
        self._gradient_filters = {}
        self._gradient_premul = {}  # non-SRCALPHA surface for pre-multiplied composite
        for size in [400, 600, 800]:
            for zoom in defaultZooms:
                dims = self.resizedLightIMGs["Gradient" + str(size)][zoom].get_size()
                surf = pygame.Surface(dims, flags=pygame.SRCALPHA)
                self._gradient_filters[(zoom, size)] = surf
                self._gradient_premul[(zoom, size)] = pygame.Surface(dims)  # black opaque

    def addMistParticle(self, x, y, color=(255, 255, 255)):
        # FIX 2: was indexing a dict with an integer (bug) — now correctly indexes the list
        mist_list = self.resizedLightIMGs["MistParticles"]
        newParticle = MistParticle(x, y, mist_list[random.randint(0, len(mist_list) - 1)], color)
        self.particles.append(newParticle)

    def tickEffects(self, frameLength):
        for i in range(len(self.particles) - 1, -1, -1):
            if self.particles[i].tick(frameLength) == "end":
                # FIX 1: del at known index is O(1); list.remove() scans from front O(n)
                del self.particles[i]

    def drawGradient(self, surface: pygame.Surface, frame, color, x, y, offset_x=0, offset_y=0):
        left, top, zoom = frame

        img = self.resizedLightIMGs["Gradient400"][zoom]
        dimensions = img.get_size()

        # Build filter: color tinted at full RGB, soft falloff from gradient PNG's alpha channel.
        # BLEND_RGBA_MULT multiplies both RGB and alpha — so the gradient's alpha falloff
        # is preserved in the filter surface. Then BLEND_ADD composites additively but
        # we need the falloff respected, so we pre-multiply alpha into RGB and use BLEND_ADD.
        filt = self._gradient_filters[(zoom, 400)]
        filt.fill((color[0], color[1], color[2], 255))
        filt.blit(img, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        # Pre-multiply alpha into RGB: blit SRCALPHA filt onto black opaque surface —
        # normal blit folds alpha falloff into RGB against black background.
        premul = self._gradient_premul[(zoom, 400)]
        premul.fill((0, 0, 0))
        premul.blit(filt, (0, 0))
        scale = 60 / 255
        premul.fill((int(scale * 255), int(scale * 255), int(scale * 255)), special_flags=pygame.BLEND_RGB_MULT)
        surface.blit(premul, ((x - left) * zoom - dimensions[0] / 2 + offset_x, (y - top) * zoom - dimensions[1] / 2 + offset_y), special_flags=pygame.BLEND_ADD)

    def drawThickGradient(self, surface: pygame.Surface, frame, x, y, offset_x=0, offset_y=0):
        left, top, zoom = frame

        img = self.resizedLightIMGs["ThickGradient"][zoom]
        dimensions = img.get_size()
        surface.blit(img, ((x - left) * zoom - dimensions[0] / 2 + offset_x, (y - top) * zoom - dimensions[1] / 2 + offset_y))

    def drawEffects(self, surface: pygame.Surface, frame, offset_x=0, offset_y=0):
        for particle in self.particles:
            particle.draw(surface, frame, offset_x=offset_x, offset_y=offset_y)


class MistParticle:
    def __init__(self, x, y, IMGs, color=(255, 255, 255)):
        self.color = color
        self.xSpeed = (random.random() - 0.5) / 12
        self.ySpeed = (random.random() - 0.5) / 12
        self.lifeTime = 500
        self.x = x + random.randint(-50, 50)
        self.y = y + random.randint(-50, 50)
        self.brightness = (random.random() + 0.2) * 2
        self.fadeIn = 0
        # FIX 2: was assigning self.IMGs = IMGs then immediately overwriting with {}
        # Now we only build the tinted dict once
        self.IMGs = {}
        self._premul = {}
        for key in IMGs:
            dimensions = (IMGs[key].get_width(), IMGs[key].get_height())
            filt = pygame.Surface(dimensions, flags=pygame.SRCALPHA)
            filt.fill((self.color[0], self.color[1], self.color[2], 255))
            filt.blit(IMGs[key], (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            self.IMGs[key] = filt
            self._premul[key] = pygame.Surface(dimensions)  # black opaque, reused each draw

    def tick(self, frameLength):
        self.lifeTime -= frameLength / 3
        if self.lifeTime < 0:
            return "end"
        self.x += self.xSpeed * frameLength
        self.y += self.ySpeed * frameLength
        self.ySpeed -= frameLength * 0.00001 * frameLength / 60
        self.xSpeed *= 0.99994 ** frameLength
        self.ySpeed *= 0.99994 ** frameLength

        if self.fadeIn < 1:
            self.fadeIn += 0.02 * frameLength / 16

    def draw(self, surface: pygame.Surface, frame, offset_x=0, offset_y=0):
        left, top, zoom = frame
        img = self.IMGs[zoom]
        dimensions = (img.get_width(), img.get_height())
        # set_alpha scales the whole surface opacity non-destructively
        img.set_alpha(min(255, int(self.lifeTime / 4 * self.brightness * self.fadeIn)))
        # fold alpha into RGB by blitting onto a black opaque surface,
        # then composite additively so the particle illuminates the scene
        self._premul[zoom].fill((0, 0, 0))
        self._premul[zoom].blit(img, (0, 0))
        surface.blit(self._premul[zoom], ((self.x - left) * zoom - dimensions[0] / 2 + offset_x, (self.y - top) * zoom - dimensions[1] / 2 + offset_y), special_flags=pygame.BLEND_ADD)