import math
import random
import threading
import time

import pygame

import scripts.nest as nest
import scripts.particles as particles
from config import CHUNK_SIZE
from scripts.structures.checkpoint import Checkpoint
from scripts.cells import Cell, validate_cell_coords
from scripts.global_assets import get_asset
from scripts.UI.interaction_display import InteractionDisplayManager
from scripts.util import dist, poisson_count

# ------------------------------------------------------------------
# Architecture overview
# ------------------------------------------------------------------
# Terrain is split into a TRUTH layer and a SURFACE (cache) layer.
#
#   Chunk.air_pockets / Chunk.nests / Chunk.cells / Chunk.structures
#       -> truth data. Cheap plain-data objects, no pygame Surfaces.
#          Generated on demand, one chunk at a time, as the player
#          approaches (see present_chunk), and added to incrementally
#          afterwards (player mining).
#
#   Chunk.visuals[zoom] -> derived pygame Surfaces (the pretty rendered
#          art), built lazily from truth data the first time a chunk is
#          needed (see _build_chunk).
#   Chunk.mask[zoom] -> derived pygame.mask.Mask (collision truth), same
#          lazy-build story, used for all terrain collision queries.
#          Both are safe to throw away and rebuild at any time
#          (evict_far_chunks), since they're a pure function of the
#          chunk's truth data.
#
# Chunk.generation_state tracks truth-generation progress through 3
# stages (independent of Chunk.built, which only tracks whether visuals/
# mask are currently resident -- see present_chunk for the full pipeline):
#   "initialized" -> a Chunk object exists (created on first touch, e.g.
#          get_or_create_chunk), possibly already holding air pockets
#          spilled over from a neighboring chunk's cave growth, but none
#          of its own.
#   "generated" -> this chunk has rolled and grown all caves/nests that
#          originate within its own bounds (see _generate_chunk). May
#          still receive further spillover from a not-yet-generated
#          neighbor's cave growth.
#   "finalized" -> structures and elements have been placed for this
#          chunk (see _finalize_chunk), and it will never receive another
#          terrain-generated air pocket: every cave-growth call checks
#          _overlaps_finalized_chunk before carving and simply skips
#          (never partially carves) anything that would touch a finalized
#          chunk, so this guarantee holds regardless of generation order.
#
# Biomes: each Chunk has a `biome` string (currently always "default",
# see get_biome). BIOME_RULES holds per-biome tunables (fill_mode, cave
# kinds, nest frequency/type thresholds by depth), each expressed as an
# expected count per chunk (see poisson_count) rather than a chance roll,
# so origination is naturally chunk-scoped.
# ------------------------------------------------------------------

max_air_pocket_radius = 120
rim_pocket_ratio = 1.5
rocks_world_span = 2 * CHUNK_SIZE

# Chunk.generation_state values -- see the architecture overview above.
STATE_INITIALIZED = "initialized"
STATE_GENERATED = "generated"
STATE_FINALIZED = "finalized"

# How many chunks out present_chunk force-generates (not finalizes) around
# the chunk it's actually presenting, before that chunk itself finalizes.
# Purely a lookahead/richness knob, not a correctness requirement: a
# smaller radius means chunks finalize sooner relative to how far
# generation has spread, so a growing cave runs into a finalized (closed)
# chunk -- and gets cut off, see _overlaps_finalized_chunk -- more often,
# yielding shorter, more contained caves. A larger radius delays
# finalization, giving caves more room to wander before that happens.
# Must be >= 1: a nest can bleed one chunk past its own (pad=1 in
# generate_nest's registration loop) and is never larger than a chunk, so
# radius 1 is what guarantees (by construction, not luck) that a chunk's
# own nest rolls never need to fight over a chunk that's already finalized.
GENERATION_RADIUS_CHUNKS = 3

# World coordinate origin (0, 0): both the player's actual spawn point
# (see world.py) and where the one world-spanning cave descends from.
# world_width is NOT a generation boundary -- generation is on demand per
# chunk (see present_chunk) regardless of x, so it happens uniformly no
# matter how far the player wanders. world_width is only how far the
# player/camera are nudged to stay within (see player.py's edge push,
# releaseTheLight.py's camera clamp), symmetric around this origin.
MASTER_CAVE_ORIGIN = (0, 0)  # (row, col) -- always the first chunk presented

# Structure erase-rect carving (see Terrain.carve_structure_erase_rects) --
# fixed regardless of structure/rect size. Border pockets vary between these
# two, interior pockets aren't used at all (the interior is carved as a
# plain rect, disguised by the border pockets around it).
STRUCTURE_CARVE_MIN_R = 20
STRUCTURE_CARVE_MAX_R = 60

# generate_structures_for_chunk -- world-space y of the guaranteed spawn
# Checkpoint, fixed regardless of the player's own spawn y (dev vs. normal
# mode use different free-fall heights, see world.py)
CHECKPOINT_DEPTH = 400
# The one chunk whose turn at generate_structures_for_chunk places the
# Checkpoint -- its own (x=0, y=CHECKPOINT_DEPTH) center point determines
# which single chunk "owns" it; carve_structure_erase_rects/
# reblit_structure_on_chunks still register it into every chunk its
# footprint actually overlaps, same as before.
CHECKPOINT_CHUNK = (CHECKPOINT_DEPTH // CHUNK_SIZE, 0)


PALETTE = [
    (0.000, (255, 200, 60)),  # golden yellow
    (0.060, (255, 110, 40)),  # bright orange
    (0.120, (255, 60, 90)),  # hot pink-red
    (0.180, (230, 40, 180)),  # magenta
    (0.240, (170, 50, 240)),  # violet
    (0.300, (100, 70, 255)),  # indigo
    (0.360, (60, 120, 255)),  # bright blue
    (0.420, (40, 190, 255)),  # cyan-blue
    (0.480, (40, 230, 210)),  # turquoise
    (0.540, (60, 230, 120)),  # spring green
    (0.600, (170, 230, 60)),  # lime
    (0.660, (255, 230, 50)),  # bright yellow
    (0.720, (255, 160, 40)),  # amber
    (0.780, (255, 90, 60)),  # coral red
    (0.840, (230, 50, 130)),  # rose
    (0.900, (150, 60, 255)),  # purple
    (1.000, (80, 200, 255)),  # sky blue
]

# ------------------------------------------------------------------
# Biome stub -- everything currently resolves to "default". Swap
# get_biome for a noise-based lookup later; add more entries to
# BIOME_RULES as new biomes are introduced.
# ------------------------------------------------------------------

# cave_kinds/nest_rules/surface_fissure expected-per-chunk values below are
# uniform across the whole default biome (no depth dependence) -- depth- or
# region-varying density is a per-biome concern for whenever more biomes
# exist (see get_biome), not something the default biome itself needs to
# encode. Values were derived by taking the old whole-world generation
# loop's total expected event count at the shipped world size (15x100
# chunks) and dividing by the total chunk count, so aggregate density
# roughly matches what shipped before, not an exact match. Retune by feel.
BIOME_RULES = {
    "default": {
        # "solid": chunk starts as solid rock, air pockets are carved (subtracted) out.
        # "air": reserved for future biomes that start hollow and add solid
        #        features instead. Not implemented -- see _render_base_terrain.
        "fill_mode": "solid",
        # Each kind rolls independently per chunk: poisson_count(expected_per_chunk)
        # spawns, each at a uniformly random point inside the chunk -- see
        # generate_caves_for_chunk. shape selects generate_skinny_cave vs
        # generate_blob_cave; skinny/blob each get a small- and large-radius
        # variant for visual variety.
        "cave_kinds": {
            "skinny_small": {"radius_range": (20, 60), "max_pockets": 20, "shape": "skinny", "expected_per_chunk": 0.08},
            "skinny_large": {"radius_range": (30, 120), "max_pockets": 20, "shape": "skinny", "expected_per_chunk": 0.08},
            "blob_small": {"radius_range": (30, 100), "max_pockets": 10, "shape": "blob", "expected_per_chunk": 0.046},
            "blob_large": {"radius_range": (60, 150), "max_pockets": 10, "shape": "blob", "expected_per_chunk": 0.08},
        },
        # Temporary stand-in for a real surface biome (see fill_mode's "air"
        # note) -- a dense scatter of small pockets along row 0 only,
        # reproducing the old edge-to-edge surface band. Remove once
        # fill_mode "air" exists.
        "surface_fissure": {"radius_range": (10, 30), "expected_per_chunk": 38},
        "nest_rules": {
            "white": {"expected_per_chunk": 0.148},
            "blue": {"expected_per_chunk": 0.121},
            "red": {"expected_per_chunk": 0.108},
        },
        # generate_elements_for_chunk -- expected placement attempts per
        # chunk that has any air pockets to anchor against. "spikes" drives
        # both upright and upside-down spike attempts (same count each).
        "element_rules": {
            "spikes_per_chunk": 1,
            "vines_per_chunk": 10,
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
        circle_im_gs.append(get_asset("air_pocket_" + str(i + 1)))
    for i in range(1):
        circle_rim_im_gs.append(get_asset("air_pocket_" + str(i + 1) + "_rim"))
    for i in range(1):
        circle_explode_im_gs.append(get_asset("air_pocket_" + str(i + 1) + "_explode"))
    air_im_gs["circle"] = circle_im_gs
    air_rim_im_gs["circle"] = circle_rim_im_gs
    air_explode_im_gs["circle"] = circle_explode_im_gs
    air_hitbox_im_gs["circle"] = get_asset("air_pocket_hitbox")

    rocks_raw = get_asset("rocks")
    rocks_img["raw"] = rocks_raw
    vignette_img = get_asset("gradient_vignette")


def rect_to_circle(left, top, width, height):
    return left + width / 2, top + height / 2, math.dist((0, 0), (width, height)) / 2


_scaled_img_cache: dict = {}
_scaled_mask_cache: dict = {}
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


def _get_cached_mask(src_surface, pocket_type, img_index, radius, zoom):
    key = (pocket_type, img_index, radius, zoom)
    if key not in _scaled_mask_cache:
        scaled_img = _get_cached_scale(src_surface, pocket_type, img_index, radius, zoom)
        _scaled_mask_cache[key] = pygame.mask.from_surface(scaled_img)
    return _scaled_mask_cache[key]


# ------------------------------------------------------------------
# Chunk -- one bucket of truth data plus (lazily) its derived surfaces
# ------------------------------------------------------------------


class Chunk:
    __slots__ = (
        "row",
        "col",
        "biome",
        "air_pockets",
        "nests",
        "cells",
        "structures",
        "elements",
        "erase_rects",
        "visuals",
        "mask",
        "built",
        "last_touched",
        "generation_state",
        "lock",
    )

    def __init__(self, row, col, biome="default"):
        self.row = row
        self.col = col
        self.biome = biome
        self.air_pockets = []
        self.nests = []
        self.cells = []
        self.structures = []  # generic solid structures (e.g. gateway tiles)
        self.elements = []  # breakable elements (spikes, fire, vines, decorative terrain, ...)
        self.erase_rects = []  # plain-rect carves from structure.erase_rects -- see Terrain.carve_structure_erase_rects
        self.visuals = {}  # dict[zoom] -> Surface, populated once built
        self.mask = None  # single native-resolution pygame.mask.Mask, collision truth, populated once built
        self.built = False
        self.last_touched = 0.0
        self.generation_state = STATE_INITIALIZED
        # Reentrant: _build_chunk can call helpers that also lock this chunk.
        self.lock = threading.RLock()


# ------------------------------------------------------------------
# AirPocket -- pure truth data. No Surfaces are created until a chunk
# using this pocket is actually built (get_img / get_hitbox_img /
# get_rim_img resolve + cache the scaled image on first use).
# ------------------------------------------------------------------


class AirPocket:
    __slots__ = ("x", "y", "r", "true_r", "top", "left", "type", "player_made", "img_index", "rim_img_index")

    def __init__(self, x, y, radius, pocket_type="circle", player_made=False):
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

    def get_hitbox_mask(self):
        # collision is always sampled at native (zoom=1) resolution -- no
        # need for a mask per zoom, unlike get_img/get_hitbox_img/get_rim_img
        # which feed the per-zoom rendered visuals.
        return _get_cached_mask(air_hitbox_im_gs[self.type], self.type + "_hitbox", 0, self.true_r, 1)

    def get_rim_img(self, zoom):
        rim_imgs = air_explode_im_gs[self.type] if self.player_made else air_rim_im_gs[self.type]
        return _get_cached_scale(rim_imgs[self.rim_img_index], self.type + "rim_playermade:" + str(self.player_made), self.rim_img_index, self.true_r, zoom)

    def close(self, x, y, radius):
        return math.dist((self.x, self.y), (x, y)) < radius + self.r


# ------------------------------------------------------------------
# Structure erase-rect border planning -- pure geometry, no chunk/pygame
# state, so it's cheap to call and easy to reason about on its own. Mirrors
# how elements.py keeps its placement math as plain module-level functions.
# See Terrain.carve_structure_erase_rects for how this feeds add_air_pocket.
# ------------------------------------------------------------------

# Distance from each corner over which a border pocket's radius ramps from
# STRUCTURE_CARVE_MIN_R up to STRUCTURE_CARVE_MAX_R -- reusing the max as the
# ramp length keeps this one fewer magic number, and gives a full, visible
# taper rather than an abrupt jump right at the corner.
_BORDER_TAPER_DIST = STRUCTURE_CARVE_MAX_R
_BORDER_JITTER_R = (STRUCTURE_CARVE_MAX_R - STRUCTURE_CARVE_MIN_R) * 0.25


def _border_taper_radius(d, length):
    """Target radius for a border pocket at distance d along an edge of the
    given length, before jitter: MIN_R at both corners, ramping up to MAX_R
    over _BORDER_TAPER_DIST -- softening corners while leaning larger
    (fewer pockets) along the rest of the edge. Short edges just never
    reach MAX_R (the two ramps meet in the middle), which is fine."""
    ramp = min(d, length - d, _BORDER_TAPER_DIST) / _BORDER_TAPER_DIST
    return STRUCTURE_CARVE_MIN_R + (STRUCTURE_CARVE_MAX_R - STRUCTURE_CARVE_MIN_R) * ramp


def _walk_border_edge(pockets, start, direction, perp, length):
    """Appends (x, y, r) pockets walking from one corner of an edge to the
    other (exclusive of both ends -- corners get their own explicit pocket,
    see _plan_border_pockets). direction/perp are unit vectors (along the
    edge, and outward off the edge, respectively). Step size scales with
    each pocket's own radius, so bigger pockets naturally space out more.

    Perpendicular jitter only ever pushes a pocket further outward (deeper
    into the surrounding rock), never inward: carve_structure_erase_rects's
    core rect is inset by exactly STRUCTURE_CARVE_MIN_R, on the assumption
    that every border pocket reaches at least that far inward from the edge
    line. A pocket centered ON the edge reaches its own radius inward, so
    jittering it outward eats into that -- capping the outward jitter at
    (r - STRUCTURE_CARVE_MIN_R) keeps the worst case (a MIN_R pocket,
    jittered fully outward) still reaching exactly MIN_R inward, with no
    gap between the border ring and the core it's meant to meet."""
    d = STRUCTURE_CARVE_MIN_R * 1.3
    while d < length - STRUCTURE_CARVE_MIN_R * 1.3:
        r = _border_taper_radius(d, length) + random.uniform(-_BORDER_JITTER_R, _BORDER_JITTER_R)
        r = max(STRUCTURE_CARVE_MIN_R, min(STRUCTURE_CARVE_MAX_R, r))
        perp_offset = random.uniform(0, 1) * (r - STRUCTURE_CARVE_MIN_R)
        x = start[0] + direction[0] * d + perp[0] * perp_offset
        y = start[1] + direction[1] * d + perp[1] * perp_offset
        pockets.append((x, y, r))
        d += r * 1.3


def _plan_border_pockets(rect):
    """Plans the full set of (x, y, r) air pockets lining rect's perimeter:
    one small, corner-softening pocket at each corner, plus a taper-sized,
    jittered walk along each of the 4 edges. Doesn't touch the interior --
    see Terrain.carve_structure_erase_rects, which carves that as a plain
    rect instead, relying on this border to hide its sharp edges."""
    pockets = [(x, y, STRUCTURE_CARVE_MIN_R) for x, y in (rect.topleft, rect.topright, rect.bottomleft, rect.bottomright)]

    _walk_border_edge(pockets, rect.topleft, (1, 0), (0, -1), rect.width)  # top, outward = up
    _walk_border_edge(pockets, rect.bottomleft, (1, 0), (0, 1), rect.width)  # bottom, outward = down
    _walk_border_edge(pockets, rect.topleft, (0, 1), (-1, 0), rect.height)  # left, outward = left
    _walk_border_edge(pockets, rect.topright, (0, 1), (1, 0), rect.height)  # right, outward = right

    return pockets


# ------------------------------------------------------------------
# Terrain
# ------------------------------------------------------------------


class Terrain:
    def __init__(self, world_width: int, world_height: int, default_zooms: list = (0.1, 2)):

        self.knockback_circles = []
        self.new_knockback_circles = []
        self.player_damage_circles = []
        self.new_player_damage_circles = []
        self.pending_shake = 0  # generic screen-shake request for events not tied to the player's own laser (e.g. cell explosions) -- consumed by the main loop

        self.display_manager = InteractionDisplayManager()

        # world_width does not bound generation -- see MASTER_CAVE_ORIGIN's
        # note. It's only how far the player/camera are meant to stay
        # within, centered on the origin; the world itself extends
        # infinitely in both x directions, generating identically however
        # far the player wanders.
        self.world_width = world_width
        self.world_height = world_height
        self.default_zooms = default_zooms
        self.particles = particles.Particles()
        self.enemies = []

        self.chunks: dict[tuple, Chunk] = {}
        # Flat registry of every nest, alongside (not instead of) their
        # per-chunk registration in chunk.nests -- the per-chunk copies are
        # what spatial queries (_nests_touching_rect etc.) use, since a nest
        # can be registered into several chunks; this is for callers that
        # want every nest exactly once regardless of chunk (see
        # World.heal_nests/remove_enemies), without scanning self.chunks.
        self.nests: list = []

        self._rocks_scaled = {}
        for zoom in default_zooms:
            scaled_span = int(rocks_world_span * zoom)
            self._rocks_scaled[zoom] = pygame.transform.smoothscale(rocks_img["raw"], (scaled_span, scaled_span))

        self._terrain_layer = None
        self._terrain_layer_size = None
        self._scratch_surfaces = {}
        self._placeholder_surfaces = {}
        self._vignette_surf = None
        self._vignette_size = None
        self._vignette_stencil = None
        self._vignette_stencil_size = None

        # entity collision: cached fully-solid masks, keyed by (width, height) --
        # entity hitbox rects don't change size after spawn, so this is built once
        # per distinct size and reused every collision check thereafter.
        self._rect_mask_cache = {}

        # streaming -- see _stream_worker_loop for why this isn't a
        # queue.PriorityQueue (fixed priority at enqueue time can't reflect
        # the player having moved since)
        self._stream_pending = set()  # {(row, col)} not yet built, not currently being presented
        self._stream_chunk_pos = (0, 0)  # player's (row, col), refreshed every update_streaming call
        self._stream_lock = threading.Lock()
        self._stream_thread = None
        self._last_evict_time = 0.0

        # Currently-built chunk keys -- self.chunks itself only grows over a
        # session (evicting a chunk keeps its truth data, see
        # evict_far_chunks), so this is what evict_far_chunks scans instead:
        # it stays roughly keep_radius_chunks-sized forever, rather than
        # growing with how much of the world has been visited.
        self._built_chunk_keys = set()
        self._built_lock = threading.Lock()

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
        col_end = math.floor((left + width) / CHUNK_SIZE) + pad
        row_start = max(0, math.floor(top / CHUNK_SIZE) - pad)
        row_end = math.floor((top + height) / CHUNK_SIZE) + pad
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
        for chunk in self._chunks_near(x, y, radius, 0):
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
        for row, col in self._chunks_in_rect(rect.left, rect.top, rect.width, rect.height, pad=0):
            chunk = self.chunks.get((row, col))
            if chunk is None:
                continue
            for n in chunk.nests:
                if id(n) not in seen:
                    seen.add(id(n))
                    result.append(n)
        return result

    def _elements_touching_rect(self, rect):
        seen = set()
        result = []
        for row, col in self._chunks_in_rect(rect.left, rect.top, rect.width, rect.height, pad=0):
            chunk = self.chunks.get((row, col))
            if chunk is None:
                continue
            for e in chunk.elements:
                if id(e) not in seen:
                    seen.add(id(e))
                    result.append(e)
        return result

    def _structures_touching_rect(self, rect):
        seen = set()
        result = []
        for row, col in self._chunks_in_rect(rect.left, rect.top, rect.width, rect.height, pad=0):
            chunk = self.chunks.get((row, col))
            if chunk is None:
                continue
            for s in chunk.structures:
                if id(s) not in seen:
                    seen.add(id(s))
                    result.append(s)
        return result

    def _elements_touching_chunks(self, chunks):
        seen = set()
        result = []
        for chunk in chunks:
            for e in chunk.elements:
                if id(e) not in seen:
                    seen.add(id(e))
                    result.append(e)
        return result

    def _cells_in_rect(self, rect):
        seen = set()
        result = []
        for row, col in self._chunks_in_rect(rect.left, rect.top, rect.width, rect.height, pad=0):
            chunk = self.chunks.get((row, col))
            if chunk is None:
                continue
            for c in chunk.cells:
                if id(c) not in seen:
                    seen.add(id(c))
                    result.append(c)
        return result

    # ------------------------------------------------------------------
    # Structure baking
    # ------------------------------------------------------------------

    def reblit_structure_on_chunks(self, structure):
        """Registers structure into every chunk its registration_rect
        (footprint + erase_rects) touches, mirroring how
        elements.attempt_place_element registers an element across its own
        footprint + anchor. Re-callable (e.g. a gateway tile re-baking
        after opening) -- guarded by containment check, unlike element
        registration which only ever runs once per element."""
        rect = structure.get_registration_rect()
        for row, col in self._chunks_in_rect(rect.left, rect.top, rect.width, rect.height, pad=1):
            chunk = self.get_or_create_chunk(row, col)
            if structure not in chunk.structures:
                chunk.structures.append(structure)
            if chunk.built:
                self._bake_structure_into_chunk(chunk, structure)

    def _bake_structure_into_chunk(self, chunk, structure):
        left, top = chunk.col * CHUNK_SIZE, chunk.row * CHUNK_SIZE
        with chunk.lock:
            if chunk.mask is not None:
                collide_mask = structure.get_collide_hitbox_mask()
                if collide_mask is not None:
                    offset = (int(structure.left - left), int(structure.top - top))
                    chunk.mask.draw(collide_mask, offset)

    def _reblit_solid_structures_on_chunk(self, chunk):
        """Re-apply nests + structures on top of a chunk's collision mask
        after carving, since the carve erase can remove overlapping solid
        features drawn earlier."""
        if chunk.mask is None:
            return
        left, top = chunk.col * CHUNK_SIZE, chunk.row * CHUNK_SIZE
        for n in chunk.nests:
            offset = (int(n.left - left), int(n.top - top))
            chunk.mask.draw(n.hitbox_mask, offset)
        for structure in chunk.structures:
            collide_mask = structure.get_collide_hitbox_mask()
            if collide_mask is not None:
                offset = (int(structure.left - left), int(structure.top - top))
                chunk.mask.draw(collide_mask, offset)
        for element in chunk.elements:
            collide_mask = element.get_collide_hitbox_mask()
            if collide_mask is not None:
                offset = (int(element.left - left), int(element.top - top))
                chunk.mask.draw(collide_mask, offset)

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

    # Debug colors for a not-yet-built chunk, by generation_state -- lets
    # streaming/generation lag show up visually during testing (see
    # draw_terrain). Does not trigger generation itself.
    _PLACEHOLDER_COLORS = {
        STATE_INITIALIZED: (200, 0, 0),
        STATE_GENERATED: (200, 200, 0),
        STATE_FINALIZED: (0, 160, 0),
    }

    def _get_unbuilt_placeholder(self, zoom, state):
        key = (zoom, state)
        if key not in self._placeholder_surfaces:
            chunk_px = max(1, int(CHUNK_SIZE * zoom))
            surf = pygame.Surface((chunk_px, chunk_px))
            surf.fill(self._PLACEHOLDER_COLORS.get(state, self._PLACEHOLDER_COLORS[STATE_INITIALIZED]))
            self._placeholder_surfaces[key] = surf
        return self._placeholder_surfaces[key]

    # ------------------------------------------------------------------
    # Noise / colour -- continuous with world_y, no layers
    # ------------------------------------------------------------------

    def _noise_val(self, x, y, scale=1):
        x, y = x * scale, y * scale
        v = math.sin(x * 0.017 + y * 0.011) * 0.4
        v += math.cos(x * 0.031 - y * 0.023) * 0.3
        v += math.sin(x * 0.053 + y * 0.047 + 1.3) * 0.2
        v += math.cos(x * 0.079 - y * 0.061 + 2.7) * 0.1
        return max(-1.0, min(1.0, v))

    def _depth_fraction(self, y):
        return max(0.0, min(1.0, y / self.world_height))

    def _depth_color(self, world_x, world_y):
        depth_frac = self._depth_fraction(world_y)
        noise = self._noise_val(world_x, world_y) * 0.03
        d = max(0.0, min(1.0, depth_frac + noise))

        for i in range(len(PALETTE) - 1):
            d0, c0 = PALETTE[i]
            d1, c1 = PALETTE[i + 1]
            if d <= d1:
                t = (d - d0) / (d1 - d0) if d1 != d0 else 0.0
                r = int(c0[0] + (c1[0] - c0[0]) * t)
                g = int(c0[1] + (c1[1] - c0[1]) * t)
                b = int(c0[2] + (c1[2] - c0[2]) * t)
                return (r, g, b)
        return PALETTE[-1][1]

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
            chunk.mask = pygame.mask.Mask((CHUNK_SIZE, CHUNK_SIZE), fill=True)

            for pocket in chunk.air_pockets:
                self._carve_hitbox(chunk, pocket)
                for zoom in self.default_zooms:
                    self._carve_visual(chunk, pocket, zoom)

            for rect in chunk.erase_rects:
                self._carve_hitbox_rect(chunk, rect)
                for zoom in self.default_zooms:
                    self._carve_visual_rect(chunk, rect, zoom)

            self._reblit_solid_structures_on_chunk(chunk)

            chunk.built = True
            with self._built_lock:
                self._built_chunk_keys.add((chunk.row, chunk.col))

    def get_chunk_if_built(self, row, col):
        chunk = self.chunks.get((row, col))
        if chunk is not None and chunk.built:
            return chunk
        return None

    # ------------------------------------------------------------------
    # Carving (used both by lazy build, and incremental player-mining)
    # ------------------------------------------------------------------

    def _carve_hitbox(self, chunk, air_pocket):
        left, top = chunk.col * CHUNK_SIZE, chunk.row * CHUNK_SIZE
        l = int(air_pocket.left - left)
        t = int(air_pocket.top - top)
        chunk.mask.erase(air_pocket.get_hitbox_mask(), (l, t))

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

    def _carve_hitbox_rect(self, chunk, rect):
        left, top = chunk.col * CHUNK_SIZE, chunk.row * CHUNK_SIZE
        offset = (int(rect.left - left), int(rect.top - top))
        chunk.mask.erase(self._get_rect_mask(rect.width, rect.height), offset)

    def _carve_visual_rect(self, chunk, rect, zoom):
        """Plain rect erase, no rim -- structure erase_rects rely on the
        border air pockets around them (see carve_structure_erase_rects) to
        hide the rect's sharp edges, so there's no shading transition to
        blend here the way a lone air pocket needs its rim for."""
        left, top = chunk.col * CHUNK_SIZE, chunk.row * CHUNK_SIZE
        l = zoom * (rect.left - left)
        t = zoom * (rect.top - top)
        size = (max(1, int(rect.width * zoom)), max(1, int(rect.height * zoom)))
        eraser = pygame.Surface(size, pygame.SRCALPHA)
        eraser.fill((255, 255, 255, 255))
        chunk.visuals[zoom].blit(eraser, (l, t), special_flags=pygame.BLEND_RGBA_SUB)

    def _rebuild_chunk_mask(self, chunk):
        """Recomputes chunk.mask from truth data alone (solid rock, minus
        every air pocket, plus nests/structures/elements drawn back on top)
        -- visuals untouched. Needed when removing a solid-adding feature
        (e.g. remove_element): a targeted mask.erase of just that feature's
        own hitbox shape would also erase any independently-solid terrain
        that happened to coincide with the same pixels (e.g. a spike's
        footprint mostly sitting on top of genuinely solid rock), leaving a
        spike-shaped hole in the terrain behind it. A full rebuild has no
        such ambiguity."""
        if not chunk.built or chunk.mask is None:
            return
        with chunk.lock:
            chunk.mask = pygame.mask.Mask((CHUNK_SIZE, CHUNK_SIZE), fill=True)
            for pocket in chunk.air_pockets:
                self._carve_hitbox(chunk, pocket)
            for rect in chunk.erase_rects:
                self._carve_hitbox_rect(chunk, rect)
            self._reblit_solid_structures_on_chunk(chunk)

    def _carve_chunk_incremental(self, chunk, air_pocket):
        """Patch a single already-built chunk with one new air pocket,
        without a full rebuild."""
        with chunk.lock:
            self._carve_hitbox(chunk, air_pocket)
            for zoom in self.default_zooms:
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
            key = self._pop_nearest_pending()
            if key is None:
                time.sleep(0.05)
                continue
            row, col = key
            self.present_chunk(row, col)

    def _pop_nearest_pending(self):
        """Picks and removes whichever pending chunk is currently closest
        to the player, recomputed fresh against _stream_chunk_pos every
        call -- unlike a priority queue (fixed priority at enqueue time),
        this can never go stale: a chunk queued while the player was
        somewhere else can't jump the line ahead of what's actually
        nearest by the time a worker slot opens up."""
        with self._stream_lock:
            if not self._stream_pending:
                return None
            pr, pc = self._stream_chunk_pos
            nearest = min(self._stream_pending, key=lambda rc: (rc[0] - pr) ** 2 + (rc[1] - pc) ** 2)
            self._stream_pending.discard(nearest)
            return nearest

    def update_streaming(self, player_x, player_y, build_radius_chunks=3):
        """Call once per tick (or every few ticks). Marks chunks around the
        player as pending for the background worker to present, and
        refreshes the player position the worker prioritizes against (see
        _pop_nearest_pending)."""
        pr = int(math.floor(player_y / CHUNK_SIZE))
        pc = int(math.floor(player_x / CHUNK_SIZE))
        now = time.time()
        with self._stream_lock:
            self._stream_chunk_pos = (pr, pc)
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
                    self._stream_pending.add(key)

    def evict_far_chunks(self, player_x, player_y, keep_radius_chunks=20, min_interval=5.0):
        """Drops cached surfaces for chunks far from the player. Truth
        data (air_pockets/nests/cells/biome) is retained, so re-entering
        the area rebuilds identically. Scans _built_chunk_keys, not
        self.chunks -- self.chunks only grows over a session, but built
        chunks stay bounded to roughly the area around the player, so this
        scan doesn't get any slower the more of the world has been visited.
        Still throttled to once per min_interval seconds regardless."""
        now = time.time()
        if now - self._last_evict_time < min_interval:
            return
        self._last_evict_time = now
        pr = int(math.floor(player_y / CHUNK_SIZE))
        pc = int(math.floor(player_x / CHUNK_SIZE))
        with self._built_lock:
            keys = list(self._built_chunk_keys)
        for key in keys:
            row, col = key
            if abs(row - pr) > keep_radius_chunks or abs(col - pc) > keep_radius_chunks:
                chunk = self.chunks.get(key)
                if chunk is not None and chunk.built:
                    with chunk.lock:
                        chunk.visuals.clear()
                        chunk.mask = None
                        chunk.built = False
                with self._built_lock:
                    self._built_chunk_keys.discard(key)

    # ------------------------------------------------------------------
    # World generation -- on demand, one chunk at a time. present_chunk is
    # the only entry point external callers need (used by both the stream
    # worker above and the synchronous starting-chunk call in world.py);
    # everything else here is its internal pipeline. See the architecture
    # overview at the top of this file for what each generation_state means.
    # ------------------------------------------------------------------

    def present_chunk(self, row, col):
        """Runs whatever's left of the full presentation pipeline for one
        chunk -- origination, finalization (radius lookahead + structures
        + elements), then visual/mask build -- and returns it. Idempotent:
        safe to call on a chunk at any state, it only does what's not
        already done."""
        chunk = self.get_or_create_chunk(row, col)
        self._finalize_chunk(chunk)  # also generates first, if needed
        if not chunk.built:
            self._build_chunk(chunk)
        return chunk

    def _generate_chunk(self, chunk):
        """Step 2: roll and grow every cave/nest that originates within
        this chunk's own bounds, once. No-op if already generated (or
        finalized)."""
        with chunk.lock:
            if chunk.generation_state != STATE_INITIALIZED:
                return
            rules = BIOME_RULES.get(chunk.biome, BIOME_RULES["default"])
            self.generate_caves_for_chunk(chunk, rules)
            self.generate_nests_for_chunk(chunk, rules)
            self.generate_surface_fissure_for_chunk(chunk, rules)
            if (chunk.row, chunk.col) == MASTER_CAVE_ORIGIN:
                self._generate_master_cave()
            chunk.generation_state = STATE_GENERATED

    def _finalize_chunk(self, chunk):
        """Steps 3-5: force origination for every chunk within
        GENERATION_RADIUS_CHUNKS (pure lookahead -- no-op for chunks
        already generated/finalized), then place this chunk's structures
        and elements and mark it finalized. No-op if already finalized."""
        if chunk.generation_state == STATE_FINALIZED:
            return
        self._generate_chunk(chunk)
        for dr in range(-GENERATION_RADIUS_CHUNKS, GENERATION_RADIUS_CHUNKS + 1):
            neighbor_row = chunk.row + dr
            if neighbor_row < 0:
                continue
            for dc in range(-GENERATION_RADIUS_CHUNKS, GENERATION_RADIUS_CHUNKS + 1):
                if dr == 0 and dc == 0:
                    continue
                self._generate_chunk(self.get_or_create_chunk(neighbor_row, chunk.col + dc))
        with chunk.lock:
            if chunk.generation_state == STATE_FINALIZED:
                return
            rules = BIOME_RULES.get(chunk.biome, BIOME_RULES["default"])
            self.generate_structures_for_chunk(chunk)
            self.generate_elements_for_chunk(chunk, rules)
            chunk.generation_state = STATE_FINALIZED

    def _overlaps_finalized_chunk(self, x, y, r):
        """True if a circle of radius r centered at (x, y) touches any
        chunk that's already finalized. World-gen cave/nest growth checks
        this before carving, and stops (see generate_blob_cave etc. and
        add_air_pocket) rather than partially carving into a chunk whose
        structures/elements are already locked in -- this is what makes a
        finalized chunk's truth data permanent regardless of generation
        order (see the architecture overview)."""
        row_c = math.floor(y / CHUNK_SIZE)
        col_c = math.floor(x / CHUNK_SIZE)
        chunk_radius = math.ceil(r / CHUNK_SIZE)
        for dr in range(-chunk_radius, chunk_radius + 1):
            for dc in range(-chunk_radius, chunk_radius + 1):
                chunk = self.chunks.get((row_c + dr, col_c + dc))
                if chunk is not None and chunk.generation_state == STATE_FINALIZED:
                    return True
        return False

    def _grow_cave(self, shape, x, y, r, direction, max_pockets):
        if shape == "skinny":
            self.generate_skinny_cave(x, y, r, direction, max_pockets=max_pockets)
        else:
            self.generate_blob_cave(x, y, r, direction, max_pockets=max_pockets)

    def generate_caves_for_chunk(self, chunk, rules):
        """One expected-count roll per cave_kinds entry (see BIOME_RULES),
        each spawning at a uniformly random point inside this chunk. Density
        is uniform across the biome -- depth/region variation is a per-biome
        concern for later, not encoded here."""
        for cfg in rules.get("cave_kinds", {}).values():
            for _ in range(poisson_count(cfg["expected_per_chunk"])):
                x = chunk.col * CHUNK_SIZE + random.randint(0, CHUNK_SIZE)
                y = chunk.row * CHUNK_SIZE + random.randint(0, CHUNK_SIZE)
                r = random.randint(*cfg["radius_range"])
                direction = random.random() * 2 * math.pi
                self._grow_cave(cfg["shape"], x, y, r, direction, cfg["max_pockets"])

    def generate_nests_for_chunk(self, chunk, rules):
        for nest_type, cfg in rules.get("nest_rules", {}).items():
            for _ in range(poisson_count(cfg["expected_per_chunk"])):
                x = chunk.col * CHUNK_SIZE + random.randint(0, CHUNK_SIZE)
                y = chunk.row * CHUNK_SIZE + random.randint(0, CHUNK_SIZE)
                self.generate_nest(x, y, nest_type)

    def generate_surface_fissure_for_chunk(self, chunk, rules):
        """Temporary stand-in for a real surface biome -- see the
        "surface_fissure" note in BIOME_RULES."""
        cfg = rules.get("surface_fissure")
        if cfg is None or chunk.row != 0:
            return
        for _ in range(poisson_count(cfg["expected_per_chunk"])):
            x = chunk.col * CHUNK_SIZE + random.randint(0, CHUNK_SIZE)
            r = random.randint(*cfg["radius_range"])
            self.add_air_pocket_clump(x, 0, r, override=True)

    def _generate_master_cave(self):
        """The one world-spanning cave, descending from the origin all the
        way to world_height in a single call -- see generate_descending_cave.
        Runs once, the moment MASTER_CAVE_ORIGIN is generated (always the
        first chunk presented, since that's also the player's spawn chunk)."""
        self.generate_descending_cave(0, 0, 40, math.pi / 2)

    def generate_structures_for_chunk(self, chunk):
        """Step 4: place any fixed-position structure whose designated
        chunk is this one. Temporary: only the guaranteed spawn Checkpoint
        exists right now (see CHECKPOINT_CHUNK) -- future structures
        (gateways, etc.) get their own designated-chunk check here."""
        if (chunk.row, chunk.col) == CHECKPOINT_CHUNK:
            checkpoint = Checkpoint(0, CHECKPOINT_DEPTH, self.default_zooms)
            self.carve_structure_erase_rects(checkpoint)
            self.reblit_structure_on_chunks(checkpoint)

    def generate_elements_for_chunk(self, chunk, rules):
        """Step 5: attempts to place a handful of spikes (count varies but
        averages element_rules["spikes_per_chunk"]) hanging below a
        randomly-picked air pocket in this chunk, the same number of
        upside-down spikes hanging above one, and a handful of vines
        (element_rules["vines_per_chunk"]) hanging above one. Each
        successful spawn also tries to grow into a short row by attempting
        one more of the same element directly to its left and right. No-op
        for a chunk with no air pockets to anchor against."""
        # local imports -- scripts.elements.elements imports scripts.terrain
        # at module level, so importing it back at terrain.py's own module
        # level would be circular. Neither side touches the other's
        # contents until these functions actually run, so a plain top-level
        # import would likely work too, but a local import here sidesteps
        # the question entirely.
        import scripts.elements.elements as elements
        import scripts.elements.spike as spike
        import scripts.elements.vine as vine

        if not chunk.air_pockets:
            return
        element_rules = rules.get("element_rules", {})
        spikes_per_chunk = element_rules.get("spikes_per_chunk", 0)
        vines_per_chunk = element_rules.get("vines_per_chunk", 0)
        for _ in range(poisson_count(spikes_per_chunk)):
            air_pocket = random.choice(chunk.air_pockets)
            size = random.randint(spike.SIZE_MIN, spike.SIZE_MAX)
            placed = elements.attempt_place_element_adjacent_to_air_pocket(self, spike.Spike, air_pocket, size=size)
            if placed:
                elements.attempt_place_neighbors(self, placed, size=size, randomize_kwargs=lambda: {"size": random.randint(spike.SIZE_MIN, spike.SIZE_MAX)})
        for _ in range(poisson_count(spikes_per_chunk)):
            air_pocket = random.choice(chunk.air_pockets)
            size = random.randint(spike.SIZE_MIN, spike.SIZE_MAX)
            placed = elements.attempt_place_element_adjacent_to_air_pocket(self, spike.UpsideDownSpike, air_pocket, size=size)
            if placed:
                elements.attempt_place_neighbors(self, placed, size=size, randomize_kwargs=lambda: {"size": random.randint(spike.SIZE_MIN, spike.SIZE_MAX)})
        for _ in range(poisson_count(vines_per_chunk)):
            air_pocket = random.choice(chunk.air_pockets)
            size = random.randint(vine.SIZE_MIN, vine.SIZE_MAX)
            slack_factor = random.uniform(vine.SLACK_FACTOR_MIN, vine.SLACK_FACTOR_MAX)
            placed = elements.attempt_place_element_adjacent_to_air_pocket(self, vine.Vine, air_pocket, size=size, slack_factor=slack_factor)
            if placed:
                elements.attempt_place_neighbors(
                    self,
                    placed,
                    placed.width / 4,
                    count=5,
                    size=size,
                    slack_factor=slack_factor,
                    randomize_kwargs=lambda: {"size": random.randint(vine.SIZE_MIN, vine.SIZE_MAX), "slack_factor": random.uniform(vine.SLACK_FACTOR_MIN, vine.SLACK_FACTOR_MAX)},
                )

    # ------------------------------------------------------------------
    # Cave / nest generation helpers -- bounded by world_height, and by
    # _overlaps_finalized_chunk (see add_air_pocket / generate_nest /
    # generate_blob_cave / generate_skinny_cave / generate_descending_cave).
    # ------------------------------------------------------------------

    def generate_nest(self, x, y, nest_type, size=0):
        # generation works in world-integer coordinates throughout --
        # size's own randint call below requires it (a float y makes
        # `100 + (y * 150) // self.world_height` a float, which
        # random.randint rejects).
        x, y = round(x), round(y)
        y = max(max_air_pocket_radius, min(self.world_height - max_air_pocket_radius, y))
        if size == 0:
            size = random.randint(100, 100 + (y * 150) // self.world_height)
        new_nest = nest.Nest(self.default_zooms, self.world_height, nest_type, x, y, size)
        rect = new_nest.get_rect()
        for existing in self._nests_touching_rect(rect):
            if rect.colliderect(existing.get_rect()):  # redundant?
                return False
        # A nest only ever originates from its own chunk's generate_nests_for_chunk
        # roll and is never larger than one chunk, so this should be
        # structurally unreachable (see GENERATION_RADIUS_CHUNKS) -- kept as
        # a defense-in-depth check rather than assumed.
        if self._overlaps_finalized_chunk(new_nest.x, new_nest.y, new_nest.size / 2):
            return False
        for row, col in self._chunks_in_rect(new_nest.left, new_nest.top, new_nest.size, new_nest.size, pad=1):
            self.get_or_create_chunk(row, col).nests.append(new_nest)
        self.nests.append(new_nest)

        cave_size = (size * random.randint(0, 2) / 3 + 80) / 3
        if cave_size > 15:
            self.generate_skinny_cave(x, y - cave_size / 2, cave_size, -math.pi / 2, max_pockets=10, shrinking=True)
        else:
            self.add_air_pocket_clump(x, y - cave_size / 2, cave_size)
        return True

    def generate_blob_cave(self, start_x, start_y, start_r, start_dir=0, max_pockets=10):
        if max_pockets > 0 and (start_y - 2 * start_r) > 0 and start_y - start_r < self.world_height and start_r > 0 and not self._overlaps_finalized_chunk(start_x, start_y, start_r * rim_pocket_ratio):
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
        if max_pockets > 0 and (start_y - 2 * start_r) > 0 and start_y - start_r < self.world_height and start_r > 0 and not self._overlaps_finalized_chunk(start_x, start_y, start_r * rim_pocket_ratio):
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
        # No world_width wraparound needed -- unlike the old whole-world
        # generation loop, this only ever runs once from MASTER_CAVE_ORIGIN
        # (see _generate_master_cave), drifting by at most ~50 units/step,
        # so it never travels anywhere near the edge of the generation span.
        while start_y - start_r < self.world_height and not self._overlaps_finalized_chunk(start_x, start_y, start_r * rim_pocket_ratio):
            self.add_air_pocket_clump(start_x, start_y, start_r)
            if start_y > 600 and start_y < self.world_height - 600 and random.randint(1, 100) == 1:
                self.generate_nest(start_x, start_y + random.randint(-100, 100), "white")

            r = min(50, max(10, start_r + random.randint(-5, 5)))
            dir = start_dir + (random.random() - 0.5) * math.pi / 2
            x = start_x + int(math.cos(dir) * min(r, start_r) * 0.8)
            y = start_y + int(abs(math.sin(dir)) * min(r, start_r) * 0.5)
            start_x, start_y, start_r, start_dir = x, y, r, dir
            # self.generate_descending_cave(x, y, r, dir)

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

    def add_air_pocket_clump(self, x, y, radius, player_made=False, override=False, spreading=1 / 3, spawn_particles=False):
        spreading = radius * spreading
        for i in range(3):
            self.add_air_pocket(x + spreading * (random.random() * 2 - 1), y + spreading * (random.random() * 2 - 1), radius, player_made=player_made, override=override)
        if spawn_particles:
            # matches the surrounding rock instead of plain black, since this
            # path is specifically terrain being carved away (mining)
            self.particles.spawn_mining_particles(10, self._depth_color(x, y), radius * 1.5, x, y)

    def add_air_pocket(self, x, y, radius, recursions=0, player_made=False, override=False):
        # generation works in world-integer coordinates throughout -- callers
        # (add_air_pocket_clump's jitter, cave-growth's cos/sin steps) pass
        # floats, normalized here rather than at every call site.
        x, y = round(x), round(y)
        radius = min(radius, max_air_pocket_radius)

        if recursions > 3 or y < 0 or y > self.world_height:
            return False
        # No world_width bound here -- generation is on demand per chunk
        # (see present_chunk) regardless of x, so it's not confined to any
        # fixed span; world_width is just how far the player/camera are
        # nudged to stay within (see player.py, releaseTheLight.py), not a
        # generation boundary.
        # World-gen carving only -- player mining/explosions must always be
        # able to carve wherever the player actually is, finalized or not.
        # See _overlaps_finalized_chunk.
        if not player_made and self._overlaps_finalized_chunk(x, y, radius * rim_pocket_ratio):
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
            new_air_pocket = AirPocket(x, y, radius, pocket_type="circle", player_made=player_made)
        else:
            new_air_pocket = AirPocket(x, y, radius, player_made=player_made)

        touched_chunks = []
        for row, col in self._chunks_in_rect(new_air_pocket.left, new_air_pocket.top, new_air_pocket.true_r * 2, new_air_pocket.true_r * 2, pad=0):
            chunk = self.get_or_create_chunk(row, col)
            chunk.air_pockets.append(new_air_pocket)
            touched_chunks.append(chunk)

        if player_made:
            # player_made is only ever set for post-generation air carving
            # (player mining, laser splash, enemy carving) -- world-gen cave
            # carving never sets it. That's exactly what counts as an
            # "explosion" for element anchors, so check it here rather than
            # threading a separate flag through.
            for element in self._elements_touching_chunks(touched_chunks):
                if element.anchor_destroyed(new_air_pocket.x, new_air_pocket.y, new_air_pocket.r):
                    self.remove_element(element)

            # Truth data is updated above regardless. Only patch surfaces
            # for chunks that are already built; unbuilt chunks will pick
            # this pocket up naturally whenever they're eventually built.
            for chunk in touched_chunks:
                if chunk.built:
                    self._carve_chunk_incremental(chunk, new_air_pocket)

        return True

    def remove_element(self, element):
        """Drops the element from every chunk's truth data, rebuilding each
        built chunk's mask from truth (not a targeted erase -- see
        _rebuild_chunk_mask) so terrain the element happened to overlap is
        left untouched. Called when an explosion overlaps the element's
        anchor (see add_air_pocket). Spawns mining particles once at the
        element's own position."""
        rect = element.get_registration_rect()
        for row, col in self._chunks_in_rect(rect.left, rect.top, rect.width, rect.height, pad=1):
            chunk = self.chunks.get((row, col))
            if chunk is None or element not in chunk.elements:
                continue
            chunk.elements.remove(element)
            self._rebuild_chunk_mask(chunk)

        self.particles.spawn_mining_particles(10, (0, 0, 0), element.width / 2, element.x, element.y)

    # ------------------------------------------------------------------
    # Structure erase-rect carving -- see structure.Structure's own
    # docstring for what erase_rects mean.
    # ------------------------------------------------------------------

    def carve_structure_erase_rects(self, structure):
        """Carves every one of structure.get_erase_rects(): a jittered,
        corner-softened ring of air pockets (see _plan_border_pockets)
        along the rect's perimeter, sized between STRUCTURE_CARVE_MIN_R and
        STRUCTURE_CARVE_MAX_R, plus a single plain-rect carve for the
        interior (inset by STRUCTURE_CARVE_MIN_R -- the smallest possible
        inward reach of any border pocket, so there's never a gap between
        the two). The interior is a plain rect rather than more pockets:
        far cheaper, and its sharp corners never show since the border ring
        already sits on top of them."""
        for rect in structure.get_erase_rects():
            for x, y, r in _plan_border_pockets(rect):
                self.add_air_pocket(x, y, r, player_made=False, override=True)

            core = rect.inflate(-2 * STRUCTURE_CARVE_MIN_R, -2 * STRUCTURE_CARVE_MIN_R)
            if core.width > 0 and core.height > 0:
                self.carve_erase_rect(core)

    def carve_erase_rect(self, rect):
        """Carves a single plain rect out of terrain truth data (mask +
        every zoom's visuals), registering it so unbuilt chunks pick it up
        naturally whenever they're eventually built (mirrors add_air_pocket's
        own truth-data-first, patch-if-built pattern). No element-destruction
        check here, unlike a player_made air pocket -- generation always
        places structures before elements, so there's never an element to
        destroy yet; see elements.attempt_place_element, which instead
        treats erase_rects as ungrounded the same way it treats air pockets."""
        touched_chunks = []
        for row, col in self._chunks_in_rect(rect.left, rect.top, rect.width, rect.height, pad=0):
            chunk = self.get_or_create_chunk(row, col)
            chunk.erase_rects.append(rect)
            touched_chunks.append(chunk)

        for chunk in touched_chunks:
            if chunk.built:
                with chunk.lock:
                    self._carve_hitbox_rect(chunk, rect)
                    for zoom in self.default_zooms:
                        self._carve_visual_rect(chunk, rect, zoom)
                    self._reblit_solid_structures_on_chunk(chunk)

    def add_enemy(self, enemy):
        self.enemies.append(enemy)

    def add_cell(self, coords, velocities=(1, 1), charges=None, filter_type="white"):
        if validate_cell_coords(self, coords):
            new_cell = Cell(self.default_zooms, coords, velocities, charges=charges, filter_type=filter_type)
            row = math.floor(new_cell.y / CHUNK_SIZE)
            col = math.floor(new_cell.x / CHUNK_SIZE)
            new_cell.origin_chunk_key = (row, col)
            self.get_or_create_chunk(row, col).cells.append(new_cell)

    def remove_cell(self, cell):
        # can't just recompute (row, col) from cell.x/y -- cells are never migrated between
        # chunks as they move (only ever appended once, in add_cell), so a cell that's drifted
        # since being thrown is still stored under its *original* chunk (cell.origin_chunk_key),
        # not its current one.
        self.remove_interaction_display(cell.interaction_display, True)
        chunk = self.chunks.get(cell.origin_chunk_key)
        if chunk is not None and cell in chunk.cells:
            chunk.cells.remove(cell)

    def add_screen_shake(self, amount):
        self.pending_shake += amount

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

    def _get_rect_mask(self, width, height):
        key = (max(1, int(width)), max(1, int(height)))
        cached = self._rect_mask_cache.get(key)
        if cached is None:
            cached = pygame.mask.Mask(key, fill=True)
            self._rect_mask_cache[key] = cached
        return cached

    def _sample_chunk(self, wx, wy):
        # Collision is sampled from the chunk's single native-resolution
        # mask -- there's only one, not one per zoom (zoom only matters for
        # rendering, never for collision truth).
        if wy < 0:
            return False
        if wy >= self.world_height:
            return True
        col = int(math.floor(wx / CHUNK_SIZE))
        row = int(math.floor(wy / CHUNK_SIZE))
        chunk = self.chunks.get((row, col))
        if chunk is None or not chunk.built or chunk.mask is None:
            return True  # unbuilt/unknown chunk -> treat as solid (safe default)
        px = max(0, min(int(CHUNK_SIZE - 1), int(wx % CHUNK_SIZE)))
        py = max(0, min(int(CHUNK_SIZE - 1), int(wy % CHUNK_SIZE)))
        return bool(chunk.mask.get_at((px, py)))

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
        return (v_x, v_y)

    def collide_rect(self, rect):
        # world-height floor: any part of the rect at/below world_height is
        # always a collision, matching _sample_chunk's wy >= world_height -> solid
        if rect.bottom - 1 >= self.world_height:
            return (rect.left, rect.bottom - 1)

        entity_mask = self._get_rect_mask(rect.width, rect.height)
        for row, col in self._chunks_in_rect(rect.left, rect.top, rect.width, rect.height, pad=0):
            if row < 0:
                continue  # above y=0 is never solid, matching _sample_chunk's wy < 0 -> False
            chunk = self.chunks.get((row, col))
            if chunk is None or not chunk.built or chunk.mask is None:
                # unbuilt/unknown chunk -> treat as solid (safe default), matching _sample_chunk
                return (max(rect.left, col * CHUNK_SIZE), max(rect.top, row * CHUNK_SIZE))
            chunk_left, chunk_top = col * CHUNK_SIZE, row * CHUNK_SIZE
            offset = (int(rect.left - chunk_left), int(rect.top - chunk_top))
            point = chunk.mask.overlap(entity_mask, offset)
            if point is not None:
                return (chunk_left + point[0], chunk_top + point[1])
        return False

    def laser_collide_point(self, x, y):
        if self._sample_chunk_visuals(x, y):
            return True
        if self._sample_chunk(x, y):
            return True
        return any(enemy.mode != "spawn" and enemy.rect.collidepoint(x, y) for enemy in self.enemies)

    def nests_collide_rect(self, rect):
        rect_mask = self._get_rect_mask(rect.width, rect.height)
        for n in self._nests_touching_rect(rect):
            offset = (int(rect.left - n.left), int(rect.top - n.top))
            if n.hitbox_mask.overlap(rect_mask, offset) is not None:
                return True
        return False

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    # def draw_depth_background(self, surface, frame, offset_x=0, offset_y=0):
    def get_frame_color(self, size, frame, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w, h = size
        cx = left + w / zoom / 2
        cy = top + h / zoom / 2

        return self._depth_color(cx, cy)

        # def darken(c):
        #    return (int(c[0] * 0.05), int(c[1] * 0.05), int(c[2] * 0.05))
        #
        # surface.fill(darken(self._depth_color(cx, cy)))

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

    def draw_nest_gradients(self, window_size, surface, frame, lighting, hitboxes=False, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w_width, w_height = window_size
        for n in self._nests_touching_rect(pygame.Rect(left, top, w_width / zoom, w_height / zoom)):
            if n.glow > 0:
                lighting.draw_gradient(surface, frame, n.color, n.x, n.y, size=n.size, darken=n.glow / 255, offset_x=offset_x, offset_y=offset_y)

    def draw_enemy_gradients(self, window_size, surface, frame, lighting, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w_width, w_height = window_size
        screen_rect = pygame.Rect(left, top, w_width / zoom, w_height / zoom)
        for enemy in self.enemies:
            if enemy.glow > 0 and enemy.rect.colliderect(screen_rect):
                lighting.draw_gradient(surface, frame, enemy.color, enemy.x, enemy.y, size=enemy.size * 2, darken=enemy.glow / 255, offset_x=offset_x, offset_y=offset_y)

    def draw_nests(self, window_size, surface, frame, hitboxes=False, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w_width, w_height = window_size
        for n in self._nests_touching_rect(pygame.Rect(left, top, w_width / zoom, w_height / zoom)):
            if n.close(left + w_width / zoom / 2, top + w_width / zoom / 2, dist(w_width, w_height) / zoom / 2):
                n.draw(surface, frame, hitbox=hitboxes, offset_x=offset_x, offset_y=offset_y)

    def draw_structures_back(self, window_size, surface, frame, hitboxes=False, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w_width, w_height = window_size
        for s in self._structures_touching_rect(pygame.Rect(left, top, w_width / zoom, w_height / zoom)):
            if hitboxes:
                s.draw_hitbox(surface, frame, offset_x=offset_x, offset_y=offset_y)
            else:
                s.draw_back(surface, frame, offset_x=offset_x, offset_y=offset_y)

    def draw_structures_front(self, window_size, surface, frame, hitboxes=False, offset_x=0, offset_y=0):
        if hitboxes:
            return  # already drawn by draw_structures_back -- avoid drawing hitboxes twice
        left, top, zoom = frame
        w_width, w_height = window_size
        for s in self._structures_touching_rect(pygame.Rect(left, top, w_width / zoom, w_height / zoom)):
            s.draw_front(surface, frame, offset_x=offset_x, offset_y=offset_y)

    def draw_elements_back(self, window_size, surface, frame, hitboxes=False, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w_width, w_height = window_size
        for e in self._elements_touching_rect(pygame.Rect(left, top, w_width / zoom, w_height / zoom)):
            if hitboxes:
                e.draw_hitbox(surface, frame, offset_x=offset_x, offset_y=offset_y)
            else:
                e.draw_back(surface, frame, offset_x=offset_x, offset_y=offset_y)

    def draw_elements_front(self, window_size, surface, frame, hitboxes=False, offset_x=0, offset_y=0):
        if hitboxes:
            return  # already drawn by draw_elements_back -- avoid drawing hitboxes twice
        left, top, zoom = frame
        w_width, w_height = window_size
        for e in self._elements_touching_rect(pygame.Rect(left, top, w_width / zoom, w_height / zoom)):
            e.draw_front(surface, frame, offset_x=offset_x, offset_y=offset_y)

    def draw_health_bars(self, window_size, surface, frame, time=None, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w_width, w_height = window_size
        for enemy in self.enemies:
            enemy.draw_health_bar(surface, frame, time, offset_x=offset_x, offset_y=offset_y)
        for n in self._nests_touching_rect(pygame.Rect(left, top, w_width / zoom, w_height / zoom)):
            if n.close(left + w_width / zoom / 2, top + w_width / zoom / 2, dist(w_width, w_height) / zoom / 2):
                n.draw_health_bar(surface, frame, time, offset_x=offset_x, offset_y=offset_y)

    def draw_interaction_displays(self, surface, frame, time=None, offset_x=0, offset_y=0):
        self.display_manager.draw(surface, frame, time, offset_x, offset_y)

    def draw_cells(self, window_size, surface, frame, hitboxes=False, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w_width, w_height = window_size
        for cell in self._cells_in_rect(pygame.Rect(left, top, w_width / zoom, w_height / zoom)):
            cell.draw(surface, frame, hitbox=hitboxes, offset_x=offset_x, offset_y=offset_y)

    def draw_enemies(self, window_size, surface, frame, hitboxes=False, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w_width, w_height = window_size
        for enemy in self.enemies:
            if enemy.rect.colliderect(pygame.Rect(left, top, w_width / zoom, w_height / zoom)):
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
        bottom_chunk = math.floor((top + w_height / zoom) / CHUNK_SIZE)
        right_chunk = math.floor((left + w_width / zoom) / CHUNK_SIZE)

        if self._vignette_stencil is None or self._vignette_stencil_size != real_window_size:
            self._vignette_stencil = pygame.Surface(real_window_size, pygame.SRCALPHA)
            self._vignette_stencil_size = real_window_size
        self._vignette_stencil.fill((0, 0, 0, 0))

        for row in range(top_chunk, bottom_chunk + 1):
            if row < 0:
                continue
            for col in range(left_chunk, right_chunk + 1):
                dest = ((col * CHUNK_SIZE - left) * zoom + offset_x, (row * CHUNK_SIZE - top) * zoom + offset_y)
                chunk = self.chunks.get((row, col))
                if chunk is not None and chunk.built and zoom in chunk.visuals:
                    self._vignette_stencil.blit(chunk.visuals[zoom], dest)
                else:
                    # Streaming hasn't built this chunk yet -- shown by
                    # generation_state (red/yellow/green for
                    # initialized/generated/finalized) so lag in the
                    # prefetch system is obvious during testing. Does not
                    # trigger generation itself.
                    state = chunk.generation_state if chunk is not None else STATE_INITIALIZED
                    self._vignette_stencil.blit(self._get_unbuilt_placeholder(zoom, state), dest)

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
        bottom_chunk = math.floor((top + w_height / zoom) / CHUNK_SIZE)
        right_chunk = math.floor((left + w_width / zoom) / CHUNK_SIZE)

        if hitboxes:
            # Dev-only debug view (H key) -- masks aren't blittable, so
            # convert to a Surface on demand here rather than maintaining a
            # persistent debug surface for every chunk (let alone one per
            # zoom) all the time. The mask itself is always native (zoom=1)
            # resolution, so scale the converted surface to match whatever
            # zoom is currently being viewed.
            layer.fill((0, 0, 0, 0))
            side = max(1, int(CHUNK_SIZE * zoom))
            for row in range(top_chunk, bottom_chunk + 1):
                if row < 0:
                    continue
                for col in range(left_chunk, right_chunk + 1):
                    chunk = self.chunks.get((row, col))
                    if chunk is not None and chunk.built and chunk.mask is not None:
                        debug_surf = chunk.mask.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))
                        if zoom != 1:
                            debug_surf = pygame.transform.scale(debug_surf, (side, side))
                        layer.blit(debug_surf, ((col * CHUNK_SIZE - left) * zoom + offset_x, (row * CHUNK_SIZE - top) * zoom + offset_y))
        return layer
