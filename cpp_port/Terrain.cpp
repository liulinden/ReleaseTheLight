#include "Terrain.h"
#include "Config.h"
#include "GlobalAssets.h"
#include "Canvas.h"
#include "BlendModes.h"
#include "Cell.h"
#include "Enemy.h"
#include "Nest.h"
#include <cmath>
#include <algorithm>
#include <iostream>
#include <vector>

// --- AirPocket -----------------------------------------------------------

// def __init__(self, x, y, radius, pocket_type="circle", player_made=False):
//     radius = _snap_radius(radius)
//     ...
AirPocket::AirPocket(double x_, double y_, double radius, bool playerMade_)
    : playerMade(playerMade_) {
    radius = snapRadius(radius);
    x = x_;
    y = y_;
    r = radius;
    trueR = radius * TerrainConstants::kRimPocketRatio;
    top = y - trueR;
    left = x - trueR;
    // Variant counts hardcoded to match the known asset set (2 circle
    // images, 1 rim, 1 explode) -- these indices are only consumed by
    // visual rendering, not yet implemented, so this is a placeholder
    // pending that piece; not asset-driven yet since this piece has no
    // asset dependency by design (see Terrain.h note #2).
    imgIndex = Util::randint(0, 1);
    rimImgIndex = Util::randint(0, 0);
}

bool AirPocket::close(double px, double py, double radius) const {
    return Util::dist(x - px, y - py) < radius + r;
}

// --- Terrain ---------------------------------------------------------------

Terrain::Terrain(int worldWidth, int worldHeight)
    : worldWidth_(worldWidth), worldHeight_(worldHeight) {}

Terrain::~Terrain() {
    if (streamRunning_) {
        streamRunning_ = false;
        streamQueueCv_.notify_all();
        if (streamThread_.joinable()) streamThread_.join();
    }
}

Chunk& Terrain::getOrCreateChunk(int row, int col) {
    int64_t key = packKey(row, col);
    {
        std::shared_lock<std::shared_mutex> readLock(chunksMapLock_);
        auto it = chunks_.find(key);
        if (it != chunks_.end()) return *it->second;
    }
    std::unique_lock<std::shared_mutex> writeLock(chunksMapLock_);
    // Re-check: another thread may have inserted this key between our
    // read-lock release above and acquiring the write lock here.
    auto it = chunks_.find(key);
    if (it != chunks_.end()) return *it->second;

    auto chunk = std::make_unique<Chunk>();
    chunk->row = row;
    chunk->col = col;
    chunk->biome = getBiome(row, col);
    Chunk& ref = *chunk;
    chunks_[key] = std::move(chunk);
    return ref;
}

Chunk* Terrain::getChunkIfBuilt(int row, int col) {
    std::shared_lock<std::shared_mutex> lock(chunksMapLock_);
    auto it = chunks_.find(packKey(row, col));
    if (it != chunks_.end() && it->second->built.load(std::memory_order_acquire)) return it->second.get();
    return nullptr;
}

// def _chunks_in_rect(self, left, top, width, height, pad=1):
//     col_start = floor(left/CHUNK_SIZE) - pad
//     col_end = floor((left+width)/CHUNK_SIZE) + pad
//     row_start = max(0, floor(top/CHUNK_SIZE) - pad)
//     row_end = floor((top+height)/CHUNK_SIZE) + pad
//     for row in row_start..row_end: for col in col_start..col_end: yield row, col
std::vector<std::pair<int, int>> Terrain::chunksInRect(double left, double top, double width, double height, int pad) const {
    int colStart = static_cast<int>(std::floor(left / Config::CHUNK_SIZE)) - pad;
    int colEnd = static_cast<int>(std::floor((left + width) / Config::CHUNK_SIZE)) + pad;
    int rowStart = std::max(0, static_cast<int>(std::floor(top / Config::CHUNK_SIZE)) - pad);
    int rowEnd = static_cast<int>(std::floor((top + height) / Config::CHUNK_SIZE)) + pad;

    std::vector<std::pair<int, int>> result;
    for (int row = rowStart; row <= rowEnd; ++row) {
        for (int col = colStart; col <= colEnd; ++col) {
            result.emplace_back(row, col);
        }
    }
    return result;
}

// def _chunks_near(self, x, y, radius, pad=1): ...
std::vector<Chunk*> Terrain::chunksNear(double x, double y, double radius, int pad) {
    int rowC = static_cast<int>(std::floor(y / Config::CHUNK_SIZE));
    int colC = static_cast<int>(std::floor(x / Config::CHUNK_SIZE));
    int chunkRadius = static_cast<int>(std::ceil(radius / Config::CHUNK_SIZE)) + pad;

    std::vector<Chunk*> result;
    std::shared_lock<std::shared_mutex> mapLock(chunksMapLock_);
    for (int dr = -chunkRadius; dr <= chunkRadius; ++dr) {
        for (int dc = -chunkRadius; dc <= chunkRadius; ++dc) {
            auto it = chunks_.find(packKey(rowC + dr, colC + dc));
            if (it != chunks_.end()) result.push_back(it->second.get());
        }
    }
    return result;
}

// def _nests_near(self, x, y, radius): ...
std::vector<Nest*> Terrain::nestsNear(double x, double y, double radius) {
    std::vector<Nest*> result;
    for (Chunk* chunk : chunksNear(x, y, radius, 0)) {
        std::lock_guard<std::recursive_mutex> lock(chunk->lock);
        for (Nest* n : chunk->nests) {
            // was: dedupe by id(n) across overlapping chunks -- a nest can
            // be registered in multiple chunks (its footprint), and the
            // Python dedupes via a `seen` set keyed by object identity.
            // Same dedup here, by raw pointer.
            if (std::find(result.begin(), result.end(), n) == result.end()) {
                result.push_back(n);
            }
        }
    }
    return result;
}

// def _nests_touching_rect(self, rect): ...
std::vector<Nest*> Terrain::nestsTouchingRect(const Rect& rect) {
    std::vector<Nest*> result;
    for (auto& rc : chunksInRect(rect.x, rect.y, rect.w, rect.h, 0)) {
        std::shared_lock<std::shared_mutex> mapLock(chunksMapLock_);
        auto it = chunks_.find(packKey(rc.first, rc.second));
        if (it == chunks_.end()) continue;
        Chunk* chunk = it->second.get();
        mapLock.unlock();
        std::lock_guard<std::recursive_mutex> lock(chunk->lock);
        for (Nest* n : chunk->nests) {
            if (std::find(result.begin(), result.end(), n) == result.end()) {
                result.push_back(n);
            }
        }
    }
    return result;
}

// def nests_collide_rect(self, rect): mask-vs-mask overlap against each
// nearby nest's hitbox asset mask (scaled to that nest's size), matching
// the Python's render-then-pygame.mask-overlap approach but via direct
// BitMask ops -- no intermediate render needed.
bool Terrain::nestsCollideRect(const Rect& rect) {
    for (Nest* nest : nestsTouchingRect(rect)) {
        if (nest->variantIdForCollision() < 0) continue; // Sun nest with no variant -- skip, can't sample a hitbox that doesn't exist
        const Asset& hitboxAsset = GlobalAssets::getAsset(
            "nest_" + std::to_string(nest->variantIdForCollision()) + "_hitbox");
        BitMask scaled = hitboxAsset.mask.scaledTo(static_cast<int>(nest->size), static_cast<int>(nest->size));

        BitMask rectMask(rect.w, rect.h);
        rectMask.fill(true);
        int ox = static_cast<int>(nest->left - rect.x);
        int oy = static_cast<int>(nest->top - rect.y);
        if (rectMask.overlaps(scaled, ox, oy)) return true;
    }
    return false;
}

// def laser_collide_point(self, x, y): -- see Terrain.h for the flagged
// visual-layer-sampling simplification.
bool Terrain::laserCollidePoint(double x, double y) {
    if (sampleChunk(x, y)) return true;
    for (auto& enemy : enemies) {
        // was: enemy.mode != "Spawn" (capital S) -- Enemy's mode is always
        // lowercase ("spawn"/"walk"/"attack"), so this comparison NEVER
        // filters anything out in the original (a case-mismatch bug,
        // same pattern as _enemy.py's "Attack" hitbox-debug bug).
        // Preserved as always-true here too, matching the observable
        // behavior exactly.
        Rect r = enemy->rectForCollision();
        if (r.collidePoint(static_cast<int>(x), static_cast<int>(y))) return true;
    }
    return false;
}


void Terrain::buildChunkHitboxOnly(Chunk& chunk) {
    std::lock_guard<std::recursive_mutex> lock(chunk.lock);
    if (chunk.built.load(std::memory_order_acquire)) return;

    BitMask newHitbox(Config::CHUNK_SIZE, Config::CHUNK_SIZE);
    newHitbox.fill(true); // "solid" fill_mode: starts solid, air pockets carve OUT

    double left = chunk.col * Config::CHUNK_SIZE;
    double top = chunk.row * Config::CHUNK_SIZE;
    for (auto& pocket : chunk.airPockets) {
        newHitbox.subtractCircle(pocket.x - left, pocket.y - top, pocket.trueR);
    }

    chunk.hitbox = std::move(newHitbox);
    chunk.built.store(true, std::memory_order_release); // publish -- see Chunk's threading note
}

void Terrain::carveChunkIncrementalHitboxOnly(Chunk& chunk, const AirPocket& pocket) {
    std::lock_guard<std::recursive_mutex> lock(chunk.lock);
    double left = chunk.col * Config::CHUNK_SIZE;
    double top = chunk.row * Config::CHUNK_SIZE;
    chunk.hitbox.subtractCircle(pocket.x - left, pocket.y - top, pocket.r);
}

// def _sample_chunk(self, wx, wy):
//     if wy < 0: return False
//     if wy >= self.world_height: return True
//     col = floor(wx/CHUNK_SIZE); row = floor(wy/CHUNK_SIZE)
//     chunk = chunks.get((row,col))
//     if chunk is None or not chunk.built or 1 not in chunk.hitboxes: return True
//     px = clamp(int(wx % CHUNK_SIZE), 0, CHUNK_SIZE-1)
//     py = clamp(int(wy % CHUNK_SIZE), 0, CHUNK_SIZE-1)
//     return chunk.hitboxes[1].get_at((px,py))[0] > 128
// NOTE: uses Util::pyMod, not raw fmod/`%` -- wx/wy can be negative (the
// world extends infinitely in x per the original's comments), and Python's
// `%` always returns non-negative for a positive divisor while C++'s does
// not. Using naive modulo here would produce out-of-range/wrong indices
// for negative world coordinates.
bool Terrain::sampleChunk(double wx, double wy) const {
    if (wy < 0) return false;
    if (wy >= worldHeight_) return true;

    int col = static_cast<int>(std::floor(wx / Config::CHUNK_SIZE));
    int row = static_cast<int>(std::floor(wy / Config::CHUNK_SIZE));

    Chunk* chunk = nullptr;
    {
        // Map-structure lock held only for the lookup itself -- the Chunk
        // object it points to is stable (owned by unique_ptr, never moved
        // or freed while the map entry exists), so it's safe to keep using
        // `chunk` after releasing this lock. See Chunk's threading note
        // for why `built`/`hitbox` access below doesn't also need this
        // lock (or the chunk's own lock) held.
        std::shared_lock<std::shared_mutex> mapLock(chunksMapLock_);
        auto it = chunks_.find(packKey(row, col));
        if (it != chunks_.end()) chunk = it->second.get();
    }
    if (chunk == nullptr || !chunk->built.load(std::memory_order_acquire)) {
        return true; // unbuilt/unknown -> solid, safe default
    }

    int px = std::clamp(static_cast<int>(Util::pyMod(wx, static_cast<double>(Config::CHUNK_SIZE))), 0, Config::CHUNK_SIZE - 1);
    int py = std::clamp(static_cast<int>(Util::pyMod(wy, static_cast<double>(Config::CHUNK_SIZE))), 0, Config::CHUNK_SIZE - 1);

    return chunk->hitbox.get(px, py);
}

// def get_normal(self, x, y):
//     v_x = self._sample_chunk(x - 1, y) - self._sample_chunk(x + 1, y)
//     v_y = self._sample_chunk(x, y - 1) - self._sample_chunk(x, y + 1)
//     if v_x == v_y == 0:
//         tl, tr, bl, br = sample(x-1,y-1), sample(x-1,y+1), sample(x+1,y-1), sample(x+1,y+1)
//         v_x = (tr or br) - (tl or bl)
//         v_y = (tl or tr) - (bl or br)
//     if v_x == v_y == 0:
//         ...ASCII debug print...
//     return (v_x, v_y)
std::pair<double, double> Terrain::getNormal(double x, double y) const {
    double vx = static_cast<double>(sampleChunk(x - 1, y)) - static_cast<double>(sampleChunk(x + 1, y));
    double vy = static_cast<double>(sampleChunk(x, y - 1)) - static_cast<double>(sampleChunk(x, y + 1));

    if (vx == 0 && vy == 0) {
        bool tl = sampleChunk(x - 1, y - 1);
        bool tr = sampleChunk(x - 1, y + 1);
        bool bl = sampleChunk(x + 1, y - 1);
        bool br = sampleChunk(x + 1, y + 1);
        vx = static_cast<double>(tr || br) - static_cast<double>(tl || bl);
        vy = static_cast<double>(tl || tr) - static_cast<double>(bl || br);
    }

    if (vx == 0 && vy == 0) {
        int ix = static_cast<int>(x), iy = static_cast<int>(y);
        for (int i = ix - 8; i <= ix + 8; ++i) {
            std::string row;
            for (int j = iy - 8; j <= iy + 8; ++j) {
                row += sampleChunk(i, j) ? "X " : "_ ";
            }
            std::cout << row << "\n";
        }
    }

    return { vx, vy };
}

// def collide_rect(self, rect):
//     l, r, t, b = float(rect.left), float(rect.right-1), float(rect.top), float(rect.bottom-1)
//     step = 1
//     for i in range(floor(b-t)):
//         y = t+step*i
//         if sample(l,y): return (l,y)
//         if sample(r,y): return (r,y)
//     for i in range(floor(r-l)):
//         x = l+step*i
//         if sample(x,b): return (x,b)
//         if sample(x,t): return (x,t)
//     return False
Terrain::CollisionResult Terrain::collideRect(const Rect& rect) const {
    double l = static_cast<double>(rect.left());
    double r = static_cast<double>(rect.right() - 1);
    double t = static_cast<double>(rect.top());
    double b = static_cast<double>(rect.bottom() - 1);
    int step = 1;

    int yIterations = static_cast<int>(std::floor(b - t));
    for (int i = 0; i < yIterations; ++i) {
        double y = t + step * i;
        if (sampleChunk(l, y)) return { true, l, y };
        if (sampleChunk(r, y)) return { true, r, y };
    }
    int xIterations = static_cast<int>(std::floor(r - l));
    for (int i = 0; i < xIterations; ++i) {
        double x = l + step * i;
        if (sampleChunk(x, b)) return { true, x, b };
        if (sampleChunk(x, t)) return { true, x, t };
    }
    return { false, 0.0, 0.0 };
}

// def _cells_in_rect(self, rect): ...
std::vector<Cell*> Terrain::cellsInRect(const Rect& rect) {
    std::vector<Cell*> result;
    for (auto& rc : chunksInRect(rect.x, rect.y, rect.w, rect.h, 0)) {
        std::shared_lock<std::shared_mutex> mapLock(chunksMapLock_);
        auto it = chunks_.find(packKey(rc.first, rc.second));
        if (it == chunks_.end()) continue;
        Chunk* chunk = it->second.get();
        mapLock.unlock();
        std::lock_guard<std::recursive_mutex> lock(chunk->lock);
        for (auto& c : chunk->cells) {
            if (std::find(result.begin(), result.end(), c.get()) == result.end()) {
                result.push_back(c.get());
            }
        }
    }
    return result;
}

// def draw_nest_gradients(self, window_size, surface, frame, ...): ...
void Terrain::drawNestGradients(SDL_Renderer* renderer, const Frame& frame) {
    Rect viewRect{
        static_cast<int>(frame.left), static_cast<int>(frame.top),
        static_cast<int>(frame.viewWidth / frame.zoom), static_cast<int>(frame.viewHeight / frame.zoom)
    };
    for (Nest* n : nestsTouchingRect(viewRect)) {
        n->drawGradient(renderer, frame);
    }
}

void Terrain::drawEnemyGradients(SDL_Renderer* renderer, const Frame& frame) {
    for (auto& enemy : enemies) {
        enemy->drawGradient(renderer, frame);
    }
}

// def draw_nests(self, window_size, surface, frame, ...): -- see Terrain.h
// for the preserved width/height mixup bug in the close() center point.
void Terrain::drawNests(SDL_Renderer* renderer, const Frame& frame, bool hitboxes) {
    Rect viewRect{
        static_cast<int>(frame.left), static_cast<int>(frame.top),
        static_cast<int>(frame.viewWidth / frame.zoom), static_cast<int>(frame.viewHeight / frame.zoom)
    };
    double centerX = frame.left + frame.viewWidth / frame.zoom / 2.0;
    double centerY = frame.top + frame.viewWidth / frame.zoom / 2.0; // was: w_width used for BOTH -- preserved bug
    double closeRadius = Util::dist(frame.viewWidth, frame.viewHeight) / frame.zoom / 2.0;
    for (Nest* n : nestsTouchingRect(viewRect)) {
        if (n->close(centerX, centerY, closeRadius)) {
            n->draw(renderer, frame, hitboxes);
        }
    }
}

void Terrain::drawCells(SDL_Renderer* renderer, const Frame& frame, bool hitboxes) {
    Rect viewRect{
        static_cast<int>(frame.left), static_cast<int>(frame.top),
        static_cast<int>(frame.viewWidth / frame.zoom), static_cast<int>(frame.viewHeight / frame.zoom)
    };
    for (Cell* c : cellsInRect(viewRect)) {
        c->draw(renderer, frame, hitboxes);
    }
}

void Terrain::drawEnemies(SDL_Renderer* renderer, const Frame& frame, bool hitboxes) {
    Rect viewRect{
        static_cast<int>(frame.left), static_cast<int>(frame.top),
        static_cast<int>(frame.viewWidth / frame.zoom), static_cast<int>(frame.viewHeight / frame.zoom)
    };
    for (auto& enemy : enemies) {
        if (enemy->rectForCollision().collideRect(viewRect)) {
            enemy->draw(renderer, frame, hitboxes);
        }
    }
}

void Terrain::drawHealthBars(SDL_Renderer* renderer, const Frame& frame, int64_t timeMs) {
    Rect viewRect{
        static_cast<int>(frame.left), static_cast<int>(frame.top),
        static_cast<int>(frame.viewWidth / frame.zoom), static_cast<int>(frame.viewHeight / frame.zoom)
    };
    for (auto& enemy : enemies) {
        enemy->drawHealthBar(renderer, frame, timeMs);
    }
    double centerX = frame.left + frame.viewWidth / frame.zoom / 2.0;
    double centerY = frame.top + frame.viewWidth / frame.zoom / 2.0; // same preserved bug as drawNests
    double closeRadius = Util::dist(frame.viewWidth, frame.viewHeight) / frame.zoom / 2.0;
    for (Nest* n : nestsTouchingRect(viewRect)) {
        if (n->close(centerX, centerY, closeRadius)) {
            n->drawHealthBar(renderer, frame, timeMs);
        }
    }
}

void Terrain::drawInteractionDisplays(SDL_Renderer* renderer, const Frame& frame, int64_t timeMs) {
    displayManager.draw(renderer, frame, timeMs);
}

// def add_air_pocket(self, x, y, radius, recursions=0, player_made=False, override=False): ...
bool Terrain::addAirPocket(double x, double y, double radius, int recursions, bool playerMade, bool override_, SDL_Renderer* renderer) {
    radius = std::min(radius, TerrainConstants::kMaxAirPocketRadius);

    if (recursions > 3 || y < 0 || y > worldHeight_) return false;
    if (!playerMade && (x + radius > worldWidth_ || x - radius < 0)) return false;

    int baseRow = static_cast<int>(std::floor(y / Config::CHUNK_SIZE));
    int baseCol = static_cast<int>(std::floor(x / Config::CHUNK_SIZE));

    if (!playerMade && !override_) {
        for (int dRow = -1; dRow <= 1; ++dRow) {
            for (int dCol = -1; dCol <= 1; ++dCol) {
                Chunk* chunk = nullptr;
                {
                    std::shared_lock<std::shared_mutex> mapLock(chunksMapLock_);
                    auto it = chunks_.find(packKey(baseRow + dRow, baseCol + dCol));
                    if (it != chunks_.end()) chunk = it->second.get();
                }
                if (chunk == nullptr) continue;

                // Fixed per ThreadSanitizer's lock-order-inversion finding:
                // determine the outcome while holding this chunk's lock,
                // then RELEASE it before any recursive addAirPocket call
                // below -- recursing while still holding a chunk lock
                // meant different recursion paths could acquire chunk
                // locks in different relative orders, a genuine (if
                // currently unexercised, since world-gen is single-
                // threaded today) deadlock risk. No lock needs to be held
                // during the recursive call itself.
                bool reject = false;
                bool merge = false;
                double mergeX = 0.0, mergeY = 0.0, mergeR = 0.0;
                {
                    std::lock_guard<std::recursive_mutex> pocketReadLock(chunk->lock);
                    for (auto& pocket : chunk->airPockets) {
                        double dx = pocket.x - x, dy = pocket.y - y;
                        double combined = pocket.r + radius + 10;
                        if (std::abs(dx) > combined || std::abs(dy) > combined) continue;
                        double d = std::sqrt(dx * dx + dy * dy);
                        if (d < radius / 4.0) { reject = true; break; }
                        if (pocket.r + radius < d && d < pocket.r + radius + 10) {
                            merge = true;
                            mergeX = (pocket.x + x) / 2.0;
                            mergeY = (pocket.y + y) / 2.0;
                            mergeR = (pocket.r + radius) / 2.0;
                            break;
                        }
                    }
                } // pocketReadLock released here, before any recursion
                if (reject) return false;
                if (merge) return addAirPocket(mergeX, mergeY, mergeR, recursions + 1, playerMade, override_, renderer);
            }
        }
    }

    // NOTE PRESERVED FAITHFULLY: the Python branches on a random draw here
    // (`(not player_made) and random.randint(1,10)==1`) to pick between
    // two AirPocket constructions that are actually IDENTICAL (both
    // default to pocket_type="circle" either way) -- this looks like
    // vestigial logic from when multiple pocket types existed. Preserved
    // exactly, including the "wasted" random draw (matters only in that
    // it consumes an RNG value, shifting what subsequent random calls
    // produce -- inconsequential since nothing in this codebase relies on
    // exact RNG reproducibility, per the earlier RNG design note).
    if (!playerMade) {
        Util::randint(1, 10); // consumed for parity with the Python's dead branch; result unused
    }
    AirPocket newPocket(x, y, radius, playerMade);

    std::vector<Chunk*> touchedChunks;
    for (auto& rc : chunksInRect(newPocket.left, newPocket.top, newPocket.trueR * 2, newPocket.trueR * 2, 0)) {
        Chunk& chunk = getOrCreateChunk(rc.first, rc.second);
        {
            // See conversation notes: unlike Python (safe here only via
            // the GIL), std::vector::push_back racing a concurrent
            // iteration (buildChunkHitboxOnly, on the streaming worker
            // thread) is a real crash risk, not just a benign timing
            // race -- needs this chunk's own lock, which the Python
            // didn't need here.
            std::lock_guard<std::recursive_mutex> lock(chunk.lock);
            chunk.airPockets.push_back(newPocket);
        }
        touchedChunks.push_back(&chunk);
    }

    if (playerMade) {
        for (Chunk* chunk : touchedChunks) {
            if (chunk->built.load(std::memory_order_acquire)) {
                carveChunkIncrementalHitboxOnly(*chunk, newPocket);
            }
            // Live visual carving for player-made pockets (mining), matching
            // the Python's _carve_chunk_incremental doing hitbox+visual
            // together. Only possible here (not during world-gen) since
            // this needs a renderer -- see addAirPocket's header doc.
            if (renderer != nullptr && chunk->visualBuilt) {
                std::lock_guard<std::recursive_mutex> lock(chunk->lock);
                carveVisual(renderer, *chunk, newPocket);
            }
        }
    }

    return true;
}

// def add_air_pocket_clump(self, x, y, radius, player_made=False, override=False, spreading=1/3):
//     spreading = radius * spreading
//     for i in range(3):
//         self.add_air_pocket(x + spreading*(random()*2-1), y + spreading*(random()*2-1), radius, ...)
void Terrain::addAirPocketClump(double x, double y, double radius, bool playerMade, bool override_, double spreading, SDL_Renderer* renderer) {
    double spread = radius * spreading;
    for (int i = 0; i < 3; ++i) {
        addAirPocket(x + spread * (Util::randomDouble() * 2 - 1),
                     y + spread * (Util::randomDouble() * 2 - 1),
                     radius, 0, playerMade, override_, renderer);
    }
}

// def add_cell(self, coords, velocities=(1, 1)):
//     if validate_cell_coords(self, coords):
//         new_cell = Cell(self.default_zooms, coords, velocities)
//         row = floor(new_cell.y / CHUNK_SIZE); col = floor(new_cell.x / CHUNK_SIZE)
//         self.get_or_create_chunk(row, col).cells.append(new_cell)
void Terrain::addCell(SDL_Renderer* renderer, Vec2 coords, Vec2 velocities) {
    if (!validateCellCoords(*this, coords)) return;
    auto newCell = std::make_unique<Cell>(renderer, coords, velocities);
    int row = static_cast<int>(std::floor(coords.y / Config::CHUNK_SIZE));
    int col = static_cast<int>(std::floor(coords.x / Config::CHUNK_SIZE));
    Chunk& chunk = getOrCreateChunk(row, col);
    std::lock_guard<std::recursive_mutex> lock(chunk.lock);
    chunk.cells.push_back(std::move(newCell));
}

void Terrain::addEnemy(std::unique_ptr<Enemy> enemy) {
    enemies.push_back(std::move(enemy));
}

void Terrain::removeEnemy(Enemy* enemy) {
    enemies.erase(
        std::remove_if(enemies.begin(), enemies.end(),
                        [&](const std::unique_ptr<Enemy>& e) { return e.get() == enemy; }),
        enemies.end());
}

// --- World generation (pure logic; nest CREATION deferred -- see header) --

double Terrain::depthFraction(double y) const {
    return std::max(0.0, std::min(1.0, y / worldHeight_));
}

// def _nest_chance(self, nest_type, depth_frac):
//     rules = BIOME_RULES["default"]["nest_rules"][nest_type]
//     if depth_frac < rules["min_frac"]: return None
//     return rules["early_denom"] if depth_frac < rules["switch_frac"] else rules["late_denom"]
std::optional<int> Terrain::nestChance(ChargeType nestType, double depthFrac) const {
    const NestRule& rule = defaultNestRules()[static_cast<int>(nestType)];
    if (depthFrac < rule.minFrac) return std::nullopt;
    return (depthFrac < rule.switchFrac) ? rule.earlyDenom : rule.lateDenom;
}

// def generate_nest(self, x, y, nest_type, size=0): ...
bool Terrain::generateNest(double x, double y, ChargeType nestType, double size, SDL_Renderer* renderer) {
    y = std::max(TerrainConstants::kMaxAirPocketRadius,
                  std::min(static_cast<double>(worldHeight_) - TerrainConstants::kMaxAirPocketRadius, y));
    if (size == 0.0) {
        int upper = 100 + static_cast<int>(std::floor(y * 150.0 / worldHeight_));
        size = Util::randint(100, upper);
    }

    if (renderer != nullptr) {
        NestType nt = static_cast<NestType>(nestType); // ChargeType/NestType share White=0,Blue=1,Red=2 ordering by design
        auto newNest = std::make_unique<Nest>(renderer, nt, static_cast<double>(worldHeight_), x, y, size);
        Rect rect = newNest->getRect();

        for (Nest* existing : nestsTouchingRect(rect)) {
            if (rect.collideRect(existing->getRect())) {
                return false; // matches Python's early return on overlap
            }
        }

        Nest* nestPtr = newNest.get();
        for (auto& rc : chunksInRect(newNest->left, newNest->top, newNest->size, newNest->size, 1)) {
            Chunk& chunk = getOrCreateChunk(rc.first, rc.second);
            std::lock_guard<std::recursive_mutex> lock(chunk.lock);
            chunk.nests.push_back(nestPtr); // non-owning; every touched chunk references the same Nest
        }
        // Terrain takes sole ownership (matches Python's Terrain-level
        // reference-counted lifetime -- the Nest lives as long as ANY
        // chunk still points to it there; here it simply lives as long as
        // Terrain does, which is at least as long as any chunk needs it).
        // No lock here: nests/enemies (like knockbackCircles/particles)
        // are only ever mutated from the main thread in this design
        // (world-gen and gameplay both run there; only chunk building
        // happens on the background worker) -- consistent with those
        // other Terrain members already being unprotected.
        nests.push_back(std::move(newNest));
    }
    // else (renderer == nullptr, e.g. no display context available): skip
    // real Nest construction entirely, matching the earlier temporary
    // scope -- cave carving below still happens unconditionally either way.

    double caveSize = (size * Util::randint(0, 2) / 3.0 + 80.0) / 3.0;
    if (caveSize > 15.0) {
        generateSkinnyCave(x, y - caveSize / 2.0, caveSize, -M_PI / 2.0, 10, true);
    } else {
        addAirPocketClump(x, y - caveSize / 2.0, caveSize);
    }
    return true;
}

// def generate_blob_cave(self, start_x, start_y, start_r, start_dir=0, max_pockets=10): ...
void Terrain::generateBlobCave(double startX, double startY, double startR, double startDir, int maxPockets) {
    if (maxPockets > 0 && (startY - 2 * startR) > 0 && startY - startR < worldHeight_ && startR > 0) {
        addAirPocketClump(startX, startY, startR);
        for (int i = 0; i < 2; ++i) {
            double r = startR + (Util::randomDouble() - 0.6) * 20.0;
            double dir = startDir + (Util::randomDouble() - 0.5) * M_PI;
            double x = startX + std::cos(dir) * std::min(r, startR) * 0.8;
            double y = startY + std::sin(dir) * std::min(r, startR) * 0.8 * 0.2;
            generateBlobCave(x, y, r, dir, maxPockets - 1);
            if (Util::randint(1, 15) > 1) break;
        }
    }
}

// def generate_skinny_cave(self, start_x, start_y, start_r, start_dir=0, max_pockets=20, shrinking=False): ...
void Terrain::generateSkinnyCave(double startX, double startY, double startR, double startDir, int maxPockets, bool shrinking) {
    if (maxPockets > 0 && (startY - 2 * startR) > 0 && startY - startR < worldHeight_ && startR > 0) {
        addAirPocketClump(startX, startY, startR);
        for (int i = 0; i < 2; ++i) {
            double r = startR + (Util::randomDouble() - 0.6) * 5.0;
            if (shrinking) {
                r = startR - Util::randomDouble() * 2.0;
            }
            double dir = startDir + (Util::randomDouble() - 0.5) * M_PI / 2.0;
            double x = startX + std::cos(dir) * std::min(r, startR) * 0.8;
            double y = startY + std::sin(dir) * std::min(r, startR) * 0.8 * 0.8;
            generateSkinnyCave(x, y, r, dir, maxPockets - 1, shrinking);
            if (Util::randint(1, 30) > 1) break;
        }
    }
}

// def generate_descending_cave(self, start_x, start_y, start_r, start_dir=0):
// NOTE: uses math.fmod (C-style, sign-of-dividend), NOT the `%` operator
// -- std::fmod is the correct direct match here, unlike ChargeDisplay's
// filter-angle wrapping which needed Util::pyMod. Different original
// functions, different semantics; not a contradiction.
void Terrain::generateDescendingCave(double startX, double startY, double startR, double startDir, SDL_Renderer* renderer) {
    while (startY - startR < worldHeight_) {
        double boundedX = std::abs(std::fmod(startX, 2.0 * worldWidth_) - worldWidth_);
        addAirPocketClump(boundedX, startY, startR);
        if (startY > 600 && startY < worldHeight_ - 600 && Util::randint(1, 100) == 1) {
            generateNest(boundedX, startY + Util::randint(-100, 100), ChargeType::White, 0.0, renderer);
        }

        double r = std::min(50.0, std::max(10.0, startR + Util::randint(-5, 5)));
        double dir = startDir + (Util::randomDouble() - 0.5) * M_PI / 2.0;
        double x = startX + static_cast<int>(std::cos(dir) * std::min(r, startR) * 0.8);
        double y = startY + static_cast<int>(std::abs(std::sin(dir)) * std::min(r, startR) * 0.5);
        startX = x; startY = y; startR = r; startDir = dir;
    }
}

// def generate_bedrock_cave(self, start_x, start_y, start_r, start_dir=0, max_pockets=3): ...
void Terrain::generateBedrockCave(double startX, double startY, double startR, double startDir, int maxPockets) {
    if (maxPockets > 0 && (startY - 2 * startR) > 0 && startY - startR < worldHeight_ && startR > 0) {
        addAirPocketClump(startX, startY, startR);
        for (int i = 0; i < 2; ++i) {
            double r = startR + (Util::randomDouble() - 0.6) * 20.0;
            double dir = startDir + (Util::randomDouble() - 0.5) * M_PI / 2.0;
            double x = startX + std::cos(dir) * std::min(r, startR) * 0.7;
            double y = startY + std::sin(dir) * std::min(r, startR) * 0.7 * 0.5;
            generateBedrockCave(x, y, r, dir, maxPockets - 1);
            if (Util::randint(1, 30) > 1) break;
        }
    }
}

// def generate_world(self, loading_screen=None): -- loading_screen
// progress reporting omitted (orthogonal to terrain logic; can be threaded
// through at the Game/World call site later).
void Terrain::generateWorld(SDL_Renderer* renderer) {
    double x = -Config::CHUNK_SIZE;
    while (x < worldWidth_ + Config::CHUNK_SIZE) {
        double r = Util::randint(10, 30);
        addAirPocketClump(x, 0, r, false, true);
        x += r / 2.0;
    }

    generateDescendingCave(worldWidth_ / 2.0, 0, 40, M_PI / 2.0, renderer);

    int numSteps = std::max(1, static_cast<int>(worldHeight_ / 100));
    for (int i = 0; i < numSteps; ++i) {
        for (int j = 0; j < std::max(1, static_cast<int>(worldWidth_ / 1000)); ++j) {
            double baseX = j * 1000.0;

            if (Util::randint(1, 20) == 1) {
                generateSkinnyCave(baseX + Util::randint(0, 1000), Util::randint(0, static_cast<int>(worldHeight_ / 3)),
                                    Util::randint(20, 60), Util::randomDouble() * 2 * M_PI);
            }
            if (Util::randint(1, 20) == 1) {
                generateSkinnyCave(baseX + Util::randint(0, 1000),
                                    Util::randint(static_cast<int>(worldHeight_ / 4), worldHeight_),
                                    Util::randint(30, 90), Util::randomDouble() * 2 * M_PI);
            }
            if (Util::randint(1, 35) == 1) {
                generateBlobCave(baseX + Util::randint(0, 1000),
                                  Util::randint(static_cast<int>(worldHeight_ / 4), worldHeight_),
                                  Util::randint(30, 60), Util::randomDouble() * 2 * M_PI);
            }
            if (Util::randint(1, 20) == 1) {
                generateBlobCave(baseX + Util::randint(0, 1000),
                                  Util::randint(static_cast<int>(worldHeight_ * 2 / 3), worldHeight_),
                                  Util::randint(60, 120), Util::randomDouble() * 2 * M_PI);
            }

            double yWhite = Util::randint(500, std::max(501, worldHeight_ - 500));
            auto denomW = nestChance(ChargeType::White, depthFraction(yWhite));
            if (denomW && Util::randint(1, *denomW) == 1) {
                generateNest(baseX + Util::randint(0, 1000), yWhite, ChargeType::White, 0.0, renderer);
            }

            double yBlue = Util::randint(500, std::max(501, worldHeight_ - 500));
            auto denomB = nestChance(ChargeType::Blue, depthFraction(yBlue));
            if (denomB && Util::randint(1, *denomB) == 1) {
                generateNest(baseX + Util::randint(0, 1000), yBlue, ChargeType::Blue, 0.0, renderer);
            }

            double yRed = Util::randint(500, std::max(501, worldHeight_ - 500));
            auto denomR = nestChance(ChargeType::Red, depthFraction(yRed));
            if (denomR && Util::randint(1, *denomR) == 1) {
                generateNest(baseX + Util::randint(0, 1000), yRed, ChargeType::Red, 0.0, renderer);
            }
        }
    }
}

// --- Chunk streaming -------------------------------------------------------

// def start_streaming(self):
//     if self._stream_thread is not None: return
//     self._stream_thread = threading.Thread(target=self._stream_worker_loop, daemon=True)
//     self._stream_thread.start()
void Terrain::startStreaming() {
    if (streamRunning_.exchange(true)) return; // already running -- matches the Python's idempotent guard
    streamThread_ = std::thread(&Terrain::streamWorkerLoop, this);
}

// def _stream_worker_loop(self):
//     while True:
//         try: _, _, key = self._stream_queue.get(timeout=1.0)
//         except queue.Empty: continue
//         with self._stream_lock: self._stream_queued_keys.discard(key)
//         row, col = key
//         chunk = self.get_or_create_chunk(row, col)
//         if not chunk.built: self._build_chunk(chunk)
void Terrain::streamWorkerLoop() {
    while (streamRunning_.load()) {
        StreamQueueEntry entry{};
        bool got = false;
        {
            std::unique_lock<std::mutex> lock(streamQueueMutex_);
            got = streamQueueCv_.wait_for(lock, std::chrono::seconds(1), [&] {
                return !streamQueue_.empty() || !streamRunning_.load();
            });
            if (got && !streamQueue_.empty()) {
                entry = streamQueue_.top();
                streamQueue_.pop();
            } else {
                got = false;
            }
        }
        if (!got) continue; // timeout (or spurious wake with an empty queue) -- matches queue.Empty path

        {
            std::lock_guard<std::mutex> lock(streamLock_);
            streamQueuedKeys_.erase(packKey(entry.row, entry.col));
        }

        Chunk& chunk = getOrCreateChunk(entry.row, entry.col);
        if (!chunk.built.load(std::memory_order_acquire)) {
            buildChunkHitboxOnly(chunk); // TODO: full _build_chunk (with visuals) once that piece exists
        }
    }
}

// def update_streaming(self, player_x, player_y, build_radius_chunks=3): ...
// MAIN-THREAD-ONLY, per streamSeq_'s doc comment in Terrain.h.
void Terrain::updateStreaming(double playerX, double playerY, int buildRadiusChunks) {
    int pr = static_cast<int>(std::floor(playerY / Config::CHUNK_SIZE));
    int pc = static_cast<int>(std::floor(playerX / Config::CHUNK_SIZE));
    double now = std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();

    for (int dr = -buildRadiusChunks; dr <= buildRadiusChunks; ++dr) {
        int row = pr + dr;
        if (row < 0 || row * Config::CHUNK_SIZE > worldHeight_) continue;
        for (int dc = -buildRadiusChunks; dc <= buildRadiusChunks; ++dc) {
            int col = pc + dc;
            int64_t key = packKey(row, col);

            Chunk* existing = nullptr;
            {
                std::shared_lock<std::shared_mutex> mapLock(chunksMapLock_);
                auto it = chunks_.find(key);
                if (it != chunks_.end()) existing = it->second.get();
            }
            if (existing != nullptr && existing->built.load(std::memory_order_acquire)) {
                existing->lastTouched = now;
                continue;
            }

            {
                std::lock_guard<std::mutex> lock(streamLock_);
                if (streamQueuedKeys_.count(key)) continue;
                streamQueuedKeys_.insert(key);
            }

            int priority = dr * dr + dc * dc;
            streamSeq_++;
            {
                std::lock_guard<std::mutex> qlock(streamQueueMutex_);
                streamQueue_.push({ priority, streamSeq_, row, col });
            }
            streamQueueCv_.notify_one();
        }
    }
}

// def evict_far_chunks(self, player_x, player_y, keep_radius_chunks=20): ...
// See Terrain.h's doc comment on this method for the known,
// currently-unexercised race tradeoff with sampleChunk.
void Terrain::evictFarChunks(double playerX, double playerY, int keepRadiusChunks) {
    int pr = static_cast<int>(std::floor(playerY / Config::CHUNK_SIZE));
    int pc = static_cast<int>(std::floor(playerX / Config::CHUNK_SIZE));

    std::shared_lock<std::shared_mutex> mapLock(chunksMapLock_);
    for (auto& kv : chunks_) {
        Chunk& chunk = *kv.second;
        if (std::abs(chunk.row - pr) > keepRadiusChunks || std::abs(chunk.col - pc) > keepRadiusChunks) {
            if (chunk.built.load(std::memory_order_acquire)) {
                std::lock_guard<std::recursive_mutex> lock(chunk.lock);
                chunk.hitbox = BitMask(); // was: chunk.hitboxes.clear() / chunk.visuals.clear()
                chunk.visual = RenderTarget();
                chunk.visualBuilt = false;
                chunk.built.store(false, std::memory_order_release);
            }
        }
    }
}

// --- Visual rendering --------------------------------------------------

namespace {
// was: PALETTE = [...]
const std::vector<std::pair<double, Color>>& terrainPalette() {
    static const std::vector<std::pair<double, Color>> palette = {
        {0.000, {255, 200, 60, 255}},  {0.060, {255, 110, 40, 255}},  {0.120, {255, 60, 90, 255}},
        {0.180, {230, 40, 180, 255}},  {0.240, {170, 50, 240, 255}},  {0.300, {100, 70, 255, 255}},
        {0.360, {60, 120, 255, 255}},  {0.420, {40, 190, 255, 255}},  {0.480, {40, 230, 210, 255}},
        {0.540, {60, 230, 120, 255}},  {0.600, {170, 230, 60, 255}},  {0.660, {255, 230, 50, 255}},
        {0.720, {255, 160, 40, 255}},  {0.780, {255, 90, 60, 255}},   {0.840, {230, 50, 130, 255}},
        {0.900, {150, 60, 255, 255}},  {1.000, {80, 200, 255, 255}},
    };
    return palette;
}
} // namespace

// def init(): loads air_pocket_1/_2, _rim, _explode, rocks, gradient_vignette.
// NOTE: "air_pocket_hitbox" (loaded in the Python's init) is deliberately
// NOT fetched here -- our hitbox collision uses a mathematical circle
// approximation (see Terrain.h class note #2), so that asset is unused by
// this port.
void Terrain::init(SDL_Renderer* /*renderer*/) {
    GlobalAssets::getAsset("air_pocket_1");
    GlobalAssets::getAsset("air_pocket_2");
    GlobalAssets::getAsset("air_pocket_1_rim");
    GlobalAssets::getAsset("air_pocket_1_explode");
    GlobalAssets::getAsset("rocks");
    GlobalAssets::getAsset("gradient_vignette");
}

// def _noise_val(self, x, y, scale=1): ...
double Terrain::noiseVal(double x, double y, double scale) const {
    x *= scale;
    y *= scale;
    double v = std::sin(x * 0.017 + y * 0.011) * 0.4;
    v += std::cos(x * 0.031 - y * 0.023) * 0.3;
    v += std::sin(x * 0.053 + y * 0.047 + 1.3) * 0.2;
    v += std::cos(x * 0.079 - y * 0.061 + 2.7) * 0.1;
    return std::max(-1.0, std::min(1.0, v));
}

// def _depth_color(self, world_x, world_y): ...
Color Terrain::depthColor(double worldX, double worldY) const {
    double depthFrac = depthFraction(worldY);
    double noise = noiseVal(worldX, worldY) * 0.03;
    double d = std::max(0.0, std::min(1.0, depthFrac + noise));

    const auto& palette = terrainPalette();
    for (size_t i = 0; i + 1 < palette.size(); ++i) {
        double d0 = palette[i].first, d1 = palette[i + 1].first;
        const Color& c0 = palette[i].second;
        const Color& c1 = palette[i + 1].second;
        if (d <= d1) {
            double t = (d1 != d0) ? (d - d0) / (d1 - d0) : 0.0;
            return {
                static_cast<uint8_t>(c0.r + (c1.r - c0.r) * t),
                static_cast<uint8_t>(c0.g + (c1.g - c0.g) * t),
                static_cast<uint8_t>(c0.b + (c1.b - c0.b) * t),
                255
            };
        }
    }
    return palette.back().second;
}

// def _render_base_terrain(self, row, col, zoom): ...
RenderTarget Terrain::renderBaseTerrain(SDL_Renderer* renderer, int row, int col) {
    int chunkPx = Config::CHUNK_SIZE;
    double worldLeft = col * Config::CHUNK_SIZE;
    double worldTop = row * Config::CHUNK_SIZE;
    double worldRight = worldLeft + Config::CHUNK_SIZE;
    double worldBot = worldTop + Config::CHUNK_SIZE;

    Color tl = depthColor(worldLeft, worldTop);
    Color tr = depthColor(worldRight, worldTop);
    Color bl = depthColor(worldLeft, worldBot);
    Color br = depthColor(worldRight, worldBot);

    // was: surf.fill((0,0,0,255)); surf.blit(gradient, BLEND_RGB_MAX) --
    // simplified to a direct draw of the gradient, since MAX(black, x)==x
    // always (the fill color is pure black), making that two-step
    // sequence provably equivalent to just drawing the gradient directly.
    RenderTarget gradient(renderer, 2, 2);
    gradient.renderTo(renderer, [&] {
        Canvas::rectFilled(renderer, Rect{0, 0, 1, 1}, tl);
        Canvas::rectFilled(renderer, Rect{1, 0, 1, 1}, tr);
        Canvas::rectFilled(renderer, Rect{0, 1, 1, 1}, bl);
        Canvas::rectFilled(renderer, Rect{1, 1, 1, 1}, br);
    });
    SDL_SetTextureScaleMode(gradient.texture(), SDL_ScaleModeLinear); // bilinear, matches pygame.transform.smoothscale

    RenderTarget surf(renderer, chunkPx, chunkPx);
    surf.renderTo(renderer, [&] {
        Canvas::blit(renderer, gradient.texture(), 0, 0, chunkPx, chunkPx);
    });

    // Rock tiling multiply. NOTE: uses Util::pyMod (matches the Python's
    // `%` operator here, NOT math.fmod -- see generateDescendingCave's
    // comment for the opposite case; each modulo site needed checking
    // individually).
    const Asset& rocksAsset = GlobalAssets::getAsset("rocks");
    int rockX = static_cast<int>(Util::pyMod(worldLeft, static_cast<double>(TerrainConstants::kRocksWorldSpan)));
    int rockY = static_cast<int>(Util::pyMod(worldTop, static_cast<double>(TerrainConstants::kRocksWorldSpan)));

    RenderTarget rockLayer(renderer, chunkPx, chunkPx);
    rockLayer.renderTo(renderer, [&] {
        rockLayer.clear({0, 0, 0, 255});
        for (int ty = -rockY; ty < chunkPx; ty += TerrainConstants::kRocksWorldSpan) {
            for (int tx = -rockX; tx < chunkPx; tx += TerrainConstants::kRocksWorldSpan) {
                Canvas::blit(renderer, rocksAsset.texture, tx, ty,
                             TerrainConstants::kRocksWorldSpan, TerrainConstants::kRocksWorldSpan);
            }
        }
    });
    surf.renderTo(renderer, [&] {
        Canvas::blit(renderer, rockLayer.texture(), 0, 0, chunkPx, chunkPx, BlendModes::rgbMult());
    });

    return surf;
}

// def _carve_visual(self, chunk, air_pocket, zoom): the rim-glow composite.
void Terrain::carveVisual(SDL_Renderer* renderer, Chunk& chunk, const AirPocket& pocket) {
    double left = chunk.col * Config::CHUNK_SIZE;
    double top = chunk.row * Config::CHUNK_SIZE;
    double l = pocket.left - left;
    double t = pocket.top - top;
    int side = std::max(1, static_cast<int>(std::round(pocket.trueR * 2)));

    const Asset& eraserAsset = GlobalAssets::getAsset("air_pocket_" + std::to_string(pocket.imgIndex + 1));
    chunk.visual.renderTo(renderer, [&] {
        Canvas::blit(renderer, eraserAsset.texture, l, t, side, side, BlendModes::rgbaSub());
    });

    Color dc = depthColor(pocket.x, pocket.y);
    std::string rimName = "air_pocket_" + std::to_string(pocket.rimImgIndex + 1) + (pocket.playerMade ? "_explode" : "_rim");
    const Asset& rimAsset = GlobalAssets::getAsset(rimName);

    RenderTarget mask(renderer, side, side);
    mask.renderTo(renderer, [&] {
        Canvas::rectFilled(renderer, Rect{0, 0, side, side}, Color{dc.r, dc.g, dc.b, 0});
    });
    mask.renderTo(renderer, [&] {
        Canvas::blitRegion(renderer, chunk.visual.texture(),
                            Rect{static_cast<int>(l), static_cast<int>(t), side, side},
                            0, 0, side, side, BlendModes::rgbaMax());
    });
    mask.renderTo(renderer, [&] {
        Canvas::blit(renderer, rimAsset.texture, 0, 0, side, side, BlendModes::rgbaMult());
    });

    chunk.visual.renderTo(renderer, [&] {
        Canvas::blit(renderer, mask.texture(), l, t, side, side);
    });
}

void Terrain::buildChunkVisual(SDL_Renderer* renderer, Chunk& chunk) {
    std::lock_guard<std::recursive_mutex> lock(chunk.lock);
    if (chunk.visualBuilt) return;

    chunk.visual = renderBaseTerrain(renderer, chunk.row, chunk.col);
    for (auto& pocket : chunk.airPockets) {
        carveVisual(renderer, chunk, pocket);
    }
    chunk.visualBuilt = true;
}

// def draw_vignette(self, surface, window_size, offset_x=0, offset_y=0): ...
void Terrain::drawVignette(SDL_Renderer* renderer, int screenWidth, int screenHeight, int offsetX, int offsetY) {
    if (vignetteCacheW_ != screenWidth || vignetteCacheH_ != screenHeight) {
        const Asset& vignetteAsset = GlobalAssets::getAsset("gradient_vignette");
        vignetteCache_ = RenderTarget(renderer, screenWidth, screenHeight);
        vignetteCache_.renderTo(renderer, [&] {
            vignetteCache_.clear({0, 0, 0, 0});
            Canvas::blit(renderer, vignetteAsset.texture, 0, 0, screenWidth, screenHeight);
        });
        vignetteCacheW_ = screenWidth;
        vignetteCacheH_ = screenHeight;
    }
    Canvas::blit(renderer, vignetteCache_.texture(), offsetX, offsetY, screenWidth, screenHeight, BlendModes::rgbMult());
}

// def get_frame_color(self, surface, frame, offset_x=0, offset_y=0): ...
// Uses screen size (matches the Python's surface.get_size() at the real
// call site, which passes the full render target, not the letterboxed
// viewport size).
Color Terrain::getFrameColor(const Frame& frame) const {
    double cx = frame.left + frame.screenWidth / frame.zoom / 2.0;
    double cy = frame.top + frame.screenHeight / frame.zoom / 2.0;
    return depthColor(cx, cy);
}

// def draw_terrain(self, window_size, surface, frame, hitboxes=False, ...): ...
void Terrain::drawTerrain(SDL_Renderer* renderer, const Frame& frame, bool hitboxes) {
    int topChunk = static_cast<int>(std::floor(frame.top / Config::CHUNK_SIZE));
    int leftChunk = static_cast<int>(std::floor(frame.left / Config::CHUNK_SIZE));
    int bottomChunk = static_cast<int>(std::floor((frame.top + frame.viewHeight / frame.zoom) / Config::CHUNK_SIZE));
    int rightChunk = static_cast<int>(std::floor((frame.left + frame.viewWidth / frame.zoom) / Config::CHUNK_SIZE));

    if (hitboxes) {
        // FLAGGED SIMPLIFICATION: dev-only debug overlay (Game's K_h
        // toggle). The Python composites a cached chunk.hitboxes[zoom]
        // surface via BLEND_RGBA_SUB; we no longer have a rendered hitbox
        // surface at all (BitMask, not a texture, is the collision source
        // of truth -- see Terrain.h note #1), so this rasterizes each
        // visible chunk's BitMask into an on-the-fly semi-transparent
        // overlay instead. Not performance-optimized (no caching) --
        // acceptable since this is a manually-toggled dev tool, not a hot
        // path.
        for (int row = topChunk; row <= bottomChunk; ++row) {
            if (row < 0) continue;
            for (int col = leftChunk; col <= rightChunk; ++col) {
                Chunk* chunk = getChunkIfBuilt(row, col);
                if (chunk == nullptr) continue;

                std::vector<uint8_t> buf(static_cast<size_t>(Config::CHUNK_SIZE) * Config::CHUNK_SIZE * 4, 0);
                for (int y = 0; y < Config::CHUNK_SIZE; ++y) {
                    for (int x = 0; x < Config::CHUNK_SIZE; ++x) {
                        if (chunk->hitbox.get(x, y)) {
                            size_t idx = (static_cast<size_t>(y) * Config::CHUNK_SIZE + x) * 4;
                            buf[idx + 0] = 255; buf[idx + 1] = 0; buf[idx + 2] = 0; buf[idx + 3] = 120;
                        }
                    }
                }
                RenderTarget debugTex(renderer, Config::CHUNK_SIZE, Config::CHUNK_SIZE);
                SDL_UpdateTexture(debugTex.texture(), nullptr, buf.data(), Config::CHUNK_SIZE * 4);

                Vec2 pos = frame.worldToScreen(col * Config::CHUNK_SIZE, row * Config::CHUNK_SIZE);
                double destSize = Config::CHUNK_SIZE * frame.zoom;
                Canvas::blit(renderer, debugTex.texture(), pos.x, pos.y, destSize, destSize);
            }
        }
        return;
    }

    // was: if zoom not in self.default_zooms: return -- DROPPED. This
    // existed only because rendering was locked to a fixed set of
    // pre-scaled zoom levels; GPU draw-time scaling removes that
    // constraint entirely (see Terrain.h class notes), so any zoom value
    // is valid now.

    if (terrainStencilW_ != frame.screenWidth || terrainStencilH_ != frame.screenHeight) {
        terrainStencil_ = RenderTarget(renderer, frame.screenWidth, frame.screenHeight);
        terrainStencilW_ = frame.screenWidth;
        terrainStencilH_ = frame.screenHeight;
    }

    terrainStencil_.renderTo(renderer, [&] {
        terrainStencil_.clear({0, 0, 0, 0});
        for (int row = topChunk; row <= bottomChunk; ++row) {
            if (row < 0) continue;
            for (int col = leftChunk; col <= rightChunk; ++col) {
                Chunk* chunk = getChunkIfBuilt(row, col);
                Vec2 pos = frame.worldToScreen(col * Config::CHUNK_SIZE, row * Config::CHUNK_SIZE);
                double destSize = Config::CHUNK_SIZE * frame.zoom;

                if (chunk != nullptr) {
                    if (!chunk->visualBuilt) buildChunkVisual(renderer, *chunk);
                    Canvas::blit(renderer, chunk->visual.texture(), pos.x, pos.y, destSize, destSize);
                } else {
                    // was: flat red "unbuilt" placeholder
                    Canvas::rectFilled(renderer, Rect{
                        static_cast<int>(pos.x), static_cast<int>(pos.y),
                        static_cast<int>(destSize), static_cast<int>(destSize)
                    }, Color{255, 0, 0, 255});
                }
            }
        }
        // Vignette applied HERE, to the stencil only -- see Terrain.h's
        // note on terrainStencil_ for why this two-step matters.
        drawVignette(renderer, frame.screenWidth, frame.screenHeight, frame.offsetX, frame.offsetY);
    });

    Canvas::blit(renderer, terrainStencil_.texture(), 0, 0, frame.screenWidth, frame.screenHeight);
}

