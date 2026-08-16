#pragma once
#include <string>
#include <vector>
#include <unordered_map>
#include <unordered_set>
#include <memory>
#include <mutex>
#include <shared_mutex>
#include <atomic>
#include <thread>
#include <condition_variable>
#include <queue>
#include <chrono>
#include <cmath>
#include <array>
#include <optional>
#include "Core.h"
#include "BitMask.h"
#include "Util.h"
#include "Types.h"
#include "Frame.h"
#include "RenderTarget.h"
#include "Config.h"
#include "Particles.h"
#include "InteractionDisplay.h"

// Ported from terrain.py -- COLLISION CORE PIECE ONLY.
//
// This header/its .cpp cover: Chunk/AirPocket truth data, chunk lookup and
// spatial iteration, hitbox carving, and all collision queries
// (_sample_chunk, collide_rect, get_normal). Deliberately NOT yet covered
// (separate, later pieces): visual chunk rendering (depth-color gradient,
// rock tiling, the rim-tint carve composite), world generation (cave
// carving, nest placement), background chunk-streaming thread, and
// anything touching Cell/Nest/Enemy (not yet ported).
//
// Key architecture decisions made here:
//
//   1. ONE canonical BitMask per chunk, not per-zoom. The Python's
//      chunk.hitboxes[zoom] dict existed because collision sampling read
//      pixel color from a rendered pygame.Surface, and other zoom entries
//      existed only for the debug hitbox-overlay draw. Since our BitMask
//      collision (per the earlier roadmap discussion) is fully decoupled
//      from rendering and rendering itself now scales at draw time (GPU),
//      neither reason for per-zoom storage applies -- one CHUNK_SIZE x
//      CHUNK_SIZE bitmask per chunk is both the (only) collision source
//      of truth and, later, the source for any debug overlay.
//
//   2. Air-pocket collision shape approximated as a mathematical circle
//      (radius = trueR), not derived from the real "air_pocket_hitbox"
//      art asset. FLAGGED DEVIATION: the Python scales that asset's
//      pixels per-instance; using a perfect circle instead avoids this
//      piece depending on loaded assets/SDL at all (pure, fully
//      unit-testable logic), and should be visually near-identical given
//      the pocket type is literally named "circle". If the real asset
//      turns out to have a distinctly non-circular silhouette, swap this
//      for an asset-derived BitMask later (carving call sites don't need
//      to change, just what shape gets passed to them).
//
//   3. `Chunk` holds a std::recursive_mutex (matches the Python's
//      threading.RLock(), used because _build_chunk's helpers re-lock the
//      same chunk -- see original comment), which makes Chunk non-movable/
//      non-copyable, hence chunks are stored via unique_ptr in the map.

namespace TerrainConstants {
constexpr double kMaxAirPocketRadius = 120.0;
constexpr double kRimPocketRatio = 1.5;
constexpr int kRadiusSnap = 10;
constexpr int kRocksWorldSpan = 2 * Config::CHUNK_SIZE; // was: rocks_world_span = 2 * CHUNK_SIZE
}

// def _snap_radius(r): return int(round(r / _RADIUS_SNAP) * _RADIUS_SNAP)
inline double snapRadius(double r) {
    return std::round(r / TerrainConstants::kRadiusSnap) * TerrainConstants::kRadiusSnap;
}

// Forward declaration only -- Cell.h needs Terrain.h (complete type, for
// collision calls), so Terrain.h cannot include Cell.h back without a
// circular dependency. Chunk stores cells behind unique_ptr specifically
// so this forward declaration is sufficient here; only Terrain.cpp needs
// the complete Cell definition (via including Cell.h there).
class Cell;
// Same reasoning as Cell above: Enemy.h needs Terrain.h, so Terrain.h
// only forward-declares Enemy; Terrain owns spawned enemies (matching
// Python's c_terrain.enemies list) via unique_ptr, with Nest (once
// ported) holding non-owning raw pointers into this list -- mirrors the
// Python's shared-reference semantics (both lists reference the same
// object) without ambiguous ownership in C++.
class Enemy;
// Same reasoning again: Nest.h needs Terrain.h (Terrain& params
// throughout). Chunks own their nests via unique_ptr (matches Python's
// chunk.nests.append(new_nest)).
class Nest;

// was: knockback_circle = [pow, x, y, r, falloff] (plain list/tuple in Python)
struct KnockbackCircle {
    double power, x, y, r, falloff;
};
// was: damage_circle -- identical shape to knockback_circle in the Python
// (same [pow, x, y, r, falloff] list), used for a conceptually different
// purpose (player_damage_circles vs knockback_circles). Aliased rather
// than duplicated for clarity at call sites.
using DamageCircle = KnockbackCircle;

// was: BIOME_RULES["default"]["nest_rules"] -- keyed by nest/charge type
// (white/blue/red). Kept as a ChargeType-indexed array rather than a
// nested dict-of-dicts, since "default" is the only biome that currently
// exists (get_biome is a stub always returning "default" in the Python
// too -- preserved as a stub here, ready to extend if biomes are added).
struct NestRule {
    double minFrac, switchFrac;
    int earlyDenom, lateDenom;
};
// white: {min_frac: 0.0, switch_frac: 0.2, early_denom: 5, late_denom: 15}
// blue:  {min_frac: 0.2, switch_frac: 0.3, early_denom: 6, late_denom: 12}
// red:   {min_frac: 0.3, switch_frac: 0.4, early_denom: 6, late_denom: 12}
inline const std::array<NestRule, 3>& defaultNestRules() {
    static const std::array<NestRule, 3> rules = {{
        { 0.0, 0.2, 5, 15 }, // ChargeType::White
        { 0.2, 0.3, 6, 12 }, // ChargeType::Blue
        { 0.3, 0.4, 6, 12 }, // ChargeType::Red
    }};
    return rules;
}

// def get_biome(row, col): return "default"
inline std::string getBiome(int /*row*/, int /*col*/) { return "default"; }

// was: class AirPocket -- pure truth data (no cached scaled images here;
// see class-level note #2 above on the collision-shape approximation).
struct AirPocket {
    double x, y;
    double r;
    double trueR;
    double top, left;
    std::string type = "circle"; // only "circle" is ever constructed in the source we've seen
    bool playerMade;
    int imgIndex;    // random variant selection -- reserved for visual rendering piece, unused here
    int rimImgIndex;

    AirPocket(double x, double y, double radius, bool playerMade = false);

    // def close(self, x, y, radius): return math.dist(...) < radius + self.r
    bool close(double px, double py, double radius) const;
};

// was: class Chunk
//
// THREADING NOTE: `built` is std::atomic<bool> rather than a plain bool.
// Python's dict/attribute access is implicitly made safe across threads
// by the GIL; C++ has no equivalent, so this needed an explicit mechanism.
// The streaming worker writes `hitbox` fully, THEN stores built=true
// (release); readers (sampleChunk, hot path, no lock) load built
// (acquire) before reading hitbox -- the standard "publish once, consume
// many times, lock-free" pattern, chosen specifically because collision
// sampling happens far too often per frame to afford a mutex there. This
// deliberately does NOT protect against eviction racing a concurrent
// read -- see Terrain.h's class-level note on evictFarChunks for why
// that's an accepted, narrow tradeoff rather than an oversight.
struct Chunk {
    int row = 0, col = 0;
    std::string biome = "default";

    std::vector<AirPocket> airPockets; // truth data
    // was: chunk.structures -- deferred until those types exist (not used
    // anywhere in the source we've seen; gateways were removed per an
    // original comment, kept only for a hypothetical future structure type)
    std::vector<std::unique_ptr<Cell>> cells; // was: chunk.cells
    std::vector<Nest*> nests; // was: chunk.nests -- non-owning; a Nest
        // spans multiple chunks (its footprint) and is registered into
        // each one, matching Python's shared-object-reference semantics.
        // Terrain owns the actual Nest objects (see Terrain::nests below),
        // same ownership split already used for Enemy.

    BitMask hitbox; // CHUNK_SIZE x CHUNK_SIZE, native resolution, built lazily
    std::atomic<bool> built{false};
    double lastTouched = 0.0;

    // Visual chunk texture -- native resolution (no per-zoom storage, per
    // the earlier GPU-scaling decision). UNLIKE `hitbox`/`built`, this is
    // NOT built on the background streaming worker -- it's a GPU texture,
    // and per our established rule (GPU work stays on the main thread),
    // it's built lazily on first draw instead. See Terrain.h's class-level
    // note on visual rendering for why this splits from the Python's
    // _build_chunk, which built both together on the worker thread.
    RenderTarget visual;
    bool visualBuilt = false; // main-thread-only flag, no atomic needed (never touched off-thread)

    // Guards actual MUTATION of this chunk's data (building, incremental
    // carving, eviction) -- matches Python's threading.RLock() (reentrant,
    // since _build_chunk's helpers re-lock the same chunk). Distinct from
    // Terrain::chunksMapLock_, which guards the map STRUCTURE (which
    // chunks exist), not any individual chunk's contents.
    std::recursive_mutex lock;
};

class Terrain {
public:
    Terrain(int worldWidth, int worldHeight);
    ~Terrain();

    // was: self.knockback_circles / self._new_knockback_circles -- public
    // list access, matching the Python's direct attribute access from
    // Cell/Enemy/Player (World.tick() swaps new_* into the live list each
    // tick; that swap logic lives in World, not here, once World exists).
    std::vector<KnockbackCircle> knockbackCircles;
    std::vector<KnockbackCircle> newKnockbackCircles;
    // was: self.player_damage_circles / self._new_player_damage_circles
    std::vector<DamageCircle> playerDamageCircles;
    std::vector<DamageCircle> newPlayerDamageCircles;
    // was: self.particles = particles.Particles()
    Particles particles;
    // was: self.enemies = [] -- Terrain owns spawned enemies (see class
    // note above); Nest keeps non-owning raw pointers into this list.
    std::vector<std::unique_ptr<Enemy>> enemies;
    // was: implicit -- every chunk.nests.append(new_nest) call in Python
    // shares the same Nest object across chunks; Terrain owns the actual
    // objects here, chunks hold non-owning raw pointers (Chunk::nests).
    std::vector<std::unique_ptr<Nest>> nests;
    // was: self.display_manager = InteractionDisplayManager()
    InteractionDisplayManager displayManager;

    // was: def add_interaction_display(self, display): self.display_manager.display_in_range(display)
    void addInteractionDisplay(InteractionDisplay* display) { displayManager.displayInRange(display); }
    // was: def remove_interaction_display(self, display, complete=False)
    void removeInteractionDisplay(InteractionDisplay* display, bool complete = false) {
        displayManager.displayOutRange(display, complete);
    }

    int worldWidth() const { return worldWidth_; }
    int worldHeight() const { return worldHeight_; }

    // was: def get_or_create_chunk(self, row, col)
    Chunk& getOrCreateChunk(int row, int col);
    // was: def get_chunk_if_built(self, row, col)
    Chunk* getChunkIfBuilt(int row, int col);

    // was: def _chunks_in_rect(self, left, top, width, height, pad=1)
    std::vector<std::pair<int, int>> chunksInRect(double left, double top, double width, double height, int pad = 1) const;

    // Builds a chunk's hitbox BitMask from its truth-data air pockets.
    // TEMPORARY NAME/SCOPE: this is the hitbox-only subset of the
    // Python's _build_chunk; will be folded into the real build once
    // visual rendering (and structure/nest reblitting) exist.
    void buildChunkHitboxOnly(Chunk& chunk);

    // was: def _sample_chunk(self, wx, wy)
    bool sampleChunk(double wx, double wy) const;

    // was: def get_normal(self, x, y)
    std::pair<double, double> getNormal(double x, double y) const;

    struct CollisionResult {
        bool hit;
        double x, y;
    };
    // was: def collide_rect(self, rect) -- returns False or (x, y) in Python
    CollisionResult collideRect(const Rect& rect) const;

    // was: def nests_collide_rect(self, rect) -- REAL implementation now
    // that Nest exists (was a stub returning false during the Enemy-only
    // porting phase). Matches the Python's approach (draw all nearby
    // nests' hitboxes, then pygame.mask overlap against a query rect) but
    // via direct BitMask overlap against each nearby nest's hitbox asset
    // mask (scaled to that nest's size), no intermediate render needed.
    bool nestsCollideRect(const Rect& rect);

    // was: def laser_collide_point(self, x, y)
    // FLAGGED FOR REAL FOLLOW-UP (not a minor nuance): the Python also
    // checks _sample_chunk_visuals (the rendered visual layer's alpha),
    // and per project discussion this is INTENTIONAL, not redundant --
    // without it, a player can end up with a visually-solid-looking wall
    // the laser can't detect/mine (since our hitbox is a mathematical-
    // circle approximation of air pockets, while the visual carving uses
    // the real, possibly-irregular eraser art -- see Terrain.h note #2),
    // which is a genuinely annoying, confusing gameplay bug (looks solid,
    // acts like open air, or vice versa).
    // Currently NOT implemented: sampling the actual GPU visual texture
    // per ray-marched point would need expensive readback every laser
    // tick. SUGGESTED FIX for later: maintain a SECOND per-chunk BitMask
    // alongside `hitbox`, built from the exact same (irregular) eraser
    // shapes used for visual carving (rather than the circle
    // approximation), updated in lockstep with carveVisual. That gives
    // laserCollidePoint a second free (CPU-side, no GPU readback) sample
    // to OR against sampleChunk's result, matching the Python's two-layer
    // check without any per-frame texture readback cost. Not done yet --
    // implemented as hitbox-only for now, since it's more work than fits
    // in this pass, but this is real behavior to restore, not something
    // to leave as-is indefinitely.
    bool laserCollidePoint(double x, double y);

    // was: def _chunks_near(self, x, y, radius, pad=1) -- PUBLIC here, not
    // private-by-convention like the Python's leading underscore: Player
    // (and other modules) call this cross-module directly in the
    // original, same as _nests_near/_nests_touching_rect below, so it
    // needs real (not just conventional) external access in C++.
    std::vector<Chunk*> chunksNear(double x, double y, double radius, int pad = 1);

    // was: def _nests_near(self, x, y, radius)
    std::vector<Nest*> nestsNear(double x, double y, double radius);

    // was: def _nests_touching_rect(self, rect)
    std::vector<Nest*> nestsTouchingRect(const Rect& rect);

    // was: def add_air_pocket(self, x, y, radius, recursions=0, player_made=False, override=False)
    // `renderer` is new (not in the Python signature): when non-null AND
    // the affected chunk's visual is already built, this also carves the
    // visual live (matching the Python's _carve_chunk_incremental doing
    // both hitbox and visual together) -- needed for player-made mining
    // during actual gameplay, which runs on the main thread and has
    // renderer access. World-gen (renderer=nullptr, the default) only
    // ever touches hitboxes, which is correct: nothing has a visual built
    // yet during world generation.
    bool addAirPocket(double x, double y, double radius, int recursions = 0,
                       bool playerMade = false, bool override_ = false,
                       SDL_Renderer* renderer = nullptr);

    // was: def add_air_pocket_clump(self, x, y, radius, player_made=False, override=False, spreading=1/3)
    void addAirPocketClump(double x, double y, double radius, bool playerMade = false,
                            bool override_ = false, double spreading = 1.0 / 3.0,
                            SDL_Renderer* renderer = nullptr);

    // --- World generation (pure logic -- no rendering). ---

    // was: def generate_world(self, loading_screen=None)
    // `renderer` is new (not in Python): world-gen runs synchronously on
    // the main thread BEFORE start_streaming() is ever called (matches
    // World.__init__'s call order), so it's safe to construct real GPU-
    // backed Nest objects here directly. nullptr (the default) skips real
    // Nest construction entirely -- cave carving still happens for real,
    // matching generateNest's own scoped behavior (see its doc comment).
    void generateWorld(SDL_Renderer* renderer = nullptr);

    // was: def generate_nest(self, x, y, nest_type, size=0) -> bool
    // Now constructs and registers a REAL Nest when `renderer` is
    // non-null (closing out the earlier TODO from when Nest didn't exist
    // yet) -- does the y-clamp, size/cave_size randomization, and cave
    // carving unconditionally (all real either way), but only builds the
    // actual Nest object, registers it into every chunk in its footprint,
    // and checks nest-vs-nest rect collision (matching the Python's
    // early-return-false-on-overlap) when a renderer is provided.
    bool generateNest(double x, double y, ChargeType nestType, double size = 0.0, SDL_Renderer* renderer = nullptr);

    // was: def generate_blob_cave / generate_skinny_cave /
    // generate_descending_cave / generate_bedrock_cave
    void generateBlobCave(double startX, double startY, double startR, double startDir = 0.0, int maxPockets = 10);
    void generateSkinnyCave(double startX, double startY, double startR, double startDir = 0.0,
                             int maxPockets = 20, bool shrinking = false);
    // was: def generate_descending_cave(self, start_x, start_y, start_r, start_dir=0)
    void generateDescendingCave(double startX, double startY, double startR, double startDir = 0.0, SDL_Renderer* renderer = nullptr);
    void generateBedrockCave(double startX, double startY, double startR, double startDir = 0.0, int maxPockets = 3);

    // was: def _cells_in_rect(self, rect)
    std::vector<Cell*> cellsInRect(const Rect& rect);

    // was: def draw_nest_gradients(self, window_size, surface, frame, ...)
    // was: def draw_enemy_gradients(...) / draw_nests / draw_cells /
    // draw_enemies / draw_health_bars / draw_interaction_displays --
    // `window_size` dropped from these signatures since it's redundant
    // with Frame::viewWidth/viewHeight (same consolidation already used
    // by drawTerrain).
    void drawNestGradients(SDL_Renderer* renderer, const Frame& frame);
    void drawEnemyGradients(SDL_Renderer* renderer, const Frame& frame);
    // FLAGGED BUG PRESERVED: uses `left + viewWidth/zoom/2` for BOTH the x
    // and y center coordinate (the Python's `top + w_width/zoom/2` uses
    // window WIDTH, not height, for the y-center) -- only visibly wrong on
    // non-square windows, preserved exactly rather than "fixed".
    void drawNests(SDL_Renderer* renderer, const Frame& frame, bool hitboxes = false);
    void drawCells(SDL_Renderer* renderer, const Frame& frame, bool hitboxes = false);
    void drawEnemies(SDL_Renderer* renderer, const Frame& frame, bool hitboxes = false);
    void drawHealthBars(SDL_Renderer* renderer, const Frame& frame, int64_t timeMs = -1);
    void drawInteractionDisplays(SDL_Renderer* renderer, const Frame& frame, int64_t timeMs = -1);

    // was: def add_cell(self, coords, velocities=(1, 1))
    // `renderer` is new (not in Python) -- Cell construction needs it for
    // asset access consistency with the rest of the port; validated via
    // validateCellCoords (free function, matches Python's module-level
    // validate_cell_coords) before construction.
    void addCell(SDL_Renderer* renderer, Vec2 coords, Vec2 velocities = {1.0, 1.0});

    // was: def add_enemy(self, enemy): self.enemies.append(enemy)
    // Takes ownership (see class note on Terrain/Nest enemy ownership).
    void addEnemy(std::unique_ptr<Enemy> enemy);

    // was: c_terrain.enemies.remove(enemy) (identity-based removal, called
    // directly in nest.py/Enemy tick paths rather than through a named
    // Terrain method in the Python -- named here since C++ needs an
    // explicit way to find-and-erase by raw pointer identity from the
    // owning unique_ptr vector).
    void removeEnemy(Enemy* enemy);

    // --- Visual rendering (main-thread-only; needs SDL_Renderer/assets) ---

    // was: def init(): loads air_pocket_1/_2, _rim, _explode, hitbox,
    // rocks, gradient_vignette assets, after the display exists.
    static void init(SDL_Renderer* renderer);

    // was: def _build_chunk(self, chunk) -- VISUAL portion only (base
    // terrain render + carving every truth-data air pocket's visual hole).
    // Call once per chunk, lazily, on first draw. Requires chunk.hitbox to
    // already exist (uses truth data only, not the hitbox itself).
    void buildChunkVisual(SDL_Renderer* renderer, Chunk& chunk);

    // was: def draw_terrain(self, window_size, surface, frame, hitboxes=False, ...)
    // Renders onto whatever target is currently bound to `renderer`.
    // Lazily builds any visible chunk's visual texture that isn't built
    // yet (matches the Python's on-demand nature, just moved to the main
    // thread's draw call instead of the worker thread's build call).
    void drawTerrain(SDL_Renderer* renderer, const Frame& frame, bool hitboxes = false);

    // was: def draw_vignette(self, surface, window_size, offset_x=0, offset_y=0)
    void drawVignette(SDL_Renderer* renderer, int screenWidth, int screenHeight, int offsetX = 0, int offsetY = 0);

    // was: def get_frame_color(self, surface, frame, offset_x=0, offset_y=0)
    Color getFrameColor(const Frame& frame) const;

    // --- Chunk streaming ---------------------------------------------------

    // was: def start_streaming(self)
    // Spawns the background worker thread (idempotent -- matches the
    // Python's "if self._stream_thread is not None: return" guard).
    void startStreaming();

    // was: def update_streaming(self, player_x, player_y, build_radius_chunks=3)
    // Call once per tick from the main thread ONLY -- streamSeq_ is a
    // plain (non-atomic) counter, matching the Python's assumption that
    // only one thread (the caller of update_streaming) ever touches it;
    // the worker thread never writes it, only reads via the queue.
    void updateStreaming(double playerX, double playerY, int buildRadiusChunks = 3);

    // was: def evict_far_chunks(self, player_x, player_y, keep_radius_chunks=20)
    // KNOWN TRADEOFF, not an oversight: sampleChunk (the hot collision
    // path) intentionally does NOT take a chunk's lock before reading its
    // hitbox, for performance (see Chunk's threading note). This means
    // eviction racing a concurrent sampleChunk read on the same chunk is
    // a real, if narrow and currently-unexercised (evict_far_chunks isn't
    // called anywhere in the source we've ported), possibility. Revisit
    // if eviction becomes an active, frequently-called part of the game
    // loop rather than a currently-unused method.
    void evictFarChunks(double playerX, double playerY, int keepRadiusChunks = 20);

private:
    int worldWidth_, worldHeight_;

    // Guards the chunks_ MAP STRUCTURE (which chunks exist / lookup),
    // not any individual chunk's contents (see Chunk::lock for that).
    // shared_lock for read-only lookups (the common case, including the
    // hot sampleChunk path), unique_lock only when actually inserting.
    mutable std::shared_mutex chunksMapLock_;
    std::unordered_map<int64_t, std::unique_ptr<Chunk>> chunks_;

    // was: self._vignette_surf / self._vignette_size -- cached scaled
    // vignette texture, rebuilt only when the screen size changes.
    RenderTarget vignetteCache_;
    int vignetteCacheW_ = -1, vignetteCacheH_ = -1;

    // was: self._vignette_stencil / self._vignette_stencil_size -- terrain
    // is composited into this scratch layer first, THEN vignette-MULT is
    // applied to just this layer, THEN the whole vignetted result is
    // blitted normally onto the real target. This two-step indirection
    // matters: it keeps the vignette darkening confined to the terrain
    // layer itself, not everything already drawn underneath it (world.py
    // draws lighting/background before terrain) -- applying vignette
    // directly to the final target would incorrectly darken those too.
    RenderTarget terrainStencil_;
    int terrainStencilW_ = -1, terrainStencilH_ = -1;

    static int64_t packKey(int row, int col) {
        return (static_cast<int64_t>(row) << 32) | static_cast<uint32_t>(col);
    }

    // was: def _carve_chunk_incremental(self, chunk, air_pocket) -- hitbox
    // portion only; visual carving deferred (see header note above).
    void carveChunkIncrementalHitboxOnly(Chunk& chunk, const AirPocket& pocket);

    // was: def _carve_visual(self, chunk, air_pocket, zoom) -- the rim-glow
    // compositing (subtract eraser, then MAX+MULT rim-tint blend). Main-
    // thread-only (needs renderer/assets).
    void carveVisual(SDL_Renderer* renderer, Chunk& chunk, const AirPocket& pocket);

    // was: def _render_base_terrain(self, row, col, zoom) -- depth-color
    // gradient + tiled rock texture, at native resolution.
    RenderTarget renderBaseTerrain(SDL_Renderer* renderer, int row, int col);

    // was: def _depth_color(self, world_x, world_y)
    Color depthColor(double worldX, double worldY) const;

    // was: def _noise_val(self, x, y, scale=1)
    double noiseVal(double x, double y, double scale = 1.0) const;

    // was: def _depth_fraction(self, y): return clamp(y / world_height, 0, 1)
    double depthFraction(double y) const;

    // was: def _nest_chance(self, nest_type, depth_frac) -> Optional[int]
    // (returns a denominator, or "no chance yet" -- std::optional stands
    // in for Python's None return)
    std::optional<int> nestChance(ChargeType nestType, double depthFrac) const;

    // --- Streaming internals ---
    struct StreamQueueEntry {
        int priority;
        int64_t seq;
        int row, col;
    };
    struct StreamQueueCompare {
        // Min-heap on (priority, seq): std::priority_queue is a max-heap
        // by its comparator's convention, so this is inverted to surface
        // the smallest priority (most urgent -- closest chunk) first,
        // tie-broken by smallest seq (FIFO among equal priorities) --
        // matches Python's queue.PriorityQueue min-first tuple ordering.
        bool operator()(const StreamQueueEntry& a, const StreamQueueEntry& b) const {
            if (a.priority != b.priority) return a.priority > b.priority;
            return a.seq > b.seq;
        }
    };

    std::mutex streamQueueMutex_;
    std::condition_variable streamQueueCv_;
    std::priority_queue<StreamQueueEntry, std::vector<StreamQueueEntry>, StreamQueueCompare> streamQueue_;

    std::mutex streamLock_; // matches Python's self._stream_lock (guards streamQueuedKeys_)
    std::unordered_set<int64_t> streamQueuedKeys_;

    std::atomic<bool> streamRunning_{false};
    std::thread streamThread_;
    int64_t streamSeq_ = 0; // see updateStreaming's doc comment on single-writer assumption

    void streamWorkerLoop(); // was: def _stream_worker_loop(self)
};
