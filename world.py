# imports
import pygame, random, terrain, decoration, nest, player

# load images
airIMGs=[]
for i in range(5):
    airIMGs.append(pygame.image.load(".AirPocket"+str(i+1)+".png"))

# overall game world class
class World:

    # set up and create world
    def __init__(self, worldWidth, worldHeight, defaultZoom=1):

        # set up world data
        self.terrain = terrain.Terrain(worldWidth,worldHeight,defaultZoom=defaultZoom)
        self.nests= []
        self.decorations=[]
        self.worldWidth=worldWidth
        self.worldHeight=worldHeight
        self.defaultZoom = defaultZoom

        # procedural generation
        self.generateWorld()
    
    # generate caves/nests/decorations
    def generateWorld(self):
        self.terrain.generate()
    
    # create an air pocket at x, y with specified radius
    def addAirPocket(self, x, y, radius):
        self.terrain.addAirPocket(x,y,radius)
    
    # return world layer
    def getSurface(self,window,frame):

        # set up layer
        layer=pygame.Surface(window.get_size())
        layer.fill((100,100,100,0))

        # add lighting layer

        #add enemies layer

        # add player layer

        # add particles layer

        # add terrain layer
        layer.blit(self.terrain.getTerrainLayer(window,frame),(0,0),special_flags=pygame.BLEND_RGBA_SUB)

        return layer