import math

import pygame

import laser
import laserProperties
import terrain
from global_assets import get_asset
from util import channel_bound, charges_to_color, rotate_and_get_offset

SPRITE_WIDTH = 40
SPRITE_HEIGHT = 40
ARM_PIVOT_X = 20
ARM_PIVOT_Y = 21

IMPACT_SIZE = 100  # world-space size in px — easy to change
IMPACT_FPS = 24
IMPACT_FRAMES = 7

PLAYER_IMGS = {}
LASER_IMPACT_IMGS_RAW = []  # raw unscaled images, loaded in init()
ANIMATION_LENGTHS = {"Idle": 8, "Run": 8, "Backpedal": 8, "Falling": 1, "Jumping": 1}
ANIMATION_FPS = 13


def filter_charges(filter_type, charges):
    match filter_type:
        case "white":
            return charges
        case "blue":
            return {"white": 0, "blue": charges["white"] / 2 + charges["blue"], "red": 0}
        case "red":
            return {"white": 0, "blue": 0, "red": charges["white"] / 2 + charges["red"]}


filter_feeds = {"white": {"white": (1, 0, 0), "blue": (0, 1, 0), "red": (0, 0, 1)}, "blue": {"white": (0, 0.5, 0), "blue": (0, 1, 0), "red": (0, 0, 0)}, "red": {"white": (0, 0, 0.5), "blue": (0, 0, 0), "red": (0, 0, 1)}}


def init():
    global PLAYER_IMGS, LASER_IMPACT_IMGS_RAW

    img_set = []
    for i in range(5):
        img_set.append(get_asset("PlayerIdle" + str(i + 1)))
    for i in range(3):
        img_set.append(get_asset("PlayerIdle" + str(4 - i)))
    PLAYER_IMGS["Idle"] = img_set

    img_set = []
    for i in range(8):
        img_set.append(get_asset("PlayerRun" + str(i + 1)))
    PLAYER_IMGS["Run"] = img_set

    # TEMPORARY ANIMATION
    img_set = []
    for i in range(8):
        img_set.append(get_asset("PlayerRun" + str(8 - i)))
    PLAYER_IMGS["Backpedal"] = img_set

    PLAYER_IMGS["Falling"] = [get_asset("PlayerFalling")]
    PLAYER_IMGS["Jumping"] = [get_asset("PlayerJumping")]
    # playerIMGs["Sliding"]=[get_asset("PlayerSliding")]
    PLAYER_IMGS["Arm"] = [get_asset("Arm")]

    LASER_IMPACT_IMGS_RAW = []
    for i in range(1, IMPACT_FRAMES + 1):
        LASER_IMPACT_IMGS_RAW.append(get_asset(f"LaserImpact{i}"))


class LaserImpact:
    """Single impact animation instance. Follows the live laser endpoint while
    the laser is active, then freezes at its last known position."""

    _frame_duration = 1000 / IMPACT_FPS

    def __init__(self, x, y, angle, source_laser, scaled_im_gs):
        self.x = x
        self.y = y
        self.angle = angle
        self.source_laser = source_laser  # reference to spawning Laser; set to None when gone
        self.scaled_im_gs = scaled_im_gs  # pre-scaled images for all zooms
        self.timer = 0.0

    def tick(self, frame_length, active_lasers):
        # update position if source laser is still active
        if self.source_laser is not None:
            if self.source_laser in active_lasers:
                lase = self.source_laser
                self.x = lase.start_x + math.cos(lase.angle) * lase.length
                self.y = lase.start_y + math.sin(lase.angle) * lase.length
                self.angle = lase.angle
            else:
                self.source_laser = None  # laser gone — freeze position

        self.timer += frame_length
        return self.timer >= self._frame_duration * IMPACT_FRAMES  # True = finished

    def draw(self, surface, frame, color, zoom):
        left, top, _ = frame
        frame_index = min(IMPACT_FRAMES - 1, int(self.timer / self._frame_duration))
        img = self.scaled_im_gs[zoom][frame_index]

        size = img.get_size()
        tinted = img.copy()
        color_surf = pygame.Surface(size, pygame.SRCALPHA)
        color_surf.fill((color[0], color[1], color[2], 255))
        tinted.blit(color_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

        cx = size[0] / 2
        cy = size[1] / 2
        rot_angle = math.pi - self.angle
        rotated, off_x, off_y = rotate_and_get_offset(tinted, cx, cy, rot_angle)

        half_h = size[1] / 2
        screen_x = (self.x - left) * zoom - cx + off_x - math.cos(self.angle) * half_h
        screen_y = (self.y - top) * zoom - cy + off_y - math.sin(self.angle) * half_h
        surface.blit(rotated, (screen_x, screen_y))


class Player:
    def __init__(self, default_zooms, x, y, dimensions=(10, 30)):
        self.spawn_x = x
        self.spawn_y = y
        self.x = x
        self.y = y
        self.x_speed = 0
        self.y_speed = 0
        self.width, self.height = dimensions
        self.rect = pygame.Rect(self.x - self.width / 2, self.y - self.height / 2, self.width, self.height)
        self.on_ground = False
        self.color = (255, 0, 0)
        self.default_zooms = default_zooms
        self.facing = "Right"
        self.animation_timer = 0
        self.animation_type = "Idle"
        self.animation_frame = 0
        self.arm_angle = 0
        self.arm_offset_x = 0
        self.arm_offset_y = 0

        self.filter_type = "white"
        self.filter_change_right = True
        self.laser_timer = 0
        self.laser_ramps = 0
        self.laser_first_hit = False
        self.laser = []
        self.impacts = []  # active LaserImpact instances
        self.laser_attributes = laserProperties.LaserAttributes(18, 1, 0.2, 10, 400, 1, 20, 0.3, 1, 20, 20, 0.5, 2, 0.5, {"white": (0, False), "blue": (0, False), "red": (0, False)})

        self.ability_timer = 0
        self.ability_cooldown = 800

        self.charge_capacity = 100
        self.charges = {"white": self.charge_capacity, "blue": 0, "red": 0}
        self.practical_charges = {"white": self.charge_capacity, "blue": 0, "red": 0}
        self.max_charge = 500
        self.immunity_timer = 0
        self.immunity_time = 500
        self.queued_damage = 0
        self.queued_drain_damage = 0

        self.player_im_gs = {}
        for zoom in self.default_zooms:
            zoom_img_sets = {}
            for direction in ["Left", "Right"]:
                direction_set = {}
                for animation_type in PLAYER_IMGS:
                    direction_set[animation_type] = []
                    for img in PLAYER_IMGS[animation_type]:
                        resized_img = pygame.transform.scale(img, (SPRITE_WIDTH * zoom, SPRITE_HEIGHT * zoom))
                        if direction == "Left":
                            resized_img = pygame.transform.flip(resized_img, True, False)
                        direction_set[animation_type].append(resized_img)
                zoom_img_sets[direction] = direction_set
            self.player_im_gs[zoom] = zoom_img_sets

        # pre-scale impact images for each zoom — done here since defaultZooms is available
        self._impact_im_gs = {}
        for zoom in self.default_zooms:
            size = int(IMPACT_SIZE * zoom)
            self._impact_im_gs[zoom] = [pygame.transform.scale(img, (size, size)) for img in LASER_IMPACT_IMGS_RAW]

    def reset_player(self):
        self.x = self.spawn_x
        self.y = self.spawn_y
        self.x_speed = 0
        self.y_speed = 0
        self.set_charges(max(150, self.charge_capacity * 2 / 3), 0, 0)
        self.filter_type = "white"
        self.practical_charges = filter_charges(self.filter_type, self.charges)

    def update_costume(self, frame_length, mouse_pos):
        self.animation_timer = (self.animation_timer + frame_length) % (1000 / ANIMATION_FPS * (ANIMATION_LENGTHS[self.animation_type]))
        previous_animation_type = self.animation_type

        target_x, target_y = mouse_pos

        if self.x < target_x:
            self.facing = "Right"
        elif self.x > target_x:
            self.facing = "Left"

        self.arm_angle = -math.atan2(target_y - self.y, target_x - self.x)

        if not self.on_ground:
            if self.y_speed > 0.2:
                self.animation_type = "Falling"
            elif self.y_speed < -0.2:
                self.animation_type = "Jumping"
        else:
            if abs(self.x_speed) > 0.1:
                if (self.x_speed > 0 and self.facing == "Right") or (self.x_speed < 0 and self.facing == "Left"):
                    self.animation_type = "Run"
                else:
                    self.animation_type = "Backpedal"
            else:
                self.animation_type = "Idle"

        if self.animation_type != previous_animation_type:
            self.animation_timer = 0

        animation_length = ANIMATION_LENGTHS[self.animation_type]
        if animation_length == 1:
            self.animation_frame = 0
        else:
            self.animation_frame = math.floor(self.animation_timer / (1000 / ANIMATION_FPS))

    def update_rect(self):
        self.rect.x, self.rect.y = self.x - self.width / 2, self.y - self.height / 2

    def update_color(self):
        cw, cb, cr = self.practical_charges.values()
        self.color = charges_to_color(cw, cb, cr, self.max_charge)

    def update_laser_stats(self):
        laserProperties.set_laser_attributes(self.laser_attributes, self.practical_charges, self.filter_type, self.max_charge)

    def set_charges(self, white, blue, red):
        self.charges["white"] = white
        self.charges["blue"] = blue
        self.charges["red"] = red

    def add_charge(self, added_charge, charge_distribution, max_charge):

        sum_added = 0
        for color in self.charges:
            add = charge_distribution[color] * added_charge

            addw = add * filter_feeds[self.filter_type][color][0]
            addb = add * filter_feeds[self.filter_type][color][1]
            addr = add * filter_feeds[self.filter_type][color][2]

            self.charges["white"] += addw
            self.charges["blue"] += addb
            self.charges["red"] += addr

            sum_added += addw + addb + addr

        total_charge = sum(self.charges.values())
        overflow = 0
        if total_charge > self.charge_capacity:
            self.charge_capacity = max(self.charge_capacity, min(self.max_charge, min(max_charge, total_charge)))
            overflow = total_charge - self.charge_capacity

        self.lose_charge(overflow)

        self.practical_charges = filter_charges(self.filter_type, self.charges)

        return sum_added - overflow

    def lose_charge(self, loss):
        if self.filter_type == "white":
            n_split = 3
            while n_split > 0:
                split_loss = loss / n_split
                for charge in self.charges:
                    if 0 < self.charges[charge] < split_loss:
                        loss -= self.charges[charge]
                        self.charges[charge] = 0
                        n_split -= 1
                        break
                for charge in self.charges:
                    if self.charges[charge] > 0:
                        self.charges[charge] -= split_loss
                n_split = 0
        else:
            if loss < self.charges[self.filter_type]:
                self.charges[self.filter_type] -= loss
            else:
                loss -= self.charges[self.filter_type]
                self.charges[self.filter_type] = 0
                if loss < self.charges["white"]:
                    self.charges["white"] -= loss
                else:
                    loss -= self.charges["white"]
                    self.charges["white"] = 0
                    self.filter_type = "white"
                    self.lose_charge(loss)

        self.practical_charges = filter_charges(self.filter_type, self.charges)
        if sum(self.charges.values()) > 0:
            return False
        self.reset_player()
        return True

    def deal_damage(self, damage):
        self.queued_damage += damage

    def drain_damage(self, damage):
        self.queued_drain_damage += damage

    def tick(self, frame_length, c_terrain: terrain.Terrain, mouse_pos, keys_down, events):
        if self.lose_charge(self.queued_damage) or self.lose_charge(self.queued_drain_damage):
            return True
        self.queued_damage = 0
        self.queued_drain_damage = 0

        self.y_speed = min(0.4, self.y_speed + 0.0015 * frame_length)
        if self.immunity_timer > 0:
            self.immunity_timer -= frame_length
            if self.immunity_timer < 0:
                self.immunity_timer = 0

        if events[pygame.K_RIGHT]:
            self.filter_change_right = True
            match self.filter_type:
                case "white":
                    self.filter_type = "blue"
                case "blue":
                    self.filter_type = "red"
                case "red":
                    self.filter_type = "white"

        if events[pygame.K_LEFT]:
            self.filter_change_right = False
            match self.filter_type:
                case "white":
                    self.filter_type = "red"
                case "blue":
                    self.filter_type = "white"
                case "red":
                    self.filter_type = "blue"

        if events[pygame.K_SPACE] and self.ability_timer == 0 and self.laser_attributes.passed_thresholds[self.filter_type][1]:
            match self.filter_type:
                case "white":
                    mx, my = mouse_pos
                    dx, dy = mx - self.x, my - self.y
                    d = math.sqrt(dx**2 + dy**2)
                    self.x_speed = dx / d / 1.2
                    self.y_speed = dy / d / 2
                    self.ability_timer = self.ability_cooldown
                    c_terrain.particles.spawn_pulse_particle(self.color, 40, self.x, self.y)
                case "blue":
                    self.y_speed -= 0.3
                    c_terrain.new_knockback_circles.append([self.laser_attributes.base_kb * 5, self.x, self.y, self.laser_attributes.KBRange * 3, 1])
                    c_terrain.particles.spawn_pulse_particle(self.color, self.laser_attributes.KBRange * 3, self.x, self.y, 800)
                    self.ability_timer = self.ability_cooldown
                case "red":
                    self.y_speed -= 0.3
                    # explosionSize=self.laserAttributes.baseXPL*3
                    # cTerrain.addAirPocketClump(self.x, self.y, explosionSize, layerIndex=cTerrain._layerForY(self.y), playerMade=True, spreading=1/5)
                    # should detect ground and spawn particles if detected

                    c_terrain.new_player_damage_circles.append([self.laser_attributes.base_dmg, self.x, self.y, self.laser_attributes.DMGRange * 2, 1])
                    c_terrain.particles.spawn_pulse_particle(self.color, self.laser_attributes.DMGRange * 2, self.x, self.y, 800)
                    self.ability_timer = self.ability_cooldown

        if keys_down["mouse"] and len(self.laser) == 0 and self.laser_timer <= self.laser_attributes.cooldown / 4:
            new_laser = laser.Laser()
            self.laser = [new_laser]
            self.laser_ramps = 0
            self.laser_first_hit = True

        if events["mouseUp"] and len(self.laser) > 0:
            self.laser_timer = self.laser[0].timer
            self.laser = []

        self.ability_timer -= frame_length
        self.ability_timer = max(0, self.ability_timer)

        self.laser_timer -= frame_length
        self.laser_timer = max(0, self.laser_timer)

        for lase in self.laser:
            locked = lase.update_laser(
                c_terrain,
                self.x - SPRITE_WIDTH / 2 + ARM_PIVOT_X + self.laser_attributes.distance * math.cos(self.arm_angle),
                self.y - SPRITE_HEIGHT / 2 + ARM_PIVOT_Y + self.laser_attributes.distance * math.sin(-self.arm_angle),
                -self.arm_angle,
            )
            lase.tick(frame_length)
            if lase.damage_frame:
                if not locked:
                    self.laser_ramps = 0
                if lase.collision:
                    point = lase.collision[0]
                    x, y = point
                    explosion_size = laserProperties.get_laser_expl(self.laser_attributes, self.laser_first_hit, self.laser_ramps)
                    c_terrain.add_air_pocket_clump(x, y, explosion_size, layer_index=c_terrain._layer_for_y(y), player_made=True, spreading=1 / 5)
                    if lase.collision[1] == "ground":
                        c_terrain.particles.spawn_mining_particles(10, (0, 0, 0), explosion_size * 1.5, x, y)

                    c_terrain.new_knockback_circles.append(
                        [laserProperties.get_laser_kb(self.laser_attributes, self.laser_first_hit, self.laser_ramps), x, y, self.laser_attributes.KBRange, self.laser_attributes.area_kb_falloff]
                    )
                    c_terrain.new_player_damage_circles.append(
                        [laserProperties.get_laser_dmg(self.laser_attributes, self.laser_first_hit, self.laser_ramps), x, y, self.laser_attributes.DMGRange, self.laser_attributes.area_dmg_falloff]
                    )
                    c_terrain.particles.spawn_pulse_particle(self.color, self.laser_attributes.DMGRange, x, y)
                    # cTerrain.particles.spawnPulseParticle(self.color,self.laserAttributes.KBRange,x,y)
                    # cTerrain.particles.spawnPulseParticle(self.color,explosionSize,x,y)

                self.laser_first_hit = False
                self.laser_ramps += 1

                if self.lose_charge(0.5):
                    return True

                # spawn impact — position follows live laser, freezes when laser released
                end_x = lase.start_x + math.cos(lase.angle) * lase.length
                end_y = lase.start_y + math.sin(lase.angle) * lase.length
                self.impacts.append(LaserImpact(end_x, end_y, lase.angle, lase, self._impact_im_gs))

        # tick impacts, passing current active lasers so they can track position
        for i in range(len(self.impacts) - 1, -1, -1):
            if self.impacts[i].tick(frame_length, self.laser):
                del self.impacts[i]

        for knockback_circle in c_terrain.knockback_circles:
            dx = self.x - knockback_circle[1]
            dy = self.y - knockback_circle[2]
            distance = math.sqrt(dx**2 + dy**2)
            knockback = knockback_circle[0]

            self.x_speed += frame_length * dx / distance * knockback / 60
            self.y_speed += frame_length * dy / distance * knockback / 60

        for li in c_terrain.active_layers:
            for nest in c_terrain.nests[li]:
                if nest.stage == nest.max_stage and nest.within_effect_radius(self.x, self.y) and nest.charge > 0:
                    charge_gain = self.add_charge(nest.charge_rate * frame_length, nest.charging, nest.max_charge)
                    nest.lose_charge(charge_gain)

        self.update_laser_stats()

        if self.x < 50:
            self.x_speed += (50 - self.x) / 10000 * frame_length
        elif self.x > c_terrain.world_width - 50:
            self.x_speed -= (self.x - c_terrain.world_width + 50) / 10000 * frame_length

        if keys_down[pygame.K_w] and self.on_ground:
            self.y_speed = -0.4

        if keys_down[pygame.K_a]:
            if self.on_ground:
                self.x_speed -= 0.005 * frame_length
            else:
                self.x_speed -= 0.0015 * frame_length
        if keys_down[pygame.K_d]:
            if self.on_ground:
                self.x_speed += 0.005 * frame_length
            else:
                self.x_speed += 0.0015 * frame_length

        if self.on_ground:
            self.x_speed *= 0.98**frame_length
        else:
            self.x_speed *= 0.993**frame_length

        self.move_vertical(frame_length, c_terrain)
        self.move_horizontal(frame_length, c_terrain)

        self.update_color()
        self.update_costume(frame_length, mouse_pos)

        for lase in self.laser:
            lase.update_laser(
                c_terrain,
                self.x - SPRITE_WIDTH / 2 + ARM_PIVOT_X + self.laser_attributes.distance * math.cos(self.arm_angle),
                self.y - SPRITE_HEIGHT / 2 + ARM_PIVOT_Y + self.laser_attributes.distance * math.sin(-self.arm_angle),
                -self.arm_angle,
                self.laser_attributes.cooldown,
            )
        return False

    def move_horizontal(self, frame_length, c_terrain):

        # TODO - add slope platforming

        self.x += frame_length * self.x_speed
        self.update_rect()
        if self.colliding_with_terrain(c_terrain):
            slope_tolerance = math.ceil(3 * abs(frame_length * self.x_speed))
            for i in range(slope_tolerance):
                self.y -= 1
                self.update_rect()
                if not self.colliding_with_terrain(c_terrain):
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
                if self.colliding_with_terrain(c_terrain):
                    self.x -= frame_length * self.x_speed / backs
                    self.update_rect()
                    break
            self.x_speed = 0

    def move_vertical(self, frame_length, c_terrain: terrain.Terrain):
        self.on_ground = False
        self.y += frame_length * self.y_speed
        self.update_rect()
        if self.colliding_with_terrain(c_terrain):
            if self.y_speed > 0:
                self.on_ground = True
                if not c_terrain.nests_collide_rect(self.rect):
                    c_terrain.particles.spawn_mining_particles(
                        int(abs((abs(max(0.005 * frame_length, abs(self.x_speed)) - 0.005 * frame_length) + 3 * (self.y_speed - 0.0015 * frame_length)) * 12)), (0, 0, 0), 20, self.x, self.y + self.height / 2, time=200
                    )
            if self.y_speed < 0:
                slope_tolerance = math.ceil(abs(0.5 * frame_length * self.y_speed))
                for i in range(slope_tolerance):
                    self.x -= 1
                    self.update_rect()
                    if not self.colliding_with_terrain(c_terrain):
                        return
                self.x += slope_tolerance
                for i in range(slope_tolerance):
                    self.x += 1
                    self.update_rect()
                    if not self.colliding_with_terrain(c_terrain):
                        return
                self.x -= slope_tolerance
            self.y -= frame_length * self.y_speed
            backs = math.ceil(abs(frame_length * self.y_speed / 1))
            for i in range(backs):
                self.y += frame_length * self.y_speed / backs
                self.update_rect()
                if self.colliding_with_terrain(c_terrain):
                    self.y -= frame_length * self.y_speed / backs
                    self.update_rect()
                    break
            self.y_speed = 0

    def draw(self, surface, frame, hitboxes=False, offset_x=0, offset_y=0, tilt=0):
        cam_x, cam_y, zoom = frame
        if hitboxes:
            self.update_rect()
            l = float(self.rect.left)
            r = float(self.rect.right - 1)
            t = float(self.rect.top)
            b = float(self.rect.bottom - 1)
            pygame.draw.line(surface, self.color, ((l - cam_x) * zoom + offset_x, (t - cam_y) * zoom + offset_y), ((l - cam_x) * zoom + offset_x, (b - cam_y) * zoom + offset_y))
            pygame.draw.line(surface, self.color, ((r - cam_x) * zoom + offset_x, (t - cam_y) * zoom + offset_y), ((r - cam_x) * zoom + offset_x, (b - cam_y) * zoom + offset_y))
            pygame.draw.line(surface, self.color, ((l - cam_x) * zoom + offset_x, (t - cam_y) * zoom + offset_y), ((r - cam_x) * zoom + offset_x, (t - cam_y) * zoom + offset_y))
            pygame.draw.line(surface, self.color, ((l - cam_x) * zoom + offset_x, (b - cam_y) * zoom + offset_y), ((r - cam_x) * zoom + offset_x, (b - cam_y) * zoom + offset_y))
            for lase in self.laser:
                lase.draw(surface, frame, self.color, hitboxes=hitboxes, offset_x=offset_x, offset_y=offset_y)
        else:
            boosted_color = (channel_bound(self.color[0] + 30), channel_bound(self.color[1] + 30), channel_bound(self.color[2] + 30))
            player_surface = pygame.Surface((SPRITE_WIDTH * zoom, SPRITE_HEIGHT * zoom), flags=pygame.SRCALPHA)
            player_surface.fill((boosted_color[0], boosted_color[1], boosted_color[2], 255))
            player_surface.blit(self.player_im_gs[zoom][self.facing][self.animation_type][self.animation_frame], (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

            if tilt != 0:
                player_surface = pygame.transform.rotate(player_surface, tilt)

            adjusted_arm_angle = self.arm_angle
            if self.facing == "Left":
                adjusted_arm_angle += math.pi
            arm, arm_offset_x, arm_offset_y = rotate_and_get_offset(self.player_im_gs[zoom][self.facing]["Arm"][0], zoom * ARM_PIVOT_X, zoom * ARM_PIVOT_Y, adjusted_arm_angle)
            width, height = arm.get_size()
            arm_surface = pygame.Surface((width, height), flags=pygame.SRCALPHA)
            arm_surface.fill((boosted_color[0], boosted_color[1], boosted_color[2], 255))
            arm_surface.blit(arm, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

            surface.blit(player_surface, ((self.x - SPRITE_WIDTH / 2 - cam_x) * zoom + offset_x, (3 + self.rect.bottom - SPRITE_HEIGHT - cam_y) * zoom + offset_y))
            surface.blit(arm_surface, ((self.x - SPRITE_WIDTH / 2 - cam_x) * zoom + arm_offset_x + offset_x, (3 + self.rect.bottom - SPRITE_HEIGHT - cam_y) * zoom + arm_offset_y + offset_y))
            for lase in self.laser:
                lase.draw(surface, frame, boosted_color, offset_x=offset_x, offset_y=offset_y)
            # draw impact animations — rendered after laser so they appear on top
            for impact in self.impacts:
                impact.draw(surface, frame, boosted_color, zoom)

    def colliding_with_terrain(self, c_terrain):
        return c_terrain.collide_rect(self.rect)
