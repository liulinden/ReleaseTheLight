#pragma once
#include "Core.h"

// Consolidates the pattern repeated across nearly every draw/tick function
// in the Python source:
//   frame = [cam_x, cam_y, zoom]                 (or left, top, zoom = frame)
//   window_size = (window_width, window_height)  (logical viewport size --
//                                                  shrinks in loading-debug mode)
//   real_window_size                             (actual full render target
//                                                  size; defaults to window_size
//                                                  when not separately given)
//   offset_x, offset_y                           (screen-space letterbox
//                                                  offset when window_size <
//                                                  real_window_size)
//
// These four pieces of data always travel together through the draw call
// chain (Game -> World -> Terrain/Player/Enemy/Nest/Cell/Lighting/Laser),
// so we pass one Frame by const-ref instead of 3-6 separate parameters.
struct Frame {
    // World-space top-left corner of the camera view (was: left, top / cam_x, cam_y)
    double left = 0.0;
    double top = 0.0;
    double zoom = 1.0;

    // Logical viewport size in screen pixels (was: window_size). Note this
    // is divided into to get world-space extents (e.g. Terrain uses
    // window_size[0] / zoom), so it must stay separate from screenWidth/
    // screenHeight below even though they're usually equal.
    int viewWidth = 0;
    int viewHeight = 0;

    // Actual render target size (was: real_window_size). Defaults to the
    // viewport size when the two aren't distinguished by the caller --
    // callers that pass real_window_size=None in Python get this behavior
    // implicitly; we replicate that by just setting both fields equal at
    // construction unless told otherwise.
    int screenWidth = 0;
    int screenHeight = 0;

    // Screen-space letterbox offset (was: offset_x, offset_y). Zero except
    // during the loading-debug (K_l) view in Game, which shrinks viewWidth/
    // viewHeight to simulate a smaller screen while screenWidth/screenHeight
    // stay at the real window size -- lets you visually confirm chunk
    // streaming loads/evicts correctly relative to a viewport smaller than
    // what's actually being rendered.
    int offsetX = 0;
    int offsetY = 0;

    // world -> screen, matching the extremely common
    //   (x - left) * zoom + offset_x, (y - top) * zoom + offset_y
    // pattern seen at dozens of call sites (Cell::draw, Enemy::draw,
    // Nest::draw, Lighting::draw_gradient, Laser::draw, etc.)
    Vec2 worldToScreen(double worldX, double worldY) const {
        return {
            (worldX - left) * zoom + offsetX,
            (worldY - top) * zoom + offsetY
        };
    }
    Vec2 worldToScreen(Vec2 worldPos) const {
        return worldToScreen(worldPos.x, worldPos.y);
    }

    // screen -> world, matching Game.coords_window_to_world:
    //   self.cam_x + (coords[0] - self.offset_x) / self.zoom,
    //   self.cam_y + (coords[1] - self.offset_y) / self.zoom
    Vec2 screenToWorld(double screenX, double screenY) const {
        return {
            left + (screenX - offsetX) / zoom,
            top + (screenY - offsetY) / zoom
        };
    }

    // World-space width/height currently visible through the viewport,
    // matching the frequent `width, height = window_size[0]/zoom,
    // window_size[1]/zoom` pattern (Terrain::draw_terrain,
    // World::tick's screen_rect, etc.)
    double visibleWorldWidth()  const { return viewWidth  / zoom; }
    double visibleWorldHeight() const { return viewHeight / zoom; }
};
