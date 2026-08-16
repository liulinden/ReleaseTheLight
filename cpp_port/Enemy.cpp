#include "Enemy.h"
#include "Canvas.h"
#include "BlendModes.h"
#include "GlobalAssets.h"
#include "Util.h"
#include <cmath>
#include <algorithm>
#include <string>

// was: costume_dimensions / enemy_attack_frames / enemy_animation_lengths
const CostumeInfo& costumeInfo(const std::string& costumeId) {
    static const std::unordered_map<std::string, CostumeInfo> table = {
        { "1", CostumeInfo{ 3.0 / 8.0, 3.0 / 4.0, {4, 5}, 6, 7, 9 } },
    };
    return table.at(costumeId);
}

// def init(): loads gradient_light + enemy_1_spawn_1..6/_walk_1..7/_attack_1..9/_attack_hitbox
void Enemy::init(SDL_Renderer* /*renderer*/) {
    GlobalAssets::getAsset("gradient_light");
    const CostumeInfo& ci = costumeInfo("1");
    for (int i = 1; i <= ci.spawnFrames; ++i) GlobalAssets::getAsset("enemy_1_spawn_" + std::to_string(i));
    for (int i = 1; i <= ci.walkFrames; ++i) GlobalAssets::getAsset("enemy_1_walk_" + std::to_string(i));
    for (int i = 1; i <= ci.attackAnimFrames; ++i) GlobalAssets::getAsset("enemy_1_attack_" + std::to_string(i));
    GlobalAssets::getAsset("enemy_1_attack_hitbox");
}

Enemy::Enemy(SDL_Renderer* renderer, const std::string& costume, Color colorIn,
             double xIn, double yIn, double sizeIn, double healthIn)
    : x(xIn), y(yIn), size(sizeIn), color(colorIn), health(healthIn), maxHealth(healthIn), damage(healthIn),
      costumeId_(costume), healthBar_(renderer, healthIn) {
    const CostumeInfo& ci = costumeInfo(costume);
    width = size * ci.widthFrac;
    height = size * ci.heightFrac;
    r_ = Util::dist(width / 2.0, height / 2.0);
    updateRect();
}

void Enemy::spawnParticles(Terrain& terrain) {
    terrain.particles.spawnMiningParticles(15, color, size / 3.0, x, y);
}

// def update_costume(self, frame_length, player): ...
void Enemy::updateCostume(double frameLength, const EnemyPlayerView& player) {
    glow += (0 - glow) / 500.0 * frameLength;
    animationTimer_ += frameLength;
    const CostumeInfo& ci = costumeInfo(costumeId_);

    if (mode == EnemyMode::Spawn) {
        if (animationTimer_ >= ci.spawnFrames * 1000.0 / kAnimationFps) {
            mode = EnemyMode::Walk;
            animationTimer_ = 0;
        }
    } else if (mode == EnemyMode::Walk) {
        animationTimer_ = std::fmod(animationTimer_, ci.walkFrames * 1000.0 / kAnimationFps);
    } else if (mode == EnemyMode::Attack) {
        if (animationTimer_ >= ci.attackAnimFrames * 1000.0 / kAnimationFps) {
            mode = EnemyMode::Walk;
            animationTimer_ = 0;
        }
    }

    if (mode == EnemyMode::Walk) {
        if (x < player.x) facing = Facing::Right;
        else if (x > player.x) facing = Facing::Left;
    }

    animationFrame_ = static_cast<int>(std::floor(animationTimer_ / (1000.0 / kAnimationFps)));
}

void Enemy::updateRect() {
    rect_.x = static_cast<int>(x - width / 2.0);
    rect_.y = static_cast<int>(y - height / 2.0);
    rect_.w = static_cast<int>(width);
    rect_.h = static_cast<int>(height);
}

// def draw_gradient(self, surface, frame, offset_x=0, offset_y=0): ...
void Enemy::drawGradient(SDL_Renderer* renderer, const Frame& frame) {
    if (glow <= 0) return;
    const Asset& gradientAsset = GlobalAssets::getAsset("gradient_light");
    double destSize = size * 2.0 * frame.zoom;

    // FIX (Tier 0 #1): was constructing a fresh RenderTarget (real
    // SDL_CreateTexture/DestroyTexture) on every call -- cached the same
    // way drawScratch_ already was, since this runs every frame for every
    // glowing enemy and glow decays slowly (persists for many seconds
    // after a hit or spawn).
    if (gradientScratchW_ != gradientAsset.width || gradientScratchH_ != gradientAsset.height) {
        gradientScratch_ = RenderTarget(renderer, gradientAsset.width, gradientAsset.height);
        gradientScratchW_ = gradientAsset.width;
        gradientScratchH_ = gradientAsset.height;
    }
    gradientScratch_.renderTo(renderer, [&] {
        gradientScratch_.clear({0, 0, 0, 0});
        Canvas::rectFilled(renderer, Rect{0, 0, gradientAsset.width, gradientAsset.height},
                            Color{color.r, color.g, color.b, static_cast<uint8_t>(std::clamp(glow, 0.0, 255.0))});
        Canvas::blit(renderer, gradientAsset.texture, 0, 0, gradientAsset.width, gradientAsset.height, BlendModes::rgbaMult());
    });

    Vec2 pos = frame.worldToScreen(x - size, y - size);
    Canvas::blit(renderer, gradientScratch_.texture(), pos.x, pos.y, destSize, destSize);
}

// def draw(self, surface, frame, hitbox=False, offset_x=0, offset_y=0): ...
void Enemy::draw(SDL_Renderer* renderer, const Frame& frame, bool hitbox) {
    updateRect();
    if (hitbox) {
        if (mode != EnemyMode::Spawn) {
            double l = rect_.x, r = rect_.x + rect_.w - 1, t = rect_.y, b = rect_.y + rect_.h - 1;
            Canvas::line(renderer, frame.worldToScreen(l, t), frame.worldToScreen(l, b), color);
            Canvas::line(renderer, frame.worldToScreen(r, t), frame.worldToScreen(r, b), color);
            Canvas::line(renderer, frame.worldToScreen(l, t), frame.worldToScreen(r, t), color);
            Canvas::line(renderer, frame.worldToScreen(l, b), frame.worldToScreen(r, b), color);
            // was: if self.mode == "Attack" (capital A -- never equals the
            // actual mode string "attack") and self.animation_frame in
            // self.attack_frames: self.draw_attack_hitbox(...) -- NEVER
            // EXECUTES in the original due to this case mismatch.
            // Preserved as an omission: an enum has no equivalent "typo"
            // failure mode, but the observable result (never drawing the
            // attack hitbox overlay in debug mode) is identical either way.
        }
        return;
    }

    std::string modeStr = (mode == EnemyMode::Spawn) ? "spawn" : (mode == EnemyMode::Walk) ? "walk" : "attack";
    std::string assetName = "enemy_" + costumeId_ + "_" + modeStr + "_" + std::to_string(animationFrame_ + 1);
    const Asset& frameAsset = GlobalAssets::getAsset(assetName);

    if (drawScratchW_ != frameAsset.width || drawScratchH_ != frameAsset.height) {
        drawScratch_ = RenderTarget(renderer, frameAsset.width, frameAsset.height);
        drawScratchW_ = frameAsset.width;
        drawScratchH_ = frameAsset.height;
    }
    drawScratch_.renderTo(renderer, [&] {
        drawScratch_.clear({0, 0, 0, 0});
        Canvas::rectFilled(renderer, Rect{0, 0, frameAsset.width, frameAsset.height}, color);
        Canvas::blit(renderer, frameAsset.texture, 0, 0, frameAsset.width, frameAsset.height,
                     BlendModes::rgbaMult(), facing == Facing::Left);
    });

    double destSize = size * frame.zoom;
    Vec2 pos = frame.worldToScreen(rect_.x + rect_.w / 2.0 - size / 2.0, rect_.y + rect_.h - size + 5);
    Canvas::blit(renderer, drawScratch_.texture(), pos.x, pos.y, destSize, destSize);
}

void Enemy::drawHealthBar(SDL_Renderer* renderer, const Frame& frame, int64_t timeMs) {
    Vec2 pos = frame.worldToScreen(rect_.x + rect_.w / 2.0, rect_.y + rect_.h - size + 5);
    healthBar_.draw(renderer, color, pos, health, timeMs);
}

// def draw_attack_hitbox(self, surface, frame, offset_x=0, offset_y=0): "never used"
void Enemy::drawAttackHitbox(SDL_Renderer* renderer, const Frame& frame) {
    const Asset& hitboxAsset = GlobalAssets::getAsset("enemy_" + costumeId_ + "_attack_hitbox");
    double destSize = size * frame.zoom;
    Vec2 pos = frame.worldToScreen(rect_.x + rect_.w / 2.0 - size / 2.0, rect_.y + rect_.h - size + 5);
    Canvas::blit(renderer, hitboxAsset.texture, pos.x, pos.y, destSize, destSize,
                 SDL_BLENDMODE_BLEND, facing == Facing::Left);
}

// def deal_damage(self, damage, direct=False): ...
bool Enemy::dealDamage(double dmg, bool direct) {
    glow = 255;
    health -= dmg;
    if (dmg > 0) healthBar_.trigger(direct);
    if (health < 0) {
        health = 0;
        return true;
    }
    return false;
}

// def tick_damage_and_knockback(self, frame_length, _terrain, player): ...
bool Enemy::tickDamageAndKnockback(double frameLength, Terrain& terrain, EnemyPlayerView& player) {
    for (auto& kc : terrain.knockbackCircles) {
        double dx = x - kc.x, dy = y - kc.y;
        double d = std::sqrt(dx * dx + dy * dy);
        if (player.laser.active) {
            if (player.laser.target == this) {
                xSpeed += frameLength * dx / d / size * kc.power / knockbackResistance;
                ySpeed += frameLength * dy / d / size * kc.power / knockbackResistance;
            } else if (d < kc.r + r_) {
                xSpeed += frameLength * dx / d / size * kc.power * kc.falloff / knockbackResistance;
                ySpeed += frameLength * dy / d / size * kc.power * kc.falloff / knockbackResistance;
            }
        } else if (d < kc.r + r_) {
            xSpeed += frameLength * dx / d / size * kc.power * kc.falloff / knockbackResistance;
            ySpeed += frameLength * dy / d / size * kc.power * kc.falloff / knockbackResistance;
        }
    }

    for (auto& dc : terrain.playerDamageCircles) {
        double dx = x - dc.x, dy = y - dc.y;
        double d = std::sqrt(dx * dx + dy * dy);
        if (player.laser.active) {
            if (player.laser.target == this) {
                terrain.particles.spawnMiningParticles(10, color, size / 5.0, dc.x, dc.y);
                if (dealDamage(dc.power, true)) return true;
            } else if (d < dc.r + r_) {
                terrain.particles.spawnMiningParticles(5, color, size / 10.0, dc.x, dc.y);
                if (dealDamage(dc.power * dc.falloff)) return true;
            }
        } else if (d < dc.r + r_) {
            terrain.particles.spawnMiningParticles(5, color, size / 10.0, dc.x, dc.y);
            if (dealDamage(dc.power * dc.falloff)) return true;
        }
    }
    return false;
}

void Enemy::tickGravity(double frameLength) {
    ySpeed = std::min(2.0, ySpeed + 0.0015 * frameLength * gravityMultiplier);
}

// def tick_enemy_behavior(self, frame_length, player): ...
void Enemy::tickEnemyBehavior(double frameLength, const EnemyPlayerView& player) {
    if (mode == EnemyMode::Walk) {
        if (player.y < y - 10 && onGround && Util::randint(1, 500) < frameLength) {
            ySpeed = -0.3;
        }
        if (std::abs(player.x - x) > size / 2.0 || std::abs(player.y - y) > size / 2.0) {
            int rnd = Util::randint(0, 3);
            bool moveTowardNegX = (player.x < x && rnd != 3) || rnd == 0;
            double rate = onGround ? 0.001 : 0.0003;
            if (moveTowardNegX) xSpeed -= rate * frameLength * speed;
            else xSpeed += rate * frameLength * speed;
        } else {
            mode = EnemyMode::Attack;
            animationTimer_ = 0;
        }

        xSpeed *= onGround ? std::pow(0.98, frameLength) : std::pow(0.993, frameLength);
    }
}

void Enemy::attemptMovement(double frameLength, Terrain& terrain) {
    moveVertical(frameLength, terrain);
    moveHorizontal(frameLength, terrain);
}

bool Enemy::checkDespawn(const EnemyPlayerView& player) const {
    return Util::dist(x - player.x, y - player.y) > 500.0;
}

// def handle_attack(self, player): ...
void Enemy::handleAttack(EnemyPlayerView& player) {
    if (player.immunityTimer == 0 && mode == EnemyMode::Attack) {
        const CostumeInfo& ci = costumeInfo(costumeId_);
        bool frameMatches = (animationFrame_ == ci.attackFrames[0] || animationFrame_ == ci.attackFrames[1]);
        if (frameMatches) {
            if (attackCollideRect(player.rect)) {
                player.immunityTimer = player.immunityTime;
                player.xSpeed = (facing == Facing::Right) ? knockback : -knockback;
                player.ySpeed = -knockback;
                player.dealDamage(damage);
            }
        }
    }
}

bool Enemy::tick(double frameLength, Terrain& terrain, EnemyPlayerView& player) {
    if (mode != EnemyMode::Spawn) {
        tickGravity(frameLength);
        if (tickDamageAndKnockback(frameLength, terrain, player)) return true;
        tickEnemyBehavior(frameLength, player);
        attemptMovement(frameLength, terrain);
        handleAttack(player);
        if (checkDespawn(player)) return true;
    }
    updateCostume(frameLength, player);
    return false;
}

// def move_horizontal(self, frame_length, _terrain): ...
void Enemy::moveHorizontal(double frameLength, Terrain& terrain) {
    x += frameLength * xSpeed;
    updateRect();
    if (collidingWithTerrain(terrain).hit) {
        int slopeTolerance = static_cast<int>(std::ceil(3 * std::abs(frameLength * xSpeed)));
        for (int i = 0; i < slopeTolerance; ++i) {
            y -= 1;
            updateRect();
            if (!collidingWithTerrain(terrain).hit) {
                xSpeed -= xSpeed * i / static_cast<double>(slopeTolerance);
                return;
            }
        }
        y += slopeTolerance;
        x -= frameLength * xSpeed;
        int backs = static_cast<int>(std::ceil(std::abs(frameLength * xSpeed / 1.0)));
        for (int i = 0; i < backs; ++i) {
            x += frameLength * xSpeed / backs;
            updateRect();
            if (collidingWithTerrain(terrain).hit) {
                x -= frameLength * xSpeed / backs;
                updateRect();
                break;
            }
        }
        xSpeed = 0;
    }
}

// def move_vertical(self, frame_length, _terrain): ...
void Enemy::moveVertical(double frameLength, Terrain& terrain) {
    onGround = false;
    y += frameLength * ySpeed;
    updateRect();
    auto collision = collidingWithTerrain(terrain);
    if (collision.hit) {
        if (ySpeed > 0) {
            onGround = true;
            if (!terrain.nestsCollideRect(rect_)) {
                int n = static_cast<int>(std::abs(
                    (std::abs(std::max(0.005 * frameLength, std::abs(xSpeed))) - 0.005 * frameLength)
                    + 3 * (ySpeed - 0.0015 * frameLength)) * 12);
                terrain.particles.spawnMiningParticles(n, Color{0, 0, 0, 255}, 20, x, y + height / 2.0, 200);
            }
        }
        if (ySpeed < 0) {
            int slopeTolerance = static_cast<int>(std::ceil(std::abs(0.5 * frameLength * ySpeed)));
            for (int i = 0; i < slopeTolerance; ++i) {
                x -= 1;
                updateRect();
                if (!collidingWithTerrain(terrain).hit) return;
            }
            x += slopeTolerance;
            for (int i = 0; i < slopeTolerance; ++i) {
                x += 1;
                updateRect();
                if (!collidingWithTerrain(terrain).hit) return;
            }
            x -= slopeTolerance;
        }
        y -= frameLength * ySpeed;
        int backs = static_cast<int>(std::ceil(std::abs(frameLength * ySpeed / 1.0)));
        for (int i = 0; i < backs; ++i) {
            y += frameLength * ySpeed / backs;
            updateRect();
            if (collidingWithTerrain(terrain).hit) {
                y -= frameLength * ySpeed / backs;
                updateRect();
                break;
            }
        }
        ySpeed = 0;
    }
}

Terrain::CollisionResult Enemy::collidingWithTerrain(Terrain& terrain) {
    return terrain.collideRect(rect_);
}

// def attack_collide_rect(self, rect): pixel-perfect mask overlap, ported
// using BitMask directly (no intermediate render-then-extract-mask
// roundabout needed, since asset masks are already available from
// AssetManager) -- same pixel-level result, simpler implementation.
bool Enemy::attackCollideRect(const Rect& rect) {
    const Asset& hitboxAsset = GlobalAssets::getAsset("enemy_" + costumeId_ + "_attack_hitbox");
    BitMask scaled = hitboxAsset.mask.scaledTo(static_cast<int>(size), static_cast<int>(size));
    BitMask attackMask = (facing == Facing::Left) ? scaled.flippedX() : scaled;

    int destX = static_cast<int>(rect_.x + rect_.w / 2.0 - size / 2.0 - rect.x);
    int destY = static_cast<int>(rect_.y + rect_.h - size - rect.y + 5);

    BitMask rectMask(rect.w, rect.h);
    rectMask.fill(true);
    return rectMask.overlaps(attackMask, destX, destY);
}
