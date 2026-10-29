"""历法与天文计算。

职责：
    1. 农历生日 -> 公历日期（zhdate）
    2. 当天日月黄经差 + 月球亮面比例（ephem / JPL 星历）
    3. 干支年、生肖
    4. 由黄经差推导中文月相名与亮面朝向

所有角度对外的单位约定：
    get_phase() 返回 (黄经差弧度, 亮面比例 0~1)
    phase_name() / lit_side() 接受「度」
"""

import math
from datetime import datetime

import ephem
from zhdate import ZhDate

MONTH_CN = ["", "正月", "二月", "三月", "四月", "五月", "六月",
            "七月", "八月", "九月", "十月", "冬月", "腊月"]

DAY_CN = ["", "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
          "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九",
          "二十", "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十"]

GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"
SHENGXIAO = "鼠牛虎兔龙蛇马羊猴鸡狗猪"


def lunar_to_gregorian(ly, lm, ld):
    """农历 (年, 月, 日) -> datetime。闰月请用 lm 带 leap 标记的方式由调用方处理。"""
    return ZhDate(ly, lm, ld).to_datetime()


def ganzhi_year(ly):
    """干支纪年。以农历年为基准（春节换年）。例：1996 -> 丙子"""
    return GAN[(ly - 4) % 10] + ZHI[(ly - 4) % 12]


def shengxiao_year(ly):
    """生肖。例：1996 -> 鼠"""
    return SHENGXIAO[(ly - 4) % 12]


def lunar_text(ly, lm, ld):
    """完整阴历文字。例：阴历 丙子年(鼠) 三月廿五"""
    return f"阴历 {ganzhi_year(ly)}年({shengxiao_year(ly)}) {MONTH_CN[lm]}{DAY_CN[ld]}"


def get_phase(dt, hour=12):
    """给定公历 datetime，返回 (黄经差弧度, 亮面比例)。

    亮面比例取 ephem 的 Moon.phase（已考虑天平动等），并同时给出几何值备查。
    """
    obs = ephem.Observer()
    obs.date = dt.strftime(f"%Y/%m/%d {hour:02d}:00")
    moon = ephem.Moon(obs)
    sun = ephem.Sun(obs)
    lon_m = math.degrees(ephem.Ecliptic(moon).lon)
    lon_s = math.degrees(ephem.Ecliptic(sun).lon)
    elong_deg = (lon_m - lon_s) % 360
    return math.radians(elong_deg), moon.phase / 100.0


def geometric_lit_fraction(elong_deg):
    """几何亮面比例 (1 - cos e) / 2，用于独立校验渲染结果。"""
    return (1.0 - math.cos(math.radians(elong_deg))) / 2.0


def phase_name(elong_deg):
    """中文月相名。"""
    if elong_deg < 5 or elong_deg >= 355:
        return "新月"
    if elong_deg < 85:
        return "蛾眉月"
    if elong_deg < 95:
        return "上弦月"
    if elong_deg < 175:
        return "盈凸月"
    if elong_deg < 185:
        return "满月"
    if elong_deg < 265:
        return "亏凸月"
    if elong_deg < 275:
        return "下弦月"
    return "残月"


def lit_side(elong_deg):
    """亮面朝向：黄经差 < 180° 为盈（北半球观看到的亮面在右），否则为亏（左）。"""
    return "右" if elong_deg < 180 else "左"


def gregorian_to_lunar(dt):
    """公历 datetime -> (农历年, 月, 日)。"""
    z = ZhDate.from_datetime(dt)
    return z.lunar_year, z.lunar_month, z.lunar_day


def resolve(y, m, d, hour=12, calendar="lunar"):
    """一步到位：生日 -> 全部展示/渲染所需信息。

    calendar="lunar"  输入的 y/m/d 是农历生日，换算成公历日期
    calendar="solar"  输入的 y/m/d 本来就是公历日期，反查对应的农历

    两种情况下返回结构一致：gregorian_text 是公历，lunar_text 是农历。
    """
    if calendar not in ("lunar", "solar"):
        raise ValueError(f"未知历法: {calendar}（应为 lunar 或 solar）")

    if calendar == "lunar":
        dt = lunar_to_gregorian(y, m, d)
        ly, lm, ld = y, m, d
    else:
        dt = datetime(y, m, d)
        ly, lm, ld = gregorian_to_lunar(dt)

    phase_rad, frac = get_phase(dt, hour)
    elong_deg = math.degrees(phase_rad)
    return {
        "calendar": calendar,
        "lunar_year": ly, "lunar_month": lm, "lunar_day": ld,
        "gregorian": dt,
        "gregorian_text": dt.strftime("%Y.%m.%d"),
        "lunar_text": lunar_text(ly, lm, ld),
        "ganzhi": ganzhi_year(ly),
        "shengxiao": shengxiao_year(ly),
        "elong_deg": elong_deg,
        "lit_fraction": frac,
        "lit_fraction_geometric": geometric_lit_fraction(elong_deg),
        "phase_name": phase_name(elong_deg),
        "lit_side": lit_side(elong_deg),
        "phase_rad": phase_rad,
    }
