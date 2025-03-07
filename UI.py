import pygame,math
pygame.init()

chargeIcon = pygame.transform.scale(pygame.image.load(".ChargeIcon.png").convert_alpha(),(80,80))
lightGradient=pygame.image.load(".LightGradient.png").convert_alpha()

class ChargeDisplay():
    def __init__(self,worldHeight):
        self.rotation=0
        self.rotationGoal=1
        self.scale=100
        self.x=100
        self.y=100
        self.rotationSpeed=0
        self.playerCharge=0
        self.color=(0,0,0)
        self.worldHeight=worldHeight
        self.playerY=0

    def update(self,fps,color,playerCharge,playerY):
        frameLength=1000/fps
        self.playerY=max(0,playerY)
        chargeChange=playerCharge-self.playerCharge
        self.playerCharge=playerCharge
        p_r,p_g,p_b=color
        r,g,b=self.color
        if r!=p_r:
            r+=(p_r-r)/abs(p_r-r)*frameLength/16
        if g!=p_g:
            g+=(p_g-g)/abs(p_g-g)*frameLength/16
        if b!=p_b:
            b+=(p_b-b)/abs(p_b-b)*frameLength/16
        self.color=(min(255,r),min(255,g),min(255,b))

        if chargeChange>0:
            self.rotationGoal+=chargeChange/10
            self.scale=90
        elif chargeChange<0:
            #self.rotation=0
            #self.rotationGoal=0
            if self.scale<81:
                self.scale=60
        realGoal=math.floor(self.rotationGoal)
        goalSpeed=(realGoal-self.rotation)/300
        if goalSpeed>self.rotationSpeed:
            self.rotationSpeed+=1/1000
        if goalSpeed<self.rotationSpeed:
            self.rotationSpeed=goalSpeed
        self.rotation+=self.rotationSpeed*frameLength
        self.scale+=(80-self.scale)/300*frameLength
        if abs(self.rotation-realGoal)<0.001:
            self.rotation=0
            self.rotationGoal-=realGoal

    def draw(self,surface):
        transformedIcon=pygame.transform.rotate(pygame.transform.scale(chargeIcon,(self.scale,self.scale)),-self.rotation*(360))
        filter=pygame.Surface(transformedIcon.get_size(),flags=pygame.SRCALPHA)
        filter.fill(self.color)
        filter.blit(transformedIcon,(0,0),special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(filter,(self.x-filter.get_width()/2,self.y-filter.get_height()/2))
        pygame.draw.arc(surface,self.color,pygame.Rect(self.x-60,self.y-60,120,120),math.pi/2-2*math.pi*self.playerCharge/500,math.pi/2,10)
        pygame.draw.line(surface,self.color, (self.x+66,self.y-50),(self.x+80,self.y-50),2)
        pygame.draw.line(surface,self.color, (self.x+66,self.y+50),(self.x+80,self.y+50),2)
        pygame.draw.line(surface,self.color, (self.x+73,self.y-50),(self.x+73,self.y+50),2)
        
        pygame.draw.line(surface,self.color, (self.x+66,self.y-50+100*self.playerY/self.worldHeight),(self.x+80,self.y-50+100*self.playerY/self.worldHeight),6)