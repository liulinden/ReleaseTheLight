#pragma once
#include <array>
#include <vector>
#include <SDL.h>
#include "Core.h"
#include "Types.h"
#include "RenderTarget.h"

// Ported from charge_display.py.
//
// Structural notes:
//   - No init()-time pre-scaling of charge_icon/cell_imgs (GPU scaling at
//     draw time, per project decision) and no cell_imgs_cache of
//     pre-rotated bitmaps (GPU rotation at draw time via
//     Canvas::blitRotated) -- both caches existed purely to avoid pygame's
//     CPU transform cost, which doesn't apply here.
//   - `light_gradient` (loaded in Python's init() but never read outside
//     the large commented-out legacy draw() block) is dropped entirely,
//     along with that ~70-line dead code block itself -- not ported even
//     as comments, since it's disabled code with no live callers.
//   - `player` parameter is temporarily replaced with a PlayerChargeSnapshot
//     capturing exactly the fields update() reads, since Player hasn't
//     been ported yet. FLAGGED: revisit once player.py is translated --
//     likely just building this snapshot from the real Player each frame
//     in World/Game glue code, rather than changing ChargeDisplay itself.
struct PlayerChargeSnapshot {
    double chargeCapacity;
    std::array<double, 3> charges;          // indexed by ChargeType (was player.charges dict)
    std::array<double, 3> practicalCharges; // indexed by ChargeType (was player.practical_charges dict)
    FilterType filterType;
    bool filterChangeRight;
    int nCells;
    double y;
};

// was: get_diamond_points(center, angle)
std::vector<Vec2> chargeDiamondPoints(Vec2 center, double angle);
// was: get_outer_triangle_points(center, angle)
std::vector<Vec2> chargeOuterTrianglePoints(Vec2 center, double angle);

class ChargeDisplay {
public:
    explicit ChargeDisplay(SDL_Renderer* renderer);

    // was: def update(self, fps, player)
    void update(double fps, const PlayerChargeSnapshot& player);

    // was: def draw(self, surface) -- renders onto whatever target is
    // currently bound to `renderer`, matching the rest of the port.
    void draw(SDL_Renderer* renderer);

private:
    SDL_Renderer* renderer_;

    double rotation_ = 0.0;
    double rotationGoal_ = 1.0;
    double scale_ = 90.0;
    double rotationSpeed_ = 0.0;

    std::array<double, 3> playerCharges_{};       // was: self.player_charges (smoothed, indexed by ChargeType)
    double playerTotalCharge_ = 0.0;
    double activeCharge_ = 0.0;
    Color chargeColor_{0, 0, 0, 255};
    Color color_{0, 0, 0, 255};
    double playerY_ = 0.0;
    double chargeCapacity_ = 0.0;

    // was: self.filters = {"white": 0} -- grows as the player uses new
    // filter types for the first time (blue/red indicators stay hidden
    // until then). Indexed array + presence flags replaces the
    // dynamically-growing dict, preserving that "progressive reveal"
    // behavior exactly.
    std::array<double, 3> filters_{};
    std::array<bool, 3> filterPresent_{ true, false, false }; // white present from construction

    FilterType filterType_ = FilterType::White;
    double animationTimer_ = 0.0;
    int frame_ = 1;
    int nCells_ = 0;

    // Native-resolution scratch buffers for the "fill flat color, multiply-
    // blit source sprite onto it" tint step, done at native asset
    // resolution then scaled+rotated in one shot at final blit (tinting
    // commutes with scaling, so this is visually equivalent to Python's
    // "pre-scale then tint" order while being simpler under our
    // draw-time-scaling architecture).
    RenderTarget iconScratch_;
    RenderTarget cellScratch_;
};
