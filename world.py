# imports
import pygame, random, terrain, decoration, nest, aplayer

# load images
airIMGs=[]
for i in range(5):
    airIMGs.append(pygame.image.load(".AirPocket"+str(i+1)+".png"))

# overall game world class
class World:

    # set up and create world
    def __init__(self, worldWidth, worldHeight, defaultZooms=[0.1,1]):

        # set up world data
        self.terrain = terrain.Terrain(worldWidth,worldHeight,defaultZooms=defaultZooms)
        self.nests= []
        self.decorations=[]
        self.worldWidth=worldWidth
        self.worldHeight=worldHeight
        self.defaultZooms = defaultZooms
        self.player= aplayer.Player(0,-200)

        # procedural generation
        self.generateWorld()
    
    # generate caves/nests/decorations
    def generateWorld(self):
        self.terrain.generate()
    
    # create an air pocket at x, y with specified radius
    def addAirPocket(self, x, y, radius):
        self.terrain.addAirPocket(x,y,radius)
    
    #perform frame actions
    def tick(self,FPS,window,frame, keysDown):
        frameLength=1000/FPS

        self.player.tick(frameLength,self.terrain, keysDown)

        #change camx camy
        #update airpockets - FPS KILLERRR
        self.terrain.updateOnscreenAirPockets(window,frame)

        #draw
        
        ...
    
    # return world layer
    def getSurface(self,window,frame):

        # set up layer
        layer=pygame.Surface(window.get_size())
        layer.fill((100,100,100,0))

        # add lighting layer

        #add enemies layer

        # add player layer
        self.player.draw(layer, frame)

        # add particles layer

        # add terrain layer
        layer.blit(self.terrain.getTerrainLayer(window,frame),(0,0),special_flags=pygame.BLEND_RGBA_SUB)

        return layer