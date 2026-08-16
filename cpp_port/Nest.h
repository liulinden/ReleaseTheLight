#pragma once
#include <array>
#include <vector>
#include <string>
#include <SDL.h>
#include "Core.h"
#include "Frame.h"
#include "Types.h"
#include "Terrain.h"
#include "Enemy.h"
#include "HealthBar.h"
#include "InteractionDisplay.h"
#include "RenderTarget.h"

// Ported from nest.py.
//
// No per-zoom pre-scaled image/gradient/filter caches -- GPU scales/tints
// at draw time, per the established architecture decision.
//
// FLAGGED: the Python defines a 4th nest type, "sun", with an EMPTY
// variant list (nest_im_gs["sun"] would be []) and no entry in
// _enemy_handling.eligible_enemies. Constructing a sun-type Nest would
// hit `random.randint(0, len(selection)-1)` with selection empty
// (random.randint(0, -1), which raises), and calling add_enemy on one
// would hit a KeyError on eligible_enemies["sun"]. terrain.py's world
// generation only ever spawns "white"/"blue"/"red" nests -- "sun" looks
// vestigial/unfinished in the source we've been given. NestType is
// defined here as a full 4-value enum for fidelity (matching the data
// structures that reference all 4), but Sun's failure modes are
// preserved as loud failures (exceptions) rather than invented graceful
// handling, since inventing behavior the original never had would be a
// bigger deviation than just failing the same way.
enum class NestType { White, Blue, Red, Sun };

// Converts NestType to the matching ChargeType for charge-accumulator
// indexing and for EnemyHandling::getEnemy (which only knows ChargeType).
// Throws for Sun -- see class note above.
ChargeType nestTypeToChargeType(NestType type);

class Nest {
public:
    // was: def init(): loads gradient_light + nest_<variant>_<stage> /
    // nest_<variant>_hitbox for each (type, stages, variants) tuple.
    static void init(SDL_Renderer* renderer);

    Nest(SDL_Renderer* renderer, NestType type, double worldHeight, double x, double y, double size);

    // was: def get_rect(self)
    Rect getRect() const;

    // was: def update_color(self)
    void updateColor();

    // was: def lose_charge(self, loss)
    void loseCharge(double loss);

    // was: def update_visuals(self, frame_length)
    void updateVisuals(double frameLength);

    // was: def draw_gradient(self, surface, frame, offset_x=0, offset_y=0)
    void drawGradient(SDL_Renderer* renderer, const Frame& frame);

    // was: def draw(self, surface, frame, hitbox=False, offset_x=0, offset_y=0)
    void draw(SDL_Renderer* renderer, const Frame& frame, bool hitbox = false);

    // was: def draw_health_bar(self, surface, frame, time=None, offset_x=0, offset_y=0)
    void drawHealthBar(SDL_Renderer* renderer, const Frame& frame, int64_t timeMs = -1);

    // was: def add_enemy(self, c_terrain, player)
    // `player` reduced to (playerX, playerY, playerRect) -- get_enemy only
    // reads these (see EnemyHandling::getEnemy's own note).
    void addEnemy(SDL_Renderer* renderer, Terrain& terrain, double playerX, double playerY, const Rect& playerRect);

    // was: def within_effect_radius(self, x, y)
    bool withinEffectRadius(double px, double py) const;

    struct DamageParticleSpec { double x, y, size; };
    // was: def apply_damage_from_circles(self, c_terrain, player) -> list of particle specs
    std::vector<DamageParticleSpec> applyDamageFromCircles(SDL_Renderer* renderer, Terrain& terrain,
                                                             const LaserTargetInfo& laser,
                                                             double playerX, double playerY, const Rect& playerRect);

    // was: def deal_damage(self, damage, c_terrain, player)
    void dealDamage(double damage, SDL_Renderer* renderer, Terrain& terrain,
                     double playerX, double playerY, const Rect& playerRect);

    // was: def update_stage(self) -> int | False
    // Returns -1 for Python's `False` (no stage change), matching the
    // "falsy sentinel that's also sometimes a real value" pattern -- here
    // stage is always >= 0 when it DID change, so -1 is unambiguous.
    int updateStage();

    // was: def close(self, x, y, radius)
    bool close(double px, double py, double radius) const;

    // Exposes the randomly-chosen art variant id for hitbox mask lookup
    // from Terrain::nestsCollideRect (was: nest_hitboxes[nest_type][id] --
    // Terrain needs to know which specific variant's hitbox asset to
    // sample). Returns -1 for Sun nests (no variant exists).
    int variantIdForCollision() const { return variantId_; }

    double x, y, left, top, size;
    NestType nestType;
    std::vector<Enemy*> enemies; // non-owning -- see Terrain.h class note
    int basicEnemyCap = 1;
    Color color{255, 255, 255, 255};
    double glow = 0.0;
    int stage = 0;
    int maxStage;

    double maxHealth;
    double health;
    double maxCharge;
    double visualCharge;
    double charge;
    double chargeRate;
    std::array<double, 3> charging{}; // indexed by ChargeType -- was: self.charging dict

    InteractionDisplay interactionDisplay;

private:
    HealthBar healthBar_;
    int variantId_ = -1; // which art variant was randomly chosen (e.g. one of 1..4 for white); -1 for Sun (no variants exist)

    RenderTarget drawScratch_;
    int drawScratchW_ = -1, drawScratchH_ = -1;
};
