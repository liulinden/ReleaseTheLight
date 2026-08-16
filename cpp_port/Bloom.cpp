#include "Bloom.h"
#include "Canvas.h"
#include "BlendModes.h"
#include <algorithm>
#include <cmath>
#include <vector>

namespace {
void resizeIfNeeded(RenderTarget& target, SDL_Renderer* renderer, int& curW, int& curH, int w, int h) {
    if (curW != w || curH != h) {
        target = RenderTarget(renderer, w, h);
        curW = w;
        curH = h;
    }
}
} // namespace

RenderTarget& Bloom::getBloom(SDL_Renderer* renderer, SDL_Texture* source, int fullW, int fullH,
                               int threshold, int downscale, int blurPasses, double intensity) {
    int smallW = std::max(1, fullW / downscale);
    int smallH = std::max(1, fullH / downscale);
    int tinyW = std::max(1, smallW / 2);
    int tinyH = std::max(1, smallH / 2);

    resizeIfNeeded(full_, renderer, fullW_, fullH_, fullW, fullH);
    resizeIfNeeded(small_, renderer, smallW_, smallH_, smallW, smallH);
    resizeIfNeeded(tiny_, renderer, tinyW_, tinyH_, tinyW, tinyH);
    // temp_ used both for the intensity>1 self-add-avoidance copy and the
    // intensity<1 dim pass -- sized to full resolution to cover both uses.
    resizeIfNeeded(temp_, renderer, tempW_, tempH_, fullW, fullH);

    // --- 1. Downscale FIRST (matches the Python's stated rationale: all
    //        the CPU pixel work below runs on a small image, not full res) ---
    small_.renderTo(renderer, [&] {
        small_.clear({0, 0, 0, 0});
        Canvas::blit(renderer, source, 0, 0, smallW, smallH);
    });

    // --- 2. Threshold via raw pixel readback/rewrite (replaces numpy) ---
    {
        std::vector<uint8_t> buf(static_cast<size_t>(smallW) * smallH * 4);
        SDL_Texture* prevTarget = SDL_GetRenderTarget(renderer);
        SDL_SetRenderTarget(renderer, small_.texture());
        SDL_RenderReadPixels(renderer, nullptr, SDL_PIXELFORMAT_RGBA32, buf.data(), smallW * 4);
        SDL_SetRenderTarget(renderer, prevTarget);

        for (int y = 0; y < smallH; ++y) {
            uint8_t* row = buf.data() + static_cast<size_t>(y) * smallW * 4;
            for (int x = 0; x < smallW; ++x) {
                uint8_t* px = row + x * 4;
                double luminance = px[0] * 0.299 + px[1] * 0.587 + px[2] * 0.114;
                if (luminance < threshold) {
                    px[0] = px[1] = px[2] = px[3] = 0; // zero RGB and alpha, matching the Python's mask
                }
            }
        }

        SDL_UpdateTexture(small_.texture(), nullptr, buf.data(), smallW * 4);
    }

    // --- 3. Blur passes: shrink/grow via GPU texture scaling (cheap box blur) ---
    for (int i = 0; i < blurPasses; ++i) {
        tiny_.renderTo(renderer, [&] {
            tiny_.clear({0, 0, 0, 0});
            Canvas::blit(renderer, small_.texture(), 0, 0, tinyW, tinyH);
        });
        small_.renderTo(renderer, [&] {
            small_.clear({0, 0, 0, 0});
            Canvas::blit(renderer, tiny_.texture(), 0, 0, smallW, smallH);
        });
    }

    // --- 4. Upscale back to full size ---
    full_.renderTo(renderer, [&] {
        full_.clear({0, 0, 0, 0});
        Canvas::blit(renderer, small_.texture(), 0, 0, fullW, fullH);
    });

    // --- 5. Apply intensity ---
    if (intensity > 1.0) {
        int extraPasses = static_cast<int>(intensity) - 1;
        for (int i = 0; i < extraPasses; ++i) {
            // Can't read from and render to the same texture in one draw
            // call -- copy full_ into temp_ first (a plain, unblended
            // copy), then additively blit temp_ back onto full_.
            temp_.renderTo(renderer, [&] {
                Canvas::blit(renderer, full_.texture(), 0, 0, fullW, fullH, SDL_BLENDMODE_NONE);
            });
            full_.renderTo(renderer, [&] {
                Canvas::blit(renderer, temp_.texture(), 0, 0, fullW, fullH, BlendModes::rgbAdd());
            });
        }
    } else if (intensity < 1.0) {
        int shade = std::clamp(static_cast<int>(255 * intensity), 0, 255);
        // multiplyTint reads the currently-bound render target's existing
        // content via blend hardware (not texture sampling), so this is
        // safe even though it's "self"-modifying full_ -- no self-blit
        // hazard here, unlike the intensity>1 branch above.
        full_.renderTo(renderer, [&] {
            Canvas::multiplyTint(renderer, Rect{0, 0, fullW, fullH}, Color{
                static_cast<uint8_t>(shade), static_cast<uint8_t>(shade), static_cast<uint8_t>(shade), 255});
        });
    }

    return full_;
}
