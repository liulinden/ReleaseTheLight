import multiprocessing

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

    game = Game(pygame.display.set_mode((0, 0), pygame.HIDDEN), fps=100, full_world=False, loading_screen=loading_screen, dev_mode=config.DEV_MODE)

    did_user_quit_during_loading = False

    try:
        game.setup()
    except UserQuitDuringLoadingError:
        did_user_quit_during_loading = True

    loading_process.join()
    loading_process.close()

    if not did_user_quit_during_loading:
        # OPENGL|DOUBLEBUF: the real game window (unlike the HIDDEN one
        # above, which is never drawn to) gets presented via gl_present
        # instead of a plain pygame.display.flip() -- see gl_present.py and
        # Game.render_surface. Once this flag is set, the Surface set_mode
        # returns can no longer be blitted onto directly, which is why
        # everything now draws onto Game.render_surface instead.
        window = pygame.display.set_mode((0, 0), pygame.OPENGL | pygame.DOUBLEBUF)
        gl_present.init()
        # needs real asset data (game.setup(), above, already loaded it) and
        # _ctx (gl_present.init(), just above) -- uploads foreground/
        # gradient_thick once as persistent GPU textures instead of every frame
        gl_present.load_static_textures()
        game.set_window(window)
        game.run()

    pygame.quit()


if __name__ == "__main__":
    main()
