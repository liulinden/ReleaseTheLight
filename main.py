import pygame, pickle

pygame.init()
window = pygame.display.set_mode((0,0))

from releaseTheLight import Game

#preset=False
#if preset:
#    with open("_save.pkl", "rb") as file:
#        game = pickle.load(file)
#else:
game=Game(window,FPS=60,fullWorld=False,developingMode=True)
game.setup()

game.run()

pygame.quit()