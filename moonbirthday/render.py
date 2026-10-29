"""月球渲染管线（线性光逐像素光照）。

数据源：NASA SVS CGI Moon Kit
    - 色彩/反照率：LROC WAC 拼接图
    - 高程：LOLA 激光测高 DEM

管线要点（与 v3/v4/v5 完全一致，勿随意改参数）：
    1. sRGB 贴图 -> 线性光
    2. DEM 梯度 => 法线扰动（近边缘用 nzz 衰减，避免 1/cos(lat) 放大成噪点）
    3. 朗伯余弦光照 + 临边昏暗(limb darkening)
    4. 单月自动曝光（99.95 分位 -> PEAK_TARGET），模拟分帧长曝
    5. 地照(earthshine)在曝光之后按绝对线性亮度叠加，保证多颗月亮观感一致
    6. soft_clip 软压缩高光

重要：render_moon() 返回的是【线性光】数组，转 sRGB 由 layout 层统一处理。
漏掉这一步会导致整体发暗，这是早期踩过的坑。
"""

import math
import os
import numpy as np
from PIL import Image

# ---------------- 光照 / 观感参数（跨档位保持一致，便于不同作品对比） ----------------
TILT_TARGET = 13.5
TILT_PCT = 95.0
LIMB = 0.22
ES_LEVEL = 0.045
ES_TINT = (0.95, 0.98, 1.08)
CONTRAST = 1.14
GRAIN = 0.016
PEAK_TARGET = 0.92
EXP_MIN, EXP_MAX = 1.0, 80.0
KNEE = 0.72
SAT = 1.14
EDGE_BAND = 2.2
SS = 2  # 超采样倍数

# ---------------- 画质档位：只换贴图分辨率与出图尺寸，光照参数不动 ----------------
QUALITY = {
    "high":   {"col": "lroc_color_4k.tif", "dem": "ldem_16_uint.tif", "R": 1000, "label": "高清 4K"},
    "medium": {"col": "lroc_color_2k.jpg", "dem": "ldem_4_uint.tif",   "R": 700,  "label": "标准 2K"},
    "low":    {"col": "lroc_color_2k.jpg", "dem": "ldem_3_8bit.jpg",   "R": 480,  "label": "轻量 1K"},
}

TEXDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "textures")

# 用户级贴图缓存目录：首次运行若包内无贴图，自动从 NASA 下载到这里
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".moonprint", "textures")

# 本地文件名 -> NASA SVS 官方源（CGI Moon Kit）
_NASA_BASE = "https://svs.gsfc.nasa.gov/vis/a000000/a004700/a004720"
_TEX_SOURCES = {
    "lroc_color_4k.tif":  f"{_NASA_BASE}/lroc_color_poles_4k.tif",
    "lroc_color_2k.jpg":  f"{_NASA_BASE}/lroc_color_poles_2k.tif",
    "ldem_16_uint.tif":   f"{_NASA_BASE}/ldem_16_uint.tif",
    "ldem_4_uint.tif":    f"{_NASA_BASE}/ldem_4_uint.tif",
    "ldem_3_8bit.jpg":    f"{_NASA_BASE}/ldem_3_8bit.jpg",
}


def _download(url, dest):
    """下载贴图到缓存目录。用标准库 urllib，避免额外依赖。"""
    import urllib.request
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    print(f"  [月印] 下载贴图: {os.path.basename(dest)} ...", flush=True)
    try:
        with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
            while True:
                chunk = r.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
        os.replace(tmp, dest)
        return True
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        print(f"  [月印] 下载失败: {e}", flush=True)
        return False


def locate_texture(name):
    """定位贴图文件：包内 -> 用户缓存 -> 自动下载。返回可用的本地路径。"""
    # 1) 包内（开发者/完整安装）
    local = os.path.join(TEXDIR, name)
    if os.path.isfile(local):
        return local
    # 2) 用户缓存
    cached = os.path.join(CACHE_DIR, name)
    if os.path.isfile(cached):
        return cached
    # 3) 自动下载
    url = _TEX_SOURCES.get(name)
    if url and _download(url, cached):
        return cached
    raise FileNotFoundError(f"缺少贴图文件: {name}（本地无、缓存无、下载失败）")

_LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)


def srgb_to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * (c ** (1 / 2.4)) - 0.055)


def _box(a, n, axis):
    """可分离盒式均值滤波（PIL 的 GaussianBlur 不支持 F/I;16 模式，故自实现）。"""
    r = n // 2
    pad = [(0, 0), (0, 0)]
    pad[axis] = (r, r)
    ap = np.pad(a, pad, mode="edge")
    c = np.cumsum(ap, axis=axis, dtype=np.float64)
    hi = [slice(None), slice(None)]
    lo = [slice(None), slice(None)]
    hi[axis] = slice(n, None)
    lo[axis] = slice(None, -n)
    return ((c[tuple(hi)] - c[tuple(lo)]) / n).astype(np.float32)


def gauss_blur(a, passes=2, n=3):
    """3x3 盒式两次 ≈ σ1.15 高斯。"""
    for _ in range(passes):
        a = _box(a, n, 0)
        a = _box(a, n, 1)
    return a


def bilinear(img, xs, ys):
    h, w = img.shape[:2]
    x0 = np.floor(xs).astype(np.int64)
    y0 = np.floor(ys).astype(np.int64)
    wx = (xs - x0).astype(np.float32)
    wy = (ys - y0).astype(np.float32)
    x0c, x1c = np.clip(x0, 0, w - 1), np.clip(x0 + 1, 0, w - 1)
    y0c, y1c = np.clip(y0, 0, h - 1), np.clip(y0 + 1, 0, h - 1)
    if img.ndim == 3:
        wx, wy = wx[..., None], wy[..., None]
    return (img[y0c, x0c] * (1 - wx) * (1 - wy) + img[y0c, x1c] * wx * (1 - wy) +
            img[y1c, x0c] * (1 - wx) * wy + img[y1c, x1c] * wx * wy)


def raw_slopes(lon, lat, gu, gv):
    """由 DEM 梯度得到 (东向坡度, 北向坡度)。"""
    Ht, Wt = gu.shape
    u = lon / (2 * math.pi) + 0.5
    v = 0.5 - lat / math.pi
    px = u * (Wt - 1)
    py = v * (Ht - 1)
    dEdu = bilinear(gu, px, py)
    dEdv = bilinear(gv, px, py)
    dhdlon = dEdu * (Wt - 1) / (2 * math.pi)
    dhdlat = dEdv * (Ht - 1) * (-1.0 / math.pi)
    coslat = np.maximum(np.cos(lat), 0.12)
    return dhdlon / coslat, dhdlat


def compute_bump_scale(gu, gv, target_deg=TILT_TARGET, pct=TILT_PCT):
    """标定法线扰动强度，使坡度 95 分位对应 TILT_TARGET 度倾角。"""
    nl = 420
    lon = np.linspace(-1.4, 1.4, nl).astype(np.float32)
    lat = np.linspace(-1.4, 1.4, nl).astype(np.float32)
    LON, LAT = np.meshgrid(lon, lat)
    se, sn = raw_slopes(LON, LAT, gu, gv)
    mag = np.sqrt(se ** 2 + sn ** 2)
    p = np.percentile(mag, pct)
    return math.tan(math.radians(target_deg)) / max(p, 1e-9)


def soft_clip(x, knee=KNEE):
    """高光软压缩：knee 以下线性，以上指数趋近 1。"""
    return np.where(x <= knee, x, knee + (1 - knee) * (1 - np.exp(-(x - knee) / (1 - knee))))


class MoonRenderer:
    """持有贴图与标定结果，可反复渲染不同相位。

    贴图较厚重（高清档 4K 色图 + 16bit DEM），故按档位缓存，避免重复 IO 与计算。
    """

    def __init__(self, quality="high", texdir=None):
        if quality not in QUALITY:
            raise ValueError(f"未知画质档位: {quality}，可选 {list(QUALITY)}")
        self.quality = quality
        self.cfg = QUALITY[quality]
        self.R = self.cfg["R"]
        self.SS = SS
        td = texdir or TEXDIR

        # 贴图定位：优先传入的 texdir，其次包内/缓存/自动下载
        col_path = os.path.join(td, self.cfg["col"]) if texdir else locate_texture(self.cfg["col"])
        dem_path = os.path.join(td, self.cfg["dem"]) if texdir else locate_texture(self.cfg["dem"])
        for p in (col_path, dem_path):
            if not os.path.exists(p):
                raise FileNotFoundError(f"缺少贴图文件: {p}")

        col = Image.open(col_path).convert("RGB")
        col = np.asarray(col, np.float32) / 255.0
        self.col_lin = srgb_to_lin(col)

        dem_im = Image.open(dem_path)
        dem = np.asarray(dem_im).astype(np.float32)
        dem = (dem - dem.min()) / max(dem.max() - dem.min(), 1e-6)
        self.dem = gauss_blur(dem, passes=2, n=3)
        self.gv, self.gu = np.gradient(self.dem)
        self.bump_scale = compute_bump_scale(self.gu, self.gv)

    def render(self, phase_rad):
        """渲染单个月球圆盘，返回线性光 float32 数组 [H, W, 3]。"""
        return render_moon(phase_rad, self.R * self.SS, self.col_lin,
                           self.gu, self.gv, self.bump_scale)


def render_moon(phase, radius_ss, col_lin, gu, gv, bump_scale):
    """核心渲染：给定相位角(弧度)与超采样半径，输出线性光月面。"""
    Rf = float(radius_ss)
    cs = int(2 * Rf + 8)
    ys, xs = np.mgrid[0:cs, 0:cs].astype(np.float32)
    ox = oy = Rf + 4
    dx = (xs - ox) / Rf
    dy = (ys - oy) / Rf
    r2 = dx * dx + dy * dy
    disc = r2 <= 1.0

    nzz = np.sqrt(np.maximum(1.0 - r2, 0.0))
    nx = np.where(disc, dx, 0.0)
    ny = np.where(disc, -dy, 0.0)
    nzz = np.where(disc, nzz, 0.0)

    lat = np.arcsin(np.clip(ny, -1.0, 1.0))
    lon = np.arctan2(nx, nzz)

    tex_h, tex_w = col_lin.shape[:2]
    u = lon / (2 * math.pi) + 0.5
    v = 0.5 - lat / math.pi
    px = u * (tex_w - 1)
    py = v * (tex_h - 1)

    albedo = bilinear(col_lin, px, py)
    se_raw, sn_raw = raw_slopes(lon, lat, gu, gv)

    # 近边缘衰减：抑制 1/cos(lat) 把坡度放大成孤立亮噪
    fd = np.clip((nzz - 0.05) / 0.20, 0.0, 1.0)
    fade = 0.35 + 0.65 * (fd * fd * (3 - 2 * fd))
    slope_e = se_raw * bump_scale * fade
    slope_n = sn_raw * bump_scale * fade

    cl, sl = np.cos(lon), np.sin(lon)
    cla, sla = np.cos(lat), np.sin(lat)
    Te = np.stack([cl, np.zeros_like(cl), -sl], -1)
    Tn = np.stack([-sla * cl, cla, -sla * sl], -1)

    N = np.stack([nx, ny, nzz], -1) - Te * slope_e[..., None] - Tn * slope_n[..., None]
    N /= np.maximum(np.linalg.norm(N, axis=-1, keepdims=True), 1e-6)

    S = np.array([math.sin(phase), 0.0, -math.cos(phase)], np.float32)
    ccos = np.clip(N @ S, 0.0, 1.0) * disc

    limb = 1.0 - LIMB * (1.0 - np.clip(nzz, 0, 1)) ** 1.5
    lit = albedo * ccos[..., None] * limb[..., None]

    # 单月自动曝光
    lum0 = lit @ _LUMA
    vals = lum0[disc]
    p = float(np.percentile(vals, 99.95)) if vals.size else 0.0
    exp = float(np.clip(PEAK_TARGET / max(p, 1e-6), EXP_MIN, EXP_MAX))

    # 地照：曝光之后按绝对线性亮度叠加，带轻微冷调与向边缘变暗
    es_grad = 0.80 + 0.30 * np.clip(nzz, 0, 1)
    es = albedo * ES_LEVEL * np.array(ES_TINT, np.float32) * es_grad[..., None]
    out = soft_clip(lit * exp + es * disc[..., None])

    lum = out @ _LUMA
    out = lum[..., None] + (out - lum[..., None]) * SAT

    # 边缘羽化
    inward = (1.0 - np.sqrt(np.maximum(r2, 0.0))) * Rf
    feather = np.clip(inward / EDGE_BAND, 0, 1)
    out = out * (disc * feather)[..., None]
    return np.clip(out, 0, 1)
