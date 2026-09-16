# -*- coding: utf-8 -*-
"""LaTeX 语法检测与渲染(matplotlib mathtext 生成 PNG, 供小提示框展示)"""
import os
import re
import hashlib

from . import paths


def find_latex_spans(content):
    """检测 $...$ 与 $$...$$ 片段, 返回 [(start, end, expr, display)]"""
    spans = []
    for m in re.finditer(r"\$\$([^$\n]+?)\$\$|\$([^$\n]+?)\$", content):
        if m.group(1) is not None:
            spans.append((m.start(), m.end(), m.group(1), True))
        else:
            spans.append((m.start(), m.end(), m.group(2), False))
    return spans


def render_latex_png(expr, display=False):
    """把 LaTeX 表达式渲染为 PNG, 返回 (路径, 像素尺寸, 错误信息或 None)。"""
    cache_dir = os.path.join(paths.DATA_DIR, "latex_cache")
    os.makedirs(cache_dir, exist_ok=True)
    key = hashlib.md5(("1|%d|%s" % (1 if display else 0, expr)).encode("utf-8")
                      ).hexdigest()[:16]
    out = os.path.join(cache_dir, key + ".png")
    if os.path.exists(out):
        try:
            from PIL import Image
            im = Image.open(out)
            return out, im.size, None
        except Exception:
            pass
    try:
        import matplotlib
        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        fig = plt.figure(figsize=(6, 1.2))
        fig.patch.set_facecolor("none")
        fig.text(0.5, 0.5, r"$%s$" % expr.replace("\n", ""), ha="center",
                 va="center", fontsize=18)
        fig.savefig(out, dpi=120, transparent=True, bbox_inches="tight",
                    pad_inches=0.08)
        plt.close(fig)
        from PIL import Image
        im = Image.open(out)
        return out, im.size, None
    except Exception as e:
        try:
            if os.path.exists(out):
                os.remove(out)
        except Exception:
            pass
        return None, None, str(e)


def tooltip_png(expr, display=False):
    """供 GUI 使用: 返回 (PhotoImage, (w,h), 错误信息或 None)"""
    path, size, error = render_latex_png(expr, display)
    if not path:
        return None, None, error or "渲染失败"
    try:
        from PIL import Image, ImageTk
        im = Image.open(path)
        return ImageTk.PhotoImage(im), im.size, None
    except Exception as e:
        return None, None, str(e)
