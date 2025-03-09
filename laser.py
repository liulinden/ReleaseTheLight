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
        self.laserWidth=20
        self.maxLength=400
        self.collision=[]
        self.damageFrame=False
        self.hitboxes=[]

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

    def getLength(self,terrain,angle):
        
        self.hitboxes=[]

        dy=math.sin(angle)
        dx=math.cos(angle)

        size=self.laserWidth
        distance=0
        self.collision=[]

        rect=pygame.Rect(self.startX+dx*distance,self.startY+dy*distance,size,size)
        while distance<self.maxLength:
            if terrain.laserCollideRect(rect):
                if size>1:
                    distance=max(0,distance-size)
                    rect.x=self.startX+dx*distance
                    rect.y=self.startY+dy*distance
                    size=math.ceil(size/2)
                    if size>=5:
                        rect.width=size
                        rect.height=size
                else:
                    self.hitboxes.append([rect.left,rect.top,rect.width,rect.height])
                    if terrain.nestsCollideRect(rect):
                        self.collision=[rect.center,"nests"]
                    elif terrain.enemiesCollideRect(rect):
                        self.collision=[rect.center,"enemies"]
                    else:
                        self.collision=[rect.center,"ground"]
                    break
            else:
                self.hitboxes.append([rect.left,rect.top,rect.width,rect.height])
                distance+=size
                if distance>self.maxLength:
                    distance=self.maxLength
                rect.x=self.startX+dx*distance
                rect.y=self.startY+dy*distance
        return distance+5/2

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
    
    def updateLaser(self,terrain,startX,startY,angle,laserCooldown=0):
        self.startX,self.startY=startX,startY
        self.angle=angle
        self.length=self.getLength(terrain,angle)
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
            for hitbox in self.hitboxes:
                pygame.draw.rect(surface,color,pygame.Rect((hitbox[0]-left)*zoom+offset_x,(hitbox[1]-top)*zoom+offset_y,hitbox[2]*zoom,hitbox[3]*zoom))
        else:
            for laserPart in [self.laserPoints,self.laserPoints2]:
                oglength=laserPart[int(len(laserPart)/2)]
                scale = self.length/oglength
                polygonPoints=[]
                for point in laserPart:
                    if True or point <= self.length:
                        waveHeight=self.thickness*math.sin((point+self.sinWaveOffset)*1.5)*(0.5+self.timer/self.laserTime)
                        if laserPart.index(point)%(len(laserPart)/2)==0:
                            x,y=point*math.cos(self.angle)*scale,point*math.sin(self.angle)*scale
                        else:
                            x,y=point*math.cos(self.angle)*scale+waveHeight*math.sin(self.angle),point*math.sin(self.angle)*scale-waveHeight*math.cos(self.angle)
                        polygonPoints.append(((x+self.startX-left)*zoom+offset_x,(y+self.startY-top+3)*zoom+offset_y))
                    else:
                        print(self.length)
                        self.laserPoints=self.getLaserPoints(6)
                        self.laserPoints2=self.getLaserPoints(6)
                        self.draw(surface,frame,color,hitboxes=hitboxes)
                        return
                if len(polygonPoints)>=3:
                    pygame.draw.polygon(surface,color,polygonPoints)
            
    
    
