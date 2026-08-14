import random
from collections import OrderedDict

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
        mist_particle_im_gs.append(get_asset("particles_mist_" + str(i + 1)))
    light_gradient = get_asset("gradient_light")
    thick_gradient = get_asset("gradient_thick")

def snap_color(color, snap=4):
    return (color[0] // snap * snap, color[1] // snap * snap, color[2] // snap * snap)

class Lighting:
    def __init__(self, default_zooms=(0.1, 2)):
        self.particles = []
        self.resized_light_im_gs = {}
        self.resized_light_im_gs["particles_mist"] = []
        for light_img in mist_particle_im_gs:
            for size in [110, 130, 150]:
                imgs = {}
                for zoom in default_zooms:
                    imgs[zoom] = pygame.transform.scale(light_img, (zoom * size, zoom * size))
                self.resized_light_im_gs["particles_mist"].append(imgs)
        for size in [400, 600, 800]:
            self.resized_light_im_gs["gradient_" + str(size)] = {}
            for zoom in default_zooms:
                self.resized_light_im_gs["gradient_" + str(size)][zoom] = pygame.transform.smoothscale(light_gradient, (zoom * size, zoom * size))
        size = 300
        self.resized_light_im_gs["gradient_thick"] = {}
        for zoom in default_zooms:
            self.resized_light_im_gs["gradient_thick"][zoom] = pygame.transform.smoothscale(thick_gradient, (zoom * size, zoom * size))

        # NOTE: _gradient_filters / _gradient_premul preallocation removed —
        # GradientCache now owns caching, keyed by color instead of being
        # rebuilt from scratch every draw_gradient call.

    def add_mist_particle(self, x, y, color=(255, 255, 255)):
        mist_list = self.resized_light_im_gs["particles_mist"]
        new_particle = MistParticle(x, y, mist_list[random.randint(0, len(mist_list) - 1)], color)
        self.particles.append(new_particle)

    def tick_effects(self, frame_length):
        for i in range(len(self.particles) - 1, -1, -1):
            if self.particles[i].tick(frame_length) == "end":
                del self.particles[i]

    def draw_gradient(self, surface: pygame.Surface, frame, color, x, y, size=400, offset_x=0, offset_y=0):
        left, top, zoom = frame

        img_lookup = self.resized_light_im_gs["gradient_" + str(size)]
        dimensions = img_lookup[zoom].get_size()

        darken = 60 / 255
        premul = GradientCache.get_premul(img_lookup, zoom, color, darken)

        surface.blit(
            premul,
            ((x - left) * zoom - dimensions[0] / 2 + offset_x, (y - top) * zoom - dimensions[1] / 2 + offset_y),
            special_flags=pygame.BLEND_ADD,
        )

    def draw_thick_gradient(self, surface: pygame.Surface, frame, x, y, offset_x=0, offset_y=0):
        left, top, zoom = frame

        img = self.resized_light_im_gs["gradient_thick"][zoom]
        dimensions = img.get_size()
        surface.blit(img, ((x - left) * zoom - dimensions[0] / 2 + offset_x, (y - top) * zoom - dimensions[1] / 2 + offset_y))

    def draw_effects(self, surface: pygame.Surface, frame, offset_x=0, offset_y=0):
        for particle in self.particles:
            particle.draw(surface, frame, offset_x=offset_x, offset_y=offset_y)

class MistParticle:
    def __init__(self, x, y, imgs, color=(255, 255, 255)):
        self.color = color
        self.base_imgs = imgs  # shared, untinted source images -- no per-particle copies
        self.x_speed = (random.random() - 0.5) / 12
        self.y_speed = (random.random() - 0.5) / 12
        self.life_time = 500
        self.x = x + random.randint(-50, 50)
        self.y = y + random.randint(-50, 50)
        self.brightness = (random.random() + 0.2) * 2
        self.fade_in = 0

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
        base_img = self.base_imgs[zoom]
        dimensions = (base_img.get_width(), base_img.get_height())

        alpha = max(0, min(255, int(self.life_time / 4 * self.brightness * self.fade_in)))
        premul = MistParticleCache.get_premul(self.base_imgs, self.color, zoom, alpha)

        surface.blit(
            premul,
            ((self.x - left) * zoom - dimensions[0] / 2 + offset_x, (self.y - top) * zoom - dimensions[1] / 2 + offset_y),
            special_flags=pygame.BLEND_ADD,
        )


class GradientCache:
    """
    Global cache of premultiplied (tinted + alpha-folded) gradient surfaces.
    Keyed by color, LRU-capped so slowly-drifting colors don't grow unboundedly.
    """

    MAX_COLORS = 20

    _cache: "OrderedDict[tuple, dict]" = OrderedDict()  # (source_id, color, darken) -> {zoom: surface}

    @classmethod
    def get_premul(cls, img_lookup: dict, zoom, color: tuple, darken: float) -> pygame.Surface:
        color = snap_color(color)
        cache_key = (id(img_lookup), color, darken)
        zoom_entry = cls._cache.get(cache_key)
        if zoom_entry is None:
            zoom_entry = {}
            cls._cache[cache_key] = zoom_entry
            if len(cls._cache) > cls.MAX_COLORS:
                cls._cache.popitem(last=False)
        else:
            cls._cache.move_to_end(cache_key)

        surf = zoom_entry.get(zoom)
        if surf is None:
            img = img_lookup[zoom]
            dimensions = img.get_size()

            filt = pygame.Surface(dimensions, flags=pygame.SRCALPHA)
            filt.fill((color[0] * darken, color[1] * darken, color[2] * darken, 255))
            #filt.fill((100,100, 100,255))
            #print((color[0] * darken, color[1] * darken, color[2] * darken, 255))
            filt.blit(img, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

            premul = pygame.Surface(dimensions)
            premul.fill((0, 0, 0))
            premul.blit(filt, (0, 0))

            zoom_entry[zoom] = premul
            surf = premul
        return surf

class MistParticleCache:
    MAX_COLORS = 20
    ALPHA_STEP = 4

    _cache: "OrderedDict[tuple, dict]" = OrderedDict()

    @classmethod
    def get_premul(cls, base_imgs: dict, color: tuple, zoom, alpha: int) -> pygame.Surface:
        alpha_bucket = max(0, min(255, (alpha // cls.ALPHA_STEP) * cls.ALPHA_STEP))
        color = snap_color(color)

        cache_key = (id(base_imgs), color)
        color_entry = cls._cache.get(cache_key)
        if color_entry is None:
            color_entry = {}
            cls._cache[cache_key] = color_entry
            if len(cls._cache) > cls.MAX_COLORS:
                cls._cache.popitem(last=False)
        else:
            cls._cache.move_to_end(cache_key)

        key = (zoom, alpha_bucket)
        surf = color_entry.get(key)
        if surf is None:
            base = base_imgs[zoom]
            tinted = pygame.Surface(base.get_size(), flags=pygame.SRCALPHA)
            tinted.fill((*color, 255))
            tinted.blit(base, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            tinted.set_alpha(alpha_bucket)

            premul = pygame.Surface(base.get_size())
            premul.fill((0, 0, 0))
            premul.blit(tinted, (0, 0))

            color_entry[key] = premul
            surf = premul
        return surf


