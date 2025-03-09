import pygame, random,math,enemies

def loadNestIMGSet(id,stages):
    IMGs=[]
    for i in range(stages):
        IMGs.append(pygame.image.load(".Nest"+str(id)+"_"+str(i+1)+".png").convert_alpha())
    return IMGs, pygame.image.load(".Nest"+str(id)+"Hitbox.png").convert_alpha()

def distance(coord1:int,coord2:int):
    x1,y1=coord1
    x2,y2=coord2
    return math.sqrt((x1-x2)**2+(y1-y2)**2)

lightGradient=pygame.image.load(".LightGradient.png").convert_alpha()

nestEffectHitboxes={}
nestHitboxes={}
nestIMGs = {}

for nestType, nStages, variants in [("White",3,[1,2,3,4]),("Blue",4,[5,6]),("Red",4,[5,6]),("Sun",10,[])]:
    IMGsets=[]
    hitboxes=[]
    for variant in variants:
        IMGset,hitbox = loadNestIMGSet(variant,nStages)
        IMGsets.append(IMGset)
        hitboxes.append(hitbox)
    nestIMGs[nestType]=IMGsets
    nestHitboxes[nestType]=hitboxes


class Nest:
    def __init__(self,defaultZooms,worldHeight,nestType,x,y,size):
        self.x=x
        self.y=y
        self.left=x-size/2
        self.top=y-size/2
        self.nestType=nestType
        selection=nestIMGs[nestType]
        id=random.randint(0,len(selection)-1)
        stageIMGs=selection[id]
        hitbox=nestHitboxes[nestType][id]
        self.size=size
        self.enemies=[]
        self.basicEnemyCap=1
        self.totalEnemyCap=8
        self.color=(255,255,255)
        self.glow=0
        self.stage=0
        self.maxStage=len(stageIMGs)-1

        self.resizedHitboxes={}
        self.resizedGradients={}
        self.resizedIMGs={}
        for zoom in defaultZooms:
            IMGs=[]
            for stageIMG in stageIMGs:
                IMGs.append(pygame.transform.scale(stageIMG,(size*zoom,size*zoom)))
            self.resizedIMGs[zoom]=IMGs
            self.resizedHitboxes[zoom]=pygame.transform.scale(hitbox,(size*zoom,size*zoom))
            self.resizedGradients[zoom]=pygame.transform.scale(lightGradient,(size*zoom,size*zoom))

        self.resizedHitboxes[1]=pygame.transform.scale(hitbox,(size,size))
        
        self.maxHealth=self.y*500/worldHeight
        if self.nestType== "White":
            self.maxHealth*=1.1
            self.maxHealth+=10
        elif self.nestType== "Blue":
            self.maxHealth+=100
        elif self.nestType=="Red":
            self.maxHealth+=100
        elif self.nestType=="Sun":
            self.maxHealth+=1000
        
        self.health=self.maxHealth

        self.maxCharge=self.maxHealth/3+100
        self.visualCharge=self.maxCharge
        self.charge=self.maxCharge*0.5
        self.chargeRate=self.maxCharge/10000
        self.charging=(0,0,0)
        if self.nestType=="White":
            self.charging=(1,0,0)
        elif self.nestType== "Blue":
            self.charging=(0,1,0)
        elif self.nestType== "Red":
            self.charging=(0,0,1)

    def getRect(self):
        return pygame.Rect(self.left,self.top,self.size,self.size)

    def updateColor(self):
        cw,cb,cr=self.charging
        cw,cb,cr=cw*self.visualCharge,cb*self.visualCharge,cr*self.visualCharge
        r,g,b=0,0,0
        r+=cr+cw
        g+=cw+cb/4
        b+=cw+cb

        #500 is player's maxcharge
        r=(min(r/500,1))**0.3
        g=(min(g/500,1))**0.3
        b=(min(b/500,1))**0.3
        self.color=(r*255,g*255,b*255)
    
    def loseCharge(self,loss):
        self.glow=255
        self.charge-=loss
        if self.charge<0:
            self.charge=0
            #self destruct animation and self-removal?
            ...

    def updateVisuals(self,frameLength):
        if self.charge==0 and self.visualCharge!=0:
            self.visualCharge-=frameLength/10
            if self.visualCharge<0:
                self.visualCharge=0
        self.glow+=((self.stage/self.maxStage*self.visualCharge/self.maxCharge*150)-self.glow)/1500*frameLength

    def drawGradient(self,surface,frame,offset_x=0,offset_y=0):
        camX,camY,zoom=frame
        img=self.resizedGradients[zoom]
        #return
        if self.glow>0:
            filter=pygame.Surface(img.get_size(),flags=pygame.SRCALPHA)
            filter.fill((self.color[0],self.color[1],self.color[2],self.glow))
            filter.blit(img,(0,0),special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(filter,((self.left-camX)*zoom+offset_x,(self.top-camY)*zoom+offset_y))
    
    def draw(self, surface, frame,hitbox=False,offset_x=0,offset_y=0):
        camX,camY,zoom=frame
        
        if hitbox:
            img=self.resizedHitboxes[zoom]
        else:
            img=self.resizedIMGs[zoom][self.stage]
        
        self.updateColor()
        #if not hitboxes:
        #    filter=pygame.Surface(img.get_size(),flags=pygame.SRCALPHA)
        #    filter.fill((self.color[0],self.color[1],self.color[2],self.glow))
        #    filter.blit(img,(0,0),special_flags=pygame.BLEND_RGBA_MULT)
        #    surface.blit(filter,((self.left-camX)*zoom,(self.top-camY)*zoom))

        filter=pygame.Surface(img.get_size(),flags=pygame.SRCALPHA)
        filter.fill(self.color)
        filter.blit(img,(0,0),special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(filter,((self.left-camX)*zoom+offset_x,(self.top-camY)*zoom+offset_y))

    def addEnemy(self,cTerrain,player):
        if len(self.enemies)<self.basicEnemyCap:
            newEnemy=enemies.getEnemy(cTerrain,player,self.nestType,self.color,self.maxHealth,self.x,self.y,self.size)
            if newEnemy:
                self.glow=200
                self.enemies.append(newEnemy)

    def withinEffectRadius(self,x,y):
        if distance((x,y),(self.x,self.y)) < self.size*1.5:
            return True
        return False

    def applyDamageFromCircles(self,cTerrain,player):
        newParticles=[]
        if self.health>0:
            for circle in cTerrain.playerDamageCircles:
                x,y,r=circle
                if self.close(x,y,0):
                    self.dealDamage(r/2,cTerrain,player)
                    newParticles.append([x,y])
        return newParticles
    
    def dealDamage(self,damage,cTerrain,player):
        self.glow=200
        self.health-=damage
        if self.health<0:
            self.health=0
            for enemy in self.enemies:
                enemy.spawnParticles(cTerrain)
            self.enemies=[]
        elif len(self.enemies)<self.totalEnemyCap and random.randint(1,4)==1:
            newEnemy=enemies.getEnemy(cTerrain,player,self.nestType,self.color,self.maxHealth,self.x,self.y,self.size)
            if newEnemy:
                self.enemies.append(newEnemy)
        self.updateStage()

    def updateStage(self):
        self.stage=self.maxStage-math.ceil((self.maxStage-1)*self.health/self.maxHealth)
        self.basicEnemyCap=math.floor(self.stage*1.5)

    def close(self,x:int,y:int,radius:int):
        if abs(self.x-x)>radius+self.size/2:
            return False
        if abs(self.y-y)>radius+self.size/2:
            return False
        return True