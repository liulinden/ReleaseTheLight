import pygame
class Player:

    def __init__(self,x,y,dimensions=[30,40]):
        self.x=x
        self.y=y
        self.xSpeed=0
        self.ySpeed=-5
        self.width,self.height=dimensions
        self.rect=pygame.Rect(self.x,self.y,self.width,self.height)
    
    def updateRect(self):
        self.rect.x,self.rect.y=self.x,self.y

    def tick(self,frameLength,cTerrain):
        self.ySpeed+=0.05*frameLength
        
        self.moveHorizontal(frameLength,cTerrain)
        self.moveVertical(frameLength,cTerrain)
        print(self.ySpeed)
    
    def moveHorizontal(self, frameLength,cTerrain):
        self.x+=frameLength*self.xSpeed
        self.updateRect()
        if self.collidingWithTerrain(cTerrain):
            self.x-=frameLength*self.xSpeed
            self.xSpeed=0

    def moveVertical(self, frameLength,cTerrain):
        self.y+=frameLength*self.ySpeed
        self.updateRect()
        if self.collidingWithTerrain(cTerrain):
            self.y-=frameLength*self.ySpeed
            self.ySpeed=0
    
    def draw(self, surface, frame):
        camX,camY,zoom=frame
        self.updateRect()
        pygame.draw.rect(surface,(255,255,255),pygame.Rect((self.x-camX)*zoom,(self.y-camY)*zoom,self.width*zoom,self.height*zoom))

    def collidingWithTerrain(self, cTerrain):
        return cTerrain.collideRect(self.rect)
