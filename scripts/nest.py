import math
import random

import pygame

import scripts.enemies._enemy_handling as _enemy_handling
from scripts.global_assets import get_asset
from scripts.UI.health_bar import HealthBar
from scripts.UI.interaction_display import InteractionDisplay
from scripts.util import charges_to_color

HIT_FLASH_DECAY_MS = 200  # ms for the hit-flash to linearly fall from full to zero -- same punchy feel as enemies


def load_nest_img_set(id, stages):
    imgs = []
    for i in range(stages):
        imgs.append(get_asset("nest_" + str(id) + "_" + str(i + 1)))
    return imgs, get_asset("nest_" + str(id) + "_hitbox")


# FIX 2: module-level nestIMGs loaded in init() after display exists
nest_im_gs = {}
nest_hitboxes = {}


def init():
    global nest_im_gs, nest_hitboxes
    nest_im_gs = {}
    nest_hitboxes = {}
    for nest_type, n_stages, variants in [("white", 4, [1, 2, 3, 4]), ("blue", 5, [5, 6]), ("red", 5, [5, 6]), ("sun", 10, [])]:
        img_sets = []
        hitboxes = []
        for variant in variants:
            img_set, hitbox = load_nest_img_set(variant, n_stages)
            img_sets.append(img_set)
            hitboxes.append(hitbox)
        nest_im_gs[nest_type] = img_sets
        nest_hitboxes[nest_type] = hitboxes


# ------------------------------------------------------------------
# Resized-image cache, mirroring the same approach used for enemies
# (scripts/enemies/_enemy.py). Nest size is randomized per spawn
# (roughly 100-250, see terrain.generate_nest), so sizes are snapped
# to a coarse bucket before caching/building. Pre-warmed for every
# known (nest_type, variant, size bucket) combination during loading,
# so live nest generation is just a dict lookup.
# ------------------------------------------------------------------

_SIZE_SNAP = 10
_NEST_SIZE_MIN = 100
_NEST_SIZE_MAX = 250  # matches terrain.generate_nest's size formula (100 + up to 150 by depth)

_nest_image_cache = {}
_nest_mask_cache = {}


def _snap_nest_size(size):
    return max(_SIZE_SNAP, int(round(size / _SIZE_SNAP) * _SIZE_SNAP))


def _build_nest_images(nest_type, variant_id, size, zoom):
    stage_im_gs = nest_im_gs[nest_type][variant_id]
    hitbox = nest_hitboxes[nest_type][variant_id]
    imgs = [pygame.transform.smoothscale(stage_img, (size * zoom, size * zoom)) for stage_img in stage_im_gs]
    hitbox_img = pygame.transform.scale(hitbox, (size * zoom, size * zoom))
    return imgs, hitbox_img


def _get_nest_images(nest_type, variant_id, size, zoom):
    key = (nest_type, variant_id, size, zoom)
    cached = _nest_image_cache.get(key)
    if cached is None:
        cached = _build_nest_images(nest_type, variant_id, size, zoom)
        _nest_image_cache[key] = cached
    return cached


def _get_nest_hitbox_mask(nest_type, variant_id, size, zoom):
    """Collision truth for nests -- used for terrain-mask carving/solidifying
    and for nests_collide_rect. resized_hitboxes (the Surface) is kept only
    for the dev hitbox-debug draw; this is what actual collision checks use."""
    key = (nest_type, variant_id, size, zoom)
    cached = _nest_mask_cache.get(key)
    if cached is None:
        _, hitbox_img = _get_nest_images(nest_type, variant_id, size, zoom)
        cached = pygame.mask.from_surface(hitbox_img)
        _nest_mask_cache[key] = cached
    return cached


def prewarm_cache(default_zooms, loading_screen=None):
    """Builds and caches every (nest_type, variant, snapped size, zoom)
    image set that can occur, so live nest generation never scales images
    on the main thread. Collision masks are only ever needed at native
    (zoom=1) resolution -- zoom only matters for rendering."""
    size_min, size_max = _snap_nest_size(_NEST_SIZE_MIN), _snap_nest_size(_NEST_SIZE_MAX)
    steps_per_variant = (size_max - size_min) // _SIZE_SNAP + 1
    total_steps = sum(len(variants) * steps_per_variant for variants in nest_im_gs.values() if variants)
    done = 0
    for nest_type, variants in nest_im_gs.items():
        if not variants:
            continue  # e.g. "sun" nests are defined but never generated
        for variant_id in range(len(variants)):
            size = size_min
            while size <= size_max:
                for zoom in default_zooms:
                    _get_nest_images(nest_type, variant_id, size, zoom)
                _get_nest_images(nest_type, variant_id, size, 1)  # zoom=1 image always needed for the hitbox-debug draw
                _get_nest_hitbox_mask(nest_type, variant_id, size, 1)
                size += _SIZE_SNAP
                done += 1
                if loading_screen is not None:
                    loading_screen.put(done / total_steps, f"Pre-building nest cache ({nest_type})")


class Nest:
    def __init__(self, default_zooms, world_height, nest_type, x, y, size):
        # snapped so live-generated nests reuse cached scaled images instead
        # of each triggering a fresh set of pygame.transform.scale calls
        size = _snap_nest_size(size)

        self.x = x
        self.y = y
        self.left = x - size / 2
        self.top = y - size / 2
        self.nest_type = nest_type
        selection = nest_im_gs[nest_type]
        variant_id = random.randint(0, len(selection) - 1)
        stage_im_gs = selection[variant_id]
        self.variant_id = variant_id
        self.size = size
        self.enemies = []
        self.basic_enemy_cap = 1
        # self.total_enemy_cap = min(max(3, int(size / 30)), 10)
        self.color = (255, 255, 255)
        self.glow = 0
        self.hit_flash = 0  # sprite-only hit-flash, separate from the ambient charge glow -- only shown before max_stage
        self.stage = 0
        self.max_stage = len(stage_im_gs) - 1

        # resized_hitboxes (Surfaces) are kept only for the dev hitbox-debug
        # draw; hitbox_mask (a single native-resolution Mask, not one per
        # zoom -- collision is never sampled at any other resolution) is
        # what actual collision checks use.
        self.resized_hitboxes = {}
        self.resized_im_gs = {}

        # FIX 1: pre-allocate filter surfaces for draw() per zoom
        self._draw_filter = {}
        self._flash_surface = {}

        for zoom in default_zooms:
            imgs, hitbox_img = _get_nest_images(nest_type, variant_id, size, zoom)
            self.resized_im_gs[zoom] = imgs
            self.resized_hitboxes[zoom] = hitbox_img
            self._draw_filter[zoom] = pygame.Surface((size * zoom, size * zoom), flags=pygame.SRCALPHA)
            self._flash_surface[zoom] = pygame.Surface((size * zoom, size * zoom))

        _, hitbox_img_1 = _get_nest_images(nest_type, variant_id, size, 1)
        self.resized_hitboxes[1] = hitbox_img_1
        self.hitbox_mask = _get_nest_hitbox_mask(nest_type, variant_id, size, 1)
        if 1 not in self._draw_filter:
            self._draw_filter[1] = pygame.Surface((size, size), flags=pygame.SRCALPHA)
        if 1 not in self._flash_surface:
            self._flash_surface[1] = pygame.Surface((size, size))

        self.max_health = self.y * 200 * (random.random() + 0.5) / world_height
        if self.nest_type == "white":
            self.max_health *= 1.2
            self.max_health += 10
        elif self.nest_type == "blue" or self.nest_type == "red":
            self.max_health += 50
        elif self.nest_type == "sun":
            self.max_health += 1000

        self.health = self.max_health
        self.max_charge = self.max_health / 3 + 100
        self.visual_charge = self.max_charge
        self.charge = self.max_charge * 0.5
        self.charge_rate = self.max_charge / 10000
        self.charging = {"white": 0, "blue": 0, "red": 0}
        self.charging[self.nest_type] = 1

        self.health_bar = HealthBar(self.max_health)
        self.interaction_display = InteractionDisplay((self.x, self.top + self.size * 0.75), ("Hold", pygame.K_e, "to drain"), charges_to_color(*self.charging.values(), 500, maximize=True))

    def get_rect(self):
        return pygame.Rect(self.left, self.top, self.size, self.size)

    def update_color(self):
        cw, cb, cr = self.charging.values()
        cw, cb, cr = cw * self.visual_charge, cb * self.visual_charge, cr * self.visual_charge

        self.color = charges_to_color(cw, cb, cr, 500)

        # r, g, b = 0, 0, 0
        # r += cr + cw
        # g += cw + cb / 4
        # b += cw + cb

        # r = (min(r / 500, 1)) ** 0.3
        # g = (min(g / 500, 1)) ** 0.3
        # b = (min(b / 500, 1)) ** 0.3
        # self.color = (r * 255, g * 255, b * 255)

    def lose_charge(self, loss):
        self.glow = 255
        self.charge -= loss
        if self.charge < 0:
            self.charge = 0
            ...

    def update_visuals(self, frame_length):
        self.hit_flash = max(0, self.hit_flash - 255 / HIT_FLASH_DECAY_MS * frame_length)
        if self.charge == 0 and self.visual_charge != 0:
            self.visual_charge *= 0.99**frame_length
            if self.visual_charge < 1:
                self.visual_charge = 0
        # self.visualCharge=self.charge
        self.glow += ((self.stage / self.max_stage * self.visual_charge / self.max_charge * 150) - self.glow) / 1500 * frame_length

    def draw(self, surface, frame, hitbox=False, offset_x=0, offset_y=0):
        cam_x, cam_y, zoom = frame

        img = self.resized_hitboxes[zoom] if hitbox else self.resized_im_gs[zoom][self.stage]

        self.update_color()

        # FIX 1: reuse pre-allocated draw filter surface
        filt = self._draw_filter[zoom]
        filt.fill(self.color)
        filt.blit(img, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        if self.hit_flash > 1 and self.stage != self.max_stage:
            # same punchy hit-flash as enemies -- only shown while still being damaged,
            # not once the nest has fully opened (max_stage becomes a resource, not a target)
            flash = self._flash_surface[zoom]
            amt = self.hit_flash / 255
            flash.fill((int(self.color[0] * amt), int(self.color[1] * amt), int(self.color[2] * amt)))
            filt.blit(flash, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        surface.blit(filt, ((self.left - cam_x) * zoom + offset_x, (self.top - cam_y) * zoom + offset_y))

    def draw_health_bar(self, surface, frame, time=None, offset_x=0, offset_y=0):
        if self.stage != self.max_stage:
            cam_x, cam_y, zoom = frame
            self.health_bar.draw(surface, self.color, ((self.x - cam_x) * zoom + offset_x, (self.top - cam_y) * zoom + offset_y), self.health, time)

    def add_enemy(self, c_terrain, player):
        if len(self.enemies) < self.basic_enemy_cap:
            new_enemy = _enemy_handling.get_enemy(c_terrain, player, self)
            if new_enemy:
                self.glow = 200
                self.enemies.append(new_enemy)
                c_terrain.add_enemy(new_enemy)

    def within_effect_radius(self, x, y):
        return math.dist((x, y), (self.x, self.y)) < self.size * 1.5

    def apply_damage_from_circles(self, c_terrain, player):
        new_particles = []
        if self.health > 0:
            for circle in c_terrain.player_damage_circles:
                pow, x, y, r, falloff = circle
                if self.close(x, y, r):
                    # direct hit: full damage; splash: reduced damage
                    direct_hit = (player.laser.laser_target is self) if player.laser else False
                    damage = pow if direct_hit else pow * falloff
                    self.deal_damage(damage, c_terrain, player, direct_hit)
                    new_particles.append([x, y, self.size / (5 if direct_hit else 10)])
                    self.health_bar.trigger(direct_hit)
        return new_particles

    def deal_damage(self, damage, c_terrain, player, direct=False):
        self.glow = 200
        if self.stage != self.max_stage and direct:
            self.hit_flash = 255
        self.health -= damage
        if self.health < 0:
            self.health = 0
            for enemy in self.enemies:
                enemy.nest_death_particles(c_terrain)
                c_terrain.enemies.remove(enemy)
            self.enemies = []
        # elif random.randint(1, 5) == 1:
        #    self.add_enemy(c_terrain, player)
        if self.update_stage():
            if self.stage != self.max_stage:
                for i in range(3):
                    self.add_enemy(c_terrain, player)

    def update_stage(self):
        new_stage = self.max_stage - math.ceil((self.max_stage - 1) * self.health / self.max_health)
        if new_stage != self.stage:
            self.stage = new_stage
            self.basic_enemy_cap = math.floor(self.stage * 4)
            return new_stage
        return False

    def close(self, x: int, y: int, radius: int):
        return abs(self.x - x) < radius + self.size / 2 and abs(self.y - y) < radius + self.size / 2
