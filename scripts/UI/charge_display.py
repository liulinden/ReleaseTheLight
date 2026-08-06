import math

import pygame

from scripts.global_assets import get_asset
from scripts.util import charges_to_color, multiply_tuple, polar_to_rect

charge_icon = None
light_gradient = None
charge_tuples = None
cell_imgs = None

animation_fps = 12
tl_x, tl_y = 20, 30
display_size = 220
cell_display_size = display_size * 0.22
charge_icon_size = display_size * 0.62


def init():
    global charge_icon, light_gradient, chargeColors, cell_imgs

    charge_icon = pygame.transform.scale(get_asset("UI_charge_icon"), (charge_icon_size, charge_icon_size))
    light_gradient = get_asset("gradient_light")
    cell_imgs = {
        "shell": pygame.transform.scale(get_asset("cell_basic_shell"), (cell_display_size, cell_display_size)),
        **{"crackle_" + str(i + 1): pygame.transform.scale(get_asset("cell_basic_crackle_" + str(i + 1)), (cell_display_size, cell_display_size)) for i in range(5)},
    }


charge_tuples = {"white": (1, 0, 0), "blue": (0, 1, 0), "red": (0, 0, 1)}


def draw_line_from_center(surface, color, center, angle, r1, r2, thickness):
    pygame.draw.line(surface, color, polar_to_rect(r1, -angle, center), polar_to_rect(r2, -angle, center), thickness)


def get_triangle_points(center, angle):
    return (polar_to_rect(display_size * 0.43, angle - math.pi * 0.5, center), polar_to_rect(display_size * 0.5, angle - math.pi * 0.53, center), polar_to_rect(display_size * 0.5, angle - math.pi * 0.47, center))


def get_outer_triangle_points(center, angle):
    return (polar_to_rect(display_size * 0.57, angle - math.pi * 0.5, center), polar_to_rect(display_size * 0.5, angle - math.pi * 0.52, center), polar_to_rect(display_size * 0.5, angle - math.pi * 0.48, center))


order_charges = {"white": (["white", "blue", "red"], []), "blue": (["blue", "white"], ["red"]), "red": (["red", "white"], ["blue"])}


class ChargeDisplay:
    def __init__(self):
        self.rotation = 0
        self.rotation_goal = 1
        self.scale = 100

        # x/y are left/top
        self.x = 40
        self.y = 40
        self.rotation_speed = 0
        self.player_charges = {"white": 0, "blue": 0, "red": 0}
        self.player_total_charge = 0
        self.active_charge = 0
        self.charge_color = (0, 0, 0)
        self.color = (0, 0, 0)
        self.player_y = 0
        self.charge_capacity = 0
        self.filters = {"white": 0}
        self.filter_type = "white"
        self.cell_imgs_cache = {}
        self.scratch_surfaces = {}
        self.animation_timer = 0
        self.frame = 1
        self.n_cells = 0

    def update(self, fps, player):
        frame_length = 1000 / fps

        self.animation_timer = (self.animation_timer + frame_length) % (1000 / animation_fps * 5)
        self.frame = math.floor(self.animation_timer / (1000 / animation_fps)) + 1

        self.charge_capacity = player.charge_capacity
        player_charges = player.charges.copy()
        if player.filter_type is not self.filter_type:
            self.filter_type = player.filter_type
            self.rotation_goal += 1
        #if self.filter_type != "white":
        #    player_charges["white"] /= 2
        #    self.charge_capacity -= player_charges["white"]
        if self.filter_type not in self.filters:
            self.filters[self.filter_type] = 0

        total_charge = sum(player_charges.values())
        total_charge_change = total_charge - self.player_total_charge
        self.player_total_charge = total_charge

        self.player_y = max(0, player.y)
        self.n_cells = player.n_cells

        for color in player_charges:
            charge_change = int(player_charges[color]) - self.player_charges[color]
            if abs(charge_change) > 0:
                if abs(charge_change) < frame_length / 5:
                    self.player_charges[color] += charge_change
                else:
                    self.player_charges[color] += charge_change / abs(charge_change) * frame_length / 5

        practical_charges = player.practical_charges.values()
        self.active_charge = sum(practical_charges)
        self.charge_color = charges_to_color(*practical_charges)

        if total_charge_change > 0.1:
            self.rotation_goal += total_charge_change / 10
            self.scale = 100
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
            diff = order.index(color) * math.pi / 20 - self.filters[color]
            if diff > 0 and player.filter_change_right:
                diff -= 2 * math.pi
            elif diff < 0 and not player.filter_change_right:
                diff += 2 * math.pi
            self.filters[color] = (self.filters[color] + diff / 150 * frame_length) % (2 * math.pi)

    def draw(self, surface):

        transformed_icon = pygame.transform.rotate(pygame.transform.scale(charge_icon, (charge_icon_size * self.scale / 100, charge_icon_size * self.scale / 100)), -self.rotation * (360))
        charge_surface = pygame.Surface(transformed_icon.get_size(), flags=pygame.SRCALPHA)
        cx = tl_x + display_size / 2
        cy = tl_y + display_size / 2

        # different filter than above
        filter_colors = {
            "white": charges_to_color(self.player_charges["white"], self.player_charges["blue"], self.player_charges["red"], maximize=True),
            "blue": charges_to_color(0, self.player_charges["blue"] + 1, 0, maximize=True),
            "red": charges_to_color(0, 0, self.player_charges["red"] + 1, maximize=True),
        }

        self.color = filter_colors[self.filter_type]

        charge_surface.fill(self.charge_color)
        charge_surface.blit(transformed_icon, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(charge_surface, (cx - charge_surface.get_width() / 2, cy - charge_surface.get_height() / 2))

        radius = display_size * 0.38
        first_dim = int(self.active_charge / 25)

        charge_order = order_charges[self.filter_type][0] + order_charges[self.filter_type][1]
        charges = self.player_charges.copy()
        for i in range(self.n_cells):
            angle = i * 360 / 20
            shell, size = self.get_cell_img("shell", -angle)
            cell_surface = self.get_scratch_surface(size, True)
            x, y = polar_to_rect(radius, (angle - 90) * math.pi / 180, (cx - size[0] / 2, cy - size[0] / 2))

            if i < first_dim:
                darken_factor = 1
            elif i == first_dim:
                darken_factor = 0.2 + 0.8 * (self.active_charge - 25 * first_dim) / 25
            else:
                darken_factor = 0.2
            if sum(charges.values()) > 0:
                used = {"white": 0, "blue": 0, "red": 0}
                remaining = 25
                for charge in charge_order:
                    used[charge] = min(charges[charge], remaining)
                    remaining -= used[charge]
                    charges[charge] -= used[charge]
                    if remaining == 0 or sum(charges.values()) == 0:
                        break

                crackle_color = charges_to_color(used["white"], used["blue"], used["red"], 25)
                crackle, size = self.get_cell_img("crackle_" + str(self.frame), -angle)

                cell_surface.fill(crackle_color)
                cell_surface.blit(crackle, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                surface.blit(cell_surface, (x, y))

            cell_surface.fill(multiply_tuple(self.color, darken_factor))
            cell_surface.blit(shell, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(cell_surface, (x, y))


        pygame.draw.circle(surface, (0, 0, 0), (cx, cy), display_size * 0.5, 5)

        pygame.draw.polygon(surface, self.color, get_triangle_points((cx, cy), self.filters[self.filter_type]))
        pygame.draw.polygon(surface, (0, 0, 0), get_triangle_points((cx, cy), self.filters[self.filter_type]), 3)

        for color in self.filters:
            pygame.draw.polygon(surface, filter_colors[color], get_outer_triangle_points((cx, cy), self.filters[color]))

        pygame.draw.circle(surface, self.color, (cx, cy), display_size * 0.5, 3)
        # draw_line_from_center(surface, filter_color, (cx, cy), math.pi * (1 / 2 - 2 * (150 / 500)), 60, 65, 3)
        # draw_line_from_center(surface, filter_color, (cx, cy), math.pi * (1 / 2 - 2 * (200 / 500)), 60, 65, 3)
        # draw_line_from_center(surface, filter_color, (cx, cy), math.pi * (1 / 2 - 2 * (400 / 500)), 60, 65, 3)

        pygame.draw.circle(surface, self.color, polar_to_rect(display_size * 0.5 + 5, -math.pi * (1 / 2 - 2 * (200 / 500)), (cx, cy)), 6, 3)

        # pygame.draw.rect(surface, self.color, pygame.Rect(tl_x, tl_y, display_size, display_size), 2)

        
        """

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
        """

    def get_cell_img(self, img, angle):
        if (img, angle) not in self.cell_imgs_cache:
            rotated_img = pygame.transform.rotate(cell_imgs[img], angle)
            self.cell_imgs_cache[(img, angle)] = (rotated_img, rotated_img.get_size())
        return self.cell_imgs_cache[(img, angle)]

    def get_scratch_surface(self, size, alpha=False):
        if (size, alpha) not in self.scratch_surfaces:
            if alpha:
                self.scratch_surfaces[(size, alpha)] = pygame.Surface(size, pygame.SRCALPHA)
            else:
                self.scratch_surfaces[(size, alpha)] = pygame.Surface(size)
        return self.scratch_surfaces[(size, alpha)]
