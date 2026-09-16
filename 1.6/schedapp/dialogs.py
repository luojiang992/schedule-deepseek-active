# -*- coding: utf-8 -*-
"""对话框: 添加/修改日程(模板/快捷时间DIY/偏移分钟) / 子日程 / 详情 / 设置"""
import os
import datetime

from . import model, paths
from .model import (parse_dt, validate_dates, fmt_remain, new_task, new_child,
                    update_task, get_children, REPEAT_CODES, flag_markers,
                    classify, make_template_from, load_templates, save_templates,
                    load_quicktimes, save_quicktimes, apply_quicktime,
                    is_minute_offset, resolve_deadline, CAT_LABEL, REPEAT_NAMES)
from .paths import HOTKEY_PRESETS, DEFAULT_SYMBOL_ROWS, MAX_BG_SIZE, DATA_DIR


def need_tk():
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog, colorchooser
    return tk, ttk, messagebox, filedialog, colorchooser


class AddDialog:
    """添加/修改日程: 模板列表(DIY) + 快捷时间(可 DIY) + 事件偏移分钟 + 开始/截止联动"""

    def __init__(self, app, task=None, template=False):
        tk, ttk, _, _, _ = need_tk()
        self.app = app
        self.task = task
        self.template = template
        self.win = tk.Toplevel(app.root)
        self.win.title("从历史复制为新日程" if template
                       else ("修改日程" if task else "添加日程"))
        self.win.transient(app.root)
        self.win.grab_set()
        self.win.minsize(app.sz(560), app.sz(420))
        self.win.geometry("")      # 自动按内容调整大小, 保证按钮可见

        frm = ttk.Frame(self.win, padding=12)
        frm.pack(fill="both", expand=True)

        # 模板列表(DIY)
        trow = ttk.Frame(frm)
        trow.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        ttk.Label(trow, text="模板:").pack(side="left")
        self.tmpl_var = tk.StringVar()
        self.tmpl_box = ttk.Combobox(trow, textvariable=self.tmpl_var,
                                     state="readonly", width=24)
        self.tmpl_box.pack(side="left", padx=4)
        self._reload_tmpl_list()
        self.tmpl_box.bind("<<ComboboxSelected>>", lambda e: self._apply_template())
        ttk.Button(trow, text="💾 存为模板", command=self._save_as_template).pack(side="left", padx=4)
        ttk.Button(trow, text="🗑 删模板", command=self._delete_template).pack(side="left", padx=4)
        ttk.Button(trow, text="管理快捷时间", command=self._manage_quicktimes).pack(side="right")

        ttk.Label(frm, text="标题 *").grid(row=1, column=0, sticky="w")
        self.title = tk.Entry(frm, font=("Microsoft YaHei UI", 10))
        self.title.grid(row=1, column=1, sticky="ew", pady=3)
        self.title.focus_set()

        ttk.Label(frm, text="备注").grid(row=2, column=0, sticky="nw")
        self.note = tk.Text(frm, height=3, font=("Microsoft YaHei UI", 10))
        self.note.grid(row=2, column=1, sticky="ew", pady=3)

        ttk.Label(frm, text="开始时间").grid(row=3, column=0, sticky="w")
        self.start = tk.Entry(frm, font=("Microsoft YaHei UI", 10))
        self.start.grid(row=3, column=1, sticky="ew", pady=3)
        self.start.bind("<KeyRelease>", lambda e: self._update_hint())

        ttk.Label(frm, text="截止时间").grid(row=4, column=0, sticky="w")
        self.deadline = tk.Entry(frm, font=("Microsoft YaHei UI", 10))
        self.deadline.grid(row=4, column=1, sticky="ew", pady=3)
        self.deadline.bind("<KeyRelease>", lambda e: self._update_hint())
        ttk.Label(frm, text="格式 2026-08-30 18:00；设开始时间即「事件」；"
                            "截止填纯数字(如 150)=开始后 150 分钟；快捷时间作用于光标所在字段",
                  foreground=app.c("fg_done")).grid(row=5, column=1, sticky="w")
        self.hint = tk.Label(frm, text="", fg="#2e86c1", bg=app.c("bg"))
        self.hint.grid(row=6, column=1, sticky="w")

        # 快捷时间(DIY, 作用于光标所在字段)
        quick = ttk.Frame(frm)
        quick.grid(row=7, column=1, sticky="w", pady=(2, 0))
        self.quick_items = load_quicktimes()
        self._build_quick_row(quick)
        self.quick_frame = quick

        ttk.Label(frm, text="周期").grid(row=8, column=0, sticky="w")
        self.repeat_var = tk.StringVar(value="不重复")
        self.repeat_box = ttk.Combobox(frm, textvariable=self.repeat_var,
                                       state="readonly", width=12,
                                       values=list(REPEAT_CODES.keys()))
        self.repeat_box.grid(row=8, column=1, sticky="w", pady=3)
        ttk.Label(frm, text="周期日程到期后自动推进到下一周期",
                  foreground=app.c("fg_done")).grid(row=9, column=1, sticky="w")

        self.err = tk.Label(frm, text="", fg="#c0392b", bg=app.c("bg"))
        self.err.grid(row=10, column=0, columnspan=2, sticky="w", pady=(4, 0))

        btns = ttk.Frame(frm)
        btns.grid(row=11, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="保存为常规日程" if template
                   else ("保存修改" if task else "保存"),
                   command=self._save).pack(side="left", padx=4)
        ttk.Button(btns, text="取消", command=self.win.destroy).pack(side="left", padx=4)

        frm.columnconfigure(1, weight=1)
        self.win.bind("<Return>", lambda e: self._save())
        self.win.bind("<Escape>", lambda e: self.win.destroy())

        if task:
            self.title.insert(0, task.get("title", ""))
            self.note.insert("1.0", task.get("note", ""))
            if task.get("start"):
                self.start.insert(0, task["start"])
            if task.get("deadline"):
                self.deadline.insert(0, task["deadline"])
            rp = task.get("repeat")
            self.repeat_var.set(next((k for k, v in REPEAT_CODES.items() if v == rp),
                                     "不重复"))
        self._update_hint()

    # ---------- 模板 ----------
    def _reload_tmpl_list(self):
        self.templates = load_templates()
        names = [t.get("name", "未命名") for t in self.templates]
        try:
            self.tmpl_box.configure(values=names)
        except Exception:
            pass

    def _apply_template(self):
        name = self.tmpl_var.get()
        t = next((x for x in self.templates if x.get("name") == name), None)
        if not t:
            return
        self.title.delete(0, "end")
        self.title.insert(0, t.get("title", ""))
        self.note.delete("1.0", "end")
        self.note.insert("1.0", t.get("note", ""))
        self.start.delete(0, "end")
        if t.get("start"):
            self.start.insert(0, t["start"])
        self.deadline.delete(0, "end")
        if t.get("deadline"):
            self.deadline.insert(0, t["deadline"])
        self.repeat_var.set(next((k for k, v in REPEAT_CODES.items()
                                  if v == t.get("repeat")), "不重复"))

    def _save_as_template(self):
        name = self._ask_str("存为模板", "模板名称:")
        if not name:
            return
        self.templates = [t for t in load_templates() if t.get("name") != name]
        self.templates.append({
            "name": name,
            "title": self.title.get().strip(),
            "note": self.note.get("1.0", "end").strip(),
            "start": self.start.get().strip() or None,
            "deadline": self.deadline.get().strip() or None,
            "repeat": REPEAT_CODES.get(self.repeat_var.get()),
        })
        save_templates(self.templates)
        self._reload_tmpl_list()
        self.tmpl_var.set(name)
        self.app._toast("已保存模板: %s" % name)

    def _delete_template(self):
        name = self.tmpl_var.get()
        if not name:
            return
        self.templates = [t for t in load_templates() if t.get("name") != name]
        save_templates(self.templates)
        self._reload_tmpl_list()
        self.tmpl_var.set("")

    # ---------- 快捷时间(DIY) ----------
    def _build_quick_row(self, frame):
        for child in frame.winfo_children():
            child.destroy()
        for qt in self.quick_items:
            ttk.Button(frame, text=qt.get("label", "?"), width=10,
                       command=lambda q=qt: self._quick(q)).pack(
                side="left", padx=2, pady=1)

    def _manage_quicktimes(self):
        tk, ttk, _, _, _ = need_tk()
        d = tk.Toplevel(self.win)
        d.title("管理快捷时间")
        d.geometry("%dx%d" % (self.app.sz(440), self.app.sz(360)))
        d.transient(self.win)
        d.grab_set()
        lb = tk.Listbox(d, font=("Microsoft YaHei UI", 10))
        lb.pack(fill="both", expand=True, padx=8, pady=6)
        for qt in self.quick_items:
            lb.insert("end", qt.get("label", "?"))
        row = ttk.Frame(d)
        row.pack(fill="x", padx=8, pady=4)
        name_e = tk.Entry(row, width=12)
        name_e.pack(side="left", padx=2)
        ttk.Label(row, text="天/周几/月末:").pack(side="left")
        kind_e = ttk.Combobox(row, values=["days", "weekday", "month_end"],
                              width=10)
        kind_e.set("days")
        kind_e.pack(side="left", padx=2)
        hh = tk.Entry(row, width=4)
        hh.insert(0, "9")
        hh.pack(side="left", padx=1)
        mm = tk.Entry(row, width=4)
        mm.insert(0, "0")
        mm.pack(side="left", padx=1)
        ttk.Label(row, text="时:分").pack(side="left")

        def add():
            label = name_e.get().strip()
            if not label:
                return
            self.quick_items.append({"label": label, "kind": kind_e.get(),
                                     "delta": 0, "hour": int(hh.get() or 9),
                                     "minute": int(mm.get() or 0)})
            save_quicktimes(self.quick_items)
            lb.insert("end", label)
            name_e.delete(0, "end")
            self._build_quick_row(self.quick_frame)

        def remove():
            sel = lb.curselection()
            if sel:
                del self.quick_items[sel[0]]
                save_quicktimes(self.quick_items)
                lb.delete(sel[0])
                self._build_quick_row(self.quick_frame)

        brow = ttk.Frame(d)
        brow.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Button(brow, text="添加", command=add).pack(side="left", padx=4)
        ttk.Button(brow, text="删除选中", command=remove).pack(side="left", padx=4)
        ttk.Button(brow, text="恢复默认", command=self._reset_quicktimes).pack(side="left", padx=4)
        ttk.Button(brow, text="关闭", command=d.destroy).pack(side="right", padx=4)

    def _reset_quicktimes(self):
        self.quick_items = [dict(x) for x in model.DEFAULT_QUICKTIMES]
        save_quicktimes(self.quick_items)
        self._build_quick_row(self.quick_frame)

    def _quick(self, qt):
        d = apply_quicktime(qt)
        text = d.strftime("%Y-%m-%d %H:%M")
        target = self._focused_date_field()
        target.delete(0, "end")
        target.insert(0, text)
        self._update_hint()

    def _focused_date_field(self):
        w = self.win.focus_get()
        if w is self.start:
            return self.start
        if w is self.deadline:
            return self.deadline
        return self.deadline

    # ---------- 校验与保存 ----------
    def _update_hint(self):
        st = self.start.get().strip()
        dl = self.deadline.get().strip()
        if not dl and not st:
            self.hint.configure(text="")
            return
        if dl and not is_minute_offset(dl) and parse_dt(dl) is None:
            self.hint.configure(text="截止时间格式不正确（或填纯数字=相对开始偏移分钟）")
            return
        resolved, note = resolve_deadline(st, dl)
        if note:
            self.hint.configure(text="%s → %s" % (note, resolved))
        elif dl:
            self.hint.configure(text="距截止还有 %s" % fmt_remain(dl))
        else:
            self.hint.configure(text="已设开始时间（事件，截止可填偏移分钟）")

    def _save(self):
        title = self.title.get().strip()
        if not title:
            self.err.configure(text="标题不能为空！")
            return
        st = self.start.get().strip() or None
        dl = self.deadline.get().strip() or None
        dl, _ = resolve_deadline(st, dl)
        ok, msg = validate_dates(st, dl)
        if not ok:
            self.err.configure(text=msg)
            return
        repeat = REPEAT_CODES.get(self.repeat_var.get())
        if self.template:
            nt = make_template_from(self.task)
            nt["start"] = st
            nt["deadline"] = dl
            self.app.tasks.append(nt)
        elif self.task is None:
            t = new_task(title, note=self.note.get("1.0", "end").strip(),
                         deadline=dl, repeat=repeat, start=st)
            self.app.tasks.append(t)
        else:
            update_task(self.task, title, self.note.get("1.0", "end").strip(),
                        dl, repeat=repeat, start=st)
        model.save_tasks(self.app.tasks)
        self.app.refresh_all()
        self.win.destroy()

    def _ask_str(self, title, prompt):
        tk, ttk, _, _, _ = need_tk()
        d = tk.Toplevel(self.win)
        d.title(title)
        d.geometry("360x140")
        d.transient(self.win)
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
        self.win.wait_window(d)
        return result[0]


class AddChildDialog:
    """添加子日程对话框（单层不可嵌套）"""

    def __init__(self, app, parent):
        tk, ttk, _, _, _ = need_tk()
        self.app = app
        self.parent = parent
        self.win = tk.Toplevel(app.root)
        self.win.title("添加子日程")
        self.win.transient(app.root)
        self.win.grab_set()
        self.win.minsize(app.sz(380), app.sz(160))
        self.win.geometry("")      # 自动按内容调整大小
        frm = ttk.Frame(self.win, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="父日程: %s" % parent.get("title", "")).pack(anchor="w")
        self.title = tk.Entry(frm, font=("Microsoft YaHei UI", 10))
        self.title.pack(fill="x", pady=6)
        self.title.focus_set()
        ttk.Label(frm, text="子日程为单层结构，不能再包含子日程。",
                  foreground=app.c("fg_done")).pack(anchor="w")
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="保存", command=self._save).pack(side="right", padx=4)
        ttk.Button(btns, text="取消", command=self.win.destroy).pack(side="right", padx=4)
        self.win.bind("<Return>", lambda e: self._save())
        self.win.bind("<Escape>", lambda e: self.win.destroy())

    def _save(self):
        title = self.title.get().strip()
        if not title:
            return
        self.parent.setdefault("children", []).append(new_child(title))
        model.save_tasks(self.app.tasks)
        self.app.refresh_all()
        self.win.destroy()


class DetailDialog:
    """日程详情（只读, 含事件时间/周期/标记/子日程）"""

    def __init__(self, parent, task, dpi_scale=1.0):
        tk, ttk, _, _, _ = need_tk()
        self.win = tk.Toplevel(parent)
        self.win.title("日程详情")
        self.win.geometry("%dx%d" % (int(560 * dpi_scale), int(430 * dpi_scale)))
        self.win.transient(parent)
        self.win.grab_set()
        st = classify(task)
        rp = task.get("repeat")
        fm = flag_markers(task)
        lines = [
            ("标题", task.get("title", "")),
            ("状态", CAT_LABEL.get(st, "进行中") + ("（未完成已过期）" if st == "expired" else "")),
            ("开始时间", model.fmt_dt(task.get("start")) if task.get("start") else "—"),
            ("截止时间", model.fmt_dt(task.get("deadline")) if task.get("deadline") else "—"),
            ("剩余时间", fmt_remain(task.get("deadline"))),
            ("周期", REPEAT_NAMES.get(rp, "不重复") if rp else "不重复"),
            ("标记", fm or "无"),
            ("备注", task.get("note") or "（无）"),
            ("创建时间", model.fmt_dt(task.get("created_at"))),
            ("完成时间", model.fmt_dt(task.get("completed_at")) if task.get("completed_at") else "—"),
            ("作废时间", model.fmt_dt(task.get("cancelled_at")) if task.get("cancelled_at") else "—"),
        ]
        kids = get_children(task)
        if kids:
            lines.append(("子日程(%d)" % len(kids),
                          "\n".join(("✓ " if c.get("done") else "○ ") + c.get("title", "")
                                    for c in kids)))
        frm = ttk.Frame(self.win, padding=14)
        frm.pack(fill="both", expand=True)
        for i, (k, v) in enumerate(lines):
            ttk.Label(frm, text=k, font=("Microsoft YaHei UI", 9, "bold")).grid(
                row=i, column=0, sticky="nw", pady=2, padx=(0, 10))
            ttk.Label(frm, text=v, wraplength=380, justify="left").grid(
                row=i, column=1, sticky="nw", pady=2)
        ttk.Button(frm, text="关闭", command=self.win.destroy).grid(
            row=len(lines), column=1, sticky="e", pady=(12, 0))


class SettingsDialog:
    """设置中心: 外观/半透明/背景/热键/符号DIY/常规/数据"""

    def __init__(self, app, symbols_tab=False):
        tk, ttk, _, _, _ = need_tk()
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title("设置")
        self.win.geometry("%dx%d" % (app.sz(640), app.sz(580)))
        self.win.transient(app.root)
        self.win.grab_set()
        self.dark_var = tk.BooleanVar(value=app.dark)
        self.autostart_var = tk.BooleanVar(value=app.settings.get("autostart"))
        self.tray_var = tk.BooleanVar(value=app.settings.get("minimize_to_tray"))
        self.alpha_var = tk.DoubleVar(value=float(app.settings.get("window_alpha", 0.92)))
        self.sym_hk_var = tk.StringVar(value=app.settings.get("symbol_hotkey", "Ctrl+Shift+G"))
        self.snip_hk_var = tk.StringVar(value=app.settings.get("snippet_hotkey", "Ctrl+Shift+S"))

        nb = ttk.Notebook(self.win)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        p1 = ttk.Frame(nb, padding=12)
        nb.add(p1, text="外观")
        ttk.Checkbutton(p1, text="深色模式", variable=self.dark_var,
                        command=self._on_dark).pack(anchor="w", pady=(0, 4))
        alpha_row = ttk.Frame(p1)
        alpha_row.pack(fill="x", pady=4)
        ttk.Label(alpha_row, text="半透明:").pack(side="left")
        ttk.Scale(alpha_row, from_=0.7, to=1.0, variable=self.alpha_var,
                  command=self._on_alpha).pack(side="left", fill="x", expand=True, padx=6)
        self.alpha_lbl = ttk.Label(alpha_row, text="%d%%" % int(self.alpha_var.get() * 100))
        self.alpha_lbl.pack(side="left")
        bgrow = ttk.Frame(p1)
        bgrow.pack(fill="x", pady=4)
        ttk.Label(bgrow, text="背景图片:").pack(side="left")
        ttk.Button(bgrow, text="选择图片…", command=self._on_bg_pick).pack(side="left", padx=4)
        ttk.Button(bgrow, text="移除背景", command=self._on_bg_remove).pack(side="left", padx=4)
        ttk.Label(p1, text="≤8MB；背景图在主窗口后方完整不透明显示，半透明面板将其透出",
                  foreground=app.c("fg_done")).pack(anchor="w")

        p2 = ttk.Frame(nb, padding=12)
        nb.add(p2, text="符号 / 句子")
        ttk.Label(p2, text="符号小窗全局热键:").pack(anchor="w")
        ttk.Combobox(p2, textvariable=self.sym_hk_var, state="readonly", width=14,
                     values=list(HOTKEY_PRESETS.keys())).pack(anchor="w", pady=(2, 6))
        ttk.Label(p2, text="句子粘贴板全局热键:").pack(anchor="w")
        ttk.Combobox(p2, textvariable=self.snip_hk_var, state="readonly", width=14,
                     values=list(HOTKEY_PRESETS.keys())).pack(anchor="w", pady=(2, 6))
        ttk.Button(p2, text="应用热键", command=self._on_hotkeys).pack(anchor="w", pady=4)
        ttk.Label(p2, text="自定义符号列表（每行一组，直接输入字符）:").pack(anchor="w", pady=(6, 2))
        self.symbols_text = tk.Text(p2, height=6, font=("Segoe UI", 12))
        self.symbols_text.pack(fill="x")
        for row in model.load_symbol_rows():
            self.symbols_text.insert("end", row + "\n")
        srow = ttk.Frame(p2)
        srow.pack(fill="x", pady=4)
        ttk.Button(srow, text="保存符号列表", command=self._on_symbols_save).pack(side="left", padx=4)
        ttk.Button(srow, text="恢复默认", command=self._on_symbols_reset).pack(side="left", padx=4)

        p3 = ttk.Frame(nb, padding=12)
        nb.add(p3, text="常规")
        ttk.Checkbutton(p3, text="开机自启动（失败时自动请求管理员权限）",
                        variable=self.autostart_var,
                        command=self._on_autostart).pack(anchor="w", pady=4)
        ttk.Checkbutton(p3, text="关闭时最小化到托盘（托盘可恢复/退出）",
                        variable=self.tray_var,
                        command=self._on_tray).pack(anchor="w", pady=(0, 4))

        p4 = ttk.Frame(nb, padding=12)
        nb.add(p4, text="数据")
        drow = ttk.Frame(p4)
        drow.pack(fill="x", pady=4)
        ttk.Button(drow, text="导出历史为 CSV", command=self._on_export).pack(side="left", padx=(0, 8))
        ttk.Button(drow, text="打开数据文件夹", command=self._on_open_dir).pack(side="left")
        ttk.Label(p4, text="数据文件夹: %s" % DATA_DIR, wraplength=560,
                  foreground=app.c("fg_done")).pack(anchor="w", pady=(6, 0))

        btns = ttk.Frame(self.win)
        btns.pack(fill="x", padx=12, pady=(0, 10))
        ttk.Label(btns, text="版本 v%s" % paths.VERSION,
                  foreground=app.c("fg_done")).pack(side="left")
        ttk.Button(btns, text="关闭", command=self.win.destroy).pack(side="right")

        if symbols_tab:
            nb.select(1)

    def _on_dark(self):
        self.app.settings["dark"] = self.dark_var.get()
        paths.save_settings(self.app.settings)
        self.app.apply_theme()
        self.app.refresh_all()

    def _on_alpha(self, _=None):
        v = max(0.7, min(1.0, self.alpha_var.get()))
        self.alpha_lbl.configure(text="%d%%" % int(v * 100))
        self.app.settings["window_alpha"] = v
        paths.save_settings(self.app.settings)
        self.app._apply_alpha()

    def _on_hotkeys(self):
        self.app.settings["symbol_hotkey"] = self.sym_hk_var.get()
        self.app.settings["snippet_hotkey"] = self.snip_hk_var.get()
        paths.save_settings(self.app.settings)
        self.app.apply_hotkeys()
        self.app._toast("热键已应用")

    def _on_symbols_save(self):
        rows = [ln.rstrip() for ln in self.symbols_text.get("1.0", "end-1c").split("\n")
                if ln.strip()]
        model.save_symbol_rows(rows)
        self.app._toast("符号列表已保存")

    def _on_symbols_reset(self):
        self.symbols_text.delete("1.0", "end")
        for row in DEFAULT_SYMBOL_ROWS:
            self.symbols_text.insert("end", row + "\n")
        model.save_symbol_rows(list(DEFAULT_SYMBOL_ROWS))
        self.app._toast("已恢复默认符号列表")

    def _on_autostart(self):
        from . import winapi
        enabled = self.autostart_var.get()
        self.app.settings["autostart"] = enabled
        paths.save_settings(self.app.settings)
        try:
            winapi.set_autostart(enabled)
            if winapi.get_autostart() == enabled:
                self.app._toast("开机自启动已%s" % ("开启" if enabled else "关闭"))
                return
        except Exception:
            pass
        winapi.elevate_autostart(enabled)
        self.app._info("已请求管理员权限完成开机自启动设置（请在 UAC 窗口中确认）。\n"
                       "提示：若注册表被组策略锁定，可右键以管理员身份运行本程序后再设置。")

    def _on_tray(self):
        self.app.settings["minimize_to_tray"] = self.tray_var.get()
        paths.save_settings(self.app.settings)

    def _on_bg_pick(self):
        tk, ttk, messagebox, filedialog, _ = need_tk()
        path = filedialog.askopenfilename(
            title="选择背景图片",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
                       ("所有文件", "*.*")])
        if not path:
            return
        try:
            if os.path.getsize(path) > MAX_BG_SIZE:
                self.app._err("图片过大（>8MB），请换一张。")
                return
            from PIL import Image
            img = Image.open(path)
            img.load()
            target = os.path.join(DATA_DIR, "background.png")
            img.convert("RGBA").save(target)
            self.app.settings["background"] = target
            paths.save_settings(self.app.settings)
            self.app._render_bg()
            self.app._toast("背景已应用")
        except Exception as e:
            self.app._err("无法加载该图片: %s" % e)

    def _on_bg_remove(self):
        self.app.settings["background"] = None
        paths.save_settings(self.app.settings)
        self.app._hide_bg_win()
        try:
            os.remove(os.path.join(DATA_DIR, "background.png"))
        except Exception:
            pass

    def _on_export(self):
        self.app.on_export_csv()

    def _on_open_dir(self):
        try:
            os.startfile(DATA_DIR)
        except Exception:
            pass
