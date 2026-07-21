# imports
import math
import random
import threading

import pygame

import scripts.loading_screen as loading_screen
import scripts.UI as UI
import scripts.world as world
from config import CHUNK_SIZE
from scripts.global_assets import load_assets


class Game:
    def __init__(self, window: pygame.Surface, fps=60, full_world=True, dev_mode=False, loading_screen: loading_screen.LoadingScreen = None):

        self.set_window(window)

        self.font = pygame.font.SysFont("Arial", 16)

        # constants
        self.fps = fps
        if dev_mode:
            self.DEFAULT_ZOOMS = [0.1, 1, 1.4]
        else:
            self.DEFAULT_ZOOMS = [1, 1.4]
        # self.HITBOX_ZOOM=0.2 -- add later
        self.WORLD_WIDTH = 15 * CHUNK_SIZE
        self.WORLD_HEIGHT = 200 * CHUNK_SIZE
        # if not full_world:
        #    self.WORLD_HEIGHT = 50 * CHUNK_SIZE
        # high temporarily

        self.offset_x = 0
        self.offset_y = 0

        # set up variables
        self.mode = "play"

        self.developing_mode = dev_mode
        self.loading_screen = loading_screen

    def set_window(self, window: pygame.Surface):
        self.window = window
        self.window_width, self.window_height = window.get_size()

    def coords_window_to_world(self, coords: list[int]):
        return self.cam_x + (coords[0] - self.offset_x) / self.zoom, self.cam_y + (coords[1] - self.offset_y) / self.zoom

    def get_world_centered_cam(self):
        return self.get_centered_cam((self.WORLD_WIDTH / 2, self.WORLD_HEIGHT / 2))

    def get_centered_cam(self, center):
        return center[0] - self.window_width / self.zoom / 2, center[1] - self.window_height / self.zoom / 2

    def get_window_center_world_coords(self):
        return self.coords_window_to_world([self.window_width / 2, self.window_height / 2])

    def set_zoom(self, new_zoom, zoom_center):
        zoom_ratio = self.zoom / new_zoom
        self.cam_x -= (zoom_center[0] - self.cam_x) * (zoom_ratio - 1)
        self.cam_y -= (zoom_center[1] - self.cam_y) * (zoom_ratio - 1)
        self.zoom = new_zoom

    def update_cam_pos(self, fps, zoom, player_x, player_y, player_x_speed, player_y_speed):
        max_y = self.WORLD_HEIGHT - 100
        if zoom != 0.1:
            max_y = self.game_world.terrain.get_first_locked_gateway_y() - self.window_height / zoom / 2
        frame_length = 1000 / fps
        self.cam_offset_x += 2 * player_x_speed * frame_length
        self.cam_offset_y += 2 * player_y_speed * frame_length
        self.cam_offset_x = min(max(self.cam_offset_x, self.window_width / zoom * 1 / 6), self.window_width / zoom * (-1 / 6))
        self.cam_offset_y = min(max(self.cam_offset_y, self.window_height / zoom * 1 / 6), self.window_height / zoom * (-1 / 6))
        self.cam_offset_x, self.cam_offset_y = 0, 0
        goal_x = max(self.window_width / zoom / 2, min(self.WORLD_WIDTH - self.window_width / zoom / 2, player_x))
        if self.window_width / zoom / 2 > self.WORLD_WIDTH - self.window_width / zoom / 2:
            goal_x = player_x
        goal_y = max(-100, min(max_y, player_y))
        self.cam_x += (self.cam_offset_x + goal_x - self.cam_x - self.window_width / zoom / 2) * frame_length / 200
        self.cam_y += (self.cam_offset_y + goal_y - self.cam_y - self.window_height / zoom / 2) * frame_length / 200

    def setup(self):

        self.loading_screen.put(0.0, "Starting game setup")

        asset_loading, world_loading, _ = self.loading_screen.subsections(0, 0.4, 0.9999)

        load_assets(asset_loading)

        self.game_world = world.World(self.WORLD_WIDTH, self.WORLD_HEIGHT, loading_screen=world_loading, default_zooms=self.DEFAULT_ZOOMS, developing_mode=self.developing_mode)

        self.charge_display = UI.ChargeDisplay(self.WORLD_HEIGHT)

        self.clock = pygame.time.Clock()
        self.keys_down = {pygame.K_w: False, pygame.K_a: False, pygame.K_d: False, "mouse": False}
        self.events = {"mouseDown": False, "mouseUp": False, pygame.K_SPACE: False, pygame.K_RIGHT: False, pygame.K_LEFT: False}

        self.zoom = self.DEFAULT_ZOOMS[len(self.DEFAULT_ZOOMS) - 1]
        self.default_cam_coords = self.get_world_centered_cam()[0], -100
        self.cam_x, self.cam_y = self.default_cam_coords
        self.cam_offset_x, self.cam_offset_y = 0, 0

        self.shake = 0
        self.tilt = 0

        self.loading_screen.put(1.0, "Game setup complete.")

        threading.Thread(target=self.game_world.generate_next_layer, daemon=True).start()

    def run(self):

        running = True

        previous_time = pygame.time.get_ticks()
        self.kind_visibility = False
        practical_fps = self.fps
        self.visible_hitboxes = False
        self.loading_debug = False
        self.crosshair = False
        self.show_fps = self.developing_mode

        while running:
            # get mouse pos
            mouse_x, mouse_y = pygame.mouse.get_pos()

            # player inputs
            self.events = {"mouseDown": False, "mouseUp": False, pygame.K_SPACE: False, pygame.K_RIGHT: False, pygame.K_LEFT: False}
            for event in pygame.event.get():
                # close game
                if event.type == pygame.QUIT:
                    print("quit")
                    self.running = False
                    return

                # TEMPORARY for testing
                if event.type == pygame.MOUSEBUTTONDOWN:
                    self.events["mouseDown"] = True
                    self.keys_down["mouse"] = True
                    x, y = self.coords_window_to_world((mouse_x, mouse_y))

                if event.type == pygame.MOUSEBUTTONUP:
                    self.keys_down["mouse"] = False
                    self.events["mouseUp"] = True

                if event.type == pygame.KEYDOWN:
                    if event.key in self.keys_down:
                        self.keys_down[event.key] = True

                    if event.key in self.events:
                        self.events[event.key] = True

                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                        return

                    if event.key == pygame.K_F4:
                        self.show_fps = not self.show_fps

                    if self.developing_mode:
                        if event.key == pygame.K_z:
                            new_zoom = 0
                            new_zoom = self.DEFAULT_ZOOMS[0] if self.DEFAULT_ZOOMS.index(self.zoom) == len(self.DEFAULT_ZOOMS) - 1 else self.DEFAULT_ZOOMS[self.DEFAULT_ZOOMS.index(self.zoom) + 1]
                            self.set_zoom(new_zoom, (self.game_world.player.x, self.game_world.player.y))
                        elif event.key == pygame.K_i:
                            self.game_world.player.add_charge(100, {"white": 1, "red": 0, "blue": 0}, 500)
                        elif event.key == pygame.K_0:
                            self.kind_visibility = not self.kind_visibility
                        elif event.key == pygame.K_h:
                            self.visible_hitboxes = not self.visible_hitboxes
                        elif event.key == pygame.K_t:
                            x, y = self.coords_window_to_world((mouse_x, mouse_y))

                            self.game_world.player.x, self.game_world.player.y = x, y
                            self.game_world.player.update_rect()
                        elif event.key == pygame.K_p:
                            print(self.game_world.player.__dict__)
                        elif event.key == pygame.K_l:
                            if not self.loading_debug:
                                self.window_width, self.window_height = 300, 200
                                self.offset_x = (self.window.get_width() - self.window_width) / 2
                                self.offset_y = (self.window.get_height() - self.window_height) / 2
                            else:
                                self.window_width, self.window_height = self.window.get_size()
                                self.offset_x = 0
                                self.offset_y = 0
                            self.loading_debug = not self.loading_debug
                        elif event.key == pygame.K_F1:
                            self.crosshair = not self.crosshair

                #                        elif event.key==pygame.K_F5:
                #                            with open("_save.pkl", "wb") as file:
                #                                pickle.dump(self, file)

                if event.type == pygame.KEYUP:
                    if event.key in self.keys_down:
                        self.keys_down[event.key] = False

            if self.game_world.tick(practical_fps, (self.window_width, self.window_height), [self.cam_x, self.cam_y, self.zoom], self.coords_window_to_world((mouse_x, mouse_y)), self.keys_down, self.events):
                self.cam_x, self.cam_y = self.default_cam_coords
                self.game_world.heal_nests()
                self.game_world.remove_enemies()

            self.charge_display.update(practical_fps, self.game_world.player)

            self.update_cam_pos(practical_fps, self.zoom, self.game_world.player.x, self.game_world.player.y, self.game_world.player.x_speed, self.game_world.player.y_speed)
            # world wrapping
            # if self.gameWorld.player.x>self.WORLD_WIDTH:
            #    self.gameWorld.player.x-=self.WORLD_WIDTH
            #    self.camX-=self.WORLD_WIDTH
            # elif self.gameWorld.player.x<0:
            #    self.gameWorld.player.x+=self.WORLD_WIDTH
            #    self.camX+=self.WORLD_WIDTH

            # clear window
            self.window.fill((255, 255, 255))

            for lase in self.game_world.player.laser:
                if lase.damage_frame:
                    self.shake = self.game_world.player.laser_attributes.base_xpl / 8
                else:
                    self.shake += self.game_world.player.laser_attributes.base_xpl / 450

            self.shake *= 0.9
            if self.shake < 0.02:
                self.shake = 0

            if self.game_world.player.queued_damage > 0:
                tilt = math.sqrt(self.game_world.player.queued_damage * 5) * 2
                tilt = min(tilt, 10)
                tilt = math.copysign(tilt, self.game_world.player.queued_damage * -self.game_world.player.x_speed)
                if abs(tilt) > abs(self.tilt):
                    self.tilt = tilt
            else:
                delta = 1.8
                if self.tilt > 0:
                    self.tilt = max(0, self.tilt - delta)
                elif self.tilt < 0:
                    self.tilt = min(0, self.tilt + delta)

            # display world layer
            frame = [self.cam_x + (2 * random.random() - 1) * self.shake, self.cam_y + (2 * random.random() - 1) * self.shake, self.zoom]
            # self.window.blit(self.gameWorld.getSurface((self.window_width,self.window_height),frame,hitboxes=self.visibleHitboxes,kindVisibility=self.kindVisibility),(0,0))

            self.window.blit(
                self.game_world.get_surface(
                    (self.window_width, self.window_height),
                    frame,
                    hitboxes=self.visible_hitboxes,
                    kind_visibility=self.kind_visibility,
                    real_window_size=self.window.get_size(),
                    offset_x=self.offset_x,
                    offset_y=self.offset_y,
                    tilt=self.tilt,
                    crosshair=self.crosshair,
                ),
                (0, 0),
            )

            # display UI stuff
            self.charge_display.draw(self.window)

            if self.loading_debug:
                pygame.draw.rect(self.window, (0, 255, 0), pygame.Rect(self.offset_x, self.offset_y, self.window_width, self.window_height), 1)

            practical_fps = max(1, round(1000 / (pygame.time.get_ticks() - previous_time)))
            practical_fps = max(30, practical_fps)
            previous_time = pygame.time.get_ticks()

            if self.show_fps:
                text_surf = self.font.render(f"FPS: {self.clock.get_fps():.0f}", True, (255, 255, 255))
                self.window.blit(text_surf, (self.window_width - 10 - text_surf.get_width(), 10))

            # update window
            pygame.display.flip()

            # tick game
            self.clock.tick(self.fps)
