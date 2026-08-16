#pragma once
#include <string>
#include <unordered_map>
#include <array>
#include <functional>
#include <SDL.h>
#include "Core.h"
#include "Frame.h"
#include "Terrain.h"
#include "HealthBar.h"
#include "RenderTarget.h"
#include "Cell.h" // for LaserTargetInfo

// Ported from _enemy.py.
//
// No per-zoom pre-scaled image caches (resized_im_gs, resized_gradients,
// _draw_filter, _gradient_filter dicts keyed by zoom) -- GPU scales/tints
// at draw time, per the established architecture decision.
//
// FLAGGED ADAPTER: Enemy genuinely MUTATES player state (writes
// x_speed/y_speed directly, calls player.deal_damage(...), sets
// immunity_timer), not just reads it -- so a read-only snapshot (like
// ChargeDisplay's PlayerChargeSnapshot) isn't sufficient here. Player
// isn't ported yet, so this takes an EnemyPlayerView holding REFERENCES
// to the fields Enemy writes, copies of the fields it only reads, and a
// callback for deal_damage (which does more in the real Player than a
// simple field write). Once Player exists, the real call site builds
// this view from the real Player each tick; Enemy itself shouldn't need
// to change.
struct EnemyPlayerView {
    double x = 0, y = 0;
    double& xSpeed;
    double& ySpeed;
    double& immunityTimer;
    double immunityTime = 500.0; // read-only threshold (was: player.immunity_time)
    Rect rect;
    LaserTargetInfo laser;
    std::function<void(double)> dealDamage; // was: player.deal_damage(damage)
};

// was: costume_dimensions["1"] = (3/8, 3/4), enemy_attack_frames["1"] =
// [4,5], enemy_animation_lengths["1"] = {spawn:6, walk:7, attack:9}.
// Only costume "1" exists in the source we've ported; kept as lookups
// (not hardcoded into Enemy directly) in case more costumes are added.
struct CostumeInfo {
    double widthFrac, heightFrac; // costume_dimensions
    std::array<int, 2> attackFrames; // enemy_attack_frames (fixed-size: only ever 2 entries in the source)
    int spawnFrames, walkFrames, attackAnimFrames; // enemy_animation_lengths
};
const CostumeInfo& costumeInfo(const std::string& costumeId);

// was: mode = "spawn" | "walk" | "attack" (string in Python)
enum class EnemyMode { Spawn, Walk, Attack };

// was: facing = "left" | "right"
enum class Facing { Left, Right };

class Enemy {
public:
    static constexpr double kAnimationFps = 15.0;

    // was: def init(): loads gradient_light + enemy_1_spawn/_walk/_attack/_attack_hitbox
    static void init(SDL_Renderer* renderer);

    Enemy(SDL_Renderer* renderer, const std::string& costume, Color color,
          double x, double y, double size = 50.0, double health = 500.0);
    virtual ~Enemy() = default;

    // was: def spawn_particles(self, _terrain)
    void spawnParticles(Terrain& terrain);

    // was: def update_costume(self, frame_length, player)
    void updateCostume(double frameLength, const EnemyPlayerView& player);

    void updateRect();

    // was: def draw_gradient(self, surface, frame, offset_x=0, offset_y=0)
    void drawGradient(SDL_Renderer* renderer, const Frame& frame);

    // was: def draw(self, surface, frame, hitbox=False, offset_x=0, offset_y=0)
    void draw(SDL_Renderer* renderer, const Frame& frame, bool hitbox = false);

    // was: def draw_health_bar(self, surface, frame, time=None, offset_x=0, offset_y=0)
    void drawHealthBar(SDL_Renderer* renderer, const Frame& frame, int64_t timeMs = -1);

    // was: def draw_attack_hitbox(self, surface, frame, offset_x=0, offset_y=0) -- "never used"
    // per the Python's own comment, EXCEPT it's also called from the
    // dev-hitbox draw path, which is unreachable due to a "Attack" vs
    // "attack" case-mismatch bug there (preserved faithfully -- see draw()).
    void drawAttackHitbox(SDL_Renderer* renderer, const Frame& frame);

    // was: def deal_damage(self, damage, direct=False) -> bool (True if killed)
    bool dealDamage(double damage, bool direct = false);

    // was: def tick_damage_and_knockback(self, frame_length, _terrain, player) -> bool
    bool tickDamageAndKnockback(double frameLength, Terrain& terrain, EnemyPlayerView& player);

    void tickGravity(double frameLength);

    // was: def tick_enemy_behavior(self, frame_length, player) -- virtual:
    // BasicFlying and Bouncer override this.
    virtual void tickEnemyBehavior(double frameLength, const EnemyPlayerView& player);

    // was: def attempt_movement(self, frame_length, _terrain) -- virtual:
    // Bouncer overrides this entirely with different physics (per your
    // earlier note that this is a known "to unify later" asymmetry,
    // preserved as-is rather than unified now).
    virtual void attemptMovement(double frameLength, Terrain& terrain);

    // was: def check_despawn(self, player)
    bool checkDespawn(const EnemyPlayerView& player) const;

    // was: def handle_attack(self, player)
    void handleAttack(EnemyPlayerView& player);

    // was: def tick(self, frame_length, _terrain, player) -> bool (True if should be removed)
    bool tick(double frameLength, Terrain& terrain, EnemyPlayerView& player);

    void moveHorizontal(double frameLength, Terrain& terrain);
    void moveVertical(double frameLength, Terrain& terrain);

    Terrain::CollisionResult collidingWithTerrain(Terrain& terrain);

    // was: def attack_collide_rect(self, rect) -- pixel-perfect mask
    // overlap, ported using BitMask (our collision-mask primitive)
    // instead of pygame.mask, per the earlier architecture decision.
    bool attackCollideRect(const Rect& rect);

    // Exposes the current hitbox rect for point-collision checks from
    // Terrain::laserCollidePoint (was: enemy.rect.collidepoint(x,y)).
    // Assumes updateRect() has already been called this tick, which it
    // always has by the time tick() finishes -- Enemy keeps rect_ current
    // throughout tick/movement.
    Rect rectForCollision() const { return rect_; }

    double x = 0, y = 0;
    double xSpeed = 0, ySpeed = 0;
    double size;
    double width, height;
    Color color;
    double health, maxHealth;
    double damage;
    double knockback = 0.2;
    double speed = 2.0;
    double knockbackResistance = 1.0;
    double gravityMultiplier = 1.0;
    bool onGround = false;
    EnemyMode mode = EnemyMode::Spawn;
    Facing facing = Facing::Right;

protected:
    std::string costumeId_;
    double glow = 0.0;
    double animationTimer_ = 0.0;
    int animationFrame_ = 0;
    double r_;
    Rect rect_;
    HealthBar healthBar_;

    // Persistent scratch buffer for the main sprite tint composite (fill
    // color, multiply-blit the animation frame) -- reused across frames
    // rather than reallocated each draw call (matches the perf-conscious
    // pattern established in ChargeDisplay/InteractionDisplay), since
    // draw() runs every frame for every visible enemy.
    RenderTarget drawScratch_;
    int drawScratchW_ = -1, drawScratchH_ = -1;
};
