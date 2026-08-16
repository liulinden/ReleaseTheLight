#pragma once
#include <memory>
#include <SDL.h>
#include "Core.h"
#include "Types.h"
#include "Enemy.h"
#include "Terrain.h"

// Ported from _enemy_handling.py.
//
// The Python builds enemy_sizes/enemy_costumes at MODULE IMPORT TIME via
// a loop reading each enemy class's `size_range`/`costume` class
// attributes:
//   for enemy in enemies: enemy_sizes[enemy] = enemy.size_range; ...
// This is real Python dynamic-class-attribute reflection running at
// import time, before main() even starts. C++ has no equivalent "runs at
// import" hook, and static-initialization order across translation units
// is a well-known footgun -- so rather than trying to replicate "runs
// implicitly at load time," this is an explicit lookup keyed off each
// subclass's own kSizeMin/kSizeMax/kCostume static constants (which
// already exist on BasicEnemy/BasicFlying/Bouncer). No behavior change:
// same data, just constructed explicitly instead of via import-time
// reflection.
namespace EnemyHandling {

// was: eligible_enemies = {"white": [BasicEnemy], "blue": [BasicEnemy,
// BasicFlying], "red": [BasicEnemy]}
enum class EnemyVariant { BasicEnemy_, BasicFlying_, Bouncer_ };

// was: def get_enemy(_terrain, player, nest_type, color, nest_health,
//                     nest_x, nest_y, nest_size)
// `player` reduced to just (playerX, playerY, playerRect) -- the only
// fields this function actually reads (never writes), so no adapter view
// needed here, unlike Enemy::tick's EnemyPlayerView.
// Returns nullptr on failure (was: return False), matching the 20-attempt
// retry-then-give-up structure exactly.
std::unique_ptr<Enemy> getEnemy(SDL_Renderer* renderer, Terrain& terrain,
                                 double playerX, double playerY, const Rect& playerRect,
                                 ChargeType nestType, Color color, double nestHealth,
                                 double nestX, double nestY, double nestSize);

} // namespace EnemyHandling
