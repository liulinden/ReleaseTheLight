import math

import pygame

from scripts.global_assets import get_asset
from scripts.util import charges_to_color, polar_to_rect

charge_icon = None
light_gradient = None
charge_tuples = None


def init():
    global charge_icon, light_gradient, chargeColors

    charge_icon = pygame.transform.scale(get_asset("ChargeIcon"), (80, 80))
    light_gradient = get_asset("LightGradient")


charge_tuples = {"white": (1, 0, 0), "blue": (0, 1, 0), "red": (0, 0, 1)}


def draw_rounded_line(surface, color, start, end, thickness):
    pygame.draw.line(surface, color, start, end, thickness)
    pygame.draw.circle(surface, color, start, thickness // 2)
    pygame.draw.circle(surface, color, end, thickness // 2)


def draw_single_side_rounded_line(surface, color, start, end, thickness):
    # thickness should be odd
    pygame.draw.line(surface, color, start, end, thickness)
    pygame.draw.circle(surface, color, end, thickness / 2)


def draw_line_from_center(surface, color, center, angle, r1, r2, thickness):
    pygame.draw.line(surface, color, polar_to_rect(r1, -angle, center), polar_to_rect(r2, -angle, center), thickness)


def get_triangle_points(center, angle):
    return (polar_to_rect(54, angle - math.pi * 0.5, center), polar_to_rect(67, angle - math.pi * 0.55, center), polar_to_rect(67, angle - math.pi * 0.45, center))


def get_outer_triangle_points(center, angle):
    return (polar_to_rect(77, angle - math.pi * 0.5, center), polar_to_rect(67, angle - math.pi * 0.52, center), polar_to_rect(67, angle - math.pi * 0.48, center))


order_charges = {"white": (["white", "blue", "red"], []), "blue": (["blue", "white"], ["red"]), "red": (["red", "white"], ["blue"])}


class HealthBar:
    targeted = None

    def __init__(self, max_health, thickness=9):
        self.last_triggered = 0
        self.max_health = max_health
        self.thickness = thickness // 2 * 2 + 1  # thickness must be odd
        self.scale = 15 / max_health**0.8
        self.width = self.max_health * self.scale + self.thickness
        self.surface = pygame.Surface((self.width, self.thickness), pygame.SRCALPHA)

    def trigger(self, direct=False):
        self.last_triggered = pygame.time.get_ticks()
        if direct:
            HealthBar.targeted = self

    def draw(self, surface, color, coords, health, time=None):
        if time is None:
            time = pygame.time.get_ticks()
        opacity = max(0, 255 - (time - self.last_triggered - 500) / 2)
        if opacity > 0:
            self.surface.fill((0, 0, 0, 0))
            x, y = coords
            if HealthBar.targeted is self:
                draw_rounded_line(self.surface, color, (self.thickness // 2, self.thickness // 2), (self.width - self.thickness // 2, self.thickness // 2), self.thickness)
                draw_rounded_line(self.surface, (0, 0, 0), (self.thickness // 2, self.thickness // 2), (self.width - self.thickness // 2, self.thickness // 2), self.thickness - 4)
            else:
                draw_rounded_line(self.surface, (0, 0, 0), (self.thickness // 2, self.thickness // 2), (self.width - self.thickness // 2, self.thickness // 2), self.thickness)
            draw_rounded_line(self.surface, color, (self.thickness // 2, self.thickness // 2), (self.thickness // 2 + self.scale * health, self.thickness // 2), self.thickness - 4)

            left = x - self.scale * self.max_health / 2 - self.thickness / 2
            top = y - self.thickness / 2
            self.surface.set_alpha(opacity)

            surface.blit(self.surface, (left, top))


class ChargeDisplay:
    def __init__(self, world_height):
        self.rotation = 0
        self.rotation_goal = 1
        self.scale = 100

        # x/y are left/top
        self.x = 40
        self.y = 40
        self.rotation_speed = 0
        self.player_charges = {"white": 0, "blue": 0, "red": 0}
        self.player_total_charge = 0
        self.color = (0, 0, 0)
        self.world_height = world_height
        self.player_y = 0
        self.charge_capacity = 0
        self.filters = {"white": 0}

    def update(self, fps, player):
        frame_length = 1000 / fps

        self.charge_capacity = player.charge_capacity
        self.filter_type = player.filter_type
        player_charges = player.charges.copy()
        if self.filter_type != "white":
            player_charges["white"] /= 2
            self.charge_capacity -= player_charges["white"]
            if self.filter_type not in self.filters:
                self.filters[self.filter_type] = 0

        total_charge = sum(player_charges.values())
        total_charge_change = total_charge - self.player_total_charge
        self.player_total_charge = total_charge

        self.player_y = max(0, player.y)

        for color in player_charges:
            charge_change = int(player_charges[color]) - self.player_charges[color]
            if abs(charge_change) > 0:
                if abs(charge_change) < frame_length / 16:
                    self.player_charges[color] += charge_change
                else:
                    self.player_charges[color] += charge_change / abs(charge_change) * frame_length / 16

        cw, cb, cr = player.practical_charges.values()
        self.color = charges_to_color(cw, cb, cr)

        if total_charge_change > 0.1:
            self.rotation_goal += total_charge_change / 10
            self.scale = 90
        elif total_charge_change < -0.1:
            # self.rotation=0
            # self.rotationGoal=0
            if self.scale < 81:
                self.scale = 60
        real_goal = math.floor(self.rotation_goal)
        goal_speed = (real_goal - self.rotation) / 300
        if goal_speed > self.rotation_speed:
            self.rotation_speed += 1 / 1000
        if goal_speed < self.rotation_speed:
            self.rotation_speed = goal_speed
        self.rotation += self.rotation_speed * frame_length
        self.scale += (80 - self.scale) / 300 * frame_length
        if abs(self.rotation - real_goal) < 0.001:
            self.rotation = 0
            self.rotation_goal -= real_goal

        order = ()
        match self.filter_type:
            case "white":
                order = ("white", "blue", "red")
            case "blue":
                order = ("blue", "red", "white")
            case "red":
                order = ("red", "white", "blue")

        for color in self.filters:
            diff = order.index(color) * math.pi / 10 - self.filters[color]
            if diff > 0 and player.filter_change_right:
                diff -= 2 * math.pi
            elif diff < 0 and not player.filter_change_right:
                diff += 2 * math.pi
            self.filters[color] = (self.filters[color] + diff / 150 * frame_length) % (2 * math.pi)

    def draw(self, surface):
        transformed_icon = pygame.transform.rotate(pygame.transform.scale(charge_icon, (self.scale, self.scale)), -self.rotation * (360))
        filter = pygame.Surface(transformed_icon.get_size(), flags=pygame.SRCALPHA)

        # different filter than above
        filter_colors = {
            "white": charges_to_color(self.player_charges["white"], self.player_charges["blue"], self.player_charges["red"], maximize=True),
            "blue": charges_to_color(0, self.player_charges["blue"] + 1, 0, maximize=True),
            "red": charges_to_color(0, 0, self.player_charges["red"] + 1, maximize=True),
        }

        filter_color = filter_colors[self.filter_type]

        pygame.draw.line(surface, filter_color, (self.x + 0, self.y + 20), (self.x + 14, self.y + 20), 2)
        pygame.draw.line(surface, filter_color, (self.x + 0, self.y + 140), (self.x + 14, self.y + 140), 2)
        pygame.draw.line(surface, filter_color, (self.x + 7, self.y + 20), (self.x + 7, self.y + 140), 2)

        pygame.draw.line(surface, filter_color, (self.x + 0, self.y + 20 + 120 * self.player_y / self.world_height), (self.x + 14, self.y + 20 + 120 * self.player_y / self.world_height), 6)

        filter.fill(self.color)
        filter.blit(transformed_icon, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(filter, (self.x + 100 - filter.get_width() / 2, self.y + 80 - filter.get_height() / 2))

        # draw max capacity arc
        thickness = 2
        capacity_angle = math.pi * (1 / 2 - 2 * self.charge_capacity / 500)
        pygame.draw.arc(surface, filter_color, pygame.Rect(self.x + 40 + 4, self.y + 20 + 4, 120 - 8, 120 - 8), capacity_angle, math.pi / 2, thickness)

        # draw charges
        arc_angle = math.pi / 2
        for color in order_charges[self.filter_type][0]:
            if self.player_charges[color] > 0:
                new_angle = arc_angle - 2 * math.pi * (self.player_charges[color]) / 500

                def get_channel(index, color):
                    return charge_tuples[color][index] * self.player_charges[color]

                pygame.draw.arc(surface, charges_to_color(get_channel(0, color), get_channel(1, color), get_channel(2, color), maximize=True), pygame.Rect(self.x + 40, self.y + 20, 120, 120), new_angle, arc_angle, 10)
                arc_angle = new_angle
        out_line_angle = arc_angle
        for color in order_charges[self.filter_type][1]:
            if self.player_charges[color] > 0:
                new_angle = arc_angle - 2 * math.pi * (self.player_charges[color]) / 500

                def get_channel(index, color):
                    return charge_tuples[color][index] * self.player_charges[color]

                pygame.draw.arc(surface, charges_to_color(get_channel(0, color), get_channel(1, color), get_channel(2, color), maximize=True), pygame.Rect(self.x + 40, self.y + 20, 120, 120), new_angle, arc_angle, 10)
                arc_angle = new_angle

        # draw arc outline
        thickness = 3
        center = (self.x + 100, self.y + 80)
        pygame.draw.arc(surface, filter_color, pygame.Rect(self.x + 40 - thickness, self.y + 20 - thickness, 120 + 2 * thickness, 120 + 2 * thickness), out_line_angle, math.pi / 2, thickness)
        pygame.draw.arc(surface, filter_color, pygame.Rect(self.x + 40 + 10, self.y + 20 + 10, 120 - 20, 120 - 20), out_line_angle, math.pi / 2, thickness)
        draw_line_from_center(surface, filter_color, center, math.pi / 2, 60 - 10 - thickness, 60 + thickness, thickness)
        draw_line_from_center(surface, filter_color, center, out_line_angle, 60 - 10 - thickness, 60 + thickness, thickness)

        # draw max capacity end line
        draw_line_from_center(surface, filter_color, (self.x + 100, self.y + 80), min(capacity_angle, arc_angle), 60 - 10 - thickness, 60 + thickness, thickness)

        pygame.draw.circle(surface, (0, 0, 0), center, 67, 5)

        pygame.draw.polygon(surface, filter_color, get_triangle_points(center, self.filters[self.filter_type]))
        pygame.draw.polygon(surface, (0, 0, 0), get_triangle_points(center, self.filters[self.filter_type]), 3)

        for color in self.filters:
            pygame.draw.polygon(surface, filter_colors[color], get_outer_triangle_points(center, self.filters[color]))

        pygame.draw.circle(surface, filter_color, center, 67, 3)
        draw_line_from_center(surface, filter_color, center, math.pi * (1 / 2 - 2 * (150 / 500)), 60, 65, 3)
        draw_line_from_center(surface, filter_color, center, math.pi * (1 / 2 - 2 * (200 / 500)), 60, 65, 3)
        draw_line_from_center(surface, filter_color, center, math.pi * (1 / 2 - 2 * (400 / 500)), 60, 65, 3)

        pygame.draw.circle(surface, filter_color, polar_to_rect(72, -math.pi * (1 / 2 - 2 * (200 / 500)), center), 6, 3)
