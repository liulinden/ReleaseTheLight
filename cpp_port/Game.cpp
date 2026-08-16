#include "Game.h"
#include "Canvas.h"
#include "GlobalAssets.h"
#include "Util.h"
#include "Time.h"
#include "Config.h"
#include <cmath>
#include <algorithm>
#include <iostream>

Game::Game(SDL_Window* window, SDL_Renderer* renderer, const std::string& fontPath,
           int fps, bool fullWorld, bool devMode, LoadingScreen* loadingScreen)
    : developingMode(devMode), fontPath_(fontPath), fps_(fps), loadingScreen_(loadingScreen), showFps_(devMode) {
    setWindow(window, renderer);

    // was: if dev_mode: self.DEFAULT_ZOOMS = [0.1,1,2] else [1,1.8]
    defaultZooms = devMode ? std::vector<double>{0.1, 1.0, 2.0} : std::vector<double>{1.0, 1.8};

    worldWidth = 15 * Config::CHUNK_SIZE;
    worldHeight = 100 * Config::CHUNK_SIZE;
    if (!fullWorld) {
        worldWidth = 5 * Config::CHUNK_SIZE;
        worldHeight = 10 * Config::CHUNK_SIZE;
    }
}

Game::~Game() {
    if (font_) TTF_CloseFont(font_);
}

void Game::setWindow(SDL_Window* window, SDL_Renderer* renderer) {
    window_ = window;
    renderer_ = renderer;
    SDL_GetWindowSize(window_, &windowWidth_, &windowHeight_);
}

Vec2 Game::coordsWindowToWorld(Vec2 coords) const {
    return { camX_ + (coords.x - offsetX) / zoom_, camY_ + (coords.y - offsetY) / zoom_ };
}

Vec2 Game::getWorldCenteredCam() const {
    return getCenteredCam({ worldWidth / 2.0, worldHeight / 2.0 });
}

Vec2 Game::getCenteredCam(Vec2 center) const {
    return { center.x - windowWidth_ / zoom_ / 2.0, center.y - windowHeight_ / zoom_ / 2.0 };
}

Vec2 Game::getWindowCenterWorldCoords() const {
    return coordsWindowToWorld({ windowWidth_ / 2.0, windowHeight_ / 2.0 });
}

void Game::setZoom(double newZoom, Vec2 zoomCenter) {
    double zoomRatio = zoom_ / newZoom;
    camX_ -= (zoomCenter.x - camX_) * (zoomRatio - 1.0);
    camY_ -= (zoomCenter.y - camY_) * (zoomRatio - 1.0);
    zoom_ = newZoom;
}

// def update_cam_pos(...): see Game.h for the preserved dead-code note.
void Game::updateCamPos(double fps, double zoom, double playerX, double playerY, double playerXSpeed, double playerYSpeed) {
    double maxY = worldHeight - 100.0;
    double frameLength = 1000.0 / fps;
    camOffsetX_ += 2 * playerXSpeed * frameLength;
    camOffsetY_ += 2 * playerYSpeed * frameLength;
    camOffsetX_ = std::min(std::max(camOffsetX_, windowWidth_ / zoom * (1.0 / 6.0)), windowWidth_ / zoom * (-1.0 / 6.0));
    camOffsetY_ = std::min(std::max(camOffsetY_, windowHeight_ / zoom * (1.0 / 6.0)), windowHeight_ / zoom * (-1.0 / 6.0));
    camOffsetX_ = 0;
    camOffsetY_ = 0;

    double goalX = std::max(windowWidth_ / zoom / 2.0, std::min(worldWidth - windowWidth_ / zoom / 2.0, playerX));
    if (windowWidth_ / zoom / 2.0 > worldWidth - windowWidth_ / zoom / 2.0) {
        goalX = playerX;
    }
    double goalY = std::max(-100.0, std::min(maxY, playerY));
    camX_ += (camOffsetX_ + goalX - camX_ - windowWidth_ / zoom / 2.0) * frameLength / 200.0;
    camY_ += (camOffsetY_ + goalY - camY_ - windowHeight_ / zoom / 2.0) * frameLength / 200.0;
}

// def setup(self): ...
void Game::setup() {
    if (loadingScreen_) loadingScreen_->put(0.0, "Starting game setup");

    auto sections = loadingScreen_ ? loadingScreen_->subsections({0.0, 0.4}) : std::vector<LoadingScreen>{};

    GlobalAssets::loadAssets(renderer_, true);

    font_ = TTF_OpenFont(fontPath_.c_str(), 16);
    if (!font_) {
        std::cerr << "[Game] failed to open font at " << fontPath_ << ": " << TTF_GetError() << "\n";
    }

    World::init(renderer_, fontPath_);
    gameWorld_ = std::make_unique<World>(renderer_, worldWidth, worldHeight, developingMode);

    chargeDisplay_ = std::make_unique<ChargeDisplay>(renderer_);

    keysDown_[SDLK_w] = false;
    keysDown_[SDLK_a] = false;
    keysDown_[SDLK_d] = false;
    keysDown_[SDLK_e] = false;

    zoom_ = defaultZooms.back();
    defaultCamCoords_ = { getWorldCenteredCam().x, -100.0 };
    camX_ = defaultCamCoords_.x;
    camY_ = defaultCamCoords_.y;
    camOffsetX_ = 0;
    camOffsetY_ = 0;

    shake_ = 0;
    tilt_ = 0;

    if (loadingScreen_) loadingScreen_->put(1.0, "Game setup complete.");
}

void Game::renderFpsCounter(double fps) {
    if (!font_) return;
    std::string text = "FPS: " + std::to_string(static_cast<int>(std::round(fps)));
    SDL_Color white{255, 255, 255, 255};
    SDL_Surface* surf = TTF_RenderText_Blended(font_, text.c_str(), white);
    if (!surf) return;
    SDL_Texture* tex = SDL_CreateTextureFromSurface(renderer_, surf);
    int w = surf->w, h = surf->h;
    SDL_FreeSurface(surf);
    if (!tex) return;
    SDL_Rect dst{ windowWidth_ - 10 - w, 10, w, h };
    SDL_RenderCopy(renderer_, tex, nullptr, &dst);
    SDL_DestroyTexture(tex);
}

// def run(self): -- see class body below for the event loop.
void Game::run() {
    bool running = true;
    double previousTime = Time::nowMs();
    double practicalFps = fps_;
    double clockLastTick = Time::nowMs(); // was: pygame.time.Clock's own internal last-tick timestamp -- tracked SEPARATELY from previousTime (which drives practical_fps), matching that Clock.tick() measures from its own previous call, not from the practical_fps measurement point.

    while (running) {
        int mouseX, mouseY;
        SDL_GetMouseState(&mouseX, &mouseY);

        events_ = FrameEvents{};

        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            handleEvent(event, mouseX, mouseY, running);
            if (!running) return;
        }

        PlayerInput input;
        input.keyW = keysDown_[SDLK_w];
        input.keyA = keysDown_[SDLK_a];
        input.keyD = keysDown_[SDLK_d];
        input.leftMouseHeld = leftMouseHeld_;
        input.rightMouseHeld = rightMouseHeld_;
        input.leftMouseDownEvent = events_.leftMouseDown;
        input.leftMouseUpEvent = events_.leftMouseUp;
        input.rightMouseDownEvent = events_.rightMouseDown;
        input.rightMouseUpEvent = events_.rightMouseUp;
        input.spaceEvent = events_.space;
        input.rightArrowEvent = events_.rightArrow;
        input.leftArrowEvent = events_.leftArrow;

        Vec2 mouseWorld = coordsWindowToWorld({ static_cast<double>(mouseX), static_cast<double>(mouseY) });

        Frame tickFrame;
        tickFrame.left = camX_; tickFrame.top = camY_; tickFrame.zoom = zoom_;
        tickFrame.viewWidth = windowWidth_; tickFrame.viewHeight = windowHeight_;

        if (gameWorld_->tick(practicalFps, tickFrame, mouseWorld, input, keysDown_)) {
            camX_ = defaultCamCoords_.x;
            camY_ = defaultCamCoords_.y;
            gameWorld_->healNests();
            gameWorld_->removeEnemies();
        }

        PlayerChargeSnapshot snap{
            gameWorld_->player.chargeCapacity, gameWorld_->player.charges, gameWorld_->player.practicalCharges,
            gameWorld_->player.filterType, gameWorld_->player.filterChangeRight, gameWorld_->player.nCells, gameWorld_->player.y
        };
        chargeDisplay_->update(practicalFps, snap);

        updateCamPos(practicalFps, zoom_, gameWorld_->player.x, gameWorld_->player.y, gameWorld_->player.xSpeed, gameWorld_->player.ySpeed);

        SDL_SetRenderDrawColor(renderer_, 255, 255, 255, 255);
        SDL_RenderClear(renderer_);

        if (gameWorld_->player.laser) {
            if (gameWorld_->player.laser->damageFrame) {
                shake_ = gameWorld_->player.laserAttributes.baseXpl / 8.0;
            } else {
                shake_ += gameWorld_->player.laserAttributes.baseXpl / 450.0;
            }
        }
        shake_ *= 0.9;
        if (shake_ < 0.02) shake_ = 0;

        if (gameWorld_->player.queuedDamage > 0) {
            double t = std::sqrt(gameWorld_->player.queuedDamage * 5.0) * 2.0;
            t = std::min(t, 10.0);
            t = std::copysign(t, gameWorld_->player.queuedDamage * -gameWorld_->player.xSpeed);
            if (std::abs(t) > std::abs(tilt_)) tilt_ = t;
        } else {
            double delta = 1.8;
            if (tilt_ > 0) tilt_ = std::max(0.0, tilt_ - delta);
            else if (tilt_ < 0) tilt_ = std::min(0.0, tilt_ + delta);
        }

        Frame drawFrame;
        drawFrame.left = camX_ + (2 * Util::randomDouble() - 1) * shake_;
        drawFrame.top = camY_ + (2 * Util::randomDouble() - 1) * shake_;
        drawFrame.zoom = zoom_;
        drawFrame.viewWidth = windowWidth_;
        drawFrame.viewHeight = windowHeight_;
        int realW, realH;
        SDL_GetWindowSize(window_, &realW, &realH);
        drawFrame.screenWidth = realW;
        drawFrame.screenHeight = realH;
        drawFrame.offsetX = offsetX;
        drawFrame.offsetY = offsetY;

        gameWorld_->drawWorld(renderer_, drawFrame, visibleHitboxes_, kindVisibility_, tilt_, crosshair_);

        chargeDisplay_->draw(renderer_);

        if (loadingDebug_) {
            SDL_SetRenderDrawColor(renderer_, 0, 255, 0, 255);
            SDL_Rect r{ static_cast<int>(offsetX), static_cast<int>(offsetY), windowWidth_, windowHeight_ };
            SDL_RenderDrawRect(renderer_, &r);
        }

        practicalFps = std::max(1.0, std::round(1000.0 / (Time::nowMs() - previousTime)));
        practicalFps = std::max(30.0, practicalFps);
        previousTime = Time::nowMs();

        if (showFps_) {
            // was: self.clock.get_fps() -- pygame's Clock tracks a
            // smoothed real FPS separately from practical_fps (used for
            // physics); practicalFps is a reasonable stand-in here (no
            // separate smoothed-FPS tracker implemented).
            renderFpsCounter(practicalFps);
        }

        SDL_RenderPresent(renderer_);

        // was: self.clock.tick(self.fps) -- simple frame-rate cap via
        // delay, measured against clockLastTick (this loop's own previous
        // iteration), not `previousTime` (which drives practical_fps and
        // was just updated moments ago above -- using it here would make
        // elapsed almost always ~0, defeating the frame cap).
        double frameTargetMs = 1000.0 / fps_;
        double nowForClock = Time::nowMs();
        double clockElapsed = nowForClock - clockLastTick;
        if (clockElapsed < frameTargetMs) {
            SDL_Delay(static_cast<uint32_t>(frameTargetMs - clockElapsed));
        }
        clockLastTick = Time::nowMs();
    }
}

void Game::handleEvent(const SDL_Event& event, int mouseX, int mouseY, bool& running) {
    (void)mouseX;
    if (event.type == SDL_QUIT) {
        std::cout << "quit\n";
        running = false;
        return;
    }

    if (event.type == SDL_MOUSEBUTTONDOWN) {
        if (event.button.button == SDL_BUTTON_LEFT) {
            events_.leftMouseDown = true;
            leftMouseHeld_ = true;
        } else if (event.button.button == SDL_BUTTON_RIGHT) {
            events_.rightMouseDown = true;
            rightMouseHeld_ = true;
        }
        // was: x, y = self.coords_window_to_world(...) -- computed but its
        // result was never used anywhere (no assignment, no side effect).
        // Genuinely dead, unlike update_cam_pos's dead block above (which
        // still mutates state even though pointlessly) -- omitted here.
    }

    if (event.type == SDL_MOUSEBUTTONUP) {
        if (event.button.button == SDL_BUTTON_LEFT) {
            events_.leftMouseUp = true;
            leftMouseHeld_ = false;
        } else if (event.button.button == SDL_BUTTON_RIGHT) {
            events_.rightMouseUp = true;
            rightMouseHeld_ = false;
        }
    }

    if (event.type == SDL_KEYDOWN) {
        SDL_Keycode key = event.key.keysym.sym;
        if (keysDown_.count(key)) keysDown_[key] = true;

        if (key == SDLK_SPACE) events_.space = true;
        if (key == SDLK_RIGHT) events_.rightArrow = true;
        if (key == SDLK_LEFT) events_.leftArrow = true;

        if (key == SDLK_ESCAPE) {
            running = false;
            return;
        }

        if (key == SDLK_F4) showFps_ = !showFps_;

        if (developingMode) {
            if (key == SDLK_z) {
                auto it = std::find(defaultZooms.begin(), defaultZooms.end(), zoom_);
                size_t idx = (it != defaultZooms.end()) ? static_cast<size_t>(it - defaultZooms.begin()) : 0;
                double newZoom = (idx == defaultZooms.size() - 1) ? defaultZooms[0] : defaultZooms[idx + 1];
                setZoom(newZoom, { gameWorld_->player.x, gameWorld_->player.y });
            } else if (key == SDLK_i) {
                std::array<double, 3> addedDist{0, 0, 0};
                addedDist[static_cast<int>(gameWorld_->player.filterType)] = 1;
                gameWorld_->player.addCharge(25, addedDist);
            } else if (key == SDLK_0) {
                kindVisibility_ = !kindVisibility_;
            } else if (key == SDLK_h) {
                visibleHitboxes_ = !visibleHitboxes_;
            } else if (key == SDLK_t) {
                Vec2 worldPos = coordsWindowToWorld({ static_cast<double>(mouseX), static_cast<double>(mouseY) });
                gameWorld_->player.x = worldPos.x;
                gameWorld_->player.y = worldPos.y;
                gameWorld_->player.updateRect();
            } else if (key == SDLK_p) {
                // was: print(self.game_world.player.__dict__) -- Python
                // reflection dump, no direct C++ equivalent. Prints the
                // key fields manually instead (same debugging intent).
                std::cout << "player: pos=(" << gameWorld_->player.x << "," << gameWorld_->player.y << ")"
                          << " speed=(" << gameWorld_->player.xSpeed << "," << gameWorld_->player.ySpeed << ")"
                          << " charges=[" << gameWorld_->player.charges[0] << "," << gameWorld_->player.charges[1]
                          << "," << gameWorld_->player.charges[2] << "]"
                          << " filterType=" << static_cast<int>(gameWorld_->player.filterType)
                          << " nCells=" << gameWorld_->player.nCells << "\n";
            } else if (key == SDLK_l) {
                if (!loadingDebug_) {
                    windowWidth_ = 300;
                    windowHeight_ = 200;
                    int realW, realH;
                    SDL_GetWindowSize(window_, &realW, &realH);
                    offsetX = (realW - windowWidth_) / 2.0;
                    offsetY = (realH - windowHeight_) / 2.0;
                } else {
                    SDL_GetWindowSize(window_, &windowWidth_, &windowHeight_);
                    offsetX = 0;
                    offsetY = 0;
                }
                loadingDebug_ = !loadingDebug_;
            } else if (key == SDLK_F1) {
                crosshair_ = !crosshair_;
            }
        }
    }

    if (event.type == SDL_KEYUP) {
        SDL_Keycode key = event.key.keysym.sym;
        if (keysDown_.count(key)) keysDown_[key] = false;
    }
}
