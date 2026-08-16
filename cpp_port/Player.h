#pragma once
#include <array>
#include <vector>
#include <memory>
#include <SDL.h>
#include "Core.h"
#include "Frame.h"
#include "Types.h"
#include "Terrain.h"
#include "Laser.h"
#include "LaserProperties.h"
#include "HealthBar.h"
#include "RenderTarget.h"

// Ported from player.py.
//
// No per-zoom pre-scaled image caches (player_im_gs, _impact_im_gs) --
// GPU scales/tints at draw time, per the established architecture
// decision.
//
// Input handling: Python's `keys_down` (dict of pygame key constants +
// "left_mouse"/"right_mouse" strings, held state) and `events` (dict,
// edge-triggered flags reset each frame by Game) are combined here into
// one PlayerInput struct.
struct PlayerInput {
    bool keyW = false, keyA = false, keyD = false;
    bool leftMouseHeld = false, rightMouseHeld = false;

    bool leftMouseDownEvent = false, leftMouseUpEvent = false;
    bool rightMouseDownEvent = false, rightMouseUpEvent = false;
    bool spaceEvent = false, rightArrowEvent = false, leftArrowEvent = false;
};

// was: def filter_charges(filter_type, charges)
std::array<double, 3> filterCharges(FilterType filterType, const std::array<double, 3>& charges);

// was: filter_feeds[filter_type][charge_color] -> (addW, addB, addR) fractions
std::array<double, 3> filterFeed(FilterType filter, ChargeType color);

// was: class LaserImpact
class LaserImpact {
public:
    static constexpr int kImpactFrames = 7;
    static constexpr double kFrameDuration = 1000.0 / 24.0; // IMPACT_FPS = 24
    static constexpr double kImpactSize = 100.0;

    LaserImpact(SDL_Renderer* renderer, double x, double y, double angle, Laser* sourceLaser);

    // was: def tick(self, frame_length, active_laser) -> bool (True = finished)
    bool tick(double frameLength, Laser* activeLaser);

    // was: def draw(self, surface, frame, color, zoom, offset_x=0, offset_y=0)
    void draw(SDL_Renderer* renderer, const Frame& frame, Color color);

private:
    double x_, y_, angle_;
    Laser* sourceLaser_; // was: self.source_laser -- becomes nullptr once the source laser is gone, matching Python's None
    double timer_ = 0.0;

    RenderTarget scratch_;
    int scratchW_ = -1, scratchH_ = -1;
};

class Player {
public:
    static constexpr double kSpriteWidth = 40.0, kSpriteHeight = 40.0;
    static constexpr double kArmPivotX = 20.0, kArmPivotY = 21.0;
    static constexpr double kAnimationFps = 13.0;

    enum class AnimType { Idle, Run, Backpedal, Fall, Jump };

    // was: def init(): loads player_idle/_run/_arm + laser_impact_1..7
    static void init(SDL_Renderer* renderer);

    Player(SDL_Renderer* renderer, double x, double y, Vec2 dimensions = {10.0, 30.0});

    // was: def reset_player(self)
    void resetPlayer();

    // was: def update_costume(self, frame_length, mouse_pos)
    void updateCostume(double frameLength, Vec2 mousePos);

    void updateRect();

    // was: def update_color(self)
    void updateColor();

    // was: def update_charge_capacity(self)
    void updateChargeCapacity();

    // was: def update_laser_stats(self)
    void updateLaserStats();

    // was: def set_charges(self, white, blue, red)
    void setCharges(double white, double blue, double red);

    // was: def add_charge(self, added_charge, charge_distribution) -> float
    double addCharge(double addedCharge, const std::array<double, 3>& chargeDistribution);

    // was: def lose_charge(self, loss) -> bool (True if player died/reset)
    bool loseCharge(double loss);

    // was: def deal_damage(self, damage)
    void dealDamage(double damage);
    // was: def drain_damage(self, damage)
    void drainDamage(double damage);

    // was: def tick(self, frame_length, _terrain, mouse_pos, keys_down, events) -> bool
    // Returns true when World should reset camera/heal nests/remove
    // enemies (matches the Python's signal to World.tick()).
    bool tick(double frameLength, Terrain& terrain, Vec2 mousePos, const PlayerInput& input);

    void moveHorizontal(double frameLength, Terrain& terrain);
    void moveVertical(double frameLength, Terrain& terrain);
    Terrain::CollisionResult collidingWithTerrain(Terrain& terrain);

    // was: def draw(self, surface, frame, hitboxes=False, offset_x=0, offset_y=0, tilt=0)
    void draw(SDL_Renderer* renderer, const Frame& frame, bool hitboxes = false, double tilt = 0.0);

    double x, y, xSpeed = 0.0, ySpeed = 0.0;
    double width, height;
    Rect rect;
    bool onGround = false;
    Color color{255, 0, 0, 255};
    Facing facing = Facing::Right;
    double animationTimer = 0.0;
    AnimType animationType = AnimType::Idle;
    int animationFrame = 0;
    double armAngle = 0.0;

    FilterType filterType = FilterType::White;
    bool filterChangeRight = true;
    double laserTimer = 0.0;
    int laserRamps = 0;
    bool laserFirstHit = false;
    std::unique_ptr<Laser> laser; // was: self.laser = None
    std::vector<std::unique_ptr<LaserImpact>> impacts;
    LaserAttributes laserAttributes;

    double abilityTimer = 0.0;
    double abilityCooldown = 800.0;

    int nCells = 15;
    double chargeCapacity;
    std::array<double, 3> charges{100.0, 0.0, 0.0};
    std::array<double, 3> practicalCharges{100.0, 0.0, 0.0};
    double maxCharge = 500.0;
    double immunityTimer = 0.0;
    double immunityTime = 500.0;
    double queuedDamage = 0.0;
    double queuedDrainDamage = 0.0;

private:
    double spawnX_, spawnY_;
    SDL_Renderer* renderer_;

    // Persistent scratch buffers for the main sprite + arm tint composite,
    // matching the perf-conscious pattern established in Enemy/Nest.
    RenderTarget bodyScratch_, armScratch_;
    int bodyScratchW_ = -1, bodyScratchH_ = -1;
    int armScratchW_ = -1, armScratchH_ = -1;
};
