import pygame, random, math

# load images
airIMGs=[]
for i in range(5):
    airIMGs.append(pygame.image.load(".AirPocket"+str(i+1)+".png"))

def distance(coord1:int,coord2:int):
    x1,y1=coord1
    x2,y2=coord2
    return math.sqrt((x1-x2)**2+(y1-y2)**2)

# overall game world class
class Terrain:

    # set up and create world
    def __init__(self, worldWidth:int, worldHeight:int, defaultZooms:list[float]=[0.1,1]):

        # set up terrain data
        self.airPockets = []
        self.worldWidth=worldWidth
        self.worldHeight=worldHeight
        self.defaultZooms = defaultZooms
        self.onscreenAirPockets=[]
    
    # generate caves/nests/decorations
    def generate(self):
        for i in range(int(self.worldHeight/1000)):
            for j in range(int(self.worldWidth/1000)):

                if random.randint(1,1)==1:
                    self.generateSkinnyCave(j*1000+random.randint(0,1000),random.randint(0,int(self.worldHeight/4)),random.randint(20,80),random.random()*2*math.pi)
                if random.randint(1,3)==1:
                    self.generateSkinnyCave(j*1000+random.randint(0,1000),random.randint(0,int(self.worldHeight*4/5)),random.randint(40,80),random.random()*2*math.pi)
                
                if random.randint(1,3)==1:
                    self.generateBlobCave(j*1000+random.randint(0,1000),random.randint(int(self.worldHeight*1/4),self.worldHeight),random.randint(40,80),random.random()*2*math.pi)
                if random.randint(1,2)==1:
                    self.generateBlobCave(j*1000+random.randint(0,1000),random.randint(int(self.worldHeight*2/3),self.worldHeight),random.randint(80,120),random.random()*2*math.pi)

    # generate cave
    def generateBlobCave(self, startX:int, startY:int, startR:int, startDir:float=0, maxPockets:int=50):
        if maxPockets > 0 and (startY - 2*startR) > 0 and startY-startR < self.worldHeight and startR > 0:
            self.addAirPocket(startX,startY,startR)

            for i in range(2):
                r = startR + (random.random()-0.6)*20
                dir = startDir + (random.random()-0.5)*math.pi

                x = startX+math.cos(dir)*min(r,startR)*0.8
                y = startY+math.sin(dir)*min(r,startR)*0.8*0.4
                self.generateBlobCave(x,y,r,dir,maxPockets-1)
                if random.randint(1,15)>1:
                    break
    
    def generateSkinnyCave(self, startX:int, startY:int, startR:int, startDir:float=0, maxPockets:int=50):
        if maxPockets > 0 and (startY - 2*startR) > 0 and startY-startR < self.worldHeight and startR > 0:
            self.addAirPocket(startX,startY,startR)

            for i in range(2):
                r = startR + (random.random()-0.6)*5
                dir = startDir + (random.random()-0.5)*math.pi/2

                x = startX+math.cos(dir)*min(r,startR)*0.9
                y = startY+math.sin(dir)*min(r,startR)*0.9*0.9
                self.generateSkinnyCave(x,y,r,dir,maxPockets-1)
                if random.randint(1,30)>1:
                    break

    # create an air pocket at x, y with specified radius
    def addAirPocket(self, x:int, y:int, radius:int, recursions=0):
        if recursions>3 or x>self.worldWidth or x<0:
            return False
        newAirPocket=AirPocket(x,y,radius,defaultZooms=self.defaultZooms)
        for airPocket in self.airPockets:
            if not airPocket is newAirPocket:
                if airPocket.close(x,y,newAirPocket.r+10):
                    d = distance((airPocket.x,airPocket.y),(x,y))
                    if d > airPocket.r+newAirPocket.r and d < airPocket.r+newAirPocket.r + 10:
                        return self.addAirPocket((airPocket.x+x)/2,(airPocket.y+y)/2,(airPocket.r+radius)/2,recursions+1)
        self.airPockets.append(newAirPocket)
        return True
    
    def updateOnscreenAirPockets(self,window,frame):
        left,top,zoom=frame
        w_width,w_height=window.get_size()
        w_x=left+w_width/zoom/2
        w_y=top+w_height/zoom/2
        w_r=distance((0,0),(w_width,w_height))/zoom/2

        self.onscreenAirPockets=[]
        for airPocket in self.airPockets:
            if airPocket.close(w_x,w_y,w_r):
                self.onscreenAirPockets.append(airPocket)
                
                

    # check for collision with rect
    def collideRect(self, rect:pygame.Rect):
        print("3",rect.bottom)
        if rect.bottom<0:
            return False
        x,y=rect.centerx,rect.centery
        r=distance((0,0),(rect.width,rect.height))/2
        for airPocket in self.onscreenAirPockets:
            if airPocket.containsRect(rect,x,y,r):
                return False
        return True
    
    # return terrain layer
    def getTerrainLayer(self,window:pygame.Surface,frame:list):

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
        if zoom in self.defaultZooms:
            for airPocket in self.onscreenAirPockets:
                air_surface.blit(airPocket.IMGs[zoom],(zoom*(airPocket.left-left),zoom*(airPocket.top-top)))
        else:
            for airPocket in self.onscreenAirPockets:
                air_surface.blit(pygame.transform.scale(airPocket.fullResIMG,(airPocket.r*2*zoom,airPocket.r*2*zoom)),(zoom*(airPocket.left-left),zoom*(airPocket.top-top)))

        # top/bottom of the world
        pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,0,w_width,zoom*max(0,0-top)))
        pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,min(w_height,(self.worldHeight-top)*zoom),w_width,w_height-min(w_height,(self.worldHeight-top)*zoom)))

        # clear air pockets from base layer
        layer.blit(air_surface, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)

        # return terrain layer
        return layer

# air pocket class
class AirPocket:

    # set up air pocket
    def __init__(self,x:int,y:int,radius:int,defaultZooms:list[float]=[0.1,1]):
        self.x=x
        self.y=y
        self.r=radius
        self.top=self.y-self.r
        self.left=self.x-self.r
        self.fullResIMG=airIMGs[random.randint(0,4)]
        self.IMGs={}
        for defaultZoom in defaultZooms:
            self.IMGs[defaultZoom]=pygame.transform.scale(self.fullResIMG,(2*self.r*defaultZoom,2*self.r*defaultZoom))

    # preliminary check if two circles are near each other
    def close(self,x:int,y:int,radius:int):
        if abs(self.x-x)>radius+self.r:
            return False
        if abs(self.y-y)>radius+self.r:
            return False
        return True
    
    # return if AirPocket contains given rect
    def containsRect(self,rect: pygame.Rect,x:int,y:int,r:int):
        if not self.close(x,y,r):
            return False
        for vertex in [rect.topleft,rect.bottomleft,rect.topright,rect.bottomright]:
            if distance(vertex,(self.x,self.y))>self.r:
                return False
        return True