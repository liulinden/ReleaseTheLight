# imports
from asset_manager import get_asset
import pygame, random, terrain, decoration, aplayer, lighting, math, os, time, enemies, nest, laser, gateway, UI, loading_screen
from util import rotateAndGetOffset

class World:
    def __init__(self, worldWidth, worldHeight, loading_screen: loading_screen.LoadingScreen, defaultZooms=[0.1, 2], developingMode=False):
        self.worldWidth   = worldWidth
        self.worldHeight  = worldHeight
        self.defaultZooms = defaultZooms
        self.developingMode = developingMode

        init_loading_screen, objects_loading_screen, generate_loading_screen = loading_screen.subsections(0, 0.25, 0.5)

        inits = [lighting.init, enemies.init, nest.init, terrain.init, aplayer.init, laser.init, gateway.init, UI.init]

        for i, init in enumerate(inits):
            init_loading_screen.put((i + 1) / len(inits), f"{init.__module__}.{init.__name__}()")
            init()

        self.decorations = []

        objects_loading_screen.put(0.5, "Creating terrain object")
        self.terrain = terrain.Terrain(worldWidth, worldHeight, defaultZooms=defaultZooms)
        objects_loading_screen.put(0.6, "Creating player object")
        self.player = aplayer.Player(defaultZooms, worldWidth / 2, -200 if developingMode else -1200)
        objects_loading_screen.put(0.7, "Creating lighting object")
        self.light  = lighting.Lighting(defaultZooms=defaultZooms)
        objects_loading_screen.put(0.8, "Creating background surface")
        background_raw   = get_asset("Background")
        self.background  = pygame.transform.scale(background_raw, (4000, 4000))
        self.bg_width, self.bg_height = self.background.get_size()
        objects_loading_screen.put(0.9, "Creating foreground surface")
        foreground_raw   = get_asset("Foreground")
        self.foreground  = pygame.transform.scale(foreground_raw, (10000, 10000))
        self.fg_width, self.fg_height = self.foreground.get_size()
        objects_loading_screen.put(1.0, "Object creation complete.")

        self._world_layer      = None
        self._world_layer_size = None
        self.scratch_layer = None

        self.generateWorld(generate_loading_screen)

    def generateWorld(self, loading_screen):
        self.terrain.generateLayer(0, loading_screen)

    def generateNextLayer(self):
        self.terrain.generateLayer(1)

    def _getWorldLayer(self, real_window_size):
        if self._world_layer is None or self._world_layer_size != real_window_size:
            self._world_layer = pygame.Surface(real_window_size)
            self._world_layer_size = real_window_size
            self.scratch_layer = pygame.Surface(real_window_size)
        return self._world_layer, self.scratch_layer

    def addAirPocket(self, x, y, radius):
        # player-mined pockets go into the layer the player is currently in
        layerIndex = self.terrain._layerForY(self.player.y)
        self.terrain.addAirPocket(x, y, radius, layerIndex=layerIndex, playerMade=True)

    def healNests(self):
        for li in range(terrain.NUM_LAYERS):
            for n in self.terrain.nests[li]:
                if n.health > 0:
                    n.health = n.maxHealth
                    n.stage  = 0

    def removeEnemies(self):
        for li in range(terrain.NUM_LAYERS):
            for n in self.terrain.nests[li]:
                n.enemies.clear()

    def tick(self, FPS, window_size, frame, mousePos, keysDown, events):
        left, top, zoom = frame
        frameLength = 1000 / FPS

        # update which layers are active this frame
        self.terrain.updateActiveLayers(self.player.y)

        self.terrain.newKnockbackCircles    = []
        self.terrain.newPlayerDamageCircles = []

        if self.player.tick(frameLength, self.terrain, mousePos, keysDown, events):
            return True

        if random.randint(1, math.ceil(FPS / 7)) == 1:
            self.light.addMistParticle(self.player.x, self.player.y, color=self.player.color)
        for lase in self.player.laser:
            if random.randint(1, math.ceil(FPS / max(1, lase.length) * 25)) == 1:
                mistPos = random.random()
                self.light.addMistParticle(
                    lase.startX + mistPos * lase.length * math.cos(lase.angle),
                    lase.startY + mistPos * lase.length * math.sin(lase.angle),
                    color=self.player.color)

        w_width, w_height = window_size
        w_r = math.sqrt(w_width ** 2 + w_height ** 2) / 2 / zoom
        x, y = left + w_width / zoom / 2, top + w_height / zoom / 2

        # tick gateways
        for lase in self.player.laser:
            if self.terrain.playerDamageCircles and lase.collision:
                lx,ly=lase.collision[0]
                for gw in self.terrain.gateways:
                    if gw.tick(self.terrain, self.player, lx,ly):
                        self.terrain.particles.spawnMiningParticles(10, (255,255,255), 10, lx,ly)
                        break

        # active nests only
        for li in self.terrain.activeLayers:
            for n in self.terrain.nests[li]:
                n.updateVisuals(frameLength)
                if self.terrain.playerDamageCircles:
                    for particleCoords in n.applyDamageFromCircles(self.terrain, self.player):
                        self.terrain.particles.spawnMiningParticles(
                            10, n.color, particleCoords[2], particleCoords[0], particleCoords[1])

                if n.stage != n.maxStage:
                    ndx  = self.player.x - n.x
                    ndy  = self.player.y - n.y
                    d_sq = ndx * ndx + ndy * ndy
                    if d_sq < 300 * 300 and random.randint(1, int(200 + 0.1 * int(math.sqrt(d_sq) / 2) ** 2)) < frameLength:
                        n.addEnemy(self.terrain, self.player)
                    for i in range(len(n.enemies) - 1, -1, -1):
                        enemy = n.enemies[i]
                        if enemy.tick(frameLength, self.terrain, self.player):
                            del n.enemies[i]

                if random.randint(1, math.ceil(FPS / 6)) == 1 and n.close(x, y, w_r) and n.stage == n.maxStage:
                    self.light.addMistParticle(n.x, n.y, color=n.color)

        self.light.tickEffects(frameLength)
        self.terrain.particles.tickParticles(frameLength)

        self.terrain.knockbackCircles    = self.terrain.newKnockbackCircles
        self.terrain.playerDamageCircles = self.terrain.newPlayerDamageCircles

        return False

    def drawBackground(self, layer, window_size, frame):
        left, top, zoom = frame
        x = (-left * zoom) % self.bg_width/2  - self.bg_width/2
        y = (-top  * zoom) % self.bg_height/2 - self.bg_height/2
        layer.blit(self.background, (x, y))
    
    def drawForeground(self,layer,window_size,frame):
        left, top, zoom = frame
        x = (-left*6 * zoom) % self.fg_width/2  - self.fg_width/2
        y = ((-top*6+500)  * zoom) % self.fg_height/2 - self.fg_height/2
        layer.blit(self.foreground, (x, y))

    def getSurface(self, window_size, frame, hitboxes=False, kindVisibility=False,
                   real_window_size=None, offset_x=0, offset_y=0, tilt=0, crosshair=False):
        if real_window_size is None:
            real_window_size = window_size

        layer, scratchLayer = self._getWorldLayer(real_window_size)

        if kindVisibility:
            layer.fill((200, 200, 200))
        else:
            self.terrain.drawDepthBackground(layer, frame, offset_x=offset_x, offset_y=offset_y)

        

        self.light.drawEffects(layer, frame, offset_x=offset_x, offset_y=offset_y)

        self.light.drawGradient(layer, frame, self.player.color,
                                self.player.x, self.player.y,
                                offset_x=offset_x, offset_y=offset_y)
        if self.player.laser:
            if self.player.laser[0].collision:
                cx, cy = self.player.laser[0].collision[0]
                self.light.drawGradient(layer, frame, self.player.color, cx, cy,
                                        offset_x=offset_x, offset_y=offset_y)

        self.terrain.drawNestGradients(window_size, layer, frame,
                                       offset_x=offset_x, offset_y=offset_y)

        

        self.drawBackground(scratchLayer, window_size, frame)

        # gateway back elements (behind terrain)
        for gw in self.terrain.gateways:
            gw.drawBack(scratchLayer, frame, offset_x=offset_x, offset_y=offset_y)
        
        layer.blit(scratchLayer,(0,0),special_flags=pygame.BLEND_RGB_MULT)

        self.player.draw(layer, frame, hitboxes=hitboxes,
                         offset_x=offset_x, offset_y=offset_y, tilt=tilt)

        self.terrain.drawEnemies(window_size, layer, frame, hitboxes=hitboxes,
                                 offset_x=offset_x, offset_y=offset_y)

        self.terrain.particles.drawParticles(layer, frame,
                                             offset_x=offset_x, offset_y=offset_y)

        self.terrain.drawNests(window_size, layer, frame, hitboxes=hitboxes,
                               offset_x=offset_x, offset_y=offset_y)

        self.terrain.drawTerrain(window_size, layer, frame, hitboxes=hitboxes,
                                 real_window_size=real_window_size,
                                 offset_x=offset_x, offset_y=offset_y)

        # gateway front elements (after terrain)
        for gw in self.terrain.gateways:
            gw.draw(layer, frame, offset_x=offset_x, offset_y=offset_y)
        
        self.terrain.drawHealthBars(window_size, layer, frame, pygame.time.get_ticks(),offset_x=offset_x,offset_y=offset_y)

        self.drawForeground(scratchLayer, window_size, frame)
        self.light.drawThickGradient(scratchLayer,frame,self.player.x, self.player.y, offset_x=offset_x, offset_y=offset_y) 
        layer.blit(self.scratch_layer, (0,0), special_flags=pygame.BLEND_MULT)

        if crosshair:
            pygame.draw.line(layer, (100, 100, 100, 0.3), (real_window_size[0]*0.45, real_window_size[1]//2), (real_window_size[0]*0.55, real_window_size[1]//2), 2)
            pygame.draw.line(layer, (100, 100, 100, 0.3), (real_window_size[0]//2, real_window_size[1]*0.45), (real_window_size[0]//2, real_window_size[1]*0.55), 2)

        if tilt != 0:
            layer, cx, cy = rotateAndGetOffset(layer, real_window_size[0]/2, real_window_size[1]/2, math.radians(tilt))
            layer.blit(layer, (cx, cy))

        if crosshair:
            size = 10
            pygame.draw.line(layer, (255, 0, 0), (real_window_size[0]//2 - size, real_window_size[1]//2), (real_window_size[0]//2 + size, real_window_size[1]//2), 2)
            pygame.draw.line(layer, (255, 0, 0), (real_window_size[0]//2, real_window_size[1]//2 - size), (real_window_size[0]//2, real_window_size[1]//2 + size), 2)
                

        return layer