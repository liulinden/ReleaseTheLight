import math
import random
import threading
import time

import pygame

import nest
import particles
from gateway import GATEWAY_Y_POSITIONS, Gateway
from global_assets import get_asset
from loading_screen import LoadingScreen

NUM_LAYERS = 10

hitbox_chunk_size = 125
max_airpocket_radius = 120
visual_chunk_size = 500
rocks_world_span = 8 * hitbox_chunk_size

# Placeholder charge required to unlock each gateway (index = gateway index)
GATEWAY_CHARGE = [100, 200, 300, 500, 700, 900, 1000, 1200, 1500]

PALETTES = [
    [(0.0, (120, 100, 65)), (0.5, (60, 55, 65)), (1.0, (70, 20, 60))],
    [(0.0, (30, 20, 30)), (0.5, (10, 10, 10)), (0.55, (50, 70, 100)), (0.6, (15, 10, 20)), (1.0, (10, 10, 10))],
    [(0.0, (70, 100, 240)), (0.65, (0, 64, 255)), (0.7, (200, 50, 60)), (0.75, (100, 120, 255)), (1.0, (20, 62, 250))],
    [(0.0, (255, 55, 65)), (0.4, (180, 40, 60)), (0.45, (60, 200, 255)), (0.5, (200, 55, 100)), (1.0, (170, 60, 150))],
    [(0.0, (200, 55, 150)), (0.5, (10, 10, 10)), (1.0, (150, 55, 200))],
    [(0.0, (60, 55, 65)), (1.0, (60, 55, 65))],
    [(0.0, (60, 55, 65)), (1.0, (60, 55, 65))],
    [(0.0, (60, 55, 65)), (1.0, (60, 55, 65))],
    [(0.0, (60, 55, 65)), (1.0, (60, 55, 65))],
    [(0.0, (60, 55, 65)), (1.0, (255, 255, 255))],
]


# load images — call terrain.init() after pygame.display.set_mode()
air_im_gs = {}
circle_im_gs = []
air_hitbox_im_gs = {}
rocks_img = {}
vignette_img = None


def init():
    global air_im_gs, circle_im_gs, air_hitbox_im_gs, rocks_img, vignette_img
    circle_im_gs = []
    for i in range(4):
        circle_im_gs.append(get_asset("AirPocket" + str(i + 1)))
    air_im_gs["Circle"] = circle_im_gs
    for custom_pocket in ["C1"]:
        air_im_gs[custom_pocket] = [get_asset("AirPocket" + custom_pocket)]
        air_hitbox_im_gs[custom_pocket] = get_asset("AirPocket" + custom_pocket + "Hitbox")
    rocks_raw = get_asset("Rocks")
    rocks_img["raw"] = rocks_raw
    vignette_img = get_asset("VignetteGradient")


def rect_to_circle(left, top, width, height):
    return left + width / 2, top + height / 2, math.dist((0, 0), (width, height)) / 2


def _layer_y_bounds(layer_index, world_height):
    """Return (yTop, yBottom) world-space Y range for a layer."""
    y_top = GATEWAY_Y_POSITIONS[layer_index - 1] if layer_index > 0 else 0
    y_bottom = GATEWAY_Y_POSITIONS[layer_index] if layer_index < NUM_LAYERS - 1 else world_height
    return y_top, y_bottom


def world_yto_layer_y(world_y):
    for i in range(NUM_LAYERS - 1):
        if world_y <= GATEWAY_Y_POSITIONS[i]:
            if i == 0:
                return (world_y, 0)
            return world_y - (GATEWAY_Y_POSITIONS)[i - 1], i
    return world_y - (GATEWAY_Y_POSITIONS)[NUM_LAYERS - 2], NUM_LAYERS - 1


def choose_unique_randoms(n: int, low: int, high: int, excluded=[]) -> list[int]:
    nums = set()
    excluded = set(excluded)
    while len(nums) < n:
        nums.add(random.randint(low, high))
        nums = nums - excluded
    return list(nums)


_GRID_CELL = max_airpocket_radius * 2


def _grid_cell(x, y):
    return (int(x // _GRID_CELL), int(y // _GRID_CELL))


def _grid_neighbours(cx, cy):
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            yield (cx + dc, cy + dr)


_scaled_img_cache: dict = {}
_RADIUS_SNAP = 10


def _snap_radius(r: float) -> int:
    return int(round(r / _RADIUS_SNAP) * _RADIUS_SNAP)


def _get_cached_scale(src_surface, pocket_type, img_index, radius, zoom):

    key = (pocket_type, img_index, radius, zoom)

    if key not in _scaled_img_cache:
        side = max(1, int(2 * radius * zoom))
        cached = pygame.transform.scale(src_surface, (side, side))
        _scaled_img_cache[key] = cached

    return _scaled_img_cache[key]


def _get_cached_rim_scale(src_surface, pocket_type, img_index, radius, zoom):

    key = (pocket_type, img_index, radius, zoom, "rim")

    if key not in _scaled_img_cache:
        side = max(1, int(2 * radius * zoom * Terrain._RIM_MULT))
        cached = pygame.transform.scale(src_surface, (side, side))
        cached.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MULT)
        _scaled_img_cache[key] = cached

    return _scaled_img_cache[key]


class Terrain:
    def __init__(self, world_width: int, world_height: int, default_zooms: list = [0.1, 2]):

        self.knockback_circles = []
        self.new_knockback_circles = []
        self.player_damage_circles = []
        self.new_player_damage_circles = []

        # nests and airPockets keyed by layer index
        self.nests = {i: [] for i in range(NUM_LAYERS)}
        self.air_pockets = {i: [] for i in range(NUM_LAYERS)}

        self._air_grid: dict[int, dict[tuple, list]] = {i: {} for i in range(NUM_LAYERS)}

        # active layers for iteration — updated every frame
        self.active_layers = [0]

        # per-layer generation locks and completion tracking
        self._layer_locks = {i: threading.Lock() for i in range(NUM_LAYERS)}
        self._generated_layers = set()

        self.world_width = world_width
        self.world_height = world_height
        self.default_zooms = default_zooms
        self.particles = particles.Particles()

        # gateways
        self.gateways = []
        for gi in range(NUM_LAYERS - 1):
            num_tiles = math.ceil(world_width / visual_chunk_size)
            n_exits = random.randint(math.ceil(num_tiles / 4), math.ceil(num_tiles / 2))
            n_entries = random.randint(1, math.ceil((num_tiles - n_exits) / 2))
            entry_cols = choose_unique_randoms(n_entries, 1, num_tiles - 2)
            exit_cols = choose_unique_randoms(n_exits, 1, num_tiles - 2, entry_cols)
            gw = Gateway(gi, world_width, visual_chunk_size, default_zooms, entry_columns=entry_cols, exit_columns=exit_cols, max_charge_per_entry=GATEWAY_CHARGE[gi])
            gw.on_unlock = self._on_gateway_unlock
            self.gateways.append(gw)

        # chunk surfaces
        self.air_pockets_surfaces = {}
        self.air_pockets_hitboxes_surfaces = {}
        self.chunk_visuals = {}
        self.chunk_hitboxes = {}

        for zoom in default_zooms:
            self.air_pockets_surfaces[zoom] = []
            for row in range(math.ceil(world_height / 500) + 1):
                row_list = []
                for j in range(math.ceil(world_width / 500)):
                    row_list.append(pygame.Surface((500 * zoom, 500 * zoom), pygame.SRCALPHA))
                self.air_pockets_surfaces[zoom].append(row_list)

        for zoom in default_zooms:
            self.air_pockets_hitboxes_surfaces[zoom] = []
            for row in range(math.ceil(world_height / hitbox_chunk_size) + 1):
                row_list = []
                for j in range(math.ceil(world_width / hitbox_chunk_size)):
                    surf = pygame.Surface((hitbox_chunk_size * zoom, hitbox_chunk_size * zoom), pygame.SRCALPHA)
                    # surf.fill((0,0,0,255)) probable not needed
                    row_list.append(surf)
                self.air_pockets_hitboxes_surfaces[zoom].append(row_list)

        for zoom in default_zooms:
            self.chunk_visuals[zoom] = []
            for row in range(math.ceil(world_height / visual_chunk_size) + 1):
                row_list = []
                for col in range(math.ceil(world_width / visual_chunk_size)):
                    surf = pygame.Surface((visual_chunk_size * zoom, visual_chunk_size * zoom), pygame.SRCALPHA)
                    # surf.fill((0,0,0,255)) probable not needed
                    row_list.append(surf)
                self.chunk_visuals[zoom].append(row_list)

        self._rocks_scaled = {}
        for zoom in default_zooms:
            scaled_span = int(rocks_world_span * zoom)
            self._rocks_scaled[zoom] = pygame.transform.scale(rocks_img["raw"], (scaled_span, scaled_span))

        for zoom in default_zooms:
            self.chunk_hitboxes[zoom] = []
            for row in range(math.ceil(world_height / hitbox_chunk_size) + 1):
                row_list = []
                for col in range(math.ceil(world_width / hitbox_chunk_size)):
                    row_list.append(pygame.Surface((hitbox_chunk_size * zoom, hitbox_chunk_size * zoom), pygame.SRCALPHA))
                self.chunk_hitboxes[zoom].append(row_list)

        self._terrain_layer = None
        self._terrain_layer_size = None
        self._collide_scratch = pygame.Surface((512, 512), pygame.SRCALPHA)
        self._collide_scratch_hitbox = pygame.Surface((512, 512), pygame.SRCALPHA)
        self._vignette_surf = None
        self._vignette_size = None
        self._vignette_stencil = None
        self._vignette_stencil_size = None

    # ------------------------------------------------------------------
    # Active layer management
    # ------------------------------------------------------------------

    def update_active_layers(self, player_y):
        """Called each frame from world.tick(). Updates self.activeLayers."""
        current_layer = self._layer_for_y(player_y)
        y_top, y_bottom = _layer_y_bounds(current_layer, self.world_height)
        layer_mid = (y_top + y_bottom) / 2
        if player_y < layer_mid and current_layer > 0:
            adjacent = current_layer - 1
        elif player_y >= layer_mid and current_layer < NUM_LAYERS - 1:
            adjacent = current_layer + 1
        else:
            adjacent = None
        layers = [current_layer]
        if adjacent is not None and adjacent in self._generated_layers:
            layers.append(adjacent)
        self.active_layers = layers

    def _layer_for_y(self, y):
        for i, gy in enumerate(GATEWAY_Y_POSITIONS):
            if y < gy:
                return i
        return NUM_LAYERS - 1

    def get_first_locked_gateway_y(self):
        for gw in self.gateways:
            if not gw.unlocked:
                return gw.y
        return self.world_height

    def _active_nests(self) -> list[nest.Nest]:
        result = []
        for li in self.active_layers:
            result.extend(self.nests[li])
        return result

    def _active_air_pockets(self):
        result = []
        for li in self.active_layers:
            result.extend(self.air_pockets[li])
        return result

    # ------------------------------------------------------------------
    # Gateway unlock callback
    # ------------------------------------------------------------------

    def _on_gateway_unlock(self, gateway_index):
        next_layer = gateway_index + 2
        if next_layer < NUM_LAYERS and next_layer not in self._generated_layers:

            def _generate():
                with self._layer_locks[next_layer - 1]:
                    pass
                print("layer generating - ", next_layer)
                self.generate_layer(next_layer)

            threading.Thread(target=_generate, daemon=True).start()

    # ------------------------------------------------------------------
    # Structure collision baking
    # ------------------------------------------------------------------

    def reblit_structure_on_chunks(self, structure, erase=True):
        for zoom in self.default_zooms:
            erase_hitbox_surf = structure.get_erase_hitbox_surface(zoom)
            hitbox_surf = structure.get_hitbox_surface(zoom)
            if hitbox_surf is None:
                continue
            col_start = max(0, math.floor(structure.left / hitbox_chunk_size) - 1)
            col_end = min(len(self.chunk_hitboxes[zoom][0]) - 1, math.ceil((structure.left + structure.width) / hitbox_chunk_size))
            row_start = max(0, math.floor(structure.top / hitbox_chunk_size) - 1)
            row_end = min(len(self.chunk_hitboxes[zoom]) - 1, math.ceil((structure.top + structure.height) / hitbox_chunk_size))
            for row in range(row_start, row_end + 1):
                for col in range(col_start, col_end + 1):
                    chunk_left = col * hitbox_chunk_size
                    chunk_top = row * hitbox_chunk_size
                    if erase and erase_hitbox_surf:
                        self.chunk_hitboxes[zoom][row][col].blit(erase_hitbox_surf, (zoom * (structure.left - chunk_left), zoom * (structure.top - chunk_top)), special_flags=pygame.BLEND_RGBA_SUB)
                    self.chunk_hitboxes[zoom][row][col].blit(hitbox_surf, (zoom * (structure.left - chunk_left), zoom * (structure.top - chunk_top)), special_flags=pygame.BLEND_RGBA_MAX)

    def _bake_gateway_into_chunks(self, gateway):
        for tile in gateway.tiles:
            self.reblit_structure_on_chunks(tile, True)

    # ------------------------------------------------------------------
    # Surface helpers
    # ------------------------------------------------------------------

    def _get_terrain_layer_surface(self, real_window_size):
        if self._terrain_layer is None or self._terrain_layer_size != real_window_size:
            self._terrain_layer = pygame.Surface(real_window_size, pygame.SRCALPHA)
            self._terrain_layer_size = real_window_size
        self._terrain_layer.fill((255, 255, 255, 255))
        return self._terrain_layer

    # ------------------------------------------------------------------
    # Air pocket / nest surface methods
    # ------------------------------------------------------------------

    def add_air_pocket_to_surfaces(self, air_pocket):
        base_row = math.floor(air_pocket.y / 500)
        base_col = math.floor(air_pocket.x / 500)
        for d_row in range(-1, 2):
            for d_col in range(-1, 2):
                row = base_row + d_row
                col = base_col + d_col
                if row >= 0 and col >= 0 and row <= self.world_height / 500 and col < self.world_width / 500:
                    left, top = col * 500, row * 500
                    for zoom in self.default_zooms:
                        self.air_pockets_surfaces[zoom][row][col].blit(air_pocket.IMGs[zoom], (zoom * (air_pocket.left - left), zoom * (air_pocket.top - top)))
                    if self.chunk_visuals:
                        for zoom in self.default_zooms:
                            if row < len(self.chunk_visuals[zoom]) and col < len(self.chunk_visuals[zoom][row]):
                                self._carve_visual_chunk(air_pocket, row, col, zoom)

        base_row = math.floor(air_pocket.y / hitbox_chunk_size)
        base_col = math.floor(air_pocket.x / hitbox_chunk_size)
        affected_chunks = []
        for d_row in range(-1, 2):
            for d_col in range(-1, 2):
                row = base_row + d_row
                col = base_col + d_col
                if row >= 0 and col >= 0 and row <= self.world_height / hitbox_chunk_size and col < self.world_width / hitbox_chunk_size:
                    left, top = col * hitbox_chunk_size, row * hitbox_chunk_size
                    for zoom in self.default_zooms:
                        if air_pocket.type == "Circle":
                            pygame.draw.circle(self.air_pockets_hitboxes_surfaces[zoom][row][col], (255, 255, 255), (zoom * (air_pocket.x - left), zoom * (air_pocket.y - top)), air_pocket.r * zoom)
                        else:
                            self.air_pockets_hitboxes_surfaces[zoom][row][col].blit(air_pocket.hitbox_im_gs[zoom], (zoom * (air_pocket.left - left), zoom * (air_pocket.top - top)))
                        if air_pocket.type == "Circle":
                            pygame.draw.circle(self.chunk_hitboxes[zoom][row][col], (255, 255, 255, 255), (zoom * (air_pocket.x - left), zoom * (air_pocket.y - top)), air_pocket.r * zoom)
                            self.chunk_hitboxes[zoom][row][col].blit(self.air_pockets_hitboxes_surfaces[zoom][row][col], (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
                        else:
                            self.chunk_hitboxes[zoom][row][col].blit(air_pocket.hitbox_im_gs[zoom], (zoom * (air_pocket.left - left), zoom * (air_pocket.top - top)), special_flags=pygame.BLEND_RGBA_SUB)
                    affected_chunks.append((row, col))

        for row, col in affected_chunks:
            self._reblit_solid_structures_on_chunk(row, col)

    def add_nest_to_hitbox_surfaces(self, new_nest):
        for zoom in self.default_zooms:
            img = new_nest.resized_hitboxes[zoom]
            nest_left = new_nest.left
            nest_top = new_nest.top
            nest_size = new_nest.size
            col_start = max(0, math.floor(nest_left / hitbox_chunk_size) - 1)
            col_end = min(math.ceil(self.world_width / hitbox_chunk_size) - 1, math.ceil((nest_left + nest_size) / hitbox_chunk_size))
            row_start = max(0, math.floor(nest_top / hitbox_chunk_size) - 1)
            row_end = min(math.ceil(self.world_height / hitbox_chunk_size), math.ceil((nest_top + nest_size) / hitbox_chunk_size))
            for row in range(row_start, row_end + 1):
                for col in range(col_start, col_end + 1):
                    if row < len(self.air_pockets_hitboxes_surfaces[zoom]) and col < len(self.air_pockets_hitboxes_surfaces[zoom][row]):
                        chunk_left = col * hitbox_chunk_size
                        chunk_top = row * hitbox_chunk_size
                        offset = (zoom * (nest_left - chunk_left), zoom * (nest_top - chunk_top))
                        if self.chunk_hitboxes[zoom] and row < len(self.chunk_hitboxes[zoom]) and col < len(self.chunk_hitboxes[zoom][row]):
                            self.chunk_hitboxes[zoom][row][col].blit(img, offset, special_flags=pygame.BLEND_RGBA_MAX)

    def _reblit_solid_structures_on_chunk(self, row, col):
        """Re-blit all solid structures (nests + gateway tiles) onto a chunk after mining."""
        chunk_left = col * hitbox_chunk_size
        chunk_top = row * hitbox_chunk_size
        chunk_right = chunk_left + hitbox_chunk_size
        chunk_bottom = chunk_top + hitbox_chunk_size
        for n in self._active_nests():
            if n.left < chunk_right and n.left + n.size > chunk_left and n.top < chunk_bottom and n.top + n.size > chunk_top:
                for zoom in self.default_zooms:
                    self.chunk_hitboxes[zoom][row][col].blit(n.resized_hitboxes[zoom], (zoom * (n.left - chunk_left), zoom * (n.top - chunk_top)), special_flags=pygame.BLEND_RGBA_MAX)
        for gw in self.gateways:
            for tile in gw.tiles:
                if tile.left < chunk_right and tile.left + tile.width > chunk_left and tile.top < chunk_bottom and tile.top + tile.height > chunk_top:
                    for zoom in self.default_zooms:
                        hitbox_surf = tile.get_hitbox_surface(zoom)
                        if hitbox_surf:
                            self.chunk_hitboxes[zoom][row][col].blit(hitbox_surf, (zoom * (tile.left - chunk_left), zoom * (tile.top - chunk_top)), special_flags=pygame.BLEND_RGBA_MAX)

    def carve_structures_visual_air(self, layer_top=0):
        structures = []
        for gw in self.gateways:
            structures.extend(gw.tiles)
        for zoom in self.default_zooms:
            for structure in structures:
                if structure.top + structure.height > layer_top:
                    erase_surf = structure.get_erase_surface(zoom)
                    if erase_surf is None:
                        continue
                    col_start = max(0, math.floor(structure.left / visual_chunk_size) - 1)
                    col_end = min(len(self.chunk_visuals[zoom][0]) - 1, math.ceil((structure.left + structure.width) / visual_chunk_size))
                    row_start = max(0, math.floor(structure.top / visual_chunk_size) - 1)
                    row_end = min(len(self.chunk_visuals[zoom]) - 1, math.ceil((structure.top + structure.height) / visual_chunk_size))
                    for row in range(row_start, row_end + 1):
                        for col in range(col_start, col_end + 1):
                            chunk_left = col * visual_chunk_size
                            chunk_top = row * visual_chunk_size
                            self.chunk_visuals[zoom][row][col].blit(erase_surf, (zoom * (structure.left - chunk_left), zoom * (structure.top - chunk_top)), special_flags=pygame.BLEND_RGBA_SUB)

    # ------------------------------------------------------------------
    # Noise / colour
    # ------------------------------------------------------------------

    def _noise_val(self, x, y, scale=1.0):
        x, y = x * scale, y * scale
        v = math.sin(x * 0.017 + y * 0.011) * 0.4
        v += math.cos(x * 0.031 - y * 0.023) * 0.3
        v += math.sin(x * 0.053 + y * 0.047 + 1.3) * 0.2
        v += math.cos(x * 0.079 - y * 0.061 + 2.7) * 0.1
        return max(-1.0, min(1.0, v))

    def _depth_color(self, world_x, world_y):
        layer_y, layer = world_yto_layer_y(world_y)
        top, bottom = _layer_y_bounds(layer, self.world_height)

        depth = max(0.0, min(1.0, layer_y / (bottom - top)))
        noise = self._noise_val(world_x, world_y) * 0.3
        d = max(0.0, min(1.0, depth + noise))

        palette = PALETTES[layer]
        for i in range(len(palette) - 1):
            d0, c0 = palette[i]
            d1, c1 = palette[i + 1]
            if d <= d1:
                t = (d - d0) / (d1 - d0)
                r = int(c0[0] + (c1[0] - c0[0]) * t)
                g = int(c0[1] + (c1[1] - c0[1]) * t)
                b = int(c0[2] + (c1[2] - c0[2]) * t)
                return (r, g, b)
        return palette[-1][1]

    def _make_gradient_surf(self, tl, tr, bl, br, width, height):
        surf = pygame.Surface((2, 2))
        surf.set_at((0, 0), tl)
        surf.set_at((1, 0), tr)
        surf.set_at((0, 1), bl)
        surf.set_at((1, 1), br)
        return pygame.transform.smoothscale(surf, (width, height))

    # ------------------------------------------------------------------
    # Chunk building (per-layer)
    # ------------------------------------------------------------------

    _RIM_MULT = 1.7

    def _build_chunk_hitboxes_for_layer(self, layer_index):
        y_top, y_bottom = _layer_y_bounds(layer_index, self.world_height)
        for zoom in self.default_zooms:
            air_chunks = self.air_pockets_hitboxes_surfaces[zoom]
            row_start = math.floor(y_top / hitbox_chunk_size)
            row_end = math.ceil(y_bottom / hitbox_chunk_size)
            for row in range(row_start, min(row_end + 1, len(self.chunk_hitboxes[zoom]))):
                for col, chunk in enumerate(self.chunk_hitboxes[zoom][row]):
                    chunk.fill((255, 255, 255, 255))
                    chunk.blit(air_chunks[row][col], (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
            for n in self.nests[layer_index]:
                self._blit_nest_on_chunk_hitboxes(n, zoom)
        for gw in self.gateways:
            if gw.y - visual_chunk_size / 2 < y_bottom and gw.y + visual_chunk_size / 2 > y_top:
                self._bake_gateway_into_chunks(gw)

    def _blit_nest_on_chunk_hitboxes(self, n, zoom):
        img = n.resized_hitboxes[zoom]
        col_start = max(0, math.floor(n.left / hitbox_chunk_size) - 1)
        col_end = min(len(self.chunk_hitboxes[zoom][0]) - 1, math.ceil((n.left + n.size) / hitbox_chunk_size))
        row_start = max(0, math.floor(n.top / hitbox_chunk_size) - 1)
        row_end = min(len(self.chunk_hitboxes[zoom]) - 1, math.ceil((n.top + n.size) / hitbox_chunk_size))
        for row in range(row_start, row_end + 1):
            for col in range(col_start, col_end + 1):
                chunk_left = col * hitbox_chunk_size
                chunk_top = row * hitbox_chunk_size
                self.chunk_hitboxes[zoom][row][col].blit(img, (zoom * (n.left - chunk_left), zoom * (n.top - chunk_top)), special_flags=pygame.BLEND_RGBA_MAX)

    def _build_chunk_visuals_for_layer(self, layer_index, loading_screen: LoadingScreen = None):
        y_top, y_bottom = _layer_y_bounds(layer_index, self.world_height)
        layer_pockets = self.air_pockets[layer_index]
        for i, zoom in enumerate(self.default_zooms):
            air_chunks = self.air_pockets_surfaces[zoom]
            rocks = self._rocks_scaled[zoom]
            rocks_span_px = int(rocks_world_span * zoom)
            chunk_px = int(visual_chunk_size * zoom)
            row_start = math.floor(y_top / visual_chunk_size)
            row_end = min(math.ceil(y_bottom / visual_chunk_size), len(self.chunk_visuals[zoom]) - 1)
            total_rows = row_end - row_start

            if loading_screen is not None:
                loading_bar_section = loading_screen.subsection(i / len(self.default_zooms), (i + 1) / len(self.default_zooms))
            else:
                loading_bar_section = None

            for row in range(row_start, row_end):
                if loading_bar_section is not None:
                    loading_bar_section.put((row - row_start + 1) / total_rows, f"Build chunk visuals row {row - row_start + 1}/{total_rows} ({zoom=})")

                for col, chunk in enumerate(self.chunk_visuals[zoom][row]):
                    world_left = col * visual_chunk_size
                    world_top = row * visual_chunk_size
                    world_right = world_left + visual_chunk_size
                    world_bot = world_top + visual_chunk_size

                    tl = self._depth_color(world_left, world_top)
                    tr = self._depth_color(world_right, world_top)
                    bl = self._depth_color(world_left, world_bot)
                    br = self._depth_color(world_right, world_bot)

                    chunk.fill((0, 0, 0, 255))
                    chunk.blit(self._make_gradient_surf(tl, tr, bl, br, chunk_px, chunk_px), (0, 0), special_flags=pygame.BLEND_RGB_MAX)

                    rock_x = int((world_left * zoom) % rocks_span_px)
                    rock_y = int((world_top * zoom) % rocks_span_px)
                    rock_surf = pygame.Surface((chunk_px, chunk_px))
                    for ty in range(-rock_y, chunk_px, rocks_span_px):
                        for tx in range(-rock_x, chunk_px, rocks_span_px):
                            rock_surf.blit(rocks, (tx, ty))
                    chunk.blit(rock_surf, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

                    rim_margin = visual_chunk_size * self._RIM_MULT
                    for air_pocket in layer_pockets:
                        if (
                            air_pocket.x + air_pocket.r * self._RIM_MULT < world_left - rim_margin
                            or air_pocket.x - air_pocket.r * self._RIM_MULT > world_right + rim_margin
                            or air_pocket.y + air_pocket.r * self._RIM_MULT < world_top - rim_margin
                            or air_pocket.y - air_pocket.r * self._RIM_MULT > world_bot + rim_margin
                        ):
                            continue
                        rim_surf = air_pocket.rim_im_gs[zoom]
                        cx = zoom * (air_pocket.x - world_left)
                        cy = zoom * (air_pocket.y - world_top)
                        rim_size = rim_surf.get_size()
                        chunk.blit(rim_surf, (int(cx - rim_size[0] / 2), int(cy - rim_size[1] / 2)))

                    chunk.blit(air_chunks[row][col], (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
        self.carve_structures_visual_air(y_top)

    # ------------------------------------------------------------------
    # Per-layer generation entry point
    # ------------------------------------------------------------------

    def generate_layer(self, layer_index, loading_screen: LoadingScreen = None):
        """Generate one layer. Thread-safe. Layer 0 threads layer 1 on completion."""

        print(f"{time.strftime('%H:%M:%S')} - layer {layer_index} generating...")

        if loading_screen is not None:
            loading_screen_main, loading_screen_visuals = loading_screen.subsections(0, 0.5)
        else:
            loading_screen_main = loading_screen_visuals = None

        with self._layer_locks[layer_index]:
            if loading_screen_main is not None:
                loading_screen_main.put(0, "Generating master caves")

            y_top, y_bottom = _layer_y_bounds(layer_index, self.world_height)

            if layer_index == 0:
                x = -500
                while x < self.world_width + 500:
                    r = random.randint(10, 30)
                    self.add_air_pocket_clump(x, 0, r, layer_index=layer_index, player_made=True)
                    x += r / 2
                self.generate_descending_cave(self.world_width / 2, 0, 40, math.pi / 2, layer_index=layer_index)
            else:
                self.generate_descending_cave(int((random.random() + 0.5) / 2 * self.world_width), y_top + 20, 30, math.pi / 2, layer_index=layer_index)
                for exit in self.gateways[layer_index - 1].exit_tiles:
                    self.generate_skinny_cave(exit.x, exit.y + exit.tile_size / 4, 50, math.pi / 2, layer_index=layer_index)

            for entry in self.gateways[layer_index].entry_tiles:
                self.generate_skinny_cave(entry.x, entry.y - entry.tile_size / 4, 90, -math.pi / 2, 10, layer_index=layer_index)

            num_steps = int((y_bottom - y_top) / 100)
            for i in range(num_steps):
                if loading_screen_main is not None:
                    loading_screen_main.put((i + 1) / num_steps, f"Generate layer section {i + 1}/{num_steps}")
                for j in range(int(self.world_width / 1000)):
                    if random.randint(1, 20) == 1:
                        self.generate_skinny_cave(
                            j * 1000 + random.randint(0, 1000), random.randint(int(y_top), int(y_top + (y_bottom - y_top) / 3)), random.randint(20, 60), random.random() * 2 * math.pi, layer_index=layer_index
                        )
                    if random.randint(1, 20) == 1:
                        self.generate_skinny_cave(
                            j * 1000 + random.randint(0, 1000), random.randint(int(y_top + (y_bottom - y_top) / 4), int(y_bottom)), random.randint(30, 90), random.random() * 2 * math.pi, layer_index=layer_index
                        )
                    if random.randint(1, 35) == 1:
                        self.generate_blob_cave(
                            j * 1000 + random.randint(0, 1000), random.randint(int(y_top + (y_bottom - y_top) / 4), int(y_bottom)), random.randint(30, 60), random.random() * 2 * math.pi, layer_index=layer_index
                        )
                    if random.randint(1, 20) == 1:
                        self.generate_blob_cave(
                            j * 1000 + random.randint(0, 1000), random.randint(int(y_top + (y_bottom - y_top) * 2 / 3), int(y_bottom)), random.randint(60, 120), random.random() * 2 * math.pi, layer_index=layer_index
                        )

                    if layer_index < 2:
                        if random.randint(1, 5) == 1:
                            self.generate_nest(j * 1000 + random.randint(0, 1000), random.randint(int(y_top + 500), int(y_bottom - 500)), "white", layer_index=layer_index)
                    else:
                        if random.randint(1, 15) == 1:
                            self.generate_nest(j * 1000 + random.randint(0, 1000), random.randint(int(y_top + 500), int(y_bottom - 500)), "white", layer_index=layer_index)

                    if layer_index == 2:
                        if random.randint(1, 6) == 1:
                            self.generate_nest(j * 1000 + random.randint(0, 1000), random.randint(int(y_top + 500), int(y_bottom - 500)), "blue", layer_index=layer_index)
                    elif layer_index > 2:
                        if random.randint(1, 12) == 1:
                            self.generate_nest(j * 1000 + random.randint(0, 1000), random.randint(int(y_top + 500), int(y_bottom - 500)), "blue", layer_index=layer_index)
                    if layer_index == 3:
                        if random.randint(1, 6) == 1:
                            self.generate_nest(j * 1000 + random.randint(0, 1000), random.randint(int(y_top + 500), int(y_bottom - 500)), "red", layer_index=layer_index)
                    elif layer_index > 3:
                        if random.randint(1, 12) == 1:
                            self.generate_nest(j * 1000 + random.randint(0, 1000), random.randint(int(y_top + 500), int(y_bottom - 500)), "red", layer_index=layer_index)

            self._build_chunk_hitboxes_for_layer(layer_index)
            self._build_chunk_visuals_for_layer(layer_index, loading_screen=loading_screen_visuals)
            self._generated_layers.add(layer_index)

            print(f"{time.strftime('%H:%M:%S')} - layer {layer_index} generation complete.")

            if loading_screen is not None:
                loading_screen.put(1, "Layer generation complete")

    # ------------------------------------------------------------------
    # Cave / nest generation helpers
    # ------------------------------------------------------------------

    def generate_nest(self, x, y, nest_type, layer_index, size=0):
        y_top, y_bottom = _layer_y_bounds(layer_index, self.world_height)
        y = max(y_top + max_airpocket_radius, min(y_bottom - max_airpocket_radius, y))
        if size == 0:
            size = random.randint(100, 100 + (y * 150) // self.world_height)
        new_nest = nest.Nest(self.default_zooms, self.world_height, layer_index, nest_type, x, y, size)
        rect = new_nest.get_rect()
        for cnest in self.nests[layer_index]:
            if rect.colliderect(cnest.get_rect()):
                return False
        self.nests[layer_index].append(new_nest)
        self.add_nest_to_hitbox_surfaces(new_nest)
        cave_size = (size * random.randint(0, 2) / 3 + 80) / 3
        if cave_size > 15:
            self.generate_skinny_cave(x, y - cave_size / 2, cave_size, -math.pi / 2, max_pockets=10, shrinking=True, layer_index=layer_index)
        else:
            self.add_air_pocket_clump(x, y - cave_size / 2, cave_size, layer_index=layer_index)
        return True

    def generate_blob_cave(self, start_x, start_y, start_r, start_dir=0, max_pockets=10, layer_index=0):
        y_top, y_bottom = _layer_y_bounds(layer_index, self.world_height)
        if max_pockets > 0 and (start_y - 2 * start_r) > y_top and start_y - start_r < y_bottom and start_r > 0:
            self.add_air_pocket_clump(start_x, start_y, start_r, layer_index=layer_index)
            for i in range(2):
                r = start_r + (random.random() - 0.6) * 20
                dir = start_dir + (random.random() - 0.5) * math.pi
                x = start_x + math.cos(dir) * min(r, start_r) * 0.8
                y = start_y + math.sin(dir) * min(r, start_r) * 0.8 * 0.2
                self.generate_blob_cave(x, y, r, dir, max_pockets - 1, layer_index=layer_index)
                if random.randint(1, 15) > 1:
                    break

    def generate_skinny_cave(self, start_x, start_y, start_r, start_dir=0, max_pockets=20, shrinking=False, layer_index=0):
        y_top, y_bottom = _layer_y_bounds(layer_index, self.world_height)
        if max_pockets > 0 and (start_y - 2 * start_r) > y_top and start_y - start_r < y_bottom and start_r > 0:
            self.add_air_pocket_clump(start_x, start_y, start_r, layer_index=layer_index)
            for i in range(2):
                r = start_r + (random.random() - 0.6) * 5
                if shrinking:
                    r = start_r - random.random() * 2
                dir = start_dir + (random.random() - 0.5) * math.pi / 2
                x = start_x + math.cos(dir) * min(r, start_r) * 0.8
                y = start_y + math.sin(dir) * min(r, start_r) * 0.8 * 0.8
                self.generate_skinny_cave(x, y, r, dir, max_pockets - 1, shrinking=shrinking, layer_index=layer_index)
                if random.randint(1, 30) > 1:
                    break

    def generate_descending_cave(self, start_x, start_y, start_r, start_dir=0, layer_index=0):
        y_top, y_bottom = _layer_y_bounds(layer_index, self.world_height)
        if start_y - start_r < y_bottom:
            bounded_x = abs(math.fmod(start_x, 2 * self.world_width) - self.world_width)
            self.add_air_pocket_clump(bounded_x, start_y, start_r, layer_index=layer_index)
            if start_y > y_top + 600 and start_y < y_bottom - 600 and random.randint(1, 100) == 1:
                # change white to selected randomly from list based on layerindex
                self.generate_nest(bounded_x, start_y + random.randint(-100, 100), "white", layer_index=layer_index)

            r = min(50, max(10, start_r + random.randint(-5, 5)))
            dir = start_dir + (random.random() - 0.5) * math.pi / 2
            x = start_x + int(math.cos(dir) * min(r, start_r) * 0.8)
            y = start_y + int(abs(math.sin(dir)) * min(r, start_r) * 0.5)
            self.generate_descending_cave(x, y, r, dir, layer_index=layer_index)

    def generate_bedrock_cave(self, start_x, start_y, start_r, start_dir=0, max_pockets=3, layer_index=0):
        y_top, y_bottom = _layer_y_bounds(layer_index, self.world_height)
        if max_pockets > 0 and (start_y - 2 * start_r) > y_top and start_y - start_r < y_bottom and start_r > 0:
            self.add_air_pocket_clump(start_x, start_y, start_r, layer_index=layer_index)
            for i in range(2):
                r = start_r + (random.random() - 0.6) * 20
                dir = start_dir + (random.random() - 0.5) * math.pi / 2
                x = start_x + math.cos(dir) * min(r, start_r) * 0.7
                y = start_y + math.sin(dir) * min(r, start_r) * 0.7 * 0.5
                self.generate_bedrock_cave(x, y, r, dir, max_pockets - 1, layer_index=layer_index)
                if random.randint(1, 30) > 1:
                    break

    def add_air_pocket_clump(self, x, y, radius, layer_index=0, player_made=False, spreading=1 / 3):
        spreading = radius * spreading
        for i in range(3):
            self.add_air_pocket(x + spreading * (random.random() * 2 - 1), y + spreading * (random.random() * 2 - 1), radius, layer_index=layer_index, player_made=player_made)

    def add_air_pocket(self, x, y, radius, layer_index=0, recursions=0, player_made=False):
        radius = min(radius, max_airpocket_radius)
        y_top, y_bottom = _layer_y_bounds(layer_index, self.world_height)
        if (not player_made and x - radius < 0) or (recursions > 3 or x + radius > self.world_width or x - radius < 0 or y < y_top or y > y_bottom):
            return False

        # ── Fast overlap check via spatial grid ────────────────────────────
        cx, cy = _grid_cell(x, y)
        if not player_made:
            for cell in _grid_neighbours(cx, cy):
                bucket = self._air_grid[layer_index].get(cell)
                if bucket is None:
                    continue
                for air_pocket in bucket:
                    dx = air_pocket.x - x
                    dy = air_pocket.y - y
                    # Quick AABB rejection before sqrt
                    combined = air_pocket.r + radius + 10
                    if abs(dx) > combined or abs(dy) > combined:
                        continue
                    d = math.sqrt(dx * dx + dy * dy)
                    if d < radius / 4:
                        return False
                    if air_pocket.r + radius < d < air_pocket.r + radius + 10:
                        return self.add_air_pocket((air_pocket.x + x) / 2, (air_pocket.y + y) / 2, (air_pocket.r + radius) / 2, layer_index=layer_index, recursions=recursions + 1)
        # ──────────────────────────────────────────────────────────────────

        if (not player_made) and random.randint(1, 10) == 1:
            new_air_pocket = AirPocket(x, y, radius, default_zooms=self.default_zooms, pocket_type="C1")
        else:
            new_air_pocket = AirPocket(x, y, radius, default_zooms=self.default_zooms)

        self.air_pockets[layer_index].append(new_air_pocket)

        # Register in spatial grid
        self._air_grid[layer_index].setdefault((cx, cy), []).append(new_air_pocket)

        self.add_air_pocket_to_surfaces(new_air_pocket)
        return True

    # ------------------------------------------------------------------
    # Vignette / carve
    # ------------------------------------------------------------------

    def draw_vignette(self, surface, window_size, offset_x=0, offset_y=0):
        w, h = window_size
        if self._vignette_surf is None or self._vignette_size != window_size:
            self._vignette_surf = pygame.transform.smoothscale(vignette_img, (w, h))
            self._vignette_size = window_size
        surface.blit(self._vignette_surf, (offset_x, offset_y), special_flags=pygame.BLEND_RGB_MULT)

    def _carve_visual_chunk(self, air_pocket, row, col, zoom):
        left, top = col * visual_chunk_size, row * visual_chunk_size
        chunk = self.chunk_visuals[zoom][row][col]
        if air_pocket.type == "Circle":
            pygame.draw.circle(chunk, (0, 0, 0, 0), (int(zoom * (air_pocket.x - left)), int(zoom * (air_pocket.y - top))), int(air_pocket.r * zoom))
        else:
            eraser = pygame.Surface(air_pocket.IMGs[zoom].get_size(), pygame.SRCALPHA)
            eraser.fill((0, 0, 0, 0))
            chunk.blit(eraser, (zoom * (air_pocket.left - left), zoom * (air_pocket.top - top)))

    # ------------------------------------------------------------------
    # Collision
    # ------------------------------------------------------------------

    def ray_cast_ground(self, start_x, start_y, angle, max_length):
        chunks = self.air_pockets_hitboxes_surfaces[1]
        chunk_rows = len(chunks)
        chunk_cols = len(chunks[0]) if chunk_rows > 0 else 0
        dx = math.cos(angle)
        dy = math.sin(angle)
        step = 2
        dist = 0
        while dist < max_length:
            wx = start_x + dx * dist
            wy = start_y + dy * dist
            if wx < 0 or wx >= self.world_width or wy < 0 or wy >= self.world_height:
                return wx, wy, dist
            col = int(wx // hitbox_chunk_size)
            row = int(wy // hitbox_chunk_size)
            if row >= chunk_rows or col >= chunk_cols:
                return wx, wy, dist
            pixel = chunks[row][col].get_at((int(wx % hitbox_chunk_size), int(wy % hitbox_chunk_size)))
            if pixel[0] < 128:
                return wx, wy, dist
            dist += step
        return None, None, max_length

    def _get_scratch(self, w, h):
        w, h = int(math.ceil(w)), int(math.ceil(h))
        if w > self._collide_scratch.get_width() or h > self._collide_scratch.get_height():
            new_w = max(w, self._collide_scratch.get_width())
            new_h = max(h, self._collide_scratch.get_height())
            self._collide_scratch = pygame.Surface((new_w, new_h), pygame.SRCALPHA)
        self._collide_scratch.fill((0, 0, 0, 0), pygame.Rect(0, 0, w, h))
        return self._collide_scratch

    def _sample_chunk(self, wx, wy):
        if wy < 0:
            return False
        if wx < 0 or wx >= self.world_width or wy >= self.world_height:
            return True
        chunks = self.chunk_hitboxes[1]
        col = int(wx // hitbox_chunk_size)
        row = int(wy // hitbox_chunk_size)
        if row >= len(chunks) or col >= len(chunks[0]):
            return True
        px = max(0, min(int(hitbox_chunk_size - 1), int(wx % hitbox_chunk_size)))
        py = max(0, min(int(hitbox_chunk_size - 1), int(wy % hitbox_chunk_size)))
        return chunks[row][col].get_at((px, py))[0] > 128

    def _sample_chunk_visuals(self, wx, wy):
        if wy < 0:
            return False
        if wx < 0 or wx >= self.world_width or wy >= self.world_height:
            return True
        chunks = self.chunk_visuals[1]
        col = int(wx // visual_chunk_size)
        row = int(wy // visual_chunk_size)
        if row >= len(chunks) or col >= len(chunks[0]):
            return True
        px = max(0, min(int(visual_chunk_size - 1), int(wx % visual_chunk_size)))
        py = max(0, min(int(visual_chunk_size - 1), int(wy % visual_chunk_size)))
        return chunks[row][col].get_at((px, py))[3] > 128

    def _sample_rect(self, rect):
        l = float(rect.left)
        r = float(rect.right - 1)
        t = float(rect.top)
        b = float(rect.bottom - 1)
        # step = (b - t) / 9
        step = 1
        for i in range(math.floor(b - t)):
            y = t + step * i
            if self._sample_chunk(l, y) or self._sample_chunk(r, y):
                return True
        for i in range(math.floor(r - l)):
            x = l + step * i
            if self._sample_chunk(x, b) or self._sample_chunk(x, t):
                return True
        return False

    def collide_rect(self, rect):
        return self._sample_rect(rect)

    def laser_collide_point(self, x, y):
        # the two below are somewhat redundant
        # samplechunkvisuals ensures all bits of visual terrain interact with laser, and samplechunk takes care of nests.
        # in the future would have this function identify the laser target, because that is currently also done in a separate redundant function
        if self._sample_chunk_visuals(x, y):
            return True
        if self._sample_chunk(x, y):
            return True
        for n in self._active_nests():
            for enemy in n.enemies:
                if enemy.mode != "Spawn" and enemy.rect.collidepoint(x, y):
                    return True
        return False

    def ground_collide_rect(self, rect):
        return self._sample_rect(rect)

    def enemies_collide_rect(self, rect):
        rect_mask = pygame.Mask((rect.width, rect.height), fill=True)
        colliding_layer = pygame.Surface((rect.width, rect.height), flags=pygame.SRCALPHA)
        self.draw_enemies((rect.width, rect.height), colliding_layer, [rect.left, rect.top, 1], hitboxes=True)
        return pygame.mask.from_surface(colliding_layer).overlap(rect_mask, (0, 0)) is not None

    def enemies_attack_collide_rect(self, rect):
        rect_mask = pygame.Mask((rect.width, rect.height), fill=True)
        colliding_layer = pygame.Surface((rect.width, rect.height), flags=pygame.SRCALPHA)
        self.draw_enemies((rect.width, rect.height), colliding_layer, [rect.left, rect.top, 1], hitboxes=True)
        return pygame.mask.from_surface(colliding_layer).overlap(rect_mask, (0, 0)) is not None

    def nests_collide_rect(self, rect):
        rect_mask = pygame.Mask((rect.width, rect.height), fill=True)
        colliding_layer = pygame.Surface((rect.width, rect.height), flags=pygame.SRCALPHA)
        self.draw_nests((rect.width, rect.height), colliding_layer, [rect.left, rect.top, 1], hitboxes=True)
        return pygame.mask.from_surface(colliding_layer).overlap(rect_mask, (0, 0)) is not None

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    def draw_depth_background(self, surface, frame, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w, h = surface.get_size()
        right = left + w / zoom
        bottom = top + h / zoom
        tl = self._depth_color(left, top)
        tr = self._depth_color(right, top)
        bl = self._depth_color(left, bottom)
        br = self._depth_color(right, bottom)

        def darken(c):
            return (int(c[0] * 0.05), int(c[1] * 0.05), int(c[2] * 0.05))

        surface.blit(self._make_gradient_surf(darken(tl), darken(tr), darken(bl), darken(br), w, h), (offset_x, offset_y))

    def draw_collision_debug(self, surface, rect, frame, color=(255, 0, 0), offset_x=0, offset_y=0):
        left, top, zoom = frame
        l = float(rect.left)
        r = float(rect.right - 1)
        t = float(rect.top)
        b = float(rect.bottom - 1)
        step = (b - t) / 9
        for i in range(10):
            y = t + step * i
            for wx, wy in [(l, y), (r, y)]:
                pygame.draw.circle(surface, color, (int((wx - left) * zoom + offset_x), int((wy - top) * zoom + offset_y)), max(2, int(zoom * 2)))

    def draw_nest_gradients(self, window_size, surface, frame, hitboxes=False, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w_width, w_height = window_size
        r = math.sqrt(w_width**2 + w_height**2) / 2 / zoom
        x, y = left + w_width / zoom / 2, top + w_height / zoom / 2
        for n in self._active_nests():
            if n.close(x, y, r):
                n.draw_gradient(surface, frame, offset_x=offset_x, offset_y=offset_y)
            for enemy in n.enemies:
                dx = x - enemy.x
                dy = y - enemy.y
                if dx * dx + dy * dy < (r + enemy.r) ** 2:
                    enemy.draw_gradient(surface, frame, offset_x=offset_x, offset_y=offset_y)

    def draw_nests(self, window_size, surface, frame, hitboxes=False, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w_width, w_height = window_size
        r = math.sqrt(w_width**2 + w_height**2) / 2 / zoom
        x, y = left + w_width / zoom / 2, top + w_height / zoom / 2
        for n in self._active_nests():
            if n.close(x, y, r):
                n.draw(surface, frame, hitbox=hitboxes, offset_x=offset_x, offset_y=offset_y)

    def draw_health_bars(self, window_size, surface, frame, time=None, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w_width, w_height = window_size
        r = math.sqrt(w_width**2 + w_height**2) / 2 / zoom
        x, y = left + w_width / zoom / 2, top + w_height / zoom / 2
        for n in self._active_nests():
            for enemy in n.enemies:
                enemy.draw_health_bar(surface, frame, time, offset_x=offset_x, offset_y=offset_y)
            if n.close(x, y, r):
                n.draw_health_bar(surface, frame, time, offset_x=offset_x, offset_y=offset_y)
        for gw in self.gateways:
            for entry in gw.entry_tiles:
                entry.draw_health_bar(surface, frame, time, offset_x=offset_x, offset_y=offset_y)

    def draw_enemies(self, window_size, surface, frame, hitboxes=False, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w_width, w_height = window_size
        r = math.sqrt(w_width**2 + w_height**2) / 2 / zoom
        x, y = left + w_width / zoom / 2, top + w_height / zoom / 2
        for n in self._active_nests():
            for i in range(len(n.enemies) - 1, -1, -1):
                enemy = n.enemies[i]
                dx = x - enemy.x
                dy = y - enemy.y
                if dx * dx + dy * dy < (r + enemy.r) ** 2:
                    enemy.draw(surface, frame, hitbox=hitboxes, offset_x=offset_x, offset_y=offset_y)

    def draw_terrain(self, window_size, surface, frame, hitboxes=False, real_window_size=None, offset_x=0, offset_y=0):
        if real_window_size is None:
            real_window_size = window_size
        left, top, zoom = frame
        w_width, w_height = window_size
        if zoom not in self.default_zooms:
            return
        if hitboxes:
            surface.blit(self.get_terrain_layer(window_size, frame, hitboxes=True, real_window_size=real_window_size, offset_x=offset_x, offset_y=offset_y), (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
        else:
            top_chunk = math.floor(max(0, min(self.world_height, top)) / visual_chunk_size)
            left_chunk = math.floor(max(0, min(self.world_width - visual_chunk_size, left)) / visual_chunk_size)
            bottom_chunk = math.ceil(max(0, min(self.world_height, top + w_height / zoom - visual_chunk_size)) / visual_chunk_size)
            right_chunk = math.ceil(max(0, min(self.world_width - visual_chunk_size, left + w_width / zoom - visual_chunk_size)) / visual_chunk_size)

            if self._vignette_stencil is None or self._vignette_stencil_size != real_window_size:
                self._vignette_stencil = pygame.Surface(real_window_size, pygame.SRCALPHA)
                self._vignette_stencil_size = real_window_size
            self._vignette_stencil.fill((0, 0, 0, 0))

            chunks = self.chunk_visuals[zoom]
            for row in range(top_chunk, bottom_chunk + 1):
                for col in range(left_chunk, right_chunk + 1):
                    if row < len(chunks) and col < len(chunks[row]):
                        self._vignette_stencil.blit(chunks[row][col], ((col * visual_chunk_size - left) * zoom + offset_x, (row * visual_chunk_size - top) * zoom + offset_y))

            self.draw_vignette(self._vignette_stencil, window_size, offset_x=offset_x, offset_y=offset_y)
            surface.blit(self._vignette_stencil, (0, 0))

    def get_terrain_layer(self, window_size, frame, hitboxes=False, real_window_size=None, offset_x=0, offset_y=0):
        if real_window_size is None:
            real_window_size = window_size
        left, top, zoom = frame
        w_width, w_height = window_size
        layer = self._get_terrain_layer_surface(real_window_size)
        if zoom in self.default_zooms:
            if hitboxes:
                top_chunk = math.floor(max(0, min(self.world_height, top)) / hitbox_chunk_size)
                left_chunk = math.floor(max(0, min(self.world_width - hitbox_chunk_size, left)) / hitbox_chunk_size)
                bottom_chunk = math.ceil(max(0, min(self.world_height, top + w_height / zoom - hitbox_chunk_size)) / hitbox_chunk_size)
                right_chunk = math.ceil(max(0, min(self.world_width - hitbox_chunk_size, left + w_width / zoom - hitbox_chunk_size)) / hitbox_chunk_size)
                layer.fill((0, 0, 0, 0))
                surfaces = self.chunk_hitboxes[zoom]
                for row in range(top_chunk, bottom_chunk + 1):
                    for column in range(left_chunk, right_chunk + 1):
                        layer.blit(surfaces[row][column], ((column * hitbox_chunk_size - left) * zoom + offset_x, (row * hitbox_chunk_size - top) * zoom + offset_y))
            else:
                top_chunk = math.floor(max(0, min(self.world_height, top)) / 500)
                left_chunk = math.floor(max(0, min(self.world_width - 500, left)) / 500)
                bottom_chunk = math.ceil(max(0, min(self.world_height, top + w_height / zoom - 500)) / 500)
                right_chunk = math.ceil(max(0, min(self.world_width - 500, left + w_width / zoom - 500)) / 500)
                surfaces = self.air_pockets_surfaces[zoom]
                for row in range(top_chunk, bottom_chunk + 1):
                    for column in range(left_chunk, right_chunk + 1):
                        layer.blit(surfaces[row][column], ((column * 500 - left) * zoom + offset_x, (row * 500 - top) * zoom + offset_y), special_flags=pygame.BLEND_RGBA_SUB)
                air_surface = pygame.Surface((w_width, w_height), pygame.SRCALPHA)
                layer.blit(air_surface, (offset_x, offset_y), special_flags=pygame.BLEND_RGBA_SUB)
        return layer


# ------------------------------------------------------------------
# AirPocket
# ------------------------------------------------------------------


class AirPocket:
    def __init__(self, x, y, radius, default_zooms=[0.1, 2], pocket_type="Circle"):
        radius = _snap_radius(radius)

        self.x = x
        self.y = y
        self.r = radius
        self.type = pocket_type
        self.top = self.y - self.r
        self.left = self.x - self.r

        imgs = air_im_gs[pocket_type]
        img_index = random.randint(0, len(imgs) - 1)

        self.full_res_img = imgs[img_index]

        self.IMGs = {}
        self.hitbox_im_gs = {}
        self.rim_im_gs = {}

        for zoom in default_zooms:
            self.IMGs[zoom] = _get_cached_scale(self.full_res_img, pocket_type, img_index, radius, zoom)

        if self.type != "Circle":
            self.full_res_hitbox_img = air_hitbox_im_gs[pocket_type]
            for zoom in default_zooms:
                self.hitbox_im_gs[zoom] = _get_cached_scale(self.full_res_hitbox_img, pocket_type + "_hitbox", 0, radius, zoom)

        for zoom in default_zooms:
            self.rim_im_gs[zoom] = _get_cached_rim_scale(self.full_res_img, pocket_type, img_index, radius, zoom)

    def close(self, x, y, radius):
        # return abs(self.x - x) < radius + self.r and abs(self.y - y) < radius + self.r
        return math.dist((self.x, self.y), (x, y)) < radius + self.r
