# imports
import pygame, random

# load images
airIMGs=[]
for i in range(5):
    airIMGs.append(pygame.image.load("AirPocket"+str(i+1)+".png"))

# overall game world class
class World:

    # set up and create world
    def __init__(self, worldWidth, worldBottom, worldTop, defaultZoom=1):

        # set up world data
        self.airPockets = []
        self.nests= []
        self.surface = []
        self.worldWidth=worldWidth
        self.worldBottom=worldBottom
        self.worldTop=worldTop
        self.defaultZoom = defaultZoom

        # TEMPORARY - starting air pockets
        self.addAirPocket(60,50,50)
        self.addAirPocket(100,100,50)
        self.addAirPocket(150,140,60)

        # procedural generation
        self.generateWorld()
    
    # generate caves/nests/decorations
    def generateWorld(self):
        ...
    
    # create an air pocket at x, y with specified radius
    def addAirPocket(self, x, y, radius):
        self.airPockets.append(AirPocket(x,y,radius,defaultZoom=self.defaultZoom))
    
    # return world layer
    def getSurface(self,window,frame):

        # get camera framing
        left,top,zoom=frame
        w_width,w_height=window.get_size()

        # set up world layer
        s=pygame.Surface([w_width,w_height])
        s.fill((255,255,255,255))

        # set up air pocket layer (negative space of the world)
        air_surface = pygame.Surface((w_width, w_height), pygame.SRCALPHA)
        air_surface.fill((0, 0, 0, 0))

        # draw air pockets
        if zoom == self.defaultZoom:
            for airPocket in self.airPockets:
                air_surface.blit(airPocket.img,(zoom*(airPocket.left-left),zoom*(airPocket.top-top)))
        else:
            for airPocket in self.airPockets:
                air_surface.blit(pygame.transform.scale(airPocket.img,(airPocket.r*2*zoom,airPocket.r*2*zoom)),(zoom*(airPocket.left-left),zoom*(airPocket.top-top)))

        # top/bottom of the world
        pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,0,w_width,zoom*max(0,self.worldTop-top)))
        pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,min(w_height,(self.worldBottom-top)*zoom),w_width,w_height-min(w_height,(self.worldBottom-top)*zoom)))

        # clear air pockets from base layer
        s.blit(air_surface, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)

        # return world layer
        return s

# air pocket class
class AirPocket:

    # set up air pocket
    def __init__(self,x,y,radius,defaultZoom=1):
        self.x=x
        self.y=y
        self.r=radius
        self.top=self.y-self.r
        self.left=self.x-self.r
        self.img=pygame.transform.scale(airIMGs[random.randint(0,4)],(2*self.r*defaultZoom,2*self.r*defaultZoom))
