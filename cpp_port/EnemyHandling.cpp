#include "EnemyHandling.h"
#include "BasicEnemy.h"
#include "BasicFlying.h"
#include "Bouncer.h"
#include "Util.h"
#include <cmath>
#include <vector>

namespace EnemyHandling {

namespace {
// was: costume_dimensions -- only "1" exists; reused here for the
// width/height pre-check before actually constructing an enemy (matches
// the Python computing width/height from enemy_costumes[variant] before
// constructing anything).
constexpr double kCostume1WidthFrac = 3.0 / 8.0;
constexpr double kCostume1HeightFrac = 3.0 / 4.0;

// was: eligible_enemies = {"white": [BasicEnemy], "blue": [BasicEnemy,
// BasicFlying], "red": [BasicEnemy]}
const std::vector<EnemyVariant>& eligibleEnemies(ChargeType nestType) {
    static const std::vector<EnemyVariant> white = { EnemyVariant::BasicEnemy_ };
    static const std::vector<EnemyVariant> blue = { EnemyVariant::BasicEnemy_, EnemyVariant::BasicFlying_ };
    static const std::vector<EnemyVariant> red = { EnemyVariant::BasicEnemy_ };
    switch (nestType) {
        case ChargeType::White: return white;
        case ChargeType::Blue: return blue;
        case ChargeType::Red: return red;
    }
    return white; // unreachable
}

int sizeMin(EnemyVariant v) {
    switch (v) {
        case EnemyVariant::BasicEnemy_: return BasicEnemy::kSizeMin;
        case EnemyVariant::BasicFlying_: return BasicFlying::kSizeMin;
        case EnemyVariant::Bouncer_: return Bouncer::kSizeMin;
    }
    return 0;
}
int sizeMax(EnemyVariant v) {
    switch (v) {
        case EnemyVariant::BasicEnemy_: return BasicEnemy::kSizeMax;
        case EnemyVariant::BasicFlying_: return BasicFlying::kSizeMax;
        case EnemyVariant::Bouncer_: return Bouncer::kSizeMax;
    }
    return 0;
}

std::unique_ptr<Enemy> construct(EnemyVariant v, SDL_Renderer* renderer, Color color,
                                  double size, double nestHealth, double x, double y) {
    switch (v) {
        case EnemyVariant::BasicEnemy_: return std::make_unique<BasicEnemy>(renderer, color, size, nestHealth, x, y);
        case EnemyVariant::BasicFlying_: return std::make_unique<BasicFlying>(renderer, color, size, nestHealth, x, y);
        case EnemyVariant::Bouncer_: return std::make_unique<Bouncer>(renderer, color, size, nestHealth, x, y);
    }
    return nullptr; // unreachable
}
} // namespace

// def get_enemy(_terrain, player, nest_type, color, nest_health, nest_x, nest_y, nest_size): ...
std::unique_ptr<Enemy> getEnemy(SDL_Renderer* renderer, Terrain& terrain,
                                 double playerX, double playerY, const Rect& playerRect,
                                 ChargeType nestType, Color color, double nestHealth,
                                 double nestX, double nestY, double nestSize) {
    for (int i = 0; i < 20; ++i) {
        double angle = std::atan2(playerY - nestY, playerX - nestX) + (Util::randomDouble() * 2 - 1) * M_PI / 2.0;
        int r = Util::randint(static_cast<int>(nestSize / 2.0 - 10), static_cast<int>(nestSize / 2.0 + 10));
        int x = static_cast<int>(nestX + r * std::cos(angle));
        int y = static_cast<int>(nestY + r * std::sin(angle));

        const auto& eligible = eligibleEnemies(nestType);
        EnemyVariant variant = eligible[Util::randint(0, static_cast<int>(eligible.size()) - 1)];

        double size = Util::randint(sizeMin(variant), sizeMax(variant));
        double width = size * kCostume1WidthFrac;
        double height = size * kCostume1HeightFrac;

        Rect newEnemyRect{
            static_cast<int>(x - width / 2.0), static_cast<int>(y - height / 2.0),
            static_cast<int>(width), static_cast<int>(height)
        };

        if (!(terrain.collideRect(newEnemyRect).hit || newEnemyRect.collideRect(playerRect))) {
            auto newEnemy = construct(variant, renderer, color, size, nestHealth, x, y);
            newEnemy->spawnParticles(terrain);
            return newEnemy;
        }
    }
    return nullptr;
}

} // namespace EnemyHandling
