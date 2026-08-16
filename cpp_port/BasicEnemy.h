#pragma once
#include "Enemy.h"

// Ported from basic_enemy.py. Trivial subclass: no behavior override,
// just stat tuning via the base constructor.
class BasicEnemy : public Enemy {
public:
    static constexpr int kSizeMin = 20, kSizeMax = 70;
    static constexpr const char* kCostume = "1";
    static constexpr double kHealthFactor = 0.5;

    BasicEnemy(SDL_Renderer* renderer, Color color, double size, double nestHealth, double x, double y)
        : Enemy(renderer, kCostume, color, x, y, size, nestHealth * kHealthFactor) {}
};
