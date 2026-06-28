import pygame,math,os
pygame.init()

chargeIcon = pygame.transform.scale(pygame.image.load(os.path.join("assets","ChargeIcon.png")).convert_alpha(),(80,80))
lightGradient=pygame.image.load(os.path.join("assets","LightGradient.png")).convert_alpha()

chargeColors ={
    "white": (1,1,1),"blue":(0,0.25,1), "red":(1,0,0)
}

def drawRoundedLine(surface, color, start, end, thickness):
    pygame.draw.line(surface, color, start, end, thickness)
    pygame.draw.circle(surface, color, start, thickness/2)
    pygame.draw.circle(surface, color, end, thickness/2)

def drawSingleSideRoundedLine(surface, color, start, end, thickness):
    #thickness should be odd
    pygame.draw.line(surface, color, start, end, thickness)
    pygame.draw.circle(surface, color, end, thickness/2)

def polarToRect(r,angle):
    return r*math.cos(angle), r*math.sin(angle)

def getTrianglePoints(cx,cy,angle):
    point=polarToRect(58,angle-math.pi*0.5)
    pconcave=polarToRect(66,angle-math.pi*0.5)
    p2=polarToRect(67,angle-math.pi*0.53)
    p3=polarToRect(67,angle-math.pi*0.47)
    return ((point[0]+cx,point[1]+cy),(p2[0]+cx,p2[1]+cy),(pconcave[0]+cx,pconcave[1]+cy),(p3[0]+cx,p3[1]+cy))

class HealthBar():
    def __init__(self, maxHealth,thickness=5):
        self.lastTriggered=0
        self.maxHealth=maxHealth
        self.thickness=thickness
        self.scale=5/math.sqrt(maxHealth)
        self.width=self.maxHealth*self.scale+self.thickness
        self.surface=pygame.Surface((self.width,self.thickness))

    def trigger(self):
        self.lastTriggered=pygame.time.get_ticks()

    def draw(self, surface, color, coords, health,time=None):
        if time is None:
            time=pygame.time.get_ticks()
        opacity=max(0,255 - (time-self.lastTriggered-500)/2)
        if opacity>0:

            x,y=coords
            
            drawRoundedLine(self.surface, (0,0,0), (self.thickness/2,self.thickness/2), (self.width-self.thickness/2,self.thickness/2),self.thickness)
            drawRoundedLine(self.surface, color, (self.thickness/2,self.thickness/2), (self.thickness/2+self.scale*health,self.thickness/2),self.thickness)

            left = x - self.scale*self.maxHealth/2-self.thickness/2
            top = y - self.thickness/2
            self.surface.set_alpha(opacity)

            surface.blit(self.surface,(left,top))



class ChargeDisplay():
    def __init__(self,worldHeight):
        self.rotation=0
        self.rotationGoal=1
        self.scale=100

        #x/y are left/top
        self.x=40
        self.y=40
        self.rotationSpeed=0
        self.playerCharges={"white":0,"blue":0,"red":0}
        self.playerTotalCharge=0
        self.color=(0,0,0)
        self.worldHeight=worldHeight
        self.playerY=0

    def update(self,fps,playerCharges,playerY):
        frameLength=1000/fps

        totalCharge=sum(playerCharges.values())
        totalChargeChange=totalCharge-self.playerTotalCharge
        self.playerTotalCharge=totalCharge

        self.playerY=max(0,playerY)

        for color in playerCharges:

            chargeChange=playerCharges[color]-self.playerCharges[color]
            if abs(chargeChange) > 0:
                self.playerCharges[color]+=chargeChange/abs(chargeChange)*frameLength/16
        
        cw,cb,cr=self.playerCharges.values()
        r=cr+cw
        g=cw+cb/4
        b=cw+cb
        r=math.sqrt(max(0,min(r/500,1)))
        g=math.sqrt(max(0,min(g/500,1)))
        b=math.sqrt(max(0,min(b/500,1)))
        self.color=(r*255,g*255,b*255)

        if totalChargeChange>0:
            self.rotationGoal+=totalChargeChange/10
            self.scale=90
        elif totalChargeChange<0:
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

        pygame.draw.line(surface,self.color, (self.x+0,self.y+10),(self.x+14,self.y+10),2)
        pygame.draw.line(surface,self.color, (self.x+0,self.y+110),(self.x+14,self.y+110),2)
        pygame.draw.line(surface,self.color, (self.x+7,self.y+10),(self.x+7,self.y+110),2)

        pygame.draw.line(surface,self.color, (self.x+0,self.y+10+100*self.playerY/self.worldHeight),(self.x+14,self.y+10+100*self.playerY/self.worldHeight),6)

        filter.fill(self.color)
        filter.blit(transformedIcon,(0,0),special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(filter,(self.x+80-filter.get_width()/2,self.y+60-filter.get_height()/2))
        
        pygame.draw.arc(surface,self.color,pygame.Rect(self.x+20,self.y,120,120),math.pi/2-2*math.pi*self.playerTotalCharge/500,math.pi/2,11)


        #placeholder
        pygame.draw.polygon(surface,(255/2,0,0),getTrianglePoints(self.x+80,self.y+60,math.pi*0.16))
        pygame.draw.polygon(surface,(0,127/2,255/2),getTrianglePoints(self.x+80,self.y+60,math.pi*0.08))
        pygame.draw.polygon(surface,(255,255,255),getTrianglePoints(self.x+80,self.y+60,0))

        offset=0
        for color in self.playerCharges:
            fraction=self.playerCharges[color]/500
            if fraction>0:
                drawSingleSideRoundedLine(surface,(255*math.sqrt(fraction*chargeColors[color][0]),255*math.sqrt(fraction*chargeColors[color][1]),255*math.sqrt(fraction*chargeColors[color][2])),(self.x+146,self.y+10+offset), (self.x+146+max(6,100*fraction),self.y+10+offset),11)
            offset+=15