#pragma once
#include <vector>
#include <memory>
#include <SDL.h>
#include "Core.h"
#include "Frame.h"
#include "RenderTarget.h"

// was: class MiningParticle
class MiningParticle {
public:
    MiningParticle(Color color, double size, double x, double y,
                    double xSpeed = 0, double ySpeed = 0, double time = 500);

    // Returns true when finished (matches Python's `return "end"` sentinel,
    // simplified to a bool since nothing else ever checked the string
    // value beyond truthiness).
    bool tick(double frameLength);
    void draw(SDL_Renderer* renderer, const Frame& frame);

private:
    Color color_;
    double x_, y_;
    double xSpeed_, ySpeed_;
    double lifeTime_;
    double size_;
};

// was: class PulseParticle
class PulseParticle {
public:
    PulseParticle(Color color, double size, double x, double y, double time = 0);

    bool tick(double frameLength); // true when finished
    void draw(SDL_Renderer* renderer, const Frame& frame);

private:
    Color color_;
    double x_, y_;
    double timer_;
    double size_;
    double opacity_; // FLAGGED: tracked here, matching Python, but draw()
                      // never reads it -- see .cpp for details. Preserved
                      // as dead state, not removed, per project convention
                      // of not silently "fixing" quirks during translation.
};

// was: class Particles
class Particles {
public:
    // was: def spawn_mining_particles(self, n, color, size, x, y, time=500)
    void spawnMiningParticles(int n, Color color, double size, double x, double y, double time = 500);
    // was: def spawn_pulse_particle(self, color, size, x, y, time=600)
    void spawnPulseParticle(Color color, double size, double x, double y, double time = 600);

    // was: def tick_particles(self, frame_length)
    void tickParticles(double frameLength);

    // was: def draw_particles(self, surface, frame, offset_x=0, offset_y=0)
    // Renders onto whatever target is currently bound to `renderer`.
    void drawParticles(SDL_Renderer* renderer, const Frame& frame);

    // was: def draw_pulse_particles(self, surface, frame, offset_x=0, offset_y=0)
    // Composites pulse particles onto a scratch layer first, then blits
    // that onto whatever's bound to `renderer` -- matches the Python's
    // scratch_layer indirection (needed there to avoid particles
    // double-drawing over each other's alpha; kept for fidelity even
    // though the reason it existed in pygame's software blitting model
    // may not strictly apply on the GPU path).
    void drawPulseParticles(SDL_Renderer* renderer, const Frame& frame);

private:
    std::vector<MiningParticle> particles_;
    std::vector<PulseParticle> pulseParticles_;
    RenderTarget scratchLayer_;
    int scratchW_ = -1, scratchH_ = -1;
};
