import pygame, random, math, nest

# load images
airIMGs=[]
for i in range(5):
    airIMGs.append(pygame.image.load(".AirPocket"+str(i+1)+".png"))

def distance(coord1:int,coord2:int):
    x1,y1=coord1
    x2,y2=coord2
    return math.sqrt((x1-x2)**2+(y1-y2)**2)

def rectToCircle(left,top,width,height):
    return left+width/2,top+height/2,distance((0,0),(width,height))/2

# overall game world class
class Terrain:

    # set up and create world
    def __init__(self, worldWidth:int, worldHeight:int, defaultZooms:list[float]=[0.1,2]):

        # set up terrain data
        self.nests=[]
        self.airPockets = []
        self.worldWidth=worldWidth
        self.worldHeight=worldHeight
        self.defaultZooms = defaultZooms
        self.airPocketsSurfaces = {}
        for zoom in defaultZooms:
            self.airPocketsSurfaces[zoom]=[]
            for row in range(math.ceil(worldHeight/500)):
                row=[]
                for j in range(math.ceil(worldWidth/500)):
                    layer=pygame.Surface((500*zoom,500*zoom),pygame.SRCALPHA)
                    layer.fill((0,0,0,0))
                    row.append(layer)
                self.airPocketsSurfaces[zoom].append(row)
    
    def addAirPocketToSurfaces(self, airPocket):
        row,column=math.floor(airPocket.y/500),math.floor(airPocket.x/500)
        if row>9:
            print("broken")
        for offsets in ([0,0],[0,1],[1,0],[0,-1],[0,-1],[-1,0],[-1,0],[0,1],[0,1]):
            row+=offsets[0]
            column+=offsets[1]
            if row>=0 and column >=0 and row<self.worldHeight/500 and column<self.worldWidth/500:
                left,top=column*500,row*500
                for zoom in self.defaultZooms:
                    self.airPocketsSurfaces[zoom][row][column].blit(airPocket.IMGs[zoom],(zoom*(airPocket.left-left),zoom*(airPocket.top-top)))

    # generate caves/nests/decorations
    def generate(self):
        for i in range(int(self.worldHeight/100)):
            for j in range(int(self.worldWidth/1000)):

                if random.randint(1,10)==1:
                    self.generateSkinnyCave(j*1000+random.randint(0,1000),random.randint(0,int((self.worldHeight-500)/4)),random.randint(20,80),random.random()*2*math.pi)
                if random.randint(1,20)==1:
                    self.generateSkinnyCave(j*1000+random.randint(0,1000),random.randint(int((self.worldHeight-500)/4),int((self.worldHeight-500))),random.randint(40,80),random.random()*2*math.pi)
                
                if random.randint(1,35)==1:
                    self.generateBlobCave(j*1000+random.randint(0,1000),random.randint(int((self.worldHeight-500)*1/4),self.worldHeight-500),random.randint(40,80),random.random()*2*math.pi)
                if random.randint(1,25)==1:
                    self.generateBlobCave(j*1000+random.randint(0,1000),random.randint(int((self.worldHeight-500)*2/3),self.worldHeight-500),random.randint(80,120),random.random()*2*math.pi)

                if random.randint(1,30)==1:
                    self.generateBedrockCave(j*1000+random.randint(0,1000),random.randint(self.worldHeight-100,self.worldHeight),random.randint(120,150),random.randint(0,1)*2*math.pi)

                if random.randint(1,15)==1:
                    self.generateNest(j*1000+random.randint(0,1000),random.randint(500,int((self.worldHeight-500)/4)),"White")
                
                if random.randint(1,20)==1:
                    self.generateNest(j*1000+random.randint(0,1000),random.randint(int((self.worldHeight-500)/4),int((self.worldHeight-500)*2/3)),"White")

    def generateNest(self,x,y,nestType, size=0):
        if size==0:
            size = random.randint(100,100+y//50)
        newNest=nest.Nest(self.defaultZooms,nestType,x,y,size)
        self.nests.append(newNest)

        caveSize=(size*random.randint(0,2)/2+50)/2
        if caveSize >25:
            self.generateSkinnyCave(x,y-caveSize/2,caveSize,-math.pi/2,maxPockets=4,shrinking=True)

    # generate cave
    def generateBlobCave(self, startX:int, startY:int, startR:int, startDir:float=0, maxPockets:int=10):
        if maxPockets > 0 and (startY - 2*startR) > 0 and startY-startR < self.worldHeight and startR > 0:
            self.addAirPocket(startX,startY,startR)

            for i in range(2):
                r = startR + (random.random()-0.6)*20
                dir = startDir + (random.random()-0.5)*math.pi

                x = startX+math.cos(dir)*min(r,startR)*0.9
                y = startY+math.sin(dir)*min(r,startR)*0.9*0.4
                self.generateBlobCave(x,y,r,dir,maxPockets-1)
                if random.randint(1,15)>1:
                    break
    
    def generateSkinnyCave(self, startX:int, startY:int, startR:int, startDir:float=0, maxPockets:int=20,shrinking=False):
        if maxPockets > 0 and (startY - 2*startR) > 0 and startY-startR < self.worldHeight and startR > 0:
            self.addAirPocket(startX,startY,startR)

            for i in range(2):
                r = startR + (random.random()-0.6)*5
                if shrinking:
                    r=startR-random.random()*2
                dir = startDir + (random.random()-0.5)*math.pi/2

                x = startX+math.cos(dir)*min(r,startR)*0.9
                y = startY+math.sin(dir)*min(r,startR)*0.9*0.9
                self.generateSkinnyCave(x,y,r,dir,maxPockets-1,shrinking=shrinking)
                if random.randint(1,30)>1:
                    break
    
    def generateBedrockCave(self, startX:int, startY:int, startR:int, startDir:float=0, maxPockets:int=3):
        if maxPockets > 0 and (startY - 2*startR) > 0 and startY-startR < self.worldHeight and startR > 0:
            self.addAirPocket(startX,startY,startR)

            for i in range(2):
                r = startR + (random.random()-0.6)*20
                dir = startDir + (random.random()-0.5)*math.pi/2

                x = startX+math.cos(dir)*min(r,startR)*0.9
                y = startY+math.sin(dir)*min(r,startR)*0.9*0.3
                self.generateBedrockCave(x,y,r,dir,maxPockets-1)
                if random.randint(1,30)>1:
                    break

    # create an air pocket at x, y with specified radius
    def addAirPocket(self, x:int, y:int, radius:int, recursions=0, playerMade=False):
        if recursions>3 or x+radius>self.worldWidth or x-radius<0 or y<0 or y>self.worldHeight:
            return False
        newAirPocket=AirPocket(x,y,radius,defaultZooms=self.defaultZooms)
        if not playerMade:
            for airPocket in self.airPockets:
                if not airPocket is newAirPocket:
                    if airPocket.close(x,y,newAirPocket.r+10):
                        d = distance((airPocket.x,airPocket.y),(x,y))
                        if d<newAirPocket.r/4:
                            return False
                        if d > airPocket.r+newAirPocket.r and d < airPocket.r+newAirPocket.r + 10:
                            return self.addAirPocket((airPocket.x+x)/2,(airPocket.y+y)/2,(airPocket.r+radius)/2,recursions+1)
        self.airPockets.append(newAirPocket)
        self.addAirPocketToSurfaces(newAirPocket)
        return True

    """
    def updateOnscreenAirPockets(self,window,frame):
        left,top,zoom=frame
        w_width,w_height=window.get_size()
        w_x=left+w_width/zoom/2
        w_y=top+w_height/zoom/2
        w_r=distance((0,0),(w_width,w_height))/zoom/2

        self.onscreenAirPockets=[]
        for airPocket in self.airPockets:
            if airPocket.close(w_x,w_y,w_r):
                self.onscreenAirPockets.append(airPocket)"""
                
                

    # check for collision with rect
    def collideRect(self, rect:pygame.Rect):

        #new method

        #get terrain hitbox surface
        rectMask=pygame.Mask((rect.width,rect.height),fill=True)
        
        collidingLayer=self.getTerrainLayer(pygame.Surface((rect.width,rect.height)),[rect.left,rect.top,1],hitboxes=True)
        self.drawNests(collidingLayer,[rect.left,rect.top,1],hitboxes=True)

        terrainMask = pygame.mask.from_surface(collidingLayer)

        return not (terrainMask.overlap(rectMask,(0,0)) ==None)
        #compare with rect

    def drawNests(self,window:pygame.Surface,frame:list,hitboxes=False):
        left,top,zoom=frame
        w_width,w_height=window.get_size()
        x,y,r=left+w_width/zoom/2,top+w_height/zoom/2,distance((0,0),(w_width,w_height))/2/zoom

        for nest in self.nests:
            if nest.close(x,y,r):
                nest.draw(window,frame,hitbox=hitboxes)

    # return terrain layer
    def getTerrainLayer(self,window:pygame.Surface,frame:list,hitboxes=False):

        # get camera framing
        left,top,zoom=frame
        w_width,w_height=window.get_size()

        # set up world layer
        layer=pygame.Surface([w_width,w_height], pygame.SRCALPHA)
        layer.fill((255,255,255,255))

        # set up air pocket layer (negative space of the world)

        """
        air_surface = pygame.Surface((w_width, w_height), pygame.SRCALPHA)
        air_surface.fill((0, 0, 0, 0))

        
        # draw air pockets
        x,y,r = rectToCircle(left,top,w_width/zoom,w_height/zoom)
        if not hitboxes:
            if zoom in self.defaultZooms:
                for airPocket in self.airPockets:
                    if airPocket.close(x,y,r):
                        air_surface.blit(airPocket.IMGs[zoom],(zoom*(airPocket.left-left),zoom*(airPocket.top-top)))
            else:
                for airPocket in self.airPockets:
                    if airPocket.close(x,y,r):
                        air_surface.blit(pygame.transform.scale(airPocket.fullResIMG,(airPocket.r*2*zoom,airPocket.r*2*zoom)),(zoom*(airPocket.left-left),zoom*(airPocket.top-top)))
        else:
            for airPocket in self.airPockets:
                if airPocket.close(x,y,r):
                    pygame.draw.circle(air_surface,(255,255,255,255),((zoom*(airPocket.x-left),zoom*(airPocket.y-top))),airPocket.r*zoom)

        # top/bottom of the world
        pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,0,w_width,zoom*max(0,0-top)))
        #pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,min(w_height,(self.worldHeight-top)*zoom),w_width,w_height-min(w_height,(self.worldHeight-top)*zoom)))
        
        layer.blit(air_surface, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)

        """
        if not hitboxes:
            if zoom in self.defaultZooms:
                topChunk=math.floor(max(0,min(self.worldHeight,top-500))/500)
                leftChunk=math.floor(max(0,min(self.worldWidth,left-500))/500)
                bottomChunk=math.ceil(max(0,min(self.worldHeight-500,top+w_height/zoom+500))/500)
                rightChunk=math.ceil(max(0,min(self.worldWidth-500,left+w_width/zoom+500))/500)
                # clear air pockets from base 
                for row in range(topChunk,bottomChunk+1,1):
                    for column in range(leftChunk,rightChunk+1,1):
                        layer.blit(self.airPocketsSurfaces[zoom][row][column], ((column*500-left)*zoom, (row*500-top)*zoom), special_flags=pygame.BLEND_RGBA_SUB)
                air_surface = pygame.Surface((w_width, w_height), pygame.SRCALPHA)
                pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,0,w_width,zoom*max(0,0-top)))
                pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,min(w_height,(self.worldHeight-top)*zoom),w_width,w_height-min(w_height,(self.worldHeight-top)*zoom)))
                layer.blit(air_surface, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
            else:
                topChunk=math.floor(max(0,min(self.worldHeight,top-500))/500)
                leftChunk=math.floor(max(0,min(self.worldWidth,left-500))/500)
                bottomChunk=math.ceil(max(0,min(self.worldHeight-500,top+w_height/zoom+500))/500)
                rightChunk=math.ceil(max(0,min(self.worldWidth-500,left+w_width/zoom+500))/500)
                # clear air pockets from base 
                for row in range(topChunk,bottomChunk+1,1):
                    for column in range(leftChunk,rightChunk+1,1):
                        layer.blit(pygame.transform.scale(self.airPocketsSurfaces[2][row][column],(500*zoom,500*zoom)), ((column*500-left)*zoom, (row*500-top)*zoom), special_flags=pygame.BLEND_RGBA_SUB)
                air_surface = pygame.Surface((w_width, w_height), pygame.SRCALPHA)
                pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,0,w_width,zoom*max(0,0-top)))
                pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,min(w_height,(self.worldHeight-top)*zoom),w_width,w_height-min(w_height,(self.worldHeight-top)*zoom)))
                layer.blit(air_surface, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)            
        else:
            air_surface = pygame.Surface((w_width, w_height), pygame.SRCALPHA)
            air_surface.fill((0, 0, 0, 0))
            x,y,r = rectToCircle(left,top,w_width/zoom,w_height/zoom)
            for airPocket in self.airPockets:
                if airPocket.close(x,y,r):
                    pygame.draw.circle(air_surface,(255,255,255,255),((zoom*(airPocket.x-left),zoom*(airPocket.y-top))),airPocket.r*zoom)
            # top/bottom of the world
            pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,0,w_width,zoom*max(0,0-top)))
            pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,min(w_height,(self.worldHeight-top)*zoom),w_width,w_height-min(w_height,(self.worldHeight-top)*zoom)))
            
            layer.blit(air_surface, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
        
        

        # return terrain layer
        return layer

# air pocket class
class AirPocket:

    # set up air pocket
    def __init__(self,x:int,y:int,radius:int,defaultZooms:list[float]=[0.1,2]):
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