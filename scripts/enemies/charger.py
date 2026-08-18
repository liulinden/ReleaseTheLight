import math

from scripts.enemies._enemy import Enemy, GLOW_DECAY_MS, TILT_DECAY_RATE, animation_fps


class Charger(Enemy):
    """Red-nest enemy. Wanders/chases and melees normally like a base Enemy,
    but once the player is within a certain horizontal band it winds up
    (backing away slightly), then dashes at high speed for a fixed
    duration, plowing straight through terrain along the way, before a
    brief recovery.

    State is driven entirely through the shared Enemy.mode field:
        walk -> attack (standard melee, inherited from Enemy) -> walk
        walk -> load -> charge_attack (the dash) -> cooldown -> walk

    "load", "charge_attack", and "cooldown" are new modes on top of the base
    spawn/walk/attack set -- "attack" is left alone as the ordinary melee
    swing, "charge_attack" is the charge. Costume "1" has no dedicated art
    for load/cooldown/charge_attack yet, so they currently render the
    walk/attack animation as a placeholder (see _DISPLAY_MODE below).
    TODO: give "load" (wind-up), "charge_attack" (dash), and "cooldown"
    (stagger/recover) their own animations once art exists, and drop the
    _DISPLAY_MODE fallback.
    """

    size_range = (40, 70)
    costume = "1"
    health_factor = 0.3

    # mode -> which costume animation to display until dedicated art exists
    _DISPLAY_MODE = {"load": "walk", "cooldown": "walk", "charge_attack": "attack"}

    CHARGE_MIN_RANGE = 100  # won't trigger if the player is already this close (melee range instead)
    CHARGE_MAX_RANGE = 400  # won't trigger if the player is further than this
    CHARGE_VERTICAL_TOLERANCE = 100  # only charges when roughly level with the player
    CHARGE_SPEED = 0.4  # world units / ms while charging
    CHARGE_DURATION = 1200  # ms, max charge length if it doesn't reach the player first
    CHARGE_DISTANCE = 200  # world units, max charge length by distance -- charge stops on whichever limit (time or distance) is hit first
    CARVE_RADIUS_RATIO = 0.6  # air pocket radius, relative to enemy size -- must clear the enemy's full rect, not just its center point
    CARVE_INTERVAL = 250  # ms; carving through a wall it's rammed into can happen at most this often
    CHARGE_JUMP_TRIGGER_HEIGHT = 20  # jump mid-charge once the player is at least this far above
    CHARGE_JUMP_SPEED = -0.5

    LOAD_DURATION = 800  # ms spent backing up before a charge
    LOAD_BACK_SPEED = 0.05  # world units / ms while backing up

    COOLDOWN_DURATION = 900  # ms spent recovering after a charge, no active movement

    def __init__(self, default_zooms, nest, color, size, nest_health, x, y):
        super().__init__(default_zooms, nest, Charger.costume, color, x, y, size, nest_health * Charger.health_factor)
        self.knockback = 0.25
        self.speed = 1.2

        self.carve_radius = max(10, size * Charger.CARVE_RADIUS_RATIO)

        self.charge_timer = 0
        self.charge_direction = 0  # -1 or 1, set when a charge starts
        self.charge_distance_traveled = 0  # world units covered so far this charge_attack, reset when one begins
        self._carve_cooldown = 0

    def tick_enemy_behavior(self, frame_length, player):
        if self.mode == "load":
            self.charge_timer -= frame_length
            self.x_speed = -self.charge_direction * Charger.LOAD_BACK_SPEED
            if self.charge_timer <= 0:
                self.mode = "charge_attack"
                self.animation_timer = 0
                self.charge_timer = Charger.CHARGE_DURATION
                self.charge_distance_traveled = 0
                self._carve_cooldown = 0  # allow carving right away if it starts already against a wall
            return

        if self.mode == "charge_attack":
            self.charge_timer -= frame_length
            self.x_speed = self.charge_direction * Charger.CHARGE_SPEED
            if self.on_ground and self.y - player.y >= Charger.CHARGE_JUMP_TRIGGER_HEIGHT:
                self.y_speed = Charger.CHARGE_JUMP_SPEED

            overshot = (self.charge_direction > 0 and self.x >= player.x) or (self.charge_direction < 0 and self.x <= player.x)
            if overshot or self.charge_timer <= 0 or self.charge_distance_traveled >= Charger.CHARGE_DISTANCE:
                self.mode = "cooldown"
                self.animation_timer = 0
                self.charge_timer = Charger.COOLDOWN_DURATION
            return

        if self.mode == "cooldown":
            self.charge_timer -= frame_length
            if self.charge_timer <= 0:
                self.mode = "walk"
                self.animation_timer = 0
            # no active steering here -- x_speed/y_speed are left alone, so it
            # only moves via residual momentum, gravity, collision, or knockback
            return

        if self.mode != "walk":
            return

        # normal chase/wander behavior while walking -- this can flip mode to
        # "attack" (standard melee, inherited) via ordinary proximity; that's
        # left alone, distinct from the charge below
        super().tick_enemy_behavior(frame_length, player)

        if self.mode == "walk" and self.on_ground:
            dx = player.x - self.x
            horizontal_dist = abs(dx)
            if Charger.CHARGE_MIN_RANGE <= horizontal_dist <= Charger.CHARGE_MAX_RANGE and abs(player.y - self.y) < Charger.CHARGE_VERTICAL_TOLERANCE:
                self.mode = "load"
                self.animation_timer = 0
                self.charge_timer = Charger.LOAD_DURATION
                self.charge_direction = 1 if dx > 0 else -1
                self.facing = "right" if dx > 0 else "left"

    def attempt_movement(self, frame_length, _terrain):
        if self.mode != "charge_attack":
            super().attempt_movement(frame_length, _terrain)
            return

        self._carve_cooldown -= frame_length

        expected_dx = self.charge_direction * Charger.CHARGE_SPEED * frame_length
        x_before = self.x
        super().attempt_movement(frame_length, _terrain)
        actual_dx = self.x - x_before
        self.charge_distance_traveled += abs(actual_dx)

        # Terrain actually slowed it down this tick (it didn't get most of the
        # way it should have) -- only then, and no more than once every
        # CARVE_INTERVAL, break through so next tick can proceed.
        blocked = abs(actual_dx) < abs(expected_dx) * 0.5
        if blocked and self._carve_cooldown <= 0:
            _terrain.add_air_pocket_clump(self.x, self.y, self.carve_radius, player_made=True, spreading=1 / 10, spawn_particles=True)
            self._carve_cooldown = Charger.CARVE_INTERVAL

    def handle_attack(self, player):
        if self.mode == "charge_attack":
            if player.immunity_timer == 0 and self.rect.colliderect(player.rect):
                player.immunity_timer = player.immunity_time
                player.x_speed = self.charge_direction * self.knockback
                player.y_speed = -self.knockback
                player.take_enemy_hit(self.damage)
            return
        super().handle_attack(player)  # handles standard "attack" (melee) itself

    def update_costume(self, frame_length, player):
        # Overridden (rather than relying on Enemy.update_costume) because
        # "load"/"charge_attack"/"cooldown" have no animation entry to look
        # up directly, and their mode changes must be driven exclusively by
        # Charger's own timers in tick_enemy_behavior, not by animation
        # length. Standard "attack" (melee) keeps the base class's lifecycle
        # (ends when its animation finishes).
        self.glow = max(0, self.glow - 255 / GLOW_DECAY_MS * frame_length)
        if self.tilt > 0:
            self.tilt = max(0, self.tilt - TILT_DECAY_RATE * frame_length)
        elif self.tilt < 0:
            self.tilt = min(0, self.tilt + TILT_DECAY_RATE * frame_length)
        self.animation_timer += frame_length

        display_mode = Charger._DISPLAY_MODE.get(self.mode, self.mode)
        anim_length = self.animation_lengths[display_mode]

        if self.mode == "spawn":
            if self.animation_timer >= anim_length * 1000 / animation_fps:
                self.mode = "walk"
                self.animation_timer = 0
        elif self.mode == "attack":
            if self.animation_timer >= anim_length * 1000 / animation_fps:
                self.mode = "walk"
                self.animation_timer = 0
        else:  # walk, load, charge_attack, cooldown -- looping placeholder/idle clip
            self.animation_timer = self.animation_timer % (anim_length * 1000 / animation_fps)

        if self.mode in ("walk", "load", "cooldown"):
            if self.x < player.x:
                self.facing = "right"
            elif self.x > player.x:
                self.facing = "left"
        # facing stays locked while mid-melee ("attack") or mid-charge ("charge_attack")

        self.animation_frame = math.floor(self.animation_timer / (1000 / animation_fps))

    def draw(self, surface, frame, hitbox=False, offset_x=0, offset_y=0):
        # TODO: remove this mode-swap once "load"/"charge_attack"/"cooldown"
        # have real art -- borrows the walk/attack animation as a
        # placeholder for the image lookup.
        real_mode = self.mode
        self.mode = Charger._DISPLAY_MODE.get(self.mode, self.mode)
        try:
            super().draw(surface, frame, hitbox=hitbox, offset_x=offset_x, offset_y=offset_y)
        finally:
            self.mode = real_mode
