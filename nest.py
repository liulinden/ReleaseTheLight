import pygame, random, math, enemies, os, UI
from util import chargesToColor
from global_assets import get_asset


def loadNestIMGSet(id, stages):
    IMGs = []
    for i in range(stages):
        IMGs.append(get_asset("Nest" + str(id) + "_" + str(i + 1)))
    return IMGs, get_asset("Nest" + str(id) + "Hitbox")


# FIX 2: module-level lightGradient and nestIMGs loaded in init() after display exists
lightGradient = None
nestIMGs = {}
nestHitboxes = {}

def init():
    global lightGradient, nestIMGs, nestHitboxes
    lightGradient = get_asset("LightGradient")
    nestIMGs = {}
    nestHitboxes = {}
    for nestType, nStages, variants in [("white", 3, [1, 2, 3, 4]), ("blue", 4, [5, 6]), ("red", 4, [5, 6]), ("sun", 10, [])]:
        IMGsets = []
        hitboxes = []
        for variant in variants:
            IMGset, hitbox = loadNestIMGSet(variant, nStages)
            IMGsets.append(IMGset)
            hitboxes.append(hitbox)
        nestIMGs[nestType] = IMGsets
        nestHitboxes[nestType] = hitboxes


class Nest:
    def __init__(self, defaultZooms, worldHeight, nestType, x, y, size):
        self.x = x
        self.y = y
        self.left = x - size / 2
        self.top = y - size / 2
        self.nestType = nestType
        selection = nestIMGs[nestType]
        id = random.randint(0, len(selection) - 1)
        stageIMGs = selection[id]
        hitbox = nestHitboxes[nestType][id]
        self.size = size
        self.enemies = []
        self.basicEnemyCap = 1
        self.totalEnemyCap = min(max(3,int(size/30)),10)
        self.color = (255, 255, 255)
        self.glow = 0
        self.stage = 0
        self.maxStage = len(stageIMGs) - 1

        self.resizedHitboxes = {}
        self.resizedGradients = {}
        self.resizedIMGs = {}

        # FIX 1: pre-allocate filter surfaces for draw() and drawGradient() per zoom
        self._draw_filter = {}
        self._gradient_filter = {}

        for zoom in defaultZooms:
            IMGs = []
            for stageIMG in stageIMGs:
                IMGs.append(pygame.transform.scale(stageIMG, (size * zoom, size * zoom)))
            self.resizedIMGs[zoom] = IMGs
            self.resizedHitboxes[zoom] = pygame.transform.scale(hitbox, (size * zoom, size * zoom))
            grad_img = pygame.transform.scale(lightGradient, (size * zoom, size * zoom))
            self.resizedGradients[zoom] = grad_img

            self._draw_filter[zoom] = pygame.Surface((size * zoom, size * zoom), flags=pygame.SRCALPHA)
            self._gradient_filter[zoom] = pygame.Surface(grad_img.get_size(), flags=pygame.SRCALPHA)

        self.resizedHitboxes[1] = pygame.transform.scale(hitbox, (size, size))
        if 1 not in self._draw_filter:
            self._draw_filter[1] = pygame.Surface((size, size), flags=pygame.SRCALPHA)

        self.maxHealth = self.y * 200 * (random.random()+0.2) / worldHeight
        if self.nestType == "white":
            self.maxHealth *= 1.2
            self.maxHealth += 10
        elif self.nestType == "blue":
            self.maxHealth += 50
        elif self.nestType == "red":
            self.maxHealth += 50
        elif self.nestType == "sun":
            self.maxHealth += 1000

        self.health = self.maxHealth
        self.healthBar = UI.HealthBar(self.maxHealth)

        self.maxCharge = self.maxHealth / 3 + 100
        self.visualCharge = self.maxCharge
        self.charge = self.maxCharge * 0.5
        self.chargeRate = self.maxCharge / 10000
        self.charging = {"white":0,"blue":0,"red":0}
        self.charging[self.nestType]=1

    def getRect(self):
        return pygame.Rect(self.left, self.top, self.size, self.size)

    def updateColor(self):
        cw, cb, cr = self.charging.values()
        cw, cb, cr = cw * self.visualCharge, cb * self.visualCharge, cr * self.visualCharge

        self.color=chargesToColor(cw,cb,cr,500)
        
        # r, g, b = 0, 0, 0
        # r += cr + cw
        # g += cw + cb / 4
        # b += cw + cb

        # r = (min(r / 500, 1)) ** 0.3
        # g = (min(g / 500, 1)) ** 0.3
        # b = (min(b / 500, 1)) ** 0.3
        # self.color = (r * 255, g * 255, b * 255)

    def loseCharge(self, loss):
        self.glow = 255
        self.charge -= loss
        if self.charge < 0:
            self.charge = 0
            ...

    def updateVisuals(self, frameLength):
        if self.charge == 0 and self.visualCharge != 0:
            self.visualCharge -= frameLength / 10
            if self.visualCharge < 0:
                self.visualCharge = 0
        #self.visualCharge=self.charge
        self.glow += ((self.stage / self.maxStage * self.visualCharge / self.maxCharge * 150) - self.glow) / 1500 * frameLength

    def drawGradient(self, surface, frame, offset_x=0, offset_y=0):
        camX, camY, zoom = frame
        img = self.resizedGradients[zoom]
        if self.glow > 0:
            # FIX 1: reuse pre-allocated gradient filter surface
            filt = self._gradient_filter[zoom]
            filt.fill((self.color[0], self.color[1], self.color[2], self.glow))
            filt.blit(img, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(filt, ((self.left - camX) * zoom + offset_x, (self.top - camY) * zoom + offset_y))

    def draw(self, surface, frame, hitbox=False, offset_x=0, offset_y=0):
        camX, camY, zoom = frame

        if hitbox:
            img = self.resizedHitboxes[zoom]
        else:
            img = self.resizedIMGs[zoom][self.stage]

        self.updateColor()

        # FIX 1: reuse pre-allocated draw filter surface
        filt = self._draw_filter[zoom]
        filt.fill(self.color)
        filt.blit(img, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(filt, ((self.left - camX) * zoom + offset_x, (self.top - camY) * zoom + offset_y))
            
    def drawHealthBar(self,surface, frame, time=None, offset_x=0,offset_y=0):
        if self.stage != self.maxStage:
            camX, camY, zoom = frame 
            self.healthBar.draw(surface, self.color, ((self.x - camX) * zoom + offset_x, (self.top - camY) * zoom + offset_y), self.health,time)

    def addEnemy(self, cTerrain, player):
        if len(self.enemies) < self.basicEnemyCap:
            newEnemy = enemies.getEnemy(cTerrain, player, self.nestType, self.color, self.maxHealth, self.x, self.y, self.size)
            if newEnemy:
                self.glow = 200
                self.enemies.append(newEnemy)

    def withinEffectRadius(self, x, y):
        if math.dist((x, y), (self.x, self.y)) < self.size * 1.5:
            return True
        return False

    def applyDamageFromCircles(self, cTerrain, player):
        newParticles = []
        if self.health > 0:
            for circle in cTerrain.playerDamageCircles:
                pow, x, y, r, falloff = circle
                if self.close(x, y, r):
                    # direct hit: full damage; splash: reduced damage
                    directHit = any(lase.laserTarget is self for lase in player.laser)
                    damage = pow if directHit else pow*falloff
                    self.dealDamage(damage, cTerrain, player)
                    newParticles.append([x, y, self.size/(5 if directHit else 10)])
                    self.healthBar.trigger()
        return newParticles

    def dealDamage(self, damage, cTerrain, player):
        self.glow = 200
        self.health -= damage
        if self.health < 0:
            self.health = 0
            for enemy in self.enemies:
                enemy.spawnParticles(cTerrain)
            self.enemies = []
        elif len(self.enemies) < self.totalEnemyCap and random.randint(1, 4) == 1:
            newEnemy = enemies.getEnemy(cTerrain, player, self.nestType, self.color, self.maxHealth, self.x, self.y, self.size)
            if newEnemy:
                self.enemies.append(newEnemy)
        self.updateStage()

    def updateStage(self):
        self.stage = self.maxStage - math.ceil((self.maxStage - 1) * self.health / self.maxHealth)
        self.basicEnemyCap = math.floor(self.stage * 1.5)

    def close(self, x: int, y: int, radius: int):
        if abs(self.x - x) > radius + self.size / 2:
            return False
        if abs(self.y - y) > radius + self.size / 2:
            return False
        return True