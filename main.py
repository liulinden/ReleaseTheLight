import pygame
pygame.init()

window = pygame.display.set_mode((0,0))

from loading_screen import LoadingScreen
loading_screen = LoadingScreen(window)
loading_screen.subsection(0, 0.1).run_on_thread()

from releaseTheLight import Game
loading_screen.put(0.05)
Game(window,FPS=60,fullWorld=False,developingMode=True,loading_screen=loading_screen).run()
