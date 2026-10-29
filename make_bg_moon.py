#!/usr/bin/env python3
"""生成网页背景装饰用的「真实月球」圆盘资源。

复用出图管线（NASA LROC 色彩图 + LOLA 高程 DEM）正交投影渲染一个大尺寸
月球圆盘，保存为带透明通道的 PNG：web/bg-moon.png

用法：
    python3 make_bg_moon.py                        # 默认 radius=620, phase=105
    python3 make_bg_moon.py --radius 800 --phase 90
"""

import argparse
import math
import os
import sys

import numpy as np
from PIL import Image

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from moonbirthday import render as _r


def build_disc(renderer, phase_deg, radius):
    """渲染月球圆盘，返回带 alpha 的 PIL.Image。

    出图管线返回线性光，这里统一转 sRGB，并按同样的羽化曲线套圆形 alpha。
    """
    SS = renderer.SS
    Rf = float(radius * SS)
    cs = int(2 * Rf + 8)
    ys, xs = np.mgrid[0:cs, 0:cs].astype(np.float32)
    ox = oy = Rf + 4
    dx = (xs - ox) / Rf
    dy = (ys - oy) / Rf
    r2 = dx * dx + dy * dy

    disc = (r2 <= 1.0).astype(np.float32)
    inward = (1.0 - np.sqrt(np.maximum(r2, 0.0))) * Rf
    feather = np.clip(inward / _r.EDGE_BAND, 0, 1).astype(np.float32)
    alpha = disc * feather

    lin = _r.render_moon(math.radians(phase_deg), Rf,
                         renderer.col_lin, renderer.gu, renderer.gv,
                         renderer.bump_scale)

    # 2x2 均值降采样（取代 LANCZOS，消除月牙边缘振铃）
    rgb = lin.reshape(cs // SS, SS, cs // SS, SS, 3).mean(axis=(1, 3))
    a = alpha.reshape(cs // SS, SS, cs // SS, SS).mean(axis=(1, 3))

    # 去预乘：管线输出已乘过 alpha（out * disc*feather），
    # 若直接配 alpha 会在羽化边缘二次变暗，这里先还原为直通 alpha
    rgb = rgb / np.maximum(a[..., None], 1e-6)

    rgb = _r.lin_to_srgb(np.clip(rgb, 0, 1))
    rgb = np.clip(0.5 + (rgb - 0.5) * _r.CONTRAST, 0, 1)
    rgba = np.dstack([rgb, a[..., None]])
    return Image.fromarray((np.clip(rgba, 0, 1) * 255).astype(np.uint8), "RGBA")


def main():
    ap = argparse.ArgumentParser(description="生成背景装饰用真实月球圆盘")
    ap.add_argument("-o", "--out", default=None,
                    help="输出路径，默认 <包目录>/web/bg-moon.png")
    ap.add_argument("--radius", type=int, default=620,
                    help="圆盘半径(像素)，默认 620")
    ap.add_argument("--phase", type=float, default=105.0,
                    help="日月黄经差(度): 0=朔, 90=上弦, 180=望")
    a = ap.parse_args()

    out = a.out or os.path.join(_HERE, "web", "bg-moon.png")
    renderer = _r.MoonRenderer("high")
    img = build_disc(renderer, a.phase, a.radius)
    img.save(out)
    print(f"Saved: {out}  {img.size[0]}x{img.size[1]}  "
          f"{os.path.getsize(out) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
