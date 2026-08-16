#define SDL_MAIN_HANDLED

#include <SDL.h>
#include <SDL_image.h>
#include <SDL_ttf.h>
#include <iostream>
#include <string>
#include "Config.h"
#include "Game.h"
#include "LoadingScreen.h"

// Ported from main.py.
//
// No separate loading-screen process/thread: LoadingScreen is dummy-mode
// only in this port (progress printed to console -- see LoadingScreen.h
// for why), so there's no `.run()` window to launch on a background
// process at all. The multiprocessing.Process/join/close dance around it
// in the Python simply doesn't apply here.
int main(int /*argc*/, char** /*argv*/) {
    // was: loading_screen = LoadingScreen(dev_mode=config.DEV_MODE)
    LoadingScreen loadingScreen(0.0, 1.0, Config::DEV_MODE);

    if (SDL_Init(SDL_INIT_VIDEO) != 0) {
        std::cerr << "SDL_Init failed: " << SDL_GetError() << "\n";
        return 1;
    }
    if (!(IMG_Init(IMG_INIT_PNG) & IMG_INIT_PNG)) {
        std::cerr << "IMG_Init failed: " << IMG_GetError() << "\n";
        return 1;
    }
    if (TTF_Init() != 0) {
        std::cerr << "TTF_Init failed: " << TTF_GetError() << "\n";
        return 1;
    }

    SDL_Rect desktopBounds;
    SDL_GetDisplayBounds(0, &desktopBounds);

    // was: pygame.display.set_mode((0, 0), pygame.HIDDEN)
    SDL_Window* window = SDL_CreateWindow(
        Config::WINDOW_NAME.c_str(),
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        desktopBounds.w, desktopBounds.h,
        SDL_WINDOW_HIDDEN
    );
    if (!window) {
        std::cerr << "SDL_CreateWindow failed: " << SDL_GetError() << "\n";
        return 1;
    }

    // was: pygame.display.set_icon(pygame.image.load(config.WINDOW_ICON_PATH))
    SDL_Surface* icon = IMG_Load(Config::WINDOW_ICON_PATH.c_str());
    if (icon) {
        SDL_SetWindowIcon(window, icon);
        SDL_FreeSurface(icon);
    } else {
        std::cerr << "[main] failed to load window icon '" << Config::WINDOW_ICON_PATH << "': " << IMG_GetError() << "\n";
    }

    SDL_Renderer* renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_ACCELERATED);
    if (!renderer) {
        // Reasonable fallback, not just a testing convenience: not every
        // system has GPU acceleration available (or a real display driver
        // at all, e.g. some CI/headless setups) -- software rendering
        // still produces a correct result, just slower.
        std::cerr << "[main] accelerated renderer unavailable (" << SDL_GetError() << "), falling back to software\n";
        renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_SOFTWARE);
    }
    if (!renderer) {
        std::cerr << "SDL_CreateRenderer failed: " << SDL_GetError() << "\n";
        return 1;
    }

    // FONT PATH GAP (see Game.h's note): needs a real font file for both
    // the FPS counter and InteractionDisplay's "maiandragd" text, neither
    // of which has a confirmed path/fallback yet. Placeholder used here.
    std::string fontPath = "/mnt/skills/examples/canvas-design/canvas-fonts/BigShoulders-Regular.ttf";

    // `game` (and everything it owns -- World, Terrain, every RenderTarget
    // holding an SDL_Texture, Terrain's background thread) is scoped here
    // deliberately so it's fully destructed BEFORE SDL_Quit() runs below.
    // Local variables are only destroyed as a function actually returns,
    // so without this scope, `game`'s destructor chain would run AFTER
    // SDL_DestroyRenderer/SDL_Quit already tore down the SDL state its
    // RenderTargets' destructors need (SDL_DestroyTexture on textures
    // belonging to an already-quit SDL) -- undefined behavior, and the
    // likely cause of an observed hang-on-exit during testing.
    {
        // was: game = Game(pygame.display.set_mode((0,0), pygame.HIDDEN),
        //                   fps=100, full_world=False, loading_screen=loading_screen,
        //                   dev_mode=config.DEV_MODE)
        Game game(window, renderer, fontPath, 100, /*fullWorld=*/false, Config::DEV_MODE, &loadingScreen);

        bool didUserQuitDuringLoading = false;
        try {
            game.setup();
        } catch (const UserQuitDuringLoadingError&) {
            didUserQuitDuringLoading = true;
        }

        if (!didUserQuitDuringLoading) {
            // was: game.set_window(pygame.display.set_mode((0, 0))) --
            // re-creates the window non-hidden. SHOWING the existing hidden
            // window is the natural SDL equivalent (same visible end state
            // without an unnecessary destroy/recreate).
            SDL_ShowWindow(window);
            game.setWindow(window, renderer);
            game.run();
        }
    } // <-- game destructed here, while renderer/window/SDL are still valid

    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    TTF_Quit();
    IMG_Quit();
    SDL_Quit();

    return 0;
}
