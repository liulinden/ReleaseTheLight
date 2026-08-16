#pragma once
#include <string>
#include <vector>
#include <unordered_map>
#include <memory>
#include <SDL.h>
#include <SDL_ttf.h>
#include "Core.h"
#include "Frame.h"
#include "RenderTarget.h"
#include "Anchor.h"

// was: display = tuple of str and pygame key constants, e.g.
// (pygame.K_e, "") or ("Hold", pygame.K_e, "to drain")
struct DisplaySegment {
    bool isKey = false;
    std::string text;                 // used when !isKey
    SDL_Keycode key = SDLK_UNKNOWN;    // used when isKey
    bool operator==(const DisplaySegment& o) const {
        return isKey == o.isKey && text == o.text && key == o.key;
    }
};
using DisplaySpec = std::vector<DisplaySegment>;
inline DisplaySegment TextSeg(std::string s) { return { false, std::move(s), SDLK_UNKNOWN }; }
inline DisplaySegment KeySeg(SDL_Keycode k)  { return { true, "", k }; }

// was: align="centered" / "top_centered" / "screen" string parameter.
// Split into two orthogonal concerns now that this is shared, reusable
// infrastructure rather than a one-off: Anchor (where on the item's own
// bounding box the reference point sits) and screenSpace (below) for
// coordinate space. "centered"->Anchor::Center, "top_centered"->
// Anchor::TopCenter.
class InteractionDisplay {
public:
    // was: def init(): InteractionDisplay.font = pygame.font.SysFont("maiandragd", font_size)
    // `fontPath` is a placeholder per our conversation -- swap for the
    // real font asset later without touching any other code.
    static void init(SDL_Renderer* renderer, const std::string& fontPath, int fontSize = 16);

    InteractionDisplay(SDL_Renderer* renderer, Vec2 coords, const DisplaySpec& display,
                        Color color = {255, 255, 255, 255}, Anchor anchor = Anchor::Center,
                        bool screenSpace = false);

    // was: def update_coordinates(self, coords)
    void updateCoordinates(Vec2 coords);

    // was: def tick(self, frame_length, primary, keys_down)
    void tick(double frameLength, bool primary, const std::unordered_map<SDL_Keycode, bool>& keysDown);

    // was: def draw(self, surface, frame, time=None, offset_x=0, offset_y=0) -> bool
    // Renders onto whatever target is currently bound to `renderer`.
    // Returns true if it drew (still visible), matching the Python's
    // return value, which InteractionDisplayManager uses to decide
    // whether to keep or drop a display.
    bool draw(SDL_Renderer* renderer, const Frame& frame, int64_t timeMs = -1);

    // Touched directly by InteractionDisplayManager, matching Python's
    // `display.post_active = False` direct attribute access.
    bool active = false;
    bool postActive = false;

private:
    struct CachedDisplayData {
        double w = 0, h = 0;
        RenderTarget text;    // baked white+black-outline text + static circle-ring decoration (per spec, cached)
        RenderTarget scratch; // SHARED per-frame scratch buffer -- see class-level note on why sharing is safe
        std::unordered_map<SDL_Keycode, double> circleX; // x-offset of each key-indicator circle within the display
    };
    static std::shared_ptr<CachedDisplayData> getOrBuildCache(SDL_Renderer* renderer, const DisplaySpec& display);

    std::shared_ptr<CachedDisplayData> cached_;
    std::unordered_map<SDL_Keycode, double> circleAlpha_; // per-instance (was: self.circles[key][1])

    double x_, y_;
    Color color_;
    Anchor anchor_;
    bool screenSpace_;

    double opacity_ = 0.0;
    bool keyReleased_ = false;
    double rise_ = 0.0;
};

// was: InteractionDisplayManager
class InteractionDisplayManager {
public:
    void tick(double frameLength, const std::unordered_map<SDL_Keycode, bool>& keysDown);
    void draw(SDL_Renderer* renderer, const Frame& frame, int64_t timeMs = -1);

    // was: def display_in_range(self, display)
    void displayInRange(InteractionDisplay* display);
    // was: def display_out_range(self, display, complete=False)
    void displayOutRange(InteractionDisplay* display, bool complete = false);

private:
    std::vector<InteractionDisplay*> onScreenDisplays_;
    std::vector<InteractionDisplay*> inRangeDisplays_;
};
