#pragma once
#include <array>
#include <vector>
#include "Types.h"

// FLAGGED FOR REVIEW: dmg_range and kb_range are declared `int` in the
// Python dataclass, but set_laser_attributes() never casts them back to
// int after linear interpolation (only `distance` gets that treatment) --
// Python doesn't enforce dataclass type hints at runtime, so these fields
// silently hold fractional float values in practice, and downstream code
// (Cell.tick_knockback, damage-circle falloff) relies on that fractional
// precision. Declared `double` here to match actual behavior, not the
// (misleading) type hint. `distance` stays `int`, matching its real
// explicit int() cast in the Python.

// X-macro listing every field that gets linearly interpolated in
// setLaserAttributes, replacing Python's `for field in
// dataclasses.fields(attributes)` reflection loop. Trade-off flagged: this
// avoids hand-duplicating 14 fields across the struct definition and the
// interpolation loop (and the risk of the two silently drifting out of
// sync), at the cost of a little macro indirection. Say the word if you'd
// rather have this written out longhand instead.
#define LASER_ATTR_FIELDS(X) \
    X(distance,              int) \
    X(baseDmg,                double) \
    X(baseKb,                 double) \
    X(baseXpl,                double) \
    X(cooldown,                double) \
    X(rampRate,                double) \
    X(rampMax,                 double) \
    X(areaDmgFalloff,          double) \
    X(areaKbFalloff,           double) \
    X(dmgRange,                double) \
    X(kbRange,                 double) \
    X(firstHitDmgMultiplier,   double) \
    X(firstHitKbMultiplier,    double) \
    X(firstHitXplMultiplier,   double)

// was: passed_thresholds[color] = (n_passed, ...bool...)
struct PassedThreshold {
    int count = 0;
    bool passedAbility = false; // sticky -- once true, set_laser_attributes never clears it (matches Python's `or`)
};

struct LaserAttributes {
#define X(name, type) type name{};
    LASER_ATTR_FIELDS(X)
#undef X

    // was: passed_thresholds: dict, keyed "white"/"blue"/"red"
    std::array<PassedThreshold, 3> passedThresholds{}; // indexed by ChargeType
};

namespace LaserProperties {

// was: base, max_white, max_blue, max_red module-level constants
const LaserAttributes& base();
const LaserAttributes& maxWhite();
const LaserAttributes& maxBlue();
const LaserAttributes& maxRed();

// was: ability_thresholds = {"white": 0.4, "blue": 0.4, "red": 0.4}
double abilityThreshold(ChargeType c);

// was: boost_thresholds = {"white": [...], "blue": [...], "red": [...]}
const std::vector<double>& boostThresholds(ChargeType c);

// was: def set_laser_attributes(attributes, charges, filter, max_charge=500):
// `charges` indexed by ChargeType (was the {"white":.., "blue":.., "red":..} dict)
void setLaserAttributes(LaserAttributes& attributes,
                         const std::array<double, 3>& charges,
                         FilterType activeFilter,
                         double maxCharge = 500.0);

double getLaserDmg(const LaserAttributes& attributes, bool firstHit, int ramps);
double getLaserKb(const LaserAttributes& attributes, bool firstHit, int ramps);
double getLaserExpl(const LaserAttributes& attributes, bool firstHit, int ramps);

} // namespace LaserProperties
