import math

import pygame

import scripts.elements.elements as elements

# Prototype rendering: no texture at all, just a poly-line traced through a
# simulated rope -- see Vine.tick/draw_front. Cheap to build, cheap to
# iterate on visually before committing to real art.
LINE_COLOR = (0, 0, 0)
LINE_WIDTH = 2  # world units, scaled by zoom like everything else

# SIZE_MIN/SIZE_MAX/DEFAULT_SIZE is the horizontal SPAN between the vine's
# two connection points (left and right, both at the same height -- see
# Element's anchor-vs-footprint split in elements.py). The rope itself is
# longer than the span by a slack_factor so it has room to sag between them
# instead of being pulled taut -- slack_factor varies per vine (see
# SLACK_FACTOR_MIN/MAX) rather than being one fixed constant, so vines
# don't all sag by the exact same amount. It's a real constructor
# parameter (like size), not drawn internally at random: it changes the
# anchor's own height, so get_placement_geometry and __init__ have to
# agree on the same value for a given placement, the same reasoning that
# keeps Spike's variant argument -- which does NOT affect geometry --
# safe to randomize internally while this can't be.
SIZE_MIN = 20
SIZE_MAX = 100
DEFAULT_SIZE = 80
SLACK_FACTOR_MIN = 1.15
SLACK_FACTOR_MAX = 3
DEFAULT_SLACK_FACTOR = 1.3

N_SEGMENTS = 20  # rope is split into this many equal-length segments between the two fixed endpoints

# anchor: a thin strip at the very top, spanning the full width between
# the two connection points -- where the vine is hypothetically rooted
# into the ceiling. Height is a fraction of the footprint's own height
# (itself just a rough estimate of how deep the rope sags, for
# registration/anchor purposes -- not read by the physics at all).
ANCHOR_TOP_FRAC = 0
ANCHOR_HEIGHT_FRAC = 1 / 8

# Rope physics -- ordinary verlet integration (implicit velocity from
# position history, so damping/gravity/pushes all just nudge a position)
# plus a few iterations of distance-constraint relaxation per tick to keep
# segments close to their rest length. Both endpoints are pinned to the
# connection points and never move; only the interior points simulate.
GRAVITY = 0.0001  # world units / ms^2, pulls interior points down every tick -- combined with
# the parabolic starting shape below, this settles a fresh vine to its natural sag in ~2s;
# much weaker values are still stable but take tens of seconds to visibly settle from spawn
VELOCITY_DAMPING = 0.996  # per-ms decay applied to each point's implicit verlet velocity
CONSTRAINT_ITERATIONS = 3

# Two independent push sources, both expressed as a direct per-ms position
# nudge (verlet turns any one-frame nudge into ongoing "velocity" on its
# own, so there's no separate impulse/force bookkeeping needed):
#   - proximity to the player/any enemy (continuous while overlapping)
PUSH_RADIUS = 20  # world units
PUSH_STRENGTH = 0.01
#   - terrain.knockback_circles (the same one-shot impulse circles cells
#     and enemies react to -- see Cell.tick_knockback) -- pow*falloff is
#     already the circle's own effective strength, so this is just a unit
#     conversion, not a second strength dial
KNOCKBACK_PUSH_SCALE = 0.00006


def init():
    # no art to load -- current rendering is math-only line segments (see
    # module docstring). Kept as a real function (not deleted) so
    # World.__init__'s init list doesn't need special-casing, and so a
    # texture-based rendering pass can slot back in here later.
    pass


def prewarm_cache(default_zooms, loading_screen=None):
    # nothing to prewarm -- see init(). Reports done immediately so the
    # loading bar doesn't wait on a step that has no work left in it.
    if loading_screen is not None:
        loading_screen.put(1.0, "Vines need no image cache")


class Vine(elements.Element):
    """Purely decorative hazard-free element: a rope simulated between two
    fixed connection points at the top (both rooted in the ceiling above
    it, mirrors Spike's floor-rooted anchor -- see SPAWN_SIDE and
    attempt_place_element_adjacent_to_air_pocket), rendered every frame as
    a straight-line poly-line traced through the live simulated points
    rather than a static image. No collide/interaction hitbox at all (so
    it never blocks movement and never reacts to touch); destroyed only
    when an explosion overlaps its anchor, same as any other element.

    tick() nudges nearby interior points away from the player/enemies
    passing through and away from terrain.knockback_circles, then lets
    gravity/damping/the rope's own distance constraints pull it back into
    a natural sag -- see the physics constants above the class."""

    SPAWN_SIDE = "top"  # rooted in the ceiling, hangs down into the pocket below it

    def __init__(self, default_zooms, x, y, size=DEFAULT_SIZE, slack_factor=DEFAULT_SLACK_FACTOR):
        anchor_left, anchor_top, anchor_width, anchor_height = self._anchor_geometry(size, slack_factor)
        # footprint height is only a rough estimate of how deep the rope
        # can sag, for registration/anchoring purposes -- the physics below
        # doesn't consult it at all, the rope sags exactly however far
        # slack_factor and gravity actually take it.
        height = size * slack_factor / 2
        super().__init__(default_zooms, x, y, size, height, anchor_left, anchor_top, anchor_width, anchor_height)

        self.left_root = (self.x - size / 2, self.top)
        self.right_root = (self.x + size / 2, self.top)
        self.segment_length = (size * slack_factor) / N_SEGMENTS

        # N_SEGMENTS+1 points; index 0 and N_SEGMENTS are pinned to
        # left_root/right_root and never move. Laid out along a rough
        # parabolic droop at spawn (rather than a flat line) -- gravity vs.
        # damping settles to its true equilibrium slowly (tens of seconds
        # from a standing start, verified empirically), so starting already
        # close to the eventual sag means a newly-generated vine looks
        # right immediately instead of visibly unfurling for a long stretch.
        sag_estimate = (size * slack_factor - size) * 1.2
        self.points = []
        for i in range(N_SEGMENTS + 1):
            t = i / N_SEGMENTS
            px = self.left_root[0] + (self.right_root[0] - self.left_root[0]) * t
            py = self.left_root[1] + sag_estimate * 4 * t * (1 - t)
            self.points.append([px, py])
        self.prev_points = [list(p) for p in self.points]

    @staticmethod
    def _anchor_geometry(size, slack_factor):
        return (0, size * ANCHOR_TOP_FRAC, size, (size * slack_factor / 2) * ANCHOR_HEIGHT_FRAC)

    @classmethod
    def get_placement_geometry(cls, size=DEFAULT_SIZE, slack_factor=DEFAULT_SLACK_FACTOR):
        anchor_left, anchor_top, anchor_width, anchor_height = cls._anchor_geometry(size, slack_factor)
        return size, size * slack_factor / 2, anchor_left, anchor_top, anchor_width, anchor_height

    def _satisfy_constraint(self, i, j):
        p1, p2 = self.points[i], self.points[j]
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        d = math.hypot(dx, dy)
        if d == 0:
            return
        diff = (d - self.segment_length) / d
        # pinned endpoints (0 and N_SEGMENTS) never move -- correction is
        # applied only to whichever side is a free interior point
        move1 = 0.0 if i == 0 or i == N_SEGMENTS else 0.5
        move2 = 0.0 if j == 0 or j == N_SEGMENTS else 0.5
        p1[0] += dx * diff * move1
        p1[1] += dy * diff * move1
        p2[0] -= dx * diff * move2
        p2[1] -= dy * diff * move2

    def tick(self, frame_length, _terrain, player, enemies):
        pushers = [(player.x, player.y)] + [(enemy.x, enemy.y) for enemy in enemies]
        knockbacks = _terrain.knockback_circles

        for i in range(1, N_SEGMENTS):
            px, py = self.points[i]
            prev_x, prev_y = self.prev_points[i]

            vx = (px - prev_x) * VELOCITY_DAMPING
            vy = (py - prev_y) * VELOCITY_DAMPING

            push_x, push_y = 0.0, 0.0
            for ex, ey in pushers:
                dx, dy = px - ex, py - ey
                d = math.hypot(dx, dy)
                if 0 < d < PUSH_RADIUS:
                    strength = PUSH_STRENGTH * (1 - d / PUSH_RADIUS) * frame_length
                    push_x += dx / d * strength
                    push_y += dy / d * strength

            for pow_, kx, ky, r, falloff in knockbacks:
                dx, dy = px - kx, py - ky
                d = math.hypot(dx, dy)
                if 0 < d < r:
                    strength = KNOCKBACK_PUSH_SCALE * pow_ * falloff * frame_length
                    push_x += dx / d * strength
                    push_y += dy / d * strength

            self.prev_points[i] = [px, py]
            self.points[i] = [px + vx + push_x, py + vy + GRAVITY * frame_length * frame_length + push_y]

        for _ in range(CONSTRAINT_ITERATIONS):
            for i in range(N_SEGMENTS):
                self._satisfy_constraint(i, i + 1)

    def draw_front(self, surface, frame, offset_x=0, offset_y=0):
        cam_x, cam_y, zoom = frame
        screen_points = [(((wx - cam_x) * zoom + offset_x), ((wy - cam_y) * zoom + offset_y)) for wx, wy in self.points]
        pygame.draw.lines(surface, LINE_COLOR, False, screen_points, max(1, round(LINE_WIDTH * zoom)))
