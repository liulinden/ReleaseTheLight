import pygame,math,random

class Laser:
    def __init__(self):
        self.angle=0
        self.length=0
        self.startX=0
        self.startY=0
        self.digSpeed=1
        self.thickness=5
        self.laserPoints=[]
        self.laserPoints2=[]
        self.sinWaveOffset=0
        self.timer=0
        self.laserTime=400
        self.laserWidth=10
        self.maxLength=400
        self.collision=[]
        self.damageFrame=False

    def getLaserPoints(self, n_points):
        n_points=max(3,1+round(self.length/40))
        spacing=self.length/(n_points-1)
        points = []
        points.append(0)
        for i in range(n_points-2):
            points.append(spacing*i+random.random()*spacing)
        points.append(self.length)
        for i in range(n_points-2):
            points.append(spacing*(n_points-3-i)+random.random()*spacing)
        return points

    def getAngleLength(self,terrain,targetX,targetY):

        dx=targetX-self.startX
        dy=targetY-self.startY
        angle=math.atan2(dy,dx)

        length=math.sqrt(dx**2+dy**2)
        dx*=self.laserWidth/2/length
        dy*=self.laserWidth/2/length

        self.collision=[]

        rect=pygame.Rect(self.startX-self.laserWidth/2,self.startY-self.laserWidth/2,self.laserWidth,self.laserWidth)
        for i in range(math.ceil(self.maxLength/(self.laserWidth/2))):
            if terrain.collideRect(rect):
                self.collision=[rect.center]
                return angle,i*self.laserWidth/2
            rect.x+=dx
            rect.y+=dy
        return angle,self.maxLength
        #return math.atan2(dy,dx),math.sqrt(dx**2+dy**2)*5
    
    def updateLaser(self,terrain,startX,startY,targetX,targetY,laserCooldown=0):
        self.startX,self.startY=startX,startY
        self.angle,self.length=self.getAngleLength(terrain,targetX,targetY)
        if laserCooldown!=0:
            self.laserTime=laserCooldown

    def tick(self,frameLength):
        self.sinWaveOffset+=frameLength/100
        self.timer-=frameLength
        self.damageFrame=False
        if self.timer<=0:
            self.timer=self.laserTime
            self.laserPoints=self.getLaserPoints(6)
            self.laserPoints2=self.getLaserPoints(6)
            self.damageFrame=True
    
    def draw(self, surface, frame,color, hitboxes=False,offset_x=0,offset_y=0):
        left,top,zoom=frame
        if hitboxes:
            dx=self.laserWidth/2*math.cos(self.angle)
            dy=self.laserWidth/2*math.sin(self.angle)
            rect=pygame.Rect(self.startX-self.laserWidth/2,self.startY-self.laserWidth/2,self.laserWidth,self.laserWidth)
            for i in range(round(self.length*2/self.laserWidth+1)):
                pygame.draw.rect(surface,color,pygame.Rect((rect.x-left)*zoom+offset_x,(rect.y-top)*zoom+offset_y,rect.width*zoom,rect.width*zoom))
                rect.x+=dx
                rect.y+=dy
        else:
            for laserPart in [self.laserPoints,self.laserPoints2]:
                polygonPoints=[]
                for point in laserPart:
                    if point <= self.length:
                        waveHeight=self.thickness*math.sin((point+self.sinWaveOffset)*1.5)*(0.5+self.timer/self.laserTime)
                        if laserPart.index(point)%(len(laserPart)/2)==0:
                            x,y=point*math.cos(self.angle),point*math.sin(self.angle)
                        else:
                            x,y=point*math.cos(self.angle)+waveHeight*math.sin(self.angle),point*math.sin(self.angle)-waveHeight*math.cos(self.angle)
                        polygonPoints.append(((x+self.startX-left)*zoom+offset_x,(y+self.startY-top)*zoom+offset_y))
                    else:
                        self.laserPoints=self.getLaserPoints(6)
                        self.laserPoints2=self.getLaserPoints(6)
                        self.draw(surface,frame,color,hitboxes=hitboxes)
                        return
                if len(polygonPoints)>=3:
                    pygame.draw.polygon(surface,color,polygonPoints)
            
    
    
