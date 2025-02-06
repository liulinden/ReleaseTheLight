import pygame,math,terrain
class Player:

    def __init__(self,x,y,dimensions=[20,30]):
        self.x=x
        self.y=y
        self.xSpeed=0
        self.ySpeed=-1
        self.width,self.height=dimensions
        self.rect=pygame.Rect(self.x-self.width/2,self.y-self.height/2,self.width,self.height)
        self.onGround=False
        self.color=(255,0,0)

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
        
    
    def moveHorizontal(self, frameLength,cTerrain):

        #TODO - add slope platforming

        self.x+=frameLength*self.xSpeed
        self.updateRect()
        if self.collidingWithTerrain(cTerrain):
            slopeTolerance=math.ceil(2*abs(frameLength*self.xSpeed))
            for i in range(slopeTolerance):
                self.y-=1
                self.updateRect()
                if not self.collidingWithTerrain(cTerrain):
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
    
    def draw(self, surface, frame):
        camX,camY,zoom=frame
        self.updateRect()
        pygame.draw.rect(surface,self.color,pygame.Rect((self.rect.left-camX)*zoom,(self.rect.top-camY)*zoom,self.width*zoom,self.height*zoom))

    def collidingWithTerrain(self, cTerrain):
        return cTerrain.collideRect(self.rect)
