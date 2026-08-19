import math
import random
from collections import OrderedDict

import pygame

from scripts.global_assets import get_asset

# ------------------------------------------------------------------
# Image caches
# ------------------------------------------------------------------
# mining_particle.png -- textured rock-chunk art. light_particle.png --
# solid white with a soft alpha falloff, used for both LightParticle (the
# existing fading glow) and SparkParticle (a non-fading mining_particle
# stand-in for any color other than black). Both are colorized the same
# way: multiply a color-filled surface by the source image (BLEND_RGBA_MULT,
# same tinting technique nest.py's draw() uses) -- leaves the source's own
# per-pixel alpha AND its texture/shading untouched, only recolors RGB.
#
# color is close to continuous in practice (comes from charges_to_color,
# entity .color attributes, etc.), so a plain dict cache keyed on exact
# color could grow without bound over a long play session even with size/
# zoom bucketed on top. angle/size/color are all snapped to a handful of
# buckets to keep the key space small, and the caches are additionally
# capped with LRU eviction as a safety net -- most play sessions will only
# ever touch a small, frequently-reused set of buckets (a handful of charge
# colors, a handful of particle sizes), so the cap should rarely if ever
# actually evict anything live.
# ------------------------------------------------------------------

_raw_mining_img = None
_raw_light_img = None

_SIZE_BUCKET = 2  # px, pre-zoom particle size snap
_COLOR_BUCKET = 32  # per RGB channel
_ALPHA_BUCKET = 16
_ANGLE_STEPS = 24  # discrete rotation steps for mining_particle (15 degrees apart)

_MAX_CACHE_SIZE = 256


def init():
    global _raw_mining_img, _raw_light_img
    _raw_mining_img = get_asset("mining_particle")
    _raw_light_img = get_asset("light_particle")


def _snap_size(size):
    return max(_SIZE_BUCKET, int(round(size / _SIZE_BUCKET) * _SIZE_BUCKET))


def _bucket_color(color):
    return tuple(min(255, int(c) // _COLOR_BUCKET * _COLOR_BUCKET + _COLOR_BUCKET // 2) for c in color[:3])


def _bucket_alpha(alpha):
    return min(255, max(0, int(round(alpha / _ALPHA_BUCKET) * _ALPHA_BUCKET)))


def _bucket_angle(angle):
    step = 2 * math.pi / _ANGLE_STEPS
    return round(angle / step) % _ANGLE_STEPS


class _LRUCache:
    """Bounded cache -- evicts the least-recently-used entry once max_size
    is exceeded. See module docstring for why particle image caches need
    this instead of a plain unbounded dict."""

    def __init__(self, max_size):
        self.max_size = max_size
        self._data = OrderedDict()

    def get_or_build(self, key, build_fn):
        cached = self._data.get(key)
        if cached is not None:
            self._data.move_to_end(key)
            return cached
        value = build_fn()
        self._data[key] = value
        if len(self._data) > self.max_size:
            self._data.popitem(last=False)
        return value


_mining_image_cache = _LRUCache(_MAX_CACHE_SIZE)
_light_image_cache = _LRUCache(_MAX_CACHE_SIZE)


def _get_mining_image(size, zoom, angle_bucket, color_bucket):
    key = (size, zoom, angle_bucket, color_bucket)

    def build():
        side = max(1, int(size * zoom))
        scaled = pygame.transform.smoothscale(_raw_mining_img, (side, side))
        filt = pygame.Surface((side, side), pygame.SRCALPHA)
        filt.fill((*color_bucket, 255))
        filt.blit(scaled, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return pygame.transform.rotate(filt, angle_bucket * (360 / _ANGLE_STEPS))

    return _mining_image_cache.get_or_build(key, build)


def _get_light_image(size, zoom, color_bucket):
    key = (size, zoom, color_bucket)

    def build():
        side = max(1, int(size * zoom))
        scaled = pygame.transform.smoothscale(_raw_light_img, (side, side))
        filt = pygame.Surface((side, side), pygame.SRCALPHA)
        filt.fill((*color_bucket, 255))
        filt.blit(scaled, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return filt

    return _light_image_cache.get_or_build(key, build)


class Particles:
    def __init__(self):
        self.particles = []
        self.pulse_particles = []
        self.light_particles = []
        self.scratch_layer = None
        self.scratch_layer_size = None

    def update_scratch_layer(self, dimensions):
        if dimensions != self.scratch_layer_size:
            self.scratch_layer = pygame.Surface(dimensions, pygame.SRCALPHA)
            self.scratch_layer_size = dimensions

    def spawn_mining_particles(self, n, color, size, x, y, time=500):
        for i in range(n):
            angle = -random.random() * 2 * math.pi
            scale = (random.random() + 1) / 10
            self.particles.append(MiningParticle(color, size, x, y, math.cos(angle) * scale, math.sin(angle) * scale - 0.05, time=time))

    def spawn_spark_particles(self, n, color, size, x, y, time=500):
        """Same spawn/physics/lifetime behavior as spawn_mining_particles,
        but colorized light_particle art instead of black rock debris --
        use this for any color besides (0, 0, 0)."""
        for i in range(n):
            angle = -random.random() * 2 * math.pi
            scale = (random.random() + 1) / 10
            self.particles.append(SparkParticle(color, size, x, y, math.cos(angle) * scale, math.sin(angle) * scale - 0.05, time=time))

    def spawn_light_particles(self, n, color, size, x, y, time=1200, target=None):
        for i in range(n):
            angle = -random.random() * 2 * math.pi
            scale = (random.random() + 1) / 15
            self.light_particles.append(LightParticle(color, size, x, y, math.cos(angle) * scale, math.sin(angle) * scale - 0.05, time=time, target=target))

    def spawn_pulse_particle(self, color, size, x, y, time=600):
        self.pulse_particles.append(PulseParticle(color, size, x, y, time))

    def tick_particles(self, frame_length):
        for particle_set in [self.pulse_particles, self.particles, self.light_particles]:
            for i in range(len(particle_set) - 1, -1, -1):
                if particle_set[i].tick(frame_length):
                    particle_set.remove(particle_set[i])

    def draw_particles(self, surface, frame, offset_x=0, offset_y=0):
        for particle in self.particles:
            particle.draw(surface, frame, offset_x, offset_y)

    def draw_pulse_particles(self, surface: pygame.Surface, frame, offset_x=0, offset_y=0):
        self.update_scratch_layer(surface.get_size())
        self.scratch_layer.fill((0, 0, 0, 0))
        for particle in self.pulse_particles:
            particle.draw(self.scratch_layer, frame, offset_x, offset_y)
        surface.blit(self.scratch_layer, (0, 0))

    def draw_light_particles(self, surface: pygame.Surface, frame, offset_x=0, offset_y=0):
        # drawn onto a per-pixel-alpha scratch layer (like pulse particles) since a
        # plain surface ignores per-color alpha -- that's what lets these fade out
        self.update_scratch_layer(surface.get_size())
        self.scratch_layer.fill((0, 0, 0, 0))
        for particle in self.light_particles:
            particle.draw(self.scratch_layer, frame, offset_x, offset_y)
        surface.blit(self.scratch_layer, (0, 0))


class MiningParticle:
    """Rock-debris particle, colorized mining_particle.png art (see
    _get_mining_image) at a random rotation picked once at spawn time, not
    re-randomized per frame. Default color is (0, 0, 0) everywhere except
    while actually carving terrain, where callers pass the local depth
    color instead so the debris matches the surrounding rock."""

    def __init__(self, color, size, x, y, x_speed=0, y_speed=0, time=500):
        self.color = color
        self.x = x
        self.y = y
        self.x_speed = x_speed
        self.y_speed = y_speed
        self.timer = time
        self.size = random.randint(1, 3) * size / 10
        self.angle_bucket = _bucket_angle(random.random() * 2 * math.pi)

    def tick(self, frame_length):
        self.y_speed += 0.0012 * frame_length
        self.x += self.x_speed * frame_length
        self.y += self.y_speed * frame_length
        self.timer -= frame_length
        return self.timer <= 0

    def draw(self, surface, frame, offset_x=0, offset_y=0):
        left, top, zoom = frame
        img = _get_mining_image(_snap_size(self.size), zoom, self.angle_bucket, _bucket_color(self.color))
        img.set_alpha(255)  # image cache is shared with LightParticle/SparkParticle -- never trust an inherited alpha
        rect = img.get_rect(center=((self.x - left) * zoom + offset_x, (self.y - top) * zoom + offset_y))
        surface.blit(img, rect)


class SparkParticle:
    """Exact same spawn/physics/lifetime behavior as MiningParticle, but
    colorized light_particle.png art instead of black rock debris -- the
    non-(0, 0, 0) replacement for spawn_mining_particles' old color param."""

    def __init__(self, color, size, x, y, x_speed=0, y_speed=0, time=500):
        self.color = color
        self.x = x
        self.y = y
        self.x_speed = x_speed
        self.y_speed = y_speed
        self.timer = time
        self.size = random.randint(1, 3) * size / 10

    def tick(self, frame_length):
        self.y_speed += 0.0012 * frame_length
        self.x += self.x_speed * frame_length
        self.y += self.y_speed * frame_length
        self.timer -= frame_length
        return self.timer <= 0

    def draw(self, surface, frame, offset_x=0, offset_y=0):
        left, top, zoom = frame
        img = _get_light_image(_snap_size(self.size), zoom, _bucket_color(self.color))
        img.set_alpha(255)  # no fade -- image cache is shared with LightParticle, never trust an inherited alpha
        rect = img.get_rect(center=((self.x - left) * zoom + offset_x, (self.y - top) * zoom + offset_y))
        surface.blit(img, rect)


class LightParticle:
    UPWARD_ACCEL = 0.0001  # weak, constant -- becomes the dominant force only once the initial burst decays away
    SPEED_DECAY = 0.994  # per-ms exponential decay applied to both the initial burst and the upward drift
    DRIFT_ACCEL = 0.0006  # pull toward target, if one is set
    FADE_DURATION = 300  # ms -- opacity eases to 0 over this final stretch of life instead of vanishing outright

    def __init__(self, color, size, x, y, x_speed=0, y_speed=0, time=1200, target=None):
        self.color = color
        self.x = x
        self.y = y
        self.x_speed = x_speed
        self.y_speed = y_speed
        self.timer = time
        self.fade_duration = min(LightParticle.FADE_DURATION, time)  # never fade longer than the particle actually lives
        self.size = random.randint(1, 3) * size / 10
        self.target = target

    def tick(self, frame_length):
        decay = self.SPEED_DECAY**frame_length
        self.x_speed *= decay
        self.y_speed *= decay

        if self.target is not None:
            tx, ty = self.target
            dx, dy = tx - self.x, ty - self.y
            d = math.hypot(dx, dy)
            if d > 0:
                self.x_speed += dx / d * self.DRIFT_ACCEL * frame_length
                self.y_speed += dy / d * self.DRIFT_ACCEL * frame_length
        else:
            self.y_speed -= self.UPWARD_ACCEL * frame_length

        self.x += self.x_speed * frame_length
        self.y += self.y_speed * frame_length
        self.timer -= frame_length
        return self.timer <= 0

    def draw(self, surface, frame, offset_x=0, offset_y=0):
        left, top, zoom = frame
        alpha = 255 if self.timer > self.fade_duration else max(0, int(255 * self.timer / self.fade_duration))
        img = _get_light_image(_snap_size(self.size), zoom, _bucket_color(self.color))
        img.set_alpha(_bucket_alpha(alpha))
        rect = img.get_rect(center=((self.x - left) * zoom + offset_x, (self.y - top) * zoom + offset_y))
        surface.blit(img, rect)


class PulseParticle:
    def __init__(self, color, size, x, y, time=0):
        self.color = color
        self.x = x
        self.y = y
        self.timer = time if time != 0 else size * 20
        self.size = size
        self.opacity = 150

        if self.timer == 0:
            self.timer = size * 10

    def tick(self, frame_length):
        self.timer -= frame_length
        factor = self.timer / (self.timer + frame_length)
        self.size *= factor
        self.opacity *= factor
        return self.timer <= 5

    def draw(self, surface, frame, offset_x=0, offset_y=0):
        left, top, zoom = frame
        pygame.draw.circle(surface, (self.color[0], self.color[1], self.color[2], 100), ((self.x - left) * zoom + offset_x, (self.y - top) * zoom + offset_y), self.size * zoom, 2)
