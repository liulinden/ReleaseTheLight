#include "Laser.h"
#include "Canvas.h"
#include "GlobalAssets.h"
#include "Util.h"
#include <cmath>
#include <algorithm>
#include <array>

namespace {
// Samples a nest's chosen art-variant hitbox mask at LOCAL coordinates
// (lx, ly), matching `n.resized_hitboxes[1].get_at((lx,ly))[3] > 128`.
// FLAGGED PERFORMANCE NOTE: rescales the hitbox BitMask to (size,size) on
// every call rather than caching it, since this is called potentially
// many times per laser tick (once per nearby nest per ray-march step
// that hits terrain). Per the note that this port doesn't need every
// section fully optimized yet, this is left simple/correct rather than
// adding a cache -- worth revisiting if laser-vs-nest performance
// actually matters once more of the game is wired up and profiled.
bool sampleNestHitboxAlpha(Nest& n, int lx, int ly) {
    int variantId = n.variantIdForCollision();
    if (variantId < 0) return false; // Sun nest -- no hitbox asset exists
    const Asset& hitboxAsset = GlobalAssets::getAsset("nest_" + std::to_string(variantId) + "_hitbox");
    BitMask scaled = hitboxAsset.mask.scaledTo(static_cast<int>(n.size), static_cast<int>(n.size));
    return scaled.get(lx, ly);
}
} // namespace

void Laser::init() {}

Laser::Laser() {}

// def get_laser_points(self, n_points): ...
std::vector<double> Laser::getLaserPoints(int /*nPointsIn*/) {
    int nPoints = std::max(3, 1 + static_cast<int>(std::round(length / 40.0)));
    double spacing = length / (nPoints - 1);

    std::vector<double> points;
    points.reserve(2 * nPoints - 2);
    points.push_back(0.0);
    for (int i = 0; i < nPoints - 2; ++i) {
        points.push_back(spacing * i + Util::randomDouble() * spacing);
    }
    points.push_back(length);
    for (int i = 0; i < nPoints - 2; ++i) {
        points.push_back(spacing * (nPoints - 3 - i) + Util::randomDouble() * spacing);
    }
    return points;
}

// def get_length(self, terrain, angle): -- see Laser.h for the two
// preserved bugs implemented here.
double Laser::getLength(Terrain& terrain, double angleIn) {
    hitboxes.clear();
    collision = CollisionInfo{};
    targetType = TargetType::None;
    target = nullptr;

    double dx = std::cos(angleIn);
    double dy = std::sin(angleIn);
    double step = step_;
    double distance = 0.0;

    while (distance < maxLength) {
        int wx = static_cast<int>(startX + dx * distance);
        int wy = static_cast<int>(startY + dy * distance);

        if (terrain.laserCollidePoint(wx, wy)) {
            Nest* hitNest = nullptr;
            for (Nest* n : terrain.nestsNear(wx, wy, 5)) {
                if (n->close(wx, wy, 5)) {
                    int l = (wx - static_cast<int>(n->left)) - 1;
                    int t = (wy - static_cast<int>(n->top)) - 1;
                    int r = l + 2;
                    int b = t + 2;

                    int lx = l, ly = t;
                    bool foundFirst = false;
                    for (lx = l; lx <= r; ++lx) {
                        for (int lyv : { t, b }) {
                            ly = lyv;
                            if (lx >= 0 && lx < static_cast<int>(n->size) && ly >= 0 && ly < static_cast<int>(n->size)) {
                                if (sampleNestHitboxAlpha(*n, lx, ly)) { hitNest = n; foundFirst = true; break; }
                            }
                        }
                        if (foundFirst) break;
                    }

                    // Second (buggy) loop -- see Laser.h class note: a
                    // single pass here is behaviorally identical to the
                    // Python's redundant (b-t+1)-times outer loop, since
                    // the outer iteration has no effect on the result.
                    for (int lyv : { l, r }) {
                        ly = lyv;
                        if (lx >= 0 && lx < static_cast<int>(n->size) && ly >= 0 && ly < static_cast<int>(n->size)) {
                            if (sampleNestHitboxAlpha(*n, lx, ly)) { hitNest = n; break; }
                        }
                    }

                    if (hitNest != nullptr) break;
                }
            }

            if (hitNest != nullptr) {
                collision = { true, static_cast<double>(wx), static_cast<double>(wy), "nests" };
                targetType = TargetType::Nest;
                target = hitNest;
            } else {
                bool hitEnemy = false;
                for (Nest* n : terrain.nestsNear(wx, wy, 500)) {
                    for (Enemy* enemy : n->enemies) {
                        // was: enemy.mode != "Spawn" (capital S) -- always
                        // true (case-mismatch bug; Enemy's mode is always
                        // lowercase). Preserved as always-true -- see
                        // Terrain::laserCollidePoint's matching note.
                        if (enemy->rectForCollision().collidePoint(wx, wy)) {
                            collision = { true, static_cast<double>(wx), static_cast<double>(wy), "enemies" };
                            targetType = TargetType::Enemy;
                            target = enemy;
                            hitEnemy = true;
                            break;
                        }
                    }
                    if (hitEnemy) break;
                }
                if (!hitEnemy) {
                    collision = { true, static_cast<double>(wx), static_cast<double>(wy), "ground" };
                }
            }
            break;
        }

        hitboxes.push_back({ static_cast<double>(wx), static_cast<double>(wy) });
        distance += step;
    }

    return distance + step / 2.0;
}

// def update_laser(self, terrain, start_x, start_y, angle, length=None, laser_cooldown=None): ...
bool Laser::updateLaser(Terrain& terrain, double startXIn, double startYIn, double angleIn,
                         std::optional<double> lengthIn, std::optional<double> laserCooldownIn) {
    startX = startXIn;
    startY = startYIn;
    angle = angleIn;
    length = getLength(terrain, angleIn);
    if (lengthIn) maxLength = *lengthIn * 15.0;
    if (laserCooldownIn) laserTime = *laserCooldownIn;
    return targetType != TargetType::None && targetType == previousTargetType && target == previousTarget;
}

// def tick(self, frame_length): ...
void Laser::tick(double frameLength) {
    sinWaveOffset += frameLength / 100.0;
    timer -= frameLength;
    damageFrame = false;
    if (timer <= 0) {
        timer = laserTime;
        laserPoints = getLaserPoints(6);
        laserPoints2 = getLaserPoints(6);
        damageFrame = true;
        previousTarget = target;
        previousTargetType = targetType;
    }
}

// def draw(self, surface, frame, color, hitboxes=False, offset_x=0, offset_y=0): ...
void Laser::draw(SDL_Renderer* renderer, const Frame& frame, Color color, bool hitboxesMode) {
    if (hitboxesMode) {
        for (auto& p : hitboxes) {
            Vec2 pos = frame.worldToScreen(p.x, p.y);
            int cx = static_cast<int>(pos.x);
            int cy = static_cast<int>(pos.y);
            int radius = std::max(2, static_cast<int>(frame.zoom * 2.0));
            Canvas::circle(renderer, { static_cast<double>(cx), static_cast<double>(cy) },
                            static_cast<double>(radius), color);
        }
        return;
    }

    for (auto* laserPartPtr : { &laserPoints, &laserPoints2 }) {
        auto& laserPart = *laserPartPtr;
        if (laserPart.empty()) continue; // defensive -- laser_points always has entries once tick() has run at least once
        double oglength = laserPart[laserPart.size() / 2];
        double scale = length / oglength;
        int halfSize = static_cast<int>(laserPart.size()) / 2;

        std::vector<Vec2> polygonPoints;
        polygonPoints.reserve(laserPart.size());
        for (size_t idx = 0; idx < laserPart.size(); ++idx) {
            double point = laserPart[idx];
            // was: if True or point <= self.length: -- always true, see
            // Laser.h class note; the else branch never executes.
            double waveHeight = thickness * std::sin((point + sinWaveOffset) * 1.5) * (0.5 + timer / laserTime);
            double x, y;
            if (static_cast<int>(idx) % halfSize == 0) {
                x = point * std::cos(angle) * scale;
                y = point * std::sin(angle) * scale;
            } else {
                x = point * std::cos(angle) * scale + waveHeight * std::sin(angle);
                y = point * std::sin(angle) * scale - waveHeight * std::cos(angle);
            }
            Vec2 screenPos = frame.worldToScreen(x + startX, y + startY);
            polygonPoints.push_back(screenPos);
        }

        if (polygonPoints.size() >= 3) {
            Canvas::polygon(renderer, polygonPoints, color);
        }
    }
}
