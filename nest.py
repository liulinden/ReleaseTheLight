import math
import random

import pygame

import enemies
import UI
from global_assets import get_asset
from util import charges_to_color


def load_nest_img_set(id, stages):
    imgs = []
    for i in range(stages):
        imgs.append(get_asset("Nest" + str(id) + "_" + str(i + 1)))
    return imgs, get_asset("Nest" + str(id) + "Hitbox")


# FIX 2: module-level lightGradient and nestIMGs loaded in init() after display exists
light_gradient = None
nest_im_gs = {}
nest_hitboxes = {}


def init():
    global light_gradient, nest_im_gs, nest_hitboxes
    light_gradient = get_asset("LightGradient")
    nest_im_gs = {}
    nest_hitboxes = {}
    for nest_type, n_stages, variants in [("white", 3, [1, 2, 3, 4]), ("blue", 4, [5, 6]), ("red", 4, [5, 6]), ("sun", 10, [])]:
        img_sets = []
        hitboxes = []
        for variant in variants:
            img_set, hitbox = load_nest_img_set(variant, n_stages)
            img_sets.append(img_set)
            hitboxes.append(hitbox)
        nest_im_gs[nest_type] = img_sets
        nest_hitboxes[nest_type] = hitboxes


class Nest:
    def __init__(self, default_zooms, world_height, layer_index, nest_type, x, y, size):
        self.x = x
        self.y = y
        self.left = x - size / 2
        self.top = y - size / 2
        self.nest_type = nest_type
        selection = nest_im_gs[nest_type]
        id = random.randint(0, len(selection) - 1)
        stage_im_gs = selection[id]
        hitbox = nest_hitboxes[nest_type][id]
        self.size = size
        self.enemies = []
        self.basic_enemy_cap = 1
        self.total_enemy_cap = min(max(3, int(size / 30)), 10)
        self.color = (255, 255, 255)
        self.glow = 0
        self.stage = 0
        self.max_stage = len(stage_im_gs) - 1

        self.resized_hitboxes = {}
        self.resized_gradients = {}
        self.resized_im_gs = {}

        # FIX 1: pre-allocate filter surfaces for draw() and drawGradient() per zoom
        self._draw_filter = {}
        self._gradient_filter = {}

        for zoom in default_zooms:
            imgs = []
            for stage_img in stage_im_gs:
                imgs.append(pygame.transform.scale(stage_img, (size * zoom, size * zoom)))
            self.resized_im_gs[zoom] = imgs
            self.resized_hitboxes[zoom] = pygame.transform.scale(hitbox, (size * zoom, size * zoom))
            grad_img = pygame.transform.scale(light_gradient, (size * zoom, size * zoom))
            self.resized_gradients[zoom] = grad_img

            self._draw_filter[zoom] = pygame.Surface((size * zoom, size * zoom), flags=pygame.SRCALPHA)
            self._gradient_filter[zoom] = pygame.Surface(grad_img.get_size(), flags=pygame.SRCALPHA)

        self.resized_hitboxes[1] = pygame.transform.scale(hitbox, (size, size))
        if 1 not in self._draw_filter:
            self._draw_filter[1] = pygame.Surface((size, size), flags=pygame.SRCALPHA)

        self.max_health = self.y * 200 * (random.random() + 0.5) / world_height + 10 * layer_index
        if self.nest_type == "white":
            self.max_health *= 1.2
            self.max_health += 10
        elif self.nest_type == "blue" or self.nest_type == "red":
            self.max_health += 50
        elif self.nest_type == "sun":
            self.max_health += 1000

        self.health = self.max_health
        self.health_bar = UI.HealthBar(self.max_health)

        self.max_charge = self.max_health / 3 + 100
        self.visual_charge = self.max_charge
        self.charge = self.max_charge * 0.5
        self.charge_rate = self.max_charge / 10000
        self.charging = {"white": 0, "blue": 0, "red": 0}
        self.charging[self.nest_type] = 1

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
        if self.charge == 0 and self.visual_charge != 0:
            self.visual_charge -= frame_length / 10
            if self.visual_charge < 0:
                self.visual_charge = 0
        # self.visualCharge=self.charge
        self.glow += ((self.stage / self.max_stage * self.visual_charge / self.max_charge * 150) - self.glow) / 1500 * frame_length

    def draw_gradient(self, surface, frame, offset_x=0, offset_y=0):
        cam_x, cam_y, zoom = frame
        img = self.resized_gradients[zoom]
        if self.glow > 0:
            # FIX 1: reuse pre-allocated gradient filter surface
            filt = self._gradient_filter[zoom]
            filt.fill((self.color[0], self.color[1], self.color[2], self.glow))
            filt.blit(img, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(filt, ((self.left - cam_x) * zoom + offset_x, (self.top - cam_y) * zoom + offset_y))

    def draw(self, surface, frame, hitbox=False, offset_x=0, offset_y=0):
        cam_x, cam_y, zoom = frame

        img = self.resized_hitboxes[zoom] if hitbox else self.resized_im_gs[zoom][self.stage]

        self.update_color()

        # FIX 1: reuse pre-allocated draw filter surface
        filt = self._draw_filter[zoom]
        filt.fill(self.color)
        filt.blit(img, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(filt, ((self.left - cam_x) * zoom + offset_x, (self.top - cam_y) * zoom + offset_y))

    def draw_health_bar(self, surface, frame, time=None, offset_x=0, offset_y=0):
        if self.stage != self.max_stage:
            cam_x, cam_y, zoom = frame
            self.health_bar.draw(surface, self.color, ((self.x - cam_x) * zoom + offset_x, (self.top - cam_y) * zoom + offset_y), self.health, time)

    def add_enemy(self, c_terrain, player):
        if len(self.enemies) < self.basic_enemy_cap:
            new_enemy = enemies.get_enemy(c_terrain, player, self.nest_type, self.color, self.max_health, self.x, self.y, self.size)
            if new_enemy:
                self.glow = 200
                self.enemies.append(new_enemy)

    def within_effect_radius(self, x, y):
        return math.dist((x, y), (self.x, self.y)) < self.size * 1.5

    def apply_damage_from_circles(self, c_terrain, player):
        new_particles = []
        if self.health > 0:
            for circle in c_terrain.player_damage_circles:
                pow, x, y, r, falloff = circle
                if self.close(x, y, r):
                    # direct hit: full damage; splash: reduced damage
                    direct_hit = any(lase.laser_target is self for lase in player.laser)
                    damage = pow if direct_hit else pow * falloff
                    self.deal_damage(damage, c_terrain, player)
                    new_particles.append([x, y, self.size / (5 if direct_hit else 10)])
                    self.health_bar.trigger(direct_hit)
        return new_particles

    def deal_damage(self, damage, c_terrain, player):
        self.glow = 200
        self.health -= damage
        if self.health < 0:
            self.health = 0
            for enemy in self.enemies:
                enemy.spawn_particles(c_terrain)
            self.enemies = []
        elif len(self.enemies) < self.total_enemy_cap and random.randint(1, 4) == 1:
            new_enemy = enemies.get_enemy(c_terrain, player, self.nest_type, self.color, self.max_health, self.x, self.y, self.size)
            if new_enemy:
                self.enemies.append(new_enemy)
        self.update_stage()

    def update_stage(self):
        self.stage = self.max_stage - math.ceil((self.max_stage - 1) * self.health / self.max_health)
        self.basic_enemy_cap = math.floor(self.stage * 1.5)

    def close(self, x: int, y: int, radius: int):
        return abs(self.x - x) < radius + self.size / 2 and abs(self.y - y) < radius + self.size / 2
