#include "Particles.h"
#include "Canvas.h"
#include "Util.h"
#include <cmath>
#include <algorithm>

// --- MiningParticle ------------------------------------------------------

// def __init__(self, color, size, x, y, x_speed=0, y_speed=0, time=500):
//     self.size = random.randint(1, 3) * size / 20
MiningParticle::MiningParticle(Color color, double size, double x, double y,
                                double xSpeed, double ySpeed, double time)
    : color_(color), x_(x), y_(y), xSpeed_(xSpeed), ySpeed_(ySpeed), lifeTime_(time) {
    size_ = Util::randint(1, 3) * size / 20.0;
}

// def tick(self, frame_length):
//     self.y_speed += 0.0012 * frame_length
//     self.x += self.x_speed * frame_length
//     self.y += self.y_speed * frame_length
//     self.timer -= frame_length
//     return self.timer <= 0
bool MiningParticle::tick(double frameLength) {
    ySpeed_ += 0.0012 * frameLength;
    x_ += xSpeed_ * frameLength;
    y_ += ySpeed_ * frameLength;
    lifeTime_ -= frameLength;
    return lifeTime_ <= 0;
}

// def draw(self, surface, frame, offset_x=0, offset_y=0):
//     pygame.draw.circle(surface, self.color, (...), self.size * zoom)
void MiningParticle::draw(SDL_Renderer* renderer, const Frame& frame) {
    Vec2 pos = frame.worldToScreen(x_, y_);
    Canvas::circle(renderer, pos, size_ * frame.zoom, color_);
}

// --- PulseParticle ---------------------------------------------------------

// def __init__(self, color, size, x, y, time=0):
//     self.timer = time if time != 0 else size * 20
//     ...
//     if self.timer == 0: self.timer = size * 10
// NOTE: preserved exactly, including the apparently-dead second
// `if self.timer == 0` check -- by the time it runs, self.timer has
// already been set to either the caller's `time` or `size * 20`, so it
// can only still be 0 there if BOTH time==0 AND size==0. Not "fixed";
// just flagged as likely-vestigial.
PulseParticle::PulseParticle(Color color, double size, double x, double y, double time)
    : color_(color), x_(x), y_(y), size_(size) {
    timer_ = (time != 0) ? time : size * 20.0;
    opacity_ = 150.0;
    if (timer_ == 0) timer_ = size * 10.0;
}

// def tick(self, frame_length):
//     self.timer -= frame_length
//     factor = self.timer / (self.timer + frame_length)
//     self.size *= factor
//     self.opacity *= factor
//     return self.timer <= 5
bool PulseParticle::tick(double frameLength) {
    timer_ -= frameLength;
    double factor = timer_ / (timer_ + frameLength); // note: denominator == pre-decrement timer_
    size_ *= factor;
    opacity_ *= factor; // computed, but never read -- see draw()
    return timer_ <= 5;
}

// def draw(self, surface, frame, offset_x=0, offset_y=0):
//     pygame.draw.circle(surface, (r,g,b,100), (...), self.size*zoom, 2)
// FLAGGED: alpha is hardcoded to 100 here, NOT self.opacity (which tick()
// computes every frame but this never reads). Preserved exactly -- the
// opacity fade the code appears to implement has no actual visual effect.
void PulseParticle::draw(SDL_Renderer* renderer, const Frame& frame) {
    Vec2 pos = frame.worldToScreen(x_, y_);
    Color drawColor{ color_.r, color_.g, color_.b, 100 };
    Canvas::circle(renderer, pos, size_ * frame.zoom, drawColor, 2);
}

// --- Particles -------------------------------------------------------------

// def spawn_mining_particles(self, n, color, size, x, y, time=500):
//     for i in range(n):
//         angle = -random.random() * 2 * math.pi
//         scale = (random.random() + 1) / 10
//         self.particles.append(MiningParticle(color, size, x, y, cos(angle)*scale, sin(angle)*scale - 0.05, time=time))
void Particles::spawnMiningParticles(int n, Color color, double size, double x, double y, double time) {
    for (int i = 0; i < n; ++i) {
        double angle = -Util::randomDouble() * 2 * M_PI;
        double scale = (Util::randomDouble() + 1) / 10.0;
        particles_.emplace_back(color, size, x, y,
                                 std::cos(angle) * scale, std::sin(angle) * scale - 0.05, time);
    }
}

void Particles::spawnPulseParticle(Color color, double size, double x, double y, double time) {
    pulseParticles_.emplace_back(color, size, x, y, time);
}

// def tick_particles(self, frame_length):
//     for particle_set in [self.pulse_particles, self.particles]:
//         for i in range(len(particle_set)-1, -1, -1):
//             if particle_set[i].tick(frame_length): particle_set.remove(particle_set[i])
void Particles::tickParticles(double frameLength) {
    pulseParticles_.erase(
        std::remove_if(pulseParticles_.begin(), pulseParticles_.end(),
                        [&](PulseParticle& p) { return p.tick(frameLength); }),
        pulseParticles_.end());
    particles_.erase(
        std::remove_if(particles_.begin(), particles_.end(),
                        [&](MiningParticle& p) { return p.tick(frameLength); }),
        particles_.end());
}

void Particles::drawParticles(SDL_Renderer* renderer, const Frame& frame) {
    for (auto& p : particles_) p.draw(renderer, frame);
}

// def draw_pulse_particles(self, surface, frame, offset_x=0, offset_y=0):
//     self.update_scratch_layer(surface.get_size())
//     self.scratch_layer.fill((0,0,0,0))
//     for particle in self.pulse_particles: particle.draw(self.scratch_layer, frame, offset_x, offset_y)
//     surface.blit(self.scratch_layer, (0,0))
void Particles::drawPulseParticles(SDL_Renderer* renderer, const Frame& frame) {
    if (scratchW_ != frame.screenWidth || scratchH_ != frame.screenHeight) {
        scratchLayer_ = RenderTarget(renderer, frame.screenWidth, frame.screenHeight);
        scratchW_ = frame.screenWidth;
        scratchH_ = frame.screenHeight;
    }
    scratchLayer_.renderTo(renderer, [&] {
        scratchLayer_.clear({0, 0, 0, 0});
        for (auto& p : pulseParticles_) p.draw(renderer, frame);
    });
    Canvas::blit(renderer, scratchLayer_.texture(), 0, 0);
}
