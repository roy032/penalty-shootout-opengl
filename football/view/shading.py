"""Shaders for the stadium and the players, and the post-processing chain.

Everything in the scene is lit by one GLSL program (``lit``) with a sky and
ground ambient, the floodlight or sun key light with soft shadows, a cool
fill, specular highlights, a rim light and contact darkening near the grass.
The pitch has its own program that paints the grass procedurally: mowing
stripes that change with the viewing angle, patchy colour, worn goalmouths,
and the shadow of the main stand on a sunny day. Colours are lit in linear
space and tone mapped in the shader, so things drawn without a shader (the
HUD markers, the floodlight flares) still look right.

``Post`` adds glow, a soft vignette, a little colour grading and edge
smoothing on top (High quality only). If the graphics card refuses any of
it, the game falls back to Panda's own shader generator."""

from panda3d.core import Shader, Vec3, Vec4, Texture, SamplerState, FrameBufferProperties

# ------------------------------------------------------------------ GLSL
_HEAD = """#version 150
"""

_VERT = """
in vec4 p3d_Vertex;
in vec3 p3d_Normal;
in vec4 p3d_Color;
in vec2 p3d_MultiTexCoord0;
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;
uniform mat4 p3d_ModelMatrix;
out vec3 v_wpos;
out vec3 v_wnorm;
out vec4 v_color;
out vec2 v_uv;
#if SHADOWS
uniform struct { sampler2DShadow shadowMap; mat4 shadowViewMatrix; } u_sun;
out vec4 v_shadow;
#endif
#if SKINNED
// The footballers are skinned on the graphics card: each vertex follows up to
// four joints of the skeleton
uniform mat4 p3d_TransformTable[32];
in vec4 transform_weight;
in uvec4 transform_index;
#endif
void main() {
    vec4 vtx = p3d_Vertex;
    vec3 nrm = p3d_Normal;
#if SKINNED
    mat4 skin = p3d_TransformTable[transform_index.x] * transform_weight.x
              + p3d_TransformTable[transform_index.y] * transform_weight.y
              + p3d_TransformTable[transform_index.z] * transform_weight.z
              + p3d_TransformTable[transform_index.w] * transform_weight.w;
    vtx = skin * vtx;
    nrm = mat3(skin) * nrm;
#endif
    gl_Position = p3d_ModelViewProjectionMatrix * vtx;
    vec4 w = p3d_ModelMatrix * vtx;
    v_wpos = w.xyz;
    v_wnorm = mat3(p3d_ModelMatrix) * nrm;
    v_color = p3d_Color;
    v_uv = p3d_MultiTexCoord0;
#if SHADOWS
    v_shadow = u_sun.shadowViewMatrix * (p3d_ModelViewMatrix * vtx);
#endif
}
"""

# Lighting shared by the lit and grass programs
_LIGHT = """
in vec3 v_wpos;
in vec3 v_wnorm;
in vec4 v_color;
in vec2 v_uv;
out vec4 o_color;
uniform mat4 p3d_ViewMatrixInverse;
uniform vec4 p3d_ColorScale;
uniform vec3 u_sun_dir;       // towards the key light
uniform vec3 u_sun_col;
uniform vec3 u_fill_dir;
uniform vec3 u_fill_col;
uniform vec3 u_sky_col;
uniform vec3 u_ground_col;
uniform vec4 u_fog;           // rgb, density
uniform vec4 u_grade;         // exposure, saturation, contrast, warmth
uniform vec4 u_stand;         // stand edge y, roof height, softness, on
uniform vec4 u_focus;         // floodlight focus: strength, half length, half width, unused
#if SHADOWS
uniform struct { sampler2DShadow shadowMap; mat4 shadowViewMatrix; } u_sun;
in vec4 v_shadow;
uniform vec2 u_shadow_texel;
#endif

vec3 to_linear(vec3 c) { return pow(max(c, vec3(0.0)), vec3(2.2)); }

float sun_shadow(vec3 n) {
    float s = 1.0;
#if SHADOWS
    vec4 sc = v_shadow;
    // Slope-scaled bias, then a 12-tap disc for soft edges
    float ndl = clamp(dot(n, u_sun_dir), 0.0, 1.0);
    sc.z -= (0.0006 + 0.0025 * (1.0 - ndl)) * sc.w;
    vec2 o = u_shadow_texel * 1.6 * sc.w;
    float acc = 0.0;
    acc += textureProj(u_sun.shadowMap, sc);
    acc += textureProj(u_sun.shadowMap, sc + vec4(-0.94, -0.40, 0.0, 0.0) * vec4(o, 1.0, 1.0));
    acc += textureProj(u_sun.shadowMap, sc + vec4( 0.95, -0.77, 0.0, 0.0) * vec4(o, 1.0, 1.0));
    acc += textureProj(u_sun.shadowMap, sc + vec4(-0.09, -0.93, 0.0, 0.0) * vec4(o, 1.0, 1.0));
    acc += textureProj(u_sun.shadowMap, sc + vec4( 0.34,  0.29, 0.0, 0.0) * vec4(o, 1.0, 1.0));
    acc += textureProj(u_sun.shadowMap, sc + vec4(-0.92,  0.46, 0.0, 0.0) * vec4(o, 1.0, 1.0));
    acc += textureProj(u_sun.shadowMap, sc + vec4( 0.70,  0.56, 0.0, 0.0) * vec4(o, 1.0, 1.0));
    acc += textureProj(u_sun.shadowMap, sc + vec4(-0.21,  0.97, 0.0, 0.0) * vec4(o, 1.0, 1.0));
    acc += textureProj(u_sun.shadowMap, sc + vec4( 0.04, -0.19, 0.0, 0.0) * vec4(o * 2.2, 1.0, 1.0));
    acc += textureProj(u_sun.shadowMap, sc + vec4(-0.55, -0.03, 0.0, 0.0) * vec4(o * 2.2, 1.0, 1.0));
    acc += textureProj(u_sun.shadowMap, sc + vec4( 0.56, -0.15, 0.0, 0.0) * vec4(o * 2.2, 1.0, 1.0));
    acc += textureProj(u_sun.shadowMap, sc + vec4( 0.12,  0.58, 0.0, 0.0) * vec4(o * 2.2, 1.0, 1.0));
    s = acc / 12.0;
    // Outside the shadow map counts as lit
    vec3 p = sc.xyz / sc.w;
    if (p.x < 0.0 || p.x > 1.0 || p.y < 0.0 || p.y > 1.0) s = 1.0;
#endif
    // The main stand's shadow on a sunny day: follow the ray to the sun
    if (u_stand.w > 0.5 && u_sun_dir.y < -0.05) {
        float t = (u_stand.x - v_wpos.y) / u_sun_dir.y;
        if (t > 0.0) {
            float z = v_wpos.z + t * u_sun_dir.z;
            s *= mix(0.0, 1.0, smoothstep(u_stand.y - u_stand.z, u_stand.y + u_stand.z, z));
        }
    }
    return s;
}

vec3 tonemap(vec3 c) {
    c *= u_grade.x;
    // ACES filmic fit (Narkowicz)
    c = clamp((c * (2.51 * c + 0.03)) / (c * (2.43 * c + 0.59) + 0.14), 0.0, 1.0);
    c = pow(c, vec3(1.0 / 2.2));
    float l = dot(c, vec3(0.299, 0.587, 0.114));
    c = mix(vec3(l), c, u_grade.y);
    c = (c - 0.5) * u_grade.z + 0.5;
    c *= vec3(1.0 + u_grade.w, 1.0, 1.0 - u_grade.w);
    return clamp(c, 0.0, 1.0);
}

vec3 apply_fog(vec3 lit_lin, float dist) {
    float f = 1.0 - exp(-u_fog.w * dist);
    return mix(lit_lin, to_linear(u_fog.rgb), clamp(f, 0.0, 1.0));
}

// albedo: linear; m: spec, gloss, rim, wrap; m2: ground AO, emissive, sheen, unused
vec3 shade(vec3 albedo, vec3 n, vec4 m, vec4 m2, float extra_shadow) {
    vec3 cam = p3d_ViewMatrixInverse[3].xyz;
    vec3 v = normalize(cam - v_wpos);
    float ao = mix(1.0, smoothstep(-0.05, 0.85, v_wpos.z) * 0.55 + 0.45, m2.x);
    // At night the floodlights are aimed at the pitch: the stands fall off into the dark
    vec2 outside = max(abs(v_wpos.xy) - u_focus.yz, vec2(0.0));
    float focus = 1.0 - u_focus.x * smoothstep(1.0, 16.0, length(outside));
    float up = n.z * 0.5 + 0.5;
    vec3 amb = mix(u_ground_col, u_sky_col, up) * ao * mix(1.0, focus, 0.5);
    float ndl = dot(n, u_sun_dir);
    float diff = max(0.0, (ndl + m.w) / (1.0 + m.w));
    float sh = sun_shadow(n) * extra_shadow * focus;
    vec3 h = normalize(u_sun_dir + v);
    float nh = max(dot(n, h), 0.0);
    float spec = pow(nh, m.y) * m.x * (m.y + 8.0) / 32.0 * step(0.0, ndl);
    float fr = pow(1.0 - max(dot(n, v), 0.0), 4.0);
    float fd = max(0.0, dot(n, u_fill_dir)) ;
    vec3 col = albedo * (amb + u_sun_col * diff * sh + u_fill_col * fd * ao);
    col += u_sun_col * spec * sh;
    // Rim: the sky and the lights catching the edges
    col += (u_sky_col * 0.6 + u_sun_col * 0.25 * sh) * fr * m.z * ao;
    // Sheen: fabric picks up a soft glow at grazing angles
    col += albedo * fr * m2.z * u_sun_col * 0.5 * sh;
    col += albedo * m2.y;
    return col;
}
"""

_LIT_FRAG = """
uniform sampler2D p3d_Texture0;
uniform vec4 u_mat;
uniform vec4 u_mat2;
uniform float u_alpha_cut;
void main() {
    vec4 tex = texture(p3d_Texture0, v_uv);
    vec4 base = tex * v_color * p3d_ColorScale;
    if (base.a < u_alpha_cut) discard;
    vec3 n = normalize(v_wnorm);
    if (!gl_FrontFacing) n = -n;
    vec3 col = shade(to_linear(base.rgb), n, u_mat, u_mat2, 1.0);
    vec3 cam = p3d_ViewMatrixInverse[3].xyz;
    col = apply_fog(col, length(cam - v_wpos));
    o_color = vec4(tonemap(col), base.a);
}
"""

_GRASS_FRAG = """
uniform sampler2D p3d_Texture0;     // blade detail
uniform sampler2D u_noise;          // r: broad, g: medium, b: fine, a: patches
uniform vec4 u_pitch;               // half length, half width, stripe width, wet
uniform vec4 u_grass_a;             // dark grass colour
uniform vec4 u_grass_b;             // light grass colour
uniform sampler2D u_lines;          // painted markings
uniform vec4 u_lines_rect;          // x0, y0, 1/width, 1/height of the mask in metres
uniform vec4 u_line_col;
uniform vec4 u_mat;
uniform vec4 u_mat2;
void main() {
    vec2 p = v_wpos.xy;
    vec3 cam = p3d_ViewMatrixInverse[3].xyz;
    vec3 v = normalize(cam - v_wpos);
    float dist = length(cam - v_wpos);
    vec4 nz = texture(u_noise, p / 61.0);
    vec4 nz2 = texture(u_noise, p / 9.0 + vec2(0.37, 0.71));
    // Mowing stripes: blades laid one way, then the other, so the bands swap
    // brightness depending on which way you look along them
    float band = floor((p.x + u_pitch.x) / u_pitch.z);
    float dir = mod(band, 2.0) < 0.5 ? 1.0 : -1.0;
    vec2 vd = normalize(v.xy + vec2(1e-4));
    float inside = step(abs(p.x), u_pitch.x + 0.5) * step(abs(p.y), u_pitch.y + 0.5);
    float stripe = dir * (0.55 + 0.45 * abs(vd.y)) * inside;
    // A fainter cross-cut along the length
    float cross_band = floor((p.y + u_pitch.y) / (u_pitch.z * 1.25));
    float cross_dir = mod(cross_band, 2.0) < 0.5 ? 1.0 : -1.0;
    stripe += cross_dir * 0.28 * abs(vd.x) * inside;
    // Soften the edge between bands a touch
    float fx = fract((p.x + u_pitch.x) / u_pitch.z);
    float edge = smoothstep(0.0, 0.04, fx) * smoothstep(1.0, 0.96, fx);
    stripe *= mix(0.6, 1.0, edge);
    float tone = 0.5 + 0.5 * (nz.r - 0.5) * 1.4 + 0.25 * (nz2.g - 0.5);
    vec3 a = to_linear(u_grass_a.rgb);
    vec3 b = to_linear(u_grass_b.rgb);
    vec3 albedo = mix(a, b, clamp(tone, 0.0, 1.0));
    albedo *= 1.0 + 0.16 * stripe;
    // Fine blade detail, fading out with distance so it doesn't shimmer
    vec3 det = texture(p3d_Texture0, p / 1.3).rgb;
    float dfade = clamp(1.0 - dist / 70.0, 0.25, 1.0);
    albedo *= mix(vec3(1.0), det * 1.08, dfade);
    // Wear: goalmouths, the penalty spots and the centre circle
    float gm = 0.0;
    for (int s = -1; s <= 1; s += 2) {
        vec2 g = vec2(float(s) * u_pitch.x, 0.0);
        vec2 d = (p - g) / vec2(5.5, 3.8);
        gm = max(gm, exp(-dot(d, d)) * 0.9);
        vec2 ps = (p - (g - vec2(float(s) * u_pitch.x * 0.105, 0.0))) / 1.6;
        gm = max(gm, exp(-dot(ps, ps)) * 0.45);
    }
    vec2 cc = p / 3.0;
    gm = max(gm, exp(-dot(cc, cc)) * 0.35);
    gm *= smoothstep(0.25, 0.75, nz2.a + nz.b * 0.4);
    vec3 dirt = to_linear(vec3(0.42, 0.36, 0.22));
    albedo = mix(albedo, mix(albedo, dirt, 0.85), clamp(gm, 0.0, 1.0));
    // Painted lines: a touch of grass texture shows through the paint
    float line = texture(u_lines, (p - u_lines_rect.xy) * u_lines_rect.zw).r;
    albedo = mix(albedo, to_linear(u_line_col.rgb) * mix(1.0, det.g, 0.25 * dfade), line);
    albedo *= to_linear(p3d_ColorScale.rgb) * to_linear(v_color.rgb);
    // Grass catches the light at grazing angles (and more so when wet)
    vec4 m = u_mat;
    m.x += u_pitch.w * 0.9;
    m.y += u_pitch.w * 60.0;
    vec3 col = shade(albedo, vec3(0.0, 0.0, 1.0), m, u_mat2, 1.0);
    col = apply_fog(col, dist);
    o_color = vec4(tonemap(col), 1.0);
}
"""

_SKY_VERT = """
in vec4 p3d_Vertex;
uniform mat4 p3d_ModelViewProjectionMatrix;
out vec3 v_dir;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    v_dir = p3d_Vertex.xyz;
}
"""

_SKY_FRAG = """
in vec3 v_dir;
out vec4 o_color;
uniform sampler2D u_noise;
uniform vec3 u_zenith;
uniform vec3 u_horizon;
uniform vec3 u_sun_dir;
uniform vec4 u_sky_opts;     // night, cloud cover, time, unused
void main() {
    vec3 d = normalize(v_dir);
    float h = clamp(d.z, -0.2, 1.0);
    vec3 col = mix(u_horizon, u_zenith, pow(clamp(h, 0.0, 1.0), 0.55));
    // Clouds: two octaves of noise projected on a flat cloud layer
    if (d.z > 0.02) {
        vec2 cp = d.xy / (d.z + 0.12) * 0.35 + vec2(u_sky_opts.z * 0.004, 0.0);
        float c = texture(u_noise, cp).r * 0.65 + texture(u_noise, cp * 2.7).g * 0.35;
        c = smoothstep(1.0 - u_sky_opts.y, 1.05 - u_sky_opts.y * 0.5, c);
        vec3 cc = u_sky_opts.x > 0.5 ? vec3(0.06, 0.07, 0.11) : vec3(0.97, 0.97, 1.0);
        col = mix(col, cc, c * smoothstep(0.02, 0.25, d.z) * 0.85);
    }
    if (u_sky_opts.x < 0.5) {
        float sd = max(dot(d, u_sun_dir), 0.0);
        col += vec3(1.0, 0.92, 0.75) * (pow(sd, 600.0) * 3.0 + pow(sd, 12.0) * 0.25);
    }
    o_color = vec4(col, 1.0);
}
"""

# Post-processing: bright pass, separable blur, final composite
_QUAD_VERT = """
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
uniform mat4 p3d_ModelViewProjectionMatrix;
out vec2 v_uv;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    v_uv = p3d_MultiTexCoord0;
}
"""

_BRIGHT_FRAG = """
in vec2 v_uv;
out vec4 o_color;
uniform sampler2D u_src;
uniform vec4 u_texel;        // 1/size of the source, threshold, knee
void main() {
    vec2 t = u_texel.xy;
    vec3 c = texture(u_src, v_uv + vec2(-t.x, -t.y)).rgb + texture(u_src, v_uv + vec2(t.x, -t.y)).rgb
           + texture(u_src, v_uv + vec2(-t.x, t.y)).rgb + texture(u_src, v_uv + vec2(t.x, t.y)).rgb;
    c *= 0.25;
    float l = dot(c, vec3(0.2126, 0.7152, 0.0722));
    float k = smoothstep(u_texel.z, u_texel.z + u_texel.w, l);
    o_color = vec4(c * k, 1.0);
}
"""

_BLUR_FRAG = """
in vec2 v_uv;
out vec4 o_color;
uniform sampler2D u_src;
uniform vec4 u_dir;          // texel step x, y
void main() {
    vec2 d = u_dir.xy;
    vec3 c = texture(u_src, v_uv).rgb * 0.227027;
    c += (texture(u_src, v_uv + d * 1.384615).rgb + texture(u_src, v_uv - d * 1.384615).rgb) * 0.316216;
    c += (texture(u_src, v_uv + d * 3.230769).rgb + texture(u_src, v_uv - d * 3.230769).rgb) * 0.070270;
    o_color = vec4(c, 1.0);
}
"""

_FINAL_FRAG = """
in vec2 v_uv;
out vec4 o_color;
uniform sampler2D u_scene;
uniform sampler2D u_bloom;
uniform vec4 u_post;         // bloom strength, vignette, fxaa on, sharpen
uniform vec4 u_texel;        // 1/width, 1/height
vec3 fxaa(vec2 uv) {
    vec2 t = u_texel.xy;
    vec3 rgbNW = texture(u_scene, uv + vec2(-t.x, -t.y)).rgb;
    vec3 rgbNE = texture(u_scene, uv + vec2(t.x, -t.y)).rgb;
    vec3 rgbSW = texture(u_scene, uv + vec2(-t.x, t.y)).rgb;
    vec3 rgbSE = texture(u_scene, uv + vec2(t.x, t.y)).rgb;
    vec3 rgbM = texture(u_scene, uv).rgb;
    vec3 L = vec3(0.299, 0.587, 0.114);
    float lNW = dot(rgbNW, L), lNE = dot(rgbNE, L), lSW = dot(rgbSW, L), lSE = dot(rgbSE, L), lM = dot(rgbM, L);
    float lMin = min(lM, min(min(lNW, lNE), min(lSW, lSE)));
    float lMax = max(lM, max(max(lNW, lNE), max(lSW, lSE)));
    vec2 dir = vec2(-((lNW + lNE) - (lSW + lSE)), ((lNW + lSW) - (lNE + lSE)));
    float red = max((lNW + lNE + lSW + lSE) * 0.03125, 1.0 / 128.0);
    float rcp = 1.0 / (min(abs(dir.x), abs(dir.y)) + red);
    dir = clamp(dir * rcp, vec2(-8.0), vec2(8.0)) * t;
    vec3 a = 0.5 * (texture(u_scene, uv + dir * (1.0 / 3.0 - 0.5)).rgb + texture(u_scene, uv + dir * (2.0 / 3.0 - 0.5)).rgb);
    vec3 b = a * 0.5 + 0.25 * (texture(u_scene, uv - dir * 0.5).rgb + texture(u_scene, uv + dir * 0.5).rgb);
    float lB = dot(b, L);
    return (lB < lMin || lB > lMax) ? a : b;
}
void main() {
    vec3 c = u_post.z > 0.5 ? fxaa(v_uv) : texture(u_scene, v_uv).rgb;
    if (u_post.w > 0.0) {
        vec2 t = u_texel.xy;
        vec3 blur = (texture(u_scene, v_uv + vec2(t.x, 0.0)).rgb + texture(u_scene, v_uv - vec2(t.x, 0.0)).rgb
                   + texture(u_scene, v_uv + vec2(0.0, t.y)).rgb + texture(u_scene, v_uv - vec2(0.0, t.y)).rgb) * 0.25;
        c = clamp(c + (c - blur) * u_post.w, 0.0, 1.0);
    }
    vec3 bl = texture(u_bloom, v_uv).rgb;
    // Screen blend, so highlights glow without blowing out
    c = 1.0 - (1.0 - c) * (1.0 - bl * u_post.x);
    vec2 q = v_uv - 0.5;
    float vig = 1.0 - dot(q, q) * u_post.y;
    c *= vig;
    o_color = vec4(c, 1.0);
}
"""

_programs = {}


def _program(name, vert, frag, shadows=False, skinned=False):
    key = (name, shadows, skinned)
    if key not in _programs:
        defs = '#define SHADOWS %d\n#define SKINNED %d\n' % (1 if shadows else 0, 1 if skinned else 0)
        _programs[key] = Shader.make(Shader.SL_GLSL, _HEAD + defs + vert, _HEAD + defs + frag)
    return _programs[key]


def lit_shader(shadows):
    return _program('lit', _VERT, _LIGHT + _LIT_FRAG, shadows)


def skinned_shader(shadows):
    return _program('lit', _VERT, _LIGHT + _LIT_FRAG, shadows, skinned=True)


def use_skinning(np):
    """Draw a footballer with the skinned program while the scene uses ours (if not,
    Panda deforms the mesh on the processor). Tagged so a fallback can undo it."""
    from panda3d.core import ShaderAttrib
    if _active is None:
        return False
    attr = ShaderAttrib.make(skinned_shader(_active))
    np.set_attrib(attr.set_flag(ShaderAttrib.F_hardware_skinning, True))
    np.set_tag('skinned', '1')
    return True


# Whether our lighting is on, and with shadows (set by Lighting, cleared by a fallback)
_active = None


def deactivate():
    global _active
    _active = None


def grass_shader(shadows):
    return _program('grass', _VERT, _LIGHT + _GRASS_FRAG, shadows)


def sky_shader():
    return _program('sky', _SKY_VERT, _SKY_FRAG)


def all_programs():
    return list(_programs.values())


# Materials: (spec, gloss, rim, wrap), (ground AO, emissive, sheen, 0)
MATERIALS = {
    'default': ((0.08, 16.0, 0.15, 0.1), (0.0, 0.0, 0.0, 0.0)),
    'shirt': ((0.12, 14.0, 0.35, 0.3), (0.8, 0.0, 0.35, 0.0)),
    'skin': ((0.1, 14.0, 0.16, 0.45), (0.8, 0.0, 0.08, 0.0)),
    'boots': ((0.6, 60.0, 0.3, 0.1), (0.8, 0.0, 0.0, 0.0)),
    'hair': ((0.12, 18.0, 0.2, 0.3), (0.5, 0.0, 0.15, 0.0)),
    'eye': ((0.9, 90.0, 0.1, 0.2), (0.0, 0.03, 0.0, 0.0)),
    'ball': ((0.55, 48.0, 0.3, 0.2), (0.6, 0.0, 0.0, 0.0)),
    'metal': ((0.9, 70.0, 0.35, 0.1), (0.0, 0.0, 0.0, 0.0)),
    'goal': ((0.7, 40.0, 0.3, 0.25), (0.0, 0.08, 0.0, 0.0)),
    'concrete': ((0.04, 8.0, 0.05, 0.2), (0.0, 0.0, 0.0, 0.0)),
    'seats': ((0.25, 30.0, 0.1, 0.2), (0.0, 0.0, 0.0, 0.0)),
    'crowd': ((0.0, 8.0, 0.0, 0.5), (0.0, 0.0, 0.0, 0.0)),
    'roof': ((0.3, 30.0, 0.1, 0.2), (0.0, 0.0, 0.0, 0.0)),
    'led': ((0.4, 50.0, 0.0, 0.0), (0.0, 0.75, 0.0, 0.0)),
    'lines': ((0.05, 10.0, 0.0, 0.3), (0.0, 0.04, 0.0, 0.0)),
    'grass': ((0.06, 12.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0)),
    'net': ((0.0, 8.0, 0.0, 0.6), (0.0, 0.12, 0.0, 0.0)),
}


def material(np, name):
    a, b = MATERIALS[name]
    np.set_shader_input('u_mat', Vec4(*a))
    np.set_shader_input('u_mat2', Vec4(*b))


def _lin(c):
    return Vec3(*(max(0.0, c[i]) ** 2.2 for i in range(3)))


class Lighting:
    """Owns the shader inputs on render: call update() each frame so weather and
    the light colours (which other code changes on the Panda lights) carry through."""

    def __init__(self, base, world, quality):
        self.base = base
        self.world = world
        self.quality = quality
        self.shadows = quality != 'low'
        self.ok = True
        r = base.render
        r.set_shader(lit_shader(self.shadows))
        global _active
        _active = self.shadows
        a, b = MATERIALS['default']
        r.set_shader_input('u_mat', Vec4(*a))
        r.set_shader_input('u_mat2', Vec4(*b))
        r.set_shader_input('u_alpha_cut', 0.0)
        if self.shadows:
            r.set_shader_input('u_sun', world.sun)
            size = world.sun.node().get_shadow_buffer_size()
            r.set_shader_input('u_shadow_texel', (1.0 / max(1, size[0]), 1.0 / max(1, size[1])))
        night = world.night
        # Exposure, saturation, contrast, warmth
        self.grade = Vec4(1.0, 1.04, 1.08, 0.01) if night else Vec4(0.95, 1.04, 1.06, 0.02)
        r.set_shader_input('u_grade', self.grade)
        pt = world.pitch
        r.set_shader_input('u_focus', Vec4(0.8 if night else 0.0, pt.half_length, pt.half_width, 0))
        r.set_shader_input('u_stand', Vec4(0, 0, 1, 0))
        self.update()

    def set_stand_shadow(self, edge_y, height, soft=1.2):
        self.base.render.set_shader_input('u_stand', Vec4(edge_y, height, soft, 1.0))

    def update(self):
        w = self.world
        r = self.base.render
        sun_dir = -w.sun.get_quat(r).get_forward()
        fill_dir = -w.fill.get_quat(r).get_forward()
        sc = w.sun.node().get_color()
        fc = w.fill.node().get_color()
        ac = w.amb.node().get_color()
        k = 1.9 if w.night else 2.2
        r.set_shader_input('u_sun_dir', sun_dir)
        r.set_shader_input('u_sun_col', _lin(sc) * k)
        r.set_shader_input('u_fill_dir', fill_dir)
        r.set_shader_input('u_fill_col', _lin(fc) * 2.2)
        sky = _lin(ac) * (1.25 if w.night else 1.15)
        r.set_shader_input('u_sky_col', Vec3(sky[0] * 0.95, sky[1], sky[2] * 1.12))
        r.set_shader_input('u_ground_col', Vec3(sky[0] * 0.45, sky[1] * 0.6, sky[2] * 0.35))
        fog = w.root.get_fog() if w.root.has_fog() else None
        if fog is not None:
            c = fog.get_color()
            r.set_shader_input('u_fog', Vec4(c[0], c[1], c[2], fog.get_exp_density()))
        else:
            r.set_shader_input('u_fog', Vec4(0, 0, 0, 0))


def check(base):
    """True if every program compiled (after at least one frame has been drawn)."""
    for sh in all_programs():
        if sh.get_error_flag():
            return False
    return True


def _rtt_tex(name):
    t = Texture(name)
    t.set_wrap_u(SamplerState.WM_clamp)
    t.set_wrap_v(SamplerState.WM_clamp)
    t.set_minfilter(SamplerState.FT_linear)
    t.set_magfilter(SamplerState.FT_linear)
    return t


class Post:
    """Scene into a texture, then glow (bright pass and blur at quarter size),
    vignette, a touch of sharpening and FXAA on the way to the screen."""

    def __init__(self, base, bloom=0.5, vignette=0.5):
        from direct.filter.FilterManager import FilterManager
        self.base = base
        self.manager = FilterManager(base.win, base.cam)
        self.scene_tex = _rtt_tex('scene')
        depth = Texture('depth')
        fb = FrameBufferProperties()
        fb.set_rgba_bits(8, 8, 8, 8)
        fb.set_depth_bits(24)
        quad = self.manager.render_scene_into(colortex=self.scene_tex, depthtex=depth, fbprops=fb)
        if quad is None:
            raise RuntimeError('no offscreen buffer')
        self.final = quad
        # Bright pass at half size, blurred at quarter size
        self.bright_tex = _rtt_tex('bright')
        bq = self.manager.render_quad_into('bright', colortex=self.bright_tex, div=2)
        bq.set_shader(_program('bright', _QUAD_VERT, _BRIGHT_FRAG))
        bq.set_shader_input('u_src', self.scene_tex)
        self.bq = bq
        self.blur_a = _rtt_tex('blur_a')
        self.blur_b = _rtt_tex('blur_b')
        qa = self.manager.render_quad_into('blur_x', colortex=self.blur_a, div=4)
        qa.set_shader(_program('blur', _QUAD_VERT, _BLUR_FRAG))
        qa.set_shader_input('u_src', self.bright_tex)
        qb = self.manager.render_quad_into('blur_y', colortex=self.blur_b, div=4)
        qb.set_shader(_program('blur', _QUAD_VERT, _BLUR_FRAG))
        qb.set_shader_input('u_src', self.blur_a)
        self.qa, self.qb = qa, qb
        quad.set_shader(_program('final', _QUAD_VERT, _FINAL_FRAG))
        quad.set_shader_input('u_scene', self.scene_tex)
        quad.set_shader_input('u_bloom', self.blur_b)
        self.params = Vec4(bloom, vignette, 1.0, 0.25)
        quad.set_shader_input('u_post', self.params)
        self.size = None
        self.task = base.task_mgr.add(self._watch_size, 'post-size', sort=-10)

    def _watch_size(self, task):
        size = (self.base.win.get_x_size(), self.base.win.get_y_size())
        if size != self.size:
            self.size = size
            self.resize(*size)
        return task.cont

    def resize(self, w, h):
        w, h = max(1, w), max(1, h)
        self.final.set_shader_input('u_texel', Vec4(1.0 / w, 1.0 / h, 0, 0))
        self.bq.set_shader_input('u_texel', Vec4(1.0 / w, 1.0 / h, 0.8, 0.18))
        q = 4.0
        self.qa.set_shader_input('u_dir', Vec4(q / w, 0, 0, 0))
        self.qb.set_shader_input('u_dir', Vec4(0, q / h, 0, 0))

    def set_bloom(self, amount):
        self.params[0] = amount
        self.final.set_shader_input('u_post', self.params)

    def cleanup(self):
        self.base.task_mgr.remove(self.task)
        self.manager.cleanup()
