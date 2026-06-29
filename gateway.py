import pygame, os, math
from structure import Structure
from UI import HealthBar

# ---------------------------------------------------------------------------
# Gateway Y positions — one per boundary between layers.
# 5 layers → 4 gateways. Adjust values to tune layer spacing.
# ---------------------------------------------------------------------------
GATEWAY_Y_POSITIONS = [5000, 10000, 15000, 20000,25000,30000,35000,40000,45000]

# ---------------------------------------------------------------------------
# Image storage — populated by init() after pygame.display.set_mode()
# ---------------------------------------------------------------------------
gatewayIMGs = {}   # keyed by tile type + state, e.g. "corridorclosed"
gatewayHitboxIMGs = {}  # keyed by tile type + state

def init():
    global gatewayIMGs, gatewayHitboxIMGs

    def load(name):
        return pygame.image.load(os.path.join("assets", name + ".png")).convert_alpha()

    # corridor
    gatewayIMGs["corridorclosed"]  = load("gateCorridorClosed")
    gatewayIMGs["corridoropened"]  = load("gateCorridorOpened")
    gatewayIMGs["corridorback"]    = load("gateCorridorErase")
    gatewayIMGs["corridorerase"]   = load("gateCorridorErase")    
    gatewayHitboxIMGs["corridor"]  = load("gateCorridorHitbox")
    gatewayHitboxIMGs["corridorerase"] = load("gateCorridorEraseHitbox")

    # entry
    gatewayIMGs["entryclosed"]     = load("gateEntryClosed")
    gatewayIMGs["entrycharging1"]  = load("gateEntryCharging1")
    gatewayIMGs["entrycharging2"]  = load("gateEntryCharging2")
    gatewayIMGs["entrycharging3"]  = load("gateEntryCharging3")
    gatewayIMGs["entryopened"]     = load("gateEntryOpened")
    gatewayIMGs["entryback"]       = load("gateEntryBack")
    gatewayIMGs["entryerase"]      = load("gateEntryErase")
    gatewayHitboxIMGs["entryerase"]   = load("gateEntryEraseHitbox")
    gatewayHitboxIMGs["entryclosed"]  = load("gateEntryClosedHitbox")
    gatewayHitboxIMGs["entryopened"]  = load("gateEntryOpenedHitbox")
    gatewayHitboxIMGs["activator"]    = load("gatewayActivatorHitbox")

    # exit
    gatewayIMGs["exitclosed"]      = load("gateExitClosed")
    gatewayIMGs["exitopened"]      = load("gateExitOpened")
    gatewayIMGs["exitback"]        = load("gateExitBack")
    gatewayIMGs["exiterase"]       = load("gateExitErase")
    gatewayHitboxIMGs["exit"]      = load("gateExitHitbox")
    gatewayHitboxIMGs["exiterase"] = load("gateExitEraseHitbox")


# ---------------------------------------------------------------------------
# Tile classes
# ---------------------------------------------------------------------------

_scaled_img__cache = {}
class GatewayTile(Structure):
    """Single tile in a gateway row. Width and height = visual_chunk_size."""


    def __init__(self, tileX, tileY, tileSize, defaultZooms):
        super().__init__(tileX + tileSize / 2, tileY + tileSize / 2,
                         tileSize, tileSize, defaultZooms)
        self.tileSize = tileSize
        self.tileLeft = tileX
        self.tileTop  = tileY
        # pre-scaled surfaces keyed by zoom
        self._hitboxSurfs = {}
        self._frontSurfs  = {}
        self._backSurfs   = {}
        self._eraseHitboxSurfs = {}
        self._eraseSurfs={}

    def _scaledIMG(self, img, zoom):
        size = int(self.tileSize * zoom)
        name = (id(img), size)
        if name not in _scaled_img__cache:
            _scaled_img__cache[name] = pygame.transform.scale(img, (size, size))
        return _scaled_img__cache[name]

    def getHitboxSurface(self, zoom):
        return self._hitboxSurfs.get(zoom)
    
    def getEraseSurface(self,zoom):
        return self._eraseSurfs.get(zoom)

    def getEraseHitboxSurface(self,zoom):
        return self._eraseHitboxSurfs.get(zoom)
        

    def draw(self, surface, frame, offset_x=0, offset_y=0):
        left, top, zoom = frame
        surf = self._frontSurfs.get(zoom)
        if surf:
            surface.blit(surf,
                ((self.tileLeft - left) * zoom + offset_x,
                 (self.tileTop  - top)  * zoom + offset_y))

    def drawBack(self, surface, frame, offset_x=0, offset_y=0):
        left, top, zoom = frame
        surf = self._backSurfs.get(zoom)
        if surf:
            surface.blit(surf,
                ((self.tileLeft - left) * zoom + offset_x,
                 (self.tileTop  - top)  * zoom + offset_y))

    def tick(self, frameLength, terrain, player):
        return False


class CorridorTile(GatewayTile):
    def __init__(self, tileX, tileY, tileSize, defaultZooms, opened=False):
        super().__init__(tileX, tileY, tileSize, defaultZooms)
        self.opened = opened
        self._buildSurfaces()

    def _buildSurfaces(self):
        state = "opened" if self.opened else "closed"
        for zoom in self.defaultZooms:
            self._hitboxSurfs[zoom] = self._scaledIMG(
                gatewayHitboxIMGs["corridor"], zoom)
            self._frontSurfs[zoom]  = self._scaledIMG(
                gatewayIMGs[f"corridor{state}"], zoom)
            self._backSurfs[zoom]   = self._scaledIMG(
                gatewayIMGs["corridorback"], zoom)
            self._eraseSurfs[zoom]   = self._scaledIMG(
                gatewayIMGs["corridorerase"], zoom)
            self._eraseHitboxSurfs[zoom]   = self._scaledIMG(
                gatewayHitboxIMGs["corridorerase"], zoom)

    def open(self):
        if not self.opened:
            self.opened = True
            self._buildSurfaces()


class ExitTile(GatewayTile):
    """Exit hitbox never changes — always solid regardless of gateway state."""
    def __init__(self, tileX, tileY, tileSize, defaultZooms, opened=False):
        super().__init__(tileX, tileY, tileSize, defaultZooms)
        self.opened = opened
        self._buildSurfaces()

    def _buildSurfaces(self):
        state = "opened" if self.opened else "closed"
        for zoom in self.defaultZooms:
            self._hitboxSurfs[zoom] = self._scaledIMG(
                gatewayHitboxIMGs["exit"], zoom)
            self._frontSurfs[zoom]  = self._scaledIMG(
                gatewayIMGs[f"exit{state}"], zoom)
            self._backSurfs[zoom]   = self._scaledIMG(
                gatewayIMGs["exitback"], zoom)
            self._eraseSurfs[zoom]   = self._scaledIMG(
                gatewayIMGs["exiterase"], zoom)
            self._eraseHitboxSurfs[zoom]   = self._scaledIMG(
                gatewayHitboxIMGs["exiterase"], zoom)

    def open(self):
        if not self.opened:
            self.opened = True
            self._buildSurfaces()


class EntryTile(GatewayTile):
    """Entry tile tracks charge independently. Once fully charged it notifies
    the parent Gateway which then unlocks all tiles."""

    # charge thresholds for visual stages (fraction of maxCharge)
    STAGE_THRESHOLDS = [0.0, 0.01, 0.5, 1.0]

    def __init__(self, tileX, tileY, tileSize, defaultZooms, maxCharge,
                 opened=False):
        super().__init__(tileX, tileY, tileSize, defaultZooms)
        self.maxCharge = maxCharge
        self.charge    = 0.0
        self.opened    = opened
        self.chargeStage = 0   # 0=closed, 1-3=charging stages, 4=opened
        self.gateway   = None  # set by Gateway after construction

        # pre-scale activator hitbox at zoom=1 for laser detection
        self._activatorHitbox = pygame.transform.scale(
            gatewayHitboxIMGs["activator"],
            (int(tileSize), int(tileSize)))

        self._buildSurfaces()
        self.healthBar = HealthBar(self.maxCharge)

    def _buildSurfaces(self):
        for zoom in self.defaultZooms:
            if self.opened:
                self._hitboxSurfs[zoom] = self._scaledIMG(
                    gatewayHitboxIMGs["entryopened"], zoom)
                self._frontSurfs[zoom]  = self._scaledIMG(
                    gatewayIMGs["entryopened"], zoom)
            else:
                self._hitboxSurfs[zoom] = self._scaledIMG(
                    gatewayHitboxIMGs["entryclosed"], zoom)
                stage = self.chargeStage  # 0–3
                if stage == 0:
                    img = gatewayIMGs["entryclosed"]
                else:
                    img = gatewayIMGs[f"entrycharging{stage}"]
                self._frontSurfs[zoom] = self._scaledIMG(img, zoom)
            self._backSurfs[zoom] = self._scaledIMG(
                gatewayIMGs["entryback"], zoom)
            self._eraseSurfs[zoom]   = self._scaledIMG(
                gatewayIMGs["entryerase"], zoom)
            self._eraseHitboxSurfs[zoom]   = self._scaledIMG(
                gatewayHitboxIMGs["entryerase"], zoom)

    def isLaserHittingActivator(self, wx, wy):
        """Precise check: is world point (wx,wy) inside the activator sub-region?"""
        lx = int(wx - self.tileLeft)
        ly = int(wy - self.tileTop)
        if 0 <= lx < int(self.tileSize) and 0 <= ly < int(self.tileSize):
            return self._activatorHitbox.get_at((lx, ly))[3] > 128
        return False

    def addCharge(self, amount):
        """Add charge. Returns True if gateway should now unlock."""
        if self.opened:
            return False
        self.charge = min(self.maxCharge, self.charge + amount)
        # update visual stage
        newStage = 0
        for i, thresh in enumerate(self.STAGE_THRESHOLDS):
            if self.charge / self.maxCharge >= thresh:
                newStage = i
        if newStage != self.chargeStage:
            self.chargeStage = newStage
            self._buildSurfaces()
        #print(self.charge, self.maxCharge)
        return self.charge >= self.maxCharge

    def open(self):
        if not self.opened:
            self.opened = True
            self._buildSurfaces()
    
    def drawHealthBar(self,surface, frame, time=None, offset_x=0,offset_y=0):
        camX, camY, zoom = frame 
        self.healthBar.draw(surface, (255,255,255), ((self.x - camX +40) * zoom + offset_x, (self.top - camY) * zoom + offset_y), self.charge,time)


# ---------------------------------------------------------------------------
# Gateway — one horizontal row of tiles
# ---------------------------------------------------------------------------

class Gateway:
    """A full-width horizontal gateway at a fixed Y position.
    Composed of CorridorTiles, EntryTiles, and ExitTiles.
    Entry positions and exit positions are supplied at construction time."""

    def __init__(self, gatewayIndex, worldWidth, tileSize, defaultZooms,
                 entryColumns, exitColumns, maxChargePerEntry):
        self.gatewayIndex  = gatewayIndex
        self.y             = GATEWAY_Y_POSITIONS[gatewayIndex]
        self.tileSize      = tileSize
        self.defaultZooms  = defaultZooms
        self.unlocked      = False
        self.onUnlock      = None   # callback set by terrain: called when unlocked

        numTiles = math.ceil(worldWidth / tileSize)
        self.tiles = []

        for col in range(numTiles):
            tileX = col * tileSize
            tileY = self.y - tileSize / 2  # gateway row centred on self.y
            if col in exitColumns:
                tile = ExitTile(tileX, tileY, tileSize, defaultZooms)
            elif col in entryColumns:
                tile = EntryTile(tileX, tileY, tileSize, defaultZooms,
                                 maxChargePerEntry)
                tile.gateway = self
            else:
                tile = CorridorTile(tileX, tileY, tileSize, defaultZooms)
            self.tiles.append(tile)

        self.entryTiles = [t for t in self.tiles if isinstance(t, EntryTile)]
        self.exitTiles  = [t for t in self.tiles if isinstance(t, ExitTile)]

    def tick(self, frameLength, terrain, lx,ly,laserPower):
        """Check laser hits on activators each frame. Returns True if activator is hit."""
        for entry in self.entryTiles:
            if entry.isLaserHittingActivator(lx,ly):
                if not self.unlocked:
                    if entry.addCharge(laserPower):
                        self._unlock(terrain)
                    entry.healthBar.trigger()
                return True
        return False

    def _unlock(self, terrain):
        self.unlocked = True
        for tile in self.tiles:
            tile.open()
        # rebuild chunk hitboxes for all affected tiles
        for tile in self.tiles:
            terrain.reblitStructureOnChunks(tile)
        if self.onUnlock:
            self.onUnlock(self.gatewayIndex)

    def getFirstLockedY(self):
        """Y position of this gateway if locked, else None."""
        return self.y if not self.unlocked else None

    def draw(self, surface, frame, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w = surface.get_width()
        h = surface.get_height()
        # cull tiles outside view
        viewLeft  = left - self.tileSize
        viewRight = left + w / zoom + self.tileSize
        for tile in self.tiles:
            if tile.tileLeft < viewRight and tile.tileLeft + tile.tileSize > viewLeft:
                tile.draw(surface, frame, offset_x=offset_x, offset_y=offset_y)

    def drawBack(self, surface, frame, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w = surface.get_width()
        viewLeft  = left - self.tileSize
        viewRight = left + w / zoom + self.tileSize
        for tile in self.tiles:
            if tile.tileLeft < viewRight and tile.tileLeft + tile.tileSize > viewLeft:
                tile.drawBack(surface, frame, offset_x=offset_x, offset_y=offset_y)