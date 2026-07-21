import multiprocessing

import pygame

import config as config
from scripts.loading_screen import LoadingScreen, UserQuitDuringLoadingError
from releaseTheLight import Game


def main():

    # loading_screen = LoadingScreen(developer_mode=development_mode, is_dummy=True)
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
        game.set_window(pygame.display.set_mode((0, 0)))
        game.run()

    pygame.quit()


if __name__ == "__main__":
    main()
