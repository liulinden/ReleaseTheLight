"""GPU present layer: takes the CPU-composited world frame plus a separate
CPU-composited UI frame, and does everything from here on (bloom, the
foreground "grime" overlay + its thick-gradient clear zone around the
player/laser, and UI compositing) on the GPU in a single present() call.

Requires the display to have been created with pygame.OPENGL | pygame.DOUBLEBUF
(see main.py) -- once that flag is set, the window Surface pygame.display.set_mode
returns can no longer be blitted onto directly, which is why everything now
draws onto off-screen Surfaces (see Game.render_surface / Game.ui_surface in
releaseTheLight.py) that only gl_present.present() ever touches.

Per-frame upload uses Surface.get_view('1') (a zero-copy buffer-protocol view
of the Surface's raw pixel memory) instead of pygame.image.tostring, which
would otherwise dominate the cost of this whole step -- tostring does a real
format-conversion copy (~3.5ms/frame measured at 1920x1080) that get_view
skips entirely. This only works because render_surface/ui_surface are plain
32-bit-per-pixel Surfaces (see Game.set_window) -- get_view's raw bytes are
meaningless without that.

Pygame's native 32-bit pixel layout is BGRA in memory (not RGBA) -- see the
.bgra swizzle in every shader that samples a per-frame raw upload (scene,
ui). The two *static* textures (foreground, thick gradient) are uploaded
once via load_static_textures(), using pygame.image.tostring(..., "RGBA")
instead of get_view -- a one-time cost, so its safety (no surface-pitch
assumptions) is worth more than get_view's speed there -- so they're sampled
with a plain (non-swizzled) .rgba instead.

Bloom
-----
Used to be bloom.py's CPU implementation (numpy array ops on a downscaled
copy). Now a GPU render-to-texture pipeline: downscale + luminance-threshold
the scene (mipmap-based downscale, since a naive single bilinear tap at this
downscale factor would lose small bright features), then repeated
*separable Gaussian* blur passes (horizontal then vertical, each a real
multi-tap kernel) before compositing back additively. This replaced an
earlier version that used bloom.py's own shrink/grow-by-bilinear-resample
trick -- functionally similar, but that trick's repeated hard resampling
steps read as "pixely" at the tuned downscale/pass values; a proper
multi-tap blur doesn't have that artifact regardless of how many passes are
stacked. BLOOM_UPDATE_INTERVAL reproduces the old World.BLOOM_UPDATE_INTERVAL
caching (recompute only every Nth call, reuse the existing texture
otherwise -- bloom is a soft, slowly changing glow, recomputing it every
frame was already known to be wasted work before this all moved to the GPU).

Foreground + thick gradient
----------------------------
Used to be World.draw_foreground/Lighting.draw_thick_gradient, both plain
CPU blits onto a scratch surface that started white, multiplied onto the
finished frame as the very last CPU step. Moved here because -- like bloom
-- it's a clean final pass over the already-finished scene, not entangled
with the mid-pipeline ambient-lighting/background compositing the way
background_1/2 are (those stay on the CPU). The composite shader below
replicates the exact same "white, then foreground-over, then thick-gradient
(player)-over, then thick-gradient (laser)-over, then multiply onto scene"
algebra as a small number of texture samples instead of two full-window CPU
blits + one CPU multiply-blit per frame. foreground/gradient_thick are
uploaded once as static textures (load_static_textures(), called once after
assets finish loading) rather than every frame, and rather than the old
10000x10000 pre-scaled CPU copy (self.foreground in world.py) -- the raw,
much smaller asset is sampled directly with UV math replicating that same
10000x10000 effective world-space footprint.

UI compositing
--------------
charge_display and the other UI (flash overlay, debug rect, fps text) now
draw onto their own transparent Surface (Game.ui_surface) instead of being
baked into render_surface before the foreground multiply -- otherwise the
foreground/thick-gradient darkening would incorrectly apply to the UI too.
ui_surface is uploaded as its own per-frame texture and alpha-blended on top
of the scene+bloom+foreground composite as a separate final draw, with GL
blending enabled just for that one draw call.
"""

import math

import moderngl
import numpy as np
import pygame

_ctx = None
_vao = None

_prog_upload = None     # samples a per-frame raw (BGRA) upload, plain passthrough -- used for both the scene-only debug path and the final UI blend
_prog_threshold = None  # samples the uploaded (BGRA) scene texture, luminance-thresholds it
_prog_blur = None       # separable Gaussian blur, one direction (horizontal or vertical) per draw
_prog_composite = None  # scene + bloom + foreground/thick-gradient multiply

_scene_tex = None
_scene_tex_size = None

_ui_tex = None
_ui_tex_size = None

_foreground_tex = None
_thick_tex = None
_fog_tex = None
_vignette_tex = None

# bloom render targets, keyed by size
_bloom_fbos = {}

_bloom_frame_counter = 0

# -- bloom tuning --
BLOOM_THRESHOLD = 80 / 255  # normalized (bloom.py's was 0-255)
BLOOM_DOWNSCALE = 10
BLOOM_BLUR_PASSES = 5
BLOOM_INTENSITY = 0.8
BLOOM_UPDATE_INTERVAL = 2  # recompute every Nth present() call; reuse the existing bloom texture otherwise

# world-space footprints replicated from world.py/lighting.py (see their own
# comments/docstrings for where these numbers come from -- kept in sync by
# hand since they're now split across CPU and shader code)
FG_WORLD_SIZE = 10000  # was pygame.transform.scale(foreground_raw, (10000, 10000)) in world.py
TG_WORLD_SIZE = 300  # was `size = 300` in Lighting.__init__

# -- foreground fog tuning --
# foreground_fog.png is 4096x2048, authored as two identical 2048-wide
# copies side by side specifically so it can be panned with a hard modulo
# wrap at the half-width (2048) instead of the full width -- the wrapped
# frame is pixel-identical to the un-wrapped one, so the reset is
# guaranteed invisible (unlike a "normal" seamless tile, which only looks
# right at the wrap point if its two edges happen to match). It was
# cropped from a 4096x4096 source (empty top half trimmed off), so it's
# not square -- see sample_fog's vertical math in the composite shader.
FOG_TEX_HALF = 2048.0
FOG_SCROLL_SPEED = 40.0  # texels/sec it pans right at
FOG_ALPHA = 0.5  # 0..1, overall strength of the fog tint
FOG_PARALLAX = 1.8  # vs. foreground_tex's fixed 6 (see fg_x) -- fog reads as farther from
# the camera than foreground, so it should drift by less for the same camera movement

# second fog layer -- same texture, panned the opposite way (negative speed
# and parallax) for a cheap two-layer drifting-clouds look; independently
# tunable in case the second layer should read as a different depth/pace
FOG2_SCROLL_SPEED = -60
FOG2_ALPHA = FOG_ALPHA
FOG2_PARALLAX = 1.2

# how strongly Terrain's screen-edge vignette darkens the fog layers -- 0
# leaves fog untouched by it, 1 is the same full-strength darkening the
# terrain layer gets (see FOG_VIGNETTE_STRENGTH's use in the composite shader)
FOG_VIGNETTE_STRENGTH = 0.4

_VERTEX_SHADER = """
#version 330
in vec2 in_pos;
in vec2 in_uv;
out vec2 uv;
void main() {
    uv = in_uv;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

_FRAGMENT_UPLOAD = """
#version 330
uniform sampler2D scene;
in vec2 uv;
out vec4 f_color;
void main() {
    f_color = texture(scene, uv).bgra;
}
"""

_FRAGMENT_THRESHOLD = """
#version 330
uniform sampler2D scene;
uniform float threshold;
in vec2 uv;
out vec4 f_color;
void main() {
    vec4 c = texture(scene, uv).bgra;
    float lum = c.r * 0.299 + c.g * 0.587 + c.b * 0.114;
    float mask = step(threshold, lum);
    f_color = vec4(c.rgb * mask, c.a * mask);
}
"""

_FRAGMENT_BLUR = """
#version 330
uniform sampler2D tex;
uniform vec2 direction;   // (1,0) or (0,1), in texel units
uniform vec2 texel_size;
uniform float mult;
in vec2 uv;
out vec4 f_color;

// 5-tap symmetric Gaussian half-kernel (9 taps total) -- a standard,
// cheap separable blur kernel. Unlike the old shrink/grow-by-bilinear-
// resample trick, this has no hard resampling step to lose quality at,
// so it stays smooth regardless of how many passes are stacked.
const float weights[5] = float[](0.227027, 0.1945946, 0.1216216, 0.054054, 0.016216);

void main() {
    // tex is always one of the bloom FBOs here -- an ordinary GPU render
    // target, not a raw pygame upload, so it needs the un-flip (see _QUAD's
    // comment: its baked V-flip is meant for raw uploads only).
    vec2 uv2 = vec2(uv.x, 1.0 - uv.y);
    vec4 result = texture(tex, uv2) * weights[0];
    for (int i = 1; i < 5; i++) {
        vec2 offset = direction * texel_size * float(i);
        result += texture(tex, uv2 + offset) * weights[i];
        result += texture(tex, uv2 - offset) * weights[i];
    }
    f_color = result * mult;
}
"""

_FRAGMENT_COMPOSITE = """
#version 330
uniform sampler2D scene;
uniform sampler2D bloom;
uniform sampler2D foreground_tex;
uniform sampler2D thick_tex;
uniform sampler2D fog_tex;
uniform sampler2D vignette_tex;
uniform vec2 window_size;
uniform int kind_visibility;
uniform float foreground_alpha;  // 0..1
uniform vec2 fg_pos;             // top-left of the foreground footprint, in screen px
uniform float fg_size;           // footprint side length, in screen px (square)
uniform vec2 tg_player_pos;
uniform float tg_size;
uniform int has_laser;
uniform vec2 tg_laser_pos;
uniform float fog_pan;           // texels, 0..2048 -- see FOG_TEX_HALF comment in gl_present.py
uniform float fog_alpha;         // 0..1
uniform float fog_pan2;          // second fog layer, same texture, panned independently (opposite direction)
uniform float fog_alpha2;        // 0..1
uniform vec3 ambient_tint;       // 0..1, World.ambient_tint_int / 255
uniform float fog_vignette_strength;  // 0..1, see FOG_VIGNETTE_STRENGTH in gl_present.py
in vec2 uv;
out vec4 f_color;

// foreground_tex/thick_tex are static uploads (see load_static_textures --
// tostring-based, not get_view, so no .bgra swizzle needed) sampled as a
// single square footprint positioned in screen space, replicating the old
// CPU blit position math exactly (see gl_present.py module docstring).
vec4 sample_box(sampler2D tex, vec2 screen_px, vec2 box_pos, float box_size) {
    vec2 local = screen_px - box_pos;
    if (local.x < 0.0 || local.y < 0.0 || local.x >= box_size || local.y >= box_size) {
        return vec4(0.0);
    }
    return texture(tex, local / box_size).rgba;
}

// fog_tex is 4096x2048 (the doubled-width trick only applies horizontally
// -- see FOG_TEX_HALF comment above). It spans window_size.x, stretching
// one 2048-wide half across it and panning through it. Vertically it's
// scaled by that same x-derived factor (not independently stretched to
// window_size.y, which would distort it) and anchored to the bottom of
// the screen, growing upward -- if the texture's scaled height falls
// short of window_size.y, the gap above it samples nothing (transparent).
vec4 sample_fog(vec2 screen_px, float pan) {
    float scale = window_size.x / 2048.0;  // screen px per texel
    float texel_x = mod(screen_px.x / scale - pan, 2048.0);

    float texel_y = 2048.0 - (window_size.y - screen_px.y) / scale;
    if (texel_y < 0.0 || texel_y >= 2048.0) {
        return vec4(0.0);
    }

    return texture(fog_tex, vec2(texel_x / 4096.0, texel_y / 2048.0)).rgba;
}

// replicates Terrain.draw_vignette exactly: vignette_img smoothscaled to
// fill the window and multiply-blended -- a plain screen-space stretch, so
// (unlike sample_box/sample_fog) it needs no footprint/box math at all.
vec4 sample_vignette(vec2 screen_px) {
    return texture(vignette_tex, screen_px / window_size).rgba;
}

void main() {
    vec4 c = texture(scene, uv).bgra;
    vec4 b = texture(bloom, vec2(uv.x, 1.0 - uv.y));

    if (kind_visibility == 0) {
        vec2 screen_px = vec2(uv.x * window_size.x, uv.y * window_size.y);

        // fog goes down first, underneath foreground/thick-gradient -- it's
        // composited as a true alpha "over" (not folded into the multiply
        // chain below), since a multiply can only ever darken and so
        // couldn't put visible grey haze over near-black scene pixels
        // (0 * mult is still 0). This can brighten a dark scene, which is
        // the point. Two independent layers of the same texture, panned in
        // opposite directions (see fog_pan/fog_pan2 in present()) for a
        // cheap parallax-y drifting-cloud-layers look, each blended over
        // the other in turn.
        vec4 vignette = sample_vignette(screen_px);
        // full-strength vignette.rgb is Terrain's own darkening; mix it
        // toward white (no-op) by fog_vignette_strength so fog is only
        // partially affected instead of getting the same hard edge falloff
        vec3 fog_tint = ambient_tint * mix(vec3(1.0), vignette.rgb, fog_vignette_strength);

        vec4 fog = sample_fog(screen_px, fog_pan);
        float fog_a = fog.a * fog_alpha;
        // tinted by the same ambient color World.py multiplies the rest of
        // the scene by (see World.tick's ambient_tint/scratch_layer fill)
        // and darkened by the same screen-edge vignette Terrain.draw_vignette
        // multiplies the terrain layer by, so fog picks up both instead of
        // staying a flat neutral grey/edge-to-edge regardless of them
        c.rgb = (fog.rgb * fog_tint) * fog_a + c.rgb * (1.0 - fog_a);

        vec4 fog2 = sample_fog(screen_px, fog_pan2);
        float fog_a2 = fog2.a * fog_alpha2;
        c.rgb = (fog2.rgb * fog_tint) * fog_a2 + c.rgb * (1.0 - fog_a2);

        vec3 mult = vec3(1.0);

        vec4 fg = sample_box(foreground_tex, screen_px, fg_pos, fg_size);
        float fg_a = fg.a * foreground_alpha;
        mult = fg.rgb * fg_a + mult * (1.0 - fg_a);

        vec4 tgp = sample_box(thick_tex, screen_px, tg_player_pos, tg_size);
        mult = tgp.rgb * tgp.a + mult * (1.0 - tgp.a);

        if (has_laser == 1) {
            vec4 tgl = sample_box(thick_tex, screen_px, tg_laser_pos, tg_size);
            mult = tgl.rgb * tgl.a + mult * (1.0 - tgl.a);
        }

        c.rgb *= mult;
    }

    f_color = vec4(c.rgb + b.rgb, 1.0);
}
"""

# full-screen quad: (clip_x, clip_y, u, v) per vertex, rendered as a
# TRIANGLE_STRIP. V is flipped here (bottom-of-screen vertices sample v=1,
# top sample v=0) to correct for the mismatch between pygame's row-0-is-top
# surface layout and OpenGL's row-0-is-bottom texture convention -- without
# this the image renders upside down. (An earlier version of this file had
# it the other way around based on a Framebuffer.read()-based check that
# looked correct but wasn't actually representative of what lands on the
# physical screen -- confirmed wrong by actually looking at the running
# game. Trust what's on screen over a readback comparison.)
_QUAD = np.array(
    [-1, -1, 0, 1, 1, -1, 1, 1, -1, 1, 0, 0, 1, 1, 1, 0],
    dtype="f4",
)


def init():
    global _ctx, _vao, _prog_upload, _prog_threshold, _prog_blur, _prog_composite
    _ctx = moderngl.create_context()

    _prog_upload = _ctx.program(vertex_shader=_VERTEX_SHADER, fragment_shader=_FRAGMENT_UPLOAD)
    _prog_threshold = _ctx.program(vertex_shader=_VERTEX_SHADER, fragment_shader=_FRAGMENT_THRESHOLD)
    _prog_blur = _ctx.program(vertex_shader=_VERTEX_SHADER, fragment_shader=_FRAGMENT_BLUR)
    _prog_composite = _ctx.program(vertex_shader=_VERTEX_SHADER, fragment_shader=_FRAGMENT_COMPOSITE)

    vbo = _ctx.buffer(_QUAD.tobytes())
    # one VAO per program -- moderngl ties a vertex_array to a specific
    # program's attribute locations, so each program needs its own even
    # though they all share the same vertex layout/buffer
    _vao = {
        prog: _ctx.vertex_array(prog, [(vbo, "2f 2f", "in_pos", "in_uv")])
        for prog in (_prog_upload, _prog_threshold, _prog_blur, _prog_composite)
    }


def load_static_textures():
    """Uploads foreground/gradient_thick once as persistent GPU textures.
    Must be called after global_assets.load_assets() has run (needs the
    real asset data) and after init() (needs _ctx) -- see main.py."""
    global _foreground_tex, _thick_tex, _fog_tex, _vignette_tex
    from scripts.global_assets import get_asset

    _foreground_tex = _upload_static(get_asset("foreground"))
    _thick_tex = _upload_static(get_asset("gradient_thick"))
    _fog_tex = _upload_static(get_asset("foreground_fog"))
    _vignette_tex = _upload_static(get_asset("gradient_vignette"))


def _upload_static(surf):
    data = pygame.image.tostring(surf, "RGBA", False)
    tex = _ctx.texture(surf.get_size(), 4, data=data)
    tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
    tex.repeat_x = False
    tex.repeat_y = False
    return tex


def _get_scene_texture(size):
    global _scene_tex, _scene_tex_size
    if _scene_tex is None or _scene_tex_size != size:
        if _scene_tex is not None:
            _scene_tex.release()
        _scene_tex = _ctx.texture(size, 4)
        # NEAREST: always sampled 1:1 against the window's own resolution,
        # so there's nothing to interpolate -- LINEAR was measured
        # introducing tiny (~1-2/255) rounding differences per channel even
        # at exact 1:1 scale, which NEAREST eliminates.
        _scene_tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
        _scene_tex_size = size
    return _scene_tex


def _get_ui_texture(size):
    global _ui_tex, _ui_tex_size
    if _ui_tex is None or _ui_tex_size != size:
        if _ui_tex is not None:
            _ui_tex.release()
        _ui_tex = _ctx.texture(size, 4)
        _ui_tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
        _ui_tex_size = size
    return _ui_tex


def _get_bloom_fbo(size, key=None):
    """key defaults to size itself; pass a distinct key (e.g. "ping") to get
    a second, separately-cached FBO of the SAME size, for ping-pong blur
    passes where two same-size textures are needed at once."""
    if key is None:
        key = size
    fbo = _bloom_fbos.get(key)
    if fbo is None:
        tex = _ctx.texture(size, 4)
        # LINEAR: the blur shader samples neighboring texels at sub-texel
        # offsets (see _FRAGMENT_BLUR), so this needs real interpolation.
        tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        fbo = _ctx.framebuffer(color_attachments=[tex])
        _bloom_fbos[key] = fbo
    return fbo


def _draw_quad(prog):
    _vao[prog].render(moderngl.TRIANGLE_STRIP)


def _compute_bloom(window_size):
    """Renders downscale -> threshold -> N separable-Gaussian blur passes
    -> dim by intensity onto a small framebuffer, reading from the
    already-uploaded _scene_tex. Leaves the result in
    _get_bloom_fbo(small_size)'s texture, sampled by the composite pass."""
    full_w, full_h = window_size
    small_size = (max(1, full_w // BLOOM_DOWNSCALE), max(1, full_h // BLOOM_DOWNSCALE))

    small_fbo = _get_bloom_fbo(small_size)
    ping_fbo = _get_bloom_fbo(small_size, key=("ping", small_size))

    # downscale + luminance threshold in one pass. This downscale is
    # aggressive (BLOOM_DOWNSCALE=10x), so a plain single-tap sample here
    # would silently lose small bright features entirely (a 15px bright
    # spot at 10x downscale is sub-pixel) -- unlike bloom.py's own
    # pygame.transform.smoothscale, which does proper area-averaging. Build
    # mipmaps and let GL's automatic LOD selection pick a properly
    # pre-averaged mip level instead (this IS what mipmaps are for);
    # restored to NEAREST right after, since every other sampling of this
    # texture elsewhere is intentionally exact 1:1 (see _get_scene_texture).
    _scene_tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
    _scene_tex.build_mipmaps()
    small_fbo.use()
    _prog_threshold["scene"] = 0
    _prog_threshold["threshold"] = BLOOM_THRESHOLD
    _scene_tex.use(0)
    _draw_quad(_prog_threshold)
    _scene_tex.filter = (moderngl.NEAREST, moderngl.NEAREST)

    # separable Gaussian blur: each pass is one horizontal + one vertical
    # multi-tap sample, ping-ponging between small_fbo/ping_fbo. Stacking
    # passes widens the effective blur (each pass is itself a real Gaussian,
    # not a lossy resample), which is what fixed the "pixely" look the old
    # shrink/grow-by-bilinear-resample trick had.
    texel_size = (1.0 / small_size[0], 1.0 / small_size[1])
    _prog_blur["tex"] = 0
    _prog_blur["texel_size"] = texel_size
    for i in range(BLOOM_BLUR_PASSES):
        ping_fbo.use()
        _prog_blur["direction"] = (1.0, 0.0)
        _prog_blur["mult"] = 1.0
        small_fbo.color_attachments[0].use(0)
        _draw_quad(_prog_blur)

        small_fbo.use()
        _prog_blur["direction"] = (0.0, 1.0)
        _prog_blur["mult"] = BLOOM_INTENSITY if i == BLOOM_BLUR_PASSES - 1 else 1.0
        ping_fbo.color_attachments[0].use(0)
        _draw_quad(_prog_blur)


def _foreground_uniforms(frame, offset, player_pos, laser_pos):
    left, top, zoom = frame
    offset_x, offset_y = offset

    # replicates World.draw_foreground's position math exactly (no
    # offset_x/offset_y there -- draw_foreground never took those either)
    fg_x = (-left * 6 * zoom) % FG_WORLD_SIZE / 2 - FG_WORLD_SIZE / 2
    fg_y = ((-top * 6 + 500) * zoom) % FG_WORLD_SIZE / 2 - FG_WORLD_SIZE / 2

    # replicates Lighting.draw_thick_gradient's position math exactly
    tg_size = zoom * TG_WORLD_SIZE
    px, py = player_pos
    tg_player_x = (px - left) * zoom - tg_size / 2 + offset_x
    tg_player_y = (py - top) * zoom - tg_size / 2 + offset_y

    if laser_pos is not None:
        lx, ly = laser_pos
        tg_laser_x = (lx - left) * zoom - tg_size / 2 + offset_x
        tg_laser_y = (ly - top) * zoom - tg_size / 2 + offset_y
    else:
        tg_laser_x = tg_laser_y = 0.0

    return fg_x, fg_y, tg_size, tg_player_x, tg_player_y, tg_laser_x, tg_laser_y


def present(cpu_surface, ui_surface, frame, offset, player_pos, laser_pos, kind_visibility, foreground_alpha, ambient_tint):
    """Uploads cpu_surface (the world frame, must be a 32-bit opaque pygame
    Surface -- see Game.render_surface) and ui_surface (the UI overlay, must
    be a 32-bit Surface with real per-pixel alpha -- see Game.ui_surface) as
    GPU textures, computes bloom (recomputed only every BLOOM_UPDATE_INTERVAL
    calls -- see module docstring) and the foreground/thick-gradient
    darkening, composites scene+bloom+foreground, alpha-blends ui_surface on
    top of that, and flips the display.

    frame is (left, top, zoom); offset is (offset_x, offset_y); player_pos
    is (x, y) in world space; laser_pos is (x, y) in world space or None;
    foreground_alpha is 0-255 (World.foreground_alpha); ambient_tint is an
    (r, g, b) 0-255 tuple (World.ambient_tint_int) the fog is tinted by."""
    global _bloom_frame_counter

    window_size = cpu_surface.get_size()
    tex = _get_scene_texture(window_size)
    tex.write(cpu_surface.get_view("1"))

    ui_tex = _get_ui_texture(ui_surface.get_size())
    ui_tex.write(ui_surface.get_view("1"))

    _bloom_frame_counter += 1
    if _bloom_frame_counter == 1 or _bloom_frame_counter % BLOOM_UPDATE_INTERVAL == 0:
        _compute_bloom(window_size)

    small_size = (max(1, window_size[0] // BLOOM_DOWNSCALE), max(1, window_size[1] // BLOOM_DOWNSCALE))
    bloom_tex = _get_bloom_fbo(small_size).color_attachments[0]

    fg_x, fg_y, tg_size, tg_px, tg_py, tg_lx, tg_ly = _foreground_uniforms(frame, offset, player_pos, laser_pos)

    # wall-clock based (not frame_length-accumulated) so the pan rate is
    # independent of framerate/hit-stop; modulo'd on the CPU rather than
    # left to grow unboundedly, since pygame.time.get_ticks() keeps
    # climbing for the whole process lifetime. The "- left * FOG_PARALLAX *
    # zoom / scale" term adds the same *kind* of camera-parallax motion
    # foreground_tex gets (see fg_x above, "-left * 6 * zoom" before its own
    # modulo/centering), but at a smaller factor -- fog reads as farther
    # from the camera than foreground, so it should drift less for the same
    # camera movement -- on top of fog's own constant rightward drift.
    # Python's `%` (not math.fmod, which doesn't wrap negatives into
    # [0, mod)) handles left being negative.
    fog_scale = window_size[0] / FOG_TEX_HALF
    left = frame[0]
    zoom = frame[2]
    now = pygame.time.get_ticks() / 1000
    fog_pan = (now * FOG_SCROLL_SPEED - left * FOG_PARALLAX * zoom / fog_scale) % FOG_TEX_HALF
    # second layer: same texture/math, opposite drift+parallax constants
    # (FOG2_SCROLL_SPEED/FOG2_PARALLAX default to the negatives of the
    # first layer's) -- see sample_fog's two calls in the composite shader
    fog_pan2 = (now * FOG2_SCROLL_SPEED - left * FOG2_PARALLAX * zoom / fog_scale) % FOG_TEX_HALF

    _ctx.screen.use()
    _ctx.disable(moderngl.BLEND)
    _prog_composite["scene"] = 0
    _prog_composite["bloom"] = 1
    _prog_composite["foreground_tex"] = 2
    _prog_composite["thick_tex"] = 3
    _prog_composite["fog_tex"] = 4
    _prog_composite["vignette_tex"] = 5
    _prog_composite["window_size"] = window_size
    _prog_composite["kind_visibility"] = 1 if kind_visibility else 0
    _prog_composite["foreground_alpha"] = max(0.0, min(1.0, foreground_alpha / 255))
    _prog_composite["fg_pos"] = (fg_x, fg_y)
    _prog_composite["fg_size"] = float(FG_WORLD_SIZE)
    _prog_composite["tg_player_pos"] = (tg_px, tg_py)
    _prog_composite["tg_size"] = tg_size
    _prog_composite["has_laser"] = 1 if laser_pos is not None else 0
    _prog_composite["tg_laser_pos"] = (tg_lx, tg_ly)
    _prog_composite["fog_pan"] = fog_pan
    _prog_composite["fog_alpha"] = FOG_ALPHA
    _prog_composite["fog_pan2"] = fog_pan2
    _prog_composite["fog_alpha2"] = FOG2_ALPHA
    _prog_composite["ambient_tint"] = tuple(max(0.0, min(1.0, c / 255)) for c in ambient_tint)
    _prog_composite["fog_vignette_strength"] = FOG_VIGNETTE_STRENGTH
    tex.use(0)
    bloom_tex.use(1)
    _foreground_tex.use(2)
    _thick_tex.use(3)
    _fog_tex.use(4)
    _vignette_tex.use(5)
    _draw_quad(_prog_composite)

    # UI goes on top of everything above, alpha-blended -- this is the one
    # draw call in the whole frame that needs real GL blending, since it's
    # the only pass compositing onto content that's already in the
    # framebuffer rather than writing a fully opaque result.
    _ctx.enable(moderngl.BLEND)
    _ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)
    _prog_upload["scene"] = 0
    ui_tex.use(0)
    _draw_quad(_prog_upload)
    _ctx.disable(moderngl.BLEND)

    pygame.display.flip()
