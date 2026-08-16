#pragma once
#include <cstdint>
#include <SDL.h>
#include "Core.h"
#include "RenderTarget.h"

// Ported from health_bar.py.
//
// `targeted` is a class-level (shared/static) attribute in the Python --
// only ONE HealthBar across the entire game can be "targeted" (drawn with
// a distinct highlighted outline) at a time; it's overwritten globally
// wherever trigger(direct=true) is called, from any HealthBar instance.
// Preserved here as a static member, matching that global-shared-state
// design exactly (not something to "fix" -- it's how the original decides
// which health bar the player is actively focused on, e.g. via the laser).
class HealthBar {
public:
    static HealthBar* targeted; // was: HealthBar.targeted

    // `renderer` param added (not in the Python constructor) since our
    // internal scratch surface is a GPU texture (RenderTarget) that must
    // be created against a renderer, unlike a pygame.Surface.
    HealthBar(SDL_Renderer* renderer, double maxHealth, int thickness = 9);

    // was: def trigger(self, direct=False)
    void trigger(bool direct = false);

    // was: def draw(self, surface, color, coords, health, time=None)
    // Renders onto whatever target is currently bound to `renderer`,
    // matching the Canvas/RenderTarget convention established elsewhere --
    // callers select the destination beforehand rather than passing a
    // surface handle in. timeMs < 0 means "use Time::nowMs()" (matches
    // Python's time=None default).
    void draw(SDL_Renderer* renderer, Color color, Vec2 coords, double health, int64_t timeMs = -1);

private:
    double lastTriggered_ = 0.0;
    double maxHealth_;
    int thickness_;
    double scale_;
    double width_;
    RenderTarget surface_;
};
