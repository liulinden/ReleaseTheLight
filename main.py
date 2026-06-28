import pygame

pygame.init()
window = pygame.display.set_mode((0,0))

from releaseTheLight import Game
game=Game(window,FPS=60,fullWorld=False,developingMode=True)
game.setup()
game.run()

pygame.quit()