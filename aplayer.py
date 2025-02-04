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

    def updateRect(self):
        self.rect.x,self.rect.y=self.x-self.width/2,self.y-self.height/2

    def tick(self,frameLength,cTerrain,keysDown):
        self.ySpeed=min(1,self.ySpeed+0.002*frameLength)
        print(self.ySpeed)
        
        if keysDown[pygame.K_w] and self.onGround:
            self.ySpeed = -0.5
        
        if keysDown[pygame.K_a]:
            if self.onGround:
                self.xSpeed -= 0.005*frameLength
            else:
                self.xSpeed -= 0.0005*frameLength
        if keysDown[pygame.K_d]:
            if self.onGround:
                self.xSpeed += 0.005*frameLength
            else:
                self.xSpeed += 0.0005*frameLength
        
        if self.onGround:
            self.xSpeed*=0.99**frameLength
        else:
            self.xSpeed*=0.999**frameLength

        self.moveHorizontal(frameLength,cTerrain)
        self.moveVertical(frameLength,cTerrain)
    
    def moveHorizontal(self, frameLength,cTerrain):

        #TODO - add slope platforming

        self.x+=frameLength*self.xSpeed
        self.updateRect()
        if self.collidingWithTerrain(cTerrain):
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
            backs=math.ceil(abs(frameLength*self.ySpeed/1))
            for i in range(backs):
                self.y-=frameLength*self.ySpeed/backs
                self.updateRect()
                if not self.collidingWithTerrain(cTerrain):
                    break
            if self.ySpeed>0:
                self.onGround=True
            self.ySpeed=0
    
    def draw(self, surface, frame):
        camX,camY,zoom=frame
        self.updateRect()
        pygame.draw.rect(surface,(255,255,255),pygame.Rect((self.rect.left-camX)*zoom,(self.rect.top-camY)*zoom,self.width*zoom,self.height*zoom))

    def collidingWithTerrain(self, cTerrain):
        return cTerrain.collideRect(self.rect)
