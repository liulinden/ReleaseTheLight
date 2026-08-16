#pragma once
#include <vector>
#include <string>
#include <optional>
#include <SDL.h>
#include "Core.h"
#include "Frame.h"
#include "Terrain.h"
#include "Nest.h"
#include "Enemy.h"
#include "Cell.h" // for LaserTargetInfo

// Ported from laser.py.
//
// TWO BUGS PRESERVED FAITHFULLY (both already flagged during earlier
// review of this file, now actually implemented):
//   1. get_length's nest-hit double loop: the second loop's outer `ly`
//      (`for ly in range(t, b+1)`) is immediately shadowed by the inner
//      loop's own `ly` (`for ly in (l, r)`), and `lx` is left at
//      whatever value the FIRST loop's for-variable landed on (Python
//      for-loop variables persist after the loop ends) rather than being
//      re-iterated. Since nothing checked in the second loop actually
//      depends on the outer iteration, running it its full (b-t+1) times
//      has NO effect on the outcome versus running it once -- so this is
//      implemented as a single pass rather than a literal (b-t+1)-times
//      loop, which is behaviorally identical, not a fidelity compromise.
//   2. draw()'s `if True or point <= self.length:` is always true, so the
//      else branch (recursive re-draw with fresh points) never executes.
//      Omitted here for the same reason as similar dead branches
//      elsewhere in this port (Enemy's "Attack"/"attack" case bug):
//      unreachable code has no C++ equivalent worth writing.
//
// Also note: the enemy-hit check iterates each NEARBY NEST's OWN
// enemies list (n.enemies), not terrain.enemies directly -- a real,
// specific detail of the original, not a simplification opportunity.
class Laser {
public:
    static void init(); // was: def init(): pass (impact images loaded elsewhere)

    Laser();

    // was: def get_laser_points(self, n_points) -- the n_points PARAMETER
    // is immediately overwritten by the Python body and its incoming
    // value is never used; kept here for signature parity but unused,
    // matching that quirk exactly.
    std::vector<double> getLaserPoints(int nPoints);

    // was: def get_length(self, terrain, angle) -> float
    double getLength(Terrain& terrain, double angleIn);

    // was: def update_laser(self, terrain, start_x, start_y, angle, length=None, laser_cooldown=None) -> bool
    bool updateLaser(Terrain& terrain, double startXIn, double startYIn, double angleIn,
                      std::optional<double> lengthIn = std::nullopt,
                      std::optional<double> laserCooldownIn = std::nullopt);

    // was: def tick(self, frame_length)
    void tick(double frameLength);

    // was: def draw(self, surface, frame, color, hitboxes=False, offset_x=0, offset_y=0)
    void draw(SDL_Renderer* renderer, const Frame& frame, Color color, bool hitboxes = false);

    // Convenience for callers (Player, once ported) building a
    // LaserTargetInfo from this laser's current target -- not in the
    // Python (which just accesses player.laser directly), but a trivial,
    // clearly-useful bridge to the adapter pattern used by Cell/Enemy.
    LaserTargetInfo asLaserTargetInfo() const { return { targetType != TargetType::None, target }; }

    double angle = 0.0, length = 0.0, startX = 0.0, startY = 0.0;
    double digSpeed = 1.0;
    double thickness = 5.0;
    std::vector<double> laserPoints, laserPoints2;
    double sinWaveOffset = 0.0;
    double timer = 0.0;
    double laserTime = 400.0;
    double maxLength = 400.0;

    // was: self.collision = [] | [(x, y), "nests"/"enemies"/"ground"]
    struct CollisionInfo {
        bool hit = false;
        double x = 0.0, y = 0.0;
        std::string type; // "nests" | "enemies" | "ground"
    };
    CollisionInfo collision;

    bool damageFrame = false;
    std::vector<Vec2> hitboxes; // was: self.hitboxes -- ray-march sample points along the beam

    // was: self.laser_target / self.previous_target -- could be a Nest OR
    // an Enemy (unrelated hierarchies, no common base), matching Python's
    // dynamic typing. Tagged opaque pointer, identity-comparable the same
    // way LaserTargetInfo::target already is used in Cell/Enemy.
    enum class TargetType { None, Nest, Enemy };
    TargetType targetType = TargetType::None;
    void* target = nullptr;
    TargetType previousTargetType = TargetType::None;
    void* previousTarget = nullptr;

private:
    double step_ = 1.0;
};
