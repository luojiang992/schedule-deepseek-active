# -*- coding: utf-8 -*-
"""Markdown 语法 → tk.Text tag 渲染(粗体/斜体/划线/代码块/列表/标题)"""
import re


def _add_tag(text, t0, t1, tag, start_off):
    """按字符偏移为文本添加 tag"""
    try:
        text.tag_add(tag, "1.0+%dc" % (start_off + t0),
                     "1.0+%dc" % (start_off + t1))
    except Exception:
        pass


def apply_markdown(text_widget, content):
    """清空并重设所有 md tag(不修改文本内容)。
    渲染规则: #标题 / **粗体** / *斜体* / ~~划线~~ / `行内代码` /
    ```代码块``` / -或*或数字. 列表 / LaTeX($...$) 由外部处理"""
    for tag in ("h1", "h2", "bold", "italic", "strike", "code",
                "codeblock", "list"):
        try:
            text_widget.tag_remove(tag, "1.0", "end")
        except Exception:
            pass

    lines = content.split("\n")
    char_off = 0
    in_block = False
    for line in lines:
        base = char_off
        n = len(line)
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        # 代码块开关
        if stripped.startswith("```"):
            in_block = not in_block
            if in_block:
                _add_tag(text_widget, base, base + n, "codeblock", 0)
            char_off += n + 1
            continue
        if in_block:
            _add_tag(text_widget, base, base + n, "codeblock", 0)
            char_off += n + 1
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            _add_tag(text_widget, base + indent, base + n,
                     "h1" if len(m.group(1)) == 1 else "h2", 0)
            char_off += n + 1
            continue
        # 列表
        if re.match(r"^(\s*[-*+]\s|\s*\d+[.)]\s)", line):
            _add_tag(text_widget, base, base + n, "list", 0)
        # 行内样式: **bold** / *italic* / ~~strike~~ / `code`
        for pat, tag in ((r"\*\*(.+?)\*\*", "bold"),
                         (r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", "italic"),
                         (r"~~(.+?)~~", "strike"),
                         (r"`([^`]+)`", "code")):
            try:
                for mm in re.finditer(pat, line):
                    _add_tag(text_widget, base + mm.start(1), base + mm.end(1),
                             tag, 0)
            except Exception:
                pass
        char_off += n + 1

    # 配置标签样式(幂等)
    _CONFIGURE(text_widget)


def _CONFIGURE(text_widget):
    try:
        text_widget.tag_configure("h1", font=("Microsoft YaHei UI", 15, "bold"),
                                  foreground="#2e86c1", spacing3=4)
        text_widget.tag_configure("h2", font=("Microsoft YaHei UI", 13, "bold"),
                                  foreground="#2e86c1", spacing3=3)
        text_widget.tag_configure("bold", font=("Microsoft YaHei UI", 11, "bold"))
        text_widget.tag_configure("italic", font=("Microsoft YaHei UI", 11, "italic"))
        text_widget.tag_configure("strike", overstrike=True,
                                  foreground="#7f8c8d")
        text_widget.tag_configure("code", font=("Consolas", 11),
                                  background="#2d3a4a", foreground="#7ee2a8")
        text_widget.tag_configure("codeblock", font=("Consolas", 10),
                                  background="#232b38", foreground="#c8d6e5",
                                  lmargin1=16, lmargin2=16)
        text_widget.tag_configure("list", lmargin1=24, lmargin2=24)
    except Exception:
        pass


def markdown_enabled_tags():
    return ("h1", "h2", "bold", "italic", "strike", "code", "codeblock", "list")
