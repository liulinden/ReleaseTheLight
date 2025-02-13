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

    def getAngleLength(self,targetX,targetY):
        dx=targetX-self.startX
        dy=targetY-self.startY
        return math.atan2(dy,dx),math.sqrt(dx**2+dy**2)
    
    def updateLaser(self,startX,startY,targetX,targetY):
        self.startX,self.startY=startX,startY
        self.angle,self.length=self.getAngleLength(targetX,targetY)

    def tick(self,frameLength):
        self.sinWaveOffset+=frameLength/100
        self.timer-=frameLength
        if self.timer<=0:
            self.timer=self.laserTime
            self.laserPoints=self.getLaserPoints(6)
            self.laserPoints2=self.getLaserPoints(6)
    
    def draw(self, surface, frame, hitboxes=False):
        left,top,zoom=frame
        for laserPart in [self.laserPoints,self.laserPoints2]:
            polygonPoints=[]
            for point in laserPart:
                waveHeight=self.thickness*math.sin((point+self.sinWaveOffset)*1.5)*(0.5+self.timer/self.laserTime)
                if laserPart.index(point)%(len(laserPart)/2)==0:
                    x,y=point*math.cos(self.angle),point*math.sin(self.angle)
                else:
                    x,y=point*math.cos(self.angle)+waveHeight*math.sin(self.angle),point*math.sin(self.angle)-waveHeight*math.cos(self.angle)
                polygonPoints.append(((x+self.startX-left)*zoom,(y+self.startY-top)*zoom))
            print(self.startX,self.startY,polygonPoints)
            pygame.draw.polygon(surface,(255,255,255),polygonPoints)
            pygame.draw.polygon(surface,(255,255,255),polygonPoints)
            
    
    
