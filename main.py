import multiprocessing
import pygame
from loading_screen import LoadingScreen, UserQuitDuringLoadingException
from releaseTheLight import Game

development_mode = True

def main():
    
    # loading_screen = LoadingScreen(developer_mode=development_mode, is_dummy=True)
    loading_screen = LoadingScreen(developer_mode=development_mode)
    loading_process = multiprocessing.Process(target=loading_screen.run, daemon=True)
    loading_process.start()

    pygame.init()

    game=Game(pygame.display.set_mode((0,0), pygame.HIDDEN),FPS=60,fullWorld=False,developingMode=development_mode,loading_screen=loading_screen)

    try:
        game.setup()
    except UserQuitDuringLoadingException:
        pass

    loading_process.join()
    loading_process.close()

    if not loading_screen.is_quit():
        game.set_window(pygame.display.set_mode((0,0)))
        game.run()

    pygame.quit()

if __name__ == "__main__":
    main()