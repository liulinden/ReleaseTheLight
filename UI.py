import pygame,math,os

from asset_manager import get_asset


chargeIcon=None
lightGradient=None
chargeTuples=None

def init():
    global chargeIcon,lightGradient,chargeColors

    chargeIcon = pygame.transform.scale(get_asset("ChargeIcon"),(80,80))
    lightGradient=get_asset("LightGradient")

from util import chargesToColor
pygame.init()


chargeTuples ={
    "white": (1,0,0),"blue":(0,1,0), "red":(0,0,1)
}

def drawRoundedLine(surface, color, start, end, thickness):
    pygame.draw.line(surface, color, start, end, thickness)
    pygame.draw.circle(surface, color, start, thickness/2)
    pygame.draw.circle(surface, color, end, thickness/2)

def drawSingleSideRoundedLine(surface, color, start, end, thickness):
    #thickness should be odd
    pygame.draw.line(surface, color, start, end, thickness)
    pygame.draw.circle(surface, color, end, thickness/2)

def drawLineFromCenter(surface, color, center,angle,r1,r2,thickness):
    cx,cy=center
    x1,y1=polarToRect(r1,-angle)
    x2,y2=polarToRect(r2,-angle)
    pygame.draw.line(surface,color,(x1+cx,y1+cy),(x2+cx,y2+cy),thickness)

def polarToRect(r,angle):
    return r*math.cos(angle), r*math.sin(angle)

def getTrianglePoints(cx,cy,angle):
    point=polarToRect(54,angle-math.pi*0.5)
    p2=polarToRect(67,angle-math.pi*0.55)
    p3=polarToRect(67,angle-math.pi*0.45)
    return ((point[0]+cx,point[1]+cy),(p2[0]+cx,p2[1]+cy),(p3[0]+cx,p3[1]+cy))

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

            chargeChange=int(playerCharges[color])-self.playerCharges[color]
            if abs(chargeChange) > 0:
                if abs(chargeChange) < frameLength/16:
                    self.playerCharges[color]+=chargeChange
                else:
                    self.playerCharges[color]+=chargeChange/abs(chargeChange)*frameLength/16
        
        cw,cb,cr=self.playerCharges.values()
        self.color=chargesToColor(cw,cb,cr,500)

        if totalChargeChange>0.1:
            self.rotationGoal+=totalChargeChange/10
            self.scale=90
        elif totalChargeChange<-0.1:
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
        
        #different filter than above
        mixedColor= chargesToColor(self.playerCharges["white"],self.playerCharges["blue"],self.playerCharges["red"],500)
        filterColor=mixedColor

        pygame.draw.line(surface,filterColor, (self.x+0,self.y+20),(self.x+14,self.y+20),2)
        pygame.draw.line(surface,filterColor, (self.x+0,self.y+140),(self.x+14,self.y+140),2)
        pygame.draw.line(surface,filterColor, (self.x+7,self.y+20),(self.x+7,self.y+140),2)

        pygame.draw.line(surface,filterColor, (self.x+0,self.y+20+120*self.playerY/self.worldHeight),(self.x+14,self.y+20+120*self.playerY/self.worldHeight),6)

        filter.fill(self.color)
        filter.blit(transformedIcon,(0,0),special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(filter,(self.x+100-filter.get_width()/2,self.y+80-filter.get_height()/2))
        
        arcAngle=math.pi/2
        for color in self.playerCharges:
            if self.playerCharges[color]>0:
                newAngle=arcAngle-2*math.pi*(self.playerCharges[color])/500
                def getChannel(index): return chargeTuples[color][index]*self.playerCharges[color]
                pygame.draw.arc(surface,chargesToColor(getChannel(0),getChannel(1),getChannel(2)),pygame.Rect(self.x+40,self.y+20,120,120),newAngle,arcAngle,10)
                arcAngle=newAngle
        
        #draw arc outline
        thickness=3
        pygame.draw.arc(surface,self.color,pygame.Rect(self.x+40-thickness,self.y+20-thickness,120+2*thickness,120+2*thickness),newAngle,math.pi/2,thickness)
        pygame.draw.arc(surface,self.color,pygame.Rect(self.x+40+10,self.y+20+10,120-20,120-20),newAngle,math.pi/2,thickness)
        drawLineFromCenter(surface, self.color, (self.x+100,self.y+80),math.pi/2, 60-10-thickness,60+thickness,thickness)
        drawLineFromCenter(surface, self.color, (self.x+100,self.y+80),newAngle, 60-10-thickness,60+thickness,thickness)

        pygame.draw.polygon(surface,(255/2,0,0),getTrianglePoints(self.x+100,self.y+80,math.pi*0.16))
        pygame.draw.polygon(surface,(0,0,0),getTrianglePoints(self.x+100,self.y+80,math.pi*0.16),2)


        pygame.draw.polygon(surface,(0,127/4,255/2),getTrianglePoints(self.x+100,self.y+80,math.pi*0.08))
        pygame.draw.polygon(surface,(0,0,0),getTrianglePoints(self.x+100,self.y+80,math.pi*0.08),2)

        pygame.draw.circle(surface, (0,0,0), (self.x+100,self.y+80), 67, 5)

        pygame.draw.polygon(surface,mixedColor,getTrianglePoints(self.x+100,self.y+80,0))
        pygame.draw.polygon(surface,(0,0,0),getTrianglePoints(self.x+100,self.y+80,0),3)

        pygame.draw.circle(surface, filterColor, (self.x+100,self.y+80), 67, 3)