from asset_manager import get_asset
import pygame, random, math, nest, particles, os, time, threading, time
from gateway import GATEWAY_Y_POSITIONS, Gateway
from loading_screen import LoadingScreen

NUM_LAYERS = 10

hitbox_chunk_size = 125
max_airpocket_radius = 120
visual_chunk_size = 500
rocks_world_span = 8 * hitbox_chunk_size

# Placeholder charge required to unlock each gateway (index = gateway index)
GATEWAY_CHARGE = [100, 200, 300, 500, 700, 900, 1000, 1200, 1500]

PALETTES = [
            [
                (0.0, (120,  100,  65)),
                (0.5, (60,  55,  65)),
                (1.0, (70,  20,  60))
            ],
            [
                (0.0, (30,  20,  30)),
                (0.5, (10, 10, 10)),
                (0.55, (50,  70,  100)),
                (0.6, (15, 10, 20)),
                (1.0, (10,10,10))
            ],
            [
                (0.0, (70,  100,  240)),
                (0.65, (0,  64,  255)),
                (0.7, (200, 50, 60)),
                (0.75, (100,  120,  255)),
                (1.0, (20,  62,  250))
            ],
            [
                (0.0, (255,  55,  65)),
                (0.4, (180,  40,  60)),
                (0.45, (60,  200,  255)),
                (0.5, (200,  55,  100)),
                (1.0, (170,  60,  150))
            ],
            [
                (0.0, (200,  55,  150)),
                (0.5, (10,  10,  10)),
                (1.0, (150,  55,  200))
            ],
            [
                (0.0, (60,  55,  65)),
                (1.0, (60,  55,  65))
            ],
            [
                (0.0, (60,  55,  65)),
                (1.0, (60,  55,  65))
            ],
            [
                (0.0, (60,  55,  65)),
                (1.0, (60,  55,  65))
            ],
            [
                (0.0, (60,  55,  65)),
                (1.0, (60,  55,  65))
            ],
            [
                (0.0, (60,  55,  65)),
                (1.0, (255,  255,  255))
            ]
        ]


# load images — call terrain.init() after pygame.display.set_mode()
airIMGs = {}
circleIMGs = []
airHitboxIMGs = {}
rocksIMG = {}
vignetteIMG = None

def init():
    global airIMGs, circleIMGs, airHitboxIMGs, rocksIMG, vignetteIMG
    circleIMGs = []
    for i in range(4):
        circleIMGs.append(get_asset("AirPocket" + str(i + 1)))
    airIMGs["Circle"] = circleIMGs
    for customPocket in ["C1"]:
        airIMGs[customPocket] = [get_asset("AirPocket" + customPocket)]
        airHitboxIMGs[customPocket] = get_asset("AirPocket" + customPocket + "Hitbox")
    rocks_raw = get_asset("Rocks")
    rocksIMG["raw"] = rocks_raw
    vignetteIMG = get_asset("VignetteGradient")

def rectToCircle(left, top, width, height):
    return left + width / 2, top + height / 2, math.dist((0, 0), (width, height)) / 2


def _layerYBounds(layerIndex, worldHeight):
    """Return (yTop, yBottom) world-space Y range for a layer."""
    yTop    = GATEWAY_Y_POSITIONS[layerIndex - 1] if layerIndex > 0 else 0
    yBottom = GATEWAY_Y_POSITIONS[layerIndex] if layerIndex < NUM_LAYERS - 1 else worldHeight
    return yTop, yBottom

def worldYtoLayerY(worldY):
    for i in range(NUM_LAYERS-1):
        if worldY <= GATEWAY_Y_POSITIONS[i]:
            if i==0:
                return(worldY,0)
            return worldY-(GATEWAY_Y_POSITIONS)[i-1], i
    return worldY-(GATEWAY_Y_POSITIONS)[NUM_LAYERS-2], NUM_LAYERS-1

def chooseUniqueRandoms(n: int, low: int, high: int, excluded = []) -> list[int]:
    nums = set()
    excluded = set(excluded)
    while len(nums) < n:
        nums.add(random.randint(low, high))
        nums = nums - excluded
    return list(nums)


_GRID_CELL = max_airpocket_radius * 2

def _gridCell(x, y):
    return (int(x // _GRID_CELL), int(y // _GRID_CELL))

def _gridNeighbours(cx, cy):
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            yield (cx + dc, cy + dr)

_scaled_img_cache: dict = {}
_RADIUS_SNAP = 10

def _snapRadius(r: float) -> int:
    return int(round(r / _RADIUS_SNAP) * _RADIUS_SNAP)

def _getCachedScale(src_surface, pocketType, imgIndex, radius, zoom):

    key = (pocketType, imgIndex, radius, zoom)

    if key not in _scaled_img_cache:
        side = max(1, int(2 * radius * zoom))
        cached = pygame.transform.scale(src_surface, (side, side))
        _scaled_img_cache[key] = cached

    return _scaled_img_cache[key]


def _getCachedRimScale(src_surface, pocketType, imgIndex, radius, zoom):

    key = (pocketType, imgIndex, radius, zoom, "rim")

    if key not in _scaled_img_cache:
        side = max(1, int(2 * radius * zoom * Terrain._RIM_MULT))
        cached = pygame.transform.scale(src_surface, (side, side))
        cached.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MULT)
        _scaled_img_cache[key] = cached

    return _scaled_img_cache[key]
class Terrain:

    def __init__(self, worldWidth: int, worldHeight: int, defaultZooms: list = [0.1, 2]):

        self.knockbackCircles = []
        self.newKnockbackCircles = []
        self.playerDamageCircles = []
        self.newPlayerDamageCircles = []

        # nests and airPockets keyed by layer index
        self.nests      = {i: [] for i in range(NUM_LAYERS)}
        self.airPockets = {i: [] for i in range(NUM_LAYERS)}

        self._airGrid: dict[int, dict[tuple, list]] = {i: {} for i in range(NUM_LAYERS)}

        # active layers for iteration — updated every frame
        self.activeLayers = [0]

        # per-layer generation locks and completion tracking
        self._layerLocks      = {i: threading.Lock() for i in range(NUM_LAYERS)}
        self._generatedLayers = set()

        self.worldWidth   = worldWidth
        self.worldHeight  = worldHeight
        self.defaultZooms = defaultZooms
        self.particles    = particles.Particles()

        # gateways
        self.gateways = []
        for gi in range(NUM_LAYERS - 1):
            numTiles  = math.ceil(worldWidth / visual_chunk_size)
            nExits = random.randint(math.ceil(numTiles/4),math.ceil(numTiles/2))
            nEntries = random.randint(1,math.ceil((numTiles-nExits)/2))
            entryCols = chooseUniqueRandoms(nEntries,1,numTiles-2)
            exitCols  = chooseUniqueRandoms(nExits,1,numTiles-2,entryCols)
            gw = Gateway(gi, worldWidth, visual_chunk_size, defaultZooms,
                         entryColumns=entryCols, exitColumns=exitCols,
                         maxChargePerEntry=GATEWAY_CHARGE[gi])
            gw.onUnlock = self._onGatewayUnlock
            self.gateways.append(gw)

        # chunk surfaces
        self.airPocketsSurfaces = {}
        self.airPocketsHitboxesSurfaces = {}
        self.chunkVisuals  = {}
        self.chunkHitboxes = {}

        for zoom in defaultZooms:
            self.airPocketsSurfaces[zoom] = []
            for row in range(math.ceil(worldHeight / 500) + 1):
                rowList = []
                for j in range(math.ceil(worldWidth / 500)):
                    rowList.append(pygame.Surface((500 * zoom, 500 * zoom), pygame.SRCALPHA))
                self.airPocketsSurfaces[zoom].append(rowList)

        for zoom in defaultZooms:
            self.airPocketsHitboxesSurfaces[zoom] = []
            for row in range(math.ceil(worldHeight / hitbox_chunk_size) + 1):
                rowList = []
                for j in range(math.ceil(worldWidth / hitbox_chunk_size)):
                    surf = pygame.Surface((hitbox_chunk_size * zoom, hitbox_chunk_size * zoom), pygame.SRCALPHA)
                    # surf.fill((0,0,0,255)) probable not needed
                    rowList.append(surf)
                self.airPocketsHitboxesSurfaces[zoom].append(rowList)

        for zoom in defaultZooms:
            self.chunkVisuals[zoom] = []
            for row in range(math.ceil(worldHeight / visual_chunk_size) + 1):
                rowList = []
                for col in range(math.ceil(worldWidth / visual_chunk_size)):
                    surf =pygame.Surface((visual_chunk_size * zoom, visual_chunk_size * zoom), pygame.SRCALPHA)
                    # surf.fill((0,0,0,255)) probable not needed
                    rowList.append(surf)
                self.chunkVisuals[zoom].append(rowList)

        self._rocksScaled = {}
        for zoom in defaultZooms:
            scaled_span = int(rocks_world_span * zoom)
            self._rocksScaled[zoom] = pygame.transform.scale(rocksIMG["raw"], (scaled_span, scaled_span))

        for zoom in defaultZooms:
            self.chunkHitboxes[zoom] = []
            for row in range(math.ceil(worldHeight / hitbox_chunk_size) + 1):
                rowList = []
                for col in range(math.ceil(worldWidth / hitbox_chunk_size)):
                    rowList.append(pygame.Surface((hitbox_chunk_size * zoom, hitbox_chunk_size * zoom), pygame.SRCALPHA))
                self.chunkHitboxes[zoom].append(rowList)

        self._terrain_layer          = None
        self._terrain_layer_size     = None
        self._collide_scratch        = pygame.Surface((512, 512), pygame.SRCALPHA)
        self._collide_scratch_hitbox = pygame.Surface((512, 512), pygame.SRCALPHA)
        self._vignetteSurf           = None
        self._vignetteSize           = None
        self._vignette_stencil       = None
        self._vignette_stencil_size  = None

    # ------------------------------------------------------------------
    # Active layer management
    # ------------------------------------------------------------------

    def updateActiveLayers(self, playerY):
        """Called each frame from world.tick(). Updates self.activeLayers."""
        currentLayer = self._layerForY(playerY)
        yTop, yBottom = _layerYBounds(currentLayer, self.worldHeight)
        layerMid = (yTop + yBottom) / 2
        if playerY < layerMid and currentLayer > 0:
            adjacent = currentLayer - 1
        elif playerY >= layerMid and currentLayer < NUM_LAYERS - 1:
            adjacent = currentLayer + 1
        else:
            adjacent = None
        layers = [currentLayer]
        if adjacent is not None and adjacent in self._generatedLayers:
            layers.append(adjacent)
        self.activeLayers = layers

    def _layerForY(self, y):
        for i, gy in enumerate(GATEWAY_Y_POSITIONS):
            if y < gy:
                return i
        return NUM_LAYERS - 1

    def getFirstLockedGatewayY(self):
        for gw in self.gateways:
            if not gw.unlocked:
                return gw.y
        return self.worldHeight

    def _activeNests(self) -> list[nest.Nest]:
        result = []
        for li in self.activeLayers:
            result.extend(self.nests[li])
        return result

    def _activeAirPockets(self):
        result = []
        for li in self.activeLayers:
            result.extend(self.airPockets[li])
        return result

    # ------------------------------------------------------------------
    # Gateway unlock callback
    # ------------------------------------------------------------------

    def _onGatewayUnlock(self, gatewayIndex):
        nextLayer = gatewayIndex + 2
        if nextLayer < NUM_LAYERS and nextLayer not in self._generatedLayers:
            def _generate():
                with self._layerLocks[nextLayer - 1]:
                    pass
                print("layer generating - ", nextLayer)
                self.generateLayer(nextLayer)
            threading.Thread(target=_generate, daemon=True).start()

    # ------------------------------------------------------------------
    # Structure collision baking
    # ------------------------------------------------------------------

    def reblitStructureOnChunks(self, structure, erase=True):
        for zoom in self.defaultZooms:
            eraseHitboxSurf = structure.getEraseHitboxSurface(zoom)
            hitboxSurf = structure.getHitboxSurface(zoom)
            if hitboxSurf is None:
                continue
            colStart = max(0, math.floor(structure.left / hitbox_chunk_size) - 1)
            colEnd   = min(len(self.chunkHitboxes[zoom][0]) - 1,
                           math.ceil((structure.left + structure.width) / hitbox_chunk_size))
            rowStart = max(0, math.floor(structure.top / hitbox_chunk_size) - 1)
            rowEnd   = min(len(self.chunkHitboxes[zoom]) - 1,
                           math.ceil((structure.top + structure.height) / hitbox_chunk_size))
            for row in range(rowStart, rowEnd + 1):
                for col in range(colStart, colEnd + 1):
                    chunkLeft = col * hitbox_chunk_size
                    chunkTop  = row * hitbox_chunk_size
                    if erase and eraseHitboxSurf:
                        self.chunkHitboxes[zoom][row][col].blit(
                        eraseHitboxSurf,
                        (zoom * (structure.left - chunkLeft),
                         zoom * (structure.top  - chunkTop)),
                         special_flags=pygame.BLEND_RGBA_SUB
                        )
                    self.chunkHitboxes[zoom][row][col].blit(
                        hitboxSurf,
                        (zoom * (structure.left - chunkLeft),
                         zoom * (structure.top  - chunkTop)),
                         special_flags=pygame.BLEND_RGBA_MAX
                    )

    def _bakeGatewayIntoChunks(self, gateway):
        for tile in gateway.tiles:
            self.reblitStructureOnChunks(tile, True)

    # ------------------------------------------------------------------
    # Surface helpers
    # ------------------------------------------------------------------

    def _getTerrainLayerSurface(self, real_window_size):
        if self._terrain_layer is None or self._terrain_layer_size != real_window_size:
            self._terrain_layer = pygame.Surface(real_window_size, pygame.SRCALPHA)
            self._terrain_layer_size = real_window_size
        self._terrain_layer.fill((255, 255, 255, 255))
        return self._terrain_layer

    # ------------------------------------------------------------------
    # Air pocket / nest surface methods
    # ------------------------------------------------------------------

    def addAirPocketToSurfaces(self, airPocket):
        baseRow = math.floor(airPocket.y / 500)
        baseCol = math.floor(airPocket.x / 500)
        for dRow in range(-1, 2):
            for dCol in range(-1, 2):
                row = baseRow + dRow
                col = baseCol + dCol
                if row >= 0 and col >= 0 and row <= self.worldHeight / 500 and col < self.worldWidth / 500:
                    left, top = col * 500, row * 500
                    for zoom in self.defaultZooms:
                        self.airPocketsSurfaces[zoom][row][col].blit(
                            airPocket.IMGs[zoom],
                            (zoom * (airPocket.left - left), zoom * (airPocket.top - top))
                        )
                    if self.chunkVisuals:
                        for zoom in self.defaultZooms:
                            if row < len(self.chunkVisuals[zoom]) and col < len(self.chunkVisuals[zoom][row]):
                                self._carveVisualChunk(airPocket, row, col, zoom)

        baseRow = math.floor(airPocket.y / hitbox_chunk_size)
        baseCol = math.floor(airPocket.x / hitbox_chunk_size)
        affectedChunks = []
        for dRow in range(-1, 2):
            for dCol in range(-1, 2):
                row = baseRow + dRow
                col = baseCol + dCol
                if row >= 0 and col >= 0 and row <= self.worldHeight / hitbox_chunk_size and col < self.worldWidth / hitbox_chunk_size:
                    left, top = col * hitbox_chunk_size, row * hitbox_chunk_size
                    for zoom in self.defaultZooms:
                        if airPocket.type == "Circle":
                            pygame.draw.circle(
                                self.airPocketsHitboxesSurfaces[zoom][row][col],
                                (255, 255, 255),
                                (zoom * (airPocket.x - left), zoom * (airPocket.y - top)),
                                airPocket.r * zoom
                            )
                        else:
                            self.airPocketsHitboxesSurfaces[zoom][row][col].blit(
                                airPocket.hitboxIMGs[zoom],
                                (zoom * (airPocket.left - left), zoom * (airPocket.top - top))
                            )
                        if airPocket.type == "Circle":
                            pygame.draw.circle(
                                self.chunkHitboxes[zoom][row][col],
                                (255, 255, 255, 255),
                                (zoom * (airPocket.x - left), zoom * (airPocket.y - top)),
                                airPocket.r * zoom
                            )
                            self.chunkHitboxes[zoom][row][col].blit(
                                self.airPocketsHitboxesSurfaces[zoom][row][col],
                                (0, 0), special_flags=pygame.BLEND_RGBA_SUB
                            )
                        else:
                            self.chunkHitboxes[zoom][row][col].blit(
                                airPocket.hitboxIMGs[zoom],
                                (zoom * (airPocket.left - left), zoom * (airPocket.top - top)),
                                special_flags=pygame.BLEND_RGBA_SUB
                            )
                    affectedChunks.append((row, col))

        for row, col in affectedChunks:
            self._reblitSolidStructuresOnChunk(row, col)

    def addNestToHitboxSurfaces(self, newNest):
        for zoom in self.defaultZooms:
            img      = newNest.resizedHitboxes[zoom]
            nestLeft = newNest.left
            nestTop  = newNest.top
            nestSize = newNest.size
            colStart = max(0, math.floor(nestLeft / hitbox_chunk_size) - 1)
            colEnd   = min(math.ceil(self.worldWidth  / hitbox_chunk_size) - 1,
                           math.ceil((nestLeft + nestSize) / hitbox_chunk_size))
            rowStart = max(0, math.floor(nestTop  / hitbox_chunk_size) - 1)
            rowEnd   = min(math.ceil(self.worldHeight / hitbox_chunk_size),
                           math.ceil((nestTop  + nestSize) / hitbox_chunk_size))
            for row in range(rowStart, rowEnd + 1):
                for col in range(colStart, colEnd + 1):
                    if row < len(self.airPocketsHitboxesSurfaces[zoom]) and col < len(self.airPocketsHitboxesSurfaces[zoom][row]):
                        chunkLeft = col * hitbox_chunk_size
                        chunkTop  = row * hitbox_chunk_size
                        offset = (zoom * (nestLeft - chunkLeft), zoom * (nestTop - chunkTop))
                        if self.chunkHitboxes[zoom] and row < len(self.chunkHitboxes[zoom]) and col < len(self.chunkHitboxes[zoom][row]):
                            self.chunkHitboxes[zoom][row][col].blit(img, offset, special_flags=pygame.BLEND_RGBA_MAX)

    def _reblitSolidStructuresOnChunk(self, row, col):
        """Re-blit all solid structures (nests + gateway tiles) onto a chunk after mining."""
        chunkLeft   = col * hitbox_chunk_size
        chunkTop    = row * hitbox_chunk_size
        chunkRight  = chunkLeft + hitbox_chunk_size
        chunkBottom = chunkTop  + hitbox_chunk_size
        for n in self._activeNests():
            if (n.left < chunkRight and n.left + n.size > chunkLeft and
                    n.top < chunkBottom and n.top + n.size > chunkTop):
                for zoom in self.defaultZooms:
                    self.chunkHitboxes[zoom][row][col].blit(
                        n.resizedHitboxes[zoom],
                        (zoom * (n.left - chunkLeft), zoom * (n.top - chunkTop)),
                        special_flags=pygame.BLEND_RGBA_MAX
                    )
        for gw in self.gateways:
            for tile in gw.tiles:
                if (tile.left < chunkRight and tile.left + tile.width > chunkLeft and
                        tile.top < chunkBottom and tile.top + tile.height > chunkTop):
                    for zoom in self.defaultZooms:
                        hitboxSurf = tile.getHitboxSurface(zoom)
                        if hitboxSurf:
                            self.chunkHitboxes[zoom][row][col].blit(
                                hitboxSurf,
                                (zoom * (tile.left - chunkLeft), zoom * (tile.top - chunkTop)),
                                special_flags=pygame.BLEND_RGBA_MAX
                            )

    def carveStructuresVisualAir(self, layerTop=0):
        structures = []
        for gw in self.gateways:
            structures.extend(gw.tiles)
        for zoom in self.defaultZooms:
            for structure in structures:
                if structure.top + structure.height > layerTop:
                    eraseSurf = structure.getEraseSurface(zoom)
                    if eraseSurf is None:
                        continue
                    colStart = max(0, math.floor(structure.left / visual_chunk_size) - 1)
                    colEnd   = min(len(self.chunkVisuals[zoom][0]) - 1,
                                math.ceil((structure.left + structure.width) / visual_chunk_size))
                    rowStart = max(0, math.floor(structure.top / visual_chunk_size) - 1)
                    rowEnd   = min(len(self.chunkVisuals[zoom]) - 1,
                                math.ceil((structure.top + structure.height) / visual_chunk_size))
                    for row in range(rowStart, rowEnd + 1):
                        for col in range(colStart, colEnd + 1):
                            chunkLeft = col * visual_chunk_size
                            chunkTop  = row * visual_chunk_size
                            self.chunkVisuals[zoom][row][col].blit(
                            eraseSurf,
                            (zoom * (structure.left - chunkLeft),
                            zoom * (structure.top  - chunkTop)),
                            special_flags=pygame.BLEND_RGBA_SUB
                            )

    # ------------------------------------------------------------------
    # Noise / colour
    # ------------------------------------------------------------------

    def _noiseVal(self, x, y, scale=1.0):
        x, y = x * scale, y * scale
        v  =  math.sin(x * 0.017 + y * 0.011) * 0.4
        v +=  math.cos(x * 0.031 - y * 0.023) * 0.3
        v +=  math.sin(x * 0.053 + y * 0.047 + 1.3) * 0.2
        v +=  math.cos(x * 0.079 - y * 0.061 + 2.7) * 0.1
        return max(-1.0, min(1.0, v))

    def _depthColor(self, worldX, worldY):
        layerY, layer = worldYtoLayerY(worldY)
        top, bottom= _layerYBounds(layer,self.worldHeight)

        depth = max(0.0, min(1.0, layerY / (bottom-top)))
        noise = self._noiseVal(worldX, worldY) * 0.3
        d = max(0.0, min(1.0, depth + noise))
        
        palette = PALETTES[layer]
        for i in range(len(palette) - 1):
            d0, c0 = palette[i]
            d1, c1 = palette[i + 1]
            if d <= d1:
                t = (d - d0) / (d1 - d0)
                r = int(c0[0] + (c1[0] - c0[0]) * t)
                g = int(c0[1] + (c1[1] - c0[1]) * t)
                b = int(c0[2] + (c1[2] - c0[2]) * t)
                return (r, g, b)
        return palette[-1][1]

    def _makeGradientSurf(self, tl, tr, bl, br, width, height):
        surf = pygame.Surface((2, 2))
        surf.set_at((0, 0), tl)
        surf.set_at((1, 0), tr)
        surf.set_at((0, 1), bl)
        surf.set_at((1, 1), br)
        return pygame.transform.smoothscale(surf, (width, height))

    # ------------------------------------------------------------------
    # Chunk building (per-layer)
    # ------------------------------------------------------------------

    _RIM_MULT = 1.7

    def _buildChunkHitboxesForLayer(self, layerIndex):
        yTop, yBottom = _layerYBounds(layerIndex, self.worldHeight)
        for zoom in self.defaultZooms:
            airChunks = self.airPocketsHitboxesSurfaces[zoom]
            rowStart  = math.floor(yTop    / hitbox_chunk_size)
            rowEnd    = math.ceil (yBottom / hitbox_chunk_size)
            for row in range(rowStart, min(rowEnd + 1, len(self.chunkHitboxes[zoom]))):
                for col, chunk in enumerate(self.chunkHitboxes[zoom][row]):
                    chunk.fill((255, 255, 255, 255))
                    chunk.blit(airChunks[row][col], (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
            for n in self.nests[layerIndex]:
                self._blitNestOnChunkHitboxes(n, zoom)
        for gw in self.gateways:
            if gw.y - visual_chunk_size / 2 < yBottom and gw.y + visual_chunk_size / 2 > yTop:
                self._bakeGatewayIntoChunks(gw)

    def _blitNestOnChunkHitboxes(self, n, zoom):
        img      = n.resizedHitboxes[zoom]
        colStart = max(0, math.floor(n.left / hitbox_chunk_size) - 1)
        colEnd   = min(len(self.chunkHitboxes[zoom][0]) - 1,
                       math.ceil((n.left + n.size) / hitbox_chunk_size))
        rowStart = max(0, math.floor(n.top / hitbox_chunk_size) - 1)
        rowEnd   = min(len(self.chunkHitboxes[zoom]) - 1,
                       math.ceil((n.top + n.size) / hitbox_chunk_size))
        for row in range(rowStart, rowEnd + 1):
            for col in range(colStart, colEnd + 1):
                chunkLeft = col * hitbox_chunk_size
                chunkTop  = row * hitbox_chunk_size
                self.chunkHitboxes[zoom][row][col].blit(
                    img, (zoom * (n.left - chunkLeft), zoom * (n.top - chunkTop)),
                    special_flags=pygame.BLEND_RGBA_MAX
                )

    def _buildChunkVisualsForLayer(self, layerIndex, loading_screen: LoadingScreen=None):
        yTop, yBottom   = _layerYBounds(layerIndex, self.worldHeight)
        layerPockets    = self.airPockets[layerIndex]
        for i, zoom in enumerate(self.defaultZooms):
            airChunks      = self.airPocketsSurfaces[zoom]
            rocks          = self._rocksScaled[zoom]
            rocks_span_px  = int(rocks_world_span * zoom)
            chunk_px       = int(visual_chunk_size * zoom)
            rowStart       = math.floor(yTop    / visual_chunk_size)
            rowEnd         = min(math.ceil(yBottom / visual_chunk_size), len(self.chunkVisuals[zoom]) - 1)
            totalRows      = rowEnd - rowStart

            if loading_screen is not None:
                loading_bar_section = loading_screen.subsection(i / len(self.defaultZooms), (i + 1) / len(self.defaultZooms))
            else:
                loading_bar_section = None

            for row in range(rowStart, rowEnd):
                if loading_bar_section is not None:
                    loading_bar_section.put((row - rowStart + 1) / totalRows, f"Build chunk visuals row {row - rowStart + 1}/{totalRows} ({zoom=})")

                for col, chunk in enumerate(self.chunkVisuals[zoom][row]):
                    world_left  = col * visual_chunk_size
                    world_top   = row * visual_chunk_size
                    world_right = world_left + visual_chunk_size
                    world_bot   = world_top  + visual_chunk_size

                    tl = self._depthColor(world_left,  world_top)
                    tr = self._depthColor(world_right, world_top)
                    bl = self._depthColor(world_left,  world_bot)
                    br = self._depthColor(world_right, world_bot)

                    chunk.fill((0, 0, 0, 255))
                    chunk.blit(self._makeGradientSurf(tl, tr, bl, br, chunk_px, chunk_px),
                               (0, 0), special_flags=pygame.BLEND_RGB_MAX)

                    rock_x    = int((world_left * zoom) % rocks_span_px)
                    rock_y    = int((world_top  * zoom) % rocks_span_px)
                    rock_surf = pygame.Surface((chunk_px, chunk_px))
                    for ty in range(-rock_y, chunk_px, rocks_span_px):
                        for tx in range(-rock_x, chunk_px, rocks_span_px):
                            rock_surf.blit(rocks, (tx, ty))
                    chunk.blit(rock_surf, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

                    rim_margin = visual_chunk_size * self._RIM_MULT
                    for airPocket in layerPockets:
                        if (airPocket.x + airPocket.r * self._RIM_MULT < world_left - rim_margin or
                                airPocket.x - airPocket.r * self._RIM_MULT > world_right + rim_margin or
                                airPocket.y + airPocket.r * self._RIM_MULT < world_top  - rim_margin or
                                airPocket.y - airPocket.r * self._RIM_MULT > world_bot  + rim_margin):
                            continue
                        rim_surf = airPocket.rimIMGs[zoom]
                        cx = zoom * (airPocket.x - world_left)
                        cy = zoom * (airPocket.y - world_top)
                        rim_size = rim_surf.get_size()
                        chunk.blit(rim_surf, (int(cx - rim_size[0] / 2), int(cy - rim_size[1] / 2)))

                    chunk.blit(airChunks[row][col], (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
        self.carveStructuresVisualAir(yTop)

    # ------------------------------------------------------------------
    # Per-layer generation entry point
    # ------------------------------------------------------------------

    def generateLayer(self, layerIndex, loading_screen: LoadingScreen = None):
        """Generate one layer. Thread-safe. Layer 0 threads layer 1 on completion."""

        print(f"{time.strftime('%H:%M:%S')} - layer {layerIndex} generating...")

        if loading_screen is not None:
            loading_screen_main, loading_screen_visuals = loading_screen.subsections(0, 0.5)
        else:
            loading_screen_main = loading_screen_visuals = None

        with self._layerLocks[layerIndex]:

            if loading_screen_main is not None:
                loading_screen_main.put(0, "Generating master caves")

            yTop, yBottom = _layerYBounds(layerIndex, self.worldHeight)

            if layerIndex == 0:
                x = -500
                while x < self.worldWidth + 500:
                    r = random.randint(10, 30)
                    self.addAirPocketClump(x, 0, r, layerIndex=layerIndex, playerMade=True)
                    x += r / 2
                self.generateDescendingCave(self.worldWidth/2,0,40,math.pi/2,layerIndex=layerIndex)
            else:
                self.generateDescendingCave(int((random.random()+0.5)/2*self.worldWidth),yTop+20,30,math.pi/2,layerIndex=layerIndex)
                for exit in self.gateways[layerIndex-1].exitTiles:
                    self.generateSkinnyCave(exit.x,exit.y+exit.tileSize/4,50,math.pi/2,layerIndex=layerIndex)

            for entry in self.gateways[layerIndex].entryTiles:
                self.generateSkinnyCave(entry.x,entry.y-entry.tileSize/4,90,-math.pi/2,10,layerIndex=layerIndex)
            

            numSteps = int((yBottom - yTop) / 100)
            for i in range(numSteps):
                if loading_screen_main is not None:
                    loading_screen_main.put((i + 1) / numSteps, f"Generate layer section {i + 1}/{numSteps}")
                for j in range(int(self.worldWidth / 1000)):
                    if random.randint(1, 20) == 1:
                        self.generateSkinnyCave(j * 1000 + random.randint(0, 1000),
                            random.randint(int(yTop), int(yTop + (yBottom - yTop) / 3)),
                            random.randint(20, 60), random.random() * 2 * math.pi, layerIndex=layerIndex)
                    if random.randint(1, 20) == 1:
                        self.generateSkinnyCave(j * 1000 + random.randint(0, 1000),
                            random.randint(int(yTop + (yBottom - yTop) / 4), int(yBottom)),
                            random.randint(30, 90), random.random() * 2 * math.pi, layerIndex=layerIndex)
                    if random.randint(1, 35) == 1:
                        self.generateBlobCave(j * 1000 + random.randint(0, 1000),
                            random.randint(int(yTop + (yBottom - yTop) / 4), int(yBottom)),
                            random.randint(30, 60), random.random() * 2 * math.pi, layerIndex=layerIndex)
                    if random.randint(1, 20) == 1:
                        self.generateBlobCave(j * 1000 + random.randint(0, 1000),
                            random.randint(int(yTop + (yBottom - yTop) * 2 / 3), int(yBottom)),
                            random.randint(60, 120), random.random() * 2 * math.pi, layerIndex=layerIndex)

                    if layerIndex < 2:
                        if random.randint(1, 5) == 1:
                            self.generateNest(j * 1000 + random.randint(0, 1000),
                                random.randint(int(yTop + 500), int(yBottom-500)),
                                "white", layerIndex=layerIndex)
                    else:
                        if random.randint(1, 15) == 1:
                            self.generateNest(j * 1000 + random.randint(0, 1000),
                                random.randint(int(yTop + 500), int(yBottom-500)),
                                "white", layerIndex=layerIndex)

                    if layerIndex == 2:
                        if random.randint(1, 6) == 1:
                            self.generateNest(j * 1000 + random.randint(0, 1000),
                                random.randint(int(yTop + 500), int(yBottom-500)),
                                "blue", layerIndex=layerIndex)
                    elif layerIndex > 2:
                        if random.randint(1, 12) == 1:
                            self.generateNest(j * 1000 + random.randint(0, 1000),
                                random.randint(int(yTop + 500), int(yBottom-500)),
                                "blue", layerIndex=layerIndex)
                    if layerIndex == 3:
                        if random.randint(1, 6) == 1:
                            self.generateNest(j * 1000 + random.randint(0, 1000),
                                random.randint(int(yTop + 500), int(yBottom-500)),
                                "red", layerIndex=layerIndex)
                    elif layerIndex > 3:
                        if random.randint(1, 12) == 1:
                            self.generateNest(j * 1000 + random.randint(0, 1000),
                                random.randint(int(yTop + 500), int(yBottom-500)),
                                "red", layerIndex=layerIndex)

            self._buildChunkHitboxesForLayer(layerIndex)
            self._buildChunkVisualsForLayer(layerIndex, loading_screen=loading_screen_visuals)
            self._generatedLayers.add(layerIndex)

            print(f"{time.strftime('%H:%M:%S')} - layer {layerIndex} generation complete.")

            if loading_screen is not None:
                loading_screen.put(1, "Layer generation complete")

    # ------------------------------------------------------------------
    # Cave / nest generation helpers
    # ------------------------------------------------------------------

    def generateNest(self, x, y, nestType, layerIndex, size=0):
        yTop, yBottom = _layerYBounds(layerIndex, self.worldHeight)
        y = max(yTop + max_airpocket_radius, min(yBottom - max_airpocket_radius, y))
        if size == 0:
            size = random.randint(100, 100 + (y * 150) // self.worldHeight)
        newNest = nest.Nest(self.defaultZooms, self.worldHeight, nestType, x, y, size)
        rect = newNest.getRect()
        for cnest in self.nests[layerIndex]:
            if rect.colliderect(cnest.getRect()):
                return False
        self.nests[layerIndex].append(newNest)
        self.addNestToHitboxSurfaces(newNest)
        caveSize = (size * random.randint(0, 2) / 3 + 80) / 3
        if caveSize > 15:
            self.generateSkinnyCave(x, y - caveSize / 2, caveSize, -math.pi / 2,
                                    maxPockets=10, shrinking=True, layerIndex=layerIndex)
        else:
            self.addAirPocketClump(x, y - caveSize / 2, caveSize, layerIndex=layerIndex)
        return True

    def generateBlobCave(self, startX, startY, startR, startDir=0, maxPockets=10, layerIndex=0):
        yTop, yBottom = _layerYBounds(layerIndex, self.worldHeight)
        if maxPockets > 0 and (startY - 2 * startR) > yTop and startY - startR < yBottom and startR > 0:
            self.addAirPocketClump(startX, startY, startR, layerIndex=layerIndex)
            for i in range(2):
                r   = startR + (random.random() - 0.6) * 20
                dir = startDir + (random.random() - 0.5) * math.pi
                x   = startX + math.cos(dir) * min(r, startR) * 0.8
                y   = startY + math.sin(dir) * min(r, startR) * 0.8 * 0.2
                self.generateBlobCave(x, y, r, dir, maxPockets - 1, layerIndex=layerIndex)
                if random.randint(1, 15) > 1:
                    break

    def generateSkinnyCave(self, startX, startY, startR, startDir=0, maxPockets=20,
                           shrinking=False, layerIndex=0):
        yTop, yBottom = _layerYBounds(layerIndex, self.worldHeight)
        if maxPockets > 0 and (startY - 2 * startR) > yTop and startY - startR < yBottom and startR > 0:
            self.addAirPocketClump(startX, startY, startR, layerIndex=layerIndex)
            for i in range(2):
                r   = startR + (random.random() - 0.6) * 5
                if shrinking:
                    r = startR - random.random() * 2
                dir = startDir + (random.random() - 0.5) * math.pi / 2
                x   = startX + math.cos(dir) * min(r, startR) * 0.8
                y   = startY + math.sin(dir) * min(r, startR) * 0.8 * 0.8
                self.generateSkinnyCave(x, y, r, dir, maxPockets - 1,
                                        shrinking=shrinking, layerIndex=layerIndex)
                if random.randint(1, 30) > 1:
                    break
    
    def generateDescendingCave(self, startX, startY, startR, startDir=0, layerIndex=0):
        yTop, yBottom = _layerYBounds(layerIndex, self.worldHeight)
        if startY - startR < yBottom:
            boundedX=abs(math.fmod(startX,2*self.worldWidth)-self.worldWidth)
            self.addAirPocketClump(boundedX, startY, startR, layerIndex=layerIndex)
            if startY>yTop+600 and startY<yBottom-600 and random.randint(1,100)==1:
                #change white to selected randomly from list based on layerindex
                self.generateNest(boundedX,startY+random.randint(-100,100),"white",layerIndex=layerIndex)

            r   = min(50, max(10,startR+random.randint(-5,5)))
            dir = startDir + (random.random() - 0.5) * math.pi / 2
            x   = startX + int(math.cos(dir) * min(r, startR) * 0.8)
            y   = startY + int(abs(math.sin(dir)) * min(r, startR) * 0.5)
            self.generateDescendingCave(x, y, r, dir, layerIndex=layerIndex)

    def generateBedrockCave(self, startX, startY, startR, startDir=0, maxPockets=3, layerIndex=0):
        yTop, yBottom = _layerYBounds(layerIndex, self.worldHeight)
        if maxPockets > 0 and (startY - 2 * startR) > yTop and startY - startR < yBottom and startR > 0:
            self.addAirPocketClump(startX, startY, startR, layerIndex=layerIndex)
            for i in range(2):
                r   = startR + (random.random() - 0.6) * 20
                dir = startDir + (random.random() - 0.5) * math.pi / 2
                x   = startX + math.cos(dir) * min(r, startR) * 0.7
                y   = startY + math.sin(dir) * min(r, startR) * 0.7 * 0.5
                self.generateBedrockCave(x, y, r, dir, maxPockets - 1, layerIndex=layerIndex)
                if random.randint(1, 30) > 1:
                    break

    def addAirPocketClump(self, x, y, radius, layerIndex=0, playerMade=False, spreading=1/3):
        spreading = radius * spreading
        for i in range(3):
            self.addAirPocket(
                x + spreading * (random.random() * 2 - 1),
                y + spreading * (random.random() * 2 - 1),
                radius, layerIndex=layerIndex, playerMade=playerMade
            )

    def addAirPocket(self, x, y, radius, layerIndex=0, recursions=0, playerMade=False):
        radius = min(radius, max_airpocket_radius)
        yTop, yBottom = _layerYBounds(layerIndex, self.worldHeight)
        if (not playerMade and x - radius < 0) or (
                recursions > 3 or x + radius > self.worldWidth or x - radius < 0
                or y < yTop or y > yBottom):
            return False

        # ── Fast overlap check via spatial grid ────────────────────────────
        cx, cy = _gridCell(x, y)
        if not playerMade:
            for cell in _gridNeighbours(cx, cy):
                bucket = self._airGrid[layerIndex].get(cell)
                if bucket is None:
                    continue
                for airPocket in bucket:
                    dx = airPocket.x - x
                    dy = airPocket.y - y
                    # Quick AABB rejection before sqrt
                    combined = airPocket.r + radius + 10
                    if abs(dx) > combined or abs(dy) > combined:
                        continue
                    d = math.sqrt(dx * dx + dy * dy)
                    if d < radius / 4:
                        return False
                    if airPocket.r + radius < d < airPocket.r + radius + 10:
                        return self.addAirPocket(
                            (airPocket.x + x) / 2, (airPocket.y + y) / 2,
                            (airPocket.r + radius) / 2,
                            layerIndex=layerIndex, recursions=recursions + 1
                        )
        # ──────────────────────────────────────────────────────────────────

        if (not playerMade) and random.randint(1, 10) == 1:
            newAirPocket = AirPocket(x, y, radius, defaultZooms=self.defaultZooms, pocketType="C1")
        else:
            newAirPocket = AirPocket(x, y, radius, defaultZooms=self.defaultZooms)

        self.airPockets[layerIndex].append(newAirPocket)

        # Register in spatial grid
        self._airGrid[layerIndex].setdefault((cx, cy), []).append(newAirPocket)

        self.addAirPocketToSurfaces(newAirPocket)
        return True

    # ------------------------------------------------------------------
    # Vignette / carve
    # ------------------------------------------------------------------

    def drawVignette(self, surface, window_size, offset_x=0, offset_y=0):
        w, h = window_size
        if self._vignetteSurf is None or self._vignetteSize != window_size:
            self._vignetteSurf = pygame.transform.smoothscale(vignetteIMG, (w, h))
            self._vignetteSize = window_size
        surface.blit(self._vignetteSurf, (offset_x, offset_y), special_flags=pygame.BLEND_RGB_MULT)

    def _carveVisualChunk(self, airPocket, row, col, zoom):
        left, top = col * visual_chunk_size, row * visual_chunk_size
        chunk = self.chunkVisuals[zoom][row][col]
        if airPocket.type == "Circle":
            pygame.draw.circle(
                chunk, (0, 0, 0, 0),
                (int(zoom * (airPocket.x - left)), int(zoom * (airPocket.y - top))),
                int(airPocket.r * zoom)
            )
        else:
            eraser = pygame.Surface(airPocket.IMGs[zoom].get_size(), pygame.SRCALPHA)
            eraser.fill((0, 0, 0, 0))
            chunk.blit(eraser, (zoom * (airPocket.left - left), zoom * (airPocket.top - top)))

    # ------------------------------------------------------------------
    # Collision
    # ------------------------------------------------------------------

    def rayCastGround(self, startX, startY, angle, maxLength):
        chunks    = self.airPocketsHitboxesSurfaces[1]
        chunkRows = len(chunks)
        chunkCols = len(chunks[0]) if chunkRows > 0 else 0
        dx = math.cos(angle);  dy = math.sin(angle)
        step = 2;  dist = 0
        while dist < maxLength:
            wx = startX + dx * dist;  wy = startY + dy * dist
            if wx < 0 or wx >= self.worldWidth or wy < 0 or wy >= self.worldHeight:
                return wx, wy, dist
            col = int(wx // hitbox_chunk_size);  row = int(wy // hitbox_chunk_size)
            if row >= chunkRows or col >= chunkCols:
                return wx, wy, dist
            pixel = chunks[row][col].get_at((int(wx % hitbox_chunk_size), int(wy % hitbox_chunk_size)))
            if pixel[0] < 128:
                return wx, wy, dist
            dist += step
        return None, None, maxLength

    def _getScratch(self, w, h):
        w, h = int(math.ceil(w)), int(math.ceil(h))
        if w > self._collide_scratch.get_width() or h > self._collide_scratch.get_height():
            newW = max(w, self._collide_scratch.get_width())
            newH = max(h, self._collide_scratch.get_height())
            self._collide_scratch = pygame.Surface((newW, newH), pygame.SRCALPHA)
        self._collide_scratch.fill((0, 0, 0, 0), pygame.Rect(0, 0, w, h))
        return self._collide_scratch

    def _sampleChunk(self, wx, wy):
        if wy < 0:
            return False
        if wx < 0 or wx >= self.worldWidth or wy >= self.worldHeight:
            return True
        chunks = self.chunkHitboxes[1]
        col = int(wx // hitbox_chunk_size);  row = int(wy // hitbox_chunk_size)
        if row >= len(chunks) or col >= len(chunks[0]):
            return True
        px = max(0, min(int(hitbox_chunk_size - 1), int(wx % hitbox_chunk_size)))
        py = max(0, min(int(hitbox_chunk_size - 1), int(wy % hitbox_chunk_size)))
        return chunks[row][col].get_at((px, py))[0] > 128
    
    def _sampleChunkVisuals(self, wx, wy):
        if wy < 0:
            return False
        if wx < 0 or wx >= self.worldWidth or wy >= self.worldHeight:
            return True
        chunks = self.chunkVisuals[1]
        col = int(wx // visual_chunk_size);  row = int(wy // visual_chunk_size)
        if row >= len(chunks) or col >= len(chunks[0]):
            return True
        px = max(0, min(int(visual_chunk_size - 1), int(wx % visual_chunk_size)))
        py = max(0, min(int(visual_chunk_size - 1), int(wy % visual_chunk_size)))
        return chunks[row][col].get_at((px, py))[3] > 128

    def _sampleRect(self, rect):
        l = float(rect.left);  r = float(rect.right - 1)
        t = float(rect.top);   b = float(rect.bottom - 1)
        #step = (b - t) / 9
        step=1
        for i in range(math.floor(b-t)):
            y = t + step * i
            if self._sampleChunk(l, y) or self._sampleChunk(r, y):
                return True
        for i in range(math.floor(r-l)):
            x = l + step * i
            if self._sampleChunk(x, b) or self._sampleChunk(x, t):
                return True
        return False

    def collideRect(self, rect):
        return self._sampleRect(rect)

    def laserCollidePoint(self, x, y):
        # the two below are somewhat redundant
        # samplechunkvisuals ensures all bits of visual terrain interact with laser, and samplechunk takes care of nests.
        # in the future would have this function identify the laser target, because that is currently also done in a separate redundant function
        if self._sampleChunkVisuals(x,y):
            return True
        if self._sampleChunk(x,y):
            return True
        for n in self._activeNests():
            for enemy in n.enemies:
                if enemy.mode != "Spawn" and enemy.rect.collidepoint(x,y):
                    return True
        return False

    def groundCollideRect(self, rect):
        return self._sampleRect(rect)

    def enemiesCollideRect(self, rect):
        rectMask = pygame.Mask((rect.width, rect.height), fill=True)
        collidingLayer = pygame.Surface((rect.width, rect.height), flags=pygame.SRCALPHA)
        self.drawEnemies((rect.width, rect.height), collidingLayer, [rect.left, rect.top, 1], hitboxes=True)
        return pygame.mask.from_surface(collidingLayer).overlap(rectMask, (0, 0)) is not None

    def enemiesAttackCollideRect(self, rect):
        rectMask = pygame.Mask((rect.width, rect.height), fill=True)
        collidingLayer = pygame.Surface((rect.width, rect.height), flags=pygame.SRCALPHA)
        self.drawEnemies((rect.width, rect.height), collidingLayer, [rect.left, rect.top, 1], hitboxes=True)
        return pygame.mask.from_surface(collidingLayer).overlap(rectMask, (0, 0)) is not None

    def nestsCollideRect(self, rect):
        rectMask = pygame.Mask((rect.width, rect.height), fill=True)
        collidingLayer = pygame.Surface((rect.width, rect.height), flags=pygame.SRCALPHA)
        self.drawNests((rect.width, rect.height), collidingLayer, [rect.left, rect.top, 1], hitboxes=True)
        return pygame.mask.from_surface(collidingLayer).overlap(rectMask, (0, 0)) is not None

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    def drawDepthBackground(self, surface, frame, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w, h   = surface.get_size()
        right  = left + w / zoom;  bottom = top + h / zoom
        tl = self._depthColor(left,  top);   tr = self._depthColor(right, top)
        bl = self._depthColor(left,  bottom); br = self._depthColor(right, bottom)
        def darken(c): return (int(c[0]*0.05), int(c[1]*0.05), int(c[2]*0.05))
        surface.blit(self._makeGradientSurf(darken(tl), darken(tr), darken(bl), darken(br), w, h),
                     (offset_x, offset_y))

    def drawCollisionDebug(self, surface, rect, frame, color=(255, 0, 0), offset_x=0, offset_y=0):
        left, top, zoom = frame
        l = float(rect.left);  r = float(rect.right - 1)
        t = float(rect.top);   b = float(rect.bottom - 1)
        step = (b - t) / 9
        for i in range(10):
            y = t + step * i
            for wx, wy in [(l, y), (r, y)]:
                pygame.draw.circle(surface, color,
                    (int((wx - left) * zoom + offset_x), int((wy - top) * zoom + offset_y)),
                    max(2, int(zoom * 2)))

    def drawNestGradients(self, window_size, surface, frame, hitboxes=False, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w_width, w_height = window_size
        r = math.sqrt(w_width ** 2 + w_height ** 2) / 2 / zoom
        x, y = left + w_width / zoom / 2, top + w_height / zoom / 2
        for n in self._activeNests():
            if n.close(x, y, r):
                n.drawGradient(surface, frame, offset_x=offset_x, offset_y=offset_y)
            for enemy in n.enemies:
                dx = x - enemy.x;  dy = y - enemy.y
                if dx * dx + dy * dy < (r + enemy.r) ** 2:
                    enemy.drawGradient(surface, frame, offset_x=offset_x, offset_y=offset_y)

    def drawNests(self, window_size, surface, frame, hitboxes=False, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w_width, w_height = window_size
        r = math.sqrt(w_width ** 2 + w_height ** 2) / 2 / zoom
        x, y = left + w_width / zoom / 2, top + w_height / zoom / 2
        for n in self._activeNests():
            if n.close(x, y, r):
                n.draw(surface, frame, hitbox=hitboxes, offset_x=offset_x, offset_y=offset_y)

    def drawHealthBars(self, window_size, surface, frame, time=None, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w_width, w_height = window_size
        r = math.sqrt(w_width ** 2 + w_height ** 2) / 2 / zoom
        x, y = left + w_width / zoom / 2, top + w_height / zoom / 2
        for n in self._activeNests():
            for enemy in n.enemies:
                enemy.drawHealthBar(surface, frame, time, offset_x=offset_x, offset_y=offset_y)
            if n.close(x, y, r):
                n.drawHealthBar(surface, frame, time, offset_x=offset_x, offset_y=offset_y)
        for gw in self.gateways:
            for entry in gw.entryTiles:
                entry.drawHealthBar(surface, frame, time, offset_x=offset_x, offset_y=offset_y)

    def drawEnemies(self, window_size, surface, frame, hitboxes=False, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w_width, w_height = window_size
        r = math.sqrt(w_width ** 2 + w_height ** 2) / 2 / zoom
        x, y = left + w_width / zoom / 2, top + w_height / zoom / 2
        for n in self._activeNests():
            for i in range(len(n.enemies) - 1, -1, -1):
                enemy = n.enemies[i]
                dx = x - enemy.x;  dy = y - enemy.y
                if dx * dx + dy * dy < (r + enemy.r) ** 2:
                    enemy.draw(surface, frame, hitbox=hitboxes, offset_x=offset_x, offset_y=offset_y)

    def drawTerrain(self, window_size, surface, frame, hitboxes=False,
                    real_window_size=None, offset_x=0, offset_y=0):
        if real_window_size is None:
            real_window_size = window_size
        left, top, zoom = frame
        w_width, w_height = window_size
        if zoom not in self.defaultZooms:
            return
        if hitboxes:
            surface.blit(
                self.getTerrainLayer(window_size, frame, hitboxes=True,
                                     real_window_size=real_window_size,
                                     offset_x=offset_x, offset_y=offset_y),
                (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
        else:
            topChunk    = math.floor(max(0, min(self.worldHeight, top)) / visual_chunk_size)
            leftChunk   = math.floor(max(0, min(self.worldWidth - visual_chunk_size, left)) / visual_chunk_size)
            bottomChunk = math.ceil(max(0, min(self.worldHeight, top + w_height / zoom - visual_chunk_size)) / visual_chunk_size)
            rightChunk  = math.ceil(max(0, min(self.worldWidth - visual_chunk_size, left + w_width / zoom - visual_chunk_size)) / visual_chunk_size)

            if self._vignette_stencil is None or self._vignette_stencil_size != real_window_size:
                self._vignette_stencil = pygame.Surface(real_window_size, pygame.SRCALPHA)
                self._vignette_stencil_size = real_window_size
            self._vignette_stencil.fill((0, 0, 0, 0))

            chunks = self.chunkVisuals[zoom]
            for row in range(topChunk, bottomChunk + 1):
                for col in range(leftChunk, rightChunk + 1):
                    if row < len(chunks) and col < len(chunks[row]):
                        self._vignette_stencil.blit(
                            chunks[row][col],
                            ((col * visual_chunk_size - left) * zoom + offset_x,
                             (row * visual_chunk_size - top)  * zoom + offset_y))

            self.drawVignette(self._vignette_stencil, window_size, offset_x=offset_x, offset_y=offset_y)
            surface.blit(self._vignette_stencil, (0, 0))

    def getTerrainLayer(self, window_size, frame, hitboxes=False,
                        real_window_size=None, offset_x=0, offset_y=0):
        if real_window_size is None:
            real_window_size = window_size
        left, top, zoom = frame
        w_width, w_height = window_size
        layer = self._getTerrainLayerSurface(real_window_size)
        if zoom in self.defaultZooms:
            if hitboxes:
                topChunk    = math.floor(max(0, min(self.worldHeight, top)) / hitbox_chunk_size)
                leftChunk   = math.floor(max(0, min(self.worldWidth - hitbox_chunk_size, left)) / hitbox_chunk_size)
                bottomChunk = math.ceil(max(0, min(self.worldHeight, top + w_height / zoom - hitbox_chunk_size)) / hitbox_chunk_size)
                rightChunk  = math.ceil(max(0, min(self.worldWidth - hitbox_chunk_size, left + w_width / zoom - hitbox_chunk_size)) / hitbox_chunk_size)
                layer.fill((0, 0, 0, 0))
                surfaces = self.chunkHitboxes[zoom]
                for row in range(topChunk, bottomChunk + 1):
                    for column in range(leftChunk, rightChunk + 1):
                        layer.blit(surfaces[row][column],
                                   ((column * hitbox_chunk_size - left) * zoom + offset_x,
                                    (row    * hitbox_chunk_size - top)  * zoom + offset_y))
            else:
                topChunk    = math.floor(max(0, min(self.worldHeight, top)) / 500)
                leftChunk   = math.floor(max(0, min(self.worldWidth - 500, left)) / 500)
                bottomChunk = math.ceil(max(0, min(self.worldHeight, top + w_height / zoom - 500)) / 500)
                rightChunk  = math.ceil(max(0, min(self.worldWidth - 500, left + w_width / zoom - 500)) / 500)
                surfaces = self.airPocketsSurfaces[zoom]
                for row in range(topChunk, bottomChunk + 1):
                    for column in range(leftChunk, rightChunk + 1):
                        layer.blit(surfaces[row][column],
                                   ((column * 500 - left) * zoom + offset_x,
                                    (row    * 500 - top)  * zoom + offset_y),
                                   special_flags=pygame.BLEND_RGBA_SUB)
                air_surface = pygame.Surface((w_width, w_height), pygame.SRCALPHA)
                layer.blit(air_surface, (offset_x, offset_y), special_flags=pygame.BLEND_RGBA_SUB)
        return layer


# ------------------------------------------------------------------
# AirPocket
# ------------------------------------------------------------------

class AirPocket:
    def __init__(self, x, y, radius, defaultZooms=[0.1, 2], pocketType="Circle"):
        radius = _snapRadius(radius)

        self.x    = x
        self.y = y
        self.r = radius
        self.type = pocketType
        self.top  = self.y - self.r
        self.left = self.x - self.r

        imgs = airIMGs[pocketType]
        imgIndex = random.randint(0, len(imgs) - 1)

        self.fullResIMG = imgs[imgIndex]

        self.IMGs = {}
        self.hitboxIMGs = {}
        self.rimIMGs = {}

        for zoom in defaultZooms:
            self.IMGs[zoom] = _getCachedScale(self.fullResIMG, pocketType, imgIndex, radius, zoom)

        if self.type != "Circle":
            self.fullResHitboxIMG = airHitboxIMGs[pocketType]
            for zoom in defaultZooms:
                self.hitboxIMGs[zoom] = _getCachedScale(
                    self.fullResHitboxIMG, pocketType + "_hitbox", 0, radius, zoom)

        for zoom in defaultZooms:
            self.rimIMGs[zoom] = _getCachedRimScale(self.fullResIMG, pocketType, imgIndex, radius, zoom)

    def close(self, x, y, radius):
        # return abs(self.x - x) < radius + self.r and abs(self.y - y) < radius + self.r
        return math.dist((self.x, self.y), (x, y)) < radius + self.r