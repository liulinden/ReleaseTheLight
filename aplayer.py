import pygame,math,terrain

playerIMGs={}

IMGSet=[]
for i in range(5):
    IMGSet.append(pygame.image.load(".PlayerIdle"+str(i+1)+".png").convert_alpha())
playerIMGs["Idle"]=IMGSet

IMGSet=[]
for i in range(5):
    IMGSet.append(pygame.image.load(".PlayerRun"+str(i+1)+".png").convert_alpha())
playerIMGs["Run"]=IMGSet

IMGSet=[]
for i in range(0):
    IMGSet.append(pygame.image.load(".PlayerBackpedal"+str(i+1)+".png").convert_alpha())
playerIMGs["Backpedal"]=IMGSet

playerIMGs["Falling"]=[pygame.image.load(".PlayerFalling.png").convert_alpha()]
playerIMGs["Jumping"]=[pygame.image.load(".PlayerJumping.png").convert_alpha()]
#playerIMGs["Sliding"]=[pygame.image.load(".PlayerSliding.png").convert_alpha()]
#playerIMGs["arm"]=IMGSet.append([pygame.image.load(".PlayerArm").convert_alpha()])
SPRITE_WIDTH=40
SPRITE_HEIGHT=40
ARM_PIVOT_X =10
ARM_PIVOT_Y=20
animationLengths = {"Idle":5,"Run":5,"Falling":1,"Jumping":1}
animationFPS=20


class Player:

    def __init__(self,defaultZooms, x,y,dimensions=[10,30]):
        self.x=x
        self.y=y
        self.xSpeed=0
        self.ySpeed=-1
        self.width,self.height=dimensions
        self.rect=pygame.Rect(self.x-self.width/2,self.y-self.height/2,self.width,self.height)
        self.onGround=False
        self.color=(255,255,255)
        self.defaultZooms=defaultZooms
        self.facing = "Right"
        self.animationTimer=0
        self.animationType="Idle"
        self.animationFrame=0

        self.playerIMGs = {}
        for zoom in self.defaultZooms:
            zoomIMGSets={}
            for direction in ["Left","Right"]:
                directionSet={}
                
                for animationType in playerIMGs:
                    directionSet[animationType]=[]
                    for img in playerIMGs[animationType]:
                        resizedIMG=pygame.transform.scale(img,(SPRITE_WIDTH*zoom,SPRITE_HEIGHT*zoom))
                        if direction=="Left":
                            resizedIMG=pygame.transform.flip(resizedIMG,True,False)
                        directionSet[animationType].append(resizedIMG)
                zoomIMGSets[direction]=directionSet
            self.playerIMGs[zoom]=zoomIMGSets

                
    def updateCostume(self,frameLength):
        self.animationTimer=(self.animationTimer+frameLength)%(1000/animationFPS*(max(1,2*animationLengths[self.animationType]-2)))

        previousAnimationType=self.animationType

        if self.xSpeed>0:
            self.facing="Right"
        elif self.xSpeed<0:
            self.facing="Left"

        if not self.onGround:
            if self.ySpeed>0:
                self.animationType="Falling"
            else:
                self.animationType="Jumping"
        else:
            if abs(self.xSpeed)>0.1:
                self.animationType="Run"
            else:
                self.animationType="Idle"
            

        

        if self.animationType!=previousAnimationType:
            self.animationTimer=0
        
        animationLength=animationLengths[self.animationType]
        if animationLength==1:
            self.animationFrame=0
        else:
            self.animationFrame=math.floor(self.animationTimer/(1000/animationFPS))
            if self.animationFrame>animationLength-1:
                self.animationFrame=2*animationLength-2-self.animationFrame


    def updateRect(self):
        self.rect.x,self.rect.y=self.x-self.width/2,self.y-self.height/2

    def tick(self,frameLength,cTerrain,keysDown):
        self.ySpeed=min(0.4,self.ySpeed+0.0015*frameLength)
        
        if keysDown[pygame.K_w] and self.onGround:
            self.ySpeed = -0.4
        
        if keysDown[pygame.K_a]:
            if self.onGround:
                self.xSpeed -= 0.005*frameLength
            else:
                self.xSpeed -= 0.0015*frameLength
        if keysDown[pygame.K_d]:
            if self.onGround:
                self.xSpeed += 0.005*frameLength
            else:
                self.xSpeed += 0.0015*frameLength
        
        if self.onGround:
            self.xSpeed*=0.98**frameLength
        else:
            self.xSpeed*=0.993**frameLength

        self.moveVertical(frameLength,cTerrain)
        self.moveHorizontal(frameLength,cTerrain)

        self.updateCostume(frameLength)
        
    
    def moveHorizontal(self, frameLength,cTerrain):

        #TODO - add slope platforming

        self.x+=frameLength*self.xSpeed
        self.updateRect()
        if self.collidingWithTerrain(cTerrain):
            slopeTolerance=math.ceil(5*abs(frameLength*self.xSpeed))
            for i in range(slopeTolerance):
                self.y-=1
                self.updateRect()
                if not self.collidingWithTerrain(cTerrain):
                    if self.xSpeed>0:
                        self.xSpeed-=self.xSpeed*i/slopeTolerance
                    else:
                        self.xSpeed-=self.xSpeed*i/slopeTolerance
                    return
            self.y+=slopeTolerance
            backs=math.ceil(abs(frameLength*self.xSpeed/1))
            for i in range(backs):
                self.x-=frameLength*self.xSpeed/backs
                self.updateRect()
                if not self.collidingWithTerrain(cTerrain):
                    break
            self.xSpeed=0
    

    def moveVertical(self, frameLength,cTerrain):
        self.onGround=False
        self.y+=frameLength*self.ySpeed
        self.updateRect()
        if self.collidingWithTerrain(cTerrain):
            if self.ySpeed>0:
                self.onGround=True
            if self.ySpeed<0:
                slopeTolerance=math.ceil(abs(0.5*frameLength*self.ySpeed))
                for i in range(slopeTolerance):
                    self.x-=1
                    self.updateRect()
                    if not self.collidingWithTerrain(cTerrain):
                        return
                self.x+=slopeTolerance
                for i in range(slopeTolerance):
                    self.x+=1
                    self.updateRect()
                    if not self.collidingWithTerrain(cTerrain):
                        return
                self.x-=slopeTolerance
            backs=math.ceil(abs(frameLength*self.ySpeed/1))
            for i in range(backs):
                self.y-=frameLength*self.ySpeed/backs
                self.updateRect()
                if not self.collidingWithTerrain(cTerrain):
                    break
            self.ySpeed=0
    
    def draw(self, surface, frame,hitboxes=False):
        camX,camY,zoom=frame
        if hitboxes:
            self.updateRect()
            pygame.draw.rect(surface,self.color,pygame.Rect((self.rect.left-camX)*zoom,(self.rect.top-camY)*zoom,self.width*zoom,self.height*zoom))
        else:
            playerSurface=pygame.Surface((SPRITE_WIDTH*zoom,SPRITE_HEIGHT*zoom),flags=pygame.SRCALPHA)
            playerSurface.fill((self.color[0],self.color[1],self.color[2],255))
            playerSurface.blit(self.playerIMGs[zoom][self.facing][self.animationType][self.animationFrame],(0,0),special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(playerSurface,((self.x-SPRITE_WIDTH/2-camX)*zoom,(self.rect.bottom-SPRITE_HEIGHT-camY)*zoom))


    def collidingWithTerrain(self, cTerrain):
        return cTerrain.collideRect(self.rect)
