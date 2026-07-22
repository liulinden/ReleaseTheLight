import math
import random

import pygame


def init():
    pass  # impact images now loaded in aplayer.init() and scaled in Player.__init__


class Laser:
    def __init__(self):
        self.angle = 0
        self.length = 0
        self.start_x = 0
        self.start_y = 0
        self.dig_speed = 1
        self.thickness = 5
        self.laser_points = []
        self.laser_points2 = []
        self.sin_wave_offset = 0
        self.timer = 0
        self.laser_time = 400
        self.max_length = 400
        self.collision = []
        self.damage_frame = False
        self.hitboxes = []
        self.laser_target = None
        self.previous_target = None

        self._step = 1

    def get_laser_points(self, n_points):
        n_points = max(3, 1 + round(self.length / 40))
        spacing = self.length / (n_points - 1)

        points = []
        points.append(0)
        for i in range(n_points - 2):
            points.append(spacing * i + random.random() * spacing)
        points.append(self.length)
        for i in range(n_points - 2):
            points.append(spacing * (n_points - 3 - i) + random.random() * spacing)
        return points

    def get_length(self, terrain, angle):
        self.hitboxes = []
        self.collision = []
        self.laser_target = None
        dx = math.cos(angle)
        dy = math.sin(angle)
        step = self._step
        distance = 0

        while distance < self.max_length:
            wx = int(self.start_x + dx * distance)
            wy = int(self.start_y + dy * distance)

            if terrain.laser_collide_point(wx, wy):
                # nest check: AABB pre-screen then precise pixel sample from nest's hitbox image
                hit_nest = None
                for n in terrain._active_nests():
                    if n.close(wx, wy, 5):
                        # precise: sample nest's zoom=1 hitbox at local coordinates
                        l = int(wx - n.left) - 1
                        t = int(wy - n.top) - 1
                        r = l + 2
                        b = t + 2
                        for lx in range(l, r + 1):
                            for ly in (t, b):
                                if 0 <= lx < int(n.size) and 0 <= ly < int(n.size):
                                    if n.resized_hitboxes[1].get_at((lx, ly))[3] > 128:
                                        hit_nest = n
                                        break
                        for ly in range(t, b + 1):
                            for ly in (l, r):
                                if 0 <= lx < int(n.size) and 0 <= ly < int(n.size):
                                    if n.resized_hitboxes[1].get_at((lx, ly))[3] > 128:
                                        hit_nest = n
                                        break
                        if hit_nest is not None:
                            break

                if hit_nest is not None:
                    self.collision = [(wx, wy), "nests"]
                    self.laser_target = hit_nest
                else:
                    hit_enemy = False
                    for n in terrain._active_nests():
                        for enemy in n.enemies:
                            if enemy.mode != "Spawn" and enemy.rect.collidepoint(wx, wy):
                                self.collision = [(wx, wy), "enemies"]
                                self.laser_target = enemy
                                hit_enemy = True
                                break
                        if hit_enemy:
                            break
                    if not hit_enemy:
                        self.collision = [(wx, wy), "ground"]
                break

            self.hitboxes.append((wx, wy))
            distance += step

        return distance + step / 2

    def update_laser(self, terrain, start_x, start_y, angle, laser_cooldown=0):
        self.start_x, self.start_y = start_x, start_y
        self.angle = angle
        self.length = self.get_length(terrain, angle)
        if laser_cooldown != 0:
            self.laser_time = laser_cooldown
        return self.laser_target is self.previous_target and self.laser_target is not None

    def tick(self, frame_length):
        self.sin_wave_offset += frame_length / 100
        self.timer -= frame_length
        self.damage_frame = False
        if self.timer <= 0:
            self.timer = self.laser_time
            self.laser_points = self.get_laser_points(6)
            self.laser_points2 = self.get_laser_points(6)
            self.damage_frame = True
            self.previous_target = self.laser_target

    def draw(self, surface, frame, color, hitboxes=False, offset_x=0, offset_y=0):
        left, top, zoom = frame
        if hitboxes:
            for wx, wy in self.hitboxes:
                pygame.draw.circle(surface, color, (int((wx - left) * zoom + offset_x), int((wy - top) * zoom + offset_y)), max(2, int(zoom * 2)))
        else:
            for laser_part in [self.laser_points, self.laser_points2]:
                oglength = laser_part[int(len(laser_part) / 2)]
                scale = self.length / oglength
                polygon_points = []
                for point in laser_part:
                    if True or point <= self.length:  # noqa: SIM222
                        wave_height = self.thickness * math.sin((point + self.sin_wave_offset) * 1.5) * (0.5 + self.timer / self.laser_time)
                        if laser_part.index(point) % (len(laser_part) / 2) == 0:
                            x, y = (point * math.cos(self.angle) * scale, point * math.sin(self.angle) * scale)
                        else:
                            x, y = (point * math.cos(self.angle) * scale + wave_height * math.sin(self.angle), point * math.sin(self.angle) * scale - wave_height * math.cos(self.angle))
                        polygon_points.append(((x + self.start_x - left) * zoom + offset_x, (y + self.start_y - top + 3) * zoom + offset_y))
                    else:
                        print(self.length)
                        self.laser_points = self.get_laser_points(6)
                        self.laser_points2 = self.get_laser_points(6)
                        self.draw(surface, frame, color, hitboxes=hitboxes)
                        return
                if len(polygon_points) >= 3:
                    pygame.draw.polygon(surface, color, polygon_points)
