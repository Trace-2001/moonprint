"""名单预设。

内置只放一个通用示例，不含任何个人信息。

若项目根目录存在 presets.local.json，会自动并入预设列表。
该文件已被 .gitignore 忽略，适合存放自己的常用名单，不会被分发出去。

presets.local.json 格式：
    [
      {
        "id": "family",
        "name": "我的家人",
        "people": [
          {"name": "高远", "year": 2001, "month": 7, "day": 1, "calendar": "lunar"}
        ]
      }
    ]
"""

import json
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_FILE = os.path.join(_ROOT, "presets.local.json")

# 通用示例：不涉及任何人
DEMO = {
    "id": "demo",
    "name": "示例（农历 2001.7.1）",
    "people": [
        {"name": "示例", "year": 2001, "month": 7, "day": 1, "calendar": "lunar"},
    ],
}


def _load_local():
    if not os.path.isfile(LOCAL_FILE):
        return []
    try:
        with open(LOCAL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        out = []
        for item in data:
            if not isinstance(item, dict):
                continue
            people = item.get("people") or []
            norm = []
            for p in people:
                if not all(k in p for k in ("year", "month", "day")):
                    continue
                norm.append({
                    "name": str(p.get("name", "")),
                    "year": int(p["year"]),
                    "month": int(p["month"]),
                    "day": int(p["day"]),
                    "calendar": str(p.get("calendar", "lunar")).lower(),
                })
            if norm:
                out.append({"id": str(item.get("id", "local")),
                            "name": str(item.get("name", "本地名单")),
                            "people": norm})
        return out
    except Exception as e:
        print(f"[presets] 读取 {LOCAL_FILE} 失败: {e}")
        return []


PRESETS = [DEMO] + _load_local()


def get(preset_id):
    for p in PRESETS:
        if p["id"] == preset_id:
            return [dict(x) for x in p["people"]]
    return None


def listing():
    return [{"id": p["id"], "name": p["name"], "count": len(p["people"])}
            for p in PRESETS]
