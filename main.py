# do imports
import world, pygame, random

# create world
screen = pygame.display.set_mode([1000,700])
gameWorld = world.World(300,1300,0)
clock = pygame.time.Clock()

# constants
FPS = 60

# set up variables
running= True
zoom=0.1

# load images
light=pygame.transform.scale(pygame.image.load("Light.png"),(600,600))

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
            
            gameWorld.addAirPocket(x/zoom,y/zoom,100)

    # clear screen
    screen.fill((0,0,0))

    # TEMPORARY - display light at mouse position
    screen.blit(light,(x-300,y-300))
    screen.blit(light,(x-300,y-300))

    # display terrain layer
    screen.blit(gameWorld.getSurface(screen,[0,0,zoom]),(0,0),special_flags=pygame.BLEND_RGBA_SUB)

    # update screen
    pygame.display.flip()

    # tick game
    clock.tick(FPS)
    