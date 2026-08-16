#include "Cell.h"
#include "Canvas.h"
#include "GlobalAssets.h"
#include "Util.h"
#include <cmath>
#include <algorithm>
#include <iostream>
#include <string>

// def init(): global cell_imgs = {"shell": get_asset(...), "crackle_1..5": get_asset(...)}
void Cell::init(SDL_Renderer* /*renderer*/) {
    GlobalAssets::getAsset("cell_basic_shell");
    for (int i = 1; i <= 5; ++i) {
        GlobalAssets::getAsset("cell_basic_crackle_" + std::to_string(i));
    }
}

// def __init__(self, default_zooms, coords, velocities):
//     ...
//     self.r = dist(self.w, self.h)
//     self.interaction_display = InteractionDisplay((self.x, self.y+self.h/2), (pygame.K_e, ""))
Cell::Cell(SDL_Renderer* renderer, Vec2 coords, Vec2 velocities)
    : x_(coords.x), y_(coords.y), xSpeed_(velocities.x), ySpeed_(velocities.y),
      r_(Util::dist(kWidth, kHeight)),
      interactionDisplay_(renderer, {coords.x, coords.y + kHeight / 2.0}, DisplaySpec{ KeySeg(SDLK_e), TextSeg("") }) {
    updateRect();
}

// def tick_knockback(self, frame_length, _terrain, player): ...
bool Cell::tickKnockback(double frameLength, Terrain& terrain, const LaserTargetInfo& laserInfo) {
    bool affected = false;
    for (auto& kc : terrain.knockbackCircles) {
        double dx = x_ - kc.x, dy = y_ - kc.y;
        double d = Util::dist(dx, dy);
        if (laserInfo.active) {
            if (laserInfo.target == this) {
                xSpeed_ += frameLength * dx / d * kc.power / 30.0;
                ySpeed_ += frameLength * dy / d * kc.power / 30.0;
                affected = true;
            } else if (d < kc.r + r_) {
                xSpeed_ += frameLength * dx / d * kc.power * kc.falloff / 30.0;
                ySpeed_ += frameLength * dy / d * kc.power * kc.falloff / 30.0;
                affected = true;
            }
        } else if (d < kc.r + r_) {
            xSpeed_ += frameLength * dx / d * kc.power * kc.falloff / 30.0;
            ySpeed_ += frameLength * dy / d * kc.power * kc.falloff / 30.0;
            affected = true;
        }
    }
    return affected;
}

// def tick_gravity(self, frame_length): self.y_speed = min(2, self.y_speed + 0.0015*frame_length)
void Cell::tickGravity(double frameLength) {
    ySpeed_ = std::min(2.0, ySpeed_ + 0.0015 * frameLength);
}

// def _resolve_collision(...): PRESERVED, UNUSED -- see header note.
Vec2 Cell::resolveCollision(Vec2 velocity, Vec2 normal, double elasticity, double friction,
                             double frameLength, double bounceThreshold) {
    double vx = velocity.x, vy = velocity.y;
    double mag = Util::dist(normal.x, normal.y);
    if (mag == 0) return { vx, vy };

    double nx = normal.x / mag, ny = normal.y / mag;
    double normalSpeed = vx * nx + vy * ny;

    if (normalSpeed >= 0) return { vx, vy };
    if (std::abs(normalSpeed) > bounceThreshold) {
        return Util::getBouncedVector({vx, vy}, {nx, ny}, elasticity);
    }

    double tx = vx - normalSpeed * nx;
    double ty = vy - normalSpeed * ny;

    double speed = Util::dist(tx, ty);
    if (speed > 0) {
        double newSpeed = std::max(0.0, speed - friction * frameLength);
        double scale = newSpeed / speed;
        tx *= scale;
        ty *= scale;
    }
    return { tx, ty };
}

// def _find_clearance(self, _terrain, vx, vy, max_wiggle=2): ...
bool Cell::findClearance(Terrain& terrain, double vx, double vy, int maxWiggle) {
    double speed = Util::dist(vx, vy);
    double tx, ty;
    if (speed == 0) {
        tx = 0; ty = 1;
    } else {
        tx = -vy / speed; ty = vx / speed;
    }

    double origX = x_, origY = y_;

    for (int offset = 1; offset <= maxWiggle; ++offset) {
        for (int direction : {1, -1}) {
            x_ = origX + tx * offset * direction;
            y_ = origY + ty * offset * direction;
            updateRect();
            if (!collidingWithTerrain(terrain).hit) return true;
        }
    }

    x_ = origX; y_ = origY;
    updateRect();
    return false;
}

// def attempt_movement(self, frame_length, _terrain): -- see conversation
// notes for the subtle control-flow preserved here (the drag/remaining
// decrement at the bottom runs whenever we DON'T hit the nested
// `continue`, whether that's because there was no collision at all, or
// because a collision was resolved via successful clearance-finding).
void Cell::attemptMovement(double frameLength, Terrain& terrain) {
    const double elasticity = 0.4;
    const double friction = 0.97;
    const double drag = 0.993;
    const double absorption = 0.2;

    updateRect();
    auto collision = collidingWithTerrain(terrain);
    if (collision.hit) {
        std::cout << "started stuck" << std::endl;
        return;
    }

    double vx = xSpeed_, vy = ySpeed_;
    double dx = frameLength * vx, dy = frameLength * vy;
    double origX = x_, origY = y_;

    x_ += dx;
    y_ += dy;

    updateRect();
    collision = collidingWithTerrain(terrain);
    if (collision.hit) {
        if (!findClearance(terrain, vx, vy)) {
            x_ = origX; y_ = origY;
        } else {
            return;
        }
    } else {
        return;
    }

    double remaining = frameLength;
    while (remaining > 0) {
        double speed = Util::dist(vx, vy);
        if (speed == 0) return;
        double tickLength = std::min(remaining, 1.0 / speed);

        dx = vx * tickLength;
        dy = vy * tickLength;
        double ox = x_, oy = y_;

        x_ += dx;
        y_ += dy;

        updateRect();
        collision = collidingWithTerrain(terrain);
        if (collision.hit) {
            if (!findClearance(terrain, vx, vy)) {
                x_ = ox; y_ = oy;

                double collideX = collision.x, collideY = collision.y;
                auto normal = terrain.getNormal(collideX - Util::normalize1d(dx), collideY - Util::normalize1d(dy));

                double mag = Util::dist(normal.first, normal.second);
                if (mag == 0) {
                    std::cout << "something's fishy" << std::endl;
                    return;
                }
                double nx = normal.first / mag, ny = normal.second / mag;

                double scalar = nx * vx + ny * vy;
                vx -= scalar * nx;
                vy -= scalar * ny;
                vx *= std::pow(friction, tickLength);
                vy *= std::pow(friction, tickLength);
                if (-scalar > absorption) {
                    vx -= scalar * nx * elasticity;
                    vy -= scalar * ny * elasticity;
                }
                continue;
            }
        }
        vx *= std::pow(drag, tickLength);
        vy *= std::pow(drag, tickLength);

        remaining -= tickLength;
    }
    xSpeed_ = vx;
    ySpeed_ = vy;
}

// def tick(self, frame_length, _terrain, player): ...
void Cell::tick(double frameLength, Terrain& terrain, const LaserTargetInfo& laserInfo) {
    animationTimer_ = std::fmod(animationTimer_ + frameLength, 1000.0 / kAnimationFps * 5.0);
    frame_ = static_cast<int>(std::floor(animationTimer_ / (1000.0 / kAnimationFps))) + 1;

    if (tickKnockback(frameLength, terrain, laserInfo) || framesSinceMoved_ <= 2) {
        double lastX = x_, lastY = y_;
        tickGravity(frameLength);
        attemptMovement(frameLength, terrain);

        if (!(Util::aboutEqual(lastX, x_) && Util::aboutEqual(lastY, y_))) {
            interactionDisplay_.updateCoordinates({x_, y_ + h_ / 2.0});
            framesSinceMoved_ = 0;
        }
        framesSinceMoved_ += 1;
    }
}

void Cell::updateRect() {
    rect_.x = static_cast<int>(x_ - w_ / 2.0);
    rect_.y = static_cast<int>(y_ - h_ / 2.0);
    rect_.w = static_cast<int>(w_);
    rect_.h = static_cast<int>(h_);
}

Terrain::CollisionResult Cell::collidingWithTerrain(Terrain& terrain) {
    return terrain.collideRect(rect_);
}

// def draw(self, surface, frame, hitbox=False, offset_x=0, offset_y=0): ...
void Cell::draw(SDL_Renderer* renderer, const Frame& frame, bool hitbox) {
    updateRect();
    if (hitbox) {
        Vec2 pos = frame.worldToScreen(rect_.x, rect_.y);
        Canvas::rectOutline(renderer, Rect{
            static_cast<int>(pos.x), static_cast<int>(pos.y),
            static_cast<int>(w_ * frame.zoom), static_cast<int>(h_ * frame.zoom)
        }, Color{0, 0, 0, 255}, 2);
    } else {
        double destSize = size_ * frame.zoom;
        Vec2 pos = frame.worldToScreen(x_ - size_ / 2.0, y_ - size_ / 2.0);
        const Asset& shellAsset = GlobalAssets::getAsset("cell_basic_shell");
        const Asset& crackleAsset = GlobalAssets::getAsset("cell_basic_crackle_" + std::to_string(frame_));
        Canvas::blit(renderer, shellAsset.texture, pos.x, pos.y, destSize, destSize);
        Canvas::blit(renderer, crackleAsset.texture, pos.x, pos.y, destSize, destSize);
    }
}

bool Cell::withinInteractionRadius(Vec2 coords) const {
    double dx = coords.x - x_, dy = coords.y - y_;
    return Util::dist(dx, dy) < 50.0;
}

// def close(self, window_size, frame): ...
bool Cell::close(const Frame& frame) const {
    double xMargin = std::min(500.0, frame.viewWidth / frame.zoom / 2.0 + r_);
    double yMargin = std::min(400.0, frame.viewHeight / frame.zoom / 2.0 + r_);
    double cx = frame.left + frame.viewWidth / frame.zoom / 2.0;
    double cy = frame.top + frame.viewHeight / frame.zoom / 2.0;
    double dx = cx - x_, dy = cy - y_;
    return std::abs(dx) < xMargin && std::abs(dy) < yMargin;
}

// def validate_cell_coords(_terrain, coords): ...
bool validateCellCoords(Terrain& terrain, Vec2 coords) {
    Rect rect{
        static_cast<int>(coords.x - Cell::kWidth / 2.0),
        static_cast<int>(coords.y - Cell::kHeight / 2.0),
        static_cast<int>(Cell::kWidth),
        static_cast<int>(Cell::kHeight)
    };
    return !terrain.collideRect(rect).hit;
}
