#pragma once
#include "AssetManager.h"

// Ported from global_assets.py. The Python version is a module holding a
// single module-level `asset_manager` instance plus two free functions
// (load_assets, get_asset) -- Python modules are singletons by nature, so
// this translates most directly to a C++ singleton accessor rather than a
// global variable, avoiding static-initialization-order-fiasco risk with
// other globals elsewhere in the port (e.g. the enemy costume/size tables
// in _enemy_handling.py, which run at Python import time and will need
// their own explicit init step in C++ -- see that file's translation
// notes when we get there).
namespace GlobalAssets {

// Returns the single shared AssetManager instance ("assets" root,
// useCache=true, matching global_assets.py's `AssetManager("assets",
// use_cache=True)`). Constructed on first call (function-local static ->
// thread-safe init in C++11+, no separate init-order concern).
AssetManager& manager();

// def load_assets(loading_screen=None) -> None:
//     asset_manager.load(loading_screen=loading_screen)
// `renderer` param added since texture upload needs it (see AssetManager
// notes) -- the Python version didn't need this since pygame surfaces
// don't require an active renderer to create.
inline double loadAssets(SDL_Renderer* renderer, bool verbose = true) {
    return manager().load(renderer, verbose);
}

// def get_asset(name: str) -> pygame.Surface:
//     return asset_manager.get(name)
inline const Asset& getAsset(const std::string& name) {
    return manager().get(name);
}

} // namespace GlobalAssets
