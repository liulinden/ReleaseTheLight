import pygame, math, random, os, UI
from global_assets import get_asset


# FIX 2: images loaded in init() after display exists
lightGradient = None
enemyAnimations = {}

enemyAttackFrames = {'1': [4, 5]}
enemyAnimationLengths = {
    '1': {"Spawn": 6, "Walk": 7, "Attack": 9}
}

def init():
    global lightGradient, enemyAnimations
    lightGradient = get_asset("LightGradient")
    enemyAnimations = {}
    for variantID in ['1']:
        animationIMGs = {}

        spawnIMGs = []
        for i in range(enemyAnimationLengths[variantID]["Spawn"]):
            spawnIMGs.append(get_asset("Enemy" + variantID + "Spawn" + str(i + 1)))
        animationIMGs["Spawn"] = spawnIMGs

        walkIMGs = []
        for i in range(enemyAnimationLengths[variantID]["Walk"]):
            walkIMGs.append(get_asset("Enemy" + variantID + "Walk" + str(i + 1)))
        animationIMGs["Walk"] = walkIMGs

        attackIMGs = []
        for i in range(enemyAnimationLengths[variantID]["Attack"]):
            attackIMGs.append(get_asset("Enemy" + variantID + "Attack" + str(i + 1)))
        animationIMGs["Attack"] = attackIMGs
        animationIMGs["AttackHitbox"] = get_asset("Enemy" + variantID + "AttackHitbox")

        enemyAnimations[variantID] = animationIMGs


def getEnemy(cTerrain, player, nestType, color, nestHealth, nestX, nestY, nestSize):
    for i in range(20):
        x, y = random.randint(int(nestX - 10 - nestSize / 2), int(nestX + 10 + nestSize / 2)), random.randint(int(nestY - 10 - nestSize / 2), int(nestY + 10 + nestSize / 2))
        size = random.randint(20, 70)
        width, height = size * 3 / 8, size * 3 / 4 
        newEnemyRect= pygame.Rect(x - width / 2, y - height / 2, width, height)
        if not (cTerrain.collideRect(newEnemyRect) or newEnemyRect.colliderect(player.rect)):
            newEnemy=Enemy(cTerrain.defaultZooms, x, y, color, nestHealth / 5, size)
            newEnemy.spawnParticles(cTerrain)
            return newEnemy
    return False


animationFPS = 15


class Enemy:
    def __init__(self, defaultZooms, x, y, color, health, size):
        self.size = size
        self.width, self.height = self.size * 3 / 8, self.size * 3 / 4
        self.maxHealth = health
        self.damage = self.maxHealth / 2
        self.speed = 1.5
        self.canFly = True
        if random.randint(1, 2) == 1:
            self.canFly = not self.canFly
        self.variantID = '1'
        self.attackFrames = enemyAttackFrames[self.variantID]
        self.animationLengths = enemyAnimationLengths[self.variantID]

        self.x = x
        self.y = y
        self.xSpeed = 0
        self.ySpeed = 0
        self.color = color
        self.health = self.maxHealth
        self.onGround = False
        self.animationTimer = 0
        self.animationFrame = 0
        self.facing = "Right"
        self.mode = "Spawn"
        self.glow = 0
        self.r = math.dist((0, 0), (self.width / 2, self.height / 2))
        self.rect = pygame.Rect(self.x - self.width / 2, self.y - self.height / 2, self.width, self.height)
        self.healthBar=UI.HealthBar(self.maxHealth)

        self.resizedGradients = {}
        self.resizedIMGs = {}

        # FIX 1: pre-allocate filter surfaces for draw() and drawGradient() per zoom
        self._draw_filter = {}
        self._gradient_filter = {}

        for zoom in defaultZooms:
            zoomSet = {}
            for direction in ["Left", "Right"]:
                IMGs = {}

                resizedspawns = []
                for spawnIMG in enemyAnimations[self.variantID]["Spawn"]:
                    resized = pygame.transform.scale(spawnIMG, (self.size * zoom, self.size * zoom))
                    if direction == "Left":
                        resized = pygame.transform.flip(resized, True, False)
                    resizedspawns.append(resized)
                IMGs["Spawn"] = resizedspawns

                resizedwalks = []
                for walkIMG in enemyAnimations[self.variantID]["Walk"]:
                    resized = pygame.transform.scale(walkIMG, (self.size * zoom, self.size * zoom))
                    if direction == "Left":
                        resized = pygame.transform.flip(resized, True, False)
                    resizedwalks.append(resized)
                IMGs["Walk"] = resizedwalks

                resizedAttacks = []
                for attackIMG in enemyAnimations[self.variantID]["Attack"]:
                    resized = pygame.transform.scale(attackIMG, (self.size * zoom, self.size * zoom))
                    if direction == "Left":
                        resized = pygame.transform.flip(resized, True, False)
                    resizedAttacks.append(resized)
                IMGs["Attack"] = resizedAttacks

                resized = pygame.transform.scale(enemyAnimations[self.variantID]["AttackHitbox"], (self.size * zoom, self.size * zoom))
                if direction == "Left":
                    resized = pygame.transform.flip(resized, True, False)
                IMGs["AttackHitbox"] = resized

                zoomSet[direction] = IMGs
            self.resizedIMGs[zoom] = zoomSet

            grad_img = pygame.transform.scale(lightGradient, (self.size * 2 * zoom, self.size * 2 * zoom))
            self.resizedGradients[zoom] = grad_img
            self._draw_filter[zoom] = pygame.Surface((self.size * zoom, self.size * zoom), flags=pygame.SRCALPHA)
            self._gradient_filter[zoom] = pygame.Surface(grad_img.get_size(), flags=pygame.SRCALPHA)

    def spawnParticles(self, cTerrain):
        cTerrain.particles.spawnMiningParticles(15, self.color, self.size / 3, self.x, self.y)

    def updateCostume(self, frameLength, player):
        self.glow += (0 - self.glow) / 500 * frameLength
        self.animationTimer = self.animationTimer + frameLength
        if self.mode == "Spawn":
            if self.animationTimer >= self.animationLengths["Spawn"] * 1000 / animationFPS:
                self.mode = "Walk"
                self.animationTimer = 0
        elif self.mode == "Walk":
            self.animationTimer = self.animationTimer % (self.animationLengths["Walk"] * 1000 / animationFPS)
        elif self.mode == "Attack":
            if self.animationTimer >= self.animationLengths["Attack"] * 1000 / animationFPS:
                self.mode = "Walk"
                self.animationTimer = 0

        targetX, targetY = player.x, player.y

        if self.mode == "Walk":
            if self.x < targetX:
                self.facing = "Right"
            elif self.x > targetX:
                self.facing = "Left"

        self.animationFrame = math.floor(self.animationTimer / (1000 / animationFPS))

    def updateRect(self):
        self.rect.x, self.rect.y = self.x - self.width / 2, self.y - self.height / 2

    def drawGradient(self, surface, frame, offset_x=0, offset_y=0):
        camX, camY, zoom = frame
        img = self.resizedGradients[zoom]
        if self.glow > 0:
            # FIX 1: reuse pre-allocated gradient filter surface
            filt = self._gradient_filter[zoom]
            filt.fill((self.color[0], self.color[1], self.color[2], self.glow))
            filt.blit(img, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(filt, ((self.x - self.size - camX) * zoom + offset_x, (self.y - self.size - camY) * zoom + offset_y))

    def draw(self, surface, frame, hitbox=False, offset_x=0, offset_y=0):
        camX, camY, zoom = frame

        self.updateRect()
        if hitbox:
            if self.mode != "Spawn":
                l  = float(self.rect.left)
                r  = float(self.rect.right - 1)
                t  = float(self.rect.top)
                b  = float(self.rect.bottom - 1)
                pygame.draw.line(surface,self.color,((l-camX) * zoom + offset_x,(t- camY) * zoom + offset_y),((l- camX) * zoom + offset_x,(b- camY) * zoom + offset_y))
                pygame.draw.line(surface,self.color,((r-camX) * zoom + offset_x,(t- camY) * zoom + offset_y),((r- camX) * zoom + offset_x,(b- camY) * zoom + offset_y))
                pygame.draw.line(surface,self.color,((l-camX) * zoom + offset_x,(t- camY) * zoom + offset_y),((r- camX) * zoom + offset_x,(t- camY) * zoom + offset_y))
                pygame.draw.line(surface,self.color,((l-camX) * zoom + offset_x,(b- camY) * zoom + offset_y),((r- camX) * zoom + offset_x,(b- camY) * zoom + offset_y))
                if self.mode == "Attack" and self.animationFrame in self.attackFrames:
                    self.drawAttackHitbox(surface, frame, offset_x=offset_x, offset_y=offset_y)
        else:
            # FIX 1: reuse pre-allocated draw filter surface
            filt = self._draw_filter[zoom]
            filt.fill(self.color)
            filt.blit(self.resizedIMGs[zoom][self.facing][self.mode][self.animationFrame], (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(filt, ((self.rect.centerx - self.size / 2 - camX) * zoom + offset_x, (self.rect.bottom - self.size - camY + 5) * zoom + offset_y))
    
    def drawHealthBar(self, surface,frame, time=None, offset_x=0,offset_y=0):
        camX,camY,zoom = frame
        self.healthBar.draw(surface, self.color, ((self.rect.centerx - camX) * zoom + offset_x, (self.rect.bottom - self.size - camY + 5) * zoom + offset_y),self.health,time)

    def drawAttackHitbox(self, surface, frame, offset_x=0, offset_y=0):
        #never used
        camX, camY, zoom = frame
        surface.blit(self.resizedIMGs[zoom][self.facing]["AttackHitbox"], ((self.rect.centerx - self.size / 2 - camX) * zoom + offset_x, (self.rect.bottom - self.size - camY + 5) * zoom + offset_y))

    def dealDamage(self, damage):
        self.glow = 255
        self.health -= damage
        if damage>0:
            self.healthBar.trigger()
        if self.health < 0:
            self.health = 0
            return True
        return False

    def tick(self, frameLength, cTerrain, player):
        if self.mode != "Spawn":
            if not self.canFly:
                self.ySpeed = min(0.4, self.ySpeed + 0.0015 * frameLength)

            for knockbackCircle in cTerrain.knockbackCircles:
                pow,x,y,r,falloff=knockbackCircle

                for lase in player.laser:
                    dx = self.x - x
                    dy = self.y - y
                    d = math.sqrt(dx ** 2 + dy ** 2)
                    if lase.laserTarget is self:
                        self.xSpeed += frameLength * dx / d / self.size * pow
                        self.ySpeed += frameLength * dy / d / self.size * pow
                    elif d < r+self.r:
                        self.xSpeed += frameLength * dx / d / self.size * pow * falloff
                        self.ySpeed += frameLength * dy / d / self.size * pow * falloff
            
            for damageCircle in cTerrain.playerDamageCircles:
                pow, x, y, r, falloff = damageCircle
                
                for lase in player.laser:
                    if lase.laserTarget is self:
                        cTerrain.particles.spawnMiningParticles(10, self.color, self.size/5, x, y)
                        if self.dealDamage(pow):
                            return True
                    else:
                        dx = self.x - x
                        dy = self.y - y
                        d = math.sqrt(dx ** 2 + dy ** 2)
                        if d < r + self.r:
                            cTerrain.particles.spawnMiningParticles(5, self.color, self.size/10, x, y)
                            if self.dealDamage(pow*falloff):
                                return True

            if self.x < 50:
                self.xSpeed += (50 - self.x) / 10000 * frameLength
            elif self.x > cTerrain.worldWidth - 50:
                self.xSpeed -= (self.x - cTerrain.worldWidth + 50) / 10000 * frameLength

            if self.mode == "Walk":
                if self.canFly:
                    if abs(player.x - self.x) > self.size / 2 or abs(player.y - self.y) > self.size / 2:
                        rand = random.randint(0, 3)
                        if (player.x < self.x and not rand == 3) or rand == 0:
                            self.xSpeed -= 0.0003 * frameLength * self.speed
                        else:
                            self.xSpeed += 0.0003 * frameLength * self.speed
                        rand = random.randint(0, 3)
                        if (player.y < self.y and not rand == 3) or rand == 0:
                            self.ySpeed -= 0.0003 * frameLength * self.speed
                        else:
                            self.ySpeed += 0.0003 * frameLength * self.speed
                        self.xSpeed *= 0.995 ** frameLength
                        self.ySpeed *= 0.995 ** frameLength
                    else:
                        self.mode = "Attack"
                        self.animationTimer = 0
                else:
                    if player.y < self.y - 10 and self.onGround and random.randint(1, 500) < frameLength:
                        self.ySpeed = -0.3
                    if abs(player.x - self.x) > self.size / 2 or abs(player.y - self.y) > self.size / 2:
                        rand = random.randint(0, 3)
                        if (player.x < self.x and not rand == 3) or rand == 0:
                            if self.onGround:
                                self.xSpeed -= 0.001 * frameLength * self.speed
                            else:
                                self.xSpeed -= 0.0003 * frameLength * self.speed
                        else:
                            if self.onGround:
                                self.xSpeed += 0.001 * frameLength * self.speed
                            else:
                                self.xSpeed += 0.0003 * frameLength * self.speed
                    else:
                        self.mode = "Attack"
                        self.animationTimer = 0

                    if self.onGround:
                        self.xSpeed *= 0.98 ** frameLength
                    else:
                        self.xSpeed *= 0.993 ** frameLength

            self.moveVertical(frameLength, cTerrain)
            self.moveHorizontal(frameLength, cTerrain)

            if player.immunityTimer == 0 and self.mode == "Attack" and self.animationFrame in self.attackFrames:
                if self.attackCollideRect(player.rect):
                    player.immunityTimer = player.immunityTime
                    if self.facing == "Right":
                        player.xSpeed = 0.3
                    else:
                        player.xSpeed = -0.3
                    player.ySpeed = -0.3
                    player.dealDamage(self.damage)

            if math.dist((self.x, self.y), (player.x, player.y)) > 500:
                return True

        self.updateCostume(frameLength, player)

        return False

    def moveHorizontal(self, frameLength, cTerrain):
        self.x += frameLength * self.xSpeed
        self.updateRect()
        if self.collidingWithTerrain(cTerrain):
            slopeTolerance = math.ceil(3 * abs(frameLength * self.xSpeed))
            for i in range(slopeTolerance):
                self.y -= 1
                self.updateRect()
                if not self.collidingWithTerrain(cTerrain):
                    if self.xSpeed > 0:
                        self.xSpeed -= self.xSpeed * i / slopeTolerance
                    else:
                        self.xSpeed -= self.xSpeed * i / slopeTolerance
                    return
            self.y += slopeTolerance
            self.x -= frameLength * self.xSpeed
            backs = math.ceil(abs(frameLength * self.xSpeed / 1))
            for i in range(backs):
                self.x += frameLength * self.xSpeed / backs
                self.updateRect()
                if self.collidingWithTerrain(cTerrain):
                    self.x -= frameLength * self.xSpeed / backs
                    self.updateRect()
                    break
            self.xSpeed = 0

    def moveVertical(self, frameLength, cTerrain):
        self.onGround = False
        self.y += frameLength * self.ySpeed
        self.updateRect()
        if self.collidingWithTerrain(cTerrain):
            if self.ySpeed > 0:
                self.onGround = True
                if not cTerrain.nestsCollideRect(self.rect):
                    cTerrain.particles.spawnMiningParticles(int(abs((abs(max(0.005 * frameLength, abs(self.xSpeed))) - 0.005 * frameLength) + 3 * (self.ySpeed - 0.0015 * frameLength)) * 12), (0, 0, 0), 20, self.x, self.y + self.height / 2, time=200)
            if self.ySpeed < 0:
                slopeTolerance = math.ceil(abs(0.5 * frameLength * self.ySpeed))
                for i in range(slopeTolerance):
                    self.x -= 1
                    self.updateRect()
                    if not self.collidingWithTerrain(cTerrain):
                        return
                self.x += slopeTolerance
                for i in range(slopeTolerance):
                    self.x += 1
                    self.updateRect()
                    if not self.collidingWithTerrain(cTerrain):
                        return
                self.x -= slopeTolerance
            self.y -= frameLength * self.ySpeed
            backs = math.ceil(abs(frameLength * self.ySpeed / 1))
            for i in range(backs):
                self.y += frameLength * self.ySpeed / backs
                self.updateRect()
                if self.collidingWithTerrain(cTerrain):
                    self.y -= frameLength * self.ySpeed / backs
                    self.updateRect()
                    break
            self.ySpeed = 0

    def collidingWithTerrain(self, cTerrain):
        return cTerrain.collideRect(self.rect)

    def attackCollideRect(self, rect: pygame.Rect):
        rectMask = pygame.Mask((rect.width, rect.height), fill=True)
        surface = pygame.Surface((rect.width, rect.height), flags=pygame.SRCALPHA)
        self.drawAttackHitbox(surface, [rect.left, rect.y, 1])
        attackMask = pygame.mask.from_surface(surface)
        return not (attackMask.overlap(rectMask, (0, 0)) == None)