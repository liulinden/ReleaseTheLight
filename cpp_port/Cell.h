#pragma once
#include <SDL.h>
#include "Core.h"
#include "Frame.h"
#include "Terrain.h"
#include "InteractionDisplay.h"

// Ported from cells.py.
//
// No per-zoom pre-scaled image cache (Cell.cell_imgs / the class-level
// ImageCache) -- GPU scales at draw time, per the established
// architecture decision; shell/crackle textures are fetched fresh from
// GlobalAssets each draw call instead.
//
// FLAGGED ADAPTER: tick_knockback needs `player.laser.laser_target is
// self` (an identity check against whatever the player's laser is
// currently targeting) and whether the player has an active laser at
// all. Player/Laser aren't ported yet, so this takes a minimal
// LaserTargetInfo struct instead of a real Player reference -- same
// pattern as ChargeDisplay's PlayerChargeSnapshot. Once Player/Laser
// exist, the real call site just builds this struct from
// player.laser/player.laser->laserTarget each tick; Cell itself doesn't
// need to change.
struct LaserTargetInfo {
    bool active = false;      // was: player.laser is not None
    const void* target = nullptr; // was: player.laser.laser_target (identity-compared)
};

class Cell {
public:
    static constexpr double kWidth = 10.0;
    static constexpr double kHeight = 18.0;
    static constexpr double kSize = 30.0;
    static constexpr double kAnimationFps = 12.0;

    // was: def init(): loads cell_basic_shell, cell_basic_crackle_1..5
    static void init(SDL_Renderer* renderer);

    Cell(SDL_Renderer* renderer, Vec2 coords, Vec2 velocities);

    // was: def tick_knockback(self, frame_length, _terrain, player) -> bool
    bool tickKnockback(double frameLength, Terrain& terrain, const LaserTargetInfo& laserInfo);

    // was: def tick_gravity(self, frame_length)
    void tickGravity(double frameLength);

    // was: def attempt_movement(self, frame_length, _terrain)
    void attemptMovement(double frameLength, Terrain& terrain);

    // was: def tick(self, frame_length, _terrain, player)
    void tick(double frameLength, Terrain& terrain, const LaserTargetInfo& laserInfo);

    // was: def update_rect(self)
    void updateRect();

    // was: def colliding_with_terrain(self, _terrain)
    Terrain::CollisionResult collidingWithTerrain(Terrain& terrain);

    // was: def draw(self, surface, frame, hitbox=False, offset_x=0, offset_y=0)
    // Renders onto whatever target is currently bound to `renderer`.
    void draw(SDL_Renderer* renderer, const Frame& frame, bool hitbox = false);

    // was: def within_interaction_radius(self, coords)
    bool withinInteractionRadius(Vec2 coords) const;

    // was: def close(self, window_size, frame)
    bool close(const Frame& frame) const;

    double x() const { return x_; }
    double y() const { return y_; }
    InteractionDisplay& interactionDisplay() { return interactionDisplay_; }

private:
    // was: def _resolve_collision(...) -- PRESERVED BUT UNUSED, matching
    // the Python exactly: this method is defined but never called from
    // attempt_movement (which computes its bounce response inline
    // instead). Looks like dead/vestigial code in the original; kept
    // faithfully rather than removed, per project convention of not
    // silently "cleaning up" things that look like bugs or leftovers.
    Vec2 resolveCollision(Vec2 velocity, Vec2 normal, double elasticity, double friction,
                           double frameLength, double bounceThreshold = 0.05);

    // was: def _find_clearance(self, _terrain, vx, vy, max_wiggle=2)
    bool findClearance(Terrain& terrain, double vx, double vy, int maxWiggle = 2);

    double w_ = kWidth, h_ = kHeight, size_ = kSize;
    double x_, y_;
    double xSpeed_, ySpeed_;
    Rect rect_;
    double r_; // was: self.r = dist(self.w, self.h)

    InteractionDisplay interactionDisplay_;
    int framesSinceMoved_ = 0;
    double animationTimer_ = 0.0;
    int frame_ = 1; // animation frame index (distinct from the Frame camera type)
};

// was: def validate_cell_coords(_terrain, coords)
bool validateCellCoords(Terrain& terrain, Vec2 coords);
