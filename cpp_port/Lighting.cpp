#include "Lighting.h"
#include "Canvas.h"
#include "BlendModes.h"
#include "GlobalAssets.h"
#include "Util.h"
#include <cmath>
#include <algorithm>
#include <string>

namespace {
// def snap_color(color, snap=4):
//     return (color[0]//snap*snap, color[1]//snap*snap, color[2]//snap*snap)
Color snapColor(Color c, int snap = 4) {
    return {
        static_cast<uint8_t>(c.r / snap * snap),
        static_cast<uint8_t>(c.g / snap * snap),
        static_cast<uint8_t>(c.b / snap * snap),
        255
    };
}
} // namespace

size_t Lighting::TintKeyHash::operator()(const TintKey& k) const {
    size_t h = std::hash<const void*>()(k.source);
    auto mix = [&](size_t v) { h ^= v + 0x9e3779b9 + (h << 6) + (h >> 2); };
    mix(std::hash<int>()(k.r));
    mix(std::hash<int>()(k.g));
    mix(std::hash<int>()(k.b));
    return h;
}

// was: def init(): loads particles_mist_1..5, gradient_light, gradient_thick
// after the display exists. In our version there's no per-zoom pre-scaling
// to do, so this just validates the assets exist, failing fast at startup
// (matching when the Python's init() would have raised) rather than
// lazily on first draw.
void Lighting::init(SDL_Renderer* /*renderer*/) {
    for (int i = 1; i <= 5; ++i) GlobalAssets::getAsset("particles_mist_" + std::to_string(i));
    GlobalAssets::getAsset("gradient_light");
    GlobalAssets::getAsset("gradient_thick");
}

Lighting::Lighting() {}

// def add_mist_particle(self, x, y, color=(255,255,255)):
//     mist_list = self.resized_light_im_gs["particles_mist"]
//     new_particle = MistParticle(x, y, mist_list[random.randint(0, len(mist_list)-1)], color)
// NOTE: the Python's mist_list has 5 images x 3 base sizes = 15 entries,
// each particle randomly (and permanently, at spawn) picking one
// (image, size) pair. Replicated here as two independent random picks --
// image index [0,4] and base size from {110,130,150} -- rather than a
// single random pick over a flattened 15-entry list, which is behaviorally
// identical (uniform over the same 15 combinations) but avoids needing to
// materialize that list.
void Lighting::addMistParticle(double x, double y, Color color) {
    int imageIndex = Util::randint(0, 4);
    static const std::array<double, 3> kBaseSizes = {110.0, 130.0, 150.0};
    double baseSize = kBaseSizes[Util::randint(0, 2)];
    particles_.emplace_back(x, y, imageIndex, baseSize, color);
}

// def tick_effects(self, frame_length):
//     for i in range(len(self.particles)-1,-1,-1):
//         if self.particles[i].tick(frame_length) == "end": del self.particles[i]
void Lighting::tickEffects(double frameLength) {
    particles_.erase(
        std::remove_if(particles_.begin(), particles_.end(),
                        [&](MistParticle& p) { return p.tick(frameLength); }),
        particles_.end());
}

RenderTarget& Lighting::getTinted(SDL_Renderer* renderer, SDL_Texture* source, int srcW, int srcH,
                                   Color color, double darken) {
    Color snapped = snapColor(color);
    TintKey key{ source, snapped.r, snapped.g, snapped.b };

    if (RenderTarget* existing = tintCache_.get(key)) {
        return *existing;
    }

    RenderTarget tinted(renderer, srcW, srcH);
    Color darkTint{
        static_cast<uint8_t>(snapped.r * darken),
        static_cast<uint8_t>(snapped.g * darken),
        static_cast<uint8_t>(snapped.b * darken),
        255
    };
    tinted.renderTo(renderer, [&] {
        tinted.clear({0, 0, 0, 0});
        Canvas::rectFilled(renderer, Rect{0, 0, srcW, srcH}, darkTint);
        Canvas::blit(renderer, source, 0, 0, BlendModes::rgbaMult());
    });

    return tintCache_.insert(key, std::move(tinted));
}

// def draw_gradient(self, surface, frame, color, x, y, size=400, offset_x=0, offset_y=0):
//     darken = 60/255
//     premul = GradientCache.get_premul(img_lookup, zoom, color, darken)
//     surface.blit(premul, (...), special_flags=pygame.BLEND_ADD)
void Lighting::drawGradient(SDL_Renderer* renderer, const Frame& frame, Color color, double x, double y,
                             double size, int offsetX, int offsetY) {
    const Asset& gradient = GlobalAssets::getAsset("gradient_light");
    double destSize = size * frame.zoom;
    double darken = 60.0 / 255.0;

    RenderTarget& tinted = getTinted(renderer, gradient.texture, gradient.width, gradient.height, color, darken);
    tinted.setAlpha(255); // gradient's own alpha channel provides the falloff; no per-call fade here

    Vec2 pos = frame.worldToScreen(x, y);
    Canvas::blit(renderer, tinted.texture(),
                 pos.x - destSize / 2.0 + offsetX, pos.y - destSize / 2.0 + offsetY,
                 destSize, destSize, BlendModes::rgbAdd());
}

// def draw_thick_gradient(self, surface, frame, x, y, offset_x=0, offset_y=0):
//     img = self.resized_light_im_gs["gradient_thick"][zoom]
//     surface.blit(img, (...))  # plain blit, no tint, no special blend flag
void Lighting::drawThickGradient(SDL_Renderer* renderer, const Frame& frame, double x, double y,
                                  int offsetX, int offsetY) {
    const Asset& thick = GlobalAssets::getAsset("gradient_thick");
    double destSize = 300.0 * frame.zoom;
    Vec2 pos = frame.worldToScreen(x, y);
    Canvas::blit(renderer, thick.texture,
                 pos.x - destSize / 2.0 + offsetX, pos.y - destSize / 2.0 + offsetY,
                 destSize, destSize);
}

void Lighting::drawEffects(SDL_Renderer* renderer, const Frame& frame) {
    for (auto& p : particles_) p.draw(renderer, frame, *this);
}

// --- MistParticle ------------------------------------------------------

MistParticle::MistParticle(double x, double y, int mistImageIndex, double baseSize, Color color)
    : color_(color), mistImageIndex_(mistImageIndex), baseSize_(baseSize) {
    xSpeed_ = (Util::randomDouble() - 0.5) / 12.0;
    ySpeed_ = (Util::randomDouble() - 0.5) / 12.0;
    lifeTime_ = 500.0;
    x_ = x + Util::randint(-50, 50);
    y_ = y + Util::randint(-50, 50);
    brightness_ = (Util::randomDouble() + 0.2) * 2.0;
    fadeIn_ = 0.0;
}

// def tick(self, frame_length):
//     self.life_time -= frame_length/3
//     if self.life_time < 0: return "end"
//     self.x += self.x_speed*frame_length
//     self.y += self.y_speed*frame_length
//     self.y_speed -= frame_length*0.00001*frame_length/60
//     self.x_speed *= 0.99994**frame_length
//     self.y_speed *= 0.99994**frame_length
//     if self.fade_in < 1: self.fade_in += 0.02*frame_length/16
bool MistParticle::tick(double frameLength) {
    lifeTime_ -= frameLength / 3.0;
    if (lifeTime_ < 0) return true;
    x_ += xSpeed_ * frameLength;
    y_ += ySpeed_ * frameLength;
    ySpeed_ -= frameLength * 0.00001 * frameLength / 60.0;
    xSpeed_ *= std::pow(0.99994, frameLength);
    ySpeed_ *= std::pow(0.99994, frameLength);
    if (fadeIn_ < 1.0) fadeIn_ += 0.02 * frameLength / 16.0;
    return false;
}

// def draw(self, surface, frame, offset_x=0, offset_y=0):
//     alpha = max(0, min(255, int(self.life_time/4*self.brightness*self.fade_in)))
//     premul = MistParticleCache.get_premul(self.base_imgs, self.color, zoom, alpha)
//     surface.blit(premul, (...), special_flags=pygame.BLEND_ADD)
void MistParticle::draw(SDL_Renderer* renderer, const Frame& frame, Lighting& owner) {
    const Asset& asset = GlobalAssets::getAsset("particles_mist_" + std::to_string(mistImageIndex_ + 1));
    double destSize = baseSize_ * frame.zoom;

    RenderTarget& tinted = owner.getTinted(renderer, asset.texture, asset.width, asset.height, color_, 1.0);

    int alpha = static_cast<int>(std::max(0.0, std::min(255.0, lifeTime_ / 4.0 * brightness_ * fadeIn_)));
    tinted.setAlpha(static_cast<uint8_t>(alpha));

    Vec2 pos = frame.worldToScreen(x_, y_);
    Canvas::blit(renderer, tinted.texture(),
                 pos.x - destSize / 2.0, pos.y - destSize / 2.0,
                 destSize, destSize, BlendModes::rgbAdd());
}
