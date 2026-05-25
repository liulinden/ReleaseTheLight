import pygame
pygame.init()

window = pygame.display.set_mode((0,0))

import loading_screen
queue = loading_screen.LoadingScreen(window).start_thread()

queue.put(0.05)
import releaseTheLight
queue.put(0.1)
releaseTheLight.Game(window,FPS=90,fullWorld=True,developingMode=True, loading_status_queue=queue).run()