import pygame,math,random

class Laser:
    def __init__(self):
        self.angle=0
        self.length=0
        self.startX=0
        self.startY=0
        self.digSpeed=1
        self.thickness=10
        self.laserPoints=[]
        self.sinWaveOffset=0
        self.timer=0
        self.laserTime=200

    def getLaserPoints(self, n_points):
        n_points=max(3,1+round(self.length/100))
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
        self.sinWaveOffset+=frameLength/50
        self.timer-=frameLength
        if self.timer<=0:
            self.timer=self.laserTime
            self.laserPoints=self.getLaserPoints(6)
    
    def draw(self, surface, frame, hitboxes=False):
        polygonPoints=[]
        for point in self.laserPoints:
            waveHeight=self.thickness*math.sin(point+self.sinWaveOffset)*(0.5+self.timer/self.laserTime)
            if self.laserPoints.index(point)%(len(self.laserPoints)/2)==0:
                x,y=point*math.cos(self.angle),point*math.sin(self.angle)
            else:
                x,y=point*math.cos(self.angle)+waveHeight*math.sin(self.angle),point*math.sin(self.angle)-waveHeight*math.cos(self.angle)
            polygonPoints.append((x+self.startX,y+self.startY))
        pygame.draw.polygon(surface,(255,255,255),polygonPoints)
        pygame.draw.polygon(surface,(255,255,255),polygonPoints)
            
    
    
