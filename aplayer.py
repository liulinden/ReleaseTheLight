import pygame,math,terrain,laser,laserProperties
from util import rotateAndGetOffset, rgbBound, channelBound, chargesToColor
from global_assets import get_asset


SPRITE_WIDTH=40
SPRITE_HEIGHT=40
ARM_PIVOT_X =20
ARM_PIVOT_Y=21

IMPACT_SIZE = 100   # world-space size in px — easy to change
IMPACT_FPS = 24
IMPACT_FRAMES = 7

playerIMGs={}
laserImpactIMGsRaw=[]  # raw unscaled images, loaded in init()
animationLengths = {"Idle":8,"Run":8,"Backpedal":8,"Falling":1,"Jumping":1}
animationFPS=13

def init():
    global playerIMGs, laserImpactIMGsRaw

    IMGSet=[]
    for i in range(5):
        IMGSet.append(get_asset("PlayerIdle"+str(i+1)))
    for i in range(3):
        IMGSet.append(get_asset("PlayerIdle"+str(4-i)))
    playerIMGs["Idle"]=IMGSet

    IMGSet=[]
    for i in range(8):
        IMGSet.append(get_asset("PlayerRun"+str(i+1)))
    playerIMGs["Run"]=IMGSet

    #TEMPORARY ANIMATION
    IMGSet=[]
    for i in range(8):
        IMGSet.append(get_asset("PlayerRun"+str(8-i)))
    playerIMGs["Backpedal"]=IMGSet

    playerIMGs["Falling"]=[get_asset("PlayerFalling")]
    playerIMGs["Jumping"]=[get_asset("PlayerJumping")]
    #playerIMGs["Sliding"]=[get_asset("PlayerSliding")]
    playerIMGs["Arm"]=[get_asset("Arm")]

    laserImpactIMGsRaw = []
    for i in range(1, IMPACT_FRAMES + 1):
        laserImpactIMGsRaw.append(
            get_asset(f"LaserImpact{i}")
        )


class LaserImpact:
    """Single impact animation instance. Follows the live laser endpoint while
    the laser is active, then freezes at its last known position."""
    _frameDuration = 1000 / IMPACT_FPS

    def __init__(self, x, y, angle, sourceLaser, scaledIMGs):
        self.x = x
        self.y = y
        self.angle = angle
        self.sourceLaser = sourceLaser  # reference to spawning Laser; set to None when gone
        self.scaledIMGs = scaledIMGs    # pre-scaled images for all zooms
        self.timer = 0.0

    def tick(self, frameLength, activeLasers):
        # update position if source laser is still active
        if self.sourceLaser is not None:
            if self.sourceLaser in activeLasers:
                lase = self.sourceLaser
                self.x = lase.startX + math.cos(lase.angle) * lase.length
                self.y = lase.startY + math.sin(lase.angle) * lase.length
                self.angle = lase.angle
            else:
                self.sourceLaser = None  # laser gone — freeze position

        self.timer += frameLength
        return self.timer >= self._frameDuration * IMPACT_FRAMES  # True = finished

    def draw(self, surface, frame, color, zoom):
        left, top, _ = frame
        frameIndex = min(IMPACT_FRAMES - 1, int(self.timer / self._frameDuration))
        img = self.scaledIMGs[zoom][frameIndex]

        size = img.get_size()
        tinted = img.copy()
        colorSurf = pygame.Surface(size, pygame.SRCALPHA)
        colorSurf.fill((color[0], color[1], color[2], 255))
        tinted.blit(colorSurf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

        cx = size[0] / 2
        cy = size[1] / 2
        rotAngle = math.pi - self.angle
        rotated, offX, offY = rotateAndGetOffset(tinted, cx, cy, rotAngle)

        halfH = size[1] / 2
        screenX = (self.x - left) * zoom - cx + offX - math.cos(self.angle) * halfH
        screenY = (self.y - top)  * zoom - cy + offY - math.sin(self.angle) * halfH
        surface.blit(rotated, (screenX, screenY))


class Player:

    def __init__(self,defaultZooms, x,y,dimensions=[10,30]):
        self.spawnX=x
        self.spawnY=y
        self.x=x
        self.y=y
        self.xSpeed=0
        self.ySpeed=0
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

        self.chargeFilter="white"
        self.laserTimer=0
        self.laserRamps=0
        self.laserFirstHit=False
        self.laser=[]
        self.impacts=[]  # active LaserImpact instances
        self.laserAttributes = laserProperties.LaserAttributes(18,1,0.2,10,400,1,20,0.3,1,20,20,0.5,2,0.5)

        self.chargeCapacity=100
        self.charges={"white":self.chargeCapacity,"blue":0,"red":0}
        self.maxCharge=500
        self.immunityTimer=0
        self.immunityTime=500
        self.queuedDamage=0    
        self.queuedDrainDamage=0    

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

        # pre-scale impact images for each zoom — done here since defaultZooms is available
        self._impactIMGs = {}
        for zoom in self.defaultZooms:
            size = int(IMPACT_SIZE * zoom)
            self._impactIMGs[zoom] = [
                pygame.transform.scale(img, (size, size)) for img in laserImpactIMGsRaw
            ]

    def resetPlayer(self):
        self.x=self.spawnX
        self.y=self.spawnY
        self.xSpeed=0
        self.ySpeed=0
        self.setCharges(max(150,self.chargeCapacity*2/3),0,0)
      
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
            if self.ySpeed>0.2:
                self.animationType="Falling"
            elif self.ySpeed<-0.2:
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
        cw,cb,cr=self.charges.values()
        self.color=chargesToColor(cw,cb,cr,self.maxCharge)

    def updateLaserStats(self):
        laserProperties.setLaserAttributes(self.laserAttributes,self.charges,self.maxCharge)

    def setCharges(self, white, blue, red):
        self.charges["white"]=white
        self.charges["blue"]=blue
        self.charges["red"]=red

    def addCharge(self, addedCharge, chargeDistribution, maxCharge):

        sumAdded=0
        for color in self.charges:
            addend= chargeDistribution[color]*addedCharge
            self.charges[color]+=addend
            sumAdded+=addend
        
        totalCharge=sum(self.charges.values())
        overflow=0
        if totalCharge>self.chargeCapacity:
            self.chargeCapacity=max(self.chargeCapacity, min(self.maxCharge,min(maxCharge, totalCharge)))
            overflow=totalCharge-self.chargeCapacity
        
        self.loseCharge(overflow)
        
        return sumAdded-overflow

    def loseCharge(self,loss):
        nSplit = 3
        while nSplit>0:
            splitLoss= loss/nSplit
            for charge in self.charges:
                if 0 < self.charges[charge] < splitLoss:
                    loss-=self.charges[charge]
                    self.charges[charge]=0
                    nSplit-=1
                    break
            for charge in self.charges:
                if self.charges[charge]>0: self.charges[charge]-=splitLoss
            nSplit=0
        if sum(self.charges.values())>0:
            return False
        self.resetPlayer()
        return True

    def dealDamage(self,damage):
        self.queuedDamage+=damage

    def drainDamage(self,damage):
        self.queuedDrainDamage+=damage

    def tick(self,frameLength,cTerrain:terrain.Terrain,mousePos,keysDown,events):
        if self.loseCharge(self.queuedDamage) or self.loseCharge(self.queuedDrainDamage):
            return True
        self.queuedDamage=0
        self.queuedDrainDamage=0

        self.ySpeed=min(0.4,self.ySpeed+0.0015*frameLength)
        if self.immunityTimer>0:
            self.immunityTimer-=frameLength
            if self.immunityTimer<0:
                self.immunityTimer=0
        
        if keysDown["mouse"] and len(self.laser)==0 and self.laserTimer<=self.laserAttributes.cooldown/4:
            newLaser=laser.Laser()
            self.laser=[newLaser]
            self.laserRamps=0
            self.laserFirstHit=True
        
        if events["mouseUp"] and len(self.laser)>0:
            self.laserTimer=self.laser[0].timer
            self.laser=[]

        self.laserTimer-=frameLength
        self.laserTimer=max(0,self.laserTimer)
        
        for lase in self.laser:
            locked= lase.updateLaser(cTerrain,self.x-SPRITE_WIDTH/2+ARM_PIVOT_X+self.laserAttributes.distance*math.cos(self.armAngle),self.y-SPRITE_HEIGHT/2+ARM_PIVOT_Y+self.laserAttributes.distance*math.sin(-self.armAngle),-self.armAngle)
            lase.tick(frameLength)
            if lase.damageFrame:
                if not locked:
                    self.laserRamps=0
                if lase.collision:
                    point= lase.collision[0]
                    x,y=point
                    explosionSize=laserProperties.getLaserEXPL(self.laserAttributes,self.laserFirstHit)
                    cTerrain.addAirPocketClump(x, y, explosionSize, layerIndex=cTerrain._layerForY(y), playerMade=True, spreading=1/5)
                    if lase.collision[1]=="ground":
                        cTerrain.particles.spawnMiningParticles(10,(0,0,0),explosionSize*1.5,x,y)
                    cTerrain.newKnockbackCircles.append([laserProperties.getLaserKB(self.laserAttributes,self.laserFirstHit),x,y,self.laserAttributes.KBRange, self.laserAttributes.areaKBFalloff])
                    cTerrain.newPlayerDamageCircles.append([laserProperties.getLaserDMG(self.laserAttributes,self.laserFirstHit, self.laserRamps),x,y,self.laserAttributes.DMGRange,self.laserAttributes.areaDMGFalloff])
                
                self.laserFirstHit=False
                self.laserRamps+=1

                if self.loseCharge(0.5):
                    return True
                
                # spawn impact — position follows live laser, freezes when laser released
                endX = lase.startX + math.cos(lase.angle) * lase.length
                endY = lase.startY + math.sin(lase.angle) * lase.length
                self.impacts.append(LaserImpact(endX, endY, lase.angle, lase, self._impactIMGs))

        # tick impacts, passing current active lasers so they can track position
        for i in range(len(self.impacts) - 1, -1, -1):
            if self.impacts[i].tick(frameLength, self.laser):
                del self.impacts[i]

        for knockbackCircle in cTerrain.knockbackCircles:
            dx = self.x-knockbackCircle[1]
            dy = self.y-knockbackCircle[2]
            distance=math.sqrt(dx**2+dy**2)
            knockback=knockbackCircle[0]

            self.xSpeed+=frameLength*dx/distance*knockback/60
            self.ySpeed+=frameLength*dy/distance*knockback/60

        for li in cTerrain.activeLayers:
            for nest in cTerrain.nests[li]:
                if nest.stage==nest.maxStage and nest.withinEffectRadius(self.x,self.y) and nest.charge>0:
                    chargeGain=self.addCharge(nest.chargeRate*frameLength, nest.charging,nest.maxCharge)
                    nest.loseCharge(chargeGain)
        self.updateLaserStats()

        if self.x<50:
            self.xSpeed +=(50-self.x)/10000*frameLength
        elif self.x>cTerrain.worldWidth-50:
            self.xSpeed -= (self.x-cTerrain.worldWidth+50)/10000*frameLength

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
            lase.updateLaser(cTerrain,self.x-SPRITE_WIDTH/2+ARM_PIVOT_X+self.laserAttributes.distance*math.cos(self.armAngle),self.y-SPRITE_HEIGHT/2+ARM_PIVOT_Y+self.laserAttributes.distance*math.sin(-self.armAngle),-self.armAngle,self.laserAttributes.cooldown)
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
    
    def moveVertical(self, frameLength,cTerrain:terrain.Terrain):
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
    
    def draw(self, surface, frame, hitboxes=False, offset_x=0, offset_y=0, tilt=0):
        camX,camY,zoom=frame
        if hitboxes:
            self.updateRect()
            l  = float(self.rect.left)
            r  = float(self.rect.right - 1)
            t  = float(self.rect.top)
            b  = float(self.rect.bottom - 1)
            pygame.draw.line(surface,self.color,((l-camX) * zoom + offset_x,(t- camY) * zoom + offset_y),((l- camX) * zoom + offset_x,(b- camY) * zoom + offset_y))
            pygame.draw.line(surface,self.color,((r-camX) * zoom + offset_x,(t- camY) * zoom + offset_y),((r- camX) * zoom + offset_x,(b- camY) * zoom + offset_y))
            pygame.draw.line(surface,self.color,((l-camX) * zoom + offset_x,(t- camY) * zoom + offset_y),((r- camX) * zoom + offset_x,(t- camY) * zoom + offset_y))
            pygame.draw.line(surface,self.color,((l-camX) * zoom + offset_x,(b- camY) * zoom + offset_y),((r- camX) * zoom + offset_x,(b- camY) * zoom + offset_y))
            for lase in self.laser:
                lase.draw(surface,frame,self.color,hitboxes=hitboxes,offset_x=offset_x,offset_y=offset_y)
        else:
            boostedColor = (channelBound(self.color[0]+30),channelBound(self.color[1]+30),channelBound(self.color[2]+30))
            playerSurface=pygame.Surface((SPRITE_WIDTH*zoom,SPRITE_HEIGHT*zoom),flags=pygame.SRCALPHA)
            playerSurface.fill((boostedColor[0],boostedColor[1],boostedColor[2],255))
            playerSurface.blit(self.playerIMGs[zoom][self.facing][self.animationType][self.animationFrame],(0,0),special_flags=pygame.BLEND_RGBA_MULT)

            if tilt!=0:
                playerSurface=pygame.transform.rotate(playerSurface,tilt)

            adjustedArmAngle=self.armAngle
            if self.facing=="Left":
                adjustedArmAngle+=math.pi
            arm,offsetX,offsetY=rotateAndGetOffset(self.playerIMGs[zoom][self.facing]["Arm"][0],zoom*ARM_PIVOT_X,zoom*ARM_PIVOT_Y,adjustedArmAngle)
            width,height=arm.get_size()
            armSurface=pygame.Surface((width,height),flags=pygame.SRCALPHA)
            armSurface.fill((boostedColor[0],boostedColor[1],boostedColor[2],255))
            armSurface.blit(arm,(0,0),special_flags=pygame.BLEND_RGBA_MULT)

            surface.blit(playerSurface,((self.x-SPRITE_WIDTH/2-camX)*zoom+offset_x,(3+self.rect.bottom-SPRITE_HEIGHT-camY)*zoom+offset_y))
            surface.blit(armSurface,((self.x-SPRITE_WIDTH/2-camX)*zoom+offsetX+offset_x,(3+self.rect.bottom-SPRITE_HEIGHT-camY)*zoom+offsetY+offset_y))
            for lase in self.laser:
                lase.draw(surface,frame,boostedColor,offset_x=offset_x,offset_y=offset_y)
            # draw impact animations — rendered after laser so they appear on top
            for impact in self.impacts:
                impact.draw(surface, frame, boostedColor, zoom)

    def collidingWithTerrain(self, cTerrain):
        return cTerrain.collideRect(self.rect)
        