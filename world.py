# imports
import pygame, random

# load images
airIMGs=[]
for i in range(5):
    airIMGs.append(pygame.image.load("AirPocket"+str(i+1)+".png"))

# overall game world class
class World:

    # set up and create world
    def __init__(self, worldWidth, worldBottom, worldTop):

        # set up world data
        self.airPockets = [AirPocket(60,50,50),AirPocket(100,100,50),AirPocket(150,140,60)]
        self.nests= []
        self.surface = []
        self.worldWidth=worldWidth
        self.worldBottom=worldBottom
        self.worldTop=worldTop

        # procedural generation
        self.generateWorld()
    
    # generate caves/nests/decorations
    def generateWorld(self):
        ...
    
    # create an air pocket at x, y with specified radius
    def addAirPocket(self, x, y, radius):
        self.airPockets.append(AirPocket(x,y,radius))
    
    # return world layer
    def getSurface(self,window,frame):

        # get camera framing
        left,top,zoom=frame
        w_width,w_height=window.get_size()
        width,height=w_width/zoom,w_height/zoom

        # set up world layer
        s=pygame.Surface([width,height])
        s.fill((255,255,255,255))

        # set up air pocket layer (negative space of the world)
        air_surface = pygame.Surface((width, height), pygame.SRCALPHA)
        air_surface.fill((0, 0, 0, 0))

        # draw air pockets
        for airPocket in self.airPockets:
            air_surface.blit(airPocket.img,(airPocket.left-left,airPocket.top-top))
            #pygame.draw.circle(air_surface, (255, 255, 255, 255), (x, y), r)
        
        # top/bottom of the world
        pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,0,width,max(0,self.worldTop-top)))
        pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,min(height,self.worldBottom-top),width,height-min(height,self.worldBottom-(top))))

        # clear air pockets from base layer
        s.blit(air_surface, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)

        # resize world layer for viewing
        s= pygame.transform.scale(s,(w_width,w_height))

        # return world layer
        return s

# air pocket class
class AirPocket:

    # set up air pocket
    def __init__(self,x,y,radius):
        self.x=x
        self.y=y
        self.r=radius
        self.top=self.y-self.r
        self.left=self.x-self.r
        self.img=pygame.transform.scale(airIMGs[random.randint(0,4)],(2*self.r,2*self.r))
