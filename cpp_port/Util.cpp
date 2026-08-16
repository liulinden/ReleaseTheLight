#include "Util.h"
#include <random>

namespace Util {

// --- RNG -------------------------------------------------------------
// FLAGGED FOR YOUR REVIEW:
// The Python code uses the single global `random` module throughout
// (random.random(), random.randint(), etc.) via plain top-level calls in
// terrain.py, cells.py, _enemy.py, and others. There is no seeding call
// anywhere in the files you've sent, so the Python version is NOT
// reproducible run-to-run either -- we don't need bit-exact random
// sequences, just matching *distributions* and *call sites*.
//
// C++ has no single implicit global RNG the way Python's `random` module
// provides. I'm using a thread_local Mersenne Twister here so that:
//   (a) the background chunk-streaming thread (terrain.py's world-gen
//       calls random.randint/random.random heavily) doesn't contend on a
//       shared mutex-protected RNG for every call, and
//   (b) behavior still matches Python's usage pattern of "just call
//       random() from anywhere, get a fresh independent-looking value".
// If you'd rather have a single global RNG (e.g. for reproducibility
// with a fixed seed, for debugging/testing purposes), let me know now --
// swapping this out later would mean touching every call site again.
thread_local std::mt19937 rng{std::random_device{}()};

static double randomFloat() {
    // matches Python's random.random(): float in [0.0, 1.0)
    static thread_local std::uniform_real_distribution<double> dist(0.0, 1.0);
    return dist(rng);
}

double randomDouble() { return randomFloat(); }

int randint(int a, int b) {
    // matches Python's random.randint(a, b): inclusive on both ends
    std::uniform_int_distribution<int> dist(a, b);
    return dist(rng);
}

double frameRandom(double frameLength, double expectedPerSecond) {
    double p = std::min(1.0, frameLength / 1000.0 * expectedPerSecond);
    return randomFloat() < p;
}

Vec2 getBouncedVector(Vec2 vector, Vec2 normal, double elasticity) {
    double ax = vector.x, ay = vector.y;
    double bx = normal.x, by = normal.y;
    double factor = dist(bx, by);
    if (factor == 0.0) {
        return {0.0, 0.0};
    }
    bx /= factor;
    by /= factor;

    double s = bx * bx - by * by;
    double p = 2 * bx * by;

    double bouncedX = -ax * s - p * ay;
    double bouncedY = ay * s - p * ax;

    double f = (elasticity + 1) / 2;

    return { bouncedX * f + ax * (1 - f), bouncedY * f + ay * (1 - f) };
}

Color chargesToColor(double cw, double cb, double cr, double maxCharge, bool maximize) {
    double r = cr + cw / 3.0;
    double g = cw / 3.0 + cb / 8.0 + cr / 8.0;
    double b = cw / 3.0 + cb;

    // med = sorted((r, g, b))[1]  -- the middle value of the three
    double vals[3] = {r, g, b};
    std::sort(vals, vals + 3);
    double med = vals[1];

    double sum = r + g + b;
    if (sum == 0.0) {
        return {0, 0, 0, 255};
    }

    r = std::max(sum / 20.0, r + 2 * (r - med)) * 255.0 / sum;
    g = std::max(sum / 20.0, g + 2 * (g - med)) * 255.0 / sum;
    b = std::max(sum / 20.0, b + 2 * (b - med)) * 255.0 / sum;

    double frac = std::sqrt((cw + cb + cr) / maxCharge);
    double factor = frac * 5.0;
    if (maximize) {
        factor = std::max(factor, 3.0);
    }

    return rgbBound(r * factor, g * factor, b * factor);
}

} // namespace Util
