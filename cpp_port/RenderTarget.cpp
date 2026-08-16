#include "RenderTarget.h"

RenderTarget::RenderTarget(SDL_Renderer* renderer, int width, int height)
    : renderer_(renderer), w_(width), h_(height) {
    tex_ = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_RGBA32,
                              SDL_TEXTUREACCESS_TARGET, width, height);
    if (tex_) {
        SDL_SetTextureBlendMode(tex_, SDL_BLENDMODE_BLEND);
        clear();
    }
}

RenderTarget::~RenderTarget() { destroy(); }

void RenderTarget::destroy() {
    if (tex_) {
        SDL_DestroyTexture(tex_);
        tex_ = nullptr;
    }
}

RenderTarget::RenderTarget(RenderTarget&& other) noexcept
    : renderer_(other.renderer_), tex_(other.tex_), w_(other.w_), h_(other.h_) {
    other.tex_ = nullptr;
}

RenderTarget& RenderTarget::operator=(RenderTarget&& other) noexcept {
    if (this != &other) {
        destroy();
        renderer_ = other.renderer_;
        tex_ = other.tex_;
        w_ = other.w_;
        h_ = other.h_;
        other.tex_ = nullptr;
    }
    return *this;
}

void RenderTarget::clear(Color c) {
    if (!tex_) return;
    renderTo(renderer_, [&] {
        SDL_SetRenderDrawBlendMode(renderer_, SDL_BLENDMODE_NONE); // overwrite, not blend, matches Surface.fill()
        SDL_SetRenderDrawColor(renderer_, c.r, c.g, c.b, c.a);
        SDL_RenderClear(renderer_);
        SDL_SetRenderDrawBlendMode(renderer_, SDL_BLENDMODE_BLEND);
    });
}

void RenderTarget::setAlpha(uint8_t alpha) {
    if (tex_) SDL_SetTextureAlphaMod(tex_, alpha);
}

void RenderTarget::renderTo(SDL_Renderer* renderer, const std::function<void()>& fn) {
    if (!tex_) return;
    SDL_Texture* previous = SDL_GetRenderTarget(renderer);
    SDL_SetRenderTarget(renderer, tex_);
    fn();
    SDL_SetRenderTarget(renderer, previous);
}

namespace Canvas {

void blit(SDL_Renderer* renderer, SDL_Texture* tex, double x, double y, SDL_BlendMode mode) {
    int iw = 0, ih = 0;
    SDL_QueryTexture(tex, nullptr, nullptr, &iw, &ih);
    SDL_SetTextureBlendMode(tex, mode);
    SDL_FRect dst{ static_cast<float>(x), static_cast<float>(y),
                   static_cast<float>(iw), static_cast<float>(ih) };
    SDL_RenderCopyF(renderer, tex, nullptr, &dst);
}

void blit(SDL_Renderer* renderer, SDL_Texture* tex, double x, double y,
          double destW, double destH, SDL_BlendMode mode, bool flipHorizontal) {
    SDL_SetTextureBlendMode(tex, mode);
    SDL_FRect dst{ static_cast<float>(x), static_cast<float>(y),
                   static_cast<float>(destW), static_cast<float>(destH) };
    SDL_RenderCopyExF(renderer, tex, nullptr, &dst, 0.0, nullptr,
                       flipHorizontal ? SDL_FLIP_HORIZONTAL : SDL_FLIP_NONE);
}

void blitRotated(SDL_Renderer* renderer, SDL_Texture* tex, double centerX, double centerY,
                  double destW, double destH, double angleDeg, SDL_BlendMode mode) {
    SDL_SetTextureBlendMode(tex, mode);
    SDL_Rect dst{
        static_cast<int>(std::lround(centerX - destW / 2.0)),
        static_cast<int>(std::lround(centerY - destH / 2.0)),
        static_cast<int>(std::lround(destW)),
        static_cast<int>(std::lround(destH))
    };
    // nullptr center = rotate around the destination rect's own center,
    // which is exactly what every current call site wants (Player's arm,
    // which needs an off-center pivot, will pass an explicit center when
    // we reach it rather than use this convenience overload).
    SDL_RenderCopyEx(renderer, tex, nullptr, &dst, angleDeg, nullptr, SDL_FLIP_NONE);
}

void blitRegion(SDL_Renderer* renderer, SDL_Texture* tex, Rect srcRect,
                 double destX, double destY, double destW, double destH, SDL_BlendMode mode) {
    SDL_SetTextureBlendMode(tex, mode);
    SDL_Rect src{ srcRect.x, srcRect.y, srcRect.w, srcRect.h };
    SDL_FRect dst{ static_cast<float>(destX), static_cast<float>(destY),
                   static_cast<float>(destW), static_cast<float>(destH) };
    SDL_RenderCopyF(renderer, tex, &src, &dst);
}

} // namespace Canvas
