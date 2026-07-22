import math, pygame, random
import scripts.UI as UI
from scripts.global_assets import get_asset

enemy_attack_frames = {"1": [4, 5]}
enemy_animation_lengths = {"1": {"Spawn": 6, "Walk": 7, "Attack": 9}}
costume_dimensions = {"1": (3/8, 3/4)}

animation_fps = 15

light_gradient = None
enemy_animations = {}

def init():
    global light_gradient, enemy_animations
    light_gradient = get_asset("LightGradient")
    enemy_animations = {}
    for costume_id in ["1"]:
        animation_im_gs = {}

        spawn_im_gs = []
        for i in range(enemy_animation_lengths[costume_id]["Spawn"]):
            spawn_im_gs.append(get_asset("Enemy" + costume_id + "Spawn" + str(i + 1)))
        animation_im_gs["Spawn"] = spawn_im_gs

        walk_im_gs = []
        for i in range(enemy_animation_lengths[costume_id]["Walk"]):
            walk_im_gs.append(get_asset("Enemy" + costume_id + "Walk" + str(i + 1)))
        animation_im_gs["Walk"] = walk_im_gs

        attack_im_gs = []
        for i in range(enemy_animation_lengths[costume_id]["Attack"]):
            attack_im_gs.append(get_asset("Enemy" + costume_id + "Attack" + str(i + 1)))
        animation_im_gs["Attack"] = attack_im_gs
        animation_im_gs["AttackHitbox"] = get_asset("Enemy" + costume_id + "AttackHitbox")

        enemy_animations[costume_id] = animation_im_gs

class Enemy:
    def __init__(self, default_zooms, costume, color, x, y, size=50, health=500):
        self.costume_id = costume
        self.size = size
        self.width = self.size * costume_dimensions[self.costume_id][0]
        self.height = self.size * costume_dimensions[self.costume_id][1]
        self.max_health = health
        self.damage = health
        self.knockback = 0.2
        self.speed = 2
        self.knockback_resistance = 1
        self.gravity_multiplier = 1
        self.attack_frames = enemy_attack_frames[self.costume_id]
        self.animation_lengths = enemy_animation_lengths[self.costume_id]

        self.x = x
        self.y = y
        self.x_speed = 0
        self.y_speed = 0
        self.color = color
        self.health = self.max_health
        self.on_ground = False
        self.animation_timer = 0
        self.animation_frame = 0
        self.facing = "Right"
        self.mode = "Spawn"
        self.glow = 0
        self.r = math.dist((0, 0), (self.width / 2, self.height / 2))
        self.rect = pygame.Rect(self.x - self.width / 2, self.y - self.height / 2, self.width, self.height)
        self.health_bar = UI.HealthBar(self.max_health)

        self.resized_gradients = {}
        self.resized_im_gs = {}

        # FIX 1: pre-allocate filter surfaces for draw() and drawGradient() per zoom
        self._draw_filter = {}
        self._gradient_filter = {}

        for zoom in default_zooms:
            zoom_set = {}
            for direction in ["Left", "Right"]:
                imgs = {}

                resizedspawns = []
                for spawn_img in enemy_animations[self.costume_id]["Spawn"]:
                    resized = pygame.transform.scale(spawn_img, (self.size * zoom, self.size * zoom))
                    if direction == "Left":
                        resized = pygame.transform.flip(resized, True, False)
                    resizedspawns.append(resized)
                imgs["Spawn"] = resizedspawns

                resizedwalks = []
                for walk_img in enemy_animations[self.costume_id]["Walk"]:
                    resized = pygame.transform.scale(walk_img, (self.size * zoom, self.size * zoom))
                    if direction == "Left":
                        resized = pygame.transform.flip(resized, True, False)
                    resizedwalks.append(resized)
                imgs["Walk"] = resizedwalks

                resized_attacks = []
                for attack_img in enemy_animations[self.costume_id]["Attack"]:
                    resized = pygame.transform.scale(attack_img, (self.size * zoom, self.size * zoom))
                    if direction == "Left":
                        resized = pygame.transform.flip(resized, True, False)
                    resized_attacks.append(resized)
                imgs["Attack"] = resized_attacks

                resized = pygame.transform.scale(enemy_animations[self.costume_id]["AttackHitbox"], (self.size * zoom, self.size * zoom))
                if direction == "Left":
                    resized = pygame.transform.flip(resized, True, False)
                imgs["AttackHitbox"] = resized

                zoom_set[direction] = imgs
            self.resized_im_gs[zoom] = zoom_set

            grad_img = pygame.transform.scale(light_gradient, (self.size * 2 * zoom, self.size * 2 * zoom))
            self.resized_gradients[zoom] = grad_img
            self._draw_filter[zoom] = pygame.Surface((self.size * zoom, self.size * zoom), flags=pygame.SRCALPHA)
            self._gradient_filter[zoom] = pygame.Surface(grad_img.get_size(), flags=pygame.SRCALPHA)

    def spawn_particles(self, _terrain):
        _terrain.particles.spawn_mining_particles(15, self.color, self.size / 3, self.x, self.y)

    def update_costume(self, frame_length, player):
        self.glow += (0 - self.glow) / 500 * frame_length
        self.animation_timer = self.animation_timer + frame_length
        if self.mode == "Spawn":
            if self.animation_timer >= self.animation_lengths["Spawn"] * 1000 / animation_fps:
                self.mode = "Walk"
                self.animation_timer = 0
        elif self.mode == "Walk":
            self.animation_timer = self.animation_timer % (self.animation_lengths["Walk"] * 1000 / animation_fps)
        elif self.mode == "Attack":
            if self.animation_timer >= self.animation_lengths["Attack"] * 1000 / animation_fps:
                self.mode = "Walk"
                self.animation_timer = 0

        if self.mode == "Walk":
            if self.x < player.x:
                self.facing = "Right"
            elif self.x > player.x:
                self.facing = "Left"

        self.animation_frame = math.floor(self.animation_timer / (1000 / animation_fps))

    def update_rect(self):
        self.rect.x, self.rect.y = self.x - self.width / 2, self.y - self.height / 2

    def draw_gradient(self, surface, frame, offset_x=0, offset_y=0):
        cam_x, cam_y, zoom = frame
        img = self.resized_gradients[zoom]
        if self.glow > 0:
            # FIX 1: reuse pre-allocated gradient filter surface
            filt = self._gradient_filter[zoom]
            filt.fill((self.color[0], self.color[1], self.color[2], self.glow))
            filt.blit(img, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(filt, ((self.x - self.size - cam_x) * zoom + offset_x, (self.y - self.size - cam_y) * zoom + offset_y))

    def draw(self, surface, frame, hitbox=False, offset_x=0, offset_y=0):
        cam_x, cam_y, zoom = frame

        self.update_rect()
        if hitbox:
            if self.mode != "Spawn":
                l = float(self.rect.left)
                r = float(self.rect.right - 1)
                t = float(self.rect.top)
                b = float(self.rect.bottom - 1)
                pygame.draw.line(surface, self.color, ((l - cam_x) * zoom + offset_x, (t - cam_y) * zoom + offset_y), ((l - cam_x) * zoom + offset_x, (b - cam_y) * zoom + offset_y))
                pygame.draw.line(surface, self.color, ((r - cam_x) * zoom + offset_x, (t - cam_y) * zoom + offset_y), ((r - cam_x) * zoom + offset_x, (b - cam_y) * zoom + offset_y))
                pygame.draw.line(surface, self.color, ((l - cam_x) * zoom + offset_x, (t - cam_y) * zoom + offset_y), ((r - cam_x) * zoom + offset_x, (t - cam_y) * zoom + offset_y))
                pygame.draw.line(surface, self.color, ((l - cam_x) * zoom + offset_x, (b - cam_y) * zoom + offset_y), ((r - cam_x) * zoom + offset_x, (b - cam_y) * zoom + offset_y))
                if self.mode == "Attack" and self.animation_frame in self.attack_frames:
                    self.draw_attack_hitbox(surface, frame, offset_x=offset_x, offset_y=offset_y)
        else:
            # FIX 1: reuse pre-allocated draw filter surface
            filt = self._draw_filter[zoom]
            filt.fill(self.color)
            filt.blit(self.resized_im_gs[zoom][self.facing][self.mode][self.animation_frame], (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(filt, ((self.rect.centerx - self.size / 2 - cam_x) * zoom + offset_x, (self.rect.bottom - self.size - cam_y + 5) * zoom + offset_y))

    def draw_health_bar(self, surface, frame, time=None, offset_x=0, offset_y=0):
        cam_x, cam_y, zoom = frame
        self.health_bar.draw(surface, self.color, ((self.rect.centerx - cam_x) * zoom + offset_x, (self.rect.bottom - self.size - cam_y + 5) * zoom + offset_y), self.health, time)

    def draw_attack_hitbox(self, surface, frame, offset_x=0, offset_y=0):
        # never used
        cam_x, cam_y, zoom = frame
        surface.blit(self.resized_im_gs[zoom][self.facing]["AttackHitbox"], ((self.rect.centerx - self.size / 2 - cam_x) * zoom + offset_x, (self.rect.bottom - self.size - cam_y + 5) * zoom + offset_y))

    def deal_damage(self, damage, direct=False):
        self.glow = 255
        self.health -= damage
        if damage > 0:
            self.health_bar.trigger(direct)
        if self.health < 0:
            self.health = 0
            return True
        return False

    def tick_damage_and_knockback(self, frame_length, _terrain, player):
        for knockback_circle in _terrain.knockback_circles:
            pow, x, y, r, falloff = knockback_circle

            dx = self.x - x
            dy = self.y - y
            d = math.sqrt(dx**2 + dy**2)
            if player.laser:
                lase = player.laser[0]
                if lase.laser_target is self:
                    self.x_speed += frame_length * dx / d / self.size * pow / self.knockback_resistance
                    self.y_speed += frame_length * dy / d / self.size * pow / self.knockback_resistance
                elif d < r + self.r:
                    self.x_speed += frame_length * dx / d / self.size * pow * falloff / self.knockback_resistance
                    self.y_speed += frame_length * dy / d / self.size * pow * falloff / self.knockback_resistance
            else:
                self.x_speed += frame_length * dx / d / self.size * pow * falloff / self.knockback_resistance
                self.y_speed += frame_length * dy / d / self.size * pow * falloff / self.knockback_resistance

        for damage_circle in _terrain.player_damage_circles:
            pow, x, y, r, falloff = damage_circle

            dx = self.x - x
            dy = self.y - y
            d = math.sqrt(dx**2 + dy**2)
            if player.laser:
                lase = player.laser[0]
                if lase.laser_target is self:
                    _terrain.particles.spawn_mining_particles(10, self.color, self.size / 5, x, y)
                    if self.deal_damage(pow, True):
                        return True
                else:
                    if d < r + self.r:
                        _terrain.particles.spawn_mining_particles(5, self.color, self.size / 10, x, y)
                        if self.deal_damage(pow * falloff):
                            return True
            else:
                if d < r + self.r:
                    _terrain.particles.spawn_mining_particles(5, self.color, self.size / 10, x, y)
                    if self.deal_damage(pow * falloff):
                        return True

    def tick_gravity(self, frame_length):
        self.y_speed = min(0.4, self.y_speed + 0.0015 * frame_length * self.gravity_multiplier)
    
    def tick_enemy_behavior(self, frame_length, player):
        if self.mode == "Walk":
            if player.y < self.y - 10 and self.on_ground and random.randint(1, 500) < frame_length:
                self.y_speed = -0.3
            if abs(player.x - self.x) > self.size / 2 or abs(player.y - self.y) > self.size / 2:
                rand = random.randint(0, 3)
                if (player.x < self.x and rand != 3) or rand == 0:
                    if self.on_ground:
                        self.x_speed -= 0.001 * frame_length * self.speed
                    else:
                        self.x_speed -= 0.0003 * frame_length * self.speed
                else:
                    if self.on_ground:
                        self.x_speed += 0.001 * frame_length * self.speed
                    else:
                        self.x_speed += 0.0003 * frame_length * self.speed
            else:
                self.mode = "Attack"
                self.animation_timer = 0

            if self.on_ground:
                self.x_speed *= 0.98**frame_length
            else:
                self.x_speed *= 0.993**frame_length

    def attempt_movement(self, frame_length, _terrain):
        self.move_vertical(frame_length, _terrain)
        self.move_horizontal(frame_length, _terrain)
    
    def check_despawn(self, player):
        return math.dist((self.x, self.y), (player.x, player.y)) > 500

    def handle_attack(self, player):
        if player.immunity_timer == 0 and self.mode == "Attack" and self.animation_frame in self.attack_frames:
            if self.attack_collide_rect(player.rect):
                player.immunity_timer = player.immunity_time
                if self.facing == "Right":
                    player.x_speed = self.knockback
                else:
                    player.x_speed = - self.knockback
                player.y_speed = - self.knockback
                player.deal_damage(self.damage)

    def tick(self, frame_length, _terrain, player):
        if self.mode != "Spawn":
            self.tick_gravity(frame_length)
            if self.tick_damage_and_knockback(frame_length, _terrain, player): return True
            self.tick_enemy_behavior(frame_length, player)
            self.attempt_movement(frame_length, _terrain)
            self.handle_attack(player)
            if self.check_despawn(player): return True
        self.update_costume(frame_length, player)
        return False

    def move_horizontal(self, frame_length, _terrain):
        self.x += frame_length * self.x_speed
        self.update_rect()
        if self.colliding_with_terrain(_terrain):
            slope_tolerance = math.ceil(3 * abs(frame_length * self.x_speed))
            for i in range(slope_tolerance):
                self.y -= 1
                self.update_rect()
                if not self.colliding_with_terrain(_terrain):
                    if self.x_speed > 0:
                        self.x_speed -= self.x_speed * i / slope_tolerance
                    else:
                        self.x_speed -= self.x_speed * i / slope_tolerance
                    return
            self.y += slope_tolerance
            self.x -= frame_length * self.x_speed
            backs = math.ceil(abs(frame_length * self.x_speed / 1))
            for i in range(backs):
                self.x += frame_length * self.x_speed / backs
                self.update_rect()
                if self.colliding_with_terrain(_terrain):
                    self.x -= frame_length * self.x_speed / backs
                    self.update_rect()
                    break
            self.x_speed = 0

    def move_vertical(self, frame_length, _terrain):
        self.on_ground = False
        self.y += frame_length * self.y_speed
        self.update_rect()
        if self.colliding_with_terrain(_terrain):
            if self.y_speed > 0:
                self.on_ground = True
                if not _terrain.nests_collide_rect(self.rect):
                    _terrain.particles.spawn_mining_particles(
                        int(abs((abs(max(0.005 * frame_length, abs(self.x_speed))) - 0.005 * frame_length) + 3 * (self.y_speed - 0.0015 * frame_length)) * 12), (0, 0, 0), 20, self.x, self.y + self.height / 2, time=200
                    )
            if self.y_speed < 0:
                slope_tolerance = math.ceil(abs(0.5 * frame_length * self.y_speed))
                for i in range(slope_tolerance):
                    self.x -= 1
                    self.update_rect()
                    if not self.colliding_with_terrain(_terrain):
                        return
                self.x += slope_tolerance
                for i in range(slope_tolerance):
                    self.x += 1
                    self.update_rect()
                    if not self.colliding_with_terrain(_terrain):
                        return
                self.x -= slope_tolerance
            self.y -= frame_length * self.y_speed
            backs = math.ceil(abs(frame_length * self.y_speed / 1))
            for i in range(backs):
                self.y += frame_length * self.y_speed / backs
                self.update_rect()
                if self.colliding_with_terrain(_terrain):
                    self.y -= frame_length * self.y_speed / backs
                    self.update_rect()
                    break
            self.y_speed = 0

    def colliding_with_terrain(self, _terrain):
        return _terrain.collide_rect(self.rect)

    def attack_collide_rect(self, rect: pygame.Rect):
        rect_mask = pygame.Mask((rect.width, rect.height), fill=True)
        surface = pygame.Surface((rect.width, rect.height), flags=pygame.SRCALPHA)
        self.draw_attack_hitbox(surface, [rect.left, rect.y, 1])
        attack_mask = pygame.mask.from_surface(surface)
        return attack_mask.overlap(rect_mask, (0, 0)) is not None