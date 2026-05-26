# imports
import pygame, random, terrain, decoration, aplayer,lighting,math,os, time, enemies, nest, laser
import threading

# FIX 2: background loaded in World.__init__ after display exists (removed module-level load)
# All module init() calls are centralised here so the call order is clear:
#   pygame.display.set_mode() → World.__init__() → all init() → Terrain/Player/etc

def distance(coord1: int, coord2: int):
    x1, y1 = coord1
    x2, y2 = coord2
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


class World:

    # set up and create world
    def __init__(self, worldWidth, worldHeight, defaultZooms=[0.1,2], progress_queue=None):

        self.worldWidth = worldWidth
        self.worldHeight = worldHeight
        self.defaultZooms = defaultZooms

        # FIX 2: defer all image loads until after display exists.
        # Order matters: enemies.init() before nest.init() (nest imports enemies).
        lighting.init()
        enemies.init()
        nest.init()
        terrain.init()
        aplayer.init()
        laser.init(defaultZooms)

        self.terrain = terrain.Terrain(worldWidth, worldHeight, defaultZooms=defaultZooms)
        self.decorations = []
        self.player = aplayer.Player(defaultZooms, worldWidth / 2, -1200)
        self.light = lighting.Lighting(defaultZooms=defaultZooms)

        background_raw = pygame.image.load(os.path.join("assets", "Background.png")).convert()
        self.background = pygame.transform.scale(background_raw, (4000, 4000))
        self.bg_width, self.bg_height = self.background.get_size()

        # FIX 1: reusable world surface — allocated once, resized only if window changes
        self._world_layer = None
        self._world_layer_size = None

        self.generateWorld(progress_queue)

    # generate caves/nests/decorations
    def generateWorld(self, progress_queue=None):
        if progress_queue is None:
            self.terrain.generate()
        else:
            threading.Thread(target=self.terrain.generate, args=(progress_queue,), daemon=True).start()

    def _getWorldLayer(self, real_window_size):
        if self._world_layer is None or self._world_layer_size != real_window_size:
            self._world_layer = pygame.Surface(real_window_size)
            self._world_layer_size = real_window_size
        return self._world_layer

    def addAirPocket(self, x, y, radius):
        self.terrain.addAirPocket(x, y, radius)

    def healNests(self):
        for nest in self.terrain.nests:
            if nest.health > 0:
                nest.health = nest.maxHealth
                nest.stage = 0

    def removeEnemies(self):
        for nest in self.terrain.nests:
            # FIX 1 (minor): O(n²) remove loop → O(1) clear
            nest.enemies.clear()

    def tick(self, FPS, window_size, frame, mousePos, keysDown, events):
        left, top, zoom = frame
        frameLength = 1000 / FPS

        self.terrain.newKnockbackCircles = []
        self.terrain.newPlayerDamageCircles = []

        if self.player.tick(frameLength, self.terrain, mousePos, keysDown, events):
            return True

        if random.randint(1, math.ceil(FPS / 7)) == 1:
            self.light.addMistParticle(self.player.x, self.player.y, color=self.player.color)
        for lase in self.player.laser:
            if random.randint(1, math.ceil(FPS / max(1, lase.length) * 25)) == 1:
                mistPos = random.random()
                self.light.addMistParticle(lase.startX + mistPos * lase.length * math.cos(lase.angle), lase.startY + mistPos * lase.length * math.sin(lase.angle), color=self.player.color)

        w_width, w_height = window_size
        # FIX 1: cache window-diagonal radius — recompute only when zoom/window changes
        w_r = math.sqrt(w_width ** 2 + w_height ** 2) / 2 / zoom
        x, y = left + w_width / zoom / 2, top + w_height / zoom / 2

        for nest in self.terrain.nests:
            nest.updateVisuals(frameLength)
            for particleCoords in nest.applyDamageFromCircles(self.terrain, self.player):
                self.terrain.particles.spawnMiningParticles(10, nest.color, self.player.laserPower / 2, particleCoords[0], particleCoords[1])

            if nest.stage != nest.maxStage:
                d = distance((self.player.x, self.player.y), (nest.x, nest.y))
                if d < 300 and random.randint(1, int(200 + 0.1 * int(d / 2) ** 2)) < frameLength:
                    nest.addEnemy(self.terrain, self.player)
                for i in range(len(nest.enemies) - 1, -1, -1):
                    enemy = nest.enemies[i]
                    if enemy.tick(frameLength, self.terrain, self.player):
                        del nest.enemies[i]

            if random.randint(1, math.ceil(FPS / 6)) == 1 and nest.close(x, y, w_r) and nest.stage == nest.maxStage:
                self.light.addMistParticle(nest.x, nest.y, color=nest.color)

        self.light.tickEffects(frameLength)
        self.terrain.particles.tickParticles(frameLength)

        self.terrain.knockbackCircles = self.terrain.newKnockbackCircles
        self.terrain.playerDamageCircles = self.terrain.newPlayerDamageCircles

        return False

    def drawBackground(self, layer, window_size, frame):
        left, top, zoom = frame
        x = (-left * zoom) % self.bg_width/2 - self.bg_width/2
        y = (-top * zoom) % self.bg_height/2 - self.bg_height/2
        layer.blit(self.background, (x, y), special_flags=pygame.BLEND_RGB_MULT)

    def getSurface(self, window_size, frame, hitboxes=False, kindVisibility=False, real_window_size=None, offset_x=0, offset_y=0):
        if real_window_size is None:
            real_window_size = window_size

        # FIX 1: reuse world layer surface
        layer = self._getWorldLayer(real_window_size)

        if kindVisibility:
            layer.fill((200, 200, 200))
        else:
            self.terrain.drawDepthBackground(layer, frame, offset_x=offset_x, offset_y=offset_y)

        self.light.drawEffects(layer, frame, offset_x=offset_x, offset_y=offset_y)

        self.light.drawGradient(layer, frame, self.player.color, self.player.x, self.player.y, offset_x=offset_x, offset_y=offset_y)
        if self.player.laser:
            if self.player.laser[0].collision:
                x, y = self.player.laser[0].collision[0]
                self.light.drawGradient(layer, frame, self.player.color, x, y, offset_x=offset_x, offset_y=offset_y)

        self.terrain.drawNestGradients(window_size, layer, frame, offset_x=offset_x, offset_y=offset_y)

        self.drawBackground(layer, window_size, frame)

        self.player.draw(layer, frame, hitboxes=hitboxes, offset_x=offset_x, offset_y=offset_y)

        self.terrain.drawEnemies(window_size, layer, frame, hitboxes=hitboxes, offset_x=offset_x, offset_y=offset_y)

        self.terrain.particles.drawParticles(layer, frame, offset_x=offset_x, offset_y=offset_y)

        self.terrain.drawNests(window_size, layer, frame, hitboxes=hitboxes, offset_x=offset_x, offset_y=offset_y)

        self.terrain.drawTerrain(window_size, layer, frame, hitboxes=hitboxes, real_window_size=real_window_size, offset_x=offset_x, offset_y=offset_y)

        return layer