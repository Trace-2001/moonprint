"""birthday-moon：把农历生日渲染成当天真实月相的图。

典型用法（网页）：
    python3 -m moonbirthday serve

典型用法（命令行）：
    python3 -m moonbirthday make \\
        --person "安雄娥,1996,3,25" \\
        --person "高媛,1997,10,15" \\
        --person "安有奇,1999,12,9" \\
        --person "高远,2001,7,1" \\
        --cols 2 -o 四姐弟月相图.png
"""

from . import astro, render, layout, pipeline, presets
from .pipeline import build, summarize, describe

__version__ = "1.0.0"

__all__ = ["astro", "render", "layout", "pipeline", "presets",
           "build", "summarize", "describe", "__version__"]
