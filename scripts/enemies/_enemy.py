import math
import random

import pygame

from scripts.global_assets import get_asset
from scripts.UI.health_bar import HealthBar

enemy_attack_frames = {"1": [4, 5]}
enemy_animation_lengths = {"1": {"spawn": 6, "walk": 7, "attack": 9}}
costume_dimensions = {"1": (3 / 8, 3 / 4)}

animation_fps = 15

TILT_MAX = 35  # degrees — well past the player's screen-tilt cap; sprite-only so it can be louder
TILT_DECAY_RATE = 0.06  # degrees/ms — slower than the player's recovery so the lean lingers longer

NOMINAL_FRAME_MS = 1000 / 60  # knockback circles are one-shot impulses, not continuous forces --
# baked to a 60fps frame instead of scaling with actual frame_length, or the "instant" kick becomes
# framerate-dependent and gets crushed to near-zero during hit-stop (see player.py for the full story)

GLOW_DECAY_MS = 200  # ms for the hit-glow to linearly fall from full to zero -- punchy, not a lingering fade

enemy_animations = {}


def init():
    global enemy_animations
    enemy_animations = {}
    for costume_id in ["1"]:
        animation_im_gs = {}

        spawn_im_gs = []
        for i in range(enemy_animation_lengths[costume_id]["spawn"]):
            spawn_im_gs.append(get_asset("enemy_" + costume_id + "_spawn_" + str(i + 1)))
        animation_im_gs["spawn"] = spawn_im_gs

        walk_im_gs = []
        for i in range(enemy_animation_lengths[costume_id]["walk"]):
            walk_im_gs.append(get_asset("enemy_" + costume_id + "_walk_" + str(i + 1)))
        animation_im_gs["walk"] = walk_im_gs

        attack_im_gs = []
        for i in range(enemy_animation_lengths[costume_id]["attack"]):
            attack_im_gs.append(get_asset("enemy_" + costume_id + "_attack_" + str(i + 1)))
        animation_im_gs["attack"] = attack_im_gs
        animation_im_gs["attack_hitbox"] = get_asset("enemy_" + costume_id + "_attack_hitbox")

        enemy_animations[costume_id] = animation_im_gs


# ------------------------------------------------------------------
# Resized-costume-image cache. Enemy size is randomized per spawn, so
# sizes are snapped to a coarse bucket before caching -- otherwise
# almost every enemy would produce a unique, uncached set of scaled
# animation frames. Keyed by (costume_id, snapped_size, zoom, direction).
# Pre-warmed for all known costume/size combinations during loading
# (see prewarm_size_range, called from _enemy_handling.prewarm_cache),
# so Enemy.__init__ during gameplay is just a dict lookup.
# ------------------------------------------------------------------

_SIZE_SNAP = 5
_costume_image_cache = {}


def _snap_enemy_size(size):
    return max(_SIZE_SNAP, int(round(size / _SIZE_SNAP) * _SIZE_SNAP))


def _build_costume_images(costume_id, size, zoom, direction):
    imgs = {}

    resizedspawns = []
    for spawn_img in enemy_animations[costume_id]["spawn"]:
        resized = pygame.transform.smoothscale(spawn_img, (size * zoom, size * zoom))
        if direction == "left":
            resized = pygame.transform.flip(resized, True, False)
        resizedspawns.append(resized)
    imgs["spawn"] = resizedspawns

    resizedwalks = []
    for walk_img in enemy_animations[costume_id]["walk"]:
        resized = pygame.transform.smoothscale(walk_img, (size * zoom, size * zoom))
        if direction == "left":
            resized = pygame.transform.flip(resized, True, False)
        resizedwalks.append(resized)
    imgs["walk"] = resizedwalks

    resized_attacks = []
    for attack_img in enemy_animations[costume_id]["attack"]:
        resized = pygame.transform.smoothscale(attack_img, (size * zoom, size * zoom))
        if direction == "left":
            resized = pygame.transform.flip(resized, True, False)
        resized_attacks.append(resized)
    imgs["attack"] = resized_attacks

    resized = pygame.transform.smoothscale(enemy_animations[costume_id]["attack_hitbox"], (size * zoom, size * zoom))
    if direction == "left":
        resized = pygame.transform.flip(resized, True, False)
    imgs["attack_hitbox"] = resized

    return imgs


def _get_costume_images(costume_id, size, zoom, direction):
    key = (costume_id, size, zoom, direction)
    cached = _costume_image_cache.get(key)
    if cached is None:
        cached = _build_costume_images(costume_id, size, zoom, direction)
        _costume_image_cache[key] = cached
    return cached


def prewarm_size_range(costume_id, size_min, size_max, default_zooms):
    """Builds and caches every (snapped size x zoom x direction) image set
    an enemy of this costume could ever need, so live spawns never pay the
    pygame.transform.scale cost during gameplay."""
    size = _snap_enemy_size(size_min)
    max_snapped = _snap_enemy_size(size_max)
    while size <= max_snapped:
        for zoom in default_zooms:
            for direction in ("left", "right"):
                _get_costume_images(costume_id, size, zoom, direction)
        size += _SIZE_SNAP


class Enemy:
    def __init__(self, default_zooms, nest, costume, color, x, y, size=50, health=500):
        self.costume_id = costume
        # snapped so live-spawned enemies reuse cached scaled images instead
        # of each triggering a fresh set of pygame.transform.scale calls
        self.size = _snap_enemy_size(size)
        self.nest = nest
        self.width = self.size * costume_dimensions[self.costume_id][0]
        self.height = self.size * costume_dimensions[self.costume_id][1]
        self.max_health = health
        self.damage = health
        self.knockback = 0.2
        self.speed = 2
        self.knockback_resistance = 1
        self.gravity_multiplier = 1
        self.attack_frames = enemy_attack_frames[self.costume_id]
        self.animation_lengths = enemy_animation_lengths[self.costume_id]

        self.x = x
        self.y = y
        self.x_speed = 0
        self.y_speed = 0
        self.color = color
        self.health = self.max_health
        self.on_ground = False
        self.animation_timer = 0
        self.animation_frame = 0
        self.facing = "right"
        self.mode = "spawn"
        self.glow = 0
        self.tilt = 0  # sprite-only lean on taking a hit -- never affects the camera
        self.r = math.dist((0, 0), (self.width / 2, self.height / 2))
        self.rect = pygame.Rect(self.x - self.width / 2, self.y - self.height / 2, self.width, self.height)
        self.health_bar = HealthBar(self.max_health)

        self.resized_im_gs = {}
        self._draw_filter = {}
        self._flash_surface = {}

        for zoom in default_zooms:
            zoom_set = {}
            for direction in ["left", "right"]:
                zoom_set[direction] = _get_costume_images(self.costume_id, self.size, zoom, direction)
            self.resized_im_gs[zoom] = zoom_set
            self._draw_filter[zoom] = pygame.Surface((self.size * zoom, self.size * zoom), flags=pygame.SRCALPHA)
            self._flash_surface[zoom] = pygame.Surface((self.size * zoom, self.size * zoom))

    def spawn_particles(self, _terrain):
        _terrain.particles.spawn_light_particles(6, self.color, self.size / 3, self.nest.x, self.nest.y, target=(self.x, self.y))

    def damage_particles(self, _terrain, direct):
        if direct:
            _terrain.particles.spawn_mining_particles(3, (0,0,0), self.size / 3, self.x, self.y)
            _terrain.particles.spawn_mining_particles(5, self.color, self.size / 5, self.x, self.y)
        else:
            _terrain.particles.spawn_mining_particles(2, self.color, self.size / 5, self.x, self.y)

    def nest_death_particles(self, _terrain):
        _terrain.particles.spawn_mining_particles(10, (0,0,0), self.size / 2, self.x, self.y)
        _terrain.particles.spawn_light_particles(15, self.color, self.size / 3, self.x, self.y, target=(self.nest.x, self.nest.y))

    def update_costume(self, frame_length, player):
        self.glow = max(0, self.glow - 255 / GLOW_DECAY_MS * frame_length)
        if self.tilt > 0:
            self.tilt = max(0, self.tilt - TILT_DECAY_RATE * frame_length)
        elif self.tilt < 0:
            self.tilt = min(0, self.tilt + TILT_DECAY_RATE * frame_length)
        self.animation_timer = self.animation_timer + frame_length
        if self.mode == "spawn":
            if self.animation_timer >= self.animation_lengths["spawn"] * 1000 / animation_fps:
                self.mode = "walk"
                self.animation_timer = 0
        elif self.mode == "walk":
            self.animation_timer = self.animation_timer % (self.animation_lengths["walk"] * 1000 / animation_fps)
        elif self.mode == "attack":
            if self.animation_timer >= self.animation_lengths["attack"] * 1000 / animation_fps:
                self.mode = "walk"
                self.animation_timer = 0

        if self.mode == "walk":
            if self.x < player.x:
                self.facing = "right"
            elif self.x > player.x:
                self.facing = "left"

        self.animation_frame = math.floor(self.animation_timer / (1000 / animation_fps))

    def update_rect(self):
        # pygame.Rect rounds float assignment to the nearest int rather than flooring it,
        # which doesn't match terrain._sample_chunk's floor-based pixel grid -- floor
        # explicitly so self.rect.x/y always lands on the same pixel grid collision uses.
        self.rect.x, self.rect.y = math.floor(self.x - self.width / 2), math.floor(self.y - self.height / 2)

    def draw(self, surface, frame, hitbox=False, offset_x=0, offset_y=0):
        cam_x, cam_y, zoom = frame

        self.update_rect()
        if hitbox:
            if self.mode != "spawn":
                l = float(self.rect.left)
                r = float(self.rect.right - 1)
                t = float(self.rect.top)
                b = float(self.rect.bottom - 1)
                pygame.draw.line(surface, self.color, ((l - cam_x) * zoom + offset_x, (t - cam_y) * zoom + offset_y), ((l - cam_x) * zoom + offset_x, (b - cam_y) * zoom + offset_y))
                pygame.draw.line(surface, self.color, ((r - cam_x) * zoom + offset_x, (t - cam_y) * zoom + offset_y), ((r - cam_x) * zoom + offset_x, (b - cam_y) * zoom + offset_y))
                pygame.draw.line(surface, self.color, ((l - cam_x) * zoom + offset_x, (t - cam_y) * zoom + offset_y), ((r - cam_x) * zoom + offset_x, (t - cam_y) * zoom + offset_y))
                pygame.draw.line(surface, self.color, ((l - cam_x) * zoom + offset_x, (b - cam_y) * zoom + offset_y), ((r - cam_x) * zoom + offset_x, (b - cam_y) * zoom + offset_y))
                if self.mode == "attack" and self.animation_frame in self.attack_frames:
                    self.draw_attack_hitbox(surface, frame, offset_x=offset_x, offset_y=offset_y)
        else:
            # FIX 1: reuse pre-allocated draw filter surface
            filt = self._draw_filter[zoom]
            filt.fill(self.color)
            filt.blit(self.resized_im_gs[zoom][self.facing][self.mode][self.animation_frame], (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            if self.glow > 1:
                # brighten toward the enemy's own color on hit -- BLEND_RGB_ADD only
                # touches RGB, so it can't bleed outside the sprite's silhouette
                # (those pixels stay alpha 0)
                flash = self._flash_surface[zoom]
                amt = self.glow / 255
                flash.fill((int(self.color[0] * amt), int(self.color[1] * amt), int(self.color[2] * amt)))
                filt.blit(flash, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
            if self.tilt != 0:
                filt = pygame.transform.rotate(filt, self.tilt)
            surface.blit(filt, ((self.rect.centerx - self.size / 2 - cam_x) * zoom + offset_x, (self.rect.bottom - self.size - cam_y + 5) * zoom + offset_y))

    def draw_health_bar(self, surface, frame, time=None, offset_x=0, offset_y=0):
        cam_x, cam_y, zoom = frame
        self.health_bar.draw(surface, self.color, ((self.rect.centerx - cam_x) * zoom + offset_x, (self.rect.bottom - self.size - cam_y + 5) * zoom + offset_y), self.health, time)

    def draw_attack_hitbox(self, surface, frame, offset_x=0, offset_y=0):
        # never used
        cam_x, cam_y, zoom = frame
        surface.blit(self.resized_im_gs[zoom][self.facing]["attack_hitbox"], ((self.rect.centerx - self.size / 2 - cam_x) * zoom + offset_x, (self.rect.bottom - self.size - cam_y + 5) * zoom + offset_y))

    def deal_damage(self, damage, direct=False):
        if direct:
            self.glow = 255
        else:
            self.glow = 100
        self.health -= damage
        if damage > 0:
            self.health_bar.trigger(direct)
            new_tilt = min(TILT_MAX, math.sqrt(damage * 15) * 5)
            new_tilt = math.copysign(new_tilt, -self.x_speed)
            if abs(new_tilt) > abs(self.tilt):
                self.tilt = new_tilt
        if self.health < 0:
            self.health = 0
            return True
        return False

    def tick_damage_and_knockback(self, frame_length, _terrain, player):
        for knockback_circle in _terrain.knockback_circles:
            pow, x, y, r, falloff = knockback_circle

            dx = self.x - x
            dy = self.y - y
            if dx == 0 and dy == 0:
                dy = -1  # circle acts as if it's one pixel below
            d = math.sqrt(dx**2 + dy**2)
            if player.laser:
                if player.laser.laser_target is self:
                    self.x_speed += NOMINAL_FRAME_MS * dx / d / self.size * pow / self.knockback_resistance
                    self.y_speed += NOMINAL_FRAME_MS * dy / d / self.size * pow / self.knockback_resistance
                elif d < r + self.r:
                    self.x_speed += NOMINAL_FRAME_MS * dx / d / self.size * pow * falloff / self.knockback_resistance
                    self.y_speed += NOMINAL_FRAME_MS * dy / d / self.size * pow * falloff / self.knockback_resistance
            elif d < r + self.r:
                self.x_speed += NOMINAL_FRAME_MS * dx / d / self.size * pow * falloff / self.knockback_resistance
                self.y_speed += NOMINAL_FRAME_MS * dy / d / self.size * pow * falloff / self.knockback_resistance

        for damage_circle in _terrain.player_damage_circles:
            pow, x, y, r, falloff = damage_circle

            dx = self.x - x
            dy = self.y - y
            d = math.sqrt(dx**2 + dy**2)
            if player.laser:
                if player.laser.laser_target is self:
                    self.damage_particles(_terrain, True)
                    _terrain.particles.spawn_mining_particles(10, self.color, self.size / 5, x, y)
                    if self.deal_damage(pow, True):
                        return True
                else:
                    if d < r + self.r:
                        self.damage_particles(_terrain, False)
                        _terrain.particles.spawn_mining_particles(5, self.color, self.size / 10, x, y)
                        if self.deal_damage(pow * falloff):
                            return True
            else:
                if d < r + self.r:
                    self.damage_particles(_terrain, False)
                    if self.deal_damage(pow * falloff):
                        return True

    def tick_gravity(self, frame_length):
        self.y_speed = min(2, self.y_speed + 0.0015 * frame_length * self.gravity_multiplier)

    def tick_enemy_behavior(self, frame_length, player):
        if self.mode == "walk":
            if player.y < self.y - 10 and self.on_ground and random.randint(1, 500) < frame_length:
                self.y_speed = -0.3
            if abs(player.x - self.x) > self.size / 2 or abs(player.y - self.y) > self.size / 2:
                rand = random.randint(0, 3)
                if (player.x < self.x and rand != 3) or rand == 0:
                    if self.on_ground:
                        self.x_speed -= 0.001 * frame_length * self.speed
                    else:
                        self.x_speed -= 0.0003 * frame_length * self.speed
                else:
                    if self.on_ground:
                        self.x_speed += 0.001 * frame_length * self.speed
                    else:
                        self.x_speed += 0.0003 * frame_length * self.speed
            else:
                self.mode = "attack"
                self.animation_timer = 0

            if self.on_ground:
                self.x_speed *= 0.98**frame_length
            else:
                self.x_speed *= 0.993**frame_length

    def attempt_movement(self, frame_length, _terrain):
        self.move_vertical(frame_length, _terrain)
        self.move_horizontal(frame_length, _terrain)

    def check_despawn(self, player):
        return math.dist((self.x, self.y), (player.x, player.y)) > 500

    def handle_attack(self, player):
        if player.immunity_timer == 0 and self.mode == "attack" and self.animation_frame in self.attack_frames:
            if self.attack_collide_rect(player.rect):
                player.immunity_timer = player.immunity_time
                if self.facing == "right":
                    player.x_speed = self.knockback
                else:
                    player.x_speed = -self.knockback
                player.y_speed = -self.knockback
                player.take_enemy_hit(self.damage)

    def tick(self, frame_length, _terrain, player):
        if self.mode != "spawn":
            self.tick_gravity(frame_length)
            if self.tick_damage_and_knockback(frame_length, _terrain, player):
                return True
            self.tick_enemy_behavior(frame_length, player)
            self.attempt_movement(frame_length, _terrain)
            self.handle_attack(player)
            if self.check_despawn(player):
                return True
        self.update_costume(frame_length, player)
        return False

    def move_horizontal(self, frame_length, _terrain):
        self.x += frame_length * self.x_speed
        self.update_rect()
        if self.colliding_with_terrain(_terrain):
            slope_tolerance = math.ceil(3 * abs(frame_length * self.x_speed))
            for i in range(slope_tolerance):
                self.y -= 1
                self.update_rect()
                if not self.colliding_with_terrain(_terrain):
                    self.x_speed -= self.x_speed * i / slope_tolerance
                    return
            self.y += slope_tolerance
            self.x -= frame_length * self.x_speed
            backs = math.ceil(abs(frame_length * self.x_speed / 1))
            for i in range(backs):
                self.x += frame_length * self.x_speed / backs
                self.update_rect()
                if self.colliding_with_terrain(_terrain):
                    self.x -= frame_length * self.x_speed / backs
                    self.update_rect()
                    break
            self.x_speed = 0

    def move_vertical(self, frame_length, _terrain):
        self.on_ground = False
        self.y += frame_length * self.y_speed
        self.update_rect()
        if self.colliding_with_terrain(_terrain):
            if self.y_speed > 0:
                self.on_ground = True
                if not _terrain.nests_collide_rect(self.rect):
                    _terrain.particles.spawn_mining_particles(
                        int(abs((abs(max(0.005 * frame_length, abs(self.x_speed))) - 0.005 * frame_length) + 3 * (self.y_speed - 0.0015 * frame_length)) * 12), (0, 0, 0), 20, self.x, self.y + self.height / 2, time=200
                    )
            if self.y_speed < 0:
                slope_tolerance = math.ceil(abs(0.5 * frame_length * self.y_speed))
                for i in range(slope_tolerance):
                    self.x -= 1
                    self.update_rect()
                    if not self.colliding_with_terrain(_terrain):
                        return
                self.x += slope_tolerance
                for i in range(slope_tolerance):
                    self.x += 1
                    self.update_rect()
                    if not self.colliding_with_terrain(_terrain):
                        return
                self.x -= slope_tolerance
            self.y -= frame_length * self.y_speed
            backs = math.ceil(abs(frame_length * self.y_speed / 1))
            for i in range(backs):
                self.y += frame_length * self.y_speed / backs
                self.update_rect()
                if self.colliding_with_terrain(_terrain):
                    self.y -= frame_length * self.y_speed / backs
                    self.update_rect()
                    break
            self.y_speed = 0

    def colliding_with_terrain(self, _terrain):
        return _terrain.collide_rect(self.rect)

    def attack_collide_rect(self, rect: pygame.Rect):
        rect_mask = pygame.Mask((rect.width, rect.height), fill=True)
        surface = pygame.Surface((rect.width, rect.height), flags=pygame.SRCALPHA)
        self.draw_attack_hitbox(surface, [rect.left, rect.y, 1])
        attack_mask = pygame.mask.from_surface(surface)
        return attack_mask.overlap(rect_mask, (0, 0)) is not None
