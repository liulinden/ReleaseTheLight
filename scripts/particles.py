import math
import random

import pygame


class Particles:
    def __init__(self):
        self.particles = []
        self.pulse_particles = []
        self.light_particles = []
        self.scratch_layer = None
        self.scratch_layer_size = None

    def update_scratch_layer(self, dimensions):
        if dimensions != self.scratch_layer_size:
            self.scratch_layer = pygame.Surface(dimensions, pygame.SRCALPHA)
            self.scratch_layer_size = dimensions

    def spawn_mining_particles(self, n, color, size, x, y, time=500):
        for i in range(n):
            angle = -random.random() * 2 * math.pi
            scale = (random.random() + 1) / 10
            self.particles.append(MiningParticle(color, size, x, y, math.cos(angle) * scale, math.sin(angle) * scale - 0.05, time=time))

    def spawn_light_particles(self, n, color, size, x, y, time=1200, target=None):
        for i in range(n):
            angle = -random.random() * 2 * math.pi
            scale = (random.random() + 1) / 15
            self.light_particles.append(LightParticle(color, size, x, y, math.cos(angle) * scale, math.sin(angle) * scale - 0.05, time=time, target=target))

    def spawn_pulse_particle(self, color, size, x, y, time=600):
        self.pulse_particles.append(PulseParticle(color, size, x, y, time))

    def tick_particles(self, frame_length):
        for particle_set in [self.pulse_particles, self.particles, self.light_particles]:
            for i in range(len(particle_set) - 1, -1, -1):
                if particle_set[i].tick(frame_length):
                    particle_set.remove(particle_set[i])

    def draw_particles(self, surface, frame, offset_x=0, offset_y=0):
        for particle in self.particles:
            particle.draw(surface, frame, offset_x, offset_y)

    def draw_pulse_particles(self, surface: pygame.Surface, frame, offset_x=0, offset_y=0):
        self.update_scratch_layer(surface.get_size())
        self.scratch_layer.fill((0, 0, 0, 0))
        for particle in self.pulse_particles:
            particle.draw(self.scratch_layer, frame, offset_x, offset_y)
        surface.blit(self.scratch_layer, (0, 0))

    def draw_light_particles(self, surface: pygame.Surface, frame, offset_x=0, offset_y=0):
        # drawn onto a per-pixel-alpha scratch layer (like pulse particles) since a
        # plain surface ignores per-color alpha -- that's what lets these fade out
        self.update_scratch_layer(surface.get_size())
        self.scratch_layer.fill((0, 0, 0, 0))
        for particle in self.light_particles:
            particle.draw(self.scratch_layer, frame, offset_x, offset_y)
        surface.blit(self.scratch_layer, (0, 0))


class MiningParticle:
    def __init__(self, color, size, x, y, x_speed=0, y_speed=0, time=500):
        self.color = color
        self.x = x
        self.y = y
        self.x_speed = x_speed
        self.y_speed = y_speed
        self.timer = time
        self.size = random.randint(1, 3) * size / 20

    def tick(self, frame_length):
        self.y_speed += 0.0012 * frame_length
        self.x += self.x_speed * frame_length
        self.y += self.y_speed * frame_length
        self.timer -= frame_length
        return self.timer <= 0

    def draw(self, surface, frame, offset_x=0, offset_y=0):
        left, top, zoom = frame
        pygame.draw.circle(surface, self.color, ((self.x - left) * zoom + offset_x, (self.y - top) * zoom + offset_y), self.size * zoom)


class LightParticle:
    UPWARD_ACCEL = 0.0001  # weak, constant -- becomes the dominant force only once the initial burst decays away
    SPEED_DECAY = 0.994  # per-ms exponential decay applied to both the initial burst and the upward drift
    DRIFT_ACCEL = 0.0006  # pull toward target, if one is set
    FADE_DURATION = 300  # ms -- opacity eases to 0 over this final stretch of life instead of vanishing outright

    def __init__(self, color, size, x, y, x_speed=0, y_speed=0, time=1200, target=None):
        self.color = color
        self.x = x
        self.y = y
        self.x_speed = x_speed
        self.y_speed = y_speed
        self.timer = time
        self.fade_duration = min(LightParticle.FADE_DURATION, time)  # never fade longer than the particle actually lives
        self.size = random.randint(1, 3) * size / 20
        self.target = target

    def tick(self, frame_length):
        decay = self.SPEED_DECAY**frame_length
        self.x_speed *= decay
        self.y_speed *= decay

        if self.target is not None:
            tx, ty = self.target
            dx, dy = tx - self.x, ty - self.y
            d = math.hypot(dx, dy)
            if d > 0:
                self.x_speed += dx / d * self.DRIFT_ACCEL * frame_length
                self.y_speed += dy / d * self.DRIFT_ACCEL * frame_length
        else:
            self.y_speed -= self.UPWARD_ACCEL * frame_length

        self.x += self.x_speed * frame_length
        self.y += self.y_speed * frame_length
        self.timer -= frame_length
        return self.timer <= 0

    def draw(self, surface, frame, offset_x=0, offset_y=0):
        left, top, zoom = frame
        alpha = 255 if self.timer > self.fade_duration else max(0, int(255 * self.timer / self.fade_duration))
        color = (self.color[0], self.color[1], self.color[2], alpha)
        pygame.draw.circle(surface, color, ((self.x - left) * zoom + offset_x, (self.y - top) * zoom + offset_y), self.size * zoom)


class PulseParticle:
    def __init__(self, color, size, x, y, time=0):
        self.color = color
        self.x = x
        self.y = y
        self.timer = time if time != 0 else size * 20
        self.size = size
        self.opacity = 150

        if self.timer == 0:
            self.timer = size * 10

    def tick(self, frame_length):
        self.timer -= frame_length
        factor = self.timer / (self.timer + frame_length)
        self.size *= factor
        self.opacity *= factor
        return self.timer <= 5

    def draw(self, surface, frame, offset_x=0, offset_y=0):
        left, top, zoom = frame
        pygame.draw.circle(surface, (self.color[0], self.color[1], self.color[2], 100), ((self.x - left) * zoom + offset_x, (self.y - top) * zoom + offset_y), self.size * zoom, 2)
