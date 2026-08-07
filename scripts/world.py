# imports
import math
import random

import pygame

import scripts.cells as cells
import scripts.enemies._enemy as enemies
import scripts.laser as laser
import scripts.lighting as lighting
import scripts.loading_screen as loading_screen
import scripts.nest as nest
import scripts.player as player
import scripts.terrain as terrain
import scripts.UI.charge_display as charge_display
import scripts.UI.interaction_display as interaction_display
from scripts.bloom import get_bloom
from scripts.global_assets import get_asset
from scripts.util import frame_random, rotate_and_get_offset, dist


class World:
    def __init__(self, world_width, world_height, loading_screen: loading_screen.LoadingScreen, default_zooms=(0.1, 2), developing_mode=False):
        self.world_width = world_width
        self.world_height = world_height
        self.default_zooms = default_zooms
        self.developing_mode = developing_mode

        init_loading_screen, objects_loading_screen, generate_loading_screen = loading_screen.subsections(0, 0.05, 0.12)

        inits = [lighting.init, cells.init, enemies.init, nest.init, terrain.init, player.init, laser.init, interaction_display.init, charge_display.init]

        for i, init in enumerate(inits):
            init_loading_screen.put((i + 1) / len(inits), f"{init.__module__}.{init.__name__}()")
            init()

        self.decorations = []

        objects_loading_screen.put(0.5, "Creating terrain object")
        self.terrain = terrain.Terrain(world_width, world_height, default_zooms=default_zooms)
        objects_loading_screen.put(0.6, "Creating player object")
        self.player = player.Player(default_zooms, world_width / 2, -200 if developing_mode else -1200)
        objects_loading_screen.put(0.7, "Creating lighting object")
        self.light = lighting.Lighting(default_zooms=default_zooms)
        objects_loading_screen.put(0.8, "Creating background surface")
        background_raw = get_asset("background")
        self.background = pygame.transform.scale(background_raw, (4000, 4000))
        self.bg_width, self.bg_height = self.background.get_size()
        objects_loading_screen.put(0.9, "Creating foreground surface")
        foreground_raw = get_asset("foreground")
        self.foreground = pygame.transform.scale(foreground_raw, (10000, 10000))
        self.fg_width, self.fg_height = self.foreground.get_size()
        objects_loading_screen.put(1.0, "Object creation complete.")

        self._world_layer = None
        self._world_layer_size = None
        self.scratch_layer = None

        self.foreground_alpha = 0

        self.generate_world(generate_loading_screen)
        self.terrain.start_streaming()

    def generate_world(self, loading_screen):
        self.terrain.generate_world(loading_screen)

    # def generate_next_layer(self):
    #    self.terrain.generate_layer(1)

    def _get_world_layer(self, real_window_size):
        if self._world_layer is None or self._world_layer_size != real_window_size:
            self._world_layer = pygame.Surface(real_window_size)
            self._world_layer_size = real_window_size
            self.scratch_layer = pygame.Surface(real_window_size)
        return self._world_layer, self.scratch_layer

    def add_air_pocket(self, x, y, radius):
        # player-mined pockets go into the layer the player is currently in
        layer_index = self.terrain._layer_for_y(self.player.y)
        self.terrain.add_air_pocket(x, y, radius, layer_index=layer_index, player_made=True)

    def heal_nests(self):
        for chunk in self.terrain.chunks:
            for n in self.terrain.chunks[chunk].nests:
                if n.health > 0:
                    n.health = n.max_health
                    n.stage = 0

    def remove_enemies(self):
        for chunk in self.terrain.chunks:
            for n in self.terrain.chunks[chunk].nests:
                n.enemies.clear()
        self.terrain.enemies = []

    def tick(self, fps, window_size, frame, mouse_pos, keys_down, events):
        left, top, zoom = frame
        frame_length = 1000 / fps
        width, height = window_size[0] / zoom, window_size[1] / zoom
        screen_rect = pygame.Rect(left, top, width, height)

        # update world gen
        self.terrain.update_streaming(self.player.x, self.player.y)
        # still need to add evictions

        self.terrain.new_knockback_circles = []
        self.terrain.new_player_damage_circles = []

        if self.player.tick(frame_length, self.terrain, mouse_pos, keys_down, events):
            return True

        player_speed = dist(self.player.x_speed, self.player.y_speed)
        alpha_target = max(0, 255 - 500 * player_speed)
        self.foreground_alpha += (alpha_target - self.foreground_alpha) * frame_length / (100 if alpha_target < self.foreground_alpha else 1000)
        self.foreground.set_alpha(self.foreground_alpha)

        if frame_random(frame_length, 5) == 1:
            self.light.add_mist_particle(self.player.x, self.player.y, color=self.player.color)
        if self.player.laser:
            lase = self.player.laser
            if frame_random(frame_length, lase.length / 20):
                mist_pos = random.random()
                self.light.add_mist_particle(lase.start_x + mist_pos * lase.length * math.cos(lase.angle), lase.start_y + mist_pos * lase.length * math.sin(lase.angle), color=self.player.color)

        # active nests only
        for n in self.terrain._nests_touching_rect(screen_rect):
            n.update_visuals(frame_length)
            if self.terrain.player_damage_circles:
                for particle_coords in n.apply_damage_from_circles(self.terrain, self.player):
                    self.terrain.particles.spawn_mining_particles(10, n.color, particle_coords[2], particle_coords[0], particle_coords[1])

            if n.stage != n.max_stage:
                d = math.dist((n.x, n.y), (self.player.x, self.player.y))
                if d < 300 and frame_random(frame_length, 0.2 + 0.5 * (300 - d) / 300):
                    n.add_enemy(self.terrain, self.player)
                for i in range(len(n.enemies) - 1, -1, -1):
                    enemy = n.enemies[i]
                    if enemy.tick(frame_length, self.terrain, self.player):
                        self.terrain.enemies.remove(enemy)
                        del n.enemies[i]
            else:
                if frame_random(frame_length, 8 if n.interaction_display.active else 2):
                    self.light.add_mist_particle(n.x, n.y, color=n.color)

        for cell in self.terrain._cells_in_rect(screen_rect):
            if cell.close(window_size, frame):
                cell.tick(frame_length, self.terrain, self.player)

        self.terrain.display_manager.tick(frame_length, keys_down)

        self.light.tick_effects(frame_length)
        self.terrain.particles.tick_particles(frame_length)

        self.terrain.knockback_circles = self.terrain.new_knockback_circles
        self.terrain.player_damage_circles = self.terrain.new_player_damage_circles

        return False

    def draw_background(self, layer, window_size, frame):
        left, top, zoom = frame
        x = (-left / 10 * zoom) % self.bg_width / 2 - self.bg_width / 2
        y = (-top / 10 * zoom) % self.bg_height / 2 - self.bg_height / 2
        layer.blit(self.background, (x, y))

    def draw_foreground(self, layer, window_size, frame):
        left, top, zoom = frame
        x = (-left * 6 * zoom) % self.fg_width / 2 - self.fg_width / 2
        y = ((-top * 6 + 500) * zoom) % self.fg_height / 2 - self.fg_height / 2
        layer.blit(self.foreground, (x, y))

    def get_surface(self, window_size, frame, hitboxes=False, kind_visibility=False, real_window_size=None, offset_x=0, offset_y=0, tilt=0, crosshair=False):
        if real_window_size is None:
            real_window_size = window_size

        layer, scratch_layer = self._get_world_layer(real_window_size)

        if kind_visibility:
            layer.fill((200, 200, 200))
        else:
            self.terrain.draw_depth_background(layer, frame, offset_x=offset_x, offset_y=offset_y)

        self.light.draw_effects(layer, frame, offset_x=offset_x, offset_y=offset_y)

        self.light.draw_gradient(layer, frame, self.player.color, self.player.x, self.player.y, offset_x=offset_x, offset_y=offset_y)
        if self.player.laser:
            if self.player.laser.collision:
                cx, cy = self.player.laser.collision[0]
                self.light.draw_gradient(layer, frame, self.player.color, cx, cy, offset_x=offset_x, offset_y=offset_y)

        self.terrain.draw_nest_gradients(window_size, layer, frame, offset_x=offset_x, offset_y=offset_y)

        self.terrain.draw_enemy_gradients(window_size, layer, frame, offset_x=offset_x, offset_y=offset_y)

        self.terrain.particles.draw_pulse_particles(layer, frame, offset_x=offset_x, offset_y=offset_y)

        self.draw_background(scratch_layer, window_size, frame)

        # struct back elements (behind terrain)

        layer.blit(scratch_layer, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

        self.player.draw(layer, frame, hitboxes=hitboxes, offset_x=offset_x, offset_y=offset_y, tilt=tilt)

        self.terrain.draw_cells(window_size, layer, frame, hitboxes=hitboxes, offset_x=offset_x, offset_y=offset_y)

        self.terrain.draw_enemies(window_size, layer, frame, hitboxes=hitboxes, offset_x=offset_x, offset_y=offset_y)

        self.terrain.particles.draw_particles(layer, frame, offset_x=offset_x, offset_y=offset_y)

        self.terrain.draw_nests(window_size, layer, frame, hitboxes=hitboxes, offset_x=offset_x, offset_y=offset_y)

        self.terrain.draw_terrain(window_size, layer, frame, hitboxes=hitboxes, real_window_size=real_window_size, offset_x=offset_x, offset_y=offset_y)

        # structure front

        time = pygame.time.get_ticks()
        self.terrain.draw_health_bars(window_size, layer, frame, time, offset_x=offset_x, offset_y=offset_y)
        self.terrain.draw_interaction_displays(layer, frame, time, offset_x=offset_x, offset_y=offset_y)

        if not kind_visibility:
            self.draw_foreground(scratch_layer, window_size, frame)
            self.light.draw_thick_gradient(scratch_layer, frame, self.player.x, self.player.y, offset_x=offset_x, offset_y=offset_y)
            if self.player.laser:
                if self.player.laser.collision:
                    cx, cy = self.player.laser.collision[0]
                    self.light.draw_thick_gradient(scratch_layer, frame, cx, cy, offset_x=offset_x, offset_y=offset_y)
            layer.blit(self.scratch_layer, (0, 0), special_flags=pygame.BLEND_MULT)

        if crosshair:
            pygame.draw.line(layer, (100, 100, 100, 0.3), (real_window_size[0] * 0.45, real_window_size[1] // 2), (real_window_size[0] * 0.55, real_window_size[1] // 2), 2)
            pygame.draw.line(layer, (100, 100, 100, 0.3), (real_window_size[0] // 2, real_window_size[1] * 0.45), (real_window_size[0] // 2, real_window_size[1] * 0.55), 2)

        if tilt != 0:
            layer, cx, cy = rotate_and_get_offset(layer, real_window_size[0] / 2, real_window_size[1] / 2, math.radians(tilt))
            layer.blit(layer, (cx, cy))

        if crosshair:
            size = 10
            pygame.draw.line(layer, (255, 0, 0), (real_window_size[0] // 2 - size, real_window_size[1] // 2), (real_window_size[0] // 2 + size, real_window_size[1] // 2), 2)
            pygame.draw.line(layer, (255, 0, 0), (real_window_size[0] // 2, real_window_size[1] // 2 - size), (real_window_size[0] // 2, real_window_size[1] // 2 + size), 2)

        bloom_surface = get_bloom(layer)
        layer.blit(bloom_surface, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        return layer
