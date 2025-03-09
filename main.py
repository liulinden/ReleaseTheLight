import pygame
pygame.init()

window = pygame.display.set_mode((0,0))

import releaseTheLight
releaseTheLight.Game(window,FPS=90,fullWorld=False,developingMode=True).run()