import multiprocessing
import os

import pygame

import config as config
import scripts.gl_present as gl_present
from releaseTheLight import Game
from scripts.loading_screen import LoadingScreen, UserQuitDuringLoadingError


def main():

    # loading_screen = LoadingScreen(dev_mode=config.DEV_MODE, dummy_mode=True)
    loading_screen = LoadingScreen(dev_mode=config.DEV_MODE)
    loading_process = multiprocessing.Process(target=loading_screen.run, daemon=True)
    loading_process.start()

    pygame.init()

    pygame.display.set_caption(config.WINDOW_NAME)
    pygame.display.set_icon(pygame.image.load(config.WINDOW_ICON_PATH))

    info = pygame.display.Info()
    aspect_ratio = info.current_h / info.current_w
    # fixed resolution everything CPU-side (render_surface/ui_surface, and
    # therefore every blit draw_world does -- hundreds per frame) runs at,
    # regardless of the user's actual display resolution -- kept small on
    # purpose for cheap blitting. No pygame.SCALED here (see gl_present.py's
    # module docstring note on it being flagged experimental/unreliable when
    # combined with OPENGL) -- instead the real window below is created at
    # native resolution, and gl_present.py's existing fullscreen-quad GPU
    # composite upscales this logical_size result onto it for free, since a
    # texture sampled across a full-viewport quad stretches to fill
    # whatever viewport it's drawn into regardless of the texture's own size.
    resolution_w = 1500
    logical_size = (resolution_w, int(resolution_w * aspect_ratio))
    native_size = (info.current_w, info.current_h)
    # NOFRAME (a plain borderless window sized/positioned to cover the whole
    # screen) instead of pygame.FULLSCREEN -- real exclusive fullscreen
    # (SDL_WINDOW_FULLSCREEN) can trigger an actual OS display-mode
    # switch, which visibly disrupts every other window's position/size on
    # some systems (observed on Windows here). A borderless window is just
    # a normal window as far as the OS is concerned, so it can't do that,
    # while still looking identical (no border/titlebar, fills the screen).
    os.environ["SDL_VIDEO_WINDOW_POS"] = "0,0"
    flags = pygame.OPENGL | pygame.DOUBLEBUF | pygame.NOFRAME

    # placeholder GL-capable display mode so asset loading during
    # game.setup() (below) has a display to .convert()/.convert_alpha()
    # against -- its resolution is irrelevant, only the real window
    # (created after loading, further down) is ever actually shown
    pygame.display.set_mode(native_size, pygame.HIDDEN | flags)

    # Game only ever reads .get_size() off what's passed to set_window (see
    # Game.set_window) -- never blits onto it -- so a plain off-screen
    # Surface at logical_size is all it needs; the game never has to know
    # its rendered output ends up upscaled onto a differently-sized window
    game = Game(pygame.Surface(logical_size), fps=100, full_world=True, loading_screen=loading_screen, dev_mode=config.DEV_MODE)

    did_user_quit_during_loading = False

    try:
        game.setup()
    except UserQuitDuringLoadingError:
        did_user_quit_during_loading = True

    loading_process.join()
    loading_process.close()

    if not did_user_quit_during_loading:
        # OPENGL|DOUBLEBUF: this window gets presented via gl_present
        # instead of a plain pygame.display.flip() -- see gl_present.py and
        # Game.render_surface. Once this flag is set, the Surface set_mode
        # returns can no longer be blitted onto directly, which is why
        # everything now draws onto Game.render_surface instead.
        pygame.display.set_mode(native_size, flags)
        gl_present.init()
        # needs real asset data (game.setup(), above, already loaded it) and
        # _ctx (gl_present.init(), just above) -- uploads foreground/
        # gradient_thick once as persistent GPU textures instead of every frame
        gl_present.load_static_textures()
        game.run()

    pygame.quit()


if __name__ == "__main__":
    main()
