"""命令行入口。"""

import argparse
import os
import sys
import time

from . import pipeline, presets
from . import render as _r


_CAL_ALIASES = {
    "lunar": "lunar", "农历": "lunar", "阴历": "lunar",
    "solar": "solar", "gregorian": "solar", "阳历": "solar", "公历": "solar",
}


def parse_person(s):
    """解析 '名字,年,月,日[,农历|阳历]'。历法缺省为农历。"""
    parts = [x.strip() for x in s.split(",")]
    if len(parts) not in (4, 5):
        raise argparse.ArgumentTypeError(
            f"格式应为 名字,年,月,日[,农历|阳历]，收到: {s}")
    name, y, m, d = parts[:4]
    cal = "lunar"
    if len(parts) == 5:
        key = parts[4].lower()
        if key not in _CAL_ALIASES:
            raise argparse.ArgumentTypeError(
                f"历法应为 农历 或 阳历，收到: {parts[4]}")
        cal = _CAL_ALIASES[key]
    try:
        return {"name": name, "calendar": cal,
                "year": int(y), "month": int(m), "day": int(d)}
    except ValueError:
        raise argparse.ArgumentTypeError(f"年月日必须是数字，收到: {s}")


def cmd_make(a):
    people = list(a.person)
    if a.preset:
        p = presets.get(a.preset)
        if p is None:
            print(f"未知预设: {a.preset}", file=sys.stderr)
            return 2
        people += p

    if not people:
        print("请至少用 --person 或 --preset 提供一个人", file=sys.stderr)
        return 2

    def prog(done, total, msg):
        pct = int(round(100 * done / total)) if total else 0
        print(f"  [{pct:3d}%] {msg}", flush=True)

    t0 = time.time()
    img, infos = pipeline.build(people, quality=a.quality, cols=a.cols,
                                hour=a.hour, progress=prog)
    img.convert("RGB").save(a.out)
    print(f"\n已保存: {os.path.abspath(a.out)}  {img.size[0]}x{img.size[1]}  "
          f"耗时 {time.time()-t0:.1f}s")
    for i in infos:
        d = pipeline.describe(i)
        print(f"  {d['name']}: {d['gregorian']} / {d['lunar']}"
              f" -> {d['phase_name']} {d['lit_percent']}%，亮面朝{d['lit_side']}")
    return 0


def cmd_preview(a):
    people = list(a.person)
    if a.preset:
        p = presets.get(a.preset)
        if p is None:
            print(f"未知预设: {a.preset}", file=sys.stderr)
            return 2
        people += p
    if not people:
        print("请至少用 --person 或 --preset 提供一个人", file=sys.stderr)
        return 2
    for d in [pipeline.describe(i) for i in pipeline.summarize(people, a.hour)]:
        print(f"{d['name']}: {d['lunar']} -> 公历 {d['gregorian']}  "
              f"黄经差 {d['elong_deg']}°  {d['phase_name']} "
              f"{d['lit_percent']}%  亮面朝{d['lit_side']}")
    return 0


def cmd_serve(a):
    from .server import make_server
    import threading, webbrowser
    srv = make_server(a.host, a.port)
    url = f"http://{a.host}:{a.port}/"
    print(f"生日月相图 · 网页版已启动: {url}")
    print("按 Ctrl+C 停止")
    if not a.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        srv.server_close()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="moonbirthday", description="生日月相图生成器")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # ---- make ----
    m = sub.add_parser("make", help="渲染出图")
    m.add_argument("--person", action="append", default=[], type=parse_person,
                   metavar="名字,年,月,日[,农历|阳历]", help="生日，可重复；历法缺省农历")
    m.add_argument("--preset", choices=[p["id"] for p in presets.PRESETS],
                   help="使用内置家人预设")
    m.add_argument("-o", "--out", default="月相图.png")
    m.add_argument("--quality", choices=list(_r.QUALITY), default="high")
    m.add_argument("--cols", type=int, default=None, help="列数，默认自动")
    m.add_argument("--hour", type=int, default=12, help="取当天几点(UTC)的月相")
    m.add_argument("--logo", choices=["trans", "black"], default="trans",
                help="落款 logo 版本（trans=透明底, black=黑底）")
    m.add_argument("--no-watermark", action="store_true",
                help="不在成图上加 logo 落款")
    m.add_argument("--wm-position",
                choices=["top-left", "top-right", "bottom-left", "bottom-right"],
                default="top-right", help="落款位置")
    m.add_argument("--wm-scale", type=float, default=0.16,
                help="落款宽度占画布宽度的比例")
    m.set_defaults(func=cmd_make)

    # ---- preview ----
    p = sub.add_parser("preview", help="只算天文不出图")
    p.add_argument("--person", action="append", default=[], type=parse_person,
                   metavar="名字,年,月,日")
    p.add_argument("--preset", choices=[p["id"] for p in presets.PRESETS])
    p.add_argument("--hour", type=int, default=12)
    p.set_defaults(func=cmd_preview)

    # ---- serve ----
    s = sub.add_parser("serve", help="启动网页版")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true")
    s.set_defaults(func=cmd_serve)

    a = ap.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
