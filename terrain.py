import pygame, random, math, nest,particles,os, time

hitbox_chunk_size = 125
max_airpocket_radius = 120
visual_chunk_size = 500  # world-space size of visual chunks (unchanged)
rocks_world_span = 8 * hitbox_chunk_size  # 1000px — Rocks.png spans 8 hitbox chunks

# load images — call terrain.init() after pygame.display.set_mode()
airIMGs = {}
circleIMGs = []
airHitboxIMGs = {}
rocksIMG = {}  # keyed by zoom: pre-scaled rocks texture tiles
vignetteIMG = None  # loaded in init(), smoothscaled to window size in drawVignette

def init():
    global airIMGs, circleIMGs, airHitboxIMGs, rocksIMG, vignetteIMG
    circleIMGs = []
    for i in range(4):
        circleIMGs.append(pygame.image.load(os.path.join("assets", "AirPocket" + str(i + 1) + ".png")).convert_alpha())
    airIMGs["Circle"] = circleIMGs

    for customPocket in ["C1"]:
        airIMGs[customPocket] = [pygame.image.load(os.path.join("assets", "AirPocket" + customPocket + ".png")).convert_alpha()]
        airHitboxIMGs[customPocket] = pygame.image.load(os.path.join("assets", "AirPocket" + customPocket + "Hitbox.png")).convert_alpha()

    rocks_raw = pygame.image.load(os.path.join("assets", "Rocks.png")).convert()
    # rocksIMG is stored at world scale (zoom=1) only; zoomed versions built in Terrain.__init__
    rocksIMG["raw"] = rocks_raw

    vignetteIMG = pygame.image.load(os.path.join("assets", "VignetteGradient.png")).convert_alpha()


def distance(coord1: int, coord2: int):
    x1, y1 = coord1
    x2, y2 = coord2
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def rectToCircle(left, top, width, height):
    return left + width / 2, top + height / 2, distance((0, 0), (width, height)) / 2


class Terrain:

    def __init__(self, worldWidth: int, worldHeight: int, defaultZooms: list[float] = [0.1, 2]):

        self.knockbackCircles = []
        self.newKnockbackCircles = []
        self.playerDamageCircles = []
        self.newPlayerDamageCircles = []
        self.nests = []
        self.airPockets = []
        self.worldWidth = worldWidth
        self.worldHeight = worldHeight
        self.defaultZooms = defaultZooms
        self.airPocketsSurfaces = {}
        self.airPocketsHitboxesSurfaces = {}
        self.particles = particles.Particles()

        for zoom in defaultZooms:
            self.airPocketsSurfaces[zoom] = []
            for row in range(math.ceil(worldHeight / 500) + 1):
                rowList = []
                for j in range(math.ceil(worldWidth / 500)):
                    layer = pygame.Surface((500 * zoom, 500 * zoom), pygame.SRCALPHA)
                    rowList.append(layer)
                self.airPocketsSurfaces[zoom].append(rowList)

        for zoom in defaultZooms:
            self.airPocketsHitboxesSurfaces[zoom] = []
            for row in range(math.ceil(worldHeight / hitbox_chunk_size) + 1):
                rowList = []
                for j in range(math.ceil(worldWidth / hitbox_chunk_size)):
                    layer = pygame.Surface((hitbox_chunk_size * zoom, hitbox_chunk_size * zoom), pygame.SRCALPHA)
                    rowList.append(layer)
                self.airPocketsHitboxesSurfaces[zoom].append(rowList)

        # chunkVisuals: pre-baked colored+textured terrain for rendering.
        # Indexed [zoom][row][col]. Built once after generate(), updated on mining.
        # Textured rock pixels where solid, transparent where air.
        self.chunkVisuals = {}
        for zoom in defaultZooms:
            self.chunkVisuals[zoom] = []
            for row in range(math.ceil(worldHeight / visual_chunk_size) + 1):
                rowList = []
                for col in range(math.ceil(worldWidth / visual_chunk_size)):
                    layer = pygame.Surface((visual_chunk_size * zoom, visual_chunk_size * zoom), pygame.SRCALPHA)
                    rowList.append(layer)
                self.chunkVisuals[zoom].append(rowList)

        # pre-scale Rocks.png to rocks_world_span at each zoom so baking is fast
        self._rocksScaled = {}
        for zoom in defaultZooms:
            scaled_span = int(rocks_world_span * zoom)
            self._rocksScaled[zoom] = pygame.transform.scale(rocksIMG["raw"], (scaled_span, scaled_span))

        # chunkHitboxes: pre-baked solid ground with air carved out and nests blitted in.
        # Indexed [zoom][row][col]. Built once after generate(), updated on mining.
        # White pixel = solid, transparent = air. Blitted directly in getTerrainLayer.
        self.chunkHitboxes = {}
        for zoom in defaultZooms:
            self.chunkHitboxes[zoom] = []
            for row in range(math.ceil(worldHeight / hitbox_chunk_size) + 1):
                rowList = []
                for col in range(math.ceil(worldWidth / hitbox_chunk_size)):
                    layer = pygame.Surface((hitbox_chunk_size * zoom, hitbox_chunk_size * zoom), pygame.SRCALPHA)
                    rowList.append(layer)
                self.chunkHitboxes[zoom].append(rowList)

        # FIX 1: pre-allocate reusable terrain layer surface (rendering)
        # sized lazily on first call — stored here as None until first getSurface call
        self._terrain_layer = None
        self._terrain_layer_size = None

        # FIX 1: pre-allocate reusable collision scratch surfaces
        # collision rects are at most a few hundred px; 512 covers all cases
        self._collide_scratch = pygame.Surface((512, 512), pygame.SRCALPHA)
        self._collide_scratch_hitbox = pygame.Surface((512, 512), pygame.SRCALPHA)

        # vignette: pre-baked screen-fixed darkening, rebuilt only on window resize
        self._vignetteSurf = None
        self._vignetteSize = None
        # stencil surface for vignette clipping — reused across frames, reallocated on resize
        self._vignette_stencil = None
        self._vignette_stencil_size = None

    def _getTerrainLayerSurface(self, real_window_size):
        """Return a cleared reusable terrain layer, reallocating only on resize."""
        if self._terrain_layer is None or self._terrain_layer_size != real_window_size:
            self._terrain_layer = pygame.Surface(real_window_size, pygame.SRCALPHA)
            self._terrain_layer_size = real_window_size
        self._terrain_layer.fill((255, 255, 255, 255))
        return self._terrain_layer

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
                    # carve chunkVisuals — only remove, no re-texturing needed
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
                        # carve the same air out of chunkHitboxes
                        if airPocket.type == "Circle":
                            pygame.draw.circle(
                                self.chunkHitboxes[zoom][row][col],
                                (255, 255, 255, 255),
                                (zoom * (airPocket.x - left), zoom * (airPocket.y - top)),
                                airPocket.r * zoom
                            )
                            self.chunkHitboxes[zoom][row][col].blit(
                                self.airPocketsHitboxesSurfaces[zoom][row][col],
                                (0, 0),
                                special_flags=pygame.BLEND_RGBA_SUB
                            )
                        else:
                            self.chunkHitboxes[zoom][row][col].blit(
                                airPocket.hitboxIMGs[zoom],
                                (zoom * (airPocket.left - left), zoom * (airPocket.top - top)),
                                special_flags=pygame.BLEND_RGBA_SUB
                            )
                    affectedChunks.append((row, col))

        # re-blit nests on every chunk we just carved into, restoring their solid pixels
        for row, col in affectedChunks:
            self._reblitNestsOnChunk(row, col)

    def addNestToHitboxSurfaces(self, newNest):
        """Blit nest hitbox into airPocketsHitboxesSurfaces and chunkHitboxes for every zoom.
        Called once at generation — nests are stationary so this never needs repeating."""
        for zoom in self.defaultZooms:
            img = newNest.resizedHitboxes[zoom]
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
                        self.airPocketsHitboxesSurfaces[zoom][row][col].blit(img, offset)
                        # also blit into chunkHitboxes if already built
                        if self.chunkHitboxes[zoom] and row < len(self.chunkHitboxes[zoom]) and col < len(self.chunkHitboxes[zoom][row]):
                            self.chunkHitboxes[zoom][row][col].blit(img, offset)

    def _noiseVal(self, x, y, scale=1.0):
        """Cheap layered sine/cosine noise returning a value roughly in [-1, 1].
        Not true Perlin but gives organic-looking spatial variation."""
        x, y = x * scale, y * scale
        v  =  math.sin(x * 0.017 + y * 0.011) * 0.4
        v +=  math.cos(x * 0.031 - y * 0.023) * 0.3
        v +=  math.sin(x * 0.053 + y * 0.047 + 1.3) * 0.2
        v +=  math.cos(x * 0.079 - y * 0.061 + 2.7) * 0.1
        return max(-1.0, min(1.0, v))

    def _depthColor(self, worldX, worldY):
        """Return an RGB tint for a world-space position.
        Top of world = desaturated grey. Bottom = vivid reds/blues/purples.
        Noise offsets the hue laterally so colors vary at the same depth.
        Easily tweakable: adjust the palette list or depth curve below."""
        depth = max(0.0, min(1.0, worldY / self.worldHeight))

        # noise shifts the effective depth slightly for lateral variation
        noise = self._noiseVal(worldX, worldY) * 0.15
        d = max(0.0, min(1.0, depth + noise))

        # palette: list of (depth_fraction, (r, g, b)) keyframes
        # interpolated linearly between adjacent keyframes
        palette = [
            (0.0,  (60,  55,  65)),   # near surface: dark desaturated grey-purple
            (0.2, (70,  50,  90)),   # upper mid: muted purple
            (0.4,  (40,  30, 120)),   # mid: deep blue
            (0.5, (60, 200,  100)),
            (0.6, (120, 10,  50)),   # lower mid: deep magenta
            (0.8,  (250, 15,  20)),   # bottom: vivid dark red
            (1.0,  (255, 255,  255)),
        ]

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
        """Build a bilinearly-interpolated colour gradient surface from 4 corner colours.
        Creates a 2x2 pixel surface with corner colours then scales it up — pygame's
        transform.scale bilinearly interpolates, giving a smooth seamless gradient."""
        surf = pygame.Surface((2, 2))
        surf.set_at((0, 0), tl)
        surf.set_at((1, 0), tr)
        surf.set_at((0, 1), bl)
        surf.set_at((1, 1), br)
        return pygame.transform.smoothscale(surf, (width, height))

    _RIM_MULT = 1.7  # rim radius multiplier relative to air pocket radius

    def buildChunkVisuals(self):
        """Build chunkVisuals: fill white, subtract air, multiply Rocks texture,
        multiply bilinear depth+noise gradient. Called once after generate()."""
        for zoom in self.defaultZooms:
            airChunks = self.airPocketsSurfaces[zoom]
            rocks = self._rocksScaled[zoom]
            rocks_span_px = int(rocks_world_span * zoom)
            chunk_px = int(visual_chunk_size * zoom)

            for row, rowList in enumerate(self.chunkVisuals[zoom]):
                for col, chunk in enumerate(rowList):
                    world_left  = col * visual_chunk_size
                    world_top   = row * visual_chunk_size
                    world_right = world_left + visual_chunk_size
                    world_bot   = world_top  + visual_chunk_size

                    # Sample 4 corner colours — shared with adjacent chunks for seamless transitions
                    tl = self._depthColor(world_left,  world_top)
                    tr = self._depthColor(world_right, world_top)
                    bl = self._depthColor(world_left,  world_bot)
                    br = self._depthColor(world_right, world_bot)

                    # 1. Set all pixels fully opaque solid — alpha=255, RGB=0
                    chunk.fill((0, 0, 0, 255))

                    # 2. Blit bilinear depth gradient onto RGB channels only
                    chunk.blit(self._makeGradientSurf(tl, tr, bl, br, chunk_px, chunk_px), (0, 0), special_flags=pygame.BLEND_RGB_MAX)

                    # 3. Multiply Rocks.png tile
                    rock_x = int((world_left * zoom) % rocks_span_px)
                    rock_y = int((world_top  * zoom) % rocks_span_px)
                    rock_surf = pygame.Surface((chunk_px, chunk_px))
                    for ty in range(-rock_y, chunk_px, rocks_span_px):
                        for tx in range(-rock_x, chunk_px, rocks_span_px):
                            rock_surf.blit(rocks, (tx, ty))
                    chunk.blit(rock_surf, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

                    # 4. Draw rim — enlarged air pockets using their own visual image,
                    #    tinted to ambient dark colour. Drawn before air carve so the
                    #    rim darkens solid rock at cave edges.
                    #    Player-mined pockets are excluded — rims are initial generation only.
                    rim_margin = visual_chunk_size * self._RIM_MULT
                    for airPocket in self.airPockets:
                        # quick AABB cull — skip pockets far from this chunk
                        if (airPocket.x + airPocket.r * self._RIM_MULT < world_left - rim_margin or
                                airPocket.x - airPocket.r * self._RIM_MULT > world_right + rim_margin or
                                airPocket.y + airPocket.r * self._RIM_MULT < world_top  - rim_margin or
                                airPocket.y - airPocket.r * self._RIM_MULT > world_bot  + rim_margin):
                            continue
                        # ambient dark colour at this pocket's world position
                        dc = self._depthColor(airPocket.x, airPocket.y)
                        rim_color = (int(dc[0] * 0.05), int(dc[1] * 0.05), int(dc[2] * 0.05))
                        cx = zoom * (airPocket.x - world_left)
                        cy = zoom * (airPocket.y - world_top)
                        # use the pocket's own visual image scaled up by RIM_MULT for all types
                        img = airPocket.IMGs[zoom]
                        rim_size = (int(img.get_width() * self._RIM_MULT),
                                    int(img.get_height() * self._RIM_MULT))
                        rim_img = pygame.transform.scale(img, rim_size)
                        rim_surf = pygame.Surface(rim_size, pygame.SRCALPHA)
                        rim_surf.fill(rim_color)
                        rim_surf.blit(rim_img, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                        chunk.blit(rim_surf,
                                   (int(cx - rim_size[0] / 2),
                                    int(cy - rim_size[1] / 2)))

                    # 5. Carve air last — punches clean transparent holes through rim+rock
                    chunk.blit(airChunks[row][col], (0, 0), special_flags=pygame.BLEND_RGBA_SUB)

    def drawDepthBackground(self, surface, frame, offset_x=0, offset_y=0):
        """Fill the layer with a smooth depth-colour gradient matching the terrain tint.
        Replaces layer.fill((0,0,0)) — samples _depthColor at the 4 world-space corners
        of the current view so rock colour and background colour are always in sync."""
        left, top, zoom = frame
        w, h = surface.get_size()
        right  = left + w / zoom
        bottom = top  + h / zoom
        tl = self._depthColor(left,  top)
        tr = self._depthColor(right, top)
        bl = self._depthColor(left,  bottom)
        br = self._depthColor(right, bottom)
        # substantially darker than terrain — multiply by 0.05
        def darken(c): return (int(c[0]*0.05), int(c[1]*0.05), int(c[2]*0.05))
        grad = self._makeGradientSurf(darken(tl), darken(tr), darken(bl), darken(br), w, h)
        surface.blit(grad, (offset_x, offset_y))

    def drawVignette(self, surface, window_size, offset_x=0, offset_y=0):
        """Blit a screen-fixed vignette (white centre -> black edges) using BLEND_RGB_MULT.
        Pre-baked and only rebuilt on window resize."""
        w, h = window_size
        if self._vignetteSurf is None or self._vignetteSize != window_size:
            self._vignetteSurf = pygame.transform.smoothscale(vignetteIMG, (w, h))
            self._vignetteSize = window_size
        surface.blit(self._vignetteSurf, (offset_x, offset_y), special_flags=pygame.BLEND_RGB_MULT)

    def _carveVisualChunk(self, airPocket, row, col, zoom):
        """Carve a newly-mined air pocket out of a single chunkVisuals chunk.
        No re-texturing needed — we only remove solid pixels."""
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

    def buildChunkHitboxes(self):
        """Build chunkHitboxes from scratch: fill solid white, subtract air, blit nests.
        Called once after generate() completes. Never called again — updates happen
        incrementally via addAirPocketToSurfaces and addNestToHitboxSurfaces."""
        for zoom in self.defaultZooms:
            airChunks = self.airPocketsHitboxesSurfaces[zoom]
            for row, rowList in enumerate(self.chunkHitboxes[zoom]):
                for col, chunk in enumerate(rowList):
                    # fill solid white
                    chunk.fill((255, 255, 255, 255))
                    # carve out air pockets already baked into airPocketsHitboxesSurfaces
                    chunk.blit(airChunks[row][col], (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
            # blit all nests on top (nests are solid, may overlap carved-out air)
            for n in self.nests:
                self._blitNestOnChunkHitboxes(n, zoom)

    def _blitNestOnChunkHitboxes(self, n, zoom):
        """Blit a single nest's hitbox into all chunkHitboxes chunks it overlaps."""
        img = n.resizedHitboxes[zoom]
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
                    img,
                    (zoom * (n.left - chunkLeft),
                     zoom * (n.top  - chunkTop))
                )

    def _reblitNestsOnChunk(self, row, col):
        """After mining carves into chunkHitboxes, re-blit any nests overlapping this chunk.
        Called per affected chunk from addAirPocketToSurfaces."""
        chunkLeft = col * hitbox_chunk_size
        chunkTop  = row * hitbox_chunk_size
        chunkRight  = chunkLeft + hitbox_chunk_size
        chunkBottom = chunkTop  + hitbox_chunk_size
        for n in self.nests:
            # fast AABB: does this nest overlap this chunk?
            if (n.left < chunkRight and n.left + n.size > chunkLeft and
                    n.top < chunkBottom and n.top + n.size > chunkTop):
                for zoom in self.defaultZooms:
                    self.chunkHitboxes[zoom][row][col].blit(
                        n.resizedHitboxes[zoom],
                        (zoom * (n.left - chunkLeft),
                         zoom * (n.top  - chunkTop))
                    )

    # generate caves/nests/decorations
    def generate(self, progress_queue=None):
        x=-500
        while x<self.worldWidth+500:
            r=random.randint(10,30)
            self.addAirPocketClump(x,0,r,playerMade=True)
            x+=r/2
        for i in range(int(self.worldHeight/100)):
            if progress_queue is not None:
                progress_queue.put(i / (self.worldHeight/100) * (0.999 - 0.1) + 0.1)
            for j in range(int(self.worldWidth/1000)):

                if random.randint(1, 10) == 1:
                    self.generateSkinnyCave(j * 1000 + random.randint(0, 1000), random.randint(0, int((self.worldHeight - 500) / 3)), random.randint(20, 60), random.random() * 2 * math.pi)
                if random.randint(1, 20) == 1:
                    self.generateSkinnyCave(j * 1000 + random.randint(0, 1000), random.randint(int((self.worldHeight - 500) / 4), int((self.worldHeight - 500))), random.randint(30, 90), random.random() * 2 * math.pi)

                if random.randint(1, 35) == 1:
                    self.generateBlobCave(j * 1000 + random.randint(0, 1000), random.randint(int((self.worldHeight - 500) * 1 / 4), self.worldHeight - 500), random.randint(30, 60), random.random() * 2 * math.pi)
                if random.randint(1, 20) == 1:
                    self.generateBlobCave(j * 1000 + random.randint(0, 1000), random.randint(int((self.worldHeight - 500) * 2 / 3), self.worldHeight - 500), random.randint(60, 120), random.random() * 2 * math.pi)

                if random.randint(1, 25) == 1:
                    self.generateBedrockCave(j * 1000 + random.randint(0, 1000), random.randint(self.worldHeight - 100, self.worldHeight), random.randint(80, 120), random.randint(0, 1) * 2 * math.pi)

                if random.randint(1, 10) == 1:
                    self.generateNest(j * 1000 + random.randint(0, 1000), random.randint(500, int((self.worldHeight - 500) / 4)), "White")

                if random.randint(1, 15) == 1:
                    self.generateNest(j * 1000 + random.randint(0, 1000), random.randint(int((self.worldHeight - 500) / 4), int((self.worldHeight - 500) * 2 / 3)), "White")
                if random.randint(1, 15) == 1:
                    self.generateNest(j * 1000 + random.randint(0, 1000), random.randint(int((self.worldHeight - 500) * 3 / 4), int((self.worldHeight - 500))), "White")

                if random.randint(1, 15) == 1:
                    self.generateNest(j * 1000 + random.randint(0, 1000), random.randint(int((self.worldHeight - 500) * 1 / 4), self.worldHeight - 500), "Red")
                if random.randint(1, 15) == 1:
                    self.generateNest(j * 1000 + random.randint(0, 1000), random.randint(int((self.worldHeight - 500) * 1 / 4), self.worldHeight - 500), "Blue")

                if random.randint(1, 50) == 1:
                    self.generateNest(j * 1000 + random.randint(0, 1000), random.randint(int((self.worldHeight / 2)), self.worldHeight - 5), "White")
                if random.randint(1, 20) == 1:
                    self.generateNest(j * 1000 + random.randint(0, 1000), random.randint(int((self.worldHeight / 2)), self.worldHeight - 5), "Red")
                if random.randint(1, 20) == 1:
                    self.generateNest(j * 1000 + random.randint(0, 1000), random.randint(int((self.worldHeight / 2)), self.worldHeight - 5), "Blue")

                if random.randint(1, 40) == 1:
                    self.generateNest(j * 1000 + random.randint(0, 1000), random.randint(int((self.worldHeight - 500)), self.worldHeight - 5), "White")
                if random.randint(1, 35) == 1:
                    self.generateNest(j * 1000 + random.randint(0, 1000), random.randint(int((self.worldHeight - 500)), self.worldHeight - 5), "Red")
                if random.randint(1, 35) == 1:
                    self.generateNest(j * 1000 + random.randint(0, 1000), random.randint(int((self.worldHeight - 500)), self.worldHeight - 5), "Blue")
        self.buildChunkHitboxes()
        self.buildChunkVisuals()
        if progress_queue is not None:
            progress_queue.put(1)

    def generateNest(self, x, y, nestType, size=0):
        if size == 0:
            size = random.randint(100, 100 + (y * 150) // self.worldHeight)
        newNest = nest.Nest(self.defaultZooms, self.worldHeight, nestType, x, y, size)
        rect = newNest.getRect()
        for cnest in self.nests:
            if rect.colliderect(cnest.getRect()):
                return False
        self.nests.append(newNest)
        self.addNestToHitboxSurfaces(newNest)

        caveSize = (size * random.randint(0, 2) / 3 + 80) / 3
        if caveSize > 15:
            self.generateSkinnyCave(x, y - caveSize / 2, caveSize, -math.pi / 2, maxPockets=10, shrinking=True)
        else:
            self.addAirPocketClump(x, y - caveSize / 2, caveSize)
        return True

    def generateBlobCave(self, startX: int, startY: int, startR: int, startDir: float = 0, maxPockets: int = 10):
        if maxPockets > 0 and (startY - 2 * startR) > 0 and startY - startR < self.worldHeight and startR > 0:
            self.addAirPocketClump(startX, startY, startR)

            for i in range(2):
                r = startR + (random.random() - 0.6) * 20
                dir = startDir + (random.random() - 0.5) * math.pi

                x = startX + math.cos(dir) * min(r, startR) * 0.8
                y = startY + math.sin(dir) * min(r, startR) * 0.8 * 0.2
                self.generateBlobCave(x, y, r, dir, maxPockets - 1)
                if random.randint(1, 15) > 1:
                    break

    def generateSkinnyCave(self, startX: int, startY: int, startR: int, startDir: float = 0, maxPockets: int = 20, shrinking=False):
        if maxPockets > 0 and (startY - 2 * startR) > 0 and startY - startR < self.worldHeight and startR > 0:
            self.addAirPocketClump(startX, startY, startR)

            for i in range(2):
                r = startR + (random.random() - 0.6) * 5
                if shrinking:
                    r = startR - random.random() * 2
                dir = startDir + (random.random() - 0.5) * math.pi / 2

                x = startX + math.cos(dir) * min(r, startR) * 0.8
                y = startY + math.sin(dir) * min(r, startR) * 0.8 * 0.8
                self.generateSkinnyCave(x, y, r, dir, maxPockets - 1, shrinking=shrinking)
                if random.randint(1, 30) > 1:
                    break

    def generateBedrockCave(self, startX: int, startY: int, startR: int, startDir: float = 0, maxPockets: int = 3):
        if maxPockets > 0 and (startY - 2 * startR) > 0 and startY - startR < self.worldHeight and startR > 0:
            self.addAirPocketClump(startX, startY, startR)

            for i in range(2):
                r = startR + (random.random() - 0.6) * 20
                dir = startDir + (random.random() - 0.5) * math.pi / 2

                x = startX + math.cos(dir) * min(r, startR) * 0.7
                y = startY + math.sin(dir) * min(r, startR) * 0.7 * 0.5
                self.generateBedrockCave(x, y, r, dir, maxPockets - 1)
                if random.randint(1, 30) > 1:
                    break

    def addAirPocketClump(self, x, y, radius, playerMade=False, spreading=1 / 3):
        spreading = radius * spreading
        for i in range(3):
            self.addAirPocket(x + spreading * (random.random() * 2 - 1), y + spreading * (random.random() * 2 - 1), radius, playerMade=playerMade)

    def addAirPocket(self, x: int, y: int, radius: int, recursions=0, playerMade=False):
        radius = min(radius, max_airpocket_radius)
        if (not playerMade and x - radius < 0) or (recursions > 3 or x + radius > self.worldWidth or x - radius < 0 or y < 0 or y > self.worldHeight):
            return False
        if (not playerMade) and random.randint(1, 10) == 1:
            newAirPocket = AirPocket(x, y, radius, defaultZooms=self.defaultZooms, pocketType="C1")
        else:
            newAirPocket = AirPocket(x, y, radius, defaultZooms=self.defaultZooms)
        if not playerMade:
            for airPocket in self.airPockets:
                if not airPocket is newAirPocket:
                    if airPocket.close(x, y, newAirPocket.r + 10):
                        d = distance((airPocket.x, airPocket.y), (x, y))
                        if d < newAirPocket.r / 4:
                            return False
                        if d > airPocket.r + newAirPocket.r and d < airPocket.r + newAirPocket.r + 10:
                            return self.addAirPocket((airPocket.x + x) / 2, (airPocket.y + y) / 2, (airPocket.r + radius) / 2, recursions + 1)
        self.airPockets.append(newAirPocket)
        self.addAirPocketToSurfaces(newAirPocket)
        return True

    # FIX 3: raycast-based ground collision — samples pre-baked hitbox chunks at zoom=1
    # instead of building surfaces and masks per step
    def rayCastGround(self, startX, startY, angle, maxLength):
        """
        Walk the ray in world-space pixel steps, sampling the zoom=1 hitbox chunk
        surfaces. Returns (hit_x, hit_y, distance) or (None, None, maxLength).
        White pixels (R>128) in the hitbox surface = air (no collision).
        Black pixels = solid terrain.
        """
        chunks = self.airPocketsHitboxesSurfaces[1]
        chunkRows = len(chunks)
        chunkCols = len(chunks[0]) if chunkRows > 0 else 0

        dx = math.cos(angle)
        dy = math.sin(angle)

        # step size: 1 world pixel at zoom=1 is 1 pixel in the chunk surface
        step = 2
        dist = 0
        while dist < maxLength:
            wx = startX + dx * dist
            wy = startY + dy * dist

            # out of world bounds = solid
            if wx < 0 or wx >= self.worldWidth or wy < 0 or wy >= self.worldHeight:
                return wx, wy, dist

            col = int(wx // hitbox_chunk_size)
            row = int(wy // hitbox_chunk_size)

            if row >= chunkRows or col >= chunkCols:
                return wx, wy, dist

            px = int(wx % hitbox_chunk_size)
            py = int(wy % hitbox_chunk_size)

            pixel = chunks[row][col].get_at((px, py))
            # pixel[0] is red channel; white=air (255), black=solid (0)
            if pixel[0] < 128:
                return wx, wy, dist

            dist += step

        return None, None, maxLength

    # FIX 1: reuse scratch surface for collision; clear only the needed region
    def _getScratch(self, w, h):
        """Return a cleared region of the scratch surface for collision checks."""
        w, h = int(math.ceil(w)), int(math.ceil(h))
        if w > self._collide_scratch.get_width() or h > self._collide_scratch.get_height():
            newW = max(w, self._collide_scratch.get_width())
            newH = max(h, self._collide_scratch.get_height())
            self._collide_scratch = pygame.Surface((newW, newH), pygame.SRCALPHA)
        self._collide_scratch.fill((0, 0, 0, 0), pygame.Rect(0, 0, w, h))
        return self._collide_scratch

    def _sampleChunk(self, wx, wy):
        """Sample a single world-space point from chunkHitboxes[1].
        Returns True if solid, False if air.
        Above world (wy<0) = air. Sides/bottom = solid."""
        if wy < 0:
            return False
        if wx < 0 or wx >= self.worldWidth or wy >= self.worldHeight:
            return True
        chunks = self.chunkHitboxes[1]
        col = int(wx // hitbox_chunk_size)
        row = int(wy // hitbox_chunk_size)
        if row >= len(chunks) or col >= len(chunks[0]):
            return True
        px = max(0, min(int(hitbox_chunk_size - 1), int(wx % hitbox_chunk_size)))
        py = max(0, min(int(hitbox_chunk_size - 1), int(wy % hitbox_chunk_size)))
        pixel = chunks[row][col].get_at((px, py))
        return pixel[3] > 128  # opaque = solid, transparent = air

    def _sampleRect(self, rect):
        """Sample 5 points along the left edge and 5 along the right edge.
        Top and bottom corners are included as the endpoints of each edge."""
        l  = float(rect.left)
        r  = float(rect.right - 1)
        t  = float(rect.top)
        b  = float(rect.bottom - 1)
        # 5 evenly spaced y values from top to bottom
        step = (b - t) / 9
        for i in range(10):
            y = t + step * i
            if self._sampleChunk(l, y) or self._sampleChunk(r, y):
                return True
        return False

    def collideRect(self, rect: pygame.Rect):
        return self._sampleRect(rect)

    def laserCollideRect(self, rect: pygame.Rect):
        # terrain: sample centre point only — laser is a ray, centre is where it is
        if self._sampleChunk(float(rect.centerx), float(rect.centery)):
            return True
        # enemies: AABB only — they're dynamic and not baked into chunkHitboxes
        for nest in self.nests:
            for enemy in nest.enemies:
                if enemy.mode != "Spawn" and rect.colliderect(enemy.rect):
                    return True
        return False

    def groundCollideRect(self, rect: pygame.Rect):
        return self._sampleRect(rect)

    def enemiesCollideRect(self, rect: pygame.Rect):
        rectMask = pygame.Mask((rect.width, rect.height), fill=True)
        collidingLayer = pygame.Surface((rect.width, rect.height), flags=pygame.SRCALPHA)
        self.drawEnemies((rect.width, rect.height), collidingLayer, [rect.left, rect.top, 1], hitboxes=True)
        terrainMask = pygame.mask.from_surface(collidingLayer)
        return not (terrainMask.overlap(rectMask, (0, 0)) == None)

    def enemiesAttackCollideRect(self, rect: pygame.Rect):
        rectMask = pygame.Mask((rect.width, rect.height), fill=True)
        collidingLayer = pygame.Surface((rect.width, rect.height), flags=pygame.SRCALPHA)
        self.drawEnemies((rect.width, rect.height), collidingLayer, [rect.left, rect.top, 1], hitboxes=True)
        terrainMask = pygame.mask.from_surface(collidingLayer)
        return not (terrainMask.overlap(rectMask, (0, 0)) == None)

    def nestsCollideRect(self, rect: pygame.Rect):
        rectMask = pygame.Mask((rect.width, rect.height), fill=True)
        collidingLayer = pygame.Surface((rect.width, rect.height), flags=pygame.SRCALPHA)
        self.drawNests((rect.width, rect.height), collidingLayer, [rect.left, rect.top, 1], hitboxes=True)
        terrainMask = pygame.mask.from_surface(collidingLayer)
        return not (terrainMask.overlap(rectMask, (0, 0)) == None)

    def drawCollisionDebug(self, surface, rect, frame, color=(255, 0, 0), offset_x=0, offset_y=0):
        """Draw the 10 sample points used by _sampleRect for a given rect."""
        left, top, zoom = frame
        l  = float(rect.left)
        r  = float(rect.right - 1)
        t  = float(rect.top)
        b  = float(rect.bottom - 1)
        step = (b - t) / 9
        for i in range(10):
            y = t + step * i
            for wx, wy in [(l, y), (r, y)]:
                pygame.draw.circle(surface, color,
                    (int((wx - left) * zoom + offset_x),
                     int((wy - top) * zoom + offset_y)),
                    max(2, int(zoom * 2)))

    def drawNestGradients(self, window_size, surface: pygame.Surface, frame: list, hitboxes=False, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w_width, w_height = window_size
        # FIX 1: cache window diagonal radius — only recompute when window/zoom changes
        r = math.sqrt(w_width ** 2 + w_height ** 2) / 2 / zoom
        x, y = left + w_width / zoom / 2, top + w_height / zoom / 2

        for nest in self.nests:
            if nest.close(x, y, r):
                nest.drawGradient(surface, frame, offset_x=offset_x, offset_y=offset_y)
            for enemy in nest.enemies:
                dx = x - enemy.x
                dy = y - enemy.y
                if dx * dx + dy * dy < (r + enemy.r) ** 2:
                    enemy.drawGradient(surface, frame, offset_x=offset_x, offset_y=offset_y)

    def drawNests(self, window_size, surface: pygame.Surface, frame: list, hitboxes=False, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w_width, w_height = window_size
        r = math.sqrt(w_width ** 2 + w_height ** 2) / 2 / zoom
        x, y = left + w_width / zoom / 2, top + w_height / zoom / 2

        for nest in self.nests:
            if nest.close(x, y, r):
                nest.draw(surface, frame, hitbox=hitboxes, offset_x=offset_x, offset_y=offset_y)

        pygame.draw.rect(surface, (255, 255, 255), pygame.Rect(0 + offset_x, (self.worldHeight - top) * zoom + offset_y, w_width, 200))

    def drawEnemies(self, window_size, surface: pygame.Surface, frame: list, hitboxes=False, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w_width, w_height = window_size
        r = math.sqrt(w_width ** 2 + w_height ** 2) / 2 / zoom
        x, y = left + w_width / zoom / 2, top + w_height / zoom / 2

        for nest in self.nests:
            for i in range(len(nest.enemies) - 1, -1, -1):
                enemy = nest.enemies[i]
                dx = x - enemy.x
                dy = y - enemy.y
                if dx * dx + dy * dy < (r + enemy.r) ** 2:
                    enemy.draw(surface, frame, hitbox=hitboxes, offset_x=offset_x, offset_y=offset_y)

    def drawTerrain(self, window_size, surface: pygame.Surface, frame: list, hitboxes=False, real_window_size=None, offset_x=0, offset_y=0):
        """Drop-in replacement for the getTerrainLayer blit in getSurface.
        Hitbox mode: blits chunkHitboxes for collision debug display.
        Visual mode: blits pre-baked chunkVisuals directly — textured, depth-tinted rock."""
        if real_window_size is None:
            real_window_size = window_size
        left, top, zoom = frame
        w_width, w_height = window_size

        if zoom not in self.defaultZooms:
            return

        if hitboxes:
            # reuse existing getTerrainLayer hitbox path for debug display
            surface.blit(
                self.getTerrainLayer(window_size, frame, hitboxes=True,
                                     real_window_size=real_window_size,
                                     offset_x=offset_x, offset_y=offset_y),
                (0, 0), special_flags=pygame.BLEND_RGBA_SUB
            )
        else:
            topChunk    = math.floor(max(0, min(self.worldHeight, top)) / visual_chunk_size)
            leftChunk   = math.floor(max(0, min(self.worldWidth - visual_chunk_size, left)) / visual_chunk_size)
            bottomChunk = math.ceil(max(0, min(self.worldHeight, top + w_height / zoom - visual_chunk_size)) / visual_chunk_size)
            rightChunk  = math.ceil(max(0, min(self.worldWidth - visual_chunk_size, left + w_width / zoom - visual_chunk_size)) / visual_chunk_size)

            # use a stencil surface so the vignette only darkens solid terrain pixels:
            # 1. blit terrain chunks onto a cleared SRCALPHA stencil (transparent = air)
            # 2. multiply the vignette into the stencil (only affects opaque rock pixels)
            # 3. blit the stencil onto the layer normally
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
                             (row * visual_chunk_size - top) * zoom + offset_y)
                        )

            # multiply vignette into stencil — transparent air pixels unaffected
            self.drawVignette(self._vignette_stencil, window_size, offset_x=offset_x, offset_y=offset_y)

            # blit finished stencil onto the main layer
            surface.blit(self._vignette_stencil, (0, 0))

    def getTerrainLayer(self, window_size, frame: list, hitboxes=False, real_window_size=None, offset_x=0, offset_y=0):
        if real_window_size is None:
            real_window_size = window_size

        left, top, zoom = frame
        w_width, w_height = window_size

        # FIX 1: reuse terrain layer surface instead of allocating each frame
        layer = self._getTerrainLayerSurface(real_window_size)

        if zoom in self.defaultZooms:
            if hitboxes:
                topChunk    = math.floor(max(0, min(self.worldHeight, top)) / hitbox_chunk_size)
                leftChunk   = math.floor(max(0, min(self.worldWidth - hitbox_chunk_size, left)) / hitbox_chunk_size)
                bottomChunk = math.ceil(max(0, min(self.worldHeight, top + w_height / zoom - hitbox_chunk_size)) / hitbox_chunk_size)
                rightChunk  = math.ceil(max(0, min(self.worldWidth - hitbox_chunk_size, left + w_width / zoom - hitbox_chunk_size)) / hitbox_chunk_size)

                # chunkHitboxes has white=solid, transparent=air.
                # Start with a transparent layer so air regions stay transparent after blit.
                layer.fill((0, 0, 0, 0))
                surfaces = self.chunkHitboxes[zoom]
                for row in range(topChunk, bottomChunk + 1, 1):
                    for column in range(leftChunk, rightChunk + 1, 1):
                        layer.blit(surfaces[row][column], ((column * hitbox_chunk_size - left) * zoom + offset_x, (row * hitbox_chunk_size - top) * zoom + offset_y))
            else:
                topChunk = math.floor(max(0, min(self.worldHeight, top)) / 500)
                leftChunk = math.floor(max(0, min(self.worldWidth - 500, left)) / 500)
                bottomChunk = math.ceil(max(0, min(self.worldHeight, top + w_height / zoom - 500)) / 500)
                rightChunk = math.ceil(max(0, min(self.worldWidth - 500, left + w_width / zoom - 500)) / 500)

                surfaces = self.airPocketsSurfaces[zoom]
                for row in range(topChunk, bottomChunk + 1, 1):
                    for column in range(leftChunk, rightChunk + 1, 1):
                        layer.blit(surfaces[row][column], ((column * 500 - left) * zoom + offset_x, (row * 500 - top) * zoom + offset_y), special_flags=pygame.BLEND_RGBA_SUB)
                air_surface = pygame.Surface((w_width, w_height), pygame.SRCALPHA)
                pygame.draw.rect(air_surface, (255, 255, 255, 255), pygame.Rect(0, 0, w_width, zoom * max(0, 0 - top)))
                layer.blit(air_surface, (offset_x, offset_y), special_flags=pygame.BLEND_RGBA_SUB)
        else:
            ...

        return layer


class AirPocket:

    def __init__(self, x: int, y: int, radius: int, defaultZooms: list[float] = [0.1, 2], pocketType="Circle"):
        self.x = x
        self.y = y
        self.r = radius
        self.type = pocketType
        self.top = self.y - self.r
        self.left = self.x - self.r
        self.fullResIMG = airIMGs[pocketType][random.randint(0, len(airIMGs[pocketType]) - 1)]
        self.IMGs = {}
        for defaultZoom in defaultZooms:
            self.IMGs[defaultZoom] = pygame.transform.scale(self.fullResIMG, (2 * self.r * defaultZoom, 2 * self.r * defaultZoom))

        if self.type != "Circle":
            self.fullResHitboxIMG = airHitboxIMGs[pocketType]
            self.hitboxIMGs = {}
            for defaultZoom in defaultZooms:
                self.hitboxIMGs[defaultZoom] = pygame.transform.scale(self.fullResHitboxIMG, (2 * self.r * defaultZoom, 2 * self.r * defaultZoom))

    def close(self, x: int, y: int, radius: int):
        if abs(self.x - x) > radius + self.r:
            return False
        if abs(self.y - y) > radius + self.r:
            return False
        return True