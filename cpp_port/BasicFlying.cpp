#include "BasicFlying.h"
#include "Util.h"
#include <cmath>

BasicFlying::BasicFlying(SDL_Renderer* renderer, Color color, double size, double nestHealth, double x, double y)
    : Enemy(renderer, kCostume, color, x, y, size, nestHealth * kHealthFactor) {
    knockback = 0.1;
    speed = 1.5;
    knockbackResistance = 0.8;
    gravityMultiplier = 0.0;
}

// def tick_enemy_behavior(self, frame_length, player): ...
void BasicFlying::tickEnemyBehavior(double frameLength, const EnemyPlayerView& player) {
    if (mode != EnemyMode::Walk) return;

    if (std::abs(player.x - x) > size / 2.0 || std::abs(player.y - y) > size / 2.0) {
        int rndX = Util::randint(0, 3);
        if ((player.x < x && rndX != 3) || rndX == 0) xSpeed -= 0.0003 * frameLength * speed;
        else xSpeed += 0.0003 * frameLength * speed;

        int rndY = Util::randint(0, 3);
        if ((player.y < y && rndY != 3) || rndY == 0) ySpeed -= 0.0003 * frameLength * speed;
        else ySpeed += 0.0003 * frameLength * speed;

        xSpeed *= std::pow(0.995, frameLength);
        ySpeed *= std::pow(0.995, frameLength);
    } else {
        mode = EnemyMode::Attack;
        animationTimer_ = 0;
    }
}
