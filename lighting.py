import pygame,random,copy,os

mistParticleIMGs=[]
for i in range(5):
    mistParticleIMGs.append(pygame.image.load(os.path.join("assets","MistParticle"+str(i+1)+".png")).convert_alpha())
lightGradient=pygame.image.load(os.path.join("assets","LightGradient.png")).convert_alpha()


class Lighting:
    def __init__(self, defaultZooms=[0.1,2]):
        self.particles=[]
        self.resizedLightIMGs={}
        self.resizedLightIMGs["MistParticles"]=[]
        for lightIMG in mistParticleIMGs:
            for size in [110,130,150]:
                IMGs={}
                for zoom in defaultZooms:
                    IMGs[zoom]=pygame.transform.scale(lightIMG,(zoom*size,zoom*size))
                self.resizedLightIMGs["MistParticles"].append(IMGs)
        for size in [400,600,800]:
            self.resizedLightIMGs["Gradient"+str(size)]={}
            for zoom in defaultZooms:
                self.resizedLightIMGs["Gradient"+str(size)][zoom]=pygame.transform.scale(lightGradient,(zoom*size,zoom*size))

    def addMistParticle(self,x,y,color=(255,255,255)):
        newParticle=MistParticle(x,y,self.resizedLightIMGs["MistParticles"][random.randint(0,len(self.resizedLightIMGs)-1)],color)
        self.particles.append(newParticle)

    def tickEffects(self,frameLength):
        for i in range(len(self.particles)-1,-1,-1):
            if self.particles[i].tick(frameLength)=="end":
                self.particles.remove(self.particles[i])

    def drawGradient(self,surface:pygame.Surface,frame,color,x,y,offset_x=0,offset_y=0):
        left,top,zoom=frame
        
        img=self.resizedLightIMGs["Gradient400"][zoom]
        dimensions=img.get_size()
        #"""
        filter= pygame.Surface(dimensions,flags=pygame.SRCALPHA)
        filter.fill((color[0],color[1],color[2],60))
        filter.blit(img,(0,0),special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(filter,((x-left)*zoom-dimensions[0]/2+offset_x,(y-top)*zoom-dimensions[1]/2+offset_y))
        #"""
        #surface.blit(img,((x-left)*zoom-dimensions[0]/2,(y-top)*zoom-dimensions[1]/2))
    
    def drawEffects(self,surface:pygame.Surface,frame,offset_x=0,offset_y=0):
        for particle in self.particles:
            particle.draw(surface, frame,offset_x=offset_x,offset_y=offset_y)

class MistParticle:
    def __init__(self, x, y, IMGs, color=(255,255,255)):
        self.color=color
        self.xSpeed=(random.random()-0.5)/12
        self.ySpeed=(random.random()-0.5)/12
        self.lifeTime=500
        self.x=x+random.randint(-50,50)
        self.y=y+random.randint(-50,50)
        self.IMGs=IMGs
        self.brightness=(random.random()+0.2)*2
        self.fadeIn=0
        self.IMGs={}
        for key in IMGs:
            dimensions=(IMGs[key].get_width(),IMGs[key].get_height())
            filter= pygame.Surface(dimensions,flags=pygame.SRCALPHA)
            filter.fill((self.color[0],self.color[1],self.color[2],255))
            filter.blit(IMGs[key],(0,0),special_flags=pygame.BLEND_RGBA_MULT)
            self.IMGs[key]=filter
    
    def tick(self,frameLength):
        self.lifeTime-=frameLength/3
        if self.lifeTime<0:
            return "end"
        self.x+=self.xSpeed*frameLength
        self.y+=self.ySpeed*frameLength
        self.ySpeed-=frameLength*0.00001*frameLength/60
        self.xSpeed*=0.99994**frameLength
        self.ySpeed*=0.99994**frameLength
        
        if self.fadeIn<1:
            self.fadeIn+=0.02*frameLength/16

    def draw(self,surface:pygame.Surface, frame,offset_x=0,offset_y=0):
        left,top,zoom=frame
        #if needed to reduce lag, can probably do most of this in the init function
        """
        dimensions=(self.IMGs[zoom].get_width(),self.IMGs[zoom].get_height())
        filter= pygame.Surface(dimensions,flags=pygame.SRCALPHA)
        filter.fill((self.color[0],self.color[1],self.color[2],self.lifeTime/4*self.brightness*self.fadeIn))
        lightSurface=pygame.Surface(dimensions,flags=pygame.SRCALPHA)
        lightSurface.blit(self.IMGs[zoom],(0,0))
        lightSurface.blit(filter,(0,0),special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(lightSurface,((self.x-left)*zoom-dimensions[0]/2,(self.y-top)*zoom-dimensions[1]/2))
        """
        dimensions=(self.IMGs[zoom].get_width(),self.IMGs[zoom].get_height())
        self.IMGs[zoom].set_alpha(self.lifeTime/4*self.brightness*self.fadeIn)
        surface.blit(self.IMGs[zoom],((self.x-left)*zoom-dimensions[0]/2+offset_x,(self.y-top)*zoom-dimensions[1]/2+offset_y))


        


