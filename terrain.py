import pygame, random, math

# load images
airIMGs=[]
for i in range(5):
    airIMGs.append(pygame.image.load(".AirPocket"+str(i+1)+".png"))

# overall game world class
class Terrain:

    # set up and create world
    def __init__(self, worldWidth, worldBottom, worldTop, defaultZoom=1):

        # set up terrain data
        self.airPockets = []
        self.worldWidth=worldWidth
        self.worldBottom=worldBottom
        self.worldTop=worldTop
        self.defaultZoom = defaultZoom
    
    # generate caves/nests/decorations
    def generate(self):
        for i in range(int((self.worldBottom-self.worldTop)/1000)):
            for j in range(int(self.worldWidth/500)):    
                self.generateCave(j*500+random.randint(0,500),random.randint(self.worldTop,self.worldBottom),random.randint(60,100),random.random()*2*math.pi)
    
    # generate cave
    def generateCave(self, startX, startY, startR, startDir=0, maxPockets=50):
        if maxPockets > 0 and (startY - 2*startR) > self.worldTop and startY-startR < self.worldBottom and startR > 0:
            self.addAirPocket(startX,startY,startR)

            for i in range(2):
                r = startR + (random.random()-0.6)*20
                dir = startDir + (random.random()-0.5)*math.pi

                x = startX+math.cos(dir)*min(r,startR)*0.8
                y = startY+math.sin(dir)*min(r,startR)*0.8*0.4
                self.generateCave(x,y,r,dir,maxPockets-1)
                if random.randint(1,15)>1:
                    break
    
    # create an air pocket at x, y with specified radius
    def addAirPocket(self, x, y, radius):
        self.airPockets.append(AirPocket(x,y,radius,defaultZoom=self.defaultZoom))
    
    # return terrain layer
    def getTerrainLayer(self,window,frame):

        # get camera framing
        left,top,zoom=frame
        w_width,w_height=window.get_size()

        # set up world layer
        layer=pygame.Surface([w_width,w_height])
        layer.fill((255,255,255,255))

        # set up air pocket layer (negative space of the world)
        air_surface = pygame.Surface((w_width, w_height), pygame.SRCALPHA)
        air_surface.fill((0, 0, 0, 0))

        # draw air pockets
        if zoom == self.defaultZoom:
            for airPocket in self.airPockets:
                air_surface.blit(airPocket.IMG,(zoom*(airPocket.left-left),zoom*(airPocket.top-top)))
        else:
            for airPocket in self.airPockets:
                air_surface.blit(pygame.transform.scale(airPocket.IMG,(airPocket.r*2*zoom,airPocket.r*2*zoom)),(zoom*(airPocket.left-left),zoom*(airPocket.top-top)))

        # top/bottom of the world
        pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,0,w_width,zoom*max(0,self.worldTop-top)))
        pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,min(w_height,(self.worldBottom-top)*zoom),w_width,w_height-min(w_height,(self.worldBottom-top)*zoom)))

        # clear air pockets from base layer
        layer.blit(air_surface, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)

        # return terrain layer
        return layer

# air pocket class
class AirPocket:

    # set up air pocket
    def __init__(self,x,y,radius,defaultZoom=1):
        self.x=x
        self.y=y
        self.r=radius
        self.top=self.y-self.r
        self.left=self.x-self.r
        self.IMG=pygame.transform.scale(airIMGs[random.randint(0,4)],(2*self.r*defaultZoom,2*self.r*defaultZoom))
