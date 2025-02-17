import pygame
def getEnemy(airPockets, nestType, nestX, nestY):
    for airPocket in airPockets:
        ...
    return Enemy(nestX,nestY)


class Enemy:
    def __init__(self,x,y):
        self.rect=pygame.Rect
        self.x=x
        self.y=y
        self.xSpeed=0
        self.ySpeed=-1
        self.width,self.height=20,20
        self.rect=pygame.Rect(self.x-self.width/2,self.y-self.height/2,self.width,self.height)
        self.color = (255,255,255)
        
    def updateRect(self):
        self.rect.x,self.rect.y=self.x-self.width/2,self.y-self.height/2

    def draw(self, surface, frame,hitboxes=False):
        hitboxes=True
        camX,camY,zoom=frame

        if hitboxes:
            self.updateRect()
            pygame.draw.rect(surface,self.color,pygame.Rect((self.rect.left-camX)*zoom,(self.rect.top-camY)*zoom,self.width*zoom,self.height*zoom))