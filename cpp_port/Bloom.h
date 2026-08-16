#pragma once
#include <SDL.h>
#include "RenderTarget.h"

// Ported from bloom.py's get_bloom().
//
// The numpy-based per-pixel threshold step is unavoidable without writing
// real GPU shaders (a bigger architecture change intentionally deferred --
// bloom was already flagged as the top performance item to revisit with a
// shader-based rewrite once the base port is working and profiled, per
// the original roadmap discussion). This version keeps the same overall
// structure as the Python: downsample FIRST (so the CPU threshold work
// happens on a small image, matching the Python's own stated optimization
// rationale), threshold via a raw pixel buffer readback/rewrite (replacing
// numpy), then do the shrink/grow blur passes and final upscale/composite
// entirely on the GPU via texture scaling -- cheap, unlike the Python
// where even the blur passes were CPU-adjacent pygame.transform calls.
//
// Unlike the Python (module-level scratch_surfaces/scratch_second_surfaces
// dicts keyed by size, shared mutable global state), this is a class
// holding its own persistent scratch RenderTargets, resized on demand --
// same caching intent, no global state.
class Bloom {
public:
    // Returns a texture containing just the blurred bright regions, meant
    // to be additively blitted (BlendModes::rgbAdd()) onto the original
    // scene by the caller -- matches the Python's return-a-surface-for-
    // the-caller-to-blit contract.
    RenderTarget& getBloom(SDL_Renderer* renderer, SDL_Texture* source, int fullW, int fullH,
                            int threshold = 30, int downscale = 30, int blurPasses = 2,
                            double intensity = 0.8);

private:
    RenderTarget full_;   // was: scratch_surfaces[full_size] ("big")
    RenderTarget small_;  // was: scratch_surfaces[small_size]
    RenderTarget tiny_;   // was: scratch_surfaces[shrink_size]
    RenderTarget temp_;   // extra scratch for self-blit-avoidance (intensity>1 doubling) and dim pass
    int fullW_ = -1, fullH_ = -1;
    int smallW_ = -1, smallH_ = -1;
    int tinyW_ = -1, tinyH_ = -1;
    int tempW_ = -1, tempH_ = -1;
};
