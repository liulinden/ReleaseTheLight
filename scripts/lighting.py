import random

import pygame

from scripts.global_assets import get_asset

# FIX 2: images loaded in init() after display exists
mist_particle_im_gs = []
light_gradient = None
thick_gradient = None


def init():
    global mist_particle_im_gs, light_gradient, thick_gradient
    mist_particle_im_gs = []
    for i in range(5):
        mist_particle_im_gs.append(get_asset("MistParticle" + str(i + 1)))
    light_gradient = get_asset("LightGradient")
    thick_gradient = get_asset("ThickGradient")


class Lighting:
    def __init__(self, default_zooms=(0.1, 2)):
        self.particles = []
        self.resized_light_im_gs = {}
        self.resized_light_im_gs["MistParticles"] = []
        for light_img in mist_particle_im_gs:
            for size in [110, 130, 150]:
                imgs = {}
                for zoom in default_zooms:
                    imgs[zoom] = pygame.transform.scale(light_img, (zoom * size, zoom * size))
                self.resized_light_im_gs["MistParticles"].append(imgs)
        for size in [400, 600, 800]:
            self.resized_light_im_gs["Gradient" + str(size)] = {}
            for zoom in default_zooms:
                self.resized_light_im_gs["Gradient" + str(size)][zoom] = pygame.transform.scale(light_gradient, (zoom * size, zoom * size))
        size = 300
        self.resized_light_im_gs["ThickGradient"] = {}
        for zoom in default_zooms:
            self.resized_light_im_gs["ThickGradient"][zoom] = pygame.transform.scale(thick_gradient, (zoom * size, zoom * size))

        # FIX 1: pre-allocate gradient filter surfaces keyed by (zoom, gradient_size)
        # so drawGradient never allocates a Surface per call
        self._gradient_filters = {}
        self._gradient_premul = {}  # non-SRCALPHA surface for pre-multiplied composite
        for size in [400, 600, 800]:
            for zoom in default_zooms:
                dims = self.resized_light_im_gs["Gradient" + str(size)][zoom].get_size()
                surf = pygame.Surface(dims, flags=pygame.SRCALPHA)
                self._gradient_filters[(zoom, size)] = surf
                self._gradient_premul[(zoom, size)] = pygame.Surface(dims)  # black opaque

    def add_mist_particle(self, x, y, color=(255, 255, 255)):
        # FIX 2: was indexing a dict with an integer (bug) — now correctly indexes the list
        mist_list = self.resized_light_im_gs["MistParticles"]
        new_particle = MistParticle(x, y, mist_list[random.randint(0, len(mist_list) - 1)], color)
        self.particles.append(new_particle)

    def tick_effects(self, frame_length):
        for i in range(len(self.particles) - 1, -1, -1):
            if self.particles[i].tick(frame_length) == "end":
                # FIX 1: del at known index is O(1); list.remove() scans from front O(n)
                del self.particles[i]

    def draw_gradient(self, surface: pygame.Surface, frame, color, x, y, offset_x=0, offset_y=0):
        left, top, zoom = frame

        img = self.resized_light_im_gs["Gradient400"][zoom]
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

    def draw_thick_gradient(self, surface: pygame.Surface, frame, x, y, offset_x=0, offset_y=0):
        left, top, zoom = frame

        img = self.resized_light_im_gs["ThickGradient"][zoom]
        dimensions = img.get_size()
        surface.blit(img, ((x - left) * zoom - dimensions[0] / 2 + offset_x, (y - top) * zoom - dimensions[1] / 2 + offset_y))

    def draw_effects(self, surface: pygame.Surface, frame, offset_x=0, offset_y=0):
        for particle in self.particles:
            particle.draw(surface, frame, offset_x=offset_x, offset_y=offset_y)


class MistParticle:
    def __init__(self, x, y, imgs, color=(255, 255, 255)):
        self.color = color
        self.x_speed = (random.random() - 0.5) / 12
        self.y_speed = (random.random() - 0.5) / 12
        self.life_time = 500
        self.x = x + random.randint(-50, 50)
        self.y = y + random.randint(-50, 50)
        self.brightness = (random.random() + 0.2) * 2
        self.fade_in = 0
        # FIX 2: was assigning self.IMGs = IMGs then immediately overwriting with {}
        # Now we only build the tinted dict once
        self.IMGs = {}
        self._premul = {}
        for key in imgs:
            dimensions = (imgs[key].get_width(), imgs[key].get_height())
            filt = pygame.Surface(dimensions, flags=pygame.SRCALPHA)
            filt.fill((self.color[0], self.color[1], self.color[2], 255))
            filt.blit(imgs[key], (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            self.IMGs[key] = filt
            self._premul[key] = pygame.Surface(dimensions)  # black opaque, reused each draw

    def tick(self, frame_length):
        self.life_time -= frame_length / 3
        if self.life_time < 0:
            return "end"
        self.x += self.x_speed * frame_length
        self.y += self.y_speed * frame_length
        self.y_speed -= frame_length * 0.00001 * frame_length / 60
        self.x_speed *= 0.99994**frame_length
        self.y_speed *= 0.99994**frame_length

        if self.fade_in < 1:
            self.fade_in += 0.02 * frame_length / 16

    def draw(self, surface: pygame.Surface, frame, offset_x=0, offset_y=0):
        left, top, zoom = frame
        img = self.IMGs[zoom]
        dimensions = (img.get_width(), img.get_height())
        # set_alpha scales the whole surface opacity non-destructively
        img.set_alpha(min(255, int(self.life_time / 4 * self.brightness * self.fade_in)))
        # fold alpha into RGB by blitting onto a black opaque surface,
        # then composite additively so the particle illuminates the scene
        self._premul[zoom].fill((0, 0, 0))
        self._premul[zoom].blit(img, (0, 0))
        surface.blit(self._premul[zoom], ((self.x - left) * zoom - dimensions[0] / 2 + offset_x, (self.y - top) * zoom - dimensions[1] / 2 + offset_y), special_flags=pygame.BLEND_ADD)
