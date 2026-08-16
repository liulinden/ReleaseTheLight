#pragma once
#include "Enemy.h"

// Ported from bouncer.py.
//
// FLAGGED PER YOUR EARLIER NOTE: attempt_movement here uses a different,
// simpler physics model than Cell's/Enemy's step-based collision
// (continuous motion + a "backs" sub-step search + get_normal-based
// bounce), which you already identified as something to unify with
// Cell's system later. Preserved exactly as-is for this port, not
// unified now -- flagging again here since this is where it actually
// gets implemented.
class Bouncer : public Enemy {
public:
    static constexpr int kSizeMin = 20, kSizeMax = 40;
    static constexpr const char* kCostume = "1";
    static constexpr double kHealthFactor = 0.2;

    Bouncer(SDL_Renderer* renderer, Color color, double size, double nestHealth, double x, double y);

    void attemptMovement(double frameLength, Terrain& terrain) override;
    void tickEnemyBehavior(double frameLength, const EnemyPlayerView& player) override;
};
