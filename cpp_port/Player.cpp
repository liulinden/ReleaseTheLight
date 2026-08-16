#include "Player.h"
#include "Canvas.h"
#include "BlendModes.h"
#include "GlobalAssets.h"
#include "Util.h"
#include <cmath>
#include <algorithm>
#include <string>

namespace {
int idx(ChargeType c) { return static_cast<int>(c); }
} // namespace

// def filter_charges(filter_type, charges): ...
std::array<double, 3> filterCharges(FilterType filterType, const std::array<double, 3>& charges) {
    switch (filterType) {
        case FilterType::White:
            return charges;
        case FilterType::Blue:
            return { 0.0, charges[idx(ChargeType::White)] / 2.0 + charges[idx(ChargeType::Blue)], 0.0 };
        case FilterType::Red:
            return { 0.0, 0.0, charges[idx(ChargeType::White)] / 2.0 + charges[idx(ChargeType::Red)] };
    }
    return charges; // unreachable
}

// filter_feeds = {"white": {...}, "blue": {...}, "red": {...}}
std::array<double, 3> filterFeed(FilterType filter, ChargeType color) {
    static const std::array<double, 3> table[3][3] = {
        // filter = White:       color=White      color=Blue        color=Red
        { {1.0, 0.0, 0.0},       {0.0, 1.0, 0.0},  {0.0, 0.0, 1.0} },
        // filter = Blue:
        { {0.0, 0.5, 0.0},       {0.0, 1.0, 0.0},  {0.0, 0.0, 0.0} },
        // filter = Red:
        { {0.0, 0.0, 0.5},       {0.0, 0.0, 0.0},  {0.0, 0.0, 1.0} },
    };
    return table[static_cast<int>(filter)][static_cast<int>(color)];
}

// --- LaserImpact -----------------------------------------------------------

LaserImpact::LaserImpact(SDL_Renderer* /*renderer*/, double xIn, double yIn, double angleIn, Laser* sourceLaser)
    : x_(xIn), y_(yIn), angle_(angleIn), sourceLaser_(sourceLaser) {}

// def tick(self, frame_length, active_laser): ...
bool LaserImpact::tick(double frameLength, Laser* activeLaser) {
    if (sourceLaser_ != nullptr) {
        if (sourceLaser_ == activeLaser) {
            x_ = sourceLaser_->startX + std::cos(sourceLaser_->angle) * sourceLaser_->length;
            y_ = sourceLaser_->startY + std::sin(sourceLaser_->angle) * sourceLaser_->length;
            angle_ = sourceLaser_->angle;
        } else {
            sourceLaser_ = nullptr;
        }
    }
    timer_ += frameLength;
    return timer_ >= kFrameDuration * kImpactFrames;
}

// def draw(self, surface, frame, color, zoom, offset_x=0, offset_y=0): ...
// See RenderTarget.h's blitRotated doc comment for the sign-convention
// derivation applied here (pygame CCW vs SDL CW rotation).
void LaserImpact::draw(SDL_Renderer* renderer, const Frame& frame, Color color) {
    int frameIndex = std::min(kImpactFrames - 1, static_cast<int>(timer_ / kFrameDuration));
    const Asset& img = GlobalAssets::getAsset("laser_impact_" + std::to_string(frameIndex + 1));

    if (scratchW_ != img.width || scratchH_ != img.height) {
        scratch_ = RenderTarget(renderer, img.width, img.height);
        scratchW_ = img.width;
        scratchH_ = img.height;
    }
    scratch_.renderTo(renderer, [&] {
        scratch_.clear({0, 0, 0, 0});
        Canvas::rectFilled(renderer, Rect{0, 0, img.width, img.height}, color);
        Canvas::blit(renderer, img.texture, 0, 0, img.width, img.height, BlendModes::rgbaMult());
    });

    double destSize = kImpactSize * frame.zoom;
    double halfH = destSize / 2.0;
    Vec2 center = frame.worldToScreen(x_, y_);
    center.x -= std::cos(angle_) * halfH;
    center.y -= std::sin(angle_) * halfH;

    // was: rot_angle = math.pi - self.angle; pygame.transform.rotate(img, degrees(rot_angle))
    // V_degrees = degrees(pi - angle) = 180 - degrees(angle); angle_SDL = -V = degrees(angle) - 180
    double angleSDL = angle_ * 180.0 / M_PI - 180.0;
    Canvas::blitRotated(renderer, scratch_.texture(), center.x, center.y, destSize, destSize, angleSDL);
}

// --- Player ------------------------------------------------------------

void Player::init(SDL_Renderer* /*renderer*/) {
    for (int i = 1; i <= 5; ++i) GlobalAssets::getAsset("player_idle_" + std::to_string(i));
    for (int i = 1; i <= 8; ++i) GlobalAssets::getAsset("player_run_" + std::to_string(i));
    GlobalAssets::getAsset("player_fall");
    GlobalAssets::getAsset("player_jump");
    GlobalAssets::getAsset("player_arm");
    for (int i = 1; i <= LaserImpact::kImpactFrames; ++i) {
        GlobalAssets::getAsset("laser_impact_" + std::to_string(i));
    }
}

Player::Player(SDL_Renderer* renderer, double xIn, double yIn, Vec2 dimensions)
    : x(xIn), y(yIn), width(dimensions.x), height(dimensions.y),
      spawnX_(xIn), spawnY_(yIn), renderer_(renderer) {
    updateRect();
    chargeCapacity = nCells * 25.0;

    // was: self.laser_attributes = laser_properties.LaserAttributes(18, 1,
    // 0.2, 10, 400, 1, 20, 0.3, 1, 20, 20, 0.5, 2, 0.5, {...}) -- explicit
    // initial values, NOT the struct's all-zero default member initializers.
    laserAttributes.distance = 18;
    laserAttributes.baseDmg = 1;
    laserAttributes.baseKb = 0.2;
    laserAttributes.baseXpl = 10;
    laserAttributes.cooldown = 400;
    laserAttributes.rampRate = 1;
    laserAttributes.rampMax = 20;
    laserAttributes.areaDmgFalloff = 0.3;
    laserAttributes.areaKbFalloff = 1;
    laserAttributes.dmgRange = 20;
    laserAttributes.kbRange = 20;
    laserAttributes.firstHitDmgMultiplier = 0.5;
    laserAttributes.firstHitKbMultiplier = 2;
    laserAttributes.firstHitXplMultiplier = 0.5;
    // passedThresholds already defaults to {0, false} for all three -- matches {"white": (0, False), ...}
}

// def reset_player(self): ...
void Player::resetPlayer() {
    x = spawnX_;
    y = spawnY_;
    xSpeed = 0;
    ySpeed = 0;
    setCharges(std::max(100.0, 25.0 * static_cast<int>(nCells * 2 / 3)), 0.0, 0.0);
    filterType = FilterType::White;
    practicalCharges = filterCharges(filterType, charges);
    laser.reset();
}

// def update_costume(self, frame_length, mouse_pos): ...
void Player::updateCostume(double frameLength, Vec2 mousePos) {
    double animLen = (animationType == AnimType::Idle) ? 8 : (animationType == AnimType::Run) ? 8
                    : (animationType == AnimType::Backpedal) ? 8 : 1; // fall/jump = 1
    animationTimer = std::fmod(animationTimer + frameLength, 1000.0 / kAnimationFps * animLen);
    AnimType previousAnimationType = animationType;

    double targetX = mousePos.x, targetY = mousePos.y;

    if (x < targetX) facing = Facing::Right;
    else if (x > targetX) facing = Facing::Left;

    armAngle = -std::atan2(targetY - (y + 3), targetX - x);

    if (!onGround) {
        if (ySpeed > 0.2) animationType = AnimType::Fall;
        else if (ySpeed < -0.2) animationType = AnimType::Jump;
    } else {
        if (std::abs(xSpeed) > 0.1) {
            bool movingWithFacing = (xSpeed > 0 && facing == Facing::Right) || (xSpeed < 0 && facing == Facing::Left);
            animationType = movingWithFacing ? AnimType::Run : AnimType::Backpedal;
        } else {
            animationType = AnimType::Idle;
        }
    }

    if (animationType != previousAnimationType) animationTimer = 0;

    double newAnimLen = (animationType == AnimType::Fall || animationType == AnimType::Jump) ? 1 : 8;
    if (newAnimLen == 1) animationFrame = 0;
    else animationFrame = static_cast<int>(std::floor(animationTimer / (1000.0 / kAnimationFps)));
}

void Player::updateRect() {
    rect.x = static_cast<int>(x - width / 2.0);
    rect.y = static_cast<int>(y - height / 2.0);
    rect.w = static_cast<int>(width);
    rect.h = static_cast<int>(height);
}

// def update_color(self): cw,cb,cr = self.practical_charges.values(); self.color = charges_to_color(cw,cb,cr,self.max_charge)
void Player::updateColor() {
    color = Util::chargesToColor(practicalCharges[idx(ChargeType::White)],
                                  practicalCharges[idx(ChargeType::Blue)],
                                  practicalCharges[idx(ChargeType::Red)], maxCharge);
}

// def update_charge_capacity(self): ...
void Player::updateChargeCapacity() {
    chargeCapacity = nCells * 25.0;
    double totalCharge = charges[0] + charges[1] + charges[2];
    double overflow = (totalCharge > chargeCapacity) ? (totalCharge - chargeCapacity) : 0.0;
    loseCharge(overflow);
    practicalCharges = filterCharges(filterType, charges);
}

void Player::updateLaserStats() {
    LaserProperties::setLaserAttributes(laserAttributes, practicalCharges, filterType, maxCharge);
}

void Player::setCharges(double white, double blue, double red) {
    charges[idx(ChargeType::White)] = white;
    charges[idx(ChargeType::Blue)] = blue;
    charges[idx(ChargeType::Red)] = red;
}

// def add_charge(self, added_charge, charge_distribution): ...
double Player::addCharge(double addedCharge, const std::array<double, 3>& chargeDistribution) {
    double sumAdded = 0.0;
    for (int c = 0; c < 3; ++c) {
        double add = chargeDistribution[c] * addedCharge;
        std::array<double, 3> feed = filterFeed(filterType, static_cast<ChargeType>(c));
        double addW = add * feed[0];
        double addB = add * feed[1];
        double addR = add * feed[2];

        charges[idx(ChargeType::White)] += addW;
        charges[idx(ChargeType::Blue)] += addB;
        charges[idx(ChargeType::Red)] += addR;

        sumAdded += addW + addB + addR;
    }

    double totalCharge = charges[0] + charges[1] + charges[2];
    double overflow = (totalCharge > chargeCapacity) ? (totalCharge - chargeCapacity) : 0.0;
    loseCharge(overflow);
    practicalCharges = filterCharges(filterType, charges);
    return sumAdded - overflow;
}

// def lose_charge(self, loss): ...
bool Player::loseCharge(double loss) {
    if (filterType == FilterType::White) {
        int nSplit = 3;
        while (nSplit > 0) {
            double splitLoss = loss / nSplit;
            for (int c = 0; c < 3; ++c) {
                if (charges[c] > 0 && charges[c] < splitLoss) {
                    loss -= charges[c];
                    charges[c] = 0;
                    nSplit -= 1;
                    goto foundSmall; // matches Python's `break` out of the inner for-loop
                }
            }
            foundSmall:;
            for (int c = 0; c < 3; ++c) {
                if (charges[c] > 0) charges[c] -= splitLoss;
            }
            nSplit = 0;
        }
    } else {
        int fc = idx(filterType == FilterType::Blue ? ChargeType::Blue : ChargeType::Red);
        if (loss < charges[fc]) {
            charges[fc] -= loss;
        } else {
            loss -= charges[fc];
            charges[fc] = 0;
            if (loss < charges[idx(ChargeType::White)]) {
                charges[idx(ChargeType::White)] -= loss;
            } else {
                loss -= charges[idx(ChargeType::White)];
                charges[idx(ChargeType::White)] = 0;
                filterType = FilterType::White;
                loseCharge(loss);
            }
        }
    }

    practicalCharges = filterCharges(filterType, charges);
    if (charges[0] + charges[1] + charges[2] > 0) return false;
    resetPlayer();
    return true;
}

void Player::dealDamage(double damage) { queuedDamage += damage; }
void Player::drainDamage(double damage) { queuedDrainDamage += damage; }

Terrain::CollisionResult Player::collidingWithTerrain(Terrain& terrain) {
    return terrain.collideRect(rect);
}

// def move_horizontal(self, frame_length, _terrain): -- identical
// structure to Enemy/Cell's own version (each kept separate/duplicated,
// matching the project's earlier decision not to prematurely unify these).
void Player::moveHorizontal(double frameLength, Terrain& terrain) {
    x += frameLength * xSpeed;
    updateRect();
    if (collidingWithTerrain(terrain).hit) {
        int slopeTolerance = static_cast<int>(std::ceil(3 * std::abs(frameLength * xSpeed)));
        for (int i = 0; i < slopeTolerance; ++i) {
            y -= 1;
            updateRect();
            if (!collidingWithTerrain(terrain).hit) {
                xSpeed -= xSpeed * i / static_cast<double>(slopeTolerance);
                return;
            }
        }
        y += slopeTolerance;
        x -= frameLength * xSpeed;
        int backs = static_cast<int>(std::ceil(std::abs(frameLength * xSpeed / 1.0)));
        for (int i = 0; i < backs; ++i) {
            x += frameLength * xSpeed / backs;
            updateRect();
            if (collidingWithTerrain(terrain).hit) {
                x -= frameLength * xSpeed / backs;
                updateRect();
                break;
            }
        }
        xSpeed = 0;
    }
}

// def move_vertical(self, frame_length, _terrain): -- same structure as
// Enemy's, PLUS fall-damage logic Enemy doesn't have.
void Player::moveVertical(double frameLength, Terrain& terrain) {
    onGround = false;
    y += frameLength * ySpeed;
    updateRect();
    auto collision = collidingWithTerrain(terrain);
    if (collision.hit) {
        if (ySpeed > 0) {
            onGround = true;
            if (!terrain.nestsCollideRect(rect)) {
                int n = static_cast<int>(std::abs(
                    (std::abs(std::max(0.005 * frameLength, std::abs(xSpeed)) - 0.005 * frameLength))
                    + 3 * (ySpeed - 0.0015 * frameLength)) * 12);
                terrain.particles.spawnMiningParticles(n, Color{0, 0, 0, 255}, 20, x, y + height / 2.0);
            }
            if (ySpeed >= 0.7) {
                dealDamage(std::pow(ySpeed - 0.5, 2) * 100);
                terrain.particles.spawnMiningParticles(5, color, 20 * ySpeed, x, y + height / 2.0);
            }
        }
        if (ySpeed < 0) {
            int slopeTolerance = static_cast<int>(std::ceil(std::abs(0.5 * frameLength * ySpeed)));
            for (int i = 0; i < slopeTolerance; ++i) {
                x -= 1;
                updateRect();
                if (!collidingWithTerrain(terrain).hit) return;
            }
            x += slopeTolerance;
            for (int i = 0; i < slopeTolerance; ++i) {
                x += 1;
                updateRect();
                if (!collidingWithTerrain(terrain).hit) return;
            }
            x -= slopeTolerance;
        }
        y -= frameLength * ySpeed;
        int backs = static_cast<int>(std::ceil(std::abs(frameLength * ySpeed / 1.0)));
        for (int i = 0; i < backs; ++i) {
            y += frameLength * ySpeed / backs;
            updateRect();
            if (collidingWithTerrain(terrain).hit) {
                y -= frameLength * ySpeed / backs;
                updateRect();
                break;
            }
        }
        ySpeed = 0;
    }
}

// def tick(self, frame_length, _terrain, mouse_pos, keys_down, events): ...
bool Player::tick(double frameLength, Terrain& terrain, Vec2 mousePos, const PlayerInput& input) {
    if (loseCharge(queuedDamage) || loseCharge(queuedDrainDamage)) return true;
    queuedDamage = 0;
    queuedDrainDamage = 0;

    ySpeed = std::min(2.0, ySpeed + 0.0015 * frameLength);
    if (immunityTimer > 0) {
        immunityTimer -= frameLength;
        if (immunityTimer < 0) immunityTimer = 0;
    }

    if (input.rightArrowEvent) {
        filterChangeRight = true;
        switch (filterType) {
            case FilterType::White: filterType = FilterType::Blue; break;
            case FilterType::Blue:  filterType = FilterType::Red; break;
            case FilterType::Red:   filterType = FilterType::White; break;
        }
    }

    if (input.leftArrowEvent) {
        filterChangeRight = false;
        switch (filterType) {
            case FilterType::White: filterType = FilterType::Red; break;
            case FilterType::Blue:  filterType = FilterType::White; break;
            case FilterType::Red:   filterType = FilterType::Blue; break;
        }
    }

    if (input.spaceEvent && abilityTimer == 0 &&
        laserAttributes.passedThresholds[static_cast<int>(filterType)].passedAbility) {
        switch (filterType) {
            case FilterType::White: {
                double dx = mousePos.x - x, dy = mousePos.y - y;
                double d = Util::dist(dx, dy);
                xSpeed = dx / d / 1.2;
                ySpeed = dy / d / 2.0;
                abilityTimer = abilityCooldown;
                terrain.particles.spawnPulseParticle(color, 40, x, y);
                break;
            }
            case FilterType::Blue: {
                ySpeed -= 0.3;
                terrain.newKnockbackCircles.push_back({ laserAttributes.baseKb * 5.0, x, y, laserAttributes.kbRange * 3.0, 1.0 });
                terrain.particles.spawnPulseParticle(color, laserAttributes.kbRange * 3.0, x, y, 800);
                abilityTimer = abilityCooldown;
                break;
            }
            case FilterType::Red: {
                ySpeed -= 0.3;
                terrain.newPlayerDamageCircles.push_back({ laserAttributes.baseDmg, x, y, laserAttributes.dmgRange * 2.0, 1.0 });
                terrain.particles.spawnPulseParticle(color, laserAttributes.dmgRange * 2.0, x, y, 800);
                abilityTimer = abilityCooldown;
                break;
            }
        }
    }

    if (input.leftMouseHeld && laser == nullptr && laserTimer <= laserAttributes.cooldown / 4.0) {
        laser = std::make_unique<Laser>();
        laserRamps = 0;
        laserFirstHit = true;
    }

    if (input.leftMouseUpEvent && laser != nullptr) {
        laserTimer = laser->timer;
        laser.reset();
    }

    if (input.rightMouseUpEvent) {
        if (nCells > 1) {
            double dx = mousePos.x - x, dy = mousePos.y - y;
            double d = Util::dist(dx, dy);
            terrain.addCell(renderer_, { x, y }, { xSpeed + dx / d / 3.0, ySpeed + dy / d / 3.0 });
            nCells -= 1;
            updateChargeCapacity();
        }
    }

    abilityTimer -= frameLength;
    abilityTimer = std::max(0.0, abilityTimer);

    laserTimer -= frameLength;
    laserTimer = std::max(0.0, laserTimer);

    if (laser) {
        bool locked = laser->updateLaser(
            terrain,
            x - kSpriteWidth / 2.0 + kArmPivotX + 10 * std::cos(armAngle),
            y - kSpriteHeight / 2.0 + kArmPivotY + 10 * std::sin(-armAngle) + 3,
            -armAngle,
            laserAttributes.distance,
            laserAttributes.cooldown);
        laser->tick(frameLength);
        if (laser->damageFrame) {
            if (!locked) laserRamps = 0;
            if (laser->collision.hit) {
                double lx = laser->collision.x, ly = laser->collision.y;
                double explosionSize = LaserProperties::getLaserExpl(laserAttributes, laserFirstHit, laserRamps);
                terrain.addAirPocketClump(lx, ly, explosionSize, true, false, 1.0 / 5.0, renderer_);
                if (laser->collision.type == "ground") {
                    terrain.particles.spawnMiningParticles(10, Color{0, 0, 0, 255}, explosionSize * 1.5, lx, ly);
                    HealthBar::targeted = nullptr;
                }

                terrain.newKnockbackCircles.push_back({
                    LaserProperties::getLaserKb(laserAttributes, laserFirstHit, laserRamps),
                    lx, ly, laserAttributes.kbRange, laserAttributes.areaKbFalloff });
                terrain.newPlayerDamageCircles.push_back({
                    LaserProperties::getLaserDmg(laserAttributes, laserFirstHit, laserRamps),
                    lx, ly, laserAttributes.dmgRange, laserAttributes.areaDmgFalloff });
                terrain.particles.spawnPulseParticle(color, laserAttributes.dmgRange, lx, ly);
                terrain.particles.spawnPulseParticle(color, laserAttributes.kbRange, lx, ly);
            } else {
                HealthBar::targeted = nullptr;
            }

            laserFirstHit = false;
            laserRamps += 1;

            if (loseCharge(0.5)) return true;

            double endX = laser->startX + std::cos(laser->angle) * laser->length;
            double endY = laser->startY + std::sin(laser->angle) * laser->length;
            impacts.push_back(std::make_unique<LaserImpact>(renderer_, endX, endY, laser->angle, laser.get()));
        }
    }

    impacts.erase(
        std::remove_if(impacts.begin(), impacts.end(),
                        [&](std::unique_ptr<LaserImpact>& imp) { return imp->tick(frameLength, laser.get()); }),
        impacts.end());

    for (auto& kc : terrain.knockbackCircles) {
        double dx = x - kc.x, dy = y - kc.y;
        double distance = Util::dist(dx, dy);
        double knockback = kc.power;
        xSpeed += frameLength * dx / distance * knockback / 60.0;
        ySpeed += frameLength * dy / distance * knockback / 60.0;
    }

    for (Nest* nest : terrain.nestsNear(x, y, 400)) {
        // was: self.charges[nest.nest_type] -- throws for Sun nests
        // (matches the Python's KeyError there; see nestTypeToChargeType's
        // own note). world-gen never spawns Sun nests, so this is
        // unreachable in practice, same as everywhere else Sun surfaces.
        double playerChargeForNestType = charges[static_cast<int>(nestTypeToChargeType(nest->nestType))];
        if (nest->stage == nest->maxStage && chargeCapacity > playerChargeForNestType &&
            nest->withinEffectRadius(x, y) && nest->charge > 0) {
            terrain.addInteractionDisplay(&nest->interactionDisplay);
            if (nest->interactionDisplay.active) {
                double chargeGain = addCharge(nest->chargeRate * frameLength, nest->charging);
                nest->loseCharge(chargeGain);
            }
        } else {
            terrain.removeInteractionDisplay(&nest->interactionDisplay,
                                              nest->charge == 0 || chargeCapacity == playerChargeForNestType);
        }
    }
    for (Chunk* chunk : terrain.chunksNear(x, y, 400, 0)) {
        auto& cells = chunk->cells;
        for (int i = static_cast<int>(cells.size()) - 1; i >= 0; --i) {
            Cell* cell = cells[i].get();
            if (cell->withinInteractionRadius({ x, y })) {
                terrain.addInteractionDisplay(&cell->interactionDisplay());
                if (cell->interactionDisplay().active) {
                    terrain.removeInteractionDisplay(&cell->interactionDisplay(), true);
                    cells.erase(cells.begin() + i);
                    nCells += 1;
                }
            } else {
                terrain.removeInteractionDisplay(&cell->interactionDisplay());
            }
        }
    }

    updateChargeCapacity();
    updateLaserStats();

    if (x < 50) {
        xSpeed += (50 - x) / 10000.0 * frameLength;
    } else if (x > terrain.worldWidth() - 50) {
        xSpeed -= (x - terrain.worldWidth() + 50) / 10000.0 * frameLength;
    }

    if (input.keyW && onGround) ySpeed = -0.4;

    if (input.keyA) xSpeed -= (onGround ? 0.005 : 0.0015) * frameLength;
    if (input.keyD) xSpeed += (onGround ? 0.005 : 0.0015) * frameLength;

    xSpeed *= onGround ? std::pow(0.98, frameLength) : std::pow(0.993, frameLength);

    moveVertical(frameLength, terrain);
    moveHorizontal(frameLength, terrain);

    updateColor();
    updateCostume(frameLength, mousePos);

    if (laser) {
        laser->updateLaser(
            terrain,
            x - kSpriteWidth / 2.0 + kArmPivotX + 10 * std::cos(armAngle),
            y - kSpriteHeight / 2.0 + kArmPivotY + 3 + 10 * std::sin(-armAngle),
            -armAngle,
            laserAttributes.distance,
            laserAttributes.cooldown);
    }
    return false;
}

// def draw(self, surface, frame, hitboxes=False, offset_x=0, offset_y=0, tilt=0): ...
void Player::draw(SDL_Renderer* renderer, const Frame& frame, bool hitboxesMode, double tilt) {
    updateRect();
    if (hitboxesMode) {
        double l = rect.x, r = rect.x + rect.w - 1, t = rect.y, b = rect.y + rect.h - 1;
        Canvas::line(renderer, frame.worldToScreen(l, t), frame.worldToScreen(l, b), color);
        Canvas::line(renderer, frame.worldToScreen(r, t), frame.worldToScreen(r, b), color);
        Canvas::line(renderer, frame.worldToScreen(l, t), frame.worldToScreen(r, t), color);
        Canvas::line(renderer, frame.worldToScreen(l, b), frame.worldToScreen(r, b), color);
        if (laser) {
            laser->draw(renderer, frame, color, true);
        }
        return;
    }

    Color boosted{
        static_cast<uint8_t>(Util::channelBound(color.r + 30)),
        static_cast<uint8_t>(Util::channelBound(color.g + 30)),
        static_cast<uint8_t>(Util::channelBound(color.b + 30)),
        255
    };

    std::string animStr = (animationType == AnimType::Idle) ? "idle" : (animationType == AnimType::Run) ? "run"
                         : (animationType == AnimType::Backpedal) ? "backpedal" : (animationType == AnimType::Fall) ? "fall" : "jump";
    std::string bodyAssetName = "player_" + animStr + "_" + std::to_string(animationFrame + 1);
    // was: PLAYER_IMGS["idle"] etc are precomputed lists indexed by
    // animation_frame -- "idle" specifically has a custom 8-frame
    // ping-pong sequence (5 distinct assets, then 3 reversed: 4,3,2), and
    // "backpedal" reuses the "run" assets in reverse (8,7,...,1). Both
    // built here directly rather than via a precomputed list, since we
    // fetch assets fresh each draw call anyway.
    const Asset* bodyAsset = nullptr;
    if (animationType == AnimType::Idle) {
        static const int idleSeq[8] = { 1, 2, 3, 4, 5, 4, 3, 2 };
        bodyAsset = &GlobalAssets::getAsset("player_idle_" + std::to_string(idleSeq[animationFrame % 8]));
    } else if (animationType == AnimType::Run) {
        bodyAsset = &GlobalAssets::getAsset("player_run_" + std::to_string(animationFrame + 1));
    } else if (animationType == AnimType::Backpedal) {
        bodyAsset = &GlobalAssets::getAsset("player_run_" + std::to_string(8 - animationFrame));
    } else if (animationType == AnimType::Fall) {
        bodyAsset = &GlobalAssets::getAsset("player_fall");
    } else {
        bodyAsset = &GlobalAssets::getAsset("player_jump");
    }

    double zoom = frame.zoom;
    double spriteDestW = kSpriteWidth * zoom, spriteDestH = kSpriteHeight * zoom;

    if (bodyScratchW_ != bodyAsset->width || bodyScratchH_ != bodyAsset->height) {
        bodyScratch_ = RenderTarget(renderer, bodyAsset->width, bodyAsset->height);
        bodyScratchW_ = bodyAsset->width;
        bodyScratchH_ = bodyAsset->height;
    }
    bodyScratch_.renderTo(renderer, [&] {
        bodyScratch_.clear({0, 0, 0, 0});
        Canvas::rectFilled(renderer, Rect{0, 0, bodyAsset->width, bodyAsset->height}, boosted);
        Canvas::blit(renderer, bodyAsset->texture, 0, 0, bodyAsset->width, bodyAsset->height,
                     BlendModes::rgbaMult(), facing == Facing::Left);
    });

    double adjustedArmAngle = armAngle;
    if (facing == Facing::Left) adjustedArmAngle += M_PI;

    const Asset& armAsset = GlobalAssets::getAsset("player_arm");
    if (armScratchW_ != armAsset.width || armScratchH_ != armAsset.height) {
        armScratch_ = RenderTarget(renderer, armAsset.width, armAsset.height);
        armScratchW_ = armAsset.width;
        armScratchH_ = armAsset.height;
    }
    armScratch_.renderTo(renderer, [&] {
        armScratch_.clear({0, 0, 0, 0});
        Canvas::rectFilled(renderer, Rect{0, 0, armAsset.width, armAsset.height}, boosted);
        Canvas::blit(renderer, armAsset.texture, 0, 0, armAsset.width, armAsset.height, BlendModes::rgbaMult());
    });

    // was: rotate_and_get_offset(self.player_im_gs[zoom][facing]["arm"][0],
    // zoom*ARM_PIVOT_X, zoom*ARM_PIVOT_Y, adjusted_arm_angle) -- unlike
    // LaserImpact (pivot == image center), the arm's pivot is an
    // arbitrary point, so this needs SDL_RenderCopyEx's explicit `center`
    // parameter (destination-rect-local coordinates) rather than the
    // default-center blitRotated helper. The arm asset is force-scaled to
    // the SAME (SPRITE_WIDTH*zoom, SPRITE_HEIGHT*zoom) square as the body
    // sprite in the Python's per-zoom pre-scale step (regardless of the
    // arm asset's native aspect ratio), so its pivot point in that scaled
    // space is (ARM_PIVOT_X*zoom, ARM_PIVOT_Y*zoom).
    double armDrawW = kSpriteWidth * zoom;
    double armDrawH = kSpriteHeight * zoom;
    SDL_Point pivotPx{
        static_cast<int>(kArmPivotX * zoom),
        static_cast<int>(kArmPivotY * zoom)
    };

    // was: (self.x - SPRITE_WIDTH/2 - cam_x)*zoom + offset_x,
    //      (3 + self.rect.bottom - SPRITE_HEIGHT - cam_y)*zoom + offset_y
    // -- same base position for both body and arm; SDL's pivot-based
    // rotation (via `center` above) replaces the manual bbox-offset
    // correction rotate_and_get_offset computed, so no separate
    // arm_offset_x/y term is needed here.
    Vec2 bodyPos = frame.worldToScreen(x - kSpriteWidth / 2.0, rect.bottom() - kSpriteHeight + 3);
    double armDstX = bodyPos.x;
    double armDstY = bodyPos.y;

    double angleSDL = -(adjustedArmAngle * 180.0 / M_PI); // V (pygame degrees) = degrees(adjustedArmAngle); angle_SDL = -V -- see RenderTarget.h's blitRotated note
    SDL_Rect armDst{ static_cast<int>(armDstX), static_cast<int>(armDstY), static_cast<int>(armDrawW), static_cast<int>(armDrawH) };
    SDL_SetTextureBlendMode(armScratch_.texture(), SDL_BLENDMODE_BLEND);
    SDL_RenderCopyEx(renderer, armScratch_.texture(), nullptr, &armDst, angleSDL, &pivotPx, SDL_FLIP_NONE);

    Canvas::blit(renderer, bodyScratch_.texture(), bodyPos.x, bodyPos.y, spriteDestW, spriteDestH,
                 SDL_BLENDMODE_BLEND, facing == Facing::Left);

    if (laser) {
        laser->draw(renderer, frame, boosted, false);
    }
    for (auto& impact : impacts) {
        impact->draw(renderer, frame, boosted);
    }
    (void)tilt; // FLAGGED: screen-tilt rotation (rotate the whole rendered
                // frame by `tilt` degrees) is a World/Game-level concern
                // applied to the FULL rendered layer, not per-sprite --
                // Player.draw's own `tilt` param only rotates the BODY
                // sprite image itself (`if tilt != 0: player_surface =
                // pygame.transform.rotate(player_surface, tilt)`), which
                // this doesn't yet implement. Deferred: low-impact
                // cosmetic detail (a knockback "stagger" tilt effect),
                // consistent with not fully polishing every section yet.
}

