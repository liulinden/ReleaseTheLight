#include "World.h"
#include "Canvas.h"
#include "BlendModes.h"
#include "GlobalAssets.h"
#include "Util.h"
#include "Time.h"
#include "Cell.h"
#include "Enemy.h"
#include "Nest.h"
#include "InteractionDisplay.h"
#include <cmath>
#include <algorithm>

// was: inits = [lighting.init, cells.init, enemies.init, nest.init,
//               terrain.init, player.init, laser.init,
//               interaction_display.init, charge_display.init]
void World::init(SDL_Renderer* renderer, const std::string& interactionFontPath) {
    Lighting::init(renderer);
    Cell::init(renderer);
    Enemy::init(renderer);
    Nest::init(renderer);
    Terrain::init(renderer);
    Player::init(renderer);
    Laser::init();
    InteractionDisplay::init(renderer, interactionFontPath);
    // charge_display.init() skipped -- see header note.
}

World::World(SDL_Renderer* renderer, int worldWidth, int worldHeight, bool developingModeIn)
    : terrain(worldWidth, worldHeight),
      player(renderer, worldWidth / 2.0, developingModeIn ? -200.0 : -1200.0),
      developingMode(developingModeIn),
      renderer_(renderer) {
    generateWorld();
    terrain.startStreaming();
}

void World::generateWorld() {
    terrain.generateWorld(renderer_);
}

// def heal_nests(self): ...
void World::healNests() {
    for (auto& n : terrain.nests) {
        if (n->health > 0) {
            n->health = n->maxHealth;
            n->stage = 0;
        }
    }
}

// def remove_enemies(self): ...
void World::removeEnemies() {
    for (auto& n : terrain.nests) {
        n->enemies.clear();
    }
    terrain.enemies.clear();
}

// def tick(self, fps, window_size, frame, mouse_pos, keys_down, events): ...
bool World::tick(double fps, const Frame& frame, Vec2 mousePos, const PlayerInput& input,
                  const std::unordered_map<SDL_Keycode, bool>& keysDown) {
    double frameLength = 1000.0 / fps;
    Rect screenRect{
        static_cast<int>(frame.left), static_cast<int>(frame.top),
        static_cast<int>(frame.viewWidth / frame.zoom), static_cast<int>(frame.viewHeight / frame.zoom)
    };

    terrain.updateStreaming(player.x, player.y);

    terrain.newKnockbackCircles.clear();
    terrain.newPlayerDamageCircles.clear();

    if (player.tick(frameLength, terrain, mousePos, input)) return true;

    double playerSpeed = Util::dist(player.xSpeed, player.ySpeed);
    double alphaTarget = std::max(0.0, 255.0 - 600.0 * playerSpeed);
    foregroundAlpha_ += (alphaTarget - foregroundAlpha_) * frameLength / ((alphaTarget < foregroundAlpha_) ? 100.0 : 1500.0);

    if (Util::frameRandom(frameLength, 5.0)) {
        light.addMistParticle(player.x, player.y, player.color);
    }
    if (player.laser) {
        Laser* lase = player.laser.get();
        if (Util::frameRandom(frameLength, lase->length / 20.0)) {
            double mistPos = Util::randomDouble();
            light.addMistParticle(lase->startX + mistPos * lase->length * std::cos(lase->angle),
                                   lase->startY + mistPos * lase->length * std::sin(lase->angle),
                                   player.color);
        }
    }

    for (Nest* n : terrain.nestsTouchingRect(screenRect)) {
        n->updateVisuals(frameLength);
        if (!terrain.playerDamageCircles.empty()) {
            LaserTargetInfo laserInfo = player.laser ? player.laser->asLaserTargetInfo() : LaserTargetInfo{};
            for (auto& spec : n->applyDamageFromCircles(renderer_, terrain, laserInfo, player.x, player.y, player.rect)) {
                terrain.particles.spawnMiningParticles(10, n->color, spec.size, spec.x, spec.y);
            }
        }

        if (n->stage != n->maxStage) {
            double d = Util::dist(n->x - player.x, n->y - player.y);
            if (d < 300 && Util::frameRandom(frameLength, 0.2 + 0.5 * (300 - d) / 300.0)) {
                n->addEnemy(renderer_, terrain, player.x, player.y, player.rect);
            }
            for (int i = static_cast<int>(n->enemies.size()) - 1; i >= 0; --i) {
                Enemy* enemy = n->enemies[i];
                EnemyPlayerView epv{
                    player.x, player.y, player.xSpeed, player.ySpeed, player.immunityTimer, player.immunityTime,
                    player.rect, player.laser ? player.laser->asLaserTargetInfo() : LaserTargetInfo{},
                    [&](double dmg) { player.dealDamage(dmg); }
                };
                if (enemy->tick(frameLength, terrain, epv)) {
                    terrain.removeEnemy(enemy);
                    n->enemies.erase(n->enemies.begin() + i);
                }
            }
        } else {
            if (Util::frameRandom(frameLength, n->interactionDisplay.active ? 8.0 : 2.0)) {
                light.addMistParticle(n->x, n->y, n->color);
            }
        }
    }

    for (Cell* cell : terrain.cellsInRect(screenRect)) {
        if (cell->close(frame)) {
            LaserTargetInfo laserInfo = player.laser ? player.laser->asLaserTargetInfo() : LaserTargetInfo{};
            cell->tick(frameLength, terrain, laserInfo);
        }
    }

    terrain.displayManager.tick(frameLength, keysDown);

    light.tickEffects(frameLength);
    terrain.particles.tickParticles(frameLength);

    terrain.knockbackCircles = terrain.newKnockbackCircles;
    terrain.playerDamageCircles = terrain.newPlayerDamageCircles;

    return false;
}

// def draw_background(self, layer, window_size, frame): ...
// NOTE: uses Util::pyMod (matches Python's `%` operator), not std::fmod --
// left/top can be negative (world extends infinitely in x, and the
// camera can be above y=0), so sign-correct modulo matters here.
void World::drawBackground(SDL_Renderer* renderer, const Frame& frame) {
    const Asset& bg1 = GlobalAssets::getAsset("background_1");
    const Asset& bg2 = GlobalAssets::getAsset("background_2");
    // was: self.bg_width, self.bg_height = 3000, 3000 (originally the
    // PRE-SCALED destination size; now just the destination size we scale
    // to at draw time, native asset resolution notwithstanding).
    constexpr double kBgSize = 3000.0;

    double x1 = Util::pyMod(-frame.left * 1.0 * frame.zoom, kBgSize) / 2.0 - kBgSize / 2.0;
    double y1 = Util::pyMod(-frame.top * 1.0 * frame.zoom, kBgSize) / 2.0 - kBgSize / 2.0;
    Canvas::blit(renderer, bg1.texture, x1, y1, kBgSize, kBgSize);

    double x2 = Util::pyMod(-frame.left * 1.8 * frame.zoom, kBgSize) / 2.0 - kBgSize / 2.0;
    double y2 = Util::pyMod(-frame.top * 1.8 * frame.zoom, kBgSize) / 2.0 - kBgSize / 2.0;
    Canvas::blit(renderer, bg2.texture, x2, y2, kBgSize, kBgSize);
}

// def draw_foreground(self, layer, window_size, frame): ...
// NOTE: this is a PLAIN alpha blit (matches `layer.blit(self.foreground,
// (x,y))`, no special_flags) -- the MULT blending happens one level up,
// when the whole scratch layer this draws into gets composited onto the
// main layer (see drawWorld). foreground_alpha is applied here via
// SDL_SetTextureAlphaMod, matching `self.foreground.set_alpha(...)`.
void World::drawForeground(SDL_Renderer* renderer, const Frame& frame) {
    const Asset& fg = GlobalAssets::getAsset("foreground");
    constexpr double kFgSize = 10000.0;

    double x = Util::pyMod(-frame.left * 6.0 * frame.zoom, kFgSize) / 2.0 - kFgSize / 2.0;
    double y = Util::pyMod((-frame.top * 6.0 + 500.0) * frame.zoom, kFgSize) / 2.0 - kFgSize / 2.0;
    SDL_SetTextureAlphaMod(fg.texture, static_cast<uint8_t>(std::clamp(foregroundAlpha_, 0.0, 255.0)));
    Canvas::blit(renderer, fg.texture, x, y, kFgSize, kFgSize);
}

// def draw_world(self, window, window_size, frame, hitboxes=False, ...): ...
void World::drawWorld(SDL_Renderer* renderer, const Frame& frame, bool hitboxes,
                       bool kindVisibility, double tilt, bool crosshair) {
    if (layerW_ != frame.screenWidth || layerH_ != frame.screenHeight) {
        worldLayer_ = RenderTarget(renderer, frame.screenWidth, frame.screenHeight);
        scratchLayer_ = RenderTarget(renderer, frame.screenWidth, frame.screenHeight);
        finalLayer_ = RenderTarget(renderer, frame.screenWidth, frame.screenHeight);
        layerW_ = frame.screenWidth;
        layerH_ = frame.screenHeight;
    }

    worldLayer_.renderTo(renderer, [&] {
        if (kindVisibility) worldLayer_.clear({200, 200, 200, 255});
        else worldLayer_.clear({5, 5, 5, 255});

        light.drawGradient(renderer, frame, player.color, player.x, player.y, 600);
        if (player.laser && player.laser->collision.hit) {
            light.drawGradient(renderer, frame, player.color, player.laser->collision.x, player.laser->collision.y);
        }

        terrain.drawNestGradients(renderer, frame);
        terrain.drawEnemyGradients(renderer, frame);

        scratchLayer_.renderTo(renderer, [&] {
            scratchLayer_.clear({0, 0, 0, 0});
            drawBackground(renderer, frame);
        });
        Canvas::blit(renderer, scratchLayer_.texture(), 0, 0, frame.screenWidth, frame.screenHeight, BlendModes::rgbMult());

        light.drawGradient(renderer, frame, player.color, player.x, player.y);

        Color frameColor = terrain.getFrameColor(frame);
        scratchLayer_.renderTo(renderer, [&] {
            Canvas::rectFilled(renderer, Rect{0, 0, frame.screenWidth, frame.screenHeight}, frameColor);
        });
        Canvas::blit(renderer, scratchLayer_.texture(), 0, 0, frame.screenWidth, frame.screenHeight, BlendModes::rgbMult());

        light.drawEffects(renderer, frame);

        terrain.particles.drawPulseParticles(renderer, frame);

        player.draw(renderer, frame, hitboxes, tilt);

        terrain.drawCells(renderer, frame, hitboxes);
        terrain.drawEnemies(renderer, frame, hitboxes);
        terrain.particles.drawParticles(renderer, frame);
        terrain.drawNests(renderer, frame, hitboxes);
        terrain.drawTerrain(renderer, frame, hitboxes);

        int64_t nowMs = static_cast<int64_t>(Time::nowMs());
        terrain.drawHealthBars(renderer, frame, nowMs);
        terrain.drawInteractionDisplays(renderer, frame, nowMs);

        if (!kindVisibility) {
            scratchLayer_.renderTo(renderer, [&] {
                scratchLayer_.clear({255, 255, 255, 255});
                drawForeground(renderer, frame);
                light.drawThickGradient(renderer, frame, player.x, player.y);
                if (player.laser && player.laser->collision.hit) {
                    light.drawThickGradient(renderer, frame, player.laser->collision.x, player.laser->collision.y);
                }
            });
            // was: special_flags=pygame.BLEND_MULT (the plain/un-prefixed
            // flag, which multiplies ALL channels including alpha) --
            // rgbaMult(), not rgbMult().
            Canvas::blit(renderer, scratchLayer_.texture(), 0, 0, frame.screenWidth, frame.screenHeight, BlendModes::rgbaMult());
        }

        if (crosshair) {
            // was: pygame.draw.line(layer, (100,100,100,0.3), ...) -- the
            // alpha component (0.3) is a float where pygame expects an
            // int 0-255, AND this world_layer surface was created without
            // pygame.SRCALPHA in the Python (`pygame.Surface(real_window_size)`,
            // no per-pixel alpha support), so the alpha component would
            // most likely be ignored entirely by pygame -- resulting in a
            // fully OPAQUE gray line despite the apparent "faint" intent.
            // Implemented as opaque gray here to match that most-likely
            // actual behavior, flagged since this is inference about an
            // ambiguous original, not a certainty.
            Canvas::line(renderer, {frame.screenWidth * 0.45, frame.screenHeight / 2.0},
                         {frame.screenWidth * 0.55, frame.screenHeight / 2.0}, Color{100, 100, 100, 255}, 2);
            Canvas::line(renderer, {frame.screenWidth / 2.0, frame.screenHeight * 0.45},
                         {frame.screenWidth / 2.0, frame.screenHeight * 0.55}, Color{100, 100, 100, 255}, 2);
        }
    });

    // was: layer, cx, cy = rotate_and_get_offset(layer, real_window_size[0]/2,
    // real_window_size[1]/2, math.radians(tilt)); layer.blit(layer, (cx, cy))
    // -- pivot IS the screen center here, so this is the simple "rotate
    // around own center" case (blitRotated's default), same as
    // LaserImpact. Baked into a SEPARATE offscreen buffer (not just
    // rotated at final-blit time) specifically so bloom (below) samples
    // the POST-rotation frame, matching the Python's actual execution
    // order (tilt runs before bloom, both applied to the same `layer`).
    RenderTarget* composedLayer = &worldLayer_;
    if (tilt != 0) {
        finalLayer_.renderTo(renderer, [&] {
            finalLayer_.clear({0, 0, 0, 0});
            // V (pygame degrees) = degrees(radians(tilt)) == tilt; angle_SDL = -V = -tilt
            Canvas::blitRotated(renderer, worldLayer_.texture(), frame.screenWidth / 2.0, frame.screenHeight / 2.0,
                                 frame.screenWidth, frame.screenHeight, -tilt);
        });
        composedLayer = &finalLayer_;
    }

    RenderTarget& bloomResult = bloom_.getBloom(renderer, composedLayer->texture(), frame.screenWidth, frame.screenHeight);
    composedLayer->renderTo(renderer, [&] {
        Canvas::blit(renderer, bloomResult.texture(), 0, 0, frame.screenWidth, frame.screenHeight, BlendModes::rgbAdd());
    });

    Canvas::blit(renderer, composedLayer->texture(), 0, 0, frame.screenWidth, frame.screenHeight);

    if (crosshair) {
        // was: the SECOND crosshair draw, AFTER the tilt-rotation step --
        // stays screen-fixed regardless of tilt, unlike the first
        // (gray) crosshair drawn inside worldLayer_ above.
        double size = 10.0;
        Canvas::line(renderer, {frame.screenWidth / 2.0 - size, frame.screenHeight / 2.0},
                     {frame.screenWidth / 2.0 + size, frame.screenHeight / 2.0}, Color{255, 0, 0, 255}, 2);
        Canvas::line(renderer, {frame.screenWidth / 2.0, frame.screenHeight / 2.0 - size},
                     {frame.screenWidth / 2.0, frame.screenHeight / 2.0 + size}, Color{255, 0, 0, 255}, 2);
    }
}
