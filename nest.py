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

nestEffectHitboxes={}
nestHitboxes={}
nestIMGs = {}

for nestType, nStages, variants in [("White",3,[1]),("Blue",3,[1]),("Red",3,[1]),("Sun",10,[])]:
    IMGsets=[]
    hitboxes=[]
    for variant in variants:
        IMGset,hitbox = loadNestIMGSet(variant,nStages)
        IMGsets.append(IMGset)
        hitboxes.append(hitbox)
    nestIMGs[nestType]=IMGsets
    nestHitboxes[nestType]=hitboxes


NEST_COLORS = {"White":(255,255,255),"Red":(255,0,0),"Blue":(0,255,255),"Sun":(255,255,255)}

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
        self.enemyCap=5
        self.color=NEST_COLORS[nestType]
        
        self.stage=0
        self.maxStage=len(stageIMGs)-1

        self.resizedHitboxes={}
        self.resizedIMGs={}
        for zoom in defaultZooms:
            IMGs=[]
            for stageIMG in stageIMGs:
                IMGs.append(pygame.transform.scale(stageIMG,(size*zoom,size*zoom)))
            self.resizedIMGs[zoom]=IMGs
            self.resizedHitboxes[zoom]=pygame.transform.scale(hitbox,(size*zoom,size*zoom))

        self.resizedHitboxes[1]=pygame.transform.scale(hitbox,(size,size))
        
        self.maxHealth=self.y*1000/worldHeight
        match self.nestType:
            case "White":
                self.maxHealth*=1.1
                self.maxHealth+=10
            case "Blue":
                self.maxHealth+=100
            case "Red":
                self.maxHealth+=100
            case "Sun":
                self.maxHealth+=1000
        
        self.health=self.maxHealth

        self.maxCharge=self.maxHealth/3+100
        self.visualCharge=self.maxCharge
        self.charge=self.maxCharge
        self.chargeRate=self.maxCharge/10000
        self.charging=(0,0,0)
        match self.nestType:
            case "White":
                self.charging=(1,0,0)
            case "Blue":
                self.charging=(0,1,0)
            case "Red":
                self.charging=(0,0,1)

    def updateColor(self):
        cw,cb,cr=self.charging
        cw,cb,cr=cw*self.visualCharge,cb*self.visualCharge,cr*self.visualCharge
        r,g,b=0,0,0
        r+=cr+cw
        g+=cw+cb/4
        b+=cw+cb

        #500 is player's maxcharge
        r=math.sqrt(min(r/500,1))
        g=math.sqrt(min(g/500,1))
        b=math.sqrt(min(b/500,1))
        self.color=(r*255,g*255,b*255)
    
    def loseCharge(self,loss):
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

    def draw(self, surface, frame,hitbox=False):
        camX,camY,zoom=frame
        
        if hitbox:
            img=self.resizedHitboxes[zoom]
        else:
            img=self.resizedIMGs[zoom][self.stage]
        
        self.updateColor()
        filter=pygame.Surface(img.get_size(),flags=pygame.SRCALPHA)
        filter.fill(self.color)
        filter.blit(img,(0,0),special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(filter,((self.left-camX)*zoom,(self.top-camY)*zoom))

    def addEnemy(self,airPockets):
        if len(self.enemies)<self.enemyCap:
            #self.enemies.append(enemies.getEnemy(airPockets,self.nestType))
            ...

    def withinEffectRadius(self,x,y):
        if distance((x,y),(self.x,self.y)) < self.size*1.5:
            return True
        return False

    def applyDamageFromCircles(self,damageCircles):
        for circle in damageCircles:
            x,y,r=circle
            if self.close(x,y,0):
                self.dealDamage(r/2)
    
    def dealDamage(self,damage):
        self.health-=damage
        if self.health<0:
            self.health=0
        self.stage=self.maxStage-math.ceil(self.maxStage*self.health/self.maxHealth)

    def close(self,x:int,y:int,radius:int):
        if abs(self.x-x)>radius+self.size/2:
            return False
        if abs(self.y-y)>radius+self.size/2:
            return False
        return True