"""网格排版与成图。

把 v5 里写死的 2x2 泛化成任意人数 / 任意列数：
    - 所有尺寸按 s = R / 1000 等比缩放，保证不同画质档位下构图一致
    - 文字三行：名字 / 公历 / 农历（带干支+生肖）

输出约定：
    - 纯黑背景，除月亮与文字外不加任何装饰
    - 色彩空间：sRGB（线性光在 render 层，这里统一转换）
"""

import math
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import render as _r

# 参考基准（v5 在 R=1000 时的取值），其余尺寸按比例缩放
REF_R = 1000.0
MARGIN_X, GAP_X = 150.0, 100.0
MARGIN_Y, GAP_Y = 100.0, 100.0
OFF_NAME, OFF_DATE, OFF_LUNAR = 70.0, 100.0, 215.0
SIZE_NAME, SIZE_DATE, SIZE_LUNAR = 74.0, 92.0, 62.0
# 文字块总高（自月球底边起算）：OFF_NAME + OFF_LUNAR + SIZE_LUNAR
TEXT_BLOCK = OFF_NAME + OFF_LUNAR + SIZE_LUNAR  # 347

_FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]


def find_font():
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def auto_cols(n):
    """按人数自动选列数，尽量接近正方形。"""
    if n <= 1:
        return 1
    if n <= 2:
        return 2
    if n <= 4:
        return 2
    if n <= 6:
        return 3
    if n <= 9:
        return 3
    return math.ceil(math.sqrt(n))


def grid_geometry(n, R, cols=None):
    """计算画布尺寸与各格中心坐标。返回 (W, H, cols, rows, centers)。"""
    s = R / REF_R
    cols = cols or auto_cols(n)
    cols = max(1, min(int(cols), n))
    rows = math.ceil(n / cols)

    mx = MARGIN_X * s
    gx = GAP_X * s
    my = MARGIN_Y * s
    gy = GAP_Y * s
    tb = TEXT_BLOCK * s

    W = int(round(2 * mx + cols * 2 * R + (cols - 1) * gx))
    H = int(round(2 * my + rows * 2 * R + (rows - 1) * (tb + gy) + tb))

    centers = []
    for i in range(n):
        c, rr = i % cols, i // cols
        cx = mx + R + c * (2 * R + gx)
        cy = my + R + rr * (2 * R + tb + gy)
        centers.append((int(round(cx)), int(round(cy))))

    return W, H, cols, rows, centers


def _downsample(moon_ss, SS):
    """2x2 均值降采样（取代 LANCZOS，消除边缘振铃光晕）。"""
    h, w = moon_ss.shape[:2]
    return moon_ss.reshape(h // SS, SS, w // SS, SS, 3).mean(axis=(1, 3))


def apply_logo(img, logo_path, position="top-left",
               scale=0.14, opacity=0.88, margin=0.05):
    """把「月印」logo 叠加到成图角落作为落款（可选，默认关闭）。

    画布为纯黑，logo 是白色（透明底版），直接 alpha 合成即可。
    """
    if not logo_path or not os.path.exists(logo_path):
        return img

    logo = Image.open(logo_path).convert("RGBA")
    tw = max(12, int(img.width * scale))
    th = max(1, int(round(logo.height * tw / logo.width)))
    logo = logo.resize((tw, th), Image.LANCZOS)

    if opacity < 1.0:
        logo.putalpha(logo.getchannel("A").point(lambda v: int(v * opacity)))

    m = int(min(img.width, img.height) * margin)
    pos = {
        "top-left":      (m, m),
        "top-right":     (img.width - tw - m, m),
        "bottom-left":   (m, img.height - th - m),
        "bottom-right":  (img.width - tw - m, img.height - th - m),
    }.get(position, (m, m))

    out = img.convert("RGBA")
    out.alpha_composite(logo, dest=pos)
    return out.convert("RGB")


def compose(people, renderer, cols=None, seed=20010701, progress=None,
            logo_path=None, logo_position="top-left",
            logo_scale=0.14, logo_opacity=0.88):
    """把若干人的月相排成网格并绘制文字。

    people: [{'name':..., **astro.resolve(...)}]
    progress: 可选回调 progress(done, total, message)
    logo_path: 可选，为 None 时不在图上加落款
    """
    n = len(people)
    R = renderer.R
    SS = renderer.SS
    s = R / REF_R

    W, H, cols, rows, centers = grid_geometry(n, R, cols)
    canvas = np.zeros((H, W, 3), np.float32)
    moon_mask = np.zeros((H, W), bool)

    for i, p in enumerate(people):
        cx, cy = centers[i]
        if progress:
            progress(i, n, f"正在渲染 {p.get('name', '')} 的月亮")
        disc = renderer.render(p["phase_rad"])
        small = _downsample(disc, SS)

        t = small.shape[0]
        half = t // 2
        x0, y0 = cx - half, cy - half
        x1, y1 = x0 + t, y0 + t
        sx0, sy0 = max(0, x0), max(0, y0)
        sx1, sy1 = min(W, x1), min(H, y1)
        if sx0 >= sx1 or sy0 >= sy1:
            continue
        dx0, dy0 = sx0 - x0, sy0 - y0
        patch = small[dy0:dy0 + (sy1 - sy0), dx0:dx0 + (sx1 - sx0)]
        canvas[sy0:sy1, sx0:sx1] = np.maximum(canvas[sy0:sy1, sx0:sx1], patch)
        moon_mask[sy0:sy1, sx0:sx1] |= patch.max(axis=2) > 0

    if progress:
        progress(n, n, "正在合成与调色")

    # 线性光 -> sRGB（关键步骤，漏掉会整体发暗）
    canvas = _r.lin_to_srgb(np.clip(canvas, 0, 1))
    canvas = np.clip(0.5 + (canvas - 0.5) * _r.CONTRAST, 0, 1)

    # 散粒噪点，仅作用于月面，背景保持纯净黑
    rng = np.random.default_rng(seed)
    g = rng.standard_normal(canvas.shape).astype(np.float32)
    canvas += g * _r.GRAIN * np.sqrt(np.clip(canvas, 0, 1)) * moon_mask[..., None]
    del g

    img = Image.fromarray((np.clip(canvas, 0, 1) * 255).astype(np.uint8)).convert("RGBA")
    draw = ImageDraw.Draw(img)

    fp = find_font()
    f_name = ImageFont.truetype(fp, max(8, int(round(SIZE_NAME * s)))) if fp else ImageFont.load_default()
    f_date = ImageFont.truetype(fp, max(8, int(round(SIZE_DATE * s)))) if fp else ImageFont.load_default()
    f_lunar = ImageFont.truetype(fp, max(8, int(round(SIZE_LUNAR * s)))) if fp else ImageFont.load_default()

    def centered(cx, y, text, font, fill):
        b = draw.textbbox((0, 0), text, font=font)
        draw.text((cx - (b[2] - b[0]) // 2, y), text, fill=fill, font=font)

    for i, p in enumerate(people):
        cx, cy = centers[i]
        ty = cy + R + OFF_NAME * s
        centered(cx, int(round(ty)), p.get("name", ""), f_name, (214, 214, 214, 255))
        centered(cx, int(round(ty + OFF_DATE * s)), p["gregorian_text"], f_date, (205, 205, 205, 255))
        centered(cx, int(round(ty + OFF_LUNAR * s)), p["lunar_text"], f_lunar, (150, 150, 150, 255))

    # 可选落款：用户勾选「愿意加 logo」时才叠加
    if logo_path:
        img = apply_logo(img, logo_path, position=logo_position,
                         scale=logo_scale, opacity=logo_opacity)

    return img
