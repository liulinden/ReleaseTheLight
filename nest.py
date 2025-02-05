import pygame, random,math

def loadNestIMGSet(nestType,id,stages):
    IMGs=[]
    for i in range(stages):
        IMGs.append(pygame.image.load(".Nest"+nestType+str(id)+"_"+str(i+1)+".png"))
    return IMGs, pygame.image.load(".Nest"+nestType+str(id)+"Hitbox.png")

def distance(coord1:int,coord2:int):
    x1,y1=coord1
    x2,y2=coord2
    return math.sqrt((x1-x2)**2+(y1-y2)**2)

nestEffectHitboxes={}
nestHitboxes={}
nestIMGs = {}

for nestType, nStages, nVariants in [("White",3,1),("Blue",5,0),("Red",5,0),("Sun",10,0)]:
    IMGsets=[]
    hitboxes=[]
    for i in range(nVariants):
        IMGset,hitbox = loadNestIMGSet(nestType,i+1,nStages)
        IMGsets.append(IMGset)
        hitboxes.append(hitbox)
    nestIMGs[nestType]=IMGsets
    nestHitboxes[nestType]=hitboxes


NEST_COLORS = {"White":(255,255,255),"Red":[255,0,0],"Blue":[0,255,255]}

class Nest:
    def __init__(self,defaultZooms,nestType,x,y,size):
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
        self.color=NEST_COLORS[nestType]
        
        self.stage=2
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
        
        self.maxHealth=self.y/10
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
    
    def draw(self, surface, frame, hitbox=False):
        camX,camY,zoom=frame
        if hitbox:
            surface.blit(self.resizedHitboxes[zoom],((self.left-camX)*zoom,(self.top-camY)*zoom))
        else:
            surface.blit(self.resizedIMGs[zoom][self.stage],((self.left-camX)*zoom,(self.top-camY)*zoom))

    def withinEffectRadius(self,x,y):
        if distance((x,y),(self.x,self.y)) < self.size:
            return True
        return False

    def close(self,x:int,y:int,radius:int):
        if abs(self.x-x)>radius+self.size/2:
            return False
        if abs(self.y-y)>radius+self.size/2:
            return False
        return True