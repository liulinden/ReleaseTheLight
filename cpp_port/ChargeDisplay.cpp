#include "ChargeDisplay.h"
#include "Canvas.h"
#include "BlendModes.h"
#include "Util.h"
#include "GlobalAssets.h"
#include <cmath>
#include <algorithm>
#include <string>

namespace {
constexpr double kAnimationFps = 12.0;
constexpr double kTlX = 20.0, kTlY = 30.0;
constexpr double kDisplaySize = 250.0;
constexpr double kCellDisplaySize = kDisplaySize * 0.22;
constexpr double kChargeIconSize = kDisplaySize * 0.62;

constexpr int idx(ChargeType c) { return static_cast<int>(c); }
// FilterType and ChargeType share member order (White=0, Blue=1, Red=2)
// by design (see Types.h) -- this converts a FilterType to the matching
// ChargeType array index wherever "the currently active filter" needs to
// index into a charges_/filters_ array.
constexpr int filterAsChargeIdx(FilterType f) { return static_cast<int>(f); }

// was: order_charges = {"white": (["white","blue","red"], []),
//                        "blue": (["blue","white"], ["red"]),
//                        "red": (["red","white"], ["blue"])}
std::pair<std::vector<ChargeType>, std::vector<ChargeType>> orderCharges(FilterType f) {
    switch (f) {
        case FilterType::White: return { {ChargeType::White, ChargeType::Blue, ChargeType::Red}, {} };
        case FilterType::Blue:  return { {ChargeType::Blue, ChargeType::White}, {ChargeType::Red} };
        case FilterType::Red:   return { {ChargeType::Red, ChargeType::White}, {ChargeType::Blue} };
    }
    return { {}, {} }; // unreachable
}

std::vector<ChargeType> fullChargeOrder(FilterType f) {
    auto pr = orderCharges(f);
    std::vector<ChargeType> result = pr.first;
    result.insert(result.end(), pr.second.begin(), pr.second.end());
    return result;
}

// was: match filter_type: case "white": order = ("white","blue","red") ...
// (a DIFFERENT ordering than order_charges above -- this one is used only
// for the filter-indicator angle targets in update())
std::array<ChargeType, 3> filterAngleOrder(FilterType f) {
    switch (f) {
        case FilterType::White: return { ChargeType::White, ChargeType::Blue, ChargeType::Red };
        case FilterType::Blue:  return { ChargeType::Blue, ChargeType::Red, ChargeType::White };
        case FilterType::Red:   return { ChargeType::Red, ChargeType::White, ChargeType::Blue };
    }
    return {};
}
} // namespace

// def get_diamond_points(center, angle): ...
std::vector<Vec2> chargeDiamondPoints(Vec2 center, double angle) {
    return {
        Util::polarToRect(kDisplaySize * 0.43, angle - M_PI * 0.5, center),
        Util::polarToRect(kDisplaySize * 0.5,  angle - M_PI * 0.53, center),
        Util::polarToRect(kDisplaySize * 0.59, angle - M_PI * 0.5, center),
        Util::polarToRect(kDisplaySize * 0.5,  angle - M_PI * 0.47, center),
    };
}

// def get_outer_triangle_points(center, angle): ...
std::vector<Vec2> chargeOuterTrianglePoints(Vec2 center, double angle) {
    return {
        Util::polarToRect(kDisplaySize * 0.57, angle - M_PI * 0.5, center),
        Util::polarToRect(kDisplaySize * 0.5,  angle - M_PI * 0.52, center),
        Util::polarToRect(kDisplaySize * 0.5,  angle - M_PI * 0.48, center),
    };
}

ChargeDisplay::ChargeDisplay(SDL_Renderer* renderer) : renderer_(renderer) {
    const Asset& icon = GlobalAssets::getAsset("UI_charge_icon");
    const Asset& shell = GlobalAssets::getAsset("cell_basic_shell_outlined");
    iconScratch_ = RenderTarget(renderer, icon.width, icon.height);
    cellScratch_ = RenderTarget(renderer, shell.width, shell.height);
}

void ChargeDisplay::update(double fps, const PlayerChargeSnapshot& player) {
    double frameLength = 1000.0 / fps;
    animationTimer_ = std::fmod(animationTimer_ + frameLength, 1000.0 / kAnimationFps * 5.0);
    frame_ = static_cast<int>(std::floor(animationTimer_ / (1000.0 / kAnimationFps))) + 1;

    chargeCapacity_ = player.chargeCapacity;
    const std::array<double, 3>& playerChargesNow = player.charges;

    if (player.filterType != filterType_) {
        filterType_ = player.filterType;
        rotationGoal_ += 1.0;
    }
    filterPresent_[filterAsChargeIdx(filterType_)] = true;

    double totalCharge = playerChargesNow[0] + playerChargesNow[1] + playerChargesNow[2];
    double totalChargeChange = totalCharge - playerTotalCharge_;
    playerTotalCharge_ = totalCharge;

    playerY_ = std::max(0.0, player.y);
    nCells_ = player.nCells;

    // charge_change = int(player_charges[color]) - self.player_charges[color]
    for (int c = 0; c < 3; ++c) {
        double chargeChange = static_cast<double>(static_cast<int>(playerChargesNow[c])) - playerCharges_[c];
        if (std::abs(chargeChange) > 0.0) {
            if (std::abs(chargeChange) < frameLength / 5.0) {
                playerCharges_[c] += chargeChange;
            } else {
                playerCharges_[c] += (chargeChange / std::abs(chargeChange)) * (frameLength / 5.0);
            }
        }
    }

    double practicalSum = player.practicalCharges[0] + player.practicalCharges[1] + player.practicalCharges[2];
    activeCharge_ = practicalSum;
    chargeColor_ = Util::chargesToColor(player.practicalCharges[idx(ChargeType::White)],
                                         player.practicalCharges[idx(ChargeType::Blue)],
                                         player.practicalCharges[idx(ChargeType::Red)]);

    if (totalChargeChange > 0.1) {
        rotationGoal_ += totalChargeChange / 10.0;
        scale_ = 90.0;
    } else if (totalChargeChange < -0.1) {
        if (scale_ < 81.0) scale_ = 60.0;
    }
    double realGoal = std::floor(rotationGoal_);
    double goalSpeed = (realGoal - rotation_) / 300.0;
    if (goalSpeed > rotationSpeed_) rotationSpeed_ += 1.0 / 1000.0;
    if (goalSpeed < rotationSpeed_) rotationSpeed_ = goalSpeed;
    rotation_ += rotationSpeed_ * frameLength;
    scale_ += (80.0 - scale_) / 300.0 * frameLength;
    if (std::abs(rotation_ - realGoal) < 0.001) {
        rotation_ = 0.0;
        rotationGoal_ -= realGoal;
    }

    std::array<ChargeType, 3> order = filterAngleOrder(filterType_);
    for (int c = 0; c < 3; ++c) {
        if (!filterPresent_[c]) continue;
        ChargeType ct = static_cast<ChargeType>(c);
        int orderIdx = 0;
        for (int k = 0; k < 3; ++k) if (order[k] == ct) { orderIdx = k; break; }
        double diff = orderIdx * M_PI / 20.0 - filters_[c];
        if (diff > 0 && player.filterChangeRight) diff -= 2 * M_PI;
        else if (diff < 0 && !player.filterChangeRight) diff += 2 * M_PI;
        filters_[c] = Util::pyMod(filters_[c] + diff / 150.0 * frameLength, 2 * M_PI);
    }
}

void ChargeDisplay::draw(SDL_Renderer* renderer) {
    const Asset& iconAsset = GlobalAssets::getAsset("UI_charge_icon");
    double cx = kTlX + kDisplaySize / 2.0;
    double cy = kTlY + kDisplaySize / 2.0;

    std::array<Color, 3> filterColors;
    filterColors[idx(ChargeType::White)] = Util::chargesToColor(1, 0, 0, 500, true);
    filterColors[idx(ChargeType::Blue)] = Util::chargesToColor(0, playerCharges_[idx(ChargeType::Blue)] + 20, 0, 500, true);
    filterColors[idx(ChargeType::Red)] = Util::chargesToColor(0, 0, playerCharges_[idx(ChargeType::Red)] + 20, 500, true);

    if (filterType_ == FilterType::White) {
        color_ = Util::chargesToColor(playerCharges_[idx(ChargeType::White)],
                                       playerCharges_[idx(ChargeType::Blue)],
                                       playerCharges_[idx(ChargeType::Red)], 500, true);
    } else {
        color_ = filterColors[filterAsChargeIdx(filterType_)];
    }

    // --- central charge icon: tint by chargeColor_, scale/rotate at draw time ---
    iconScratch_.renderTo(renderer, [&] {
        iconScratch_.clear({0, 0, 0, 0});
        Canvas::rectFilled(renderer, Rect{0, 0, iconAsset.width, iconAsset.height}, chargeColor_);
        Canvas::blit(renderer, iconAsset.texture, 0, 0, BlendModes::rgbaMult());
    });
    double iconDestSize = kChargeIconSize * scale_ / 100.0;
    // was: pygame.transform.rotate(icon, -self.rotation*360) -- pygame's
    // rotate is COUNTER-CLOCKWISE for positive angles, while
    // SDL_RenderCopyEx (which Canvas::blitRotated wraps) is CLOCKWISE for
    // positive angles -- opposite conventions, verified empirically
    // (rendered an asymmetric shape through both and compared). To
    // reproduce pygame.transform.rotate(img, V) via SDL, the angle must
    // be NEGATED: angle_SDL = -V. Here V = -rotation*360, so
    // angle_SDL = rotation*360 (no leading negative) -- FIXES a sign bug
    // from an earlier pass where this wasn't accounted for.
    Canvas::blitRotated(renderer, iconScratch_.texture(), cx, cy, iconDestSize, iconDestSize, rotation_ * 360.0);

    // --- ring of cell icons ---
    double radius = kDisplaySize * 0.38;
    int firstDim = static_cast<int>(activeCharge_ / 25.0);
    std::vector<ChargeType> chargeOrder = fullChargeOrder(filterType_);
    std::array<double, 3> charges = playerCharges_;

    const Asset& shellAsset = GlobalAssets::getAsset("cell_basic_shell_outlined");

    for (int i = 0; i < nCells_; ++i) {
        double angleDeg = i * 360.0 / 20.0;
        double angleRad = (angleDeg - 90.0) * M_PI / 180.0;
        Vec2 center = Util::polarToRect(radius, angleRad, {cx, cy});

        double darkenFactor;
        if (i < firstDim) darkenFactor = 1.0;
        else if (i == firstDim) darkenFactor = 0.2 + 0.8 * (activeCharge_ - 25.0 * firstDim) / 25.0;
        else darkenFactor = 0.2;

        double chargesSum = charges[0] + charges[1] + charges[2];
        if (chargesSum > 0.0) {
            std::array<double, 3> used = {0.0, 0.0, 0.0};
            double remaining = 25.0;
            for (ChargeType ct : chargeOrder) {
                int ci = idx(ct);
                used[ci] = std::min(charges[ci], remaining);
                remaining -= used[ci];
                charges[ci] -= used[ci];
                double sumNow = charges[0] + charges[1] + charges[2];
                if (remaining == 0.0 || sumNow == 0.0) break;
            }
            Color crackleColor = Util::chargesToColor(used[idx(ChargeType::White)],
                                                        used[idx(ChargeType::Blue)],
                                                        used[idx(ChargeType::Red)], 25);

            const Asset& crackleAsset = GlobalAssets::getAsset("cell_basic_crackle_" + std::to_string(frame_));

            cellScratch_.renderTo(renderer, [&] {
                cellScratch_.clear({0, 0, 0, 0});
                Canvas::rectFilled(renderer, Rect{0, 0, crackleAsset.width, crackleAsset.height}, crackleColor);
                Canvas::blit(renderer, crackleAsset.texture, 0, 0, BlendModes::rgbaMult());
            });
            // was: get_cell_img("crackle_N", -angle) -> pygame.transform.rotate(img, -angleDeg)
            // -- V = -angleDeg, so angle_SDL = -V = angleDeg (no negation). See icon rotation's note above for the full explanation.
            Canvas::blitRotated(renderer, cellScratch_.texture(), center.x, center.y,
                                 kCellDisplaySize, kCellDisplaySize, angleDeg);
        }

        Color shellTint = Util::multiplyColor(color_, darkenFactor);
        cellScratch_.renderTo(renderer, [&] {
            cellScratch_.clear({0, 0, 0, 0});
            Canvas::rectFilled(renderer, Rect{0, 0, shellAsset.width, shellAsset.height}, shellTint);
            Canvas::blit(renderer, shellAsset.texture, 0, 0, BlendModes::rgbaMult());
        });
        // was: get_cell_img("shell", -angle) -- same fix as the crackle rotation above.
        Canvas::blitRotated(renderer, cellScratch_.texture(), center.x, center.y,
                             kCellDisplaySize, kCellDisplaySize, angleDeg);
    }

    Canvas::circle(renderer, {cx, cy}, kDisplaySize * 0.5, {0, 0, 0, 255}, 5);

    for (int c = 0; c < 3; ++c) {
        if (!filterPresent_[c]) continue;
        if (c == filterAsChargeIdx(filterType_)) continue; // "if color is not self.filter_type"
        auto pts = chargeOuterTrianglePoints({cx, cy}, filters_[c]);
        Canvas::polygon(renderer, pts, filterColors[c]);
    }

    Canvas::circle(renderer, {cx, cy}, kDisplaySize * 0.5, color_, 3);

    Vec2 threshPoint = Util::polarToRect(kDisplaySize * 0.5 + 5, -M_PI * (1.0 / 2 - 2 * (200.0 / 500)), {cx, cy});
    Canvas::circle(renderer, threshPoint, 6, color_, 3);

    auto diamond = chargeDiamondPoints({cx, cy}, filters_[filterAsChargeIdx(filterType_)]);
    Canvas::polygon(renderer, diamond, filterColors[filterAsChargeIdx(filterType_)]);
    Canvas::polygonOutline(renderer, diamond, {0, 0, 0, 255}, 3);
}
