#include "Bouncer.h"
#include "Util.h"
#include <cmath>

Bouncer::Bouncer(SDL_Renderer* renderer, Color color, double size, double nestHealth, double x, double y)
    : Enemy(renderer, kCostume, color, x, y, size, nestHealth * kHealthFactor) {
    knockback = 0.3;
    damage = nestHealth * 0.5;
    knockbackResistance = 0.5;
    gravityMultiplier = 0.1;
    speed = 0.5;
}

// def attempt_movement(self, frame_length, _terrain): ...
// NOTE PRESERVED: only x_speed (not y_speed) gets zeroed at the end when
// the "backs" sub-step search exhausts without finding a collision --
// matches the Python exactly, asymmetric as it looks.
void Bouncer::attemptMovement(double frameLength, Terrain& terrain) {
    onGround = false;
    x += frameLength * xSpeed;
    y += frameLength * ySpeed;
    updateRect();
    if (collidingWithTerrain(terrain).hit) {
        x -= frameLength * xSpeed;
        y -= frameLength * ySpeed;
        int backs = static_cast<int>(std::ceil(frameLength * Util::dist(xSpeed, ySpeed)));
        for (int i = 0; i < backs; ++i) {
            x += frameLength * xSpeed / backs;
            y += frameLength * ySpeed / backs;
            updateRect();
            auto collision = collidingWithTerrain(terrain);
            if (collision.hit) {
                double collisionX = collision.x, collisionY = collision.y;

                x -= frameLength * xSpeed / backs;
                y -= frameLength * ySpeed / backs;
                updateRect();

                auto normal = terrain.getNormal(collisionX, collisionY);
                Vec2 bounced = Util::getBouncedVector({xSpeed, ySpeed}, {normal.first, normal.second});
                xSpeed = bounced.x;
                ySpeed = bounced.y;
                onGround = true;

                return;
            }
        }
        xSpeed = 0;
    }
}

// def tick_enemy_behavior(self, frame_length, player): ...
void Bouncer::tickEnemyBehavior(double frameLength, const EnemyPlayerView& player) {
    if (mode != EnemyMode::Walk) return;

    if (std::abs(player.x - x) > size / 2.0 || std::abs(player.y - y) > size / 2.0) {
        if (onGround && Util::randint(1, 50) < frameLength) {
            ySpeed = -0.2;
            int rnd = Util::randint(0, 3);
            if ((player.x < x && rnd != 3) || rnd == 0) xSpeed -= 0.2;
            else xSpeed += 0.2;
        } else {
            int rnd = Util::randint(0, 3);
            bool moveTowardNegX = (player.x < x && rnd != 3) || rnd == 0;
            double rate = onGround ? 0.001 : 0.0003;
            if (moveTowardNegX) xSpeed -= rate * frameLength * speed;
            else xSpeed += rate * frameLength * speed;
        }
    } else {
        mode = EnemyMode::Attack;
        animationTimer_ = 0;
    }

    if (onGround) {
        xSpeed *= std::pow(0.98, frameLength);
    }
}
