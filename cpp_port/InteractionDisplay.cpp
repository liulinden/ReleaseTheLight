#include "InteractionDisplay.h"
#include "Canvas.h"
#include "Util.h"
#include "Time.h"
#include <cmath>
#include <algorithm>
#include <sstream>

namespace {
TTF_Font* g_font = nullptr;
constexpr int kOutlineThickness = 1; // matches InteractionDisplay.outline_thickness

// was: keys_to_characters = {pygame.K_e: "E"}
const std::unordered_map<SDL_Keycode, std::string> kKeysToCharacters = {
    { SDLK_e, "E" },
};

// Deterministic string key for the cache, standing in for Python's use of
// the raw `display` tuple as a dict key (tuples hash by value in Python).
std::string specCacheKey(const DisplaySpec& display) {
    std::ostringstream oss;
    for (auto& seg : display) {
        if (seg.isKey) oss << "K:" << seg.key << "|";
        else oss << "S:" << seg.text << "|";
    }
    return oss.str();
}
} // namespace

void InteractionDisplay::init(SDL_Renderer* /*renderer*/, const std::string& fontPath, int fontSize) {
    if (TTF_WasInit() == 0) TTF_Init();
    if (g_font) TTF_CloseFont(g_font);
    g_font = TTF_OpenFont(fontPath.c_str(), fontSize);
    if (!g_font) {
        SDL_Log("[InteractionDisplay] failed to load font '%s': %s", fontPath.c_str(), TTF_GetError());
    }
}

std::shared_ptr<InteractionDisplay::CachedDisplayData>
InteractionDisplay::getOrBuildCache(SDL_Renderer* renderer, const DisplaySpec& display) {
    static std::unordered_map<std::string, std::shared_ptr<CachedDisplayData>> cache;

    std::string key = specCacheKey(display);
    auto it = cache.find(key);
    if (it != cache.end()) return it->second;

    auto data = std::make_shared<CachedDisplayData>();

    struct BuiltSeg {
        SDL_Texture* white = nullptr;
        SDL_Texture* black = nullptr;
        int w = 0, h = 0;
        double xOffset = 0.0; // cumulative width BEFORE this segment, matches Python's segment[2]
    };
    std::vector<BuiltSeg> segs;
    double cursorX = 0.0;
    int firstH = 0;

    for (auto& segment : display) {
        std::string renderText;
        if (segment.isKey) {
            auto charIt = kKeysToCharacters.find(segment.key);
            // FLAGGED: unmapped key falls back to "?" -- keys_to_characters
            // only defines K_e -> "E" today; if a new key-driven prompt is
            // added later without a mapping entry, this silently shows "?"
            // rather than crashing. Worth revisiting if that happens.
            std::string character = (charIt != kKeysToCharacters.end()) ? charIt->second : "?";
            renderText = "  " + character + "  ";
        } else {
            renderText = segment.text;
        }
        if (renderText.empty()) renderText = " "; // TTF_Render* on an empty string returns null

        SDL_Surface* whiteSurf = TTF_RenderUTF8_Blended(g_font, renderText.c_str(), SDL_Color{255, 255, 255, 255});
        SDL_Surface* blackSurf = TTF_RenderUTF8_Blended(g_font, renderText.c_str(), SDL_Color{0, 0, 0, 255});
        if (!whiteSurf || !blackSurf) {
            SDL_Log("[InteractionDisplay] text render failed: %s", TTF_GetError());
            continue;
        }

        BuiltSeg s;
        s.w = whiteSurf->w;
        s.h = whiteSurf->h;
        s.xOffset = cursorX;
        s.white = SDL_CreateTextureFromSurface(renderer, whiteSurf);
        s.black = SDL_CreateTextureFromSurface(renderer, blackSurf);
        SDL_FreeSurface(whiteSurf);
        SDL_FreeSurface(blackSurf);

        if (segs.empty()) firstH = s.h; // was: self.h = segments[0][0].get_height() + ... (first segment only, preserved)

        double segWidth = s.w + 2.0 * kOutlineThickness;
        if (segment.isKey) {
            data->circleX[segment.key] = cursorX + segWidth / 2.0;
        }

        segs.push_back(s);
        cursorX += segWidth;
    }

    data->w = cursorX;
    data->h = firstH + 2.0 * kOutlineThickness;

    int texW = std::max(1, static_cast<int>(std::ceil(data->w)));
    int texH = std::max(1, static_cast<int>(std::ceil(data->h)));

    data->text = RenderTarget(renderer, texW, texH);
    data->text.renderTo(renderer, [&] {
        data->text.clear({0, 0, 0, 0});

        static const std::vector<std::pair<int, int>> kOutlineOffsets = {
            {0, kOutlineThickness}, {kOutlineThickness, 0}, {0, -kOutlineThickness}, {-kOutlineThickness, 0}
        };
        for (auto& s : segs) {
            for (auto& off : kOutlineOffsets) {
                Canvas::blit(renderer, s.black,
                             kOutlineThickness + off.first + s.xOffset,
                             kOutlineThickness + off.second);
            }
            Canvas::blit(renderer, s.white, kOutlineThickness + s.xOffset, kOutlineThickness);
        }

        // Static outline-ring decoration for each key-indicator circle,
        // baked into the cached text (the dynamic filled circle showing
        // key-hold progress is drawn separately, per-frame -- see draw()).
        for (auto& kv : data->circleX) {
            double cx = kv.second;
            double cy = data->h / 2.0;
            double r = data->h / 2.0 - kOutlineThickness;
            Canvas::circle(renderer, {cx, cy}, r + 2 * kOutlineThickness, {0, 0, 0, 255}, 4 * kOutlineThickness);
            Canvas::circle(renderer, {cx, cy}, r + kOutlineThickness, {255, 255, 255, 255}, 2 * kOutlineThickness);
        }
    });

    for (auto& s : segs) {
        SDL_DestroyTexture(s.white);
        SDL_DestroyTexture(s.black);
    }

    // Shared per-spec scratch buffer -- see class-level note on why this
    // is safe (sequential draws within a frame fully consume it before
    // the next same-spec instance touches it again).
    data->scratch = RenderTarget(renderer, texW, texH);

    cache[key] = data;
    return data;
}

InteractionDisplay::InteractionDisplay(SDL_Renderer* renderer, Vec2 coords, const DisplaySpec& display,
                                        Color color, Anchor anchor, bool screenSpace)
    : x_(coords.x), y_(coords.y), color_(color), anchor_(anchor), screenSpace_(screenSpace) {
    cached_ = getOrBuildCache(renderer, display);
    for (auto& seg : display) {
        if (seg.isKey) circleAlpha_[seg.key] = 0.0;
    }
}

void InteractionDisplay::updateCoordinates(Vec2 coords) {
    x_ = coords.x;
    y_ = coords.y;
}

void InteractionDisplay::tick(double frameLength, bool primary, const std::unordered_map<SDL_Keycode, bool>& keysDown) {
    if (primary) {
        active = true;
        for (auto& kv : circleAlpha_) {
            SDL_Keycode k = kv.first;
            double& alpha = kv.second;
            auto it = keysDown.find(k);
            bool down = (it != keysDown.end()) && it->second;
            if (down) {
                if (keyReleased_) {
                    alpha = 255.0;
                    opacity_ = std::max(160.0, opacity_);
                } else {
                    active = false;
                }
            } else {
                alpha = std::max(alpha - frameLength, 0.0);
                active = false;
                keyReleased_ = true;
            }
        }
        opacity_ = std::min(opacity_ + frameLength / 5.0, active ? 255.0 : 160.0);
        postActive = active;
    } else {
        opacity_ = std::max(opacity_ - frameLength / 3.0, 0.0);
        active = false;
        keyReleased_ = false;
    }

    if (postActive) rise_ += (0.8 - rise_) * frameLength / 100.0;
    else             rise_ += (0.0 - rise_) * frameLength / 300.0;
}

bool InteractionDisplay::draw(SDL_Renderer* renderer, const Frame& frame, int64_t timeMs) {
    if (opacity_ <= 0) return false;

    double x = 0, y = 0;
    if (screenSpace_) {
        x = x_ + frame.offsetX;
        y = y_ + frame.offsetY;
    } else {
        Vec2 screen = frame.worldToScreen(x_, y_);
        x = screen.x;
        y = screen.y;
        double time = (timeMs < 0) ? static_cast<double>(Time::nowMs()) : static_cast<double>(timeMs);
        y += (std::sin(time / 500.0) / 8.0 - rise_) * cached_->h;
    }

    cached_->scratch.renderTo(renderer, [&] {
        cached_->scratch.clear({0, 0, 0, 0});
        for (auto& kv : circleAlpha_) {
            double alpha = kv.second;
            if (alpha <= 0) continue;
            double cx = cached_->circleX[kv.first];
            double cy = cached_->h / 2.0;
            double r = cached_->h / 2.0 - kOutlineThickness;
            Canvas::circle(renderer, {cx, cy}, r, {255, 255, 255, static_cast<uint8_t>(std::clamp(alpha, 0.0, 255.0))});
        }
        Canvas::blit(renderer, cached_->text.texture(), 0, 0);
        Canvas::multiplyTint(renderer, Rect{0, 0, static_cast<int>(cached_->w), static_cast<int>(cached_->h)}, color_);
    });

    cached_->scratch.setAlpha(static_cast<uint8_t>(std::clamp(opacity_, 0.0, 255.0)));

    // Now draws for every Anchor + screenSpace combination -- this is the
    // deliberate behavior change flagged in the header: the old Python had
    // no branch at all for align=="screen", so a screen-space display
    // computed a position but never actually blitted anything. Splitting
    // anchor from coordinate-space removes that gap entirely rather than
    // preserving it.
    Vec2 offset = anchorOffset(anchor_, cached_->w, cached_->h);
    Canvas::blit(renderer, cached_->scratch.texture(), x + offset.x, y + offset.y);
    return true;
}

// --- InteractionDisplayManager -----------------------------------------

void InteractionDisplayManager::tick(double frameLength, const std::unordered_map<SDL_Keycode, bool>& keysDown) {
    InteractionDisplay* activeDisplay = inRangeDisplays_.empty() ? nullptr : inRangeDisplays_.back();
    for (auto* display : onScreenDisplays_) {
        display->tick(frameLength, display == activeDisplay, keysDown);
    }
}

void InteractionDisplayManager::draw(SDL_Renderer* renderer, const Frame& frame, int64_t timeMs) {
    for (int i = static_cast<int>(onScreenDisplays_.size()) - 1; i >= 0; --i) {
        InteractionDisplay* display = onScreenDisplays_[i];
        bool stillDrawn = display->draw(renderer, frame, timeMs);
        bool inRange = std::find(inRangeDisplays_.begin(), inRangeDisplays_.end(), display) != inRangeDisplays_.end();
        if (!(stillDrawn || inRange)) {
            onScreenDisplays_.erase(onScreenDisplays_.begin() + i);
        }
    }
}

void InteractionDisplayManager::displayInRange(InteractionDisplay* display) {
    Util::safeAppend(inRangeDisplays_, display);
    Util::safeAppend(onScreenDisplays_, display);
}

void InteractionDisplayManager::displayOutRange(InteractionDisplay* display, bool complete) {
    Util::safeRemove(inRangeDisplays_, display);
    if (!complete) display->postActive = false;
}
