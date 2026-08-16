#pragma once
#include <SDL.h>
#include "Core.h"
#include "Frame.h"
#include "Terrain.h"
#include "Player.h"
#include "Lighting.h"
#include "Bloom.h"
#include "RenderTarget.h"

// Ported from world.py.
//
// `default_zooms` dropped entirely from every signature here (was a
// Python constructor param threaded through to Terrain/Player/Lighting
// for per-zoom pre-scaling) -- GPU scales at draw time, per the
// established architecture decision, so nothing downstream needs it
// anymore.
//
// `World.add_air_pocket` (Python) is NOT ported: it calls
// `self.terrain._layer_for_y(...)` and passes a `layer_index` to
// Terrain.add_air_pocket -- both reference an older, layer-based Terrain
// design that doesn't match terrain.py as given to us (no layers exist
// anywhere in the Terrain we've ported), and nothing in the source we've
// seen actually calls World.add_air_pocket. This looks like dead code
// left over from a prior Terrain architecture; Terrain::addAirPocket is
// available directly for any real future use.
class World {
public:
    // was: def init() equivalent -- calls every module's init() in the
    // same order as Python's `inits` list (lighting, cells, enemies,
    // nest, terrain, player, laser, interaction_display, charge_display).
    // charge_display.init() is NOT called here since ChargeDisplay no
    // longer needs an init() step at all (see its header notes) --
    // nothing lost, just nothing to call.
    static void init(SDL_Renderer* renderer, const std::string& interactionFontPath);

    World(SDL_Renderer* renderer, int worldWidth, int worldHeight, bool developingMode = false);

    // was: def generate_world(self, loading_screen) -- loading_screen
    // progress reporting omitted (LoadingScreen's multithreading design
    // isn't wired up to this yet); can be added at the Game/main call
    // site later without changing World itself.
    void generateWorld();

    // was: def heal_nests(self)
    void healNests();
    // was: def remove_enemies(self)
    void removeEnemies();

    // was: def tick(self, fps, window_size, frame, mouse_pos, keys_down, events) -> bool
    // `window_size` dropped (redundant with Frame::viewWidth/viewHeight).
    // Returns true when the player died/respawned this tick (matches the
    // Python's signal for Game to reset camera).
    bool tick(double fps, const Frame& frame, Vec2 mousePos, const PlayerInput& input,
              const std::unordered_map<SDL_Keycode, bool>& keysDown);

    // was: def draw_background(self, layer, window_size, frame)
    void drawBackground(SDL_Renderer* renderer, const Frame& frame);
    // was: def draw_foreground(self, layer, window_size, frame)
    void drawForeground(SDL_Renderer* renderer, const Frame& frame);

    // was: def draw_world(self, window, window_size, frame, hitboxes=False,
    //                      kind_visibility=False, real_window_size=None,
    //                      offset_x=0, offset_y=0, tilt=0, crosshair=False)
    // Renders the composed frame onto whatever target is currently bound
    // to `renderer` (matches the rest of the port's convention) --
    // `window`/`real_window_size` dropped since Frame::screenWidth/Height
    // already carries that.
    void drawWorld(SDL_Renderer* renderer, const Frame& frame, bool hitboxes = false,
                    bool kindVisibility = false, double tilt = 0.0, bool crosshair = false);

    Terrain terrain;
    Player player;
    Lighting light;
    bool developingMode;

private:
    SDL_Renderer* renderer_;
    double foregroundAlpha_ = 0.0;
    Bloom bloom_;

    RenderTarget worldLayer_, scratchLayer_, finalLayer_;
    int layerW_ = -1, layerH_ = -1;
};
