import pygame,math
class Player:

    def __init__(self,x,y,dimensions=[30,40]):
        self.x=x
        self.y=y
        self.xSpeed=0
        self.ySpeed=-1
        self.width,self.height=dimensions
        self.rect=pygame.Rect(self.x,self.y,self.width,self.height)
    
    def updateRect(self):
        self.rect.x,self.rect.y=self.x,self.y

    def tick(self,frameLength,cTerrain,keysDown):
        self.ySpeed+=0.01*frameLength
        
        if keysDown[pygame.K_w]:
            self.ySpeed = -1

        self.moveHorizontal(frameLength,cTerrain)
        self.moveVertical(frameLength,cTerrain)
    
    def moveHorizontal(self, frameLength,cTerrain):
        self.x+=frameLength*self.xSpeed
        self.updateRect()
        if self.collidingWithTerrain(cTerrain):
            backs=math.ceil(frameLength*self.xSpeed/1)
            for i in range(backs):
                self.x-=frameLength*self.xSpeed/backs
                self.updateRect()
                if not self.collidingWithTerrain(cTerrain):
                    break
            self.xSpeed=0
    

    def moveVertical(self, frameLength,cTerrain):
        self.y+=frameLength*self.ySpeed
        self.updateRect()
        if self.collidingWithTerrain(cTerrain):
            backs=math.ceil(frameLength*self.ySpeed/1)
            for i in range(backs):
                self.y-=frameLength*self.ySpeed/backs
                self.updateRect()
                if not self.collidingWithTerrain(cTerrain):
                    break
            self.ySpeed=0
    
    def draw(self, surface, frame):
        camX,camY,zoom=frame
        self.updateRect()
        pygame.draw.rect(surface,(255,255,255),pygame.Rect((self.x-camX)*zoom,(self.y-camY)*zoom,self.width*zoom,self.height*zoom))

    def collidingWithTerrain(self, cTerrain):
        return cTerrain.collideRect(self.rect)
