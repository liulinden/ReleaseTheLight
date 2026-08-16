#include "HealthBar.h"
#include "Canvas.h"
#include "Util.h"
#include "Time.h"
#include "Anchor.h"
#include <cmath>
#include <algorithm>

HealthBar* HealthBar::targeted = nullptr;

// self.thickness = thickness // 2 * 2 + 1  # thickness must be odd
// self.scale = 15 / max_health**0.8
// self.width = self.max_health * self.scale + self.thickness
// self.surface = pygame.Surface((self.width, self.thickness), pygame.SRCALPHA)
HealthBar::HealthBar(SDL_Renderer* renderer, double maxHealth, int thickness)
    : maxHealth_(maxHealth) {
    thickness_ = (thickness / 2) * 2 + 1;
    scale_ = 15.0 / std::pow(maxHealth, 0.8);
    width_ = maxHealth_ * scale_ + thickness_;
    surface_ = RenderTarget(renderer, static_cast<int>(std::ceil(width_)), thickness_);
}

// def trigger(self, direct=False):
//     self.last_triggered = pygame.time.get_ticks()
//     if direct: HealthBar.targeted = self
void HealthBar::trigger(bool direct) {
    lastTriggered_ = static_cast<double>(Time::nowMs());
    if (direct) HealthBar::targeted = this;
}

// def draw(self, surface, color, coords, health, time=None): ...
void HealthBar::draw(SDL_Renderer* renderer, Color color, Vec2 coords, double health, int64_t timeMs) {
    double time = (timeMs < 0) ? static_cast<double>(Time::nowMs()) : static_cast<double>(timeMs);
    double opacity = std::max(0.0, 255.0 - (time - lastTriggered_ - 500) / 2.0);
    if (opacity <= 0) return;

    surface_.renderTo(renderer, [&] {
        surface_.clear({0, 0, 0, 0});

        Vec2 p1{ thickness_ / 2.0, thickness_ / 2.0 };
        Vec2 p2{ width_ - thickness_ / 2.0, thickness_ / 2.0 };

        if (HealthBar::targeted == this) {
            Util::drawRoundedLine(renderer, color, p1, p2, thickness_);
            Util::drawRoundedLine(renderer, {0, 0, 0, 255}, p1, p2, thickness_ - 4);
        } else {
            Util::drawRoundedLine(renderer, {0, 0, 0, 255}, p1, p2, thickness_);
        }

        Vec2 healthEnd{ thickness_ / 2.0 + scale_ * health, thickness_ / 2.0 };
        Util::drawRoundedLine(renderer, color, p1, healthEnd, thickness_ - 4);
    });

    // left = x - scale*max_health/2 - thickness/2, top = y - thickness/2 in
    // the original -- algebraically exactly a Center anchor on a (width_,
    // thickness_) box, since scale_*maxHealth_/2 + thickness_/2 ==
    // width_/2 (width_ = maxHealth_*scale_ + thickness_). Using the shared
    // anchorOffset() helper here instead of re-deriving that by hand.
    Vec2 offset = anchorOffset(Anchor::Center, width_, thickness_);
    surface_.setAlpha(static_cast<uint8_t>(std::clamp(opacity, 0.0, 255.0)));
    Canvas::blit(renderer, surface_.texture(), coords.x + offset.x, coords.y + offset.y);
}
