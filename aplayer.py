import pygame,math,terrain,laser

#function by chatgpt
def rotateAndGetOffset(surface,cx,cy,angle):
    # Rotate the surface
    rotated_surface = pygame.transform.rotate(surface, 180/math.pi*angle)
    rect = surface.get_rect()
    rotated_rect = rotated_surface.get_rect()

    # Pivot offset before rotation
    pivot_x = cx - rect.centerx
    pivot_y = cy - rect.centery

    # Apply rotation transformation
    rotated_pivot_x = pivot_x * math.cos(angle) - pivot_y * math.sin(angle)
    rotated_pivot_y = pivot_x * math.sin(angle) + pivot_y * math.cos(angle)

    # Compute new top-left position
    offset_x = rect.centerx + rotated_pivot_x - rotated_rect.width / 2
    offset_y = rect.centery + rotated_pivot_y - rotated_rect.height / 2

    return rotated_surface, (offset_x), (offset_y)


playerIMGs={}

IMGSet=[]
for i in range(5):
    IMGSet.append(pygame.image.load(".PlayerIdle"+str(i+1)+".png").convert_alpha())
for i in range(3):
    IMGSet.append(pygame.image.load(".PlayerIdle"+str(4-i)+".png").convert_alpha())
playerIMGs["Idle"]=IMGSet

IMGSet=[]
for i in range(8):
    IMGSet.append(pygame.image.load(".PlayerRun"+str(i+1)+".png").convert_alpha())
playerIMGs["Run"]=IMGSet


#TEMPORARY ANIMATION
IMGSet=[]
for i in range(8):
    IMGSet.append(pygame.image.load(".PlayerRun"+str(8-i)+".png").convert_alpha())
playerIMGs["Backpedal"]=IMGSet

playerIMGs["Falling"]=[pygame.image.load(".PlayerFalling.png").convert_alpha()]
playerIMGs["Jumping"]=[pygame.image.load(".PlayerJumping.png").convert_alpha()]
#playerIMGs["Sliding"]=[pygame.image.load(".PlayerSliding.png").convert_alpha()]
playerIMGs["Arm"]=[pygame.image.load(".Arm.png").convert_alpha()]
SPRITE_WIDTH=40
SPRITE_HEIGHT=40
ARM_PIVOT_X =20
ARM_PIVOT_Y=21
LASER_DISTANCE=21
animationLengths = {"Idle":8,"Run":8,"Backpedal":8,"Falling":1,"Jumping":1}
animationFPS=13


class Player:

    def __init__(self,defaultZooms, x,y,dimensions=[10,30]):
        self.x=x
        self.y=y
        self.xSpeed=0
        self.ySpeed=-1
        self.width,self.height=dimensions
        self.rect=pygame.Rect(self.x-self.width/2,self.y-self.height/2,self.width,self.height)
        self.onGround=False
        self.color=(255,0,0)
        self.defaultZooms=defaultZooms
        self.facing = "Right"
        self.animationTimer=0
        self.animationType="Idle"
        self.animationFrame=0
        self.armAngle=0
        self.armOffsetX=0
        self.armOffsetY=0
        self.laserPower=10
        self.laserKnockback=10
        self.laserCooldown=400
        self.laser=[]
        self.chargeDistribution=(1,0,0)
        self.charge=150
        self.maxCharge=500

        self.playerIMGs = {}
        for zoom in self.defaultZooms:
            zoomIMGSets={}
            for direction in ["Left","Right"]:
                directionSet={}
                
                for animationType in playerIMGs:
                    directionSet[animationType]=[]
                    for img in playerIMGs[animationType]:
                        resizedIMG=pygame.transform.scale(img,(SPRITE_WIDTH*zoom,SPRITE_HEIGHT*zoom))
                        if direction=="Left":
                            resizedIMG=pygame.transform.flip(resizedIMG,True,False)
                        directionSet[animationType].append(resizedIMG)
                zoomIMGSets[direction]=directionSet
            self.playerIMGs[zoom]=zoomIMGSets


                
    def updateCostume(self,frameLength, mousePos):
        self.animationTimer=(self.animationTimer+frameLength)%(1000/animationFPS*(animationLengths[self.animationType]))
        previousAnimationType=self.animationType

        targetX,targetY=mousePos

        if self.x<targetX:
            self.facing="Right"
        elif self.x>targetX:
            self.facing="Left"
        
        self.armAngle=-math.atan2(targetY-self.y,targetX-self.x)

        if not self.onGround:
            if self.ySpeed>0:
                self.animationType="Falling"
            else:
                self.animationType="Jumping"
        else:
            if abs(self.xSpeed)>0.1:
                if (self.xSpeed>0 and self.facing=="Right") or (self.xSpeed<0 and self.facing=="Left"):
                    self.animationType="Run"
                else:
                    self.animationType="Backpedal"
            else:
                self.animationType="Idle"
            
        if self.animationType!=previousAnimationType:
            self.animationTimer=0
        
        animationLength=animationLengths[self.animationType]
        if animationLength==1:
            self.animationFrame=0
        else:
            self.animationFrame=math.floor(self.animationTimer/(1000/animationFPS))


    def updateRect(self):
        self.rect.x,self.rect.y=self.x-self.width/2,self.y-self.height/2

    def updateColor(self):
        cw,cb,cr=self.chargeDistribution
        cw,cb,cr=cw*self.charge,cb*self.charge,cr*self.charge
        r,g,b=0,0,0
        r+=cr+cw
        g+=cw+cb/4
        b+=cw+cb
        r=math.sqrt(min(r/self.maxCharge,1))
        g=math.sqrt(min(g/self.maxCharge,1))
        b=math.sqrt(min(b/self.maxCharge,1))
        self.color=(r*255,g*255,b*255)

    def updateLaserStats(self):
        cw,cb,cr=self.chargeDistribution
        cw,cb,cr=cw*self.charge,cb*self.charge,cr*self.charge
        self.laserPower=15+cw/15+cr/5+cb/20
        self.laserKnockback=5+cw/20+cr/25+cb/9
        self.laserCooldown=600-cw/2-cb/10+cr/5

    def addCharge(self, addedCharge, chargeDistribution, maxCharge):
        w,b,r=self.chargeDistribution
        w,b,r=w*self.charge,b*self.charge,r*self.charge
        w+=chargeDistribution[0]*addedCharge
        b+=chargeDistribution[1]*addedCharge
        r+=chargeDistribution[2]*addedCharge
        total=w+b+r
        self.chargeDistribution=(w/total,b/total,r/total)
        originalCharge=self.charge
        if self.charge<maxCharge:
            self.charge+=addedCharge
            if self.charge>maxCharge:
                self.charge=maxCharge
        return self.charge-originalCharge

    def loseCharge(self,loss):
        self.charge-=loss
        if self.charge<0:
            self.charge=0
            #gameover

    def tick(self,frameLength,cTerrain,mousePos,keysDown,events):
        self.ySpeed=min(0.4,self.ySpeed+0.0015*frameLength)
        
        if events["mouseDown"]:
            newLaser=laser.Laser()
            self.laser=[newLaser]
        
        if events["mouseUp"]:
            self.laser=[]
        
        for lase in self.laser:
            lase.updateLaser(cTerrain,self.x-SPRITE_WIDTH/2+ARM_PIVOT_X+LASER_DISTANCE*math.cos(self.armAngle),self.y-SPRITE_HEIGHT/2+ARM_PIVOT_Y+LASER_DISTANCE*math.sin(-self.armAngle),mousePos[0],mousePos[1])
            lase.tick(frameLength)
            if lase.damageFrame:
                for point in lase.collision:
                    x,y=point
                    cTerrain.addAirPocket(x, y, self.laserPower, playerMade=True)
                    cTerrain.newKnockbackCircles.append([x,y,self.laserKnockback])
                    cTerrain.newPlayerDamageCircles.append([x,y,self.laserPower])
                self.loseCharge(2)
                    


        for knockbackCircle in cTerrain.knockbackCircles:
            dx = self.x-knockbackCircle[0]
            dy = self.y-knockbackCircle[1]
            distance=math.sqrt(dx**2+dy**2)
            knockback=knockbackCircle[2]/distance/100
            self.xSpeed+=frameLength*dx/distance*knockback
            self.ySpeed+=frameLength*dy/distance*knockback

        for nest in cTerrain.nests:
            if nest.stage==nest.maxStage and nest.withinEffectRadius(self.x,self.y) and nest.charge>0:
                chargeGain=self.addCharge(nest.chargeRate*frameLength, nest.charging,nest.maxCharge)
                nest.loseCharge(chargeGain)
        self.updateLaserStats()

        if keysDown[pygame.K_w] and self.onGround:
            self.ySpeed = -0.4
        
        if keysDown[pygame.K_a]:
            if self.onGround:
                self.xSpeed -= 0.005*frameLength
            else:
                self.xSpeed -= 0.0015*frameLength
        if keysDown[pygame.K_d]:
            if self.onGround:
                self.xSpeed += 0.005*frameLength
            else:
                self.xSpeed += 0.0015*frameLength
        
        if self.onGround:
            self.xSpeed*=0.98**frameLength
        else:
            self.xSpeed*=0.993**frameLength

        self.moveVertical(frameLength,cTerrain)
        self.moveHorizontal(frameLength,cTerrain)

        self.updateColor()
        self.updateCostume(frameLength,mousePos)
        for lase in self.laser:
            lase.updateLaser(cTerrain,self.x-SPRITE_WIDTH/2+ARM_PIVOT_X+LASER_DISTANCE*math.cos(self.armAngle),self.y-SPRITE_HEIGHT/2+ARM_PIVOT_Y+LASER_DISTANCE*math.sin(-self.armAngle),mousePos[0],mousePos[1],self.laserCooldown)
            
    
    def moveHorizontal(self, frameLength,cTerrain):

        #TODO - add slope platforming

        self.x+=frameLength*self.xSpeed
        self.updateRect()
        if self.collidingWithTerrain(cTerrain):
            slopeTolerance=math.ceil(5*abs(frameLength*self.xSpeed))
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
            backs=math.ceil(abs(frameLength*self.xSpeed/1))
            for i in range(backs):
                self.x-=frameLength*self.xSpeed/backs
                self.updateRect()
                if not self.collidingWithTerrain(cTerrain):
                    break
            self.xSpeed=0
    

    def moveVertical(self, frameLength,cTerrain):
        self.onGround=False
        self.y+=frameLength*self.ySpeed
        self.updateRect()
        if self.collidingWithTerrain(cTerrain):
            if self.ySpeed>0:
                self.onGround=True
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
            backs=math.ceil(abs(frameLength*self.ySpeed/1))
            for i in range(backs):
                self.y-=frameLength*self.ySpeed/backs
                self.updateRect()
                if not self.collidingWithTerrain(cTerrain):
                    break
            self.ySpeed=0
    
    def draw(self, surface, frame,hitboxes=False):
        camX,camY,zoom=frame
        if hitboxes:
            self.updateRect()
            pygame.draw.rect(surface,self.color,pygame.Rect((self.rect.left-camX)*zoom,(self.rect.top-camY)*zoom,self.width*zoom,self.height*zoom))
            for lase in self.laser:
                lase.draw(surface,frame,self.color,hitboxes=hitboxes)
        else:
            playerSurface=pygame.Surface((SPRITE_WIDTH*zoom,SPRITE_HEIGHT*zoom),flags=pygame.SRCALPHA)
            playerSurface.fill((self.color[0],self.color[1],self.color[2],255))
            playerSurface.blit(self.playerIMGs[zoom][self.facing][self.animationType][self.animationFrame],(0,0),special_flags=pygame.BLEND_RGBA_MULT)

            adjustedArmAngle=self.armAngle
            if self.facing=="Left":
                adjustedArmAngle+=math.pi
            arm,offsetX,offsetY=rotateAndGetOffset(self.playerIMGs[zoom][self.facing]["Arm"][0],zoom*ARM_PIVOT_X,zoom*ARM_PIVOT_Y,adjustedArmAngle)
            width,height=arm.get_size()
            armSurface=pygame.Surface((width,height),flags=pygame.SRCALPHA)
            armSurface.fill((self.color[0],self.color[1],self.color[2],255))
            
            armSurface.blit(arm,(0,0),special_flags=pygame.BLEND_RGBA_MULT)

            surface.blit(playerSurface,((self.x-SPRITE_WIDTH/2-camX)*zoom,(self.rect.bottom-SPRITE_HEIGHT-camY)*zoom))
            surface.blit(armSurface,((self.x-SPRITE_WIDTH/2-camX)*zoom+offsetX,(self.rect.bottom-SPRITE_HEIGHT-camY)*zoom+offsetY))
            for lase in self.laser:
                lase.draw(surface,frame,self.color)


    def collidingWithTerrain(self, cTerrain):
        return cTerrain.collideRect(self.rect)
