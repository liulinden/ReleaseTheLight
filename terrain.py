import pygame, random, math, nest,particles,os

# load images
airIMGs={}
circleIMGs=[]
for i in range(4):
    circleIMGs.append(pygame.image.load(os.path.join("assets","AirPocket"+str(i+1)+".png")).convert_alpha())
airIMGs["Circle"]=circleIMGs

airHitboxIMGs={}
for customPocket in ["C1"]:
    airIMGs[customPocket]=[pygame.image.load(os.path.join("assets","AirPocket"+customPocket+".png")).convert_alpha()]
    airHitboxIMGs[customPocket]=pygame.image.load(os.path.join("assets","AirPocket"+customPocket+"Hitbox.png")).convert_alpha()

def distance(coord1:int,coord2:int):
    x1,y1=coord1
    x2,y2=coord2
    return math.sqrt((x1-x2)**2+(y1-y2)**2)

def rectToCircle(left,top,width,height):
    return left+width/2,top+height/2,distance((0,0),(width,height))/2

hitbox_chunk_size=125
max_airpocket_radius=120

# overall game world class
class Terrain:

    # set up and create world
    def __init__(self, worldWidth:int, worldHeight:int, defaultZooms:list[float]=[0.1,2]):

        # set up terrain data
        self.knockbackCircles=[]
        self.newKnockbackCircles=[]
        self.playerDamageCircles=[]
        self.newPlayerDamageCircles=[]
        self.nests=[]
        self.airPockets = []
        self.worldWidth=worldWidth
        self.worldHeight=worldHeight
        self.defaultZooms = defaultZooms
        self.airPocketsSurfaces = {}
        self.airPocketsHitboxesSurfaces={}
        self.particles=particles.Particles()
        for zoom in defaultZooms:
            self.airPocketsSurfaces[zoom]=[]
            for row in range(math.ceil(worldHeight/500)+1):
                row=[]
                row2=[]
                for j in range(math.ceil(worldWidth/500)):
                    layer=pygame.Surface((500*zoom,500*zoom),pygame.SRCALPHA)
                    row.append(layer)
                self.airPocketsSurfaces[zoom].append(row)

        for zoom in defaultZooms:
            self.airPocketsHitboxesSurfaces[zoom]=[]
            for row in range(math.ceil(worldHeight/hitbox_chunk_size)+1):
                row=[]
                for j in range(math.ceil(worldWidth/hitbox_chunk_size)):
                    layer=pygame.Surface((hitbox_chunk_size*zoom,hitbox_chunk_size*zoom),pygame.SRCALPHA)
                    row.append(layer)
                self.airPocketsHitboxesSurfaces[zoom].append(row)
    
    def addAirPocketToSurfaces(self, airPocket):
        row,column=math.floor(airPocket.y/500),math.floor(airPocket.x/500)
        for offsets in ([0,0],[0,1],[1,0],[0,-1],[0,-1],[-1,0],[-1,0],[0,1],[0,1]):
            row+=offsets[0]
            column+=offsets[1]
            if row>=0 and column >=0 and row<=self.worldHeight/500 and column<self.worldWidth/500:
                left,top=column*500,row*500
                for zoom in self.defaultZooms:
                    ...
                    self.airPocketsSurfaces[zoom][row][column].blit(airPocket.IMGs[zoom],(zoom*(airPocket.left-left),zoom*(airPocket.top-top)))
                    
        row,column=math.floor(airPocket.y/hitbox_chunk_size),math.floor(airPocket.x/hitbox_chunk_size)
        for offsets in ([0,0],[0,1],[1,0],[0,-1],[0,-1],[-1,0],[-1,0],[0,1],[0,1]):
            row+=offsets[0]
            column+=offsets[1]
            if row>=0 and column >=0 and row<=self.worldHeight/hitbox_chunk_size and column<self.worldWidth/hitbox_chunk_size:
                left,top=column*hitbox_chunk_size,row*hitbox_chunk_size
                for zoom in self.defaultZooms:
                    if airPocket.type=="Circle":
                        pygame.draw.circle(self.airPocketsHitboxesSurfaces[zoom][row][column],(255,255,255),(zoom*(airPocket.x-left),zoom*(airPocket.y-top)),airPocket.r*zoom)
                    else:
                        self.airPocketsHitboxesSurfaces[zoom][row][column].blit(airPocket.hitboxIMGs[zoom],(zoom*(airPocket.left-left),zoom*(airPocket.top-top)))

    # generate caves/nests/decorations
    def generate(self):
        x=-500
        while x<self.worldWidth+500:
            r=random.randint(10,30)
            self.addAirPocketClump(x,0,r,playerMade=True)
            x+=r/2
        for i in range(int(self.worldHeight/100)):
            for j in range(int(self.worldWidth/1000)):

                if random.randint(1,10)==1:
                    self.generateSkinnyCave(j*1000+random.randint(0,1000),random.randint(0,int((self.worldHeight-500)/3)),random.randint(20,60),random.random()*2*math.pi)
                if random.randint(1,20)==1:
                    self.generateSkinnyCave(j*1000+random.randint(0,1000),random.randint(int((self.worldHeight-500)/4),int((self.worldHeight-500))),random.randint(30,90),random.random()*2*math.pi)
                
                if random.randint(1,35)==1:
                    self.generateBlobCave(j*1000+random.randint(0,1000),random.randint(int((self.worldHeight-500)*1/4),self.worldHeight-500),random.randint(30,60),random.random()*2*math.pi)
                if random.randint(1,20)==1:
                    self.generateBlobCave(j*1000+random.randint(0,1000),random.randint(int((self.worldHeight-500)*2/3),self.worldHeight-500),random.randint(60,120),random.random()*2*math.pi)

                if random.randint(1,25)==1:
                    self.generateBedrockCave(j*1000+random.randint(0,1000),random.randint(self.worldHeight-100,self.worldHeight),random.randint(80,120),random.randint(0,1)*2*math.pi)

                if random.randint(1,10)==1:
                    self.generateNest(j*1000+random.randint(0,1000),random.randint(500,int((self.worldHeight-500)/4)),"White")
                
                if random.randint(1,15)==1:
                    self.generateNest(j*1000+random.randint(0,1000),random.randint(int((self.worldHeight-500)/4),int((self.worldHeight-500)*2/3)),"White")
                if random.randint(1,15)==1:
                    self.generateNest(j*1000+random.randint(0,1000),random.randint(int((self.worldHeight-500)*3/4),int((self.worldHeight-500))),"White")
                
                if random.randint(1,15)==1:
                    self.generateNest(j*1000+random.randint(0,1000),random.randint(int((self.worldHeight-500)*1/4),self.worldHeight-500),"Red")
                if random.randint(1,15)==1:
                    self.generateNest(j*1000+random.randint(0,1000),random.randint(int((self.worldHeight-500)*1/4),self.worldHeight-500),"Blue")
                
                if random.randint(1,50)==1:
                    self.generateNest(j*1000+random.randint(0,1000),random.randint(int((self.worldHeight/2)),self.worldHeight-5),"White")
                if random.randint(1,20)==1:
                    self.generateNest(j*1000+random.randint(0,1000),random.randint(int((self.worldHeight/2)),self.worldHeight-5),"Red")
                if random.randint(1,20)==1:
                    self.generateNest(j*1000+random.randint(0,1000),random.randint(int((self.worldHeight/2)),self.worldHeight-5),"Blue")

                if random.randint(1,40)==1:
                    self.generateNest(j*1000+random.randint(0,1000),random.randint(int((self.worldHeight-500)),self.worldHeight-5),"White")
                if random.randint(1,35)==1:
                    self.generateNest(j*1000+random.randint(0,1000),random.randint(int((self.worldHeight-500)),self.worldHeight-5),"Red")
                if random.randint(1,35)==1:
                    self.generateNest(j*1000+random.randint(0,1000),random.randint(int((self.worldHeight-500)),self.worldHeight-5),"Blue")

    def generateNest(self,x,y,nestType, size=0):
        if size==0:
            size = random.randint(100,100+(y*150)//self.worldHeight)
        newNest=nest.Nest(self.defaultZooms,self.worldHeight,nestType,x,y,size)
        rect=newNest.getRect()
        for cnest in self.nests:
            if rect.colliderect(cnest.getRect()):
                return False
        self.nests.append(newNest)

        caveSize=(size*random.randint(0,2)/3+80)/3
        if caveSize >15:
            self.generateSkinnyCave(x,y-caveSize/2,caveSize,-math.pi/2,maxPockets=10,shrinking=True)
        else:
            self.addAirPocketClump(x,y-caveSize/2,caveSize)
        return True

    # generate cave
    def generateBlobCave(self, startX:int, startY:int, startR:int, startDir:float=0, maxPockets:int=10):
        if maxPockets > 0 and (startY - 2*startR) > 0 and startY-startR < self.worldHeight and startR > 0:
            self.addAirPocketClump(startX,startY,startR)

            for i in range(2):
                r = startR + (random.random()-0.6)*20
                dir = startDir + (random.random()-0.5)*math.pi

                x = startX+math.cos(dir)*min(r,startR)*0.8
                y = startY+math.sin(dir)*min(r,startR)*0.8*0.2
                self.generateBlobCave(x,y,r,dir,maxPockets-1)
                if random.randint(1,15)>1:
                    break
    
    def generateSkinnyCave(self, startX:int, startY:int, startR:int, startDir:float=0, maxPockets:int=20,shrinking=False):
        if maxPockets > 0 and (startY - 2*startR) > 0 and startY-startR < self.worldHeight and startR > 0:
            self.addAirPocketClump(startX,startY,startR)

            for i in range(2):
                r = startR + (random.random()-0.6)*5
                if shrinking:
                    r=startR-random.random()*2
                dir = startDir + (random.random()-0.5)*math.pi/2

                x = startX+math.cos(dir)*min(r,startR)*0.8
                y = startY+math.sin(dir)*min(r,startR)*0.8*0.8
                self.generateSkinnyCave(x,y,r,dir,maxPockets-1,shrinking=shrinking)
                if random.randint(1,30)>1:
                    break
    
    def generateBedrockCave(self, startX:int, startY:int, startR:int, startDir:float=0, maxPockets:int=3):
        if maxPockets > 0 and (startY - 2*startR) > 0 and startY-startR < self.worldHeight and startR > 0:
            self.addAirPocketClump(startX,startY,startR)

            for i in range(2):
                r = startR + (random.random()-0.6)*20
                dir = startDir + (random.random()-0.5)*math.pi/2

                x = startX+math.cos(dir)*min(r,startR)*0.7
                y = startY+math.sin(dir)*min(r,startR)*0.7*0.5
                self.generateBedrockCave(x,y,r,dir,maxPockets-1)
                if random.randint(1,30)>1:
                    break

    def addAirPocketClump(self,x,y,radius, playerMade=False,spreading=1/3):
        spreading=radius*spreading
        for i in range(3):
            self.addAirPocket(x+spreading*(random.random()*2-1),y+spreading*(random.random()*2-1),radius,playerMade=playerMade)


    # create an air pocket at x, y with specified radius
    def addAirPocket(self, x:int, y:int, radius:int, recursions=0, playerMade=False):
        radius=min(radius,max_airpocket_radius)
        if (not playerMade and x-radius<0) or (recursions>3 or x+radius>self.worldWidth or x-radius<0 or y<0 or y>self.worldHeight):
            return False
        if (not playerMade) and random.randint(1,10)==1:
            newAirPocket=AirPocket(x,y,radius,defaultZooms=self.defaultZooms,pocketType="C1")
        else:
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
        
        collidingLayer=self.getTerrainLayer((rect.width,rect.height),[rect.left,rect.top,1],hitboxes=True)
        self.drawNests((rect.width,rect.height),collidingLayer,[rect.left,rect.top,1],hitboxes=True)

        terrainMask = pygame.mask.from_surface(collidingLayer)

        return not (terrainMask.overlap(rectMask,(0,0)) ==None)
        #compare with rect
    
    # check for collision with rect, including enemies
    def laserCollideRect(self, rect:pygame.Rect):

        #new method

        #get terrain hitbox surface
        rectMask=pygame.Mask((rect.width,rect.height),fill=True)
        
        collidingLayer=self.getTerrainLayer((rect.width,rect.height),[rect.left,rect.top,1],hitboxes=True)
        self.drawNests((rect.width,rect.height),collidingLayer,[rect.left,rect.top,1],hitboxes=True)
        self.drawEnemies((rect.width,rect.height),collidingLayer,[rect.left,rect.top,1],hitboxes=True)

        terrainMask = pygame.mask.from_surface(collidingLayer)

        return not (terrainMask.overlap(rectMask,(0,0)) ==None)
        #compare with rect
    
    def enemiesCollideRect(self,rect:pygame.Rect):
        rectMask=pygame.Mask((rect.width,rect.height),fill=True)
        collidingLayer=pygame.Surface((rect.width,rect.height),flags=pygame.SRCALPHA)
        #collidingLayer.fill((0,0,0,0))
        self.drawEnemies((rect.width,rect.height),collidingLayer,[rect.left,rect.top,1],hitboxes=True)
        terrainMask = pygame.mask.from_surface(collidingLayer)
        return not (terrainMask.overlap(rectMask,(0,0)) ==None)

    def enemiesAttackCollideRect(self,rect:pygame.Rect):
        rectMask=pygame.Mask((rect.width,rect.height),fill=True)
        collidingLayer=pygame.Surface((rect.width,rect.height),flags=pygame.SRCALPHA)
        #collidingLayer.fill((0,0,0,0))
        self.drawEnemies((rect.width,rect.height),collidingLayer,[rect.left,rect.top,1],hitboxes=True)
        terrainMask = pygame.mask.from_surface(collidingLayer)
        return not (terrainMask.overlap(rectMask,(0,0)) ==None)

    def nestsCollideRect(self,rect:pygame.Rect):
        rectMask=pygame.Mask((rect.width,rect.height),fill=True)
        collidingLayer=pygame.Surface((rect.width,rect.height),flags=pygame.SRCALPHA)
        #collidingLayer.fill((0,0,0,0))
        self.drawNests((rect.width,rect.height),collidingLayer,[rect.left,rect.top,1],hitboxes=True)
        terrainMask = pygame.mask.from_surface(collidingLayer)
        return not (terrainMask.overlap(rectMask,(0,0)) ==None)
    
    def groundCollideRect(self,rect:pygame.Rect):
        rectMask=pygame.Mask((rect.width,rect.height),fill=True)
        collidingLayer=self.getTerrainLayer((rect.width,rect.height),[rect.left,rect.top,1],hitboxes=True)
        terrainMask = pygame.mask.from_surface(collidingLayer)
        return not (terrainMask.overlap(rectMask,(0,0)) ==None)

    #window_size is the size of the smaller window that should have things being drawn in. dimensions might be different versus surface, which is the surface actually being drawn on
    def drawNestGradients(self,window_size,surface:pygame.Surface,frame:list,hitboxes=False,offset_x=0,offset_y=0):
        left,top,zoom=frame
        w_width,w_height=window_size
        x,y,r=left+w_width/zoom/2,top+w_height/zoom/2,distance((0,0),(w_width,w_height))/2/zoom

        for nest in self.nests:
            if nest.close(x,y,r):
                nest.drawGradient(surface,frame,offset_x=offset_x,offset_y=offset_y)
            for enemy in nest.enemies:
                d=distance((x,y),(enemy.x,enemy.y))
                if d<r+enemy.r:
                    enemy.drawGradient(surface,frame,offset_x=offset_x,offset_y=offset_y)

    #window size is size of area where things should be good, not necessary the same as the size of the surface
    def drawNests(self,window_size,surface:pygame.Surface,frame:list,hitboxes=False,offset_x=0,offset_y=0):
        left,top,zoom=frame
        w_width,w_height=window_size
        x,y,r=left+w_width/zoom/2,top+w_height/zoom/2,distance((0,0),(w_width,w_height))/2/zoom

        for nest in self.nests:
            if nest.close(x,y,r):
                nest.draw(surface,frame,hitbox=hitboxes,offset_x=offset_x,offset_y=offset_y)

        #temporary
        #    #sunnest
        pygame.draw.rect(surface,(255,255,255),pygame.Rect(0+offset_x,(self.worldHeight-top)*zoom+offset_y,w_width,200))
    
    #draw enemies
    def drawEnemies(self,window_size,surface:pygame.Surface,frame:list,hitboxes=False,offset_x=0,offset_y=0):
        left,top,zoom=frame
        w_width,w_height=window_size
        x,y,r=left+w_width/zoom/2,top+w_height/zoom/2,distance((0,0),(w_width,w_height))/2/zoom

        for nest in self.nests:
            for i in range(len(nest.enemies)-1,-1,-1):
                enemy=nest.enemies[i]
                d=distance((x,y),(enemy.x,enemy.y))
                if d<r+enemy.r:
                    enemy.draw(surface,frame,hitbox=hitboxes,offset_x=offset_x,offset_y=offset_y)

    # return terrain layer
    def getTerrainLayer(self,window_size,frame:list,hitboxes=False,real_window_size=0,offset_x=0,offset_y=0):
        if real_window_size==0:
            real_window_size=window_size

        # get camera framing
        left,top,zoom=frame
        w_width,w_height=window_size

        # set up world layer
        layer=pygame.Surface(real_window_size, pygame.SRCALPHA)
        layer.fill((255,255,255,255))
        #if not hitboxes:
        if zoom in self.defaultZooms:
            if hitboxes:
                topChunk=math.floor(max(0,min(self.worldHeight,top))/hitbox_chunk_size)
                leftChunk=math.floor(max(0,min(self.worldWidth-hitbox_chunk_size,left))/hitbox_chunk_size)
                bottomChunk=math.ceil(max(0,min(self.worldHeight,top+w_height/zoom-hitbox_chunk_size))/hitbox_chunk_size)
                rightChunk=math.ceil(max(0,min(self.worldWidth-hitbox_chunk_size,left+w_width/zoom-hitbox_chunk_size))/hitbox_chunk_size)
                
                surfaces=self.airPocketsHitboxesSurfaces[zoom]
                
                # clear air pockets from base 
                for row in range(topChunk,bottomChunk+1,1):
                    for column in range(leftChunk,rightChunk+1,1):
                        realColumn=column
                        layer.blit(surfaces[row][realColumn], ((column*hitbox_chunk_size-left)*zoom+offset_x, (row*hitbox_chunk_size-top)*zoom+offset_y), special_flags=pygame.BLEND_RGBA_SUB)
                air_surface = pygame.Surface((w_width, w_height), pygame.SRCALPHA)
                pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,0,w_width,zoom*max(0,0-top)))
                #pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,min(w_height,(self.worldHeight-top)*zoom),w_width,w_height-min(w_height,(self.worldHeight-top)*zoom)))
                layer.blit(air_surface, (offset_x, offset_y), special_flags=pygame.BLEND_RGBA_SUB)
            else:
                topChunk=math.floor(max(0,min(self.worldHeight,top))/500)
                leftChunk=math.floor(max(0,min(self.worldWidth-500,left))/500)
                bottomChunk=math.ceil(max(0,min(self.worldHeight,top+w_height/zoom-500))/500)
                rightChunk=math.ceil(max(0,min(self.worldWidth-500,left+w_width/zoom-500))/500)
                
                surfaces=self.airPocketsSurfaces[zoom]
                # clear air pockets from base 
                for row in range(topChunk,bottomChunk+1,1):
                    for column in range(leftChunk,rightChunk+1,1):
                        realColumn=column
                        layer.blit(surfaces[row][realColumn], ((column*500-left)*zoom+offset_x, (row*500-top)*zoom+offset_y), special_flags=pygame.BLEND_RGBA_SUB)
                air_surface = pygame.Surface((w_width, w_height), pygame.SRCALPHA)
                pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,0,w_width,zoom*max(0,0-top)))
                #pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,min(w_height,(self.worldHeight-top)*zoom),w_width,w_height-min(w_height,(self.worldHeight-top)*zoom)))
                layer.blit(air_surface, (offset_x, offset_y), special_flags=pygame.BLEND_RGBA_SUB)
        else:
            ...
            """
            else:
                topChunk=math.floor(max(0,min(self.worldHeight,top-500))/500)
                leftChunk=math.floor(max(0,min(self.worldWidth-500,left))/500)
                bottomChunk=math.ceil(max(0,min(self.worldHeight,top+w_height/zoom))/500)
                rightChunk=math.ceil(max(0,min(self.worldWidth-500,left+w_width/zoom))/500)
                # clear air pockets from base 
                for row in range(topChunk,bottomChunk+1,1):
                    for column in range(leftChunk,rightChunk+1,1):
                        realColumn=column
                        if column<0:
                            realColumn+=round(self.worldWidth/500)
                        elif column>=self.worldWidth/500:
                            realColumn-=round(self.worldWidth/500)
                        layer.blit(pygame.transform.scale(self.airPocketsSurfaces[2][row][realColumn],(500*zoom,500*zoom)), ((column*500-left)*zoom+offset_x, (row*500-top)*zoom+offset_y), special_flags=pygame.BLEND_RGBA_SUB)
                air_surface = pygame.Surface((w_width, w_height), pygame.SRCALPHA)
                pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,0,w_width,zoom*max(0,0-top)))
                #pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,min(w_height,(self.worldHeight-top)*zoom),w_width,w_height-min(w_height,(self.worldHeight-top)*zoom)))
                layer.blit(air_surface, (offset_x, offset_y), special_flags=pygame.BLEND_RGBA_SUB)            
        else:
            air_surface = pygame.Surface((w_width, w_height), pygame.SRCALPHA)
            air_surface.fill((0, 0, 0, 0))
            x,y,r = rectToCircle(left,top,w_width/zoom,w_height/zoom)
            for airPocket in self.airPockets:
                if airPocket.close(x,y,r):
                    if airPocket.type=="Circle":
                        pygame.draw.circle(air_surface,(255,255,255,255),((zoom*(airPocket.x-left),zoom*(airPocket.y-top))),airPocket.r*zoom)
                    else:
                        air_surface.blit(airPocket.hitboxIMGs[zoom],((zoom*(airPocket.x-airPocket.r-left),zoom*(airPocket.y-airPocket.r-top))))
            # top/bottom of the world
            pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,0,w_width,zoom*max(0,0-top)))
            pygame.draw.rect(air_surface,(255, 255, 255, 255),pygame.Rect(0,min(w_height,(self.worldHeight+500-top)*zoom),w_width,w_height-min(w_height,(self.worldHeight-top)*zoom)))
            
            layer.blit(air_surface, (offset_x, offset_y), special_flags=pygame.BLEND_RGBA_SUB)
        """
        

        # return terrain layer
        return layer

# air pocket class
class AirPocket:

    # set up air pocket
    def __init__(self,x:int,y:int,radius:int,defaultZooms:list[float]=[0.1,2],pocketType="Circle"):
        self.x=x
        self.y=y
        self.r=radius
        self.type=pocketType
        self.top=self.y-self.r
        self.left=self.x-self.r
        self.fullResIMG=airIMGs[pocketType][random.randint(0,len(airIMGs[pocketType])-1)]
        self.IMGs={}
        for defaultZoom in defaultZooms:
            self.IMGs[defaultZoom]=pygame.transform.scale(self.fullResIMG,(2*self.r*defaultZoom,2*self.r*defaultZoom))
        
        if self.type!="Circle":
            self.fullResHitboxIMG=airHitboxIMGs[pocketType]
            self.hitboxIMGs={}
            for defaultZoom in defaultZooms:
                self.hitboxIMGs[defaultZoom]=pygame.transform.scale(self.fullResHitboxIMG,(2*self.r*defaultZoom,2*self.r*defaultZoom))

    # preliminary check if two circles are near each other
    def close(self,x:int,y:int,radius:int):
        if abs(self.x-x)>radius+self.r:
            return False
        if abs(self.y-y)>radius+self.r:
            return False
        return True