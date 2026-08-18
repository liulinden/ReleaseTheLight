import math

import pygame

from config import CHUNK_SIZE
from scripts.global_assets import get_asset
from scripts.structure import Structure
from scripts.UI import HealthBar

# ---------------------------------------------------------------------------
# Gateway Y positions — one per boundary between layers.
# 5 layers → 4 gateways. Adjust values to tune layer spacing.
# ---------------------------------------------------------------------------
GATEWAY_Y_POSITIONS = [CHUNK_SIZE * 15, CHUNK_SIZE * 30, CHUNK_SIZE * 45, CHUNK_SIZE * 60, CHUNK_SIZE * 80, CHUNK_SIZE * 100, CHUNK_SIZE * 120, CHUNK_SIZE * 140, CHUNK_SIZE * 160]

# ---------------------------------------------------------------------------
# Image storage — populated by init() after pygame.display.set_mode()
# ---------------------------------------------------------------------------
gateway_imgs = {}  # keyed by tile type + state, e.g. "corridorclosed"
gateway_hitbox_imgs = {}  # keyed by tile type + state


def init():
    global gateway_imgs, gateway_hitbox_imgs

    # corridor
    gateway_imgs["corridorclosed"] = get_asset("gateCorridorClosed")
    gateway_imgs["corridoropened"] = get_asset("gateCorridorOpened")
    gateway_imgs["corridorback"] = get_asset("gateCorridorErase")
    gateway_imgs["corridorerase"] = get_asset("gateCorridorErase")
    gateway_hitbox_imgs["corridor"] = get_asset("gateCorridorHitbox")
    gateway_hitbox_imgs["corridorerase"] = get_asset("gateCorridorEraseHitbox")

    # entry
    gateway_imgs["entryclosed"] = get_asset("gateEntryClosed")
    gateway_imgs["entrycharging1"] = get_asset("gateEntryCharging1")
    gateway_imgs["entrycharging2"] = get_asset("gateEntryCharging2")
    gateway_imgs["entrycharging3"] = get_asset("gateEntryCharging3")
    gateway_imgs["entryopened"] = get_asset("gateEntryOpened")
    gateway_imgs["entryback"] = get_asset("gateEntryBack")
    gateway_imgs["entryerase"] = get_asset("gateEntryErase")
    gateway_hitbox_imgs["entryerase"] = get_asset("gateEntryEraseHitbox")
    gateway_hitbox_imgs["entryclosed"] = get_asset("gateEntryClosedHitbox")
    gateway_hitbox_imgs["entryopened"] = get_asset("gateEntryOpenedHitbox")
    gateway_hitbox_imgs["activator"] = get_asset("gatewayActivatorHitbox")

    # exit
    gateway_imgs["exitclosed"] = get_asset("gateExitClosed")
    gateway_imgs["exitopened"] = get_asset("gateExitOpened")
    gateway_imgs["exitback"] = get_asset("gateExitBack")
    gateway_imgs["exiterase"] = get_asset("gateExitErase")
    gateway_hitbox_imgs["exit"] = get_asset("gateExitHitbox")
    gateway_hitbox_imgs["exiterase"] = get_asset("gateExitEraseHitbox")


# ---------------------------------------------------------------------------
# Tile classes
# ---------------------------------------------------------------------------

_scaled_img__cache = {}


class GatewayTile(Structure):
    """Single tile in a gateway row. Width and height = visual_chunk_size."""

    def __init__(self, tile_x, tile_y, tile_size, default_zooms):
        super().__init__(tile_x + tile_size / 2, tile_y + tile_size / 2, tile_size, tile_size, default_zooms)
        self.tile_size = tile_size
        self.tile_left = tile_x
        self.tile_top = tile_y
        # pre-scaled surfaces keyed by zoom
        self._hitbox_surfs = {}
        self._front_surfs = {}
        self._back_surfs = {}
        self._erase_hitbox_surfs = {}
        self._erase_surfs = {}

    def _scaled_img(self, img, zoom):
        size = int(self.tile_size * zoom)
        name = (id(img), size)
        if name not in _scaled_img__cache:
            _scaled_img__cache[name] = pygame.transform.scale(img, (size, size))
        return _scaled_img__cache[name]

    def get_hitbox_surface(self, zoom):
        return self._hitbox_surfs.get(zoom)

    def get_erase_surface(self, zoom):
        return self._erase_surfs.get(zoom)

    def get_erase_hitbox_surface(self, zoom):
        return self._erase_hitbox_surfs.get(zoom)

    def draw(self, surface, frame, offset_x=0, offset_y=0):
        left, top, zoom = frame
        surf = self._front_surfs.get(zoom)
        if surf:
            surface.blit(surf, ((self.tile_left - left) * zoom + offset_x, (self.tile_top - top) * zoom + offset_y))

    def draw_back(self, surface, frame, offset_x=0, offset_y=0):
        left, top, zoom = frame
        surf = self._back_surfs.get(zoom)
        if surf:
            surface.blit(surf, ((self.tile_left - left) * zoom + offset_x, (self.tile_top - top) * zoom + offset_y))

    def tick(self, frame_length, terrain, player):
        return False


class CorridorTile(GatewayTile):
    def __init__(self, tile_x, tile_y, tile_size, default_zooms, opened=False):
        super().__init__(tile_x, tile_y, tile_size, default_zooms)
        self.opened = opened
        self._build_surfaces()

    def _build_surfaces(self):
        state = "opened" if self.opened else "closed"
        for zoom in self.default_zooms:
            self._hitbox_surfs[zoom] = self._scaled_img(gateway_hitbox_imgs["corridor"], zoom)
            self._front_surfs[zoom] = self._scaled_img(gateway_imgs[f"corridor{state}"], zoom)
            self._back_surfs[zoom] = self._scaled_img(gateway_imgs["corridorback"], zoom)
            self._erase_surfs[zoom] = self._scaled_img(gateway_imgs["corridorerase"], zoom)
            self._erase_hitbox_surfs[zoom] = self._scaled_img(gateway_hitbox_imgs["corridorerase"], zoom)

    def open(self):
        if not self.opened:
            self.opened = True
            self._build_surfaces()


class ExitTile(GatewayTile):
    """Exit hitbox never changes — always solid regardless of gateway state."""

    def __init__(self, tile_x, tile_y, tile_size, default_zooms, opened=False):
        super().__init__(tile_x, tile_y, tile_size, default_zooms)
        self.opened = opened
        self._build_surfaces()

    def _build_surfaces(self):
        state = "opened" if self.opened else "closed"
        for zoom in self.default_zooms:
            self._hitbox_surfs[zoom] = self._scaled_img(gateway_hitbox_imgs["exit"], zoom)
            self._front_surfs[zoom] = self._scaled_img(gateway_imgs[f"exit{state}"], zoom)
            self._back_surfs[zoom] = self._scaled_img(gateway_imgs["exitback"], zoom)
            self._erase_surfs[zoom] = self._scaled_img(gateway_imgs["exiterase"], zoom)
            self._erase_hitbox_surfs[zoom] = self._scaled_img(gateway_hitbox_imgs["exiterase"], zoom)

    def open(self):
        if not self.opened:
            self.opened = True
            self._build_surfaces()


class EntryTile(GatewayTile):
    """Entry tile tracks charge independently. Once fully charged it notifies
    the parent Gateway which then unlocks all tiles."""

    # charge thresholds for visual stages (fraction of maxCharge)
    STAGE_THRESHOLDS = [0.0, 0.01, 0.5, 1.0]

    def __init__(self, tile_x, tile_y, tile_size, default_zooms, max_charge, opened=False):
        super().__init__(tile_x, tile_y, tile_size, default_zooms)
        self.max_charge = max_charge
        self.charge = 0.0
        self.opened = opened
        self.charge_stage = 0  # 0=closed, 1-3=charging stages, 4=opened
        self.gateway = None  # set by Gateway after construction

        # pre-scale activator hitbox at zoom=1 for laser detection
        self._activator_hitbox = pygame.transform.scale(gateway_hitbox_imgs["activator"], (int(tile_size), int(tile_size)))

        self._build_surfaces()
        self.health_bar = HealthBar(self.max_charge)

    def _build_surfaces(self):
        for zoom in self.default_zooms:
            if self.opened:
                self._hitbox_surfs[zoom] = self._scaled_img(gateway_hitbox_imgs["entryopened"], zoom)
                self._front_surfs[zoom] = self._scaled_img(gateway_imgs["entryopened"], zoom)
            else:
                self._hitbox_surfs[zoom] = self._scaled_img(gateway_hitbox_imgs["entryclosed"], zoom)
                stage = self.charge_stage  # 0–3
                img = gateway_imgs["entryclosed"] if stage == 0 else gateway_imgs[f"entrycharging{stage}"]
                self._front_surfs[zoom] = self._scaled_img(img, zoom)
            self._back_surfs[zoom] = self._scaled_img(gateway_imgs["entryback"], zoom)
            self._erase_surfs[zoom] = self._scaled_img(gateway_imgs["entryerase"], zoom)
            self._erase_hitbox_surfs[zoom] = self._scaled_img(gateway_hitbox_imgs["entryerase"], zoom)

    def is_laser_hitting_activator(self, wx, wy):
        """Precise check: is world point (wx,wy) inside the activator sub-region?"""
        lx = int(wx - self.tile_left)
        ly = int(wy - self.tile_top)
        if 0 <= lx < int(self.tile_size) and 0 <= ly < int(self.tile_size):
            return self._activator_hitbox.get_at((lx, ly))[3] > 128
        return False

    def add_charge(self, amount):
        """Add charge. Returns True if gateway should now unlock."""
        if self.opened:
            return False
        self.charge = min(self.max_charge, self.charge + amount)
        # update visual stage
        new_stage = 0
        for i, thresh in enumerate(self.STAGE_THRESHOLDS):
            if self.charge / self.max_charge >= thresh:
                new_stage = i
        if new_stage != self.charge_stage:
            self.charge_stage = new_stage
            self._build_surfaces()
        return self.charge >= self.max_charge

    def open(self):
        if not self.opened:
            self.opened = True
            self._build_surfaces()

    def draw_health_bar(self, surface, frame, time=None, offset_x=0, offset_y=0):
        cam_x, cam_y, zoom = frame
        self.health_bar.draw(surface, (255, 255, 255), ((self.x - cam_x + 40) * zoom + offset_x, (self.top - cam_y) * zoom + offset_y), self.charge, time)


# ---------------------------------------------------------------------------
# Gateway — one horizontal row of tiles
# ---------------------------------------------------------------------------


class Gateway:
    """A full-width horizontal gateway at a fixed Y position.
    Composed of CorridorTiles, EntryTiles, and ExitTiles.
    Entry positions and exit positions are supplied at construction time."""

    def __init__(self, gateway_index, world_width, tile_size, default_zooms, entry_columns, exit_columns, max_charge_per_entry):
        self.gateway_index = gateway_index
        self.y = GATEWAY_Y_POSITIONS[gateway_index]
        self.tile_size = tile_size
        self.default_zooms = default_zooms
        self.unlocked = False
        self.on_unlock = None  # callback set by terrain: called when unlocked

        num_tiles = math.ceil(world_width / tile_size)
        self.tiles = []

        for col in range(num_tiles):
            tile_x = col * tile_size
            tile_y = self.y - tile_size / 2  # gateway row centred on self.y
            if col in exit_columns:
                tile = ExitTile(tile_x, tile_y, tile_size, default_zooms)
            elif col in entry_columns:
                tile = EntryTile(tile_x, tile_y, tile_size, default_zooms, max_charge_per_entry)
                tile.gateway = self
            else:
                tile = CorridorTile(tile_x, tile_y, tile_size, default_zooms)
            self.tiles.append(tile)

        self.entry_tiles = [t for t in self.tiles if isinstance(t, EntryTile)]
        self.exit_tiles = [t for t in self.tiles if isinstance(t, ExitTile)]

    def tick(self, terrain, player, lx, ly):
        """Check laser hits on activators each frame. Returns True if activator is hit."""
        for entry in self.entry_tiles:
            if entry.is_laser_hitting_activator(lx, ly):
                if not self.unlocked:
                    player.drain_damage(10)
                    if entry.add_charge(10):
                        self._unlock(terrain)
                    entry.health_bar.trigger()
                return True
        return False

    def _unlock(self, terrain):
        self.unlocked = True
        for tile in self.tiles:
            tile.open()
        # rebuild chunk hitboxes for all affected tiles
        for tile in self.tiles:
            terrain.reblit_structure_on_chunks(tile)
        if self.on_unlock:
            self.on_unlock(self.gateway_index)

    def get_first_locked_y(self):
        """Y position of this gateway if locked, else None."""
        return self.y if not self.unlocked else None

    def draw(self, surface, frame, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w = surface.get_width()
        # cull tiles outside view
        view_left = left - self.tile_size
        view_right = left + w / zoom + self.tile_size
        for tile in self.tiles:
            if tile.tile_left < view_right and tile.tile_left + tile.tile_size > view_left:
                tile.draw(surface, frame, offset_x=offset_x, offset_y=offset_y)

    def draw_back(self, surface, frame, offset_x=0, offset_y=0):
        left, top, zoom = frame
        w = surface.get_width()
        view_left = left - self.tile_size
        view_right = left + w / zoom + self.tile_size
        for tile in self.tiles:
            if tile.tile_left < view_right and tile.tile_left + tile.tile_size > view_left:
                tile.draw_back(surface, frame, offset_x=offset_x, offset_y=offset_y)
