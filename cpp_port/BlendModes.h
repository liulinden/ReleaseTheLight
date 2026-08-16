#pragma once
#include <SDL.h>

// Matches pygame's special_flags= blend constants, composed once via
// SDL_ComposeCustomBlendMode (cheap to reuse, non-trivial to recompute
// per-draw-call) and run through an accelerated SDL_Renderer -- this is
// the GPU-backed replacement for pygame's blend flags, per the earlier
// architecture decision.
namespace BlendModes {

// pygame.BLEND_RGB_MULT: dst.rgb = dst.rgb * src.rgb, alpha untouched
SDL_BlendMode rgbMult();

// pygame.BLEND_RGBA_MULT: dst.rgba = dst.rgba * src.rgba (alpha included)
SDL_BlendMode rgbaMult();

// pygame.BLEND_RGB_ADD: dst.rgb = dst.rgb + src.rgb (clamped), alpha untouched
SDL_BlendMode rgbAdd();

// pygame.BLEND_ADD: dst.rgba = dst.rgba + src.rgba (clamped), alpha included.
// FLAGGED: pygame's plain BLEND_ADD (used in lighting.py for mist particles
// and gradients) predates the RGB_ADD/RGBA_ADD split; I'm treating it as
// full-channel add here. Worth a visual sanity check once we're actually
// rendering these effects, in case pygame's legacy behavior differs subtly.
SDL_BlendMode add();

// pygame.BLEND_RGBA_SUB: dst.rgba = dst.rgba - src.rgba (clamped to 0)
SDL_BlendMode rgbaSub();

// pygame.BLEND_RGBA_MAX: dst.rgba = max(dst.rgba, src.rgba) componentwise
SDL_BlendMode rgbaMax();

// pygame.BLEND_RGB_MAX: dst.rgb = max(dst.rgb, src.rgb), alpha untouched
SDL_BlendMode rgbMax();

} // namespace BlendModes
