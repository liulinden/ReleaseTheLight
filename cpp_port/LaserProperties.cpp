#include "LaserProperties.h"
#include <algorithm>
#include <cmath>

namespace {
int idx(ChargeType c) { return static_cast<int>(c); }
}

namespace LaserProperties {

// base = LaserAttributes(10, 0.8, 0.15, 20, 500, 1, 20, 0.3, 1, 20, 20, 0.5, 1.5, 0.5, {})
const LaserAttributes& base() {
    static LaserAttributes a = [] {
        LaserAttributes a;
        a.distance = 10; a.baseDmg = 0.8; a.baseKb = 0.15; a.baseXpl = 20; a.cooldown = 500;
        a.rampRate = 1; a.rampMax = 20; a.areaDmgFalloff = 0.3; a.areaKbFalloff = 1;
        a.dmgRange = 20; a.kbRange = 20;
        a.firstHitDmgMultiplier = 0.5; a.firstHitKbMultiplier = 1.5; a.firstHitXplMultiplier = 0.5;
        return a;
    }();
    return a;
}

// max_white = LaserAttributes(25, 1.2, 0.25, 40, 300, 1, 50, 0.3, 1, 30, 30, 0.5, 2, 0.5, {})
const LaserAttributes& maxWhite() {
    static LaserAttributes a = [] {
        LaserAttributes a;
        a.distance = 25; a.baseDmg = 1.2; a.baseKb = 0.25; a.baseXpl = 40; a.cooldown = 300;
        a.rampRate = 1; a.rampMax = 50; a.areaDmgFalloff = 0.3; a.areaKbFalloff = 1;
        a.dmgRange = 30; a.kbRange = 30;
        a.firstHitDmgMultiplier = 0.5; a.firstHitKbMultiplier = 2; a.firstHitXplMultiplier = 0.5;
        return a;
    }();
    return a;
}

// max_blue = LaserAttributes(30, 3, 0.8, 35, 400, 1, 20, 0.3, 1, 20, 50, 0.5, 3, 0.5, {})
const LaserAttributes& maxBlue() {
    static LaserAttributes a = [] {
        LaserAttributes a;
        a.distance = 30; a.baseDmg = 3; a.baseKb = 0.8; a.baseXpl = 35; a.cooldown = 400;
        a.rampRate = 1; a.rampMax = 20; a.areaDmgFalloff = 0.3; a.areaKbFalloff = 1;
        a.dmgRange = 20; a.kbRange = 50;
        a.firstHitDmgMultiplier = 0.5; a.firstHitKbMultiplier = 3; a.firstHitXplMultiplier = 0.5;
        return a;
    }();
    return a;
}

// max_red = LaserAttributes(8, 5, 0.15, 60, 500, 0.2, 20, 1, 1, 50, 20, 0.8, 1.5, 1, {})
const LaserAttributes& maxRed() {
    static LaserAttributes a = [] {
        LaserAttributes a;
        a.distance = 8; a.baseDmg = 5; a.baseKb = 0.15; a.baseXpl = 60; a.cooldown = 500;
        a.rampRate = 0.2; a.rampMax = 20; a.areaDmgFalloff = 1; a.areaKbFalloff = 1;
        a.dmgRange = 50; a.kbRange = 20;
        a.firstHitDmgMultiplier = 0.8; a.firstHitKbMultiplier = 1.5; a.firstHitXplMultiplier = 1;
        return a;
    }();
    return a;
}

// ability_thresholds = {"white": 200/500, "blue": 200/500, "red": 200/500}
double abilityThreshold(ChargeType) {
    return 200.0 / 500.0; // identical for all three today; kept as a per-color
                          // lookup (rather than one flat constant) matching the
                          // Python's per-key dict, in case they diverge later
}

// boost_thresholds = {"white": [180/500, 400/500], "blue": [120/500], "red": [120/500, 400/500]}
const std::vector<double>& boostThresholds(ChargeType c) {
    static const std::vector<double> white = {180.0 / 500.0, 400.0 / 500.0};
    static const std::vector<double> blue  = {120.0 / 500.0};
    static const std::vector<double> red   = {120.0 / 500.0, 400.0 / 500.0};
    switch (c) {
        case ChargeType::White: return white;
        case ChargeType::Blue:  return blue;
        case ChargeType::Red:   return red;
    }
    return white; // unreachable
}

void setLaserAttributes(LaserAttributes& attributes,
                         const std::array<double, 3>& charges,
                         FilterType activeFilter,
                         double maxCharge) {
    // for color in attributes.passed_thresholds: ...
    for (int c = 0; c < 3; ++c) {
        ChargeType ct = static_cast<ChargeType>(c);
        int nPassed = 0;
        double charge = charges[c] / maxCharge;
        for (double threshold : boostThresholds(ct)) {
            if (threshold <= charge) ++nPassed;
        }
        PassedThreshold& pt = attributes.passedThresholds[c];
        pt.count = nPassed;
        pt.passedAbility = pt.passedAbility || (charge > abilityThreshold(ct)); // sticky
    }

    double w = charges[idx(ChargeType::White)] / maxCharge;
    double b = charges[idx(ChargeType::Blue)]  / maxCharge;
    double r = charges[idx(ChargeType::Red)]   / maxCharge;

    const LaserAttributes& baseAttr = base();
    const LaserAttributes& whiteAttr = maxWhite();
    const LaserAttributes& blueAttr = maxBlue();
    const LaserAttributes& redAttr = maxRed();

    // for field in fields(attributes): value = base + w*(white-base) + b*(blue-base) + r*(red-base)
    // Generated once per field via the X-macro, matching the Python
    // reflection loop's effect field-by-field. `distance` truncates via
    // the type's own int assignment (matches Python's explicit int(value));
    // all other fields stay double, per the flagged note in the header.
#define X(name, type) \
    attributes.name = static_cast<type>( \
        baseAttr.name + w * (whiteAttr.name - baseAttr.name) \
                       + b * (blueAttr.name  - baseAttr.name) \
                       + r * (redAttr.name   - baseAttr.name));
    LASER_ATTR_FIELDS(X)
#undef X

    // match filter: ... (bonus effects gated on ever having crossed a boost threshold)
    switch (activeFilter) {
        case FilterType::White:
            if (attributes.passedThresholds[idx(ChargeType::White)].count >= 2)
                attributes.rampRate += 1;
            break;
        case FilterType::Blue:
            if (attributes.passedThresholds[idx(ChargeType::Blue)].count >= 1)
                attributes.firstHitKbMultiplier *= 1.5;
            break;
        case FilterType::Red:
            if (attributes.passedThresholds[idx(ChargeType::Red)].count >= 1)
                attributes.dmgRange += 30;
            break;
    }
}

double getLaserDmg(const LaserAttributes& a, bool firstHit, int ramps) {
    if (firstHit) return a.baseDmg * a.firstHitDmgMultiplier;
    return a.baseDmg * (1 + a.rampRate * std::min(a.rampMax, static_cast<double>(ramps)));
}

double getLaserKb(const LaserAttributes& a, bool firstHit, int /*ramps*/) {
    if (firstHit) return a.baseKb * a.firstHitKbMultiplier;
    return a.baseKb;
}

double getLaserExpl(const LaserAttributes& a, bool firstHit, int /*ramps*/) {
    if (firstHit) return a.baseXpl * a.firstHitXplMultiplier;
    return a.baseXpl;
}

} // namespace LaserProperties
