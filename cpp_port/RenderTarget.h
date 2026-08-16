#pragma once
#include <SDL.h>
#include <functional>
#include "Core.h"

// Wraps an SDL_TEXTUREACCESS_TARGET texture -- our equivalent of
// pygame.Surface(size, SRCALPHA) used as a persistent per-instance scratch
// surface (HealthBar.surface, InteractionDisplay.surface, ChargeDisplay's
// scratch_surfaces/cell_surface pattern): fill it, draw/blit onto it, then
// composite the whole thing onto the real render target, often with an
// overall alpha (pygame's Surface.set_alpha()) or blend mode.
class RenderTarget {
public:
    RenderTarget() = default;
    RenderTarget(SDL_Renderer* renderer, int width, int height);
    ~RenderTarget();
    RenderTarget(RenderTarget&& other) noexcept;
    RenderTarget& operator=(RenderTarget&& other) noexcept;
    RenderTarget(const RenderTarget&) = delete;
    RenderTarget& operator=(const RenderTarget&) = delete;

    int width() const { return w_; }
    int height() const { return h_; }
    SDL_Texture* texture() const { return tex_; }
    bool valid() const { return tex_ != nullptr; }

    // was: self.surface.fill((r,g,b,a))
    void clear(Color c = {0, 0, 0, 0});

    // was: self.surface.set_alpha(opacity)  (0-255, applied on next blit)
    void setAlpha(uint8_t alpha);

    // Binds this texture as the active render target for `renderer` for
    // the duration of `fn`, then restores whatever was previously bound.
    // All Canvas:: draw calls and blit() inside `fn` land on this texture.
    void renderTo(SDL_Renderer* renderer, const std::function<void()>& fn);

private:
    void destroy();

    SDL_Renderer* renderer_ = nullptr;
    SDL_Texture* tex_ = nullptr;
    int w_ = 0, h_ = 0;
};

namespace Canvas {

// Draws `tex` onto whatever target is currently bound to `renderer`, at
// world/screen position (x, y) using tex's native size. Matches
// pygame's `surface.blit(other, (x, y))`.
void blit(SDL_Renderer* renderer, SDL_Texture* tex, double x, double y,
          SDL_BlendMode mode = SDL_BLENDMODE_BLEND);

// Draws `tex`, scaled to (destW, destH), at (x, y). `flipHorizontal`
// mirrors the source horizontally (matches pygame.transform.flip(img,
// True, False), used for facing="left" sprites) -- added here (rather
// than a separate function) since it's the same underlying SDL_RenderCopyEx
// call with a flip flag, first needed by Enemy's facing-dependent draws.
void blit(SDL_Renderer* renderer, SDL_Texture* tex, double x, double y,
          double destW, double destH, SDL_BlendMode mode = SDL_BLENDMODE_BLEND,
          bool flipHorizontal = false);

// Draws `tex`, scaled to (destW, destH), rotated by `angleDeg` around its
// own center, with that center placed at screen position (centerX,
// centerY). Replaces the pygame pattern of pre-rotating a Surface (which
// grows its own bounding box) then blitting the result -- SDL_RenderCopyEx
// rotates at draw time on the GPU, so there's no separate "already
// rotated" texture to manage.
//
// SIGN CONVENTION WARNING (verified empirically, not just from docs --
// rendered an asymmetric shape through both and compared pixel output):
// pygame.transform.rotate(img, V) rotates COUNTER-CLOCKWISE for positive
// V. SDL_RenderCopyEx (which this wraps) rotates CLOCKWISE for positive
// angleDeg. These are OPPOSITE conventions. To reproduce a Python
// `pygame.transform.rotate(img, V)` call here, pass `angleDeg = -V`, NOT
// V directly -- ChargeDisplay's icon/cell rotation had exactly this sign
// bug in an earlier pass, caught and fixed once this was verified. Every
// new call site translating a pygame rotate call needs this same
// negation applied explicitly; it's easy to silently get backward.
void blitRotated(SDL_Renderer* renderer, SDL_Texture* tex, double centerX, double centerY,
                  double destW, double destH, double angleDeg, SDL_BlendMode mode = SDL_BLENDMODE_BLEND);

// Draws a cropped SUB-REGION of `tex` (srcRect, in tex's own pixel
// coordinates), scaled to (destW, destH) at (destX, destY). Every other
// blit helper here copies a whole texture; this is the one primitive that
// needed source-rect cropping (Terrain's rim-glow carve compositing reads
// a sub-region of the chunk's visual texture).
void blitRegion(SDL_Renderer* renderer, SDL_Texture* tex, Rect srcRect,
                 double destX, double destY, double destW, double destH,
                 SDL_BlendMode mode = SDL_BLENDMODE_BLEND);

} // namespace Canvas
