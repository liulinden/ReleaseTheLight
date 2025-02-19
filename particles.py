import random,pygame,math
class Particles:
    def __init__(self):
        self.particles=[]
        ...
    
    def spawnMiningParticles(self,n,color,size,x,y,time=300):
        for i in range(n):
            angle=-random.random()*2*math.pi
            scale=(random.random()+1)/10
            self.particles.append(MiningParticle(color,size,x,y,math.cos(angle)*scale,math.sin(angle)*scale-0.05,time=time))
    
    def tickParticles(self,frameLength):
        for i in range(len(self.particles)-1,-1,-1):
            if self.particles[i].tick(frameLength):
                self.particles.remove(self.particles[i])

    def drawParticles(self,surface,frame,offset_x=0,offset_y=0):
        for particle in self.particles:
            particle.draw(surface,frame,offset_x,offset_y)


class MiningParticle:
    def __init__(self,color,size,x,y,xSpeed=0,ySpeed=0,time=300):
        self.color=color
        self.x=x
        self.y=y
        self.xSpeed=xSpeed
        self.ySpeed=ySpeed
        self.timer=time
        self.size=random.randint(1,3)*size/20

    def tick(self,frameLength):
        self.ySpeed+=0.0015*frameLength
        self.x+=self.xSpeed*frameLength
        self.y+=self.ySpeed*frameLength
        self.timer-=frameLength
        if self.timer<=0:
            return True
        return False
    
    def draw(self,surface,frame,offset_x=0,offset_y=0):
        left,top,zoom=frame
        pygame.draw.circle(surface,self.color,((self.x-left)*zoom+offset_x,(self.y-top)*zoom+offset_y),self.size*zoom)