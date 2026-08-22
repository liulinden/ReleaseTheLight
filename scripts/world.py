# imports
import math
import random

import pygame

import scripts.cells as cells
import scripts.elements.elements as elements
import scripts.enemies._enemy as enemies
import scripts.enemies._enemy_handling as enemy_handling
import scripts.laser as laser
import scripts.lighting as lighting
import scripts.loading_screen as loading_screen
import scripts.nest as nest
import scripts.particles as particles
import scripts.player as player
import scripts.elements.spike as spike
import scripts.elements.vine as vine
import scripts.terrain as terrain
import scripts.UI.charge_display as charge_display
import scripts.UI.interaction_display as interaction_display
from scripts.global_assets import get_asset
from scripts.util import dist, frame_random, poisson_count, rotate_and_get_offset

SPIKES_PER_CHUNK = 5  # expected number of spike-placement attempts per chunk that has any air pockets
VINES_PER_CHUNK = 10  # expected number of vine-placement attempts per chunk that has any air pockets


class World:

    def __init__(self, world_width, world_height, loading_screen: loading_screen.LoadingScreen, default_zooms=(0.1, 2), developing_mode=False, profiler=None):
        self.world_width = world_width
        self.world_height = world_height
        self.default_zooms = default_zooms
        self.developing_mode = developing_mode

        # Split points below are sized from measured wall-clock proportions
        # (asset-heavy prewarm steps dominate; object creation and init()
        # calls are near-instant) rather than being evenly spaced, so the
        # bar advances at roughly the same rate throughout instead of
        # racing through cheap steps and stalling on expensive ones.
        init_loading_screen, objects_loading_screen, generate_loading_screen = loading_screen.subsections(0, 0.05, 0.45)

        inits = [lighting.init, cells.init, enemies.init, nest.init, spike.init, vine.init, particles.init, terrain.init, player.init, laser.init, interaction_display.init, charge_display.init]

        for i, init in enumerate(inits):
            init_loading_screen.put((i + 1) / len(inits), f"{init.__module__}.{init.__name__}()")
            init()

        self.decorations = []

        # object creation itself is near-instant; the three prewarm_cache
        # calls are where almost all the real time in this phase goes, so
        # they get the bulk of the range and report their own progress
        # internally instead of jumping straight from start to finish.
        creation_loading_screen, enemy_prewarm_screen, nest_prewarm_screen, spike_prewarm_screen, vine_prewarm_screen = objects_loading_screen.subsections(0, 0.05, 0.43, 0.97, 0.99)

        creation_loading_screen.put(1 / 6, "Creating terrain object")
        self.terrain = terrain.Terrain(world_width, world_height, default_zooms=default_zooms)
        creation_loading_screen.put(2 / 6, "Creating player object")
        self.player = player.Player(default_zooms, world_width / 2, -200 if developing_mode else -1200)
        creation_loading_screen.put(3 / 6, "Creating lighting object")
        self.light = lighting.Lighting(default_zooms=default_zooms)
        creation_loading_screen.put(4 / 6, "Creating background surfaces")
        background_raw = get_asset("background_1")
        # no transparency in this layer -- .convert() drops the alpha channel
        # get_asset's own .convert_alpha() left it with, so every blit is a
        # straight opaque copy instead of paying for alpha compositing.
        # background_2/foreground keep their alpha (see draw_background/
        # draw_foreground -- they're genuinely translucent layers).
        self.background_1 = pygame.transform.scale(background_raw, (3000, 3000)).convert()
        background_raw = get_asset("background_2")
        self.background_2 = pygame.transform.scale(background_raw, (3000, 3000))
        self.bg_width, self.bg_height = 3000, 3000
        self.gradient_vertical_raw = get_asset("gradient_vertical")
        self.gradient_vertical = None
        creation_loading_screen.put(1.0, "Object creation complete")

        enemy_prewarm_screen.put(0.0, "Pre-building enemy image cache")
        enemy_handling.prewarm_cache(default_zooms, loading_screen=enemy_prewarm_screen)
        nest_prewarm_screen.put(0.0, "Pre-building nest image cache")
        nest.prewarm_cache(default_zooms, loading_screen=nest_prewarm_screen)
        spike_prewarm_screen.put(0.0, "Pre-building spike image cache")
        spike.prewarm_cache(default_zooms, loading_screen=spike_prewarm_screen)
        vine_prewarm_screen.put(0.0, "Pre-building vine image cache")
        vine.prewarm_cache(default_zooms, loading_screen=vine_prewarm_screen)
        objects_loading_screen.put(1.0, "Object creation complete.")

        self._world_layer = None
        self._world_layer_size = None
        self.scratch_layer = None
        self.profiler = profiler

        self.foreground_alpha = 0
        self.ambient_tint = (0, 0, 0)
        self.ambient_tint_int = (0, 0, 0)

        # generate_elements takes roughly 9x as long as generate_world
        # (many small placement attempts vs. a bounded number of cave/nest
        # carves), hence the lopsided split.
        world_gen_screen, elements_gen_screen = generate_loading_screen.subsections(0, 0.1)
        self.generate_world(world_gen_screen)
        self.generate_elements(elements_gen_screen)
        self.terrain.start_streaming()

    def generate_world(self, loading_screen):
        self.terrain.generate_world(loading_screen)

    def generate_elements(self, loading_screen=None):
        """Runs once, after cave/nest truth generation is complete. For
        each chunk that has any air pockets, attempts to place a handful of
        spikes (count varies per chunk but averages SPIKES_PER_CHUNK over
        the whole world) hanging below a randomly-picked air pocket in it,
        the same number of upside-down spikes hanging above one, and a
        handful of vines (VINES_PER_CHUNK) hanging above one. Each
        successful spawn also tries to grow into a short row by attempting
        one more of the same element directly to its left and right."""
        # attempt_place_element can create new chunks (get_or_create_chunk)
        # as a side effect, so snapshot before iterating
        chunks = [chunk for chunk in list(self.terrain.chunks.values()) if chunk.air_pockets]
        if not chunks:
            return
        for i, chunk in enumerate(chunks):
            for _ in range(poisson_count(SPIKES_PER_CHUNK)):
                air_pocket = random.choice(chunk.air_pockets)
                size = random.randint(spike.SIZE_MIN, spike.SIZE_MAX)
                placed = elements.attempt_place_element_adjacent_to_air_pocket(self.terrain, spike.Spike, air_pocket, size=size)
                if placed:
                    elements.attempt_place_neighbors(self.terrain, placed, size=size, randomize_kwargs=lambda: {"size": random.randint(spike.SIZE_MIN, spike.SIZE_MAX)})
            for _ in range(poisson_count(SPIKES_PER_CHUNK)):
                air_pocket = random.choice(chunk.air_pockets)
                size = random.randint(spike.SIZE_MIN, spike.SIZE_MAX)
                placed = elements.attempt_place_element_adjacent_to_air_pocket(self.terrain, spike.UpsideDownSpike, air_pocket, size=size)
                if placed:
                    elements.attempt_place_neighbors(self.terrain, placed, size=size, randomize_kwargs=lambda: {"size": random.randint(spike.SIZE_MIN, spike.SIZE_MAX)})
            for _ in range(poisson_count(VINES_PER_CHUNK)):
                air_pocket = random.choice(chunk.air_pockets)
                size = random.randint(vine.SIZE_MIN, vine.SIZE_MAX)
                slack_factor = random.uniform(vine.SLACK_FACTOR_MIN, vine.SLACK_FACTOR_MAX)
                placed = elements.attempt_place_element_adjacent_to_air_pocket(self.terrain, vine.Vine, air_pocket, size=size, slack_factor=slack_factor)
                if placed:
                    elements.attempt_place_neighbors(
                        self.terrain, placed, placed.width / 4, count=5, size=size, slack_factor=slack_factor,
                        randomize_kwargs=lambda: {"size": random.randint(vine.SIZE_MIN, vine.SIZE_MAX), "slack_factor": random.uniform(vine.SLACK_FACTOR_MIN, vine.SLACK_FACTOR_MAX)},
                    )
            if loading_screen is not None:
                loading_screen.put((i + 1) / len(chunks), f"Generating elements ({i + 1}/{len(chunks)} chunks)")

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
        self.terrain.evict_far_chunks(self.player.x, self.player.y)

        self.terrain.new_knockback_circles = []
        self.terrain.new_player_damage_circles = []

        if self.player.tick(frame_length, self.terrain, mouse_pos, keys_down, events):
            return True

        player_speed = dist(self.player.x_speed, self.player.y_speed)
        alpha_target = max(0, 255 - 600 * player_speed)
        # no longer applied to a CPU surface (see gl_present.py) -- this
        # value is read directly by Game.run() and passed to gl_present.present()
        self.foreground_alpha += (alpha_target - self.foreground_alpha) * frame_length / (100 if alpha_target < self.foreground_alpha else 1500)
        frame_tint = self.terrain.get_frame_color(window_size, frame)
        self.ambient_tint = (
            self.ambient_tint[0] + (frame_tint[0] - self.ambient_tint[0]) * frame_length / 100,
            self.ambient_tint[1] + (frame_tint[1] - self.ambient_tint[1]) * frame_length / 100,
            self.ambient_tint[0] + (frame_tint[2] - self.ambient_tint[2]) * frame_length / 100
        )
        self.ambient_tint_int = (int(self.ambient_tint[0]), int(self.ambient_tint[1]), int(self.ambient_tint[2]))

        if frame_random(frame_length, 5) == 1:
            self.light.add_mist_particle(self.player.x, self.player.y, color=self.player.color)
        if frame_random(frame_length, 4) == 1:
            self.terrain.particles.spawn_light_particles(1, self.player.color, random.randint(5, 20), self.player.x, self.player.y)
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
                    self.terrain.particles.spawn_mining_particles(3, (0,0,0), particle_coords[2], particle_coords[0], particle_coords[1])
                    self.terrain.particles.spawn_spark_particles(5, n.color, particle_coords[2]/2, particle_coords[0], particle_coords[1])

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

        # elements (e.g. Vine's sway) -- scoped to what's on screen, same
        # reasoning as the cells loop just below
        for e in self.terrain._elements_touching_rect(screen_rect):
            e.tick(frame_length, self.terrain, self.player, self.terrain.enemies)

        # dynamic objects cells can nudge away from -- scoped to what's on screen, same as
        # the cells themselves, so this stays cheap regardless of total world population
        visible_cells = self.terrain._cells_in_rect(screen_rect)
        dynamic_objects = [(cell.x, cell.y, cell) for cell in visible_cells]

        for cell in visible_cells:
            if cell.close(window_size, frame):
                if cell.tick(frame_length, self.terrain, self.player, dynamic_objects):
                    self.terrain.remove_cell(cell)

        self.terrain.display_manager.tick(frame_length, keys_down)

        self.light.tick_effects(frame_length)
        self.terrain.particles.tick_particles(frame_length)

        self.terrain.knockback_circles = self.terrain.new_knockback_circles
        self.terrain.player_damage_circles = self.terrain.new_player_damage_circles

        return False

    def draw_vertical_gradient(self, layer, window_size):
        if not self.gradient_vertical or self.gradient_vertical.get_size() != window_size:
            self.gradient_vertical = pygame.transform.smoothscale(self.gradient_vertical_raw, window_size)
        layer.blit(self.gradient_vertical, (0,0))

    def draw_background(self, layer, window_size, frame):
        left, top, zoom = frame
        x = (-left * 1 * zoom) % self.bg_width / 2 - self.bg_width / 2
        y = (-top * 1 * zoom) % self.bg_height / 2 - self.bg_height / 2
        layer.blit(self.background_1, (x, y))
        #self.draw_vertical_gradient(layer, window_size)
        x = (-left * 1.8 * zoom) % self.bg_width / 2 - self.bg_width / 2
        y = (-top * 1.8 * zoom) % self.bg_height / 2 - self.bg_height / 2
        layer.blit(self.background_2, (x, y))

    def draw_world(self, window, window_size, frame, hitboxes=False, kind_visibility=False, real_window_size=None, offset_x=0, offset_y=0, tilt=0, crosshair=False):
        if real_window_size is None:
            real_window_size = window_size

        layer, scratch_layer = self._get_world_layer(real_window_size)
        layer = window

        if kind_visibility:
            layer.fill((200, 200, 200))
        else:
            layer.fill((5, 5, 5))
            # self.terrain.draw_depth_background(layer, frame, offset_x=offset_x, offset_y=offset_y)

        self.light.draw_gradient(layer, frame, self.player.color, self.player.x, self.player.y, size=600, offset_x=offset_x, offset_y=offset_y)
        if self.player.laser:
            if self.player.laser.collision:
                cx, cy = self.player.laser.collision[0]
                self.light.draw_gradient(layer, frame, self.player.color, cx, cy, offset_x=offset_x, offset_y=offset_y)

        self.terrain.draw_nest_gradients(window_size, layer, frame, self.light, offset_x=offset_x, offset_y=offset_y)

        self.terrain.draw_enemy_gradients(window_size, layer, frame, self.light, offset_x=offset_x, offset_y=offset_y)

        self.draw_background(scratch_layer, window_size, frame)

        # struct back elements (behind terrain)
        self.terrain.draw_elements_back(window_size, layer, frame, hitboxes=hitboxes, offset_x=offset_x, offset_y=offset_y)

        layer.blit(scratch_layer, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

        self.light.draw_gradient(layer, frame, self.player.color, self.player.x, self.player.y, offset_x=offset_x, offset_y=offset_y)

        scratch_layer.fill(self.ambient_tint_int)
        layer.blit(scratch_layer, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

        self.light.draw_effects(layer, frame, offset_x=offset_x, offset_y=offset_y)

        self.terrain.particles.draw_pulse_particles(layer, frame, offset_x=offset_x, offset_y=offset_y)

        self.terrain.particles.draw_light_particles(layer, frame, offset_x=offset_x, offset_y=offset_y)

        self.player.draw(layer, frame, hitboxes=hitboxes, offset_x=offset_x, offset_y=offset_y, tilt=tilt)

        self.terrain.draw_cells(window_size, layer, frame, hitboxes=hitboxes, offset_x=offset_x, offset_y=offset_y)

        self.terrain.draw_enemies(window_size, layer, frame, hitboxes=hitboxes, offset_x=offset_x, offset_y=offset_y)

        self.terrain.particles.draw_particles(layer, frame, offset_x=offset_x, offset_y=offset_y)

        self.terrain.draw_nests(window_size, layer, frame, hitboxes=hitboxes, offset_x=offset_x, offset_y=offset_y)

        # elements-front has to come BEFORE draw_terrain: an element's
        # anchor -- and often much of its body, e.g. a vine's full-width top
        # anchor -- is deliberately embedded in solid rock, and that's meant
        # to look embedded, not floating in front of it. draw_terrain's
        # final blit fully overwrites solid-rock pixels (only carved/open
        # areas let what's underneath show through), so drawing here first
        # lets terrain naturally occlude the buried parts of the element and
        # only show whatever actually hangs out into open/carved space.
        self.terrain.draw_elements_front(window_size, layer, frame, hitboxes=hitboxes, offset_x=offset_x, offset_y=offset_y)

        self.terrain.draw_terrain(window_size, layer, frame, hitboxes=hitboxes, real_window_size=real_window_size, offset_x=offset_x, offset_y=offset_y)

        time = pygame.time.get_ticks()
        self.terrain.draw_health_bars(window_size, layer, frame, time, offset_x=offset_x, offset_y=offset_y)
        self.player.draw_cell_charge_bar(layer, frame, offset_x=offset_x, offset_y=offset_y)
        self.terrain.draw_interaction_displays(layer, frame, time, offset_x=offset_x, offset_y=offset_y)

        # Foreground darkening + its thick-gradient "clear zone" around the
        # player/laser used to be applied here (see World.draw_foreground /
        # Lighting.draw_thick_gradient) as a scratch-surface multiply blit --
        # it's now computed on the GPU instead, as part of
        # gl_present.present() (called on this same, still-unmultiplied
        # layer right after draw_world returns), for the same reason bloom
        # moved there: it's a clean final pass over the finished frame, and
        # the GPU does two full-window blits + a multiply far cheaper than
        # CPU blits can. See gl_present.py.

        if crosshair:
            pygame.draw.line(layer, (100, 100, 100, 0.3), (real_window_size[0] * 0.45, real_window_size[1] // 2), (real_window_size[0] * 0.55, real_window_size[1] // 2), 2)
            pygame.draw.line(layer, (100, 100, 100, 0.3), (real_window_size[0] // 2, real_window_size[1] * 0.45), (real_window_size[0] // 2, real_window_size[1] * 0.55), 2)

        if tilt != 0:
            rotated, cx, cy = rotate_and_get_offset(layer, real_window_size[0] / 2, real_window_size[1] / 2, math.radians(tilt))
            layer.blit(rotated, (cx, cy))

        if crosshair:
            size = 10
            pygame.draw.line(layer, (255, 0, 0), (real_window_size[0] // 2 - size, real_window_size[1] // 2), (real_window_size[0] // 2 + size, real_window_size[1] // 2), 2)
            pygame.draw.line(layer, (255, 0, 0), (real_window_size[0] // 2, real_window_size[1] // 2 - size), (real_window_size[0] // 2, real_window_size[1] // 2 + size), 2)

        # Bloom used to be computed here (see bloom.py) and additively
        # blitted onto layer as the very last step -- it's now computed on
        # the GPU instead, as part of gl_present.present() (called on this
        # same, still-pre-bloom layer right after draw_world returns), for
        # exactly the same reason bloom.py's own docstring gives for
        # downscaling before the CPU pixel work: the full-resolution pass is
        # what dominates the cost, and the GPU does that pass far cheaper
        # than a numpy round-trip can. See gl_present.py.

        return layer
