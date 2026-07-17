import multiprocessing

import pygame

import config
from loading_screen import LoadingScreen, UserQuitDuringLoadingException
from releaseTheLight import Game


def main():

    # loading_screen = LoadingScreen(developer_mode=development_mode, is_dummy=True)
    loading_screen = LoadingScreen(dev_mode=config.DEV_MODE)
    loading_process = multiprocessing.Process(target=loading_screen.run, daemon=True)
    loading_process.start()

    pygame.init()

    pygame.display.set_caption(config.WINDOW_NAME)
    pygame.display.set_icon(pygame.image.load(config.WINDOW_ICON_PATH))

    game = Game(pygame.display.set_mode((0, 0), pygame.HIDDEN), FPS=100, full_world=False, loading_screen=loading_screen, dev_mode=config.DEV_MODE)

    try:
        game.setup()
    except UserQuitDuringLoadingException:
        pass

    loading_process.join()
    loading_process.close()

    if not loading_screen.is_quit():
        game.set_window(pygame.display.set_mode((0, 0)))
        game.run()

    pygame.quit()


if __name__ == "__main__":
    main()
