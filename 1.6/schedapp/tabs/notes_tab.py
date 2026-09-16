# -*- coding: utf-8 -*-
"""「便签」标签页(类 IDE: 分类树 + 多笔记 + 行标 + Markdown/LaTeX 渲染)"""
import os
import re

from .. import model, render_md, render_latex, paths
from ..model import scan_notes, ensure_notes_root
from ..paths import NOTES_ROOT, NOTES_FILE, load_text_file, save_text_file

MD_TAGS = ("h1", "h2", "bold", "italic", "strike", "code", "codeblock", "list")

NOTES_HELP = """便签使用说明
════════════
· 左侧为笔记列表：可在「新建分类」创建子文件夹分类；「新建笔记」在选中分类下建 .txt 笔记。
· 双击左侧笔记打开；「保存」写回当前笔记；关闭程序时自动保存。
· 「📂 打开文件」可打开 .txt/.md/.py（仅读取展示）；「🏠 回到默认便签」返回默认笔记。
· 「MD 渲染」开启后支持: #标题  **粗体**  *斜体*  ~~划线~~  `行内代码`
  ```代码块```  - / 1. 列表。
· 「LaTeX」: 输入 $表达式$ 后鼠标悬停其上，会弹出 matplotlib 渲染的公式小图，
  如 $\\frac{a}{b}$、$\\sqrt{x^2+1}$、$\\alpha + \\beta$、$\\sum_{i=1}^{n} i$。
· 「Σ 符号」「📋 句子」: 符号小窗与快捷句子粘贴板(全局热键 Ctrl+Shift+G / Ctrl+Shift+S)。
· 行号在编辑器左侧自动显示。"""


class NotesTabMixin:
    def _build_notes_tab(self, nb, tk, ttk):
        self.tab_notes = ttk.Frame(nb)
        nb.add(self.tab_notes, text="  便签  ")
        nbar = ttk.Frame(self.tab_notes)
        nbar.pack(fill="x", padx=4, pady=4)
        ttk.Button(nbar, text="💾 保存", command=self.on_notes_save).pack(side="left", padx=(0, 4))
        ttk.Button(nbar, text="📂 打开文件", command=self.on_notes_open).pack(side="left", padx=4)
        ttk.Button(nbar, text="⇩ 另存为", command=self.on_notes_saveas).pack(side="left", padx=4)
        ttk.Button(nbar, text="🏠 默认", command=self.on_notes_back_default).pack(side="left", padx=4)
        ttk.Button(nbar, text="Σ 符号", command=self.toggle_symbols).pack(side="left", padx=4)
        ttk.Button(nbar, text="📋 句子", command=self.toggle_snippets).pack(side="left", padx=4)
        ttk.Button(nbar, text="❓ 帮助", command=self.on_notes_help).pack(side="left", padx=4)
        self.md_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(nbar, text="MD 渲染", variable=self.md_var,
                        command=self._notes_render).pack(side="left", padx=6)
        self.notes_file_lbl = ttk.Label(nbar, text="", foreground=self.c("fg_done"))
        self.notes_file_lbl.pack(side="right")

        body = ttk.Panedwindow(self.tab_notes, orient="horizontal")
        body.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        # 左: 笔记树
        left = ttk.Frame(body)
        body.add(left, weight=1)
        trow = ttk.Frame(left)
        trow.pack(fill="x", pady=(0, 2))
        for btn, cmd in (("＋ 笔记", self.on_note_new), ("＋ 分类", self.on_note_new_cat),
                         ("🗑 删除", self.on_note_delete), ("⟳ 刷新", self.refresh_notes_tree)):
            ttk.Button(trow, text=btn, command=cmd).pack(side="left", padx=1)
        self.notes_tree = ttk.Treeview(left, show="tree", selectmode="browse")
        self.notes_tree.pack(fill="both", expand=True)
        self.notes_tree.bind("<Double-1>", lambda e: self.on_note_open_selected())

        # 右: 行标 + 编辑器
        right = ttk.Frame(body)
        body.add(right, weight=3)
        edbar = ttk.Frame(right)
        edbar.pack(fill="x", pady=(0, 2))
        self.notes_cur = ttk.Label(edbar, text="", foreground=self.c("fg_done"))
        self.notes_cur.pack(side="left")
        edwrap = ttk.Frame(right)
        edwrap.pack(fill="both", expand=True)
        self.line_canvas = tk.Canvas(edwrap, width=44, bg=self.c("card"),
                                     highlightthickness=0)
        self.line_canvas.pack(side="left", fill="y")
        self.notes_text = tk.Text(edwrap, wrap="word", font=("Microsoft YaHei UI", 11),
                                  undo=True, padx=6)
        nsb = ttk.Scrollbar(edwrap, orient="vertical", command=self._notes_scroll)
        self.notes_text.configure(yscrollcommand=nsb.set)
        self.notes_text.pack(side="left", fill="both", expand=True)
        nsb.pack(side="right", fill="y")
        self.notes_text.bind("<Configure>", lambda e: self._draw_line_numbers())
        self.notes_text.bind("<MouseWheel>", lambda e: self._draw_line_numbers())
        self.notes_text.bind("<KeyRelease>", self._notes_on_key)
        try:
            self.notes_text.tag_bind("latex", "<Enter>", self._latex_hover)
            self.notes_text.tag_bind("latex", "<Leave>", self._latex_leave)
        except Exception:
            pass

        # 当前笔记: 默认便签
        self.notes_path = NOTES_FILE
        ensure_notes_root()
        self.refresh_notes_tree()
        self._notes_load(NOTES_FILE)
        self._update_notes_label()

    # ---------- 滚动与行号 ----------
    def _notes_scroll(self, *args):
        self.notes_text.yview(*args)
        self._draw_line_numbers()

    def _draw_line_numbers(self):
        try:
            self.line_canvas.delete("all")
            n = int(self.notes_text.index("end-1c").split(".")[0])
            width = max(30, 10 * len(str(n)) + 10)
            if self.line_canvas.cget("width") != str(width):
                self.line_canvas.configure(width=width)
            for i in range(1, n + 1):
                dline = self.notes_text.dlineinfo("%d.0" % i)
                if dline:
                    y = dline[1]
                    self.line_canvas.create_text(
                        width - 8, y + dline[3] / 2, text=str(i), anchor="e",
                        font=("Consolas", 9), fill="#7f8c8d")
        except Exception:
            pass

    # ---------- 笔记树 ----------
    def refresh_notes_tree(self):
        self.notes_tree.delete(*self.notes_tree.get_children())
        nodes = scan_notes()
        folder_iid = {}
        # 先建分类(含空分类/嵌套子目录)
        for rel, full, name, is_dir in nodes:
            if is_dir:
                parent = os.path.dirname(rel)
                p = folder_iid.get(parent, "") if parent else ""
                folder_iid[rel] = self.notes_tree.insert(
                    p, "end", iid=full, text="📁 " + name, open=True)
        for rel, full, name, is_dir in nodes:
            if not is_dir:
                folder = os.path.dirname(rel)
                parent = folder_iid.get(folder, "") if folder else ""
                self.notes_tree.insert(parent, "end", iid=full, text="📄 " + name)
        try:
            self.notes_tree.selection_set(self.notes_path)
            self.notes_tree.see(self.notes_path)
        except Exception:
            pass

    def _notes_selected_path(self):
        sel = self.notes_tree.selection()
        if sel:
            return sel[0]
        return None

    def on_note_new_cat(self):
        tk, ttk, _, _, _ = self._need_tk()
        name = self._ask_str("新建分类", "分类文件夹名:")
        if not name:
            return
        d = os.path.join(NOTES_ROOT, name.strip())
        os.makedirs(d, exist_ok=True)
        self.refresh_notes_tree()

    def on_note_new(self):
        name = self._ask_str("新建笔记", "笔记名(自动加 .txt):")
        if not name:
            return
        base = NOTES_ROOT
        sel = self._notes_selected_path()
        if sel:
            base = sel if os.path.isdir(sel) else os.path.dirname(sel)
        path = os.path.join(base, name.strip() + ".txt")
        if not os.path.exists(path):
            save_text_file(path, "")
        self.notes_path = path
        self._notes_load(path)
        self.refresh_notes_tree()
        self._update_notes_label()

    def on_note_delete(self):
        sel = self._notes_selected_path()
        if not sel or not os.path.isfile(sel):
            self._info("请选择要删除的笔记文件。")
            return
        if not self._ask("确认删除", "确定删除笔记「%s」吗？此操作不可恢复。"
                         % os.path.basename(sel)):
            return
        try:
            os.remove(sel)
        except Exception as e:
            self._err("删除失败: %s" % e)
            return
        if self.notes_path == sel:
            self.notes_path = NOTES_FILE
            self._notes_load(NOTES_FILE)
            self._update_notes_label()
        self.refresh_notes_tree()
        self._toast("已删除: %s" % os.path.basename(sel))

    def on_note_open_selected(self):
        p = self._notes_selected_path()
        if p:
            self.notes_path = p
            self.settings["notes_last_file"] = p
            paths.save_settings(self.settings)
            self._notes_load(p)
            self._update_notes_label()

    # ---------- 编辑器 ----------
    def _notes_load(self, path):
        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", load_text_file(path))
        self._notes_render()
        self._draw_line_numbers()

    def _notes_content(self):
        try:
            return self.notes_text.get("1.0", "end-1c")
        except Exception:
            return ""

    def _save_notes(self):
        try:
            save_text_file(self.notes_path, self._notes_content())
        except Exception:
            pass

    def _update_notes_label(self):
        try:
            rel = os.path.relpath(self.notes_path, NOTES_ROOT)
            tag = "（默认）" if self.notes_path == NOTES_FILE else ""
            self.notes_file_lbl.configure(text="当前: %s %s" % (rel, tag))
        except Exception:
            pass

    def on_notes_save(self):
        self._save_notes()
        self._toast("已保存: %s" % os.path.basename(self.notes_path))

    def on_notes_open(self):
        tk, ttk, messagebox, filedialog, _ = self._need_tk()
        path = filedialog.askopenfilename(
            title="打开文本文件",
            filetypes=[("文本/Markdown/Python", "*.txt *.md *.py"),
                       ("文本文件", "*.txt"), ("Markdown", "*.md"),
                       ("Python", "*.py")])
        if not path:
            return
        if self._notes_content().strip():
            if not self._ask("确认", "当前内容将被替换（不会写入原文件），继续打开？"):
                return
        self.notes_path = path
        self.settings["notes_last_file"] = path
        paths.save_settings(self.settings)
        self._notes_load(path)
        self._update_notes_label()
        self._toast("已打开: %s" % os.path.basename(path))

    def on_notes_back_default(self):
        if self.notes_path != NOTES_FILE:
            ans = self._ask3("返回默认便签",
                             "当前编辑: %s\n是否先保存当前内容？\n"
                             "是 = 保存并返回   否 = 不保存直接返回   取消 = 留在当前"
                             % os.path.basename(self.notes_path))
            if ans is None:
                return
            if ans:
                self._save_notes()
        self.notes_path = NOTES_FILE
        self.settings["notes_last_file"] = NOTES_FILE
        paths.save_settings(self.settings)
        self._notes_load(NOTES_FILE)
        self._update_notes_label()
        self._toast("已回到默认便签")

    def on_notes_saveas(self):
        tk, ttk, messagebox, filedialog, _ = self._need_tk()
        path = filedialog.asksaveasfilename(
            title="另存便签为", defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("Markdown", "*.md"),
                       ("所有文件", "*.*")],
            initialfile="便签.txt")
        if not path:
            return
        try:
            save_text_file(path, self._notes_content())
            self._toast("已保存到: %s" % os.path.basename(path))
        except Exception as e:
            self._err("保存失败: %s" % e)

    def on_notes_help(self):
        self._info(NOTES_HELP)

    def _notes_on_key(self, ev):
        if self._notes_render_job:
            try:
                self.root.after_cancel(self._notes_render_job)
            except Exception:
                pass
        self._notes_render_job = self.root.after(400, self._notes_render)
        self._draw_line_numbers()

    # ---------- Markdown / LaTeX 渲染 ----------
    def _notes_render(self):
        try:
            content = self._notes_content()
            if self.md_var.get():
                render_md.apply_markdown(self.notes_text, content)
            else:
                for tag in MD_TAGS:
                    try:
                        self.notes_text.tag_remove(tag, "1.0", "end")
                    except Exception:
                        pass
            # LaTeX 片段: 打 tag 并绑定悬停提示
            try:
                self.notes_text.tag_remove("latex", "1.0", "end")
                for start, end, expr, disp in render_latex.find_latex_spans(content):
                    self.notes_text.tag_add("latex", "1.0+%dc" % start,
                                            "1.0+%dc" % end)
            except Exception:
                pass
        except Exception:
            pass

    def _latex_hover(self, event):
        try:
            idx = self.notes_text.index("@%d,%d" % (event.x, event.y))
            ranges = self.notes_text.tag_ranges("latex")
            for i in range(0, len(ranges), 2):
                if (self.notes_text.compare(ranges[i], "<=", idx)
                        and self.notes_text.compare(idx, "<=", ranges[i + 1])):
                    s = self.notes_text.get(ranges[i], ranges[i + 1]).strip()
                    if s.startswith("$$"):
                        expr, disp = s[2:-2], True
                    else:
                        expr, disp = s[1:-1], False
                    self._show_latex_tooltip(event, expr, disp)
                    break
        except Exception:
            pass

    def _latex_leave(self, event):
        # 鼠标离开 LaTeX 片段时延迟隐藏(移入提示框时不闪烁)
        try:
            if self._latex_hide_job:
                self.root.after_cancel(self._latex_hide_job)
            self._latex_hide_job = self.root.after(400, self._hide_latex_tooltip)
        except Exception:
            pass

    def _show_latex_tooltip(self, event, expr, disp):
        try:
            photo, size, error = render_latex.tooltip_png(expr, disp)
            if photo is None:
                self._err("LaTeX 渲染失败：%s\n表达式: %s" % (error or "未知错误",
                                                           expr[:60]))
                return
            tk, _, _, _, _ = self._need_tk()
            if getattr(self, "_latex_win", None) is not None:
                try:
                    self._latex_win.destroy()
                except Exception:
                    pass
            self._latex_win = tk.Toplevel(self.root)
            self._latex_win.overrideredirect(True)
            self._latex_win.attributes("-topmost", True)
            self._latex_photo = photo
            tk.Label(self._latex_win, image=photo, bg="#fbfcfd",
                     bd=1, relief="solid").pack()
            x = self.root.winfo_pointerx() + 14
            y = self.root.winfo_pointery() + 14
            self._latex_win.geometry("+%d+%d" % (x, y))
            self._latex_win.after(6000, self._hide_latex_tooltip)
        except Exception:
            pass

    def _hide_latex_tooltip(self):
        try:
            if getattr(self, "_latex_win", None) is not None:
                self._latex_win.destroy()
                self._latex_win = None
        except Exception:
            pass

    # ---------- 输入辅助 ----------
    def _ask_str(self, title, prompt):
        tk, ttk, _, _, _ = self._need_tk()
        d = tk.Toplevel(self.root)
        d.title(title)
        d.geometry("360x140")
        d.transient(self.root)
        d.grab_set()
        ttk.Label(d, text=prompt).pack(pady=(12, 2))
        var = tk.StringVar()
        e = tk.Entry(d, textvariable=var, font=("Microsoft YaHei UI", 10))
        e.pack(fill="x", padx=14)
        e.focus_set()
        result = [None]

        def ok():
            result[0] = var.get().strip()
            d.destroy()

        b = ttk.Frame(d)
        b.pack(pady=8)
        ttk.Button(b, text="确定", command=ok).pack(side="left", padx=4)
        ttk.Button(b, text="取消", command=d.destroy).pack(side="left", padx=4)
        d.bind("<Return>", lambda e: ok())
        d.bind("<Escape>", lambda e: d.destroy())
        self.root.wait_window(d)
        return result[0]
