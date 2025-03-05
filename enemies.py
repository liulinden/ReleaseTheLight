import pygame, math, random

def distance(coord1:int,coord2:int):
    x1,y1=coord1
    x2,y2=coord2
    return math.sqrt((x1-x2)**2+(y1-y2)**2)

def getEnemy(cTerrain, nestType, color, nestHealth, nestX, nestY,nestSize):
    for i in range(10):
        x,y=random.randint(int(nestX-20-nestSize/2),int(nestX+20+nestSize/2)),random.randint(int(nestY-20-nestSize/2),int(nestY+20+nestSize/2))
        newEnemy=Enemy(x,y,color,nestHealth/10)
        if not newEnemy.collidingWithTerrain(cTerrain):
            return newEnemy
    return False

class Enemy:
    def __init__(self,x,y,color,health):
        self.x=x
        self.y=y
        self.xSpeed=0
        self.ySpeed=0
        self.width,self.height=15,15
        self.r=distance((0,0),(self.width/2,self.height/2))
        self.rect=pygame.Rect(self.x-self.width/2,self.y-self.height/2,self.width,self.height)
        self.color = color
        self.maxHealth=health
        self.health=self.maxHealth
        self.onGround=False
        self.damage=self.maxHealth/5
        
    def updateRect(self):
        self.rect.x,self.rect.y=self.x-self.width/2,self.y-self.height/2

    def draw(self, surface, frame,hitbox=False,offset_x=0,offset_y=0):
        hitbox=True
        camX,camY,zoom=frame

        if hitbox:
            self.updateRect()
            pygame.draw.rect(surface,(0,0,0),pygame.Rect((self.rect.left-camX)*zoom+offset_x,(self.rect.top-camY)*zoom+offset_y,self.width*zoom,self.height*zoom))
    
    def drawAttackHitbox(self, surface, frame,hitbox=False,offset_x=0,offset_y=0):
        #never used
        self.draw(surface, frame,hitbox=hitbox,offset_x=offset_x,offset_y=offset_y)

    def dealDamage(self,damage):
        self.health-=damage
        if self.health<0:
            self.health=0
            return True
        return False
    
    def updateRect(self):
        self.rect.x,self.rect.y=self.x-self.width/2,self.y-self.height/2

    def tick(self,frameLength,cTerrain,player):
        self.ySpeed=min(0.4,self.ySpeed+0.0015*frameLength)
        for knockbackCircle in cTerrain.knockbackCircles:
            dx = self.x-knockbackCircle[0]
            dy = self.y-knockbackCircle[1]
            d=max(25,math.sqrt(dx**2+dy**2))
            knockback=2*knockbackCircle[2]/d/100
            self.xSpeed+=frameLength*dx/d*knockback
            self.ySpeed+=frameLength*dy/d*knockback

        for damageCircle in cTerrain.playerDamageCircles:
            x,y,r=damageCircle
            dx = self.x-x
            dy = self.y-y
            d=math.sqrt(dx**2+dy**2)
            print(d,r+self.r)
            if d<r+self.r:
                print("dmg",self.maxHealth,self.health,r/2)
                cTerrain.particles.spawnMiningParticles(10,self.color,r/2,x,y)
                if self.dealDamage(r/2):
                    return True

        if self.x<50:
            self.xSpeed +=(50-self.x)/10000*frameLength
        elif self.x>cTerrain.worldWidth-50:
            self.xSpeed -= (self.x-cTerrain.worldWidth+50)/10000*frameLength


        collidingWithPlayer=self.rect.colliderect(player.rect)
        if not collidingWithPlayer:
            if player.y<self.y-10 and self.onGround and random.randint(1,500)<frameLength:
                self.ySpeed = -0.3
        
            if player.x<self.x:
                if self.onGround:
                    self.xSpeed -= 0.001*frameLength
                else:
                    self.xSpeed -= 0.0003*frameLength
            if player.x>self.x:
                if self.onGround:
                    self.xSpeed += 0.001*frameLength
                else:
                    self.xSpeed += 0.0003*frameLength
        
        if self.onGround:
            self.xSpeed*=0.98**frameLength
        else:
            self.xSpeed*=0.993**frameLength

        self.moveVertical(frameLength,cTerrain)
        self.moveHorizontal(frameLength,cTerrain)
        
        if player.immunityTimer==0:
            if self.rect.colliderect(player.rect):
                player.immunityTimer=player.immunityTime
                player.xSpeed=(player.x-self.x)/max(1,abs((player.x-self.x)))*0.3
                player.ySpeed=-0.3
                player.dealDamage(self.damage)

        if distance((self.x,self.y),(player.x,player.y))>500:
            return True

        return False
    
    def moveHorizontal(self, frameLength,cTerrain):

        #TODO - add slope platforming

        self.x+=frameLength*self.xSpeed
        self.updateRect()
        if self.collidingWithTerrain(cTerrain):
            slopeTolerance=math.ceil(3*abs(frameLength*self.xSpeed))
            for i in range(slopeTolerance):
                self.y-=1
                self.updateRect()
                if not self.collidingWithTerrain(cTerrain):
                    if self.xSpeed>0:
                        self.xSpeed-=self.xSpeed*i/slopeTolerance
                    else:
                        self.xSpeed-=self.xSpeed*i/slopeTolerance
                    return
            self.y+=slopeTolerance
            self.x-=frameLength*self.xSpeed
            backs=math.ceil(abs(frameLength*self.xSpeed/1))
            for i in range(backs):
                self.x+=frameLength*self.xSpeed/backs
                self.updateRect()
                if self.collidingWithTerrain(cTerrain):
                    self.x-=frameLength*self.xSpeed/backs
                    self.updateRect()
                    break
            self.xSpeed=0
    
    def moveVertical(self, frameLength,cTerrain):
        self.onGround=False
        self.y+=frameLength*self.ySpeed
        self.updateRect()
        if self.collidingWithTerrain(cTerrain):
            if self.ySpeed>0:
                self.onGround=True
                if not cTerrain.nestsCollideRect(self.rect):
                    cTerrain.particles.spawnMiningParticles(int(abs((abs(max(0.005*frameLength,abs(self.xSpeed))-0.005*frameLength)+3*(self.ySpeed-0.0015*frameLength))*12)),(0,0,0),20,self.x,self.y+self.height/2,time=200)
            if self.ySpeed<0:
                slopeTolerance=math.ceil(abs(0.5*frameLength*self.ySpeed))
                for i in range(slopeTolerance):
                    self.x-=1
                    self.updateRect()
                    if not self.collidingWithTerrain(cTerrain):
                        return
                self.x+=slopeTolerance
                for i in range(slopeTolerance):
                    self.x+=1
                    self.updateRect()
                    if not self.collidingWithTerrain(cTerrain):
                        return
                self.x-=slopeTolerance
            self.y-=frameLength*self.ySpeed
            backs=math.ceil(abs(frameLength*self.ySpeed/1))
            for i in range(backs):
                self.y+=frameLength*self.ySpeed/backs
                self.updateRect()
                if self.collidingWithTerrain(cTerrain):
                    self.y-=frameLength*self.ySpeed/backs
                    self.updateRect()
                    break
            self.ySpeed=0
    
    def collidingWithTerrain(self, cTerrain):
        return cTerrain.collideRect(self.rect)
