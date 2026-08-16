#pragma once
#include "Enemy.h"

// Ported from basic_flying.py. Overrides tick_enemy_behavior with true
// flight (gravity_multiplier=0, no on_ground concept in its movement
// logic), moving toward the player on both axes independently.
class BasicFlying : public Enemy {
public:
    static constexpr int kSizeMin = 20, kSizeMax = 50;
    static constexpr const char* kCostume = "1";
    static constexpr double kHealthFactor = 0.5;

    BasicFlying(SDL_Renderer* renderer, Color color, double size, double nestHealth, double x, double y);

    void tickEnemyBehavior(double frameLength, const EnemyPlayerView& player) override;
};
