# imports
import world, pygame, random

# constants
FPS = 60
DEFAULT_ZOOM = 0.1
SCREEN_WIDTH = 1000
SCREEN_HEIGHT = 700
WORLD_WIDTH = 6000
WORLD_HEIGHT = 4000

# set up variables
running= True
zoom=DEFAULT_ZOOM

# create world
screen = pygame.display.set_mode([SCREEN_WIDTH,SCREEN_HEIGHT])
gameWorld = world.World(WORLD_WIDTH,WORLD_HEIGHT,defaultZoom=DEFAULT_ZOOM)
clock = pygame.time.Clock()

# load images
light=pygame.transform.scale(pygame.image.load(".Light.png"),(600,600))

#main loop
while running:

    # get mouse pos
    x,y=pygame.mouse.get_pos()

    # player inputs
    for event in pygame.event.get():

        # close game
        if event.type==pygame.QUIT:
            running=False
            break
            
        # TEMPORARY - create new air pocket
        if event.type==pygame.MOUSEBUTTONDOWN:
            
            gameWorld.terrain.generateSkinnyCave(x/zoom,y/zoom,50)

    # clear screen
    screen.fill((0,0,0))

    # TEMPORARY - display light at mouse position
    #screen.blit(light,(x-300,y-300))
    #screen.blit(light,(x-300,y-300))

    # display terrain layer
    screen.blit(gameWorld.getSurface(screen,[-2000,-100,zoom]),(0,0))

    # update screen
    pygame.display.flip()

    # tick game
    clock.tick(FPS)
