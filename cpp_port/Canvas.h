#pragma once
#include <SDL.h>
#include <vector>
#include "Core.h"

// Replaces pygame.draw.circle / pygame.draw.line / pygame.draw.polygon.
// All functions render onto whatever target is currently bound to
// `renderer` (via SDL_SetRenderTarget) -- callers select the target
// beforehand, matching how the Python code passes a `surface` parameter
// explicitly to every draw call.
//
// Implemented via SDL_RenderGeometry (solid-color triangles, no texture)
// for filled shapes, which runs on the GPU through an accelerated
// renderer -- unlike pygame's software rasterization.
namespace Canvas {

// Filled circle (width=0, matches pygame.draw.circle default) or an
// outline ring of `width` pixels thickness (matches pygame's width= arg).
void circle(SDL_Renderer* renderer, Vec2 center, double radius, Color color, int width = 0);

// Thick line with flat caps (matches pygame.draw.line(..., width=)).
// No rounded caps here by design -- Util::drawRoundedLine adds those by
// combining this with circle(), mirroring util.py's draw_rounded_line
// exactly (a plain line plus two circles at the endpoints).
void line(SDL_Renderer* renderer, Vec2 start, Vec2 end, Color color, int thickness = 1);

// Filled polygon via triangle fan from the first vertex (matches
// pygame.draw.polygon's default filled behavior).
void polygon(SDL_Renderer* renderer, const std::vector<Vec2>& points, Color color);

// Polygon outline of `width` pixels (matches pygame.draw.polygon with a
// width> 0 argument, e.g. ChargeDisplay's diamond-indicator outline).
// Implemented as consecutive thick line segments around the loop,
// matching pygame's own unsmoothed-corner outline behavior.
void polygonOutline(SDL_Renderer* renderer, const std::vector<Vec2>& points, Color color, int width);

// Axis-aligned filled rect (matches pygame.draw.rect with width=0).
void rectFilled(SDL_Renderer* renderer, Rect r, Color color);

// Axis-aligned rect outline of `width` pixels (matches pygame.draw.rect
// with width>0).
void rectOutline(SDL_Renderer* renderer, Rect r, Color color, int width = 1);

// In-place multiply-tint of whatever's already drawn on the current
// render target within `region` -- matches pygame's
// `surface.fill(color, special_flags=BLEND_RGB_MULT)` idiom (multiplies
// EXISTING pixel content by `color`, alpha untouched). This is distinct
// from blit()-with-rgbMult(), which multiplies a *source texture* onto
// whatever's underneath -- this multiplies a flat color onto whatever's
// already there, no source texture involved.
void multiplyTint(SDL_Renderer* renderer, Rect region, Color color);

} // namespace Canvas
