from dataclasses import dataclass, fields


@dataclass
class LaserAttributes:
    distance: int
    base_dmg: float
    base_kb: float
    base_xpl: float
    cooldown: float
    ramp_rate: float
    ramp_max: float
    area_dmg_falloff: float
    area_kb_falloff: float
    DMGRange: int
    KBRange: int
    first_hit_dmg_multiplier: float
    first_hit_kb_multiplier: float
    first_hit_xpl_multiplier: float
    passed_thresholds: dict


base = LaserAttributes(10, 0.8, 0.15, 20, 500, 1, 20, 0.3, 1, 20, 20, 0.5, 1.5, 0.5, {})
max_white = LaserAttributes(25, 1.2, 0.25, 40, 300, 1, 50, 0.3, 1, 30, 30, 0.5, 2, 0.5, {})
max_blue = LaserAttributes(30, 3, 0.8, 35, 400, 1, 20, 0.3, 1, 20, 50, 0.5, 3, 0.5, {})
max_red = LaserAttributes(5, 5, 0.15, 60, 500, 0.2, 20, 1, 1, 50, 20, 0.8, 1.5, 1, {})

ability_thresholds = {"white": 200 / 500, "blue": 200 / 500, "red": 200 / 500}

boost_thresholds = {"white": [180 / 500, 400 / 500], "blue": [120 / 500], "red": [120 / 500, 400 / 500]}


def set_laser_attributes(attributes: LaserAttributes, charges, filter, max_charge=500):

    for color in attributes.passed_thresholds:
        n_passed = 0
        charge = charges[color] / max_charge
        for threshold in boost_thresholds[color]:
            if threshold <= charge:
                n_passed += 1
        attributes.passed_thresholds[color] = (n_passed, attributes.passed_thresholds[color][1] or charge > ability_thresholds[color])

    w, b, r = charges["white"] / max_charge, charges["blue"] / max_charge, charges["red"] / max_charge

    for field in fields(attributes):
        field_name = field.name

        if field_name != "passedThresholds":
            base_att = getattr(base, field_name)
            white_attr = getattr(max_white, field_name)
            blue_attr = getattr(max_blue, field_name)
            red_attr = getattr(max_red, field_name)

            value = base_att + w * (white_attr - base_att) + b * (blue_attr - base_att) + r * (red_attr - base_att)
            if field_name == "distance":
                value = int(value)

            setattr(attributes, field_name, value)

    match filter:
        case "white":
            if attributes.passed_thresholds[filter][0] >= 2:
                attributes.ramp_rate += 1
        case "blue":
            if attributes.passed_thresholds[filter][0] >= 1:
                attributes.first_hit_kb_multiplier *= 1.5
        case "red":
            if attributes.passed_thresholds[filter][0] >= 1:
                attributes.DMGRange += 30

    return attributes


def get_laser_dmg(attributes: LaserAttributes, first_hit: bool, ramps: int):
    if first_hit:
        return attributes.base_dmg * attributes.first_hit_dmg_multiplier
    else:
        out = attributes.base_dmg * (1 + attributes.ramp_rate * min(attributes.ramp_max, ramps))
        return out


def get_laser_kb(attributes: LaserAttributes, first_hit: bool, ramps: int):
    if first_hit:
        return attributes.base_kb * attributes.first_hit_kb_multiplier
    else:
        out = attributes.base_kb
        return out


def get_laser_expl(attributes: LaserAttributes, first_hit: bool, ramps: int):
    if first_hit:
        return attributes.base_xpl * attributes.first_hit_xpl_multiplier
    else:
        out = attributes.base_xpl
        return out
