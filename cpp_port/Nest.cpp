#include "Nest.h"
#include "Canvas.h"
#include "BlendModes.h"
#include "GlobalAssets.h"
#include "Util.h"
#include "EnemyHandling.h"
#include <cmath>
#include <algorithm>
#include <stdexcept>
#include <iostream>

ChargeType nestTypeToChargeType(NestType type) {
    switch (type) {
        case NestType::White: return ChargeType::White;
        case NestType::Blue: return ChargeType::Blue;
        case NestType::Red: return ChargeType::Red;
        case NestType::Sun:
            // Python's eligible_enemies dict has no "sun" key -- calling
            // get_enemy for a sun-type nest raises KeyError there.
            // Preserved as an equally loud failure here.
            throw std::runtime_error("nestTypeToChargeType: NestType::Sun has no corresponding ChargeType "
                                      "(matches Python's KeyError on eligible_enemies['sun'])");
    }
    throw std::runtime_error("unreachable");
}

namespace {
struct NestVariantInfo {
    int stages;
    std::vector<int> variantIds;
};
// was: [("white", 4, [1,2,3,4]), ("blue", 5, [5,6]), ("red", 5, [5,6]), ("sun", 10, [])]
const NestVariantInfo& nestVariantInfo(NestType type) {
    static const NestVariantInfo white{ 4, {1, 2, 3, 4} };
    static const NestVariantInfo blue{ 5, {5, 6} };
    static const NestVariantInfo red{ 5, {5, 6} };
    static const NestVariantInfo sun{ 10, {} };
    switch (type) {
        case NestType::White: return white;
        case NestType::Blue: return blue;
        case NestType::Red: return red;
        case NestType::Sun: return sun;
    }
    return white; // unreachable
}

double computeMaxHealth(NestType type, double y, double worldHeight) {
    double maxHealth = y * 200.0 * (Util::randomDouble() + 0.5) / worldHeight;
    switch (type) {
        case NestType::White: maxHealth *= 1.2; maxHealth += 10.0; break;
        case NestType::Blue:
        case NestType::Red: maxHealth += 50.0; break;
        case NestType::Sun: maxHealth += 1000.0; break;
    }
    return maxHealth;
}

// was: charges_to_color(*self.charging.values(), 500, maximize=True) --
// computed here (before the real `charging` member is set, since it's
// needed for interactionDisplay's constructor in the init list) from the
// same "all zero except own slot = 1" rule.
Color initialChargingColor(NestType type) {
    std::array<double, 3> charging = {0.0, 0.0, 0.0};
    if (type != NestType::Sun) charging[static_cast<int>(nestTypeToChargeType(type))] = 1.0;
    return Util::chargesToColor(charging[0], charging[1], charging[2], 500.0, true);
}
} // namespace

// def init(): loads gradient_light + nest_<variant>_<stage> / nest_<variant>_hitbox
void Nest::init(SDL_Renderer* /*renderer*/) {
    GlobalAssets::getAsset("gradient_light");
    for (NestType t : { NestType::White, NestType::Blue, NestType::Red, NestType::Sun }) {
        const NestVariantInfo& info = nestVariantInfo(t);
        for (int variant : info.variantIds) {
            for (int stage = 1; stage <= info.stages; ++stage) {
                GlobalAssets::getAsset("nest_" + std::to_string(variant) + "_" + std::to_string(stage));
            }
            GlobalAssets::getAsset("nest_" + std::to_string(variant) + "_hitbox");
        }
    }
}

// def __init__(self, default_zooms, world_height, nest_type, x, y, size): ...
Nest::Nest(SDL_Renderer* renderer, NestType type, double worldHeight, double xIn, double yIn, double sizeIn)
    : x(xIn), y(yIn), left(xIn - sizeIn / 2.0), top(yIn - sizeIn / 2.0), size(sizeIn), nestType(type),
      maxStage(nestVariantInfo(type).stages - 1),
      maxHealth(computeMaxHealth(type, yIn, worldHeight)),
      interactionDisplay(renderer, {xIn, top + sizeIn * 0.75},
                          DisplaySpec{ TextSeg("Hold"), KeySeg(SDLK_e), TextSeg("to drain") },
                          initialChargingColor(type)),
      healthBar_(renderer, maxHealth) {
    health = maxHealth;
    maxCharge = maxHealth / 3.0 + 100.0;
    visualCharge = maxCharge;
    charge = maxCharge * 0.5;
    chargeRate = maxCharge / 10000.0;

    charging.fill(0.0);
    if (type != NestType::Sun) {
        charging[static_cast<int>(nestTypeToChargeType(type))] = 1.0;
    }
    // else: charging stays all-zero -- Sun has no valid ChargeType slot;
    // see class-level note on Sun being effectively non-functional here.

    const NestVariantInfo& info = nestVariantInfo(type);
    if (!info.variantIds.empty()) {
        variantId_ = info.variantIds[Util::randint(0, static_cast<int>(info.variantIds.size()) - 1)];
    }
    // else (Sun): variantId_ stays -1 -- matches Python's
    // random.randint(0, len([])-1) == random.randint(0, -1) crash-in-
    // waiting; drawing/using a Sun nest will fail loudly if ever attempted.
}

Rect Nest::getRect() const {
    return Rect{ static_cast<int>(left), static_cast<int>(top), static_cast<int>(size), static_cast<int>(size) };
}

// def update_color(self):
//     cw, cb, cr = self.charging.values()
//     cw, cb, cr = cw*self.visual_charge, cb*self.visual_charge, cr*self.visual_charge
//     self.color = charges_to_color(cw, cb, cr, 500)
void Nest::updateColor() {
    double cw = charging[static_cast<int>(ChargeType::White)] * visualCharge;
    double cb = charging[static_cast<int>(ChargeType::Blue)] * visualCharge;
    double cr = charging[static_cast<int>(ChargeType::Red)] * visualCharge;
    color = Util::chargesToColor(cw, cb, cr, 500.0);
}

// def lose_charge(self, loss): self.glow = 255; self.charge -= loss; if self.charge < 0: self.charge = 0
void Nest::loseCharge(double loss) {
    glow = 255.0;
    charge -= loss;
    if (charge < 0) {
        charge = 0.0;
        // was: `...` (an empty ellipsis placeholder in the Python) -- no-op, preserved as such.
    }
}

// def update_visuals(self, frame_length): ...
void Nest::updateVisuals(double frameLength) {
    if (charge == 0 && visualCharge != 0) {
        visualCharge *= std::pow(0.99, frameLength);
        std::cout << visualCharge << std::endl; // preserved debug print, matches Python
        if (visualCharge < 1) visualCharge = 0;
    }
    glow += ((stage / static_cast<double>(maxStage) * visualCharge / maxCharge * 150.0) - glow) / 1500.0 * frameLength;
}

// def draw_gradient(self, surface, frame, offset_x=0, offset_y=0): ...
void Nest::drawGradient(SDL_Renderer* renderer, const Frame& frame) {
    if (glow <= 0) return;
    const Asset& gradientAsset = GlobalAssets::getAsset("gradient_light");
    double destSize = size * frame.zoom;

    // FIX (Tier 0 #1): cached, was allocating a fresh RenderTarget every call.
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

    Vec2 pos = frame.worldToScreen(left, top);
    Canvas::blit(renderer, gradientScratch_.texture(), pos.x, pos.y, destSize, destSize);
}

// def draw(self, surface, frame, hitbox=False, offset_x=0, offset_y=0): ...
void Nest::draw(SDL_Renderer* renderer, const Frame& frame, bool hitbox) {
    std::string assetName = hitbox
        ? "nest_" + std::to_string(variantId_) + "_hitbox"
        : "nest_" + std::to_string(variantId_) + "_" + std::to_string(stage + 1);
    const Asset& img = GlobalAssets::getAsset(assetName);

    updateColor();

    if (drawScratchW_ != img.width || drawScratchH_ != img.height) {
        drawScratch_ = RenderTarget(renderer, img.width, img.height);
        drawScratchW_ = img.width;
        drawScratchH_ = img.height;
    }
    drawScratch_.renderTo(renderer, [&] {
        drawScratch_.clear({0, 0, 0, 0});
        Canvas::rectFilled(renderer, Rect{0, 0, img.width, img.height}, color);
        Canvas::blit(renderer, img.texture, 0, 0, img.width, img.height, BlendModes::rgbaMult());
    });

    double destSize = size * frame.zoom;
    Vec2 pos = frame.worldToScreen(left, top);
    Canvas::blit(renderer, drawScratch_.texture(), pos.x, pos.y, destSize, destSize);
}

// def draw_health_bar(self, surface, frame, time=None, offset_x=0, offset_y=0): ...
void Nest::drawHealthBar(SDL_Renderer* renderer, const Frame& frame, int64_t timeMs) {
    if (stage == maxStage) return;
    Vec2 pos = frame.worldToScreen(x, top);
    healthBar_.draw(renderer, color, pos, health, timeMs);
}

// def add_enemy(self, c_terrain, player): ...
void Nest::addEnemy(SDL_Renderer* renderer, Terrain& terrain, double playerX, double playerY, const Rect& playerRect) {
    if (static_cast<int>(enemies.size()) < basicEnemyCap) {
        ChargeType ct = nestTypeToChargeType(nestType); // throws for Sun -- see class note
        auto newEnemy = EnemyHandling::getEnemy(renderer, terrain, playerX, playerY, playerRect,
                                                 ct, color, maxHealth, x, y, size);
        if (newEnemy) {
            glow = 200.0;
            Enemy* rawPtr = newEnemy.get();
            enemies.push_back(rawPtr);
            terrain.addEnemy(std::move(newEnemy));
        }
    }
}

bool Nest::withinEffectRadius(double px, double py) const {
    return Util::dist(px - x, py - y) < size * 1.5;
}

// def apply_damage_from_circles(self, c_terrain, player): ...
std::vector<Nest::DamageParticleSpec> Nest::applyDamageFromCircles(SDL_Renderer* renderer, Terrain& terrain,
                                                                     const LaserTargetInfo& laser,
                                                                     double playerX, double playerY, const Rect& playerRect) {
    std::vector<DamageParticleSpec> newParticles;
    if (health > 0) {
        for (auto& circle : terrain.playerDamageCircles) {
            if (close(circle.x, circle.y, circle.r)) {
                bool directHit = laser.active && (laser.target == this);
                double damage = directHit ? circle.power : circle.power * circle.falloff;
                dealDamage(damage, renderer, terrain, playerX, playerY, playerRect);
                newParticles.push_back({ circle.x, circle.y, size / (directHit ? 5.0 : 10.0) });
                healthBar_.trigger(directHit);
            }
        }
    }
    return newParticles;
}

// def deal_damage(self, damage, c_terrain, player): ...
void Nest::dealDamage(double damage, SDL_Renderer* renderer, Terrain& terrain,
                       double playerX, double playerY, const Rect& playerRect) {
    glow = 200.0;
    health -= damage;
    if (health < 0) {
        health = 0.0;
        for (Enemy* enemy : enemies) {
            enemy->spawnParticles(terrain);
            terrain.removeEnemy(enemy);
        }
        enemies.clear();
    }
    int newStage = updateStage();
    if (newStage != -1) {
        if (stage != maxStage) {
            for (int i = 0; i < 3; ++i) {
                addEnemy(renderer, terrain, playerX, playerY, playerRect);
            }
        }
    }
}

// def update_stage(self):
//     new_stage = self.max_stage - math.ceil((self.max_stage-1) * self.health / self.max_health)
//     if new_stage != self.stage:
//         self.stage = new_stage
//         self.basic_enemy_cap = math.floor(self.stage * 4)
//         return new_stage
//     return False
int Nest::updateStage() {
    int newStage = maxStage - static_cast<int>(std::ceil((maxStage - 1) * health / maxHealth));
    if (newStage != stage) {
        stage = newStage;
        basicEnemyCap = static_cast<int>(std::floor(stage * 4));
        return newStage;
    }
    return -1;
}

bool Nest::close(double px, double py, double radius) const {
    return std::abs(x - px) < radius + size / 2.0 && std::abs(y - py) < radius + size / 2.0;
}
