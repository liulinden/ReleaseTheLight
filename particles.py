import random,pygame,math
class Particles:
    def __init__(self):
        self.particles=[]
        self.pulseParticles=[]
        self.scratchLayer=None
        self.scratchLayerSize=None
    
    def updateScratchLayer(self,dimensions):
        if dimensions !=self.scratchLayerSize:
            self.scratchLayer=pygame.Surface(dimensions,pygame.SRCALPHA)
            self.scratchLayerSize=dimensions
    
    def spawnMiningParticles(self,n,color,size,x,y,time=300):
        for i in range(n):
            angle=-random.random()*2*math.pi
            scale=(random.random()+1)/10
            self.particles.append(MiningParticle(color,size,x,y,math.cos(angle)*scale,math.sin(angle)*scale-0.05,time=time))
    
    def spawnPulseParticle(self,color,size,x,y,time=600):
        self.pulseParticles.append(PulseParticle(color,size,x,y,time))
    
    def tickParticles(self,frameLength):
        for particleSet in [self.pulseParticles,self.particles]:
            for i in range(len(particleSet)-1,-1,-1):
                if particleSet[i].tick(frameLength):
                    particleSet.remove(particleSet[i])

    def drawParticles(self,surface,frame,offset_x=0,offset_y=0):
        for particle in self.particles:
            particle.draw(surface,frame,offset_x,offset_y)
    
    def drawPulseParticles(self,surface:pygame.Surface,frame,offset_x=0,offset_y=0):
        self.updateScratchLayer(surface.get_size())
        self.scratchLayer.fill((0,0,0,0))
        for particle in self.pulseParticles:
            particle.draw(self.scratchLayer,frame,offset_x,offset_y)
        surface.blit(self.scratchLayer,(0,0))


class MiningParticle:
    def __init__(self,color,size,x,y,xSpeed=0,ySpeed=0,time=1000):
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

class PulseParticle:
    def __init__(self,color,size,x,y,time=600):
        self.color=color
        self.x=x
        self.y=y
        self.timer=time
        self.size=size
        self.opacity=150

    def tick(self,frameLength):
        self.timer-=frameLength
        factor=self.timer/(self.timer+frameLength)
        self.size*=factor
        self.opacity*=factor
        if self.timer<=0:
            return True
        return False
    
    def draw(self,surface,frame,offset_x=0,offset_y=0):
        left,top,zoom=frame
        pygame.draw.circle(surface,(self.color[0],self.color[1],self.color[2],100),((self.x-left)*zoom+offset_x,(self.y-top)*zoom+offset_y),self.size*zoom)