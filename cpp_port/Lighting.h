#pragma once
#include <vector>
#include <SDL.h>
#include "Core.h"
#include "Frame.h"
#include "RenderTarget.h"
#include "LruCache.h"

// Ported from lighting.py.
//
// Structural notes (per the GPU-rendering decisions established earlier):
//   - No per-zoom pre-scaling of mist/gradient images (Python's
//     resized_light_im_gs) -- scaling happens at draw time via the
//     destination rect, so Lighting no longer needs a `default_zooms`
//     constructor argument. Side effect: rendering is no longer locked to
//     a fixed small set of zoom levels the way pygame's version was --
//     any zoom value scales correctly now, though gameplay may still only
//     ever *use* a small preset list (a Game/Player concern, not a
//     rendering one).
//   - GradientCache/MistParticleCache's premultiplied-alpha-into-RGB trick
//     (bake alpha into RGB, discard the alpha channel, so a software ADD
//     blit doesn't need real per-pixel alpha blending) is dropped. SDL's
//     built-in ADD blend mode already computes
//     `dst.rgb = src.rgb * src.a + dst.rgb` (verified earlier against a
//     real renderer) -- the exact generalization of what the premultiply
//     hack manually achieved -- so alpha is applied via
//     SDL_SetTextureAlphaMod at draw time instead (continuous, not
//     bucketed). The cache is kept (many simultaneous mist particles can
//     share a color, and tinting still needs a render-target switch worth
//     avoiding), but is now keyed by (source asset, snapped color) only --
//     tinting happens once at native resolution, and the destination size
//     no longer needs to be part of the key since scaling happens at blit
//     time.
//   - LRU-capped at 20 entries, matching the Python, so a continuously-
//     drifting color doesn't grow the cache unboundedly over a long
//     session.

class MistParticle {
public:
    MistParticle(double x, double y, int mistImageIndex, double baseSize, Color color);

    bool tick(double frameLength); // true when finished (was: return "end")
    void draw(SDL_Renderer* renderer, const Frame& frame, class Lighting& owner);

private:
    Color color_;
    int mistImageIndex_; // which of the 5 mist sprites -- fixed at spawn
    double baseSize_;    // one of {110, 130, 150} -- fixed at spawn
    double x_, y_;
    double xSpeed_, ySpeed_;
    double lifeTime_;
    double brightness_;
    double fadeIn_;
};

class Lighting {
public:
    // was: def init(): loads particles_mist_1..5, gradient_light, gradient_thick
    static void init(SDL_Renderer* renderer);

    Lighting();

    // was: def add_mist_particle(self, x, y, color=(255,255,255))
    void addMistParticle(double x, double y, Color color = {255, 255, 255, 255});

    // was: def tick_effects(self, frame_length)
    void tickEffects(double frameLength);

    // was: def draw_gradient(self, surface, frame, color, x, y, size=400, offset_x=0, offset_y=0)
    void drawGradient(SDL_Renderer* renderer, const Frame& frame, Color color, double x, double y,
                       double size = 400, int offsetX = 0, int offsetY = 0);

    // was: def draw_thick_gradient(self, surface, frame, x, y, offset_x=0, offset_y=0)
    void drawThickGradient(SDL_Renderer* renderer, const Frame& frame, double x, double y,
                            int offsetX = 0, int offsetY = 0);

    // was: def draw_effects(self, surface, frame, offset_x=0, offset_y=0)
    void drawEffects(SDL_Renderer* renderer, const Frame& frame);

    // Returns a native-resolution texture tinted by `color` (snapped) and
    // darkened by `darken`, from a persistent LRU cache keyed by
    // (source, snapped color). Used by both draw_gradient (public, via the
    // methods above) and MistParticle::draw (needs access to the same
    // cache -- hence public rather than duplicating this).
    RenderTarget& getTinted(SDL_Renderer* renderer, SDL_Texture* source, int srcW, int srcH,
                             Color color, double darken = 1.0);

private:
    std::vector<MistParticle> particles_;

    struct TintKey {
        SDL_Texture* source;
        uint8_t r, g, b;
        bool operator==(const TintKey& o) const {
            return source == o.source && r == o.r && g == o.g && b == o.b;
        }
    };
    struct TintKeyHash {
        size_t operator()(const TintKey& k) const;
    };
    LruCache<TintKey, RenderTarget, TintKeyHash> tintCache_{20};
};
