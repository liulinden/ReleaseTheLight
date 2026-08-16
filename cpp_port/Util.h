#pragma once
#include <vector>
#include <algorithm>
#include <cmath>
#include <SDL.h>
#include "Core.h"
#include "Canvas.h"

namespace Util {

// def safe_remove(list, item): ...
template <typename T>
bool safeRemove(std::vector<T>& list, const T& item) {
    auto it = std::find(list.begin(), list.end(), item);
    if (it != list.end()) {
        list.erase(it);
        return true;
    }
    return false;
}

// def safe_append(list, item): ...
template <typename T>
bool safeAppend(std::vector<T>& list, const T& item) {
    if (std::find(list.begin(), list.end(), item) == list.end()) {
        list.push_back(item);
        return true;
    }
    return false;
}

// def dist(x, y): return math.dist((0, 0), (x, y))
inline double dist(double x, double y) {
    return std::sqrt(x * x + y * y);
}

// def frame_random(frame_length, expected_per_second):
//     return random.random() < min(1, frame_length / 1000 * expected_per_second)
// NOTE: RNG design choice flagged in Util.cpp -- please review.
double frameRandom(double frameLength, double expectedPerSecond);

// Matches Python's random.randint(a, b): inclusive on both ends.
// Used throughout terrain.py, cells.py, _enemy.py, etc. in place of the
// many bare `random.randint(...)` calls in the original.
int randint(int a, int b);

// Matches Python's random.random(): float in [0.0, 1.0). Used in place
// of bare `random.random()` calls (particles.py's mining-particle
// scatter angle/speed, etc.).
double randomDouble();

// def normalize_1d(n): ...
inline int normalize1d(double n) {
    if (n > 0) return 1;
    if (n < 0) return -1;
    return 0;
}

// def about_equal(a, b, threshold=0.01):
//     diff = a - b
//     return diff < threshold and diff > -threshold
inline bool aboutEqual(double a, double b, double threshold = 0.01) {
    double diff = a - b;
    return diff < threshold && diff > -threshold;
}

// Python's `%` on floats always returns a result with the same sign as
// the divisor (e.g. (-1.0) % (2*M_PI) == 2*M_PI - 1, not -1). C++'s
// std::fmod instead follows the sign of the DIVIDEND -- a real semantic
// difference, not a style choice. Several angle-wrapping call sites
// throughout the port (ChargeDisplay's filter-indicator angles, and
// likely more as we go) rely on Python's convention, so this replaces
// raw fmod() wherever that matters, rather than re-deriving the fix at
// each call site.
inline double pyMod(double a, double b) {
    double r = std::fmod(a, b);
    if (r != 0.0 && ((r < 0.0) != (b < 0.0))) r += b;
    return r;
}

// def polar_to_rect(r, angle, center=(0, 0)):
//     return r * math.cos(angle) + center[0], r * math.sin(angle) + center[1]
inline Vec2 polarToRect(double r, double angle, Vec2 center = {0.0, 0.0}) {
    return { r * std::cos(angle) + center.x, r * std::sin(angle) + center.y };
}

// def multiply_tuple(tuple_, factor):
//     return tuple(entry * factor for entry in tuple_)
// Original is used on both RGB tuples and other numeric tuples. Since our
// Color type is a distinct struct (not a generic tuple), we provide a
// Color-specific overload here. If a non-color numeric tuple use turns up
// elsewhere, we'll add a matching overload at that call site rather than
// generalizing prematurely.
inline Color multiplyColor(const Color& c, double factor) {
    // Preserves the Python version's lack of clamping/rounding here --
    // channel_bound()/rgb_bound() are applied separately at call sites in
    // the original, not inside multiply_tuple itself. We match that: no
    // clamping here either. Truncation on assignment to uint8_t mirrors
    // Python's implicit float->int surface fill behavior in pygame.
    return {
        static_cast<uint8_t>(c.r * factor),
        static_cast<uint8_t>(c.g * factor),
        static_cast<uint8_t>(c.b * factor),
        c.a
    };
}

// def get_bounced_vector(vector, normal, elasticity=1): ...
Vec2 getBouncedVector(Vec2 vector, Vec2 normal, double elasticity = 1.0);

// def rgb_bound(color): return (channel_bound(r), channel_bound(g), channel_bound(b))
// def channel_bound(value): return min(255, max(0, value))
inline double channelBound(double value) {
    return std::min(255.0, std::max(0.0, value));
}
inline Color rgbBound(double r, double g, double b) {
    return {
        static_cast<uint8_t>(channelBound(r)),
        static_cast<uint8_t>(channelBound(g)),
        static_cast<uint8_t>(channelBound(b)),
        255
    };
}

// def charges_to_color(cw, cb, cr, max_charge=500, maximize=False): ...
Color chargesToColor(double cw, double cb, double cr, double maxCharge = 500.0, bool maximize = false);

// def draw_rounded_line(surface, color, start, end, thickness):
//     pygame.draw.line(surface, color, start, end, thickness)
//     pygame.draw.circle(surface, color, start, thickness // 2)
//     pygame.draw.circle(surface, color, end, thickness // 2)
inline void drawRoundedLine(SDL_Renderer* renderer, Color color, Vec2 start, Vec2 end, int thickness) {
    Canvas::line(renderer, start, end, color, thickness);
    Canvas::circle(renderer, start, thickness / 2, color);
    Canvas::circle(renderer, end, thickness / 2, color);
}

// def draw_single_side_rounded_line(surface, color, start, end, thickness):
//     # thickness should be odd
//     pygame.draw.line(surface, color, start, end, thickness)
//     pygame.draw.circle(surface, color, end, thickness / 2)
inline void drawSingleSideRoundedLine(SDL_Renderer* renderer, Color color, Vec2 start, Vec2 end, int thickness) {
    Canvas::line(renderer, start, end, color, thickness);
    Canvas::circle(renderer, end, thickness / 2.0, color);
}

// ImageCache and rotate_and_get_offset deliberately NOT ported:
//   - ImageCache existed purely to avoid repeated pygame.transform.scale
//     cost; we scale at draw time on the GPU now (see AssetManager/scaling
//     decision), so there's nothing left for it to cache.
//   - rotate_and_get_offset's job (rotate + compute the pivot-corrected
//     blit offset) is handled by SDL_RenderCopyEx's built-in center/angle
//     parameters once we're doing real texture draws (Player's arm,
//     LaserImpact, screen tilt) -- I'll verify SDL_RenderCopyEx's pivot
//     math matches this function's custom pivot calculation exactly
//     when we reach those call sites, rather than assume equivalence.

} // namespace Util
