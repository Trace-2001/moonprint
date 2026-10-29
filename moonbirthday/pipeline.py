"""高层编排：名单 -> 天文计算 -> 渲染 -> 成图。

对外主要接口：
    summarize(people)            只算天文，不渲染（快，用于前端即时预览）
    build(people, quality, ...)  完整渲染，返回 (PIL.Image, info_list)

people 的元素格式：
    {"name": "安雄娥", "year": 1996, "month": 3, "day": 25}
"""

from . import astro
from . import render as _r
from .layout import compose, grid_geometry, auto_cols

QORDER = ["high", "medium", "low"]

# 按 (档位, 贴图目录) 缓存渲染器。高清档贴图较重，缓存避免重复加载。
_RENDERERS = {}


def get_renderer(quality="high", texdir=None):
    key = (quality, texdir)
    if key not in _RENDERERS:
        _RENDERERS[key] = _r.MoonRenderer(quality, texdir)
    return _RENDERERS[key]


def clear_cache():
    _RENDERERS.clear()


def _norm(p):
    cal = str(p.get("calendar", "lunar") or "lunar").strip().lower()
    if cal not in ("lunar", "solar"):
        cal = "lunar"
    return {
        "name": str(p.get("name", "")).strip(),
        "calendar": cal,
        "year": int(p["year"]),
        "month": int(p["month"]),
        "day": int(p["day"]),
    }


def summarize(people, hour=12):
    """只做历法/天文计算，返回可直接 JSON 化的列表。不渲染，毫秒级。"""
    out = []
    for i, raw in enumerate(people):
        p = _norm(raw)
        info = astro.resolve(p["year"], p["month"], p["day"], hour, p["calendar"])
        info["name"] = p["name"]
        info["index"] = i
        out.append(info)
    return out


def describe(info):
    """把一条记录转成便于前端展示的精简字典（datetime 不可 JSON 化）。"""
    return {
        "name": info["name"],
        "calendar": info.get("calendar", "lunar"),
        "gregorian": info["gregorian_text"],
        "lunar": info["lunar_text"],
        "ganzhi": info["ganzhi"] + "年",
        "shengxiao": info["shengxiao"],
        "elong_deg": round(info["elong_deg"], 2),
        "lit_percent": round(info["lit_fraction"] * 100, 1),
        "phase_name": info["phase_name"],
        "lit_side": info["lit_side"],
    }


def build(people, quality="high", cols=None, texdir=None, hour=12,
          progress=None, logo_path=None, logo_position="top-left",
          logo_scale=0.14, logo_opacity=0.88):
    """完整渲染。返回 (PIL.Image, info_list)。

    logo_path 为 None 时不在图上加落款（默认不加）。
    """
    if quality not in _r.QUALITY:
        raise ValueError(f"未知画质档位: {quality}，可选 {QORDER}")

    renderer = get_renderer(quality, texdir)
    infos = summarize(people, hour)
    img = compose(infos, renderer, cols=cols, progress=progress,
                  logo_path=logo_path, logo_position=logo_position,
                  logo_scale=logo_scale, logo_opacity=logo_opacity)
    return img, infos


def suggest_filename(infos, ext="png"):
    """按人数与日期给出默认文件名。"""
    from datetime import datetime
    stamp = datetime.now().strftime("%Y%m%d")
    return f"月相图_{len(infos)}人_{stamp}.{ext}"
