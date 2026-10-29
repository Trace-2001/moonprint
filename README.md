# 月印 Moonprint · 生辰月相图

> 每个人来到这世上的那天，月亮都有它自己的样子。

把**生日**还原成出生当天月亮的真实样子。

不是"初一新月、十五满月"这种粗略对应，而是：

- `zhdate` 做农历 ⇄ 公历双向换算
- `ephem`（JPL 星历）反算当天日月**黄经差**，得到真实亮面比例与月牙朝向
- NASA SVS CGI Moon Kit 的 **LROC 色彩贴图 + LOLA 高程 DEM**，在线性光空间逐像素做光照

所以每颗月亮的明暗、月牙弧度、环形山阴影，都是那一天真实的几何关系。
可以为一个人生成**专属**月相图，也可以一次**批量**把全家人都排进去。

---

## 快速开始

### 网页版（推荐）

```bash
cd birthday-moon
python3 -m moonbirthday serve
```

浏览器自动打开 `http://127.0.0.1:8765/`。

界面里可以增删名单、逐行选**阴历/阳历**、调列数、选画质、自定义文件名。
填表时会**实时**显示换算出的公历日期、阴历日期和亮面比例，确认无误再点生成。

```bash
python3 -m moonbirthday serve --port 9000 --no-browser   # 换端口 / 不自动开浏览器
```

### 命令行

```bash
python3 -m moonbirthday make \
  --person "安雄娥,1996,3,25,农历" \
  --person "高媛,1997,10,15,农历" \
  --person "安有奇,1999,12,9" \
  --cols 2 --quality high -o 四姐弟月相图.png
```

`--person` 格式 `名字,年,月,日[,农历|阳历]`，历法缺省为农历，顺序即出图顺序。

只想知道月相、不想等渲染：

```bash
python3 -m moonbirthday preview --person "高远,2001,7,1"
```

### 安装为命令

```bash
pip install .
moonbirthday serve
```

---

## 两种历法输入

每一行都可以**单独**选择输入的是阴历还是阳历：

| 输入历法 | 处理 |
|---|---|
| **阴历** | 阴历生日 → 换算成公历日期 → 算那天的月相 |
| **阳历** | 本身就是公历日期 → 直接算月相，同时反查出对应的阴历 |

两种情况图上都同时显示**公历日期**与**阴历日期（含干支纪年与生肖）**。

---

## 出图设置

| 设置 | 说明 |
|---|---|
| 排版列数 | 1–4 列，或自动：1人→1列，2人→2列，3–4人→2列，5–6人→3列，7–9人→3列，>9人→⌈√n⌉ |
| 画质 | 高清 4K / 标准 2K / 轻量 1K |
| 取相时刻 | 当天 00/06/12/18 时 (UTC) |
| 图片命名 | 自定义文件名，不用写 `.png`；留空则自动生成 `月相图_人数_日期.png` |

单次最多 **12 人**。光照参数三档**完全一致**，保证不同作品之间可以横向对比。

| 档位 | 色彩贴图 | 高程贴图 | 单月直径 | 4 人耗时 |
|---|---|---|---|---|
| `high`（默认） | LROC 4K | LOLA 16bit | 2000px | ~28s |
| `medium` | LROC 2K | LOLA 4bit | 1400px | ~13s |
| `low` | LROC 2K | LOLA 8bit | 960px | ~8s |

---

## 图上文字

每人三行：

```
高远
2001.08.19
阴历 辛巳年(蛇) 七月初一
```

分别是 名字 / 公历日期 / 阴历日期（含干支纪年与生肖）。
背景**纯黑**，不加任何装饰与额外文字。

---

## 目录结构

```
birthday-moon/
├── pyproject.toml
├── README.md
├── .gitignore
├── presets.local.json      # 自己常用的名单（已 gitignore，不会外泄）
├── make_bg_moon.py         # 生成网页背景/logo 用的真实月面图
└── moonbirthday/
    ├── astro.py            # 历法双向换算、黄经差、干支生肖
    ├── render.py           # 贴图定位/下载 + 线性光渲染管线
    ├── layout.py           # 网格排版、文字绘制、可选 logo 落款
    ├── pipeline.py         # 编排：名单 -> 成图
    ├── presets.py          # 名单预设（内置仅通用示例）
    ├── cli.py              # 命令行
    ├── server.py           # 网页服务（仅标准库）
    ├── textures/           # NASA 贴图（已 gitignore，首次运行自动下载）
    └── web/
        ├── index.html
        ├── style.css
        ├── app.js
        └── *.png           # 背景月面 / logo 资源
```

网页服务**刻意不依赖 Flask/FastAPI**，只用标准库 `http.server`，换台机器不必多装东西。

### 关于隐私

内置预设只含一个通用示例，**不包含任何个人信息**。
想加自己常用的名单，在项目根目录建 `presets.local.json`（格式见 `moonbirthday/presets.py` 顶部说明），
它已被 `.gitignore` 忽略，只存在本机、不会随包分发。

---

## 依赖

```
numpy pillow ephem zhdate
```

（可选，仅打包可执行时需要：`pyinstaller`）

### NASA 贴图：首次运行自动下载

NASA 的 LROC/LOLA 贴图约 92MB，**不随仓库分发**。首次渲染时程序会自动从
NASA SVS（`svs.gsfc.nasa.gov`）下载到 `~/.moonprint/textures/` 并缓存，
之后离线可用。若下载失败（比如网络受限），也可手动下载后放到该目录。

| 本地文件名 | NASA 源 |
|---|---|
| `lroc_color_4k.tif` | `lroc_color_poles_4k.tif` |
| `lroc_color_2k.jpg` | `lroc_color_poles_2k.tif` |
| `ldem_16_uint.tif` | `ldem_16_uint.tif` |
| `ldem_4_uint.tif` | `ldem_4_uint.tif` |
| `ldem_3_8bit.jpg` | `ldem_3_8bit.jpg` |

---

## 渲染管线说明

想改观感的话，参数都集中在 `moonbirthday/render.py` 顶部：

| 参数 | 作用 |
|---|---|
| `TILT_TARGET` / `TILT_PCT` | 法线扰动标定：坡度 95 分位对应 13.5° 倾角 |
| `LIMB` | 临边昏暗强度 |
| `ES_LEVEL` / `ES_TINT` | 地照强度与冷调 |
| `PEAK_TARGET` | 自动曝光目标亮度 |
| `KNEE` | 高光软压缩拐点 |
| `CONTRAST` / `SAT` / `GRAIN` | sRGB 空间的对比、饱和、散粒噪点 |

![Uploading 月印Logo-横版-墨黑版.svg…]()

