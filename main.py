import pygame
pygame.init()

window = pygame.display.set_mode((0,0))

from loading_screen import LoadingScreen
loading_screen = LoadingScreen(window)
loading_screen.run_threaded(end_at=0.1)

from releaseTheLight import Game
loading_screen.get_queue().put(0.05)
Game(window,FPS=90,fullWorld=True,developingMode=True,loading_screen=loading_screen).run()
