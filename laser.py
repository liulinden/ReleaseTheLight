import pygame, math, random


class Laser:
    def __init__(self):
        self.angle = 0
        self.length = 0
        self.startX = 0
        self.startY = 0
        self.digSpeed = 1
        self.thickness = 5
        self.laserPoints = []
        self.laserPoints2 = []
        self.sinWaveOffset = 0
        self.timer = 0
        self.laserTime = 400
        self.laserWidth = 20
        self.maxLength = 400
        self.collision = []
        self.damageFrame = False
        self.hitboxes = []

        # step size for ray march — small enough to never skip thin terrain
        self._step = 3

    def getLaserPoints(self, n_points):
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

    def getLength(self, terrain, angle):
        self.hitboxes = []
        self.collision = []

        dx = math.cos(angle)
        dy = math.sin(angle)
        step = self._step
        distance = 0

        while distance < self.maxLength:
            wx = self.startX + dx * distance
            wy = self.startY + dy * distance

            if terrain.laserCollideRect(pygame.Rect(wx, wy, 1, 1)):
                # hit — classify what was hit
                hitRect = pygame.Rect(wx - self.laserWidth / 2,
                                      wy - self.laserWidth / 2,
                                      self.laserWidth, self.laserWidth)
                if terrain.nestsCollideRect(hitRect):
                    self.collision = [(wx, wy), "nests"]
                else:
                    # check enemies via AABB
                    hitEnemy = False
                    for n in terrain.nests:
                        for enemy in n.enemies:
                            if enemy.mode != "Spawn" and hitRect.colliderect(enemy.rect):
                                self.collision = [(wx, wy), "enemies"]
                                hitEnemy = True
                                break
                        if hitEnemy:
                            break
                    if not hitEnemy:
                        self.collision = [(wx, wy), "ground"]
                break

            self.hitboxes.append((wx, wy))  # store centre point for debug drawing
            distance += step

        return distance + step / 2

        dx *= self.laserWidth / 2 / self.length
        dy *= self.laserWidth / 2 / self.length

        self.collision = []

        rect = pygame.Rect(self.startX - self.laserWidth / 2,
                           self.startY - self.laserWidth / 2,
                           self.laserWidth, self.laserWidth)
        for i in range(math.ceil(self.maxLength / (self.laserWidth / 2))):
            if terrain.collideRect(rect):
                self.collision = [rect.center]
                return angle, i * self.laserWidth / 2
            rect.x += dx
            rect.y += dy
        return angle, self.maxLength

    def updateLaser(self, terrain, startX, startY, angle, laserCooldown=0):
        self.startX, self.startY = startX, startY
        self.angle = angle
        self.length = self.getLength(terrain, angle)
        if laserCooldown != 0:
            self.laserTime = laserCooldown

    def tick(self, frameLength):
        self.sinWaveOffset += frameLength / 100
        self.timer -= frameLength
        self.damageFrame = False
        if self.timer <= 0:
            self.timer = self.laserTime
            self.laserPoints = self.getLaserPoints(6)
            self.laserPoints2 = self.getLaserPoints(6)
            self.damageFrame = True

    def draw(self, surface, frame, color, hitboxes=False, offset_x=0, offset_y=0):
        left, top, zoom = frame
        if hitboxes:
            # draw each sampled point as a small dot
            for wx, wy in self.hitboxes:
                pygame.draw.circle(surface, color,
                    (int((wx - left) * zoom + offset_x),
                     int((wy - top) * zoom + offset_y)),
                    max(2, int(zoom * 2)))
        else:
            for laserPart in [self.laserPoints, self.laserPoints2]:
                oglength = laserPart[int(len(laserPart) / 2)]
                scale = self.length / oglength
                polygonPoints = []
                for point in laserPart:
                    if True or point <= self.length:
                        waveHeight = (self.thickness
                                      * math.sin((point + self.sinWaveOffset) * 1.5)
                                      * (0.5 + self.timer / self.laserTime))
                        if laserPart.index(point) % (len(laserPart) / 2) == 0:
                            x, y = (point * math.cos(self.angle) * scale,
                                    point * math.sin(self.angle) * scale)
                        else:
                            x, y = (point * math.cos(self.angle) * scale
                                     + waveHeight * math.sin(self.angle),
                                     point * math.sin(self.angle) * scale
                                     - waveHeight * math.cos(self.angle))
                        polygonPoints.append((
                            (x + self.startX - left) * zoom + offset_x,
                            (y + self.startY - top + 3) * zoom + offset_y))
                    else:
                        print(self.length)
                        self.laserPoints = self.getLaserPoints(6)
                        self.laserPoints2 = self.getLaserPoints(6)
                        self.draw(surface, frame, color, hitboxes=hitboxes)
                        return
                if len(polygonPoints) >= 3:
                    pygame.draw.polygon(surface, color, polygonPoints)