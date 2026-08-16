#pragma once
#include <vector>
#include <memory>
#include <string>
#include <unordered_map>
#include <SDL.h>
#include <SDL_ttf.h>
#include "Core.h"
#include "Frame.h"
#include "World.h"
#include "ChargeDisplay.h"
#include "LoadingScreen.h"

// Ported from releaseTheLight.py (class Game).
//
// FONT GAP CARRIED OVER: the Python uses pygame.font.SysFont("Arial", 16)
// for the FPS counter, and interaction_display.py separately needed the
// actual "maiandragd" TTF (flagged back when InteractionDisplay was
// ported, still unresolved). SDL_ttf has no by-name system-font
// resolution the way pygame.font.SysFont does, so both need a real font
// FILE PATH. This class takes one as a constructor parameter (used for
// both the FPS counter and passed through to World::init for
// InteractionDisplay) rather than hardcoding a guess -- caller must
// supply a real path.
class Game {
public:
    Game(SDL_Window* window, SDL_Renderer* renderer, const std::string& fontPath,
         int fps = 60, bool fullWorld = true, bool devMode = false, LoadingScreen* loadingScreen = nullptr);
    ~Game(); // closes font_ via TTF_CloseFont if it was opened -- found as a real (minor) leak during hang debugging

    // was: def set_window(self, window)
    void setWindow(SDL_Window* window, SDL_Renderer* renderer);

    // was: def coords_window_to_world(self, coords)
    Vec2 coordsWindowToWorld(Vec2 coords) const;
    // was: def get_world_centered_cam(self)
    Vec2 getWorldCenteredCam() const;
    // was: def get_centered_cam(self, center)
    Vec2 getCenteredCam(Vec2 center) const;
    // was: def get_window_center_world_coords(self)
    Vec2 getWindowCenterWorldCoords() const;
    // was: def set_zoom(self, new_zoom, zoom_center)
    void setZoom(double newZoom, Vec2 zoomCenter);
    // was: def update_cam_pos(self, fps, zoom, player_x, player_y, player_x_speed, player_y_speed)
    // FLAGGED DEAD CODE PRESERVED: cam_offset_x/y are computed via an
    // accumulate-then-clamp sequence, then immediately reset to (0, 0)
    // right after -- the entire clamp computation has zero effect on the
    // final camera position. The clamp bounds are ALSO backwards on their
    // own (`min(max(x, POS), NEG)` with POS > NEG always evaluates to NEG
    // regardless of x) -- two independent bugs compounding into one
    // provably-inert block. Preserved exactly (computed, then discarded)
    // rather than removed, per the project's "preserve quirks" approach.
    void updateCamPos(double fps, double zoom, double playerX, double playerY, double playerXSpeed, double playerYSpeed);

    // was: def setup(self)
    void setup();

    // was: def run(self) -- contains pygame's main loop; SDL_PollEvent
    // driven here. Returns when the user quits (window close, Escape).
    void run();

    std::vector<double> defaultZooms;
    int worldWidth, worldHeight;
    double offsetX = 0.0, offsetY = 0.0;
    bool developingMode;

private:
    void handleEvent(const SDL_Event& event, int mouseX, int mouseY, bool& running);
    void renderFpsCounter(double fps);

    SDL_Window* window_;
    SDL_Renderer* renderer_;
    int windowWidth_, windowHeight_;
    std::string fontPath_;
    TTF_Font* font_ = nullptr;

    int fps_;
    LoadingScreen* loadingScreen_;

    std::unique_ptr<World> gameWorld_;
    std::unique_ptr<ChargeDisplay> chargeDisplay_;

    // was: self.keys_down (keycode entries only -- "left_mouse"/
    // "right_mouse" string entries split into leftMouseHeld_/rightMouseHeld_)
    std::unordered_map<SDL_Keycode, bool> keysDown_;
    bool leftMouseHeld_ = false, rightMouseHeld_ = false;

    // was: self.events -- edge-triggered, reset every frame
    struct FrameEvents {
        bool leftMouseDown = false, leftMouseUp = false, rightMouseDown = false, rightMouseUp = false;
        bool space = false, rightArrow = false, leftArrow = false;
    };
    FrameEvents events_;

    double zoom_ = 1.0;
    Vec2 defaultCamCoords_{0.0, 0.0};
    double camX_ = 0.0, camY_ = 0.0;
    double camOffsetX_ = 0.0, camOffsetY_ = 0.0;

    double shake_ = 0.0;
    double tilt_ = 0.0;

    bool kindVisibility_ = false;
    bool visibleHitboxes_ = false;
    bool loadingDebug_ = false;
    bool crosshair_ = false;
    bool showFps_;
};
