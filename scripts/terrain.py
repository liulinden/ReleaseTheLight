import math
import queue
import random
import threading
import time

import pygame

import scripts.nest as nest
import scripts.particles as particles
from config import CHUNK_SIZE
from scripts.cells import Cell
from scripts.global_assets import get_asset
from scripts.loading_screen import LoadingScreen
from scripts.UI import InteractionDisplayManager

# ------------------------------------------------------------------
# Architecture overview
# ------------------------------------------------------------------
# Terrain is split into a TRUTH layer and a SURFACE (cache) layer.
#
#   Chunk.air_pockets / Chunk.nests / Chunk.cells / Chunk.structures
#       -> truth data. Cheap plain-data objects, no pygame Surfaces.
#          Generated once for the whole world at startup (generate_world),
#          and added to incrementally afterwards (player mining).
#
#   Chunk.visuals[zoom] / Chunk.hitboxes[zoom]
#       -> derived pygame Surfaces, built lazily from truth data the first
#          time a chunk is needed (see _build_chunk). These are the
#          expensive, blit-heavy artifacts, and are safe to throw away
#          and rebuild at any time (evict_far_chunks), since they're a
#          pure function of the chunk's truth data.
#
# Biomes: each Chunk has a `biome` string (currently always "default",
# see get_biome). BIOME_RULES holds per-biome tunables (fill_mode, nest
# frequency/type thresholds by depth). Not wired up to per-chunk cave
# generation yet (cave carving is a continuous, multi-chunk-spanning
# process at world-gen time, not chunk-scoped) -- that's future work.
# ------------------------------------------------------------------

max_airpocket_radius = 120
rim_pocket_ratio = 1.5
rocks_world_span = 8 * CHUNK_SIZE

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

# ------------------------------------------------------------------
# Biome stub -- everything currently resolves to "default". Swap
# get_biome for a noise-based lookup later; add more entries to
# BIOME_RULES as new biomes are introduced.
# ------------------------------------------------------------------

BIOME_RULES = {
    "default": {
        # "solid": chunk starts as solid rock, air pockets are carved (subtracted) out.
        # "air": reserved for future biomes that start hollow and add solid
        #        features instead. Not implemented -- see _render_base_terrain.
        "fill_mode": "solid",
        "nest_rules": {
            "white": {"min_frac": 0.0, "switch_frac": 0.2, "early_denom": 5, "late_denom": 15},
            "blue": {"min_frac": 0.2, "switch_frac": 0.3, "early_denom": 6, "late_denom": 12},
            "red": {"min_frac": 0.3, "switch_frac": 0.4, "early_denom": 6, "late_denom": 12},
        },
    },
}


def get_biome(row, col):
    """Returns the biome name for a chunk coordinate. Stubbed to always
    return "default" for now; replace with noise-based assignment later."""
    return "default"


# load images -- call terrain.init() after pygame.display.set_mode()
air_im_gs = {}
circle_im_gs = []
air_rim_im_gs = {}
air_explode_im_gs = {}
air_hitbox_im_gs = {}
rocks_img = {}
vignette_img = None


def init():
    global air_im_gs, circle_im_gs, air_hitbox_im_gs, rocks_img, vignette_img
    circle_im_gs = []
    circle_rim_im_gs = []
    circle_explode_im_gs = []
    for i in range(2):
        circle_im_gs.append(get_asset("AirPocket" + str(i + 1)))
    for i in range(1):
        circle_rim_im_gs.append(get_asset("AirPocket" + str(i + 1) + "_rim"))
    for i in range(1):
        circle_explode_im_gs.append(get_asset("AirPocket" + str(i + 1) + "_explode"))
    air_im_gs["Circle"] = circle_im_gs
    air_rim_im_gs["Circle"] = circle_rim_im_gs
    air_explode_im_gs["Circle"] = circle_explode_im_gs
    air_hitbox_im_gs["Circle"] = get_asset("AirPocketHitbox")

    rocks_raw = get_asset("Rocks")
    rocks_img["raw"] = rocks_raw
    vignette_img = get_asset("VignetteGradient")


def rect_to_circle(left, top, width, height):
    return left + width / 2, top + height / 2, math.dist((0, 0), (width, height)) / 2


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


# ------------------------------------------------------------------
# Chunk -- one bucket of truth data plus (lazily) its derived surfaces
# ------------------------------------------------------------------


class Chunk:
    __slots__ = (
        "row", "col", "biome",
        "air_pockets", "nests", "cells", "structures",
        "visuals", "hitboxes",
        "built", "last_touched", "lock",
    )

    def __init__(self, row, col, biome="default"):
        self.row = row
        self.col = col
        self.biome = biome
        self.air_pockets = []
        self.nests = []
        self.cells = []
        self.structures = []  # future: generic solid structures (was gateway tiles)
        self.visuals = {}     # dict[zoom] -> Surface, populated once built
        self.hitboxes = {}    # dict[zoom] -> Surface, populated once built
        self.built = False
        self.last_touched = 0.0
        # Reentrant: _build_chunk can call helpers that also lock this chunk.
        self.lock = threading.RLock()


# ------------------------------------------------------------------
# AirPocket -- pure truth data. No Surfaces are created until a chunk
# using this pocket is actually built (get_img / get_hitbox_img /
# get_rim_img resolve + cache the scaled image on first use).
# ------------------------------------------------------------------


class AirPocket:
    __slots__ = ("x", "y", "r", "true_r", "top", "left", "type", "player_made", "img_index", "rim_img_index")

    def __init__(self, x, y, radius, pocket_type="Circle", player_made=False):
        radius = _snap_radius(radius)
        self.x = x
        self.y = y
        self.r = radius
        self.true_r = radius * rim_pocket_ratio
        self.top = y - self.true_r
        self.left = x - self.true_r
        self.type = pocket_type
        self.player_made = player_made

        imgs = air_im_gs[pocket_type]
        self.img_index = random.randint(0, len(imgs) - 1)
        rim_imgs = air_explode_im_gs[pocket_type] if player_made else air_rim_im_gs[pocket_type]
        self.rim_img_index = random.randint(0, len(rim_imgs) - 1)

    def get_img(self, zoom):
        imgs = air_im_gs[self.type]
        return _get_cached_scale(imgs[self.img_index], self.type, self.img_index, self.true_r, zoom)

    def get_hitbox_img(self, zoom):
        return _get_cached_scale(air_hitbox_im_gs[self.type], self.type + "_hitbox", 0, self.true_r, zoom)

    def get_rim_img(self, zoom):
        rim_imgs = air_explode_im_gs[self.type] if self.player_made else air_rim_im_gs[self.type]
        return _get_cached_scale(
            rim_imgs[self.rim_img_index], self.type + "rim_playermade:" + str(self.player_made), self.rim_img_index, self.true_r, zoom
        )

    def close(self, x, y, radius):
        return math.dist((self.x, self.y), (x, y)) < radius + self.r


# ------------------------------------------------------------------
# Terrain
# ------------------------------------------------------------------


class Terrain:
    def __init__(self, world_width: int, world_height: int, default_zooms: list = (0.1, 2)):

        self.knockback_circles = []
        self.new_knockback_circles = []
        self.player_damage_circles = []
        self.new_player_damage_circles = []

        self.display_manager = InteractionDisplayManager()

        # world_width is the GENERATION SPAN width (caves/nests/cells only
        # spawn within [0, world_width] at world-gen time). The world
        # itself extends infinitely in both x directions -- the player can
        # mine out past the span freely; those chunks just start as plain
        # rock with no truth-level air pockets/nests until carved.
        self.world_width = world_width
        self.world_height = world_height
        self.default_zooms = default_zooms
        self.particles = particles.Particles()

        self.chunks: dict[tuple, Chunk] = {}

        self._rocks_scaled = {}
        for zoom in default_zooms:
            scaled_span = int(rocks_world_span * zoom)
            self._rocks_scaled[zoom] = pygame.transform.scale(rocks_img["raw"], (scaled_span, scaled_span))

        self._terrain_layer = None
        self._terrain_layer_size = None
        self._scratch_surfaces = {}
        self._placeholder_surfaces = {}
        self._vignette_surf = None
        self._vignette_size = None
        self._vignette_stencil = None
        self._vignette_stencil_size = None

        # streaming
        self._stream_queue = queue.PriorityQueue()
        self._stream_queued_keys = set()
        self._stream_lock = threading.Lock()
        self._stream_thread = None
        self._stream_seq = 0  # tie-breaker so PriorityQueue never compares Chunks/tuples of equal priority incorrectly

    # ------------------------------------------------------------------
    # Chunk lookup / creation
    # ------------------------------------------------------------------

    def get_or_create_chunk(self, row, col):
        key = (row, col)
        chunk = self.chunks.get(key)
        if chunk is None:
            chunk = Chunk(row, col, biome=get_biome(row, col))
            self.chunks[key] = chunk
        return chunk

    def _chunks_in_rect(self, left, top, width, height, pad=1):
        col_start = math.floor(left / CHUNK_SIZE) - pad
        col_end = math.ceil((left + width) / CHUNK_SIZE) + pad
        row_start = max(0, math.floor(top / CHUNK_SIZE) - pad)
        row_end = math.ceil((top + height) / CHUNK_SIZE) + pad
        for row in range(row_start, row_end + 1):
            for col in range(col_start, col_end + 1):
                yield row, col

    def _chunks_near(self, x, y, radius, pad=1):
        row_c = int(math.floor(y / CHUNK_SIZE))
        col_c = int(math.floor(x / CHUNK_SIZE))
        chunk_radius = int(math.ceil(radius / CHUNK_SIZE)) + pad
        for dr in range(-chunk_radius, chunk_radius + 1):
            for dc in range(-chunk_radius, chunk_radius + 1):
                chunk = self.chunks.get((row_c + dr, col_c + dc))
                if chunk is not None:
                    yield chunk

    def _nests_near(self, x, y, radius):
        seen = set()
        result = []
        for chunk in self._chunks_near(x, y, radius):
            for n in chunk.nests:
                if id(n) not in seen:
                    seen.add(id(n))
                    result.append(n)
        return result

    def _cells_near(self, x, y, radius):
        seen = set()
        result = []
        for chunk in self._chunks_near(x, y, radius):
            for c in chunk.cells:
                if id(c) not in seen:
                    seen.add(id(c))
                    result.append(c)
        return result

    def _nests_touching_rect(self, rect):
        seen = set()
        result = []
        for row, col in self._chunks_in_rect(rect.left, rect.top, rect.width, rect.height, pad=1):
            chunk = self.chunks.get((row, col))
            if chunk is None:
                continue
            for n in chunk.nests:
                if id(n) not in seen:
                    seen.add(id(n))
                    result.append(n)
        return result

    # ------------------------------------------------------------------
    # Structure baking (generic; nothing calls this yet since gateways
    # were removed, but kept for future structure types)
    # ------------------------------------------------------------------

    def reblit_structure_on_chunks(self, structure, erase=True):
        for row, col in self._chunks_in_rect(structure.left, structure.top, structure.width, structure.height, pad=1):
            chunk = self.get_or_create_chunk(row, col)
            if structure not in chunk.structures:
                chunk.structures.append(structure)
            if chunk.built:
                self._bake_structure_into_chunk(chunk, structure, erase)

    def _bake_structure_into_chunk(self, chunk, structure, erase=True):
        left, top = chunk.col * CHUNK_SIZE, chunk.row * CHUNK_SIZE
        with chunk.lock:
            for zoom in self.default_zooms:
                if zoom not in chunk.hitboxes:
                    continue
                erase_hitbox_surf = structure.get_erase_hitbox_surface(zoom)
                hitbox_surf = structure.get_hitbox_surface(zoom)
                if hitbox_surf is not None:
                    if erase and erase_hitbox_surf:
                        chunk.hitboxes[zoom].blit(
                            erase_hitbox_surf, (zoom * (structure.left - left), zoom * (structure.top - top)), special_flags=pygame.BLEND_RGBA_SUB
                        )
                    chunk.hitboxes[zoom].blit(
                        hitbox_surf, (zoom * (structure.left - left), zoom * (structure.top - top)), special_flags=pygame.BLEND_RGBA_MAX
                    )
                if zoom in chunk.visuals:
                    erase_surf = structure.get_erase_surface(zoom)
                    if erase_surf is not None:
                        chunk.visuals[zoom].blit(erase_surf, (zoom * (structure.left - left), zoom * (structure.top - top)), special_flags=pygame.BLEND_RGBA_SUB)

    def _reblit_solid_structures_on_chunk(self, chunk):
        """Re-apply nests + structures on top of a chunk's hitbox surfaces
        after carving, since the carve SUB blend can erode overlapping
        solid features drawn earlier."""
        left, top = chunk.col * CHUNK_SIZE, chunk.row * CHUNK_SIZE
        for n in chunk.nests:
            for zoom in self.default_zooms:
                if zoom in chunk.hitboxes:
                    chunk.hitboxes[zoom].blit(n.resized_hitboxes[zoom], (zoom * (n.left - left), zoom * (n.top - top)), special_flags=pygame.BLEND_RGBA_MAX)
        for structure in chunk.structures:
            for zoom in self.default_zooms:
                if zoom in chunk.hitboxes:
                    hitbox_surf = structure.get_hitbox_surface(zoom)
                    if hitbox_surf:
                        chunk.hitboxes[zoom].blit(
                            hitbox_surf, (zoom * (structure.left - left), zoom * (structure.top - top)), special_flags=pygame.BLEND_RGBA_MAX
                        )

    # ------------------------------------------------------------------
    # Surface helpers
    # ------------------------------------------------------------------

    def _get_terrain_layer_surface(self, real_window_size):
        if self._terrain_layer is None or self._terrain_layer_size != real_window_size:
            self._terrain_layer = pygame.Surface(real_window_size, pygame.SRCALPHA)
            self._terrain_layer_size = real_window_size
        self._terrain_layer.fill((255, 255, 255, 255))
        return self._terrain_layer

    def _get_scratch_surface(self, w, h):
        """Cached scratch surface. Only safe to use from the single chunk-
        building context (background streaming worker, or pre-worker-start
        synchronous setup) -- never from incremental player-carve code,
        which may run concurrently with the worker."""
        w, h = int(math.ceil(w)), int(math.ceil(h))
        if (w, h) not in self._scratch_surfaces:
            self._scratch_surfaces[(w, h)] = pygame.Surface((w, h), pygame.SRCALPHA)
        return self._scratch_surfaces[(w, h)]

    def _get_unbuilt_placeholder(self, zoom):
        if zoom not in self._placeholder_surfaces:
            chunk_px = max(1, int(CHUNK_SIZE * zoom))
            surf = pygame.Surface((chunk_px, chunk_px))
            surf.fill((255, 0, 0))
            self._placeholder_surfaces[zoom] = surf
        return self._placeholder_surfaces[zoom]

    # ------------------------------------------------------------------
    # Noise / colour -- continuous with world_y, no layers
    # ------------------------------------------------------------------

    def _noise_val(self, x, y, scale=1.0):
        x, y = x * scale, y * scale
        v = math.sin(x * 0.017 + y * 0.011) * 0.4
        v += math.cos(x * 0.031 - y * 0.023) * 0.3
        v += math.sin(x * 0.053 + y * 0.047 + 1.3) * 0.2
        v += math.cos(x * 0.079 - y * 0.061 + 2.7) * 0.1
        return max(-1.0, min(1.0, v))

    def _depth_fraction(self, y):
        return max(0.0, min(1.0, y / self.world_height))

    def _depth_color(self, world_x, world_y):
        # PALETTES is treated as a sequence of equal-height bands spanning
        # the full world height (this replaces the old gateway-defined
        # layer bounds). Easy to swap for non-uniform bands later.
        depth_frac = self._depth_fraction(world_y)
        band_count = len(PALETTES)
        band_f = depth_frac * band_count
        band = min(band_count - 1, int(band_f))
        local_d = band_f - band

        noise = self._noise_val(world_x, world_y) * 0.3
        d = max(0.0, min(1.0, local_d + noise))

        palette = PALETTES[band]
        for i in range(len(palette) - 1):
            d0, c0 = palette[i]
            d1, c1 = palette[i + 1]
            if d <= d1:
                t = (d - d0) / (d1 - d0) if d1 != d0 else 0.0
                r = int(c0[0] + (c1[0] - c0[0]) * t)
                g = int(c0[1] + (c1[1] - c0[1]) * t)
                b = int(c0[2] + (c1[2] - c0[2]) * t)
                return (r, g, b)
        return palette[-1][1]

    def _make_gradient_surf(self, tl, tr, bl, br, width, height):
        surf = self._get_scratch_surface(2, 2)
        surf.set_at((0, 0), tl)
        surf.set_at((1, 0), tr)
        surf.set_at((0, 1), bl)
        surf.set_at((1, 1), br)
        return pygame.transform.smoothscale(surf, (width, height), self._get_scratch_surface(width, height))

    # ------------------------------------------------------------------
    # Lazy chunk building (surfaces derived from truth data)
    # ------------------------------------------------------------------

    def _render_base_terrain(self, row, col, zoom):
        rocks = self._rocks_scaled[zoom]
        rocks_span_px = int(rocks_world_span * zoom)
        chunk_px = max(1, int(CHUNK_SIZE * zoom))

        world_left = col * CHUNK_SIZE
        world_top = row * CHUNK_SIZE
        world_right = world_left + CHUNK_SIZE
        world_bot = world_top + CHUNK_SIZE

        tl = self._depth_color(world_left, world_top)
        tr = self._depth_color(world_right, world_top)
        bl = self._depth_color(world_left, world_bot)
        br = self._depth_color(world_right, world_bot)

        surf = pygame.Surface((chunk_px, chunk_px), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 255))
        surf.blit(self._make_gradient_surf(tl, tr, bl, br, chunk_px, chunk_px), (0, 0), special_flags=pygame.BLEND_RGB_MAX)

        rock_x = int((world_left * zoom) % rocks_span_px)
        rock_y = int((world_top * zoom) % rocks_span_px)
        rock_surf = pygame.Surface((chunk_px, chunk_px))
        for ty in range(-rock_y, chunk_px, rocks_span_px):
            for tx in range(-rock_x, chunk_px, rocks_span_px):
                rock_surf.blit(rocks, (tx, ty))
        surf.blit(rock_surf, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        return surf

    def _build_chunk(self, chunk):
        """Build all zooms for a chunk together. Only ever called from the
        single streaming worker thread (or synchronously before that
        thread starts) -- never from the main thread, to keep the cached
        scratch-surface path in _make_gradient_surf single-threaded-safe."""
        with chunk.lock:
            if chunk.built:
                return
            rules = BIOME_RULES.get(chunk.biome, BIOME_RULES["default"])
            fill_mode = rules.get("fill_mode", "solid")
            # "air" fill_mode reserved for future biomes that start hollow
            # and add solid features instead of carving them out. Not
            # implemented -- falls back to "solid" behavior for now.

            for zoom in self.default_zooms:
                chunk.visuals[zoom] = self._render_base_terrain(chunk.row, chunk.col, zoom)
                hitbox = pygame.Surface((max(1, int(CHUNK_SIZE * zoom)), max(1, int(CHUNK_SIZE * zoom))), pygame.SRCALPHA)
                hitbox.fill((255, 255, 255, 255))
                chunk.hitboxes[zoom] = hitbox

            for pocket in chunk.air_pockets:
                for zoom in self.default_zooms:
                    self._carve_hitbox(chunk, pocket, zoom)
                    self._carve_visual(chunk, pocket, zoom)

            self._reblit_solid_structures_on_chunk(chunk)

            chunk.built = True

    def build_chunk_now(self, row, col):
        chunk = self.get_or_create_chunk(row, col)
        if not chunk.built:
            self._build_chunk(chunk)
        return chunk

    def get_chunk_if_built(self, row, col):
        chunk = self.chunks.get((row, col))
        if chunk is not None and chunk.built:
            return chunk
        return None

    # ------------------------------------------------------------------
    # Carving (used both by lazy build, and incremental player-mining)
    # ------------------------------------------------------------------

    def _carve_hitbox(self, chunk, air_pocket, zoom):
        left, top = chunk.col * CHUNK_SIZE, chunk.row * CHUNK_SIZE
        l = zoom * (air_pocket.left - left)
        t = zoom * (air_pocket.top - top)
        chunk.hitboxes[zoom].blit(air_pocket.get_hitbox_img(zoom), (l, t), special_flags=pygame.BLEND_RGBA_SUB)

    def _carve_visual(self, chunk, air_pocket, zoom):
        left, top = chunk.col * CHUNK_SIZE, chunk.row * CHUNK_SIZE
        l = zoom * (air_pocket.left - left)
        t = zoom * (air_pocket.top - top)
        surf = chunk.visuals[zoom]

        eraser = air_pocket.get_img(zoom)
        surf.blit(eraser, (l, t), special_flags=pygame.BLEND_RGBA_SUB)

        r, g, b = self._depth_color(air_pocket.x, air_pocket.y)
        rim = air_pocket.get_rim_img(zoom)

        # Fresh (uncached) scratch surface here -- this path can run from
        # the main thread concurrently with the background build worker,
        # so it must not share _get_scratch_surface's cache.
        mask = pygame.Surface((rim.get_width(), rim.get_height()), pygame.SRCALPHA)
        mask.fill((r, g, b, 0))
        mask.blit(surf, (-l, -t), special_flags=pygame.BLEND_RGBA_MAX)
        mask.blit(rim, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surf.blit(mask, (l, t))

    def _carve_chunk_incremental(self, chunk, air_pocket):
        """Patch a single already-built chunk with one new air pocket,
        without a full rebuild."""
        with chunk.lock:
            for zoom in self.default_zooms:
                if zoom not in chunk.hitboxes:
                    continue
                self._carve_hitbox(chunk, air_pocket, zoom)
                self._carve_visual(chunk, air_pocket, zoom)
            self._reblit_solid_structures_on_chunk(chunk)

    # ------------------------------------------------------------------
    # Streaming: background worker builds chunks near the player ahead
    # of time; evict_far_chunks drops surfaces (not truth data) far away.
    # ------------------------------------------------------------------

    def start_streaming(self):
        if self._stream_thread is not None:
            return
        self._stream_thread = threading.Thread(target=self._stream_worker_loop, daemon=True)
        self._stream_thread.start()

    def _stream_worker_loop(self):
        while True:
            try:
                _, _, key = self._stream_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            with self._stream_lock:
                self._stream_queued_keys.discard(key)
            row, col = key
            chunk = self.get_or_create_chunk(row, col)
            if not chunk.built:
                self._build_chunk(chunk)

    def update_streaming(self, player_x, player_y, build_radius_chunks=6):
        """Call once per tick (or every few ticks). Enqueues chunks around
        the player for the background worker to build, nearest first."""
        pr = int(math.floor(player_y / CHUNK_SIZE))
        pc = int(math.floor(player_x / CHUNK_SIZE))
        now = time.time()
        for dr in range(-build_radius_chunks, build_radius_chunks + 1):
            row = pr + dr
            if row < 0 or row * CHUNK_SIZE > self.world_height:
                continue
            for dc in range(-build_radius_chunks, build_radius_chunks + 1):
                col = pc + dc
                key = (row, col)
                chunk = self.chunks.get(key)
                if chunk is not None and chunk.built:
                    chunk.last_touched = now
                    continue
                with self._stream_lock:
                    if key in self._stream_queued_keys:
                        continue
                    self._stream_queued_keys.add(key)
                priority = dr * dr + dc * dc
                self._stream_seq += 1
                self._stream_queue.put((priority, self._stream_seq, key))

    def evict_far_chunks(self, player_x, player_y, keep_radius_chunks=20):
        """Drops cached surfaces for chunks far from the player. Truth
        data (air_pockets/nests/cells/biome) is retained, so re-entering
        the area rebuilds identically."""
        pr = int(math.floor(player_y / CHUNK_SIZE))
        pc = int(math.floor(player_x / CHUNK_SIZE))
        for key, chunk in list(self.chunks.items()):
            row, col = key
            if abs(row - pr) > keep_radius_chunks or abs(col - pc) > keep_radius_chunks:
                if chunk.built:
                    with chunk.lock:
                        chunk.visuals.clear()
                        chunk.hitboxes.clear()
                        chunk.built = False

    # ------------------------------------------------------------------
    # World generation (truth-only, one-time)
    # ------------------------------------------------------------------

    def generate_world(self, loading_screen: LoadingScreen = None):
        """Generates ALL truth data (air pockets, nests, cells) once, up
        front. Builds no surfaces at all -- surfaces are built lazily by
        the streaming system as the player explores."""

        print(f"{time.strftime('%H:%M:%S')} - world truth generation starting...")

        if loading_screen is not None:
            loading_screen.put(0, "Generating master cave")

        # initial band of surface pockets across the generation span
        x = -CHUNK_SIZE
        while x < self.world_width + CHUNK_SIZE:
            r = random.randint(10, 30)
            self.add_air_pocket_clump(x, 0, r, override=True)
            x += r / 2

        self.generate_descending_cave(self.world_width / 2, 0, 40, math.pi / 2)

        num_steps = max(1, int(self.world_height / 100))
        for i in range(num_steps):
            if loading_screen is not None:
                loading_screen.put((i + 1) / num_steps, f"Generating world section {i + 1}/{num_steps}")

            for j in range(max(1, int(self.world_width / 1000))):
                base_x = j * 1000

                if random.randint(1, 20) == 1:
                    self.generate_skinny_cave(base_x + random.randint(0, 1000), random.randint(0, int(self.world_height / 3)), random.randint(20, 60), random.random() * 2 * math.pi)
                if random.randint(1, 20) == 1:
                    self.generate_skinny_cave(
                        base_x + random.randint(0, 1000), random.randint(int(self.world_height / 4), self.world_height), random.randint(30, 90), random.random() * 2 * math.pi
                    )
                if random.randint(1, 35) == 1:
                    self.generate_blob_cave(
                        base_x + random.randint(0, 1000), random.randint(int(self.world_height / 4), self.world_height), random.randint(30, 60), random.random() * 2 * math.pi
                    )
                if random.randint(1, 20) == 1:
                    self.generate_blob_cave(
                        base_x + random.randint(0, 1000), random.randint(int(self.world_height * 2 / 3), self.world_height), random.randint(60, 120), random.random() * 2 * math.pi
                    )

                y_white = random.randint(500, max(501, self.world_height - 500))
                denom = self._nest_chance("white", self._depth_fraction(y_white))
                if denom and random.randint(1, denom) == 1:
                    self.generate_nest(base_x + random.randint(0, 1000), y_white, "white")

                y_blue = random.randint(500, max(501, self.world_height - 500))
                denom = self._nest_chance("blue", self._depth_fraction(y_blue))
                if denom and random.randint(1, denom) == 1:
                    self.generate_nest(base_x + random.randint(0, 1000), y_blue, "blue")

                y_red = random.randint(500, max(501, self.world_height - 500))
                denom = self._nest_chance("red", self._depth_fraction(y_red))
                if denom and random.randint(1, denom) == 1:
                    self.generate_nest(base_x + random.randint(0, 1000), y_red, "red")

        print(f"{time.strftime('%H:%M:%S')} - world truth generation complete.")
        if loading_screen is not None:
            loading_screen.put(1, "World generation complete")

    def _nest_chance(self, nest_type, depth_frac):
        rules = BIOME_RULES["default"]["nest_rules"][nest_type]
        if depth_frac < rules["min_frac"]:
            return None
        return rules["early_denom"] if depth_frac < rules["switch_frac"] else rules["late_denom"]

    # ------------------------------------------------------------------
    # Cave / nest generation helpers -- bounded by world_height only
    # ------------------------------------------------------------------

    def generate_nest(self, x, y, nest_type, size=0):
        y = max(max_airpocket_radius, min(self.world_height - max_airpocket_radius, y))
        if size == 0:
            size = random.randint(100, 100 + (y * 150) // self.world_height)
        # NOTE: nest.Nest no longer takes a layer_index argument.
        new_nest = nest.Nest(self.default_zooms, self.world_height, nest_type, x, y, size)
        rect = new_nest.get_rect()
        for existing in self._nests_touching_rect(rect):
            if rect.colliderect(existing.get_rect()):
                return False
        for row, col in self._chunks_in_rect(new_nest.left, new_nest.top, new_nest.size, new_nest.size, pad=1):
            self.get_or_create_chunk(row, col).nests.append(new_nest)

        cave_size = (size * random.randint(0, 2) / 3 + 80) / 3
        if cave_size > 15:
            self.generate_skinny_cave(x, y - cave_size / 2, cave_size, -math.pi / 2, max_pockets=10, shrinking=True)
        else:
            self.add_air_pocket_clump(x, y - cave_size / 2, cave_size)
        return True

    def generate_blob_cave(self, start_x, start_y, start_r, start_dir=0, max_pockets=10):
        if max_pockets > 0 and (start_y - 2 * start_r) > 0 and start_y - start_r < self.world_height and start_r > 0:
            self.add_air_pocket_clump(start_x, start_y, start_r)
            for i in range(2):
                r = start_r + (random.random() - 0.6) * 20
                dir = start_dir + (random.random() - 0.5) * math.pi
                x = start_x + math.cos(dir) * min(r, start_r) * 0.8
                y = start_y + math.sin(dir) * min(r, start_r) * 0.8 * 0.2
                self.generate_blob_cave(x, y, r, dir, max_pockets - 1)
                if random.randint(1, 15) > 1:
                    break

    def generate_skinny_cave(self, start_x, start_y, start_r, start_dir=0, max_pockets=20, shrinking=False):
        if max_pockets > 0 and (start_y - 2 * start_r) > 0 and start_y - start_r < self.world_height and start_r > 0:
            self.add_air_pocket_clump(start_x, start_y, start_r)
            for i in range(2):
                r = start_r + (random.random() - 0.6) * 5
                if shrinking:
                    r = start_r - random.random() * 2
                dir = start_dir + (random.random() - 0.5) * math.pi / 2
                x = start_x + math.cos(dir) * min(r, start_r) * 0.8
                y = start_y + math.sin(dir) * min(r, start_r) * 0.8 * 0.8
                self.generate_skinny_cave(x, y, r, dir, max_pockets - 1, shrinking=shrinking)
                if random.randint(1, 30) > 1:
                    break

    def generate_descending_cave(self, start_x, start_y, start_r, start_dir=0):
        while start_y - start_r < self.world_height:
            bounded_x = abs(math.fmod(start_x, 2 * self.world_width) - self.world_width)
            self.add_air_pocket_clump(bounded_x, start_y, start_r)
            if start_y > 600 and start_y < self.world_height - 600 and random.randint(1, 100) == 1:
                self.generate_nest(bounded_x, start_y + random.randint(-100, 100), "white")

            r = min(50, max(10, start_r + random.randint(-5, 5)))
            dir = start_dir + (random.random() - 0.5) * math.pi / 2
            x = start_x + int(math.cos(dir) * min(r, start_r) * 0.8)
            y = start_y + int(abs(math.sin(dir)) * min(r, start_r) * 0.5)
            start_x, start_y, start_r, start_dir = x, y, r, dir
            #self.generate_descending_cave(x, y, r, dir)

    def generate_bedrock_cave(self, start_x, start_y, start_r, start_dir=0, max_pockets=3):
        if max_pockets > 0 and (start_y - 2 * start_r) > 0 and start_y - start_r < self.world_height and start_r > 0:
            self.add_air_pocket_clump(start_x, start_y, start_r)
            for i in range(2):
                r = start_r + (random.random() - 0.6) * 20
                dir = start_dir + (random.random() - 0.5) * math.pi / 2
                x = start_x + math.cos(dir) * min(r, start_r) * 0.7
                y = start_y + math.sin(dir) * min(r, start_r) * 0.7 * 0.5
                self.generate_bedrock_cave(x, y, r, dir, max_pockets - 1)
                if random.randint(1, 30) > 1:
                    break

    def add_air_pocket_clump(self, x, y, radius, player_made=False, override=False, spreading=1 / 3):
        spreading = radius * spreading
        for i in range(3):
            self.add_air_pocket(x + spreading * (random.random() * 2 - 1), y + spreading * (random.random() * 2 - 1), radius, player_made=player_made, override=override)

    def add_air_pocket(self, x, y, radius, recursions=0, player_made=False, override=False):
        radius = min(radius, max_airpocket_radius)

        if recursions > 3 or y < 0 or y > self.world_height:
            return False
        if not player_made and (x + radius > self.world_width or x - radius < 0):
            return False

        base_row = math.floor(y / CHUNK_SIZE)
        base_col = math.floor(x / CHUNK_SIZE)

        if not player_made and not override:
            for d_row in range(-1, 2):
                for d_col in range(-1, 2):
                    chunk = self.chunks.get((base_row + d_row, base_col + d_col))
                    if chunk is None:
                        continue
                    for air_pocket in chunk.air_pockets:
                        dx = air_pocket.x - x
                        dy = air_pocket.y - y
                        combined = air_pocket.r + radius + 10
                        if abs(dx) > combined or abs(dy) > combined:
                            continue
                        d = math.sqrt(dx * dx + dy * dy)
                        if d < radius / 4:
                            return False
                        if air_pocket.r + radius < d < air_pocket.r + radius + 10:
                            return self.add_air_pocket((air_pocket.x + x) / 2, (air_pocket.y + y) / 2, (air_pocket.r + radius) / 2, recursions=recursions + 1)

        if (not player_made) and random.randint(1, 10) == 1:  # noqa: SIM108
            new_air_pocket = AirPocket(x, y, radius, pocket_type="Circle", player_made=player_made)
        else:
            new_air_pocket = AirPocket(x, y, radius, player_made=player_made)

        if not player_made and random.randint(1, 50) == 1:
            self.add_cell((x, y))

        touched_chunks = []
        for row, col in self._chunks_in_rect(new_air_pocket.left, new_air_pocket.top, new_air_pocket.true_r * 2, new_air_pocket.true_r * 2, pad=0):
            chunk = self.get_or_create_chunk(row, col)
            chunk.air_pockets.append(new_air_pocket)
            touched_chunks.append(chunk)

        if player_made:
            # Truth data is updated above regardless. Only patch surfaces
            # for chunks that are already built; unbuilt chunks will pick
            # this pocket up naturally whenever they're eventually built.
            for chunk in touched_chunks:
                if chunk.built:
                    self._carve_chunk_incremental(chunk, new_air_pocket)

        return True

    def add_cell(self, coords, velocities=(1, 1)):
        new_cell = Cell(coords, velocities)
        row = math.floor(new_cell.y / CHUNK_SIZE)
        col = math.floor(new_cell.x / CHUNK_SIZE)
        self.get_or_create_chunk(row, col).cells.append(new_cell)

    def add_interaction_display(self, display):
        self.display_manager.display_in_range(display)

    def remove_interaction_display(self, display, complete=False):
        self.display_manager.display_out_range(display, complete=complete)

    # ------------------------------------------------------------------
    # Vignette
    # ------------------------------------------------------------------

    def draw_vignette(self, surface, window_size, offset_x=0, offset_y=0):
        w, h = window_size
        if self._vignette_surf is None or self._vignette_size != window_size:
            self._vignette_surf = pygame.transform.smoothscale(vignette_img, (w, h))
            self._vignette_size = window_size
        surface.blit(self._vignette_surf, (offset_x, offset_y), special_flags=pygame.BLEND_RGB_MULT)

    # ------------------------------------------------------------------
    # Collision
    # ------------------------------------------------------------------

    def _sample_chunk(self, wx, wy):
        # NOTE: preserves the original behavior of sampling hitboxes at
        # zoom key 1 specifically (a full-res collision layer), which is
        # assumed to be present in default_zooms at runtime, same as before.
        if wy < 0:
            return False
        if wy >= self.world_height:
            return True
        col = int(math.floor(wx / CHUNK_SIZE))
        row = int(math.floor(wy / CHUNK_SIZE))
        chunk = self.chunks.get((row, col))
        if chunk is None or not chunk.built or 1 not in chunk.hitboxes:
            return True  # unbuilt/unknown chunk -> treat as solid (safe default)
        px = max(0, min(int(CHUNK_SIZE - 1), int(wx % CHUNK_SIZE)))
        py = max(0, min(int(CHUNK_SIZE - 1), int(wy % CHUNK_SIZE)))
        return chunk.hitboxes[1].get_at((px, py))[0] > 128

    def _sample_chunk_visuals(self, wx, wy):
        if wy < 0:
            return False
        if wy >= self.world_height:
            return True
        col = int(math.floor(wx / CHUNK_SIZE))
        row = int(math.floor(wy / CHUNK_SIZE))
        chunk = self.chunks.get((row, col))
        if chunk is None or not chunk.built or 1 not in chunk.visuals:
            return True
        px = max(0, min(int(CHUNK_SIZE - 1), int(wx % CHUNK_SIZE)))
        py = max(0, min(int(CHUNK_SIZE - 1), int(wy % CHUNK_SIZE)))
        return chunk.visuals[1].get_at((px, py))[3] > 128

    def get_normal(self, x, y):  # coordinate should be adjacent to a collision point
        v_x = self._sample_chunk(x - 1, y) - self._sample_chunk(x + 1, y)
        v_y = self._sample_chunk(x, y - 1) - self._sample_chunk(x, y + 1)
        if v_x == v_y == 0:
            tl, tr, bl, br = self._sample_chunk(x - 1, y - 1), self._sample_chunk(x - 1, y + 1), self._sample_chunk(x + 1, y - 1), self._sample_chunk(x + 1, y + 1)
            v_x = (tr or br) - (tl or bl)
            v_y = (tl or tr) - (bl or br)
        if v_x == v_y == 0:
            x, y = int(x), int(y)
            for i in range(x - 8, x + 9, 1):
                row = ""
                for j in range(y - 8, y + 9, 1):
                    row += "X " if self._sample_chunk(i, j) else "_ "
                print(row)
        return (v_x, v_y)

    def collide_rect(self, rect):
        l = float(rect.left)
        r = float(rect.right - 1)
        t = float(rect.top)
        b = float(rect.bottom - 1)
        step = 1
        for i in range(math.floor(b - t)):
            y = t + step * i
            if self._sample_chunk(l, y):
                return (l, y)
            if self._sample_chunk(r, y):
                return (r, y)
        for i in range(math.floor(r - l)):
            x = l + step * i
            if self._sample_chunk(x, b):
                return (x, b)
            if self._sample_chunk(x, t):
                return (x, t)
        return False

    def laser_collide_point(self, x, y):
        if self._sample_chunk_visuals(x, y):
            return True
        if self._sample_chunk(x, y):
            return True
        for n in self._nests_near(x, y, CHUNK_SIZE):
            for enemy in n.enemies:
                if enemy.mode != "Spawn" and enemy.rect.collidepoint(x, y):
                    return True
        return False

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
        cx = left + w / zoom / 2
        cy = top + h / zoom / 2

        def darken(c):
            return (int(c[0] * 0.05), int(c[1] * 0.05), int(c[2] * 0.05))

        surface.fill(darken(self._depth_color(cx, cy)))

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
        for n in self._nests_near(x, y, r):
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
        for n in self._nests_near(x, y, r):
            if n.close(x, y, r):
                n.draw(surface, frame, hitbox=hitboxes, offset_x=offset_x, offset_y=offset_y)

    def draw_health_bars(self, window_size, surface, frame, time=None, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w_width, w_height = window_size
        r = math.sqrt(w_width**2 + w_height**2) / 2 / zoom
        x, y = left + w_width / zoom / 2, top + w_height / zoom / 2
        for n in self._nests_near(x, y, r):
            for enemy in n.enemies:
                enemy.draw_health_bar(surface, frame, time, offset_x=offset_x, offset_y=offset_y)
            if n.close(x, y, r):
                n.draw_health_bar(surface, frame, time, offset_x=offset_x, offset_y=offset_y)

    def draw_interaction_displays(self, surface, frame, time=None, offset_x=0, offset_y=0):
        self.display_manager.draw(surface, frame, time, offset_x, offset_y)

    def draw_cells(self, window_size, surface, frame, hitboxes=False, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w_width, w_height = window_size
        r = math.sqrt(w_width**2 + w_height**2) / 2 / zoom
        x, y = left + w_width / zoom / 2, top + w_height / zoom / 2
        for cell in self._cells_near(x, y, r):
            if cell.close(window_size, frame):
                cell.draw(surface, frame, hitbox=hitboxes, offset_x=offset_x, offset_y=offset_y)

    def draw_enemies(self, window_size, surface, frame, hitboxes=False, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w_width, w_height = window_size
        x, y = left + w_width / zoom / 2, top + w_height / zoom / 2
        r = math.sqrt(w_width**2 + w_height**2) / 2 / zoom
        for n in self._nests_near(x, y, r):
            for i in range(len(n.enemies) - 1, -1, -1):
                enemy = n.enemies[i]
                dx = x - enemy.x
                dy = y - enemy.y
                if abs(dx) < w_width / zoom / 2 + enemy.r and abs(dy) < w_height / zoom / 2 + enemy.r:
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
            return

        top_chunk = math.floor(top / CHUNK_SIZE)
        left_chunk = math.floor(left / CHUNK_SIZE)
        bottom_chunk = math.ceil((top + w_height / zoom) / CHUNK_SIZE)
        right_chunk = math.ceil((left + w_width / zoom) / CHUNK_SIZE)

        if self._vignette_stencil is None or self._vignette_stencil_size != real_window_size:
            self._vignette_stencil = pygame.Surface(real_window_size, pygame.SRCALPHA)
            self._vignette_stencil_size = real_window_size
        self._vignette_stencil.fill((0, 0, 0, 0))

        placeholder = self._get_unbuilt_placeholder(zoom)

        for row in range(top_chunk, bottom_chunk + 1):
            if row < 0:
                continue
            for col in range(left_chunk, right_chunk + 1):
                dest = ((col * CHUNK_SIZE - left) * zoom + offset_x, (row * CHUNK_SIZE - top) * zoom + offset_y)
                chunk = self.chunks.get((row, col))
                if chunk is not None and chunk.built and zoom in chunk.visuals:
                    self._vignette_stencil.blit(chunk.visuals[zoom], dest)
                else:
                    # Streaming hasn't built this chunk yet -- shown as
                    # flat red so lag in the prefetch system is obvious
                    # during testing. Does not trigger generation itself.
                    self._vignette_stencil.blit(placeholder, dest)

        self.draw_vignette(self._vignette_stencil, window_size, offset_x=offset_x, offset_y=offset_y)
        surface.blit(self._vignette_stencil, (0, 0))

    def get_terrain_layer(self, window_size, frame, hitboxes=False, real_window_size=None, offset_x=0, offset_y=0):
        if real_window_size is None:
            real_window_size = window_size
        left, top, zoom = frame
        w_width, w_height = window_size
        layer = self._get_terrain_layer_surface(real_window_size)
        if zoom not in self.default_zooms:
            return layer

        top_chunk = math.floor(top / CHUNK_SIZE)
        left_chunk = math.floor(left / CHUNK_SIZE)
        bottom_chunk = math.ceil((top + w_height / zoom) / CHUNK_SIZE)
        right_chunk = math.ceil((left + w_width / zoom) / CHUNK_SIZE)

        if hitboxes:
            layer.fill((0, 0, 0, 0))
            for row in range(top_chunk, bottom_chunk + 1):
                if row < 0:
                    continue
                for col in range(left_chunk, right_chunk + 1):
                    chunk = self.chunks.get((row, col))
                    if chunk is not None and chunk.built and zoom in chunk.hitboxes:
                        layer.blit(chunk.hitboxes[zoom], ((col * CHUNK_SIZE - left) * zoom + offset_x, (row * CHUNK_SIZE - top) * zoom + offset_y))
        return layer