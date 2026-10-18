"""The graphics pipeline: GLSL lighting and materials, shadow maps,
anti-aliasing and post-processing (bloom, depth of field, motion blur,
heat haze, colour grading and photo filters).

Three quality levels:
- low: the original fixed-function renderer, for old laptops
- medium: shaders, procedural textures, 4x anti-aliasing, a 1024 shadow
  map, colour grading and a vignette
- high: a 2048 shadow map, bloom, depth of field, motion blur, heat haze
  and the live picture on the big screen

The shaders use the compatibility profile (GLSL 1.20), so every existing
immediate-mode draw call goes through them unchanged. If anything fails to
compile or allocate, the game falls back to low and says why.
"""

import json
import math
import os
import random

from OpenGL.GL import *  # noqa: F401,F403

from . import config as C

QUALITIES = ['low', 'medium', 'high']
QUALITY_LABELS = {'low': 'Low (fast)', 'medium': 'Medium', 'high': 'High'}
SETTINGS_FILE = os.path.join(os.path.expanduser('~'), '.penalty_shootout', 'graphics.json')

MATERIALS = {'default': 0, 'grass': 1, 'ball': 2, 'fabric': 3, 'skin': 4, 'paint': 5, 'emissive': 6,
             'screen': 7, 'crowd': 8, 'ground': 9}
# Specular strength and shininess per material (when not set in the shader itself)
SPECULAR = {'default': (0.12, 16.0), 'fabric': (0.07, 12.0), 'skin': (0.16, 22.0), 'paint': (0.75, 64.0),
            'ball': (0.55, 48.0), 'crowd': (0.0, 8.0), 'ground': (0.05, 8.0), 'grass': (0.06, 10.0)}

# Colour grade per look: gain, lift, saturation, contrast
GRADES = {
    'night': ((1.0, 1.0, 1.04), (0.0, 0.0, 0.012), 1.1, 1.06),
    'day': ((1.05, 1.02, 0.96), (0.0, 0.0, 0.0), 1.12, 1.04),
    'rain': ((0.95, 0.99, 1.06), (0.0, 0.005, 0.015), 0.82, 1.06),
    'snow': ((0.97, 1.0, 1.08), (0.02, 0.02, 0.03), 0.88, 1.0),
    'fog': ((1.0, 1.0, 1.02), (0.04, 0.04, 0.05), 0.8, 0.9),
    'dusk': ((1.1, 0.98, 0.84), (0.015, 0.0, 0.0), 1.1, 1.06),
}
PHOTO_FILTERS = ['none', 'mono', 'sepia', 'vivid', 'vintage', 'noir']

state = dict(quality='low', active=False, error=None, size=(0, 0), frame=0)
_progs = {}
_loc = {}
_res = {}            # GL objects: textures, framebuffers, renderbuffers
_uniform_cache = {}
_view = dict(inv=None, eye=(0.0, 0.0, 0.0), near=0.05, far=250.0)
_pass = dict(name='scene')     # 'scene', 'shadow' or 'screen'
_frame = dict(post=None)


# ------------------------------------------------------------------ settings
def load_quality(path=None):
    try:
        path = path or SETTINGS_FILE
        with open(path) as f:
            q = json.load(f).get('quality')
        return q if q in QUALITIES else 'high'
    except (OSError, ValueError, AttributeError):
        return 'high'


def save_quality(q, path=None):
    try:
        path = path or SETTINGS_FILE
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(dict(quality=q), f)
    except OSError:
        pass


def quality():
    return state['quality']


def shaders():
    """True while the GLSL pipeline is drawing the scene."""
    return state['active']


def fancy():
    """Medium or high quality: the extras that need shaders are on."""
    return state['quality'] != 'low'


def high():
    return state['quality'] == 'high'


def shadow_pass():
    return _pass['name'] == 'shadow'


def screen_pass():
    return _pass['name'] == 'screen'


# ------------------------------------------------------------------ matrices
def _norm(v):
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return [c / n for c in v]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def look_at(eye, center, up=(0.0, 1.0, 0.0)):
    """The gluLookAt matrix, column-major."""
    f = _norm([c - e for c, e in zip(center, eye)])
    s = _norm(_cross(f, up))
    u = _cross(s, f)
    return [s[0], u[0], -f[0], 0.0,
            s[1], u[1], -f[1], 0.0,
            s[2], u[2], -f[2], 0.0,
            -_dot(s, eye), -_dot(u, eye), _dot(f, eye), 1.0]


def ortho(l, r, b, t, n, f):
    return [2.0 / (r - l), 0, 0, 0,
            0, 2.0 / (t - b), 0, 0,
            0, 0, -2.0 / (f - n), 0,
            -(r + l) / (r - l), -(t + b) / (t - b), -(f + n) / (f - n), 1.0]


def mat_mul(a, b):
    """a * b for column-major 4x4 lists."""
    out = [0.0] * 16
    for c in range(4):
        for r in range(4):
            out[c * 4 + r] = sum(a[k * 4 + r] * b[c * 4 + k] for k in range(4))
    return out


def invert_rigid(m):
    """Inverse of a rotation plus translation (a view matrix)."""
    r = [[m[c * 4 + rr] for c in range(3)] for rr in range(3)]       # r[row][col]
    t = [m[12], m[13], m[14]]
    rt = [[r[c][rr] for c in range(3)] for rr in range(3)]
    ti = [-sum(rt[rr][k] * t[k] for k in range(3)) for rr in range(3)]
    return [rt[0][0], rt[1][0], rt[2][0], 0.0,
            rt[0][1], rt[1][1], rt[2][1], 0.0,
            rt[0][2], rt[1][2], rt[2][2], 0.0,
            ti[0], ti[1], ti[2], 1.0]


def transform(m, p):
    x, y, z = p
    return [m[0] * x + m[4] * y + m[8] * z + m[12], m[1] * x + m[5] * y + m[9] * z + m[13],
            m[2] * x + m[6] * y + m[10] * z + m[14], m[3] * x + m[7] * y + m[11] * z + m[15]]


def perspective(fov, aspect, near, far):
    f = 1.0 / math.tan(math.radians(fov) / 2.0)
    return [f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) / (near - far), -1.0,
            0, 0, 2 * far * near / (near - far), 0.0]


def _floats(m):
    return (GLfloat * 16)(*m)


# ------------------------------------------------------------------ shaders
SCENE_VS = """
#version 120
uniform mat4 u_invView;
uniform mat4 u_shadowMat;
varying vec3 v_eyePos;
varying vec3 v_eyeN;
varying vec3 v_world;
varying vec3 v_obj;
varying vec4 v_shadow;
varying vec4 v_col;
void main() {
    vec4 eye = gl_ModelViewMatrix * gl_Vertex;
    v_eyePos = eye.xyz;
    v_eyeN = gl_NormalMatrix * gl_Normal;
    vec4 w = u_invView * eye;
    v_world = w.xyz;
    v_obj = gl_Vertex.xyz;
    v_shadow = u_shadowMat * w;
    v_col = gl_Color;
    gl_TexCoord[0] = gl_MultiTexCoord0;
    gl_Position = gl_ProjectionMatrix * eye;
}
"""

SCENE_FS = """
#version 120
uniform int u_mat;
uniform int u_lit;
uniform int u_round;
uniform int u_shadows;
uniform sampler2D u_noise;
uniform sampler2DShadow u_shadowMap;
uniform sampler2D u_screen;
uniform float u_texel;
uniform mat4 u_invView;
uniform vec3 u_eyeWorld;
uniform vec3 u_sky;
uniform float u_wet;
uniform float u_snow;
uniform float u_wear;
uniform float u_dirt;
uniform float u_scuff;
uniform float u_spec;
uniform float u_shine;
uniform float u_emit;
uniform float u_time;
uniform vec3 u_accent;
uniform float u_goalZ;
uniform float u_spotZ;
uniform float u_mow;
varying vec3 v_eyePos;
varying vec3 v_eyeN;
varying vec3 v_world;
varying vec3 v_obj;
varying vec4 v_shadow;
varying vec4 v_col;

float luma(vec3 c) { return dot(c, vec3(0.3, 0.59, 0.11)); }

float shadowAt() {
    if (u_shadows == 0) return 1.0;
    vec3 p = v_shadow.xyz / v_shadow.w;
    if (p.x < 0.0 || p.x > 1.0 || p.y < 0.0 || p.y > 1.0) return 1.0;
    float s = 0.0;
    for (int i = -1; i <= 1; i++)
        for (int j = -1; j <= 1; j++)
            s += shadow2D(u_shadowMap, vec3(p.xy + vec2(float(i), float(j)) * u_texel, p.z - 0.0012)).r;
    return s / 9.0;
}

vec3 icos(int i) {
    float a = 0.5257311, b = 0.8506508;
    if (i == 0) return vec3(0.0, a, b);
    if (i == 1) return vec3(0.0, a, -b);
    if (i == 2) return vec3(0.0, -a, b);
    if (i == 3) return vec3(0.0, -a, -b);
    if (i == 4) return vec3(a, b, 0.0);
    if (i == 5) return vec3(-a, b, 0.0);
    if (i == 6) return vec3(a, -b, 0.0);
    if (i == 7) return vec3(-a, -b, 0.0);
    if (i == 8) return vec3(b, 0.0, a);
    if (i == 9) return vec3(-b, 0.0, a);
    if (i == 10) return vec3(b, 0.0, -a);
    return vec3(-b, 0.0, -a);
}

void main() {
    if (u_round == 1) {
        vec2 d = gl_PointCoord - vec2(0.5);
        if (dot(d, d) > 0.25) discard;
    }
    vec3 base = v_col.rgb;
    float alpha = v_col.a;
    float spec = u_spec;
    float shine = u_shine;
    float dist = length(v_eyePos);
    float fogF = clamp((gl_Fog.end - dist) / (gl_Fog.end - gl_Fog.start), 0.0, 1.0);

    if (u_mat == 7) {                     // the big screen: a live picture
        vec3 c = texture2D(u_screen, gl_TexCoord[0].st).rgb * 1.15;
        float scan = 0.92 + 0.08 * sin(gl_TexCoord[0].t * 540.0);
        gl_FragColor = vec4(mix(gl_Fog.color.rgb, c * scan, fogF * 0.6 + 0.4), 1.0);
        return;
    }
    if (u_lit == 0 || u_mat == 6) {
        float e = (u_mat == 6) ? u_emit : 1.0;
        vec3 c = base * e;
        gl_FragColor = vec4(mix(gl_Fog.color.rgb, c, (u_mat == 6) ? fogF * 0.5 + 0.5 : fogF), alpha);
        return;
    }

    vec3 N = normalize(v_eyeN);
    if (!gl_FrontFacing) N = -N;
    vec3 V = normalize(-v_eyePos);
    vec3 Nw = normalize((u_invView * vec4(N, 0.0)).xyz);
    vec2 p = v_world.xz;

    if (u_mat == 9) {                      // a court or sand: grain, and a sheen when wet
        float g = texture2D(u_noise, p * 2.1).g * 0.6 + texture2D(u_noise, p * 9.0).b * 0.4;
        base *= 0.9 + 0.2 * g;
        if (u_wet > 0.0) { base *= 1.0 - 0.15 * u_wet; spec = 0.35 * u_wet; shine = 60.0; }
    } else if (u_mat == 1) {               // grass
        float n1 = texture2D(u_noise, p * 0.11).r;
        float n2 = texture2D(u_noise, p * 0.9).g;
        float n3 = texture2D(u_noise, p * 6.3).b;
        float n4 = texture2D(u_noise, p * 0.023).a;
        bool chalk = luma(base) > 0.72;
        if (!chalk) {
            base *= 0.8 + 0.24 * n1 + 0.14 * n2 + 0.12 * (n3 - 0.5);
            // Mower stripes catch the light differently depending on the way
            // they were cut and the way you look at them
            float stripe = mod(floor((p.y + 40.0) / 5.5), 2.0) * 2.0 - 1.0;
            vec3 Vw = normalize(u_eyeWorld - v_world);
            base *= 1.0 + u_mow * stripe * Vw.z;
        } else {
            base *= 0.9 + 0.12 * n3;
        }
        // Wear: the goalmouth and the penalty spot get churned up
        float gm = smoothstep(4.8, 1.0, abs(p.x)) * smoothstep(3.6, 0.2, p.y - u_goalZ)
                 * smoothstep(-1.2, 0.0, p.y - u_goalZ);
        float sp = smoothstep(1.1, 0.15, length(p - vec2(0.0, u_spotZ)));
        float w = clamp(max(gm * 0.75, sp) * u_wear * (0.45 + 1.1 * n2) - 0.15 * n1, 0.0, 1.0);
        vec3 soil = vec3(0.34, 0.26, 0.16) * (0.78 + 0.45 * n3);
        base = mix(base, soil, w * (chalk ? 0.45 : 0.9));
        // Rain: darker turf and standing water that mirrors the sky and the lights
        if (u_wet > 0.0) {
            float puddle = smoothstep(0.7, 0.78, n4 * 0.85 + n1 * 0.15) * u_wet;
            puddle = max(puddle, w * u_wet * 0.5);
            base *= 1.0 - 0.15 * u_wet;
            base = mix(base, base * 0.75 + u_sky * 0.3, puddle * 0.5);
            spec = 0.18 * u_wet + puddle * 1.4;
            shine = mix(18.0, 120.0, puddle);
        }
        // Snow settles patchily, then covers everything but the chalk
        if (u_snow > 0.0) {
            float cover = smoothstep(1.0 - u_snow - 0.12, 1.0 - u_snow + 0.12, n1 * 0.55 + n2 * 0.3 + n3 * 0.15);
            cover *= 1.0 - 0.85 * clamp(max(gm, sp * 1.3), 0.0, 1.0);    // trampled round the goal and the spot
            base = mix(base, vec3(0.8, 0.83, 0.9) * (0.92 + 0.08 * n3), cover * (chalk ? 0.25 : 0.92));
            spec = mix(spec, 0.25, cover);
        }
    } else if (u_mat == 2) {               // the ball: panels, seams and scuffs
        vec3 d = normalize(v_obj);
        float m1 = -1.0, m2 = -1.0;
        for (int i = 0; i < 12; i++) {
            float k = abs(dot(d, icos(i)));
            if (k > m1) { m2 = m1; m1 = k; } else if (k > m2) { m2 = k; }
        }
        vec3 white = base;
        if (m1 > 0.955) base = mix(vec3(0.07, 0.07, 0.09), u_accent, 0.35);
        float swoosh = sin(atan(d.z, d.x) * 3.0 + d.y * 5.0);
        if (m1 <= 0.955 && swoosh > 0.82) base = mix(white, u_accent, 0.85);
        if (abs(m1 - m2) < 0.018) base *= 0.55;
        float sc = texture2D(u_noise, d.xy * 0.7 + d.zx * 0.3).b;
        base = mix(base, vec3(0.55, 0.5, 0.42), smoothstep(0.62, 0.8, sc) * u_scuff);
    } else if (u_mat == 3) {               // kit fabric: weave, and mud from slips and dives
        float weave = texture2D(u_noise, v_world.xy * 7.0 + v_world.zx * 7.0).b;
        base *= 0.94 + 0.1 * weave;
        if (u_dirt > 0.0) {
            float m = texture2D(u_noise, v_world.xy * 1.7 + v_world.zx * 1.3).g;
            float low = smoothstep(1.35, 0.3, v_world.y);
            float mud = smoothstep(0.75 - 0.4 * u_dirt, 0.85 - 0.4 * u_dirt, m) * (0.35 + 0.65 * low) * u_dirt;
            base = mix(base, vec3(0.28, 0.21, 0.12), clamp(mud, 0.0, 0.85));
        }
    } else if (u_mat == 8) {               // the crowd: a little variety, no shine
        base *= 0.85 + 0.3 * texture2D(u_noise, v_world.xz * 0.37 + v_world.yy * 0.2).g;
    }

    vec3 L0 = normalize(gl_LightSource[0].position.xyz);
    vec3 L1 = normalize(gl_LightSource[1].position.xyz);
    float d0 = max(dot(N, L0), 0.0);
    float d1 = max(dot(N, L1), 0.0);
    float sh = shadowAt();
    // Sky above, a green bounce off the grass below
    vec3 amb = gl_LightModel.ambient.rgb * mix(vec3(0.72, 0.8, 0.72), vec3(1.08, 1.1, 1.18), Nw.y * 0.5 + 0.5);
    vec3 light = amb + gl_LightSource[0].diffuse.rgb * d0 * (0.25 + 0.75 * sh) + gl_LightSource[1].diffuse.rgb * d1;
    vec3 col = base * light;
    vec3 H = normalize(L0 + V);
    float s = pow(max(dot(N, H), 0.0), shine) * spec * sh;
    col += gl_LightSource[0].diffuse.rgb * s;
    if (u_mat == 3 || u_mat == 4) {        // broadcast rim light on the players
        float rim = pow(1.0 - max(dot(N, V), 0.0), 3.0);
        col += gl_LightSource[0].diffuse.rgb * rim * 0.22 * (u_mat == 4 ? vec3(1.0, 0.85, 0.75) : vec3(1.0));
    }
    gl_FragColor = vec4(mix(gl_Fog.color.rgb, col, fogF), alpha);
}
"""

QUAD_VS = """
#version 120
void main() {
    gl_TexCoord[0] = gl_MultiTexCoord0;
    gl_Position = gl_Vertex;
}
"""

BRIGHT_FS = """
#version 120
uniform sampler2D u_src;
uniform float u_threshold;
uniform vec2 u_px;
void main() {
    vec2 uv = gl_TexCoord[0].st;
    vec3 c = vec3(0.0);
    c += texture2D(u_src, uv + vec2(-u_px.x, -u_px.y)).rgb;
    c += texture2D(u_src, uv + vec2(u_px.x, -u_px.y)).rgb;
    c += texture2D(u_src, uv + vec2(-u_px.x, u_px.y)).rgb;
    c += texture2D(u_src, uv + vec2(u_px.x, u_px.y)).rgb;
    c *= 0.25;
    float l = max(c.r, max(c.g, c.b));
    gl_FragColor = vec4(c * smoothstep(u_threshold, u_threshold + 0.25, l), 1.0);
}
"""

COPY_FS = """
#version 120
uniform sampler2D u_src;
uniform vec2 u_px;
void main() {
    vec2 uv = gl_TexCoord[0].st;
    vec3 c = texture2D(u_src, uv + vec2(-u_px.x, -u_px.y)).rgb + texture2D(u_src, uv + vec2(u_px.x, -u_px.y)).rgb
           + texture2D(u_src, uv + vec2(-u_px.x, u_px.y)).rgb + texture2D(u_src, uv + vec2(u_px.x, u_px.y)).rgb;
    gl_FragColor = vec4(c * 0.25, 1.0);
}
"""

BLUR_FS = """
#version 120
uniform sampler2D u_src;
uniform vec2 u_dir;
void main() {
    vec2 uv = gl_TexCoord[0].st;
    vec3 c = texture2D(u_src, uv).rgb * 0.227;
    c += texture2D(u_src, uv + u_dir * 1.385).rgb * 0.316;
    c += texture2D(u_src, uv - u_dir * 1.385).rgb * 0.316;
    c += texture2D(u_src, uv + u_dir * 3.231).rgb * 0.07;
    c += texture2D(u_src, uv - u_dir * 3.231).rgb * 0.07;
    gl_FragColor = vec4(c, 1.0);
}
"""

COMPOSITE_FS = """
#version 120
uniform sampler2D u_scene;
uniform sampler2D u_bloom;
uniform sampler2D u_blur;
uniform sampler2D u_depth;
uniform sampler2D u_hist;
uniform int u_post;
uniform float u_bloomK;
uniform float u_vignette;
uniform float u_mb;
uniform float u_focus;
uniform float u_range;
uniform float u_near;
uniform float u_far;
uniform vec3 u_gain;
uniform vec3 u_lift;
uniform float u_sat;
uniform float u_contrast;
uniform int u_filter;
uniform vec4 u_haze0;
uniform vec4 u_haze1;
uniform float u_time;
uniform float u_aspect;

vec2 haze(vec2 uv, vec4 h) {
    if (h.w <= 0.0) return uv;
    vec2 d = (uv - h.xy) * vec2(u_aspect, 1.0);
    float k = smoothstep(h.z, 0.0, length(d)) * h.w;
    return uv + k * 0.004 * vec2(sin(uv.y * 160.0 + u_time * 9.0), cos(uv.x * 140.0 + u_time * 7.0));
}

void main() {
    vec2 uv = gl_TexCoord[0].st;
    uv = haze(uv, u_haze0);
    uv = haze(uv, u_haze1);
    vec3 c = texture2D(u_scene, uv).rgb;
    if (u_post == 1) {
        if (u_focus > 0.0) {
            float d = texture2D(u_depth, uv).r * 2.0 - 1.0;
            float lin = 2.0 * u_near * u_far / (u_far + u_near - d * (u_far - u_near));
            float coc = clamp(abs(lin - u_focus) / u_range, 0.0, 1.0);
            c = mix(c, texture2D(u_blur, uv).rgb, coc);
        }
        c += texture2D(u_bloom, uv).rgb * u_bloomK;
        if (u_mb > 0.0) c = mix(c, texture2D(u_hist, gl_TexCoord[0].st).rgb, u_mb);
    }
    c = c * u_gain + u_lift;
    c = (c - 0.5) * u_contrast + 0.5;
    float l = dot(c, vec3(0.3, 0.59, 0.11));
    c = mix(vec3(l), c, u_sat);
    if (u_filter == 1) c = vec3(l);
    else if (u_filter == 2) c = vec3(l) * vec3(1.07, 0.93, 0.74) + vec3(0.04, 0.02, 0.0);
    else if (u_filter == 3) c = mix(vec3(l), c, 1.45) * 1.04;
    else if (u_filter == 4) {
        c = mix(vec3(l), c, 0.7) * vec3(1.06, 0.98, 0.84) * 0.92 + vec3(0.06, 0.05, 0.04);
        c += (fract(sin(dot(uv * (u_time + 1.0), vec2(12.9898, 78.233))) * 43758.5453) - 0.5) * 0.05;
    }
    else if (u_filter == 5) { float m = (l - 0.5) * 1.6 + 0.5; c = vec3(m); }
    vec2 v = uv - 0.5;
    float vig = u_vignette * (u_filter == 5 ? 2.0 : 1.0);
    c *= 1.0 - vig * pow(length(v) * 1.35, 2.6);
    gl_FragColor = vec4(clamp(c, 0.0, 1.0), 1.0);
}
"""


def _compile(vs, fs):
    def shader(kind, src):
        s = glCreateShader(kind)
        glShaderSource(s, src)
        glCompileShader(s)
        if not glGetShaderiv(s, GL_COMPILE_STATUS):
            log = glGetShaderInfoLog(s)
            raise RuntimeError('shader: ' + (log.decode() if isinstance(log, bytes) else str(log)))
        return s
    prog = glCreateProgram()
    glAttachShader(prog, shader(GL_VERTEX_SHADER, vs))
    glAttachShader(prog, shader(GL_FRAGMENT_SHADER, fs))
    glLinkProgram(prog)
    if not glGetProgramiv(prog, GL_LINK_STATUS):
        log = glGetProgramInfoLog(prog)
        raise RuntimeError('link: ' + (log.decode() if isinstance(log, bytes) else str(log)))
    return prog


def _u(prog, name):
    key = (prog, name)
    if key not in _loc:
        _loc[key] = glGetUniformLocation(_progs[prog], name)
    return _loc[key]


def _set(prog, name, *v):
    loc = _u(prog, name)
    if loc < 0:
        return
    if prog == 'scene':
        key = name
        if _uniform_cache.get(key) == v:
            return
        _uniform_cache[key] = v
    if isinstance(v[0], int) and len(v) == 1:
        glUniform1i(loc, v[0])
    elif len(v) == 1:
        glUniform1f(loc, v[0])
    elif len(v) == 2:
        glUniform2f(loc, *v)
    elif len(v) == 3:
        glUniform3f(loc, *v)
    elif len(v) == 4:
        glUniform4f(loc, *v)


def _set_mat(prog, name, m):
    loc = _u(prog, name)
    if loc >= 0:
        glUniformMatrix4fv(loc, 1, GL_FALSE, _floats(m))


# ------------------------------------------------------------------ textures
def _value_noise(size, cells, rng):
    """Tileable smooth value noise, size x size, in 0..1."""
    lattice = [[rng.random() for _ in range(cells)] for _ in range(cells)]
    out = []
    step = cells / float(size)
    for y in range(size):
        fy = y * step
        y0 = int(fy)
        ty = fy - y0
        ty = ty * ty * (3 - 2 * ty)
        r0, r1 = lattice[y0 % cells], lattice[(y0 + 1) % cells]
        for x in range(size):
            fx = x * step
            x0 = int(fx)
            tx = fx - x0
            tx = tx * tx * (3 - 2 * tx)
            a = r0[x0 % cells] + (r0[(x0 + 1) % cells] - r0[x0 % cells]) * tx
            b = r1[x0 % cells] + (r1[(x0 + 1) % cells] - r1[x0 % cells]) * tx
            out.append(a + (b - a) * ty)
    return out


def make_noise(size=128, seed=17):
    """The procedural texture every material samples: four octaves of
    tileable noise, one per channel (broad, medium, fine and very broad)."""
    rng = random.Random(seed)
    chans = []
    for cells, extra in ((8, 16), (16, 32), (32, 64), (4, 8)):
        a = _value_noise(size, cells, rng)
        b = _value_noise(size, extra, rng)
        chans.append([0.72 * u + 0.28 * v for u, v in zip(a, b)])
    data = bytearray(size * size * 4)
    for i in range(size * size):
        for c in range(4):
            data[i * 4 + c] = max(0, min(255, int(chans[c][i] * 255)))
    return bytes(data)


def _texture(w, h, internal, fmt, typ, data=None, filt=GL_LINEAR, wrap=GL_CLAMP_TO_EDGE):
    tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, filt)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, filt)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, wrap)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, wrap)
    glTexImage2D(GL_TEXTURE_2D, 0, internal, w, h, 0, fmt, typ, data)
    glBindTexture(GL_TEXTURE_2D, 0)
    return tex


def _fbo(colour=None, depth=None, depth_rb=None, colour_rb=None):
    fbo = glGenFramebuffers(1)
    glBindFramebuffer(GL_FRAMEBUFFER, fbo)
    if colour is not None:
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, colour, 0)
    if colour_rb is not None:
        glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, colour_rb)
    if depth is not None:
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_TEXTURE_2D, depth, 0)
    if depth_rb is not None:
        glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, depth_rb)
    if colour is None and colour_rb is None:
        glDrawBuffer(GL_NONE)
        glReadBuffer(GL_NONE)
    status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
    glBindFramebuffer(GL_FRAMEBUFFER, 0)
    if status != GL_FRAMEBUFFER_COMPLETE:
        raise RuntimeError(f'framebuffer incomplete ({status})')
    return fbo


def _shadow_size():
    return 2048 if high() else 1024


def _make_shadow():
    size = _shadow_size()
    tex = _texture(size, size, GL_DEPTH_COMPONENT24, GL_DEPTH_COMPONENT, GL_FLOAT, None, GL_LINEAR,
                   GL_CLAMP_TO_BORDER)
    glBindTexture(GL_TEXTURE_2D, tex)
    glTexParameterfv(GL_TEXTURE_2D, GL_TEXTURE_BORDER_COLOR, (GLfloat * 4)(1.0, 1.0, 1.0, 1.0))
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_COMPARE_MODE, GL_COMPARE_REF_TO_TEXTURE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_COMPARE_FUNC, GL_LEQUAL)
    glBindTexture(GL_TEXTURE_2D, 0)
    _res['shadow_tex'] = tex
    _res['shadow_fbo'] = _fbo(depth=tex)
    _res['shadow_size'] = size


def _make_targets(w, h):
    """Multisampled scene buffers, the resolved colour and depth, and the
    small buffers for bloom, depth-of-field blur and motion blur history."""
    _free_targets()
    samples = min(4, int(glGetIntegerv(GL_MAX_SAMPLES)))
    crb, drb = glGenRenderbuffers(1), glGenRenderbuffers(1)
    glBindRenderbuffer(GL_RENDERBUFFER, crb)
    glRenderbufferStorageMultisample(GL_RENDERBUFFER, samples, GL_RGBA8, w, h)
    glBindRenderbuffer(GL_RENDERBUFFER, drb)
    glRenderbufferStorageMultisample(GL_RENDERBUFFER, samples, GL_DEPTH_COMPONENT24, w, h)
    glBindRenderbuffer(GL_RENDERBUFFER, 0)
    _res['msaa_rb'] = (crb, drb)
    _res['msaa_fbo'] = _fbo(colour_rb=crb, depth_rb=drb)
    col = _texture(w, h, GL_RGBA8, GL_RGBA, GL_UNSIGNED_BYTE)
    dep = _texture(w, h, GL_DEPTH_COMPONENT24, GL_DEPTH_COMPONENT, GL_FLOAT, None, GL_NEAREST)
    _res['scene_tex'], _res['depth_tex'] = col, dep
    _res['scene_fbo'] = _fbo(colour=col, depth=dep)
    hw, hh = max(1, w // 2), max(1, h // 2)
    qw, qh = max(1, w // 4), max(1, h // 4)
    for name, (tw, th) in (('half', (hw, hh)), ('bloom_a', (qw, qh)), ('bloom_b', (qw, qh)),
                           ('blur_a', (hw, hh)), ('blur_b', (hw, hh))):
        t = _texture(tw, th, GL_RGBA8, GL_RGBA, GL_UNSIGNED_BYTE)
        _res[name + '_tex'] = t
        _res[name + '_fbo'] = _fbo(colour=t)
        _res[name + '_size'] = (tw, th)
    _res['hist_tex'] = _texture(w, h, GL_RGBA8, GL_RGBA, GL_UNSIGNED_BYTE)
    _res['samples'] = samples
    state['size'] = (w, h)


def _make_screen():
    """The big screen's live picture: a small render target of its own."""
    w, h = 320, 180
    col = _texture(w, h, GL_RGBA8, GL_RGBA, GL_UNSIGNED_BYTE)
    rb = glGenRenderbuffers(1)
    glBindRenderbuffer(GL_RENDERBUFFER, rb)
    glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT24, w, h)
    glBindRenderbuffer(GL_RENDERBUFFER, 0)
    _res['screen_tex'], _res['screen_rb'] = col, rb
    _res['screen_fbo'] = _fbo(colour=col, depth_rb=rb)
    _res['screen_ready'] = False


def _free_targets():
    for key in [k for k in _res if k.endswith('_fbo') and k not in ('shadow_fbo', 'screen_fbo')]:
        glDeleteFramebuffers(1, [_res.pop(key)])
    for key in [k for k in _res if k.endswith('_tex') and k not in ('shadow_tex', 'noise_tex', 'screen_tex')]:
        glDeleteTextures([_res.pop(key)])
    if 'msaa_rb' in _res:
        glDeleteRenderbuffers(2, list(_res.pop('msaa_rb')))
    state['size'] = (0, 0)


def _free_all():
    _free_targets()
    for key in ('shadow_fbo', 'screen_fbo'):
        if key in _res:
            glDeleteFramebuffers(1, [_res.pop(key)])
    for key in ('shadow_tex', 'noise_tex', 'screen_tex'):
        if key in _res:
            glDeleteTextures([_res.pop(key)])
    if 'screen_rb' in _res:
        glDeleteRenderbuffers(1, [_res.pop('screen_rb')])
    _res.clear()
    for p in _progs.values():
        glDeleteProgram(p)
    _progs.clear()
    _loc.clear()
    _uniform_cache.clear()


# ------------------------------------------------------------------ set up
def init(q):
    """Build the pipeline for quality q. Falls back to low on any failure;
    the reason is in state['error']."""
    state['error'] = None
    if state['quality'] != 'low' or _progs:
        try:
            _free_all()
        except Exception:      # noqa: BLE001 - a broken context is being replaced anyway
            _res.clear()
            _progs.clear()
    state['quality'] = q
    state['active'] = False
    if q == 'low':
        glEnable(GL_MULTISAMPLE)
        return True
    try:
        _progs['scene'] = _compile(SCENE_VS, SCENE_FS)
        _progs['bright'] = _compile(QUAD_VS, BRIGHT_FS)
        _progs['copy'] = _compile(QUAD_VS, COPY_FS)
        _progs['blur'] = _compile(QUAD_VS, BLUR_FS)
        _progs['composite'] = _compile(QUAD_VS, COMPOSITE_FS)
        size = 128
        _res['noise_tex'] = _texture(size, size, GL_RGBA8, GL_RGBA, GL_UNSIGNED_BYTE, make_noise(size),
                                     GL_LINEAR, GL_REPEAT)
        glBindTexture(GL_TEXTURE_2D, _res['noise_tex'])
        glGenerateMipmap(GL_TEXTURE_2D)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
        glBindTexture(GL_TEXTURE_2D, 0)
        _make_shadow()
        if high():
            _make_screen()
        glUseProgram(_progs['scene'])
        glUniform1i(_u('scene', 'u_noise'), 1)
        glUniform1i(_u('scene', 'u_shadowMap'), 2)
        glUniform1i(_u('scene', 'u_screen'), 3)
        glUseProgram(0)
    except Exception as e:      # noqa: BLE001 - any GL failure means: draw the simple way
        state['error'] = str(e).splitlines()[0][:120]
        try:
            _free_all()
        except Exception:       # noqa: BLE001
            _res.clear()
            _progs.clear()
        glUseProgram(0)
        state['quality'] = 'low'
        return False
    return True


# ------------------------------------------------------------------ a frame
def begin_frame(w, h):
    """Start drawing a frame into the multisampled buffer (medium and high)."""
    state['frame'] += 1
    if not fancy():
        return
    if state['size'] != (w, h):
        try:
            _make_targets(w, h)
        except Exception as e:  # noqa: BLE001
            state['error'] = str(e)[:120]
            init('low')
            return
    glBindFramebuffer(GL_FRAMEBUFFER, _res['msaa_fbo'])
    glViewport(0, 0, w, h)


def resume_frame():
    """Back to the main frame's buffer after drawing the big screen's picture."""
    if fancy() and 'msaa_fbo' in _res:
        glBindFramebuffer(GL_FRAMEBUFFER, _res['msaa_fbo'])
        glViewport(0, 0, state['size'][0], state['size'][1])


def set_view(eye, look, near=0.05, far=250.0):
    """The camera for this pass: needed to turn eye space back into the world."""
    view = look_at(eye, look)
    _view.update(inv=invert_rigid(view), eye=tuple(eye), near=near, far=far, view=view)


def light_matrix(light_dir, center=(0.0, 0.0, C.GOAL_LINE_Z + 18.0), radius=26.0):
    d = _norm(light_dir)
    eye = [center[i] + d[i] * 60.0 for i in range(3)]
    up = (0.0, 0.0, -1.0) if abs(d[1]) > 0.95 else (0.0, 1.0, 0.0)
    view = look_at(eye, center, up)
    proj = ortho(-radius, radius, -radius, radius, 1.0, 140.0)
    return proj, view


def render_shadows(light_dir, draw_casters):
    """Draw the shadow casters into the depth map, seen from the key light."""
    if not fancy() or 'shadow_fbo' not in _res:
        _res['shadow_mat'] = None
        return
    proj, view = light_matrix(light_dir)
    size = _res['shadow_size']
    glBindFramebuffer(GL_FRAMEBUFFER, _res['shadow_fbo'])
    glViewport(0, 0, size, size)
    glClear(GL_DEPTH_BUFFER_BIT)
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadMatrixf(_floats(proj))
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadMatrixf(_floats(view))
    glColorMask(GL_FALSE, GL_FALSE, GL_FALSE, GL_FALSE)
    glEnable(GL_POLYGON_OFFSET_FILL)
    glPolygonOffset(2.0, 4.0)
    was = _pass['name']
    _pass['name'] = 'shadow'
    try:
        draw_casters()
    finally:
        _pass['name'] = was
        glDisable(GL_POLYGON_OFFSET_FILL)
        glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE)
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()
    bias = [0.5, 0, 0, 0, 0, 0.5, 0, 0, 0, 0, 0.5, 0, 0.5, 0.5, 0.5, 1.0]
    _res['shadow_mat'] = mat_mul(bias, mat_mul(proj, view))


def use_scene(env):
    """Bind the scene shader and the per-frame uniforms. env: wet, snow,
    wear, sky (colour), shadows (bool)."""
    if not fancy() or 'scene' not in _progs:
        state['active'] = False
        return
    glUseProgram(_progs['scene'])
    state['active'] = True
    _uniform_cache.clear()
    glActiveTexture(GL_TEXTURE1)
    glBindTexture(GL_TEXTURE_2D, _res['noise_tex'])
    glActiveTexture(GL_TEXTURE2)
    glBindTexture(GL_TEXTURE_2D, _res.get('shadow_tex', 0))
    glActiveTexture(GL_TEXTURE3)
    glBindTexture(GL_TEXTURE_2D, _res.get('screen_tex', 0) if _res.get('screen_ready') else 0)
    glActiveTexture(GL_TEXTURE0)
    _set_mat('scene', 'u_invView', _view['inv'] or invert_rigid(look_at((0, 2, 10), (0, 1, 0))))
    shadow = _res.get('shadow_mat') if env.get('shadows', True) else None
    _set_mat('scene', 'u_shadowMat', shadow or [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0])
    _set('scene', 'u_shadows', 1 if shadow else 0)
    _set('scene', 'u_texel', 1.0 / _res.get('shadow_size', 1024))
    _set('scene', 'u_eyeWorld', *_view['eye'])
    _set('scene', 'u_sky', *env.get('sky', (0.1, 0.12, 0.2)))
    _set('scene', 'u_wet', float(env.get('wet', 0.0)))
    _set('scene', 'u_snow', float(env.get('snow', 0.0)))
    _set('scene', 'u_wear', float(env.get('wear', 0.4)))
    _set('scene', 'u_goalZ', float(C.GOAL_LINE_Z))
    _set('scene', 'u_spotZ', float(C.SPOT_Z))
    _set('scene', 'u_mow', float(env.get('mow', 0.1)))
    _set('scene', 'u_time', float(env.get('clock', 0.0)))
    _set('scene', 'u_lit', 1)
    _set('scene', 'u_round', 0)
    material('default')


def stop_scene():
    if state['active']:
        glUseProgram(0)
        state['active'] = False


def set_dirt(amount):
    """Mud on the kit being drawn: fabric drawn after this picks it up."""
    state['dirt'] = float(amount)


def material(name, dirt=None, scuff=0.0, accent=(0.85, 0.12, 0.15), emit=1.0):
    """Choose how the next things drawn are shaded (no-op without shaders)."""
    if not state['active']:
        return
    if dirt is None:
        dirt = state.get('dirt', 0.0)
    _set('scene', 'u_mat', MATERIALS.get(name, 0))
    spec, shine = SPECULAR.get(name, SPECULAR['default'])
    _set('scene', 'u_spec', float(spec))
    _set('scene', 'u_shine', float(shine))
    if name == 'fabric':
        _set('scene', 'u_dirt', float(dirt))
    elif name == 'ball':
        _set('scene', 'u_scuff', float(scuff))
        _set('scene', 'u_accent', *accent)
    elif name in ('emissive',):
        _set('scene', 'u_emit', float(emit))


def lighting(on):
    """glEnable/glDisable(GL_LIGHTING), told to the shader as well."""
    if on:
        glEnable(GL_LIGHTING)
    else:
        glDisable(GL_LIGHTING)
    if state['active']:
        _set('scene', 'u_lit', 1 if on else 0)


def round_points(on):
    """Round, soft-edged points for particles when the shader draws them."""
    if not state['active']:
        return
    if on:
        glEnable(GL_POINT_SPRITE)
    else:
        glDisable(GL_POINT_SPRITE)
    _set('scene', 'u_round', 1 if on else 0)


def bind_screen_texture():
    """The big screen's picture, for a textured quad (high quality only)."""
    return bool(state['active'] and _res.get('screen_ready'))


# ---------------------------------------------------------- the big screen
def begin_screen():
    """Render the next pass into the big screen's picture. Returns False
    when the big screen has no live picture at this quality."""
    if not high() or 'screen_fbo' not in _res:
        return False
    glBindFramebuffer(GL_FRAMEBUFFER, _res['screen_fbo'])
    glViewport(0, 0, 320, 180)
    _pass['name'] = 'screen'
    return True


def end_screen():
    stop_scene()
    _pass['name'] = 'scene'
    _res['screen_ready'] = True
    glBindFramebuffer(GL_FRAMEBUFFER, 0)


# ------------------------------------------------------------- post-process
def _quad():
    glBegin(GL_QUADS)
    for u, v in ((0, 0), (1, 0), (1, 1), (0, 1)):
        glTexCoord2f(u, v)
        glVertex2f(u * 2 - 1, v * 2 - 1)
    glEnd()


def _pass_to(fbo, size, prog, src, **uniforms):
    glBindFramebuffer(GL_FRAMEBUFFER, fbo)
    glViewport(0, 0, size[0], size[1])
    glUseProgram(_progs[prog])
    glActiveTexture(GL_TEXTURE0)
    glBindTexture(GL_TEXTURE_2D, src)
    glUniform1i(_u(prog, 'u_src'), 0)
    for k, v in uniforms.items():
        _set(prog, k, *v)
    _quad()


def end_frame(post):
    """Resolve the anti-aliased frame and run the post-processing into the
    window. post: grade (key of GRADES), bloom (strength), focus and range
    (metres; 0 = off), blur (motion blur 0..1), filter (photo filter),
    vignette, haze (list of up to two (x, y, radius, strength) in 0..1
    screen space), time."""
    if not fancy() or 'msaa_fbo' not in _res:
        stop_scene()
        return
    stop_scene()
    w, h = state['size']
    glBindFramebuffer(GL_READ_FRAMEBUFFER, _res['msaa_fbo'])
    glBindFramebuffer(GL_DRAW_FRAMEBUFFER, _res['scene_fbo'])
    glBlitFramebuffer(0, 0, w, h, 0, 0, w, h, GL_COLOR_BUFFER_BIT, GL_NEAREST)
    glBlitFramebuffer(0, 0, w, h, 0, 0, w, h, GL_DEPTH_BUFFER_BIT, GL_NEAREST)
    glPushAttrib(GL_ENABLE_BIT | GL_VIEWPORT_BIT)        # not the colour bits: they hold the draw buffer
    glDisable(GL_DEPTH_TEST)
    glDisable(GL_BLEND)
    glDisable(GL_LIGHTING)
    glDisable(GL_FOG)
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()
    full = high()
    if full:
        hs, qs = _res['half_size'], _res['bloom_a_size']
        _pass_to(_res['half_fbo'], hs, 'copy', _res['scene_tex'], u_px=(0.5 / w, 0.5 / h))
        _pass_to(_res['bloom_a_fbo'], qs, 'bright', _res['half_tex'], u_threshold=(0.84,),
                 u_px=(0.5 / hs[0], 0.5 / hs[1]))
        for _ in range(2):
            _pass_to(_res['bloom_b_fbo'], qs, 'blur', _res['bloom_a_tex'], u_dir=(1.0 / qs[0], 0.0))
            _pass_to(_res['bloom_a_fbo'], qs, 'blur', _res['bloom_b_tex'], u_dir=(0.0, 1.0 / qs[1]))
        if post.get('focus'):
            _pass_to(_res['blur_b_fbo'], hs, 'blur', _res['half_tex'], u_dir=(1.0 / hs[0], 0.0))
            _pass_to(_res['blur_a_fbo'], hs, 'blur', _res['blur_b_tex'], u_dir=(0.0, 1.0 / hs[1]))
            _pass_to(_res['blur_b_fbo'], hs, 'blur', _res['blur_a_tex'], u_dir=(2.0 / hs[0], 0.0))
            _pass_to(_res['blur_a_fbo'], hs, 'blur', _res['blur_b_tex'], u_dir=(0.0, 2.0 / hs[1]))
    glBindFramebuffer(GL_FRAMEBUFFER, 0)
    glViewport(0, 0, w, h)
    glUseProgram(_progs['composite'])
    units = (('u_scene', _res['scene_tex']), ('u_bloom', _res['bloom_a_tex']), ('u_blur', _res['blur_a_tex']),
             ('u_depth', _res['depth_tex']), ('u_hist', _res['hist_tex']))
    for i, (name, tex) in enumerate(units):
        glActiveTexture(GL_TEXTURE0 + i)
        glBindTexture(GL_TEXTURE_2D, tex)
        glUniform1i(_u('composite', name), i)
    gain, lift, sat, contrast = GRADES.get(post.get('grade', 'night'), GRADES['night'])
    haze = list(post.get('haze') or [])[:2] if full else []
    haze += [(0.0, 0.0, 0.0, 0.0)] * (2 - len(haze))
    blur = post.get('blur', 0.0) if full and state.get('hist_ok') else 0.0
    vals = dict(u_post=(1 if full else 0,), u_bloomK=(float(post.get('bloom', 0.5)),),
                u_vignette=(float(post.get('vignette', 0.35)),), u_mb=(float(blur),),
                u_focus=(float(post.get('focus', 0.0)) if full else 0.0,), u_range=(float(post.get('range', 2.0)),),
                u_near=(float(_view['near']),), u_far=(float(_view['far']),), u_gain=gain, u_lift=lift,
                u_sat=(float(sat * post.get('sat', 1.0)),), u_contrast=(float(contrast),),
                u_filter=(PHOTO_FILTERS.index(post.get('filter', 'none')),), u_haze0=tuple(haze[0]),
                u_haze1=tuple(haze[1]), u_time=(float(post.get('time', 0.0)),), u_aspect=(w / float(h),))
    for k, v in vals.items():
        _set('composite', k, *v)
    _quad()
    glUseProgram(0)
    if full:
        # Keep this frame for motion blur on the next
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, _res['hist_tex'])
        glReadBuffer(GL_BACK)
        glCopyTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, 0, 0, w, h)
        state['hist_ok'] = True
    for i in range(5, -1, -1):
        glActiveTexture(GL_TEXTURE0 + i)
        glBindTexture(GL_TEXTURE_2D, 0)
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)
    glPopMatrix()
    glPopAttrib()


def project(p, proj, view):
    """World point to 0..1 screen coordinates (None when behind the camera)."""
    c = transform(proj, transform(view, p)[:3])
    if c[3] <= 0.01:
        return None
    return (c[0] / c[3] * 0.5 + 0.5, c[1] / c[3] * 0.5 + 0.5)
