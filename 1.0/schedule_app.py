# -*- coding: utf-8 -*-
"""
轻量级桌面日程管理软件（单文件版）
==================================
- 数据: 本地 JSON（默认 %APPDATA%\\DeepSeekSchedule\\schedule.json，可用 --data-dir 覆盖）
- 界面: tkinter（仅标准库，无第三方依赖）
- 视图: 「进行中」/「历史」两个主视图
- 历史: ✅已完成 / 🚫作废 / ⏰已过期 三类，支持按类别与日期范围筛选、彻底删除、导出 CSV

命令行（供测试/便携使用）:
    python schedule_app.py                 # 正常启动图形界面
    python schedule_app.py --data-dir DIR  # 数据目录指向 DIR（便携模式）
    python schedule_app.py --selftest      # 只跑存储/分类逻辑自测，不开界面
    python schedule_app.py --smoke         # 构建界面后 1.5 秒自动关闭（冒烟测试）
"""

import os
import sys
import json
import uuid
import datetime
import shutil

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

APP_NAME = "日程管理"
VERSION = "1.0.0"

# PyInstaller 冻结（打包）运行时: 注入随包带入的 tcl/tk 运行时路径，
# 必须在 import tkinter 之前设置（本程序 tkinter 为懒加载，此处安全）。
if getattr(sys, "frozen", False):
    _base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    os.environ.setdefault("TCL_LIBRARY", os.path.join(_base, "tcl"))
    os.environ.setdefault("TK_LIBRARY", os.path.join(_base, "tk"))

# ============================================================
# 一、数据存储
# ============================================================

def get_data_dir():
    """数据目录解析：--data-dir > %APPDATA%\\DeepSeekSchedule > 程序同目录"""
    if "--data-dir" in sys.argv:
        i = sys.argv.index("--data-dir")
        if i + 1 < len(sys.argv):
            return os.path.abspath(sys.argv[i + 1])
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "DeepSeekSchedule")
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".write_probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return d
    except Exception:
        # APPDATA 不可写时退回程序所在目录（PyInstaller 单文件模式下为临时目录，
        # 极少触发；正常 Windows 用户目录均可写）
        return os.path.dirname(os.path.abspath(__file__))


DATA_FILE = os.path.join(get_data_dir(), "schedule.json")

TASK_FIELDS = ("id", "title", "note", "deadline", "created_at",
               "status", "completed_at", "cancelled_at")


def now_iso():
    return datetime.datetime.now().isoformat(timespec="minutes")


def parse_dt(text):
    """解析日期时间，支持 'YYYY-MM-DD HH:MM' / 'YYYY-MM-DD' / ISO(带 T) 等。失败返回 None"""
    if not text:
        return None
    text = str(text).strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d", "%Y/%m/%d %H:%M", "%Y/%m/%d"):
        try:
            return datetime.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def new_task(title, note="", deadline=None):
    """新建任务记录（status=active）"""
    return {
        "id": uuid.uuid4().hex,
        "title": title.strip(),
        "note": (note or "").strip(),
        "deadline": deadline,          # 形如 "2026-08-30 18:00" 或 None
        "created_at": now_iso(),
        "status": "active",            # active | done | cancelled
        "completed_at": None,
        "cancelled_at": None,
    }


def load_tasks():
    """读取 JSON；文件损坏时备份 .bak 并返回空列表"""
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return []
    except Exception:
        try:
            shutil.copy2(DATA_FILE, DATA_FILE + ".bak")
        except Exception:
            pass
        return []


def save_tasks(tasks):
    """原子写 JSON（先写临时文件再替换），人类可读（indent=2）"""
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


# ============================================================
# 二、业务逻辑（分类 / 历史）
# ============================================================

def classify(task, now=None):
    """
    返回任务当前状态:
      'done'      —— 已完成（用户主动划去）
      'cancelled' —— 已作废（用户标记取消）
      'expired'   —— 已过期（超过截止时间但未完成）
      'active'    —— 进行中
    """
    status = task.get("status", "active")
    if status != "active":
        return status
    if task.get("deadline"):
        dt = parse_dt(task["deadline"])
        if dt is not None and dt < (now or datetime.datetime.now()):
            return "expired"
    return "active"


def history_date(task):
    """历史记录归属日期：完成→完成时间；作废→作废时间；过期→截止时间"""
    if task.get("status") == "done":
        return parse_dt(task.get("completed_at"))
    if task.get("status") == "cancelled":
        return parse_dt(task.get("cancelled_at"))
    return parse_dt(task.get("deadline"))


def fmt_dt(text):
    """ISO 时间转 'YYYY-MM-DD HH:MM' 显示"""
    dt = parse_dt(text)
    return dt.strftime("%Y-%m-%d %H:%M") if dt else (text or "—")


def day_key(dt):
    return dt.strftime("%Y-%m-%d") if dt else None


# ============================================================
# 三、图形界面
# ============================================================

def need_tk():
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    return tk, ttk, messagebox, filedialog


CAT_LABEL = {"done": "✅ 已完成", "cancelled": "🚫 作废", "expired": "⏰ 已过期"}


class App:
    def __init__(self, root):
        self.root = root
        root.title("%s v%s" % (APP_NAME, VERSION))
        root.geometry("960x620")
        root.minsize(760, 500)

        self.tasks = load_tasks()
        self.dark = False

        self._build_ui()
        self.apply_theme()
        self.refresh_all()
        self._startup_remind()

    # ---------- 界面搭建 ----------
    def _build_ui(self):
        tk, ttk, _, _ = need_tk()
        self.font_base = ("Microsoft YaHei UI", 10)

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        self.nb = nb

        # --- Tab1: 进行中 ---
        self.tab_main = ttk.Frame(nb)
        nb.add(self.tab_main, text="  今日 / 进行中  ")
        bar1 = ttk.Frame(self.tab_main)
        bar1.pack(fill="x", padx=4, pady=4)
        ttk.Button(bar1, text="＋ 添加日程", command=self.on_add).pack(side="left", padx=(0, 6))
        ttk.Button(bar1, text="✓ 标记完成", command=lambda: self.on_mark("done")).pack(side="left", padx=6)
        ttk.Button(bar1, text="🚫 标记作废", command=lambda: self.on_mark("cancelled")).pack(side="left", padx=6)
        ttk.Button(bar1, text="🗑 删除", command=self.on_delete_main).pack(side="left", padx=6)
        ttk.Button(bar1, text="⟳ 刷新", command=self.refresh_main).pack(side="left", padx=6)
        self.theme_btn = ttk.Button(bar1, text="🌙 深色", command=self.toggle_theme)
        self.theme_btn.pack(side="right")

        wrap = ttk.Frame(self.tab_main)
        wrap.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        cols = ("status", "title", "deadline", "note")
        self.tree_main = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
        for cid, text, w, anchor in (
                ("status", "状态", 70, "center"),
                ("title", "标题", 280, "w"),
                ("deadline", "截止时间", 150, "center"),
                ("note", "备注", 320, "w")):
            self.tree_main.heading(cid, text=text)
            self.tree_main.column(cid, width=w, anchor=anchor, stretch=(cid == "note"))
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree_main.yview)
        self.tree_main.configure(yscrollcommand=sb.set)
        self.tree_main.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree_main.bind("<Double-1>", lambda e: self.on_detail_main())
        self.tree_main.bind("<<TreeviewSelect>>", lambda e: None)

        self.status_bar = tk.Label(self.tab_main, text="", anchor="w", font=("Microsoft YaHei UI", 9))
        self.status_bar.pack(fill="x", padx=6, pady=(0, 4))

        # --- Tab2: 历史 ---
        self.tab_hist = ttk.Frame(nb)
        nb.add(self.tab_hist, text="  历史记录  ")
        bar2 = ttk.Frame(self.tab_hist)
        bar2.pack(fill="x", padx=4, pady=4)
        ttk.Label(bar2, text="类别:").pack(side="left")
        self.hist_cat = ttk.Combobox(bar2, state="readonly", width=13,
                                     values=["全部", "✅ 已完成", "🚫 作废", "⏰ 已过期"])
        self.hist_cat.current(0)
        self.hist_cat.pack(side="left", padx=(2, 10))
        self.hist_cat.bind("<<ComboboxSelected>>", lambda e: self.refresh_hist())
        ttk.Label(bar2, text="日期:").pack(side="left")
        self.hist_range = ttk.Combobox(bar2, state="readonly", width=10,
                                       values=["全部", "今天", "昨天", "近7天", "近30天"])
        self.hist_range.current(0)
        self.hist_range.pack(side="left", padx=(2, 10))
        self.hist_range.bind("<<ComboboxSelected>>", lambda e: self.refresh_hist())
        ttk.Button(bar2, text="🗑 彻底删除", command=self.on_delete_hist).pack(side="left", padx=6)
        ttk.Button(bar2, text="⇩ 导出 CSV", command=self.on_export_csv).pack(side="left", padx=6)
        ttk.Button(bar2, text="ⓘ 详情", command=self.on_detail_hist).pack(side="left", padx=6)

        wrap2 = ttk.Frame(self.tab_hist)
        wrap2.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        cols2 = ("cat", "title", "rec_date", "deadline", "note")
        self.tree_hist = ttk.Treeview(wrap2, columns=cols2, show="headings", selectmode="browse")
        for cid, text, w, anchor in (
                ("cat", "类型", 100, "center"),
                ("title", "标题", 280, "w"),
                ("rec_date", "记录日期", 130, "center"),
                ("deadline", "截止时间", 150, "center"),
                ("note", "备注", 240, "w")):
            self.tree_hist.heading(cid, text=text)
            self.tree_hist.column(cid, width=w, anchor=anchor, stretch=(cid == "note"))
        sb2 = ttk.Scrollbar(wrap2, orient="vertical", command=self.tree_hist.yview)
        self.tree_hist.configure(yscrollcommand=sb2.set)
        self.tree_hist.pack(side="left", fill="both", expand=True)
        sb2.pack(side="right", fill="y")
        self.tree_hist.bind("<Double-1>", lambda e: self.on_detail_hist())

        # Treeview 行配色（会随主题重建）
        self._tag_trees()

    def _tag_trees(self):
        bg_n = self.c("row_normal")
        bg_soon = self.c("row_soon")
        bg_over = self.c("row_over")
        fg = self.c("fg")
        self.tree_main.tag_configure("normal", background=bg_n, foreground=fg)
        self.tree_main.tag_configure("due_soon", background=bg_soon, foreground=fg)
        self.tree_main.tag_configure("overdue", background=bg_over, foreground=fg)
        self.tree_hist.tag_configure("done", background=bg_n, foreground=self.c("fg_done"))
        self.tree_hist.tag_configure("cancelled", background=bg_n, foreground=self.c("fg_cancel"))
        self.tree_hist.tag_configure("expired", background=bg_over, foreground=fg)

    # ---------- 主题 ----------
    def c(self, key):
        """取主题颜色"""
        pal = {
            "bg": "#f4f6f7", "card": "#ffffff", "fg": "#17202a",
            "fg_done": "#7f8c8d", "fg_cancel": "#8d6e63",
            "row_normal": "#ffffff", "row_soon": "#fff3cd", "row_over": "#f8d7da",
            "accent": "#2e86c1", "select": "#d6eaf8",
        } if not self.dark else {
            "bg": "#1b222c", "card": "#232b38", "fg": "#e8ecf3",
            "fg_done": "#8a97a5", "fg_cancel": "#b39a8f",
            "row_normal": "#232b38", "row_soon": "#3f3720", "row_over": "#4a2528",
            "accent": "#4cc9f0", "select": "#2c3e50",
        }
        return pal[key]

    def apply_theme(self):
        tk, ttk, _, _ = need_tk()
        self.root.configure(bg=self.c("bg"))
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=self.c("bg"), foreground=self.c("fg"),
                        font=self.font_base)
        style.configure("TNotebook", background=self.c("bg"), borderwidth=0)
        style.configure("TNotebook.Tab", padding=(14, 7), background=self.c("card"),
                        foreground=self.c("fg"))
        style.map("TNotebook.Tab", background=[("selected", self.c("accent"))],
                  foreground=[("selected", "#ffffff")])
        style.configure("TFrame", background=self.c("bg"))
        style.configure("TButton", background=self.c("card"), foreground=self.c("fg"),
                        padding=(8, 4))
        style.map("TButton", background=[("active", self.c("select"))])
        style.configure("TLabel", background=self.c("bg"), foreground=self.c("fg"))
        style.configure("TCombobox", fieldbackground=self.c("card"),
                        foreground=self.c("fg"), background=self.c("card"))
        style.map("TCombobox", fieldbackground=[("readonly", self.c("card"))])
        style.configure("Treeview", background=self.c("row_normal"),
                        fieldbackground=self.c("row_normal"), foreground=self.c("fg"),
                        rowheight=28, borderwidth=0)
        style.map("Treeview", background=[("selected", self.c("select"))],
                  foreground=[("selected", self.c("fg"))])
        style.configure("Treeview.Heading", background=self.c("card"),
                        foreground=self.c("fg"), padding=(6, 4))
        self.status_bar.configure(bg=self.c("bg"), fg=self.c("fg"))
        self._tag_trees()
        self.theme_btn.configure(text="☀️ 浅色" if self.dark else "🌙 深色")

    def toggle_theme(self):
        self.dark = not self.dark
        self.apply_theme()
        self.refresh_all()

    # ---------- 数据刷新 ----------
    def refresh_all(self):
        self.refresh_main()
        self.refresh_hist()

    def refresh_main(self):
        now = datetime.datetime.now()
        due_soon = []
        overdue = []
        active = []
        for t in self.tasks:
            st = classify(t, now)
            if st == "active":
                active.append(t)
                if t.get("deadline"):
                    dt = parse_dt(t["deadline"])
                    if dt and dt <= now + datetime.timedelta(hours=24):
                        due_soon.append(t)
            elif st == "expired":
                overdue.append(t)
        self.tree_main.delete(*self.tree_main.get_children())
        # 进行中列表: 已过期(红) 优先, 其次按截止时间升序
        order = sorted(overdue, key=lambda t: (parse_dt(t["deadline"]) or datetime.datetime.max))
        order += sorted(active, key=lambda t: (parse_dt(t["deadline"]) or datetime.datetime.max))
        for t in order:
            tag = "overdue" if classify(t, now) == "expired" else ("due_soon" if t in due_soon else "normal")
            self.tree_main.insert("", "end", iid=t["id"], values=(
                "已过期" if tag == "overdue" else ("即将到期" if tag == "due_soon" else "进行中"),
                t["title"],
                fmt_dt(t.get("deadline")),
                t.get("note", ""),
            ), tags=(tag,))
        self.status_bar.configure(
            text="进行中 %d 项 · 今日/24h内到期 %d 项 · 已过期 %d 项"
                 % (len(active), len(due_soon), len(overdue)))

    def refresh_hist(self):
        now = datetime.datetime.now()
        cat = self.hist_cat.get()
        rng = self.hist_range.get()
        rows = []
        for t in self.tasks:
            st = classify(t, now)
            if st == "active":
                continue
            if cat == "✅ 已完成" and st != "done":
                continue
            if cat == "🚫 作废" and st != "cancelled":
                continue
            if cat == "⏰ 已过期" and st != "expired":
                continue
            d = history_date(t)
            if rng != "全部" and d is not None:
                days = (now - d).days
                ok = {"今天": days == 0, "昨天": days == 1,
                      "近7天": 0 <= days <= 7, "近30天": 0 <= days <= 30}[rng]
                if not ok:
                    continue
            rows.append((t, st, d))
        rows.sort(key=lambda r: (r[2] or datetime.datetime.min), reverse=True)
        self.tree_hist.delete(*self.tree_hist.get_children())
        for t, st, d in rows:
            self.tree_hist.insert("", "end", iid=t["id"], values=(
                CAT_LABEL[st], t["title"], fmt_dt(d.isoformat(timespec="minutes")) if d else "—",
                fmt_dt(t.get("deadline")), t.get("note", "")), tags=(st,))

    # ---------- 操作 ----------
    def _selected(self, tree):
        sel = tree.selection()
        if not sel:
            return None
        tid = sel[0]
        return next((t for t in self.tasks if t["id"] == tid), None)

    def on_add(self):
        AddDialog(self)

    def on_mark(self, status):
        t = self._selected(self.tree_main)
        if not t:
            self._info("请先在列表中选择一个日程。")
            return
        label = "完成" if status == "done" else "作废"
        if not self._ask("确认", "确定将「%s」标记为%s吗？" % (t["title"], label)):
            return
        t["status"] = status
        t["completed_at"] = now_iso() if status == "done" else t.get("completed_at")
        t["cancelled_at"] = now_iso() if status == "cancelled" else t.get("cancelled_at")
        save_tasks(self.tasks)
        self.refresh_all()

    def on_delete_main(self):
        t = self._selected(self.tree_main)
        if not t:
            self._info("请先在列表中选择一个日程。")
            return
        if self._ask("确认删除", "确定彻底删除「%s」吗？此操作不可恢复。" % t["title"]):
            self.tasks.remove(t)
            save_tasks(self.tasks)
            self.refresh_all()

    def on_delete_hist(self):
        t = self._selected(self.tree_hist)
        if not t:
            self._info("请先在历史列表中选择一条记录。")
            return
        if self._ask("确认删除", "确定彻底删除这条历史记录「%s」吗？" % t["title"]):
            self.tasks.remove(t)
            save_tasks(self.tasks)
            self.refresh_all()

    def on_detail_main(self):
        t = self._selected(self.tree_main)
        if t:
            DetailDialog(self.root, t)

    def on_detail_hist(self):
        t = self._selected(self.tree_hist)
        if t:
            DetailDialog(self.root, t)

    def on_export_csv(self):
        tk, ttk, messagebox, filedialog = need_tk()
        path = filedialog.asksaveasfilename(
            title="导出历史为 CSV", defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")], initialfile="日程历史.csv")
        if not path:
            return
        now = datetime.datetime.now()
        rows = []
        for t in self.tasks:
            st = classify(t, now)
            if st == "active":
                continue
            rows.append((CAT_LABEL[st], t["title"], t.get("note", ""),
                         fmt_dt(t.get("deadline")),
                         fmt_dt((history_date(t).isoformat(timespec="minutes")
                                 if history_date(t) else "")),
                         t.get("created_at", "")))
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                import csv
                w = csv.writer(f)
                w.writerow(["类型", "标题", "备注", "截止时间", "记录日期", "创建时间"])
                w.writerows(rows)
            self._info("已导出 %d 条历史记录到:\n%s" % (len(rows), path))
        except Exception as e:
            self._err("导出失败: %s" % e)

    def _startup_remind(self):
        now = datetime.datetime.now()
        expired = [t for t in self.tasks if classify(t, now) == "expired"]
        due_today = [t for t in self.tasks
                     if classify(t, now) == "active" and t.get("deadline")
                     and day_key(parse_dt(t["deadline"])) == day_key(now)]
        if expired or due_today:
            self._info("今日提醒\n\n已过期未完成: %d 项\n今日到期: %d 项\n"
                       "（详见「进行中」视图红色/黄色条目）" % (len(expired), len(due_today)))

    # ---------- 弹窗 ----------
    def _ask(self, title, msg):
        _, _, messagebox, _ = need_tk()
        return messagebox.askyesno(title, msg, parent=self.root)

    def _info(self, msg):
        _, _, messagebox, _ = need_tk()
        messagebox.showinfo(APP_NAME, msg, parent=self.root)

    def _err(self, msg):
        _, _, messagebox, _ = need_tk()
        messagebox.showerror(APP_NAME, msg, parent=self.root)


class AddDialog:
    """添加日程对话框"""

    def __init__(self, app):
        tk, ttk, _, _ = need_tk()
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title("添加日程")
        self.win.geometry("460x330")
        self.win.transient(app.root)
        self.win.grab_set()

        frm = ttk.Frame(self.win, padding=12)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="标题 *").grid(row=0, column=0, sticky="w")
        self.title = tk.Entry(frm, font=("Microsoft YaHei UI", 10))
        self.title.grid(row=0, column=1, sticky="ew", pady=3)
        self.title.focus_set()

        ttk.Label(frm, text="备注").grid(row=1, column=0, sticky="nw")
        self.note = tk.Text(frm, height=3, font=("Microsoft YaHei UI", 10))
        self.note.grid(row=1, column=1, sticky="ew", pady=3)

        ttk.Label(frm, text="截止时间").grid(row=2, column=0, sticky="w")
        self.deadline = tk.Entry(frm, font=("Microsoft YaHei UI", 10))
        self.deadline.grid(row=2, column=1, sticky="ew", pady=3)
        ttk.Label(frm, text="格式: 2026-08-30 18:00（可留空 = 无截止）",
                  foreground=app.c("fg_done")).grid(row=3, column=1, sticky="w")

        quick = ttk.Frame(frm)
        quick.grid(row=4, column=1, sticky="w", pady=(2, 0))
        for label, delta in (("今天 09:00", 0), ("今天 18:00", 1),
                             ("明天 09:00", 2), ("清除", -1)):
            ttk.Button(quick, text=label, width=9,
                       command=lambda d=delta: self._quick(d)).pack(side="left", padx=2)

        self.err = tk.Label(frm, text="", fg="#c0392b", bg=app.c("bg"))
        self.err.grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 0))

        btns = ttk.Frame(frm)
        btns.grid(row=6, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="保存", command=self._save).pack(side="left", padx=4)
        ttk.Button(btns, text="取消", command=self.win.destroy).pack(side="left", padx=4)

        frm.columnconfigure(1, weight=1)
        self.win.bind("<Return>", lambda e: self._save())
        self.win.bind("<Escape>", lambda e: self.win.destroy())

    def _quick(self, delta):
        if delta < 0:
            self.deadline.delete(0, "end")
            return
        d = datetime.datetime.now() + datetime.timedelta(days=delta)
        d = d.replace(hour=9 if delta == 0 else 9 if delta == 0 else (9 if delta == 2 else 18),
                      minute=0, second=0, microsecond=0)
        # 语义: 0/2 -> 9:00, 1 -> 18:00（见按钮文案）
        if delta == 1:
            d = d.replace(hour=18)
        self.deadline.delete(0, "end")
        self.deadline.insert(0, d.strftime("%Y-%m-%d %H:%M"))

    def _save(self):
        title = self.title.get().strip()
        if not title:
            self.err.configure(text="标题不能为空！")
            return
        dl = self.deadline.get().strip()
        if dl and parse_dt(dl) is None:
            self.err.configure(text="截止时间格式错误，请用 2026-08-30 18:00")
            return
        t = new_task(title, note=self.note.get("1.0", "end").strip(), deadline=dl or None)
        self.app.tasks.append(t)
        save_tasks(self.app.tasks)
        self.app.refresh_all()
        self.win.destroy()


class DetailDialog:
    """日程详情（只读）"""

    def __init__(self, parent, task):
        tk, ttk, _, _ = need_tk()
        self.win = tk.Toplevel(parent)
        self.win.title("日程详情")
        self.win.geometry("440x320")
        self.win.transient(parent)
        self.win.grab_set()
        st = classify(task)
        lines = [
            ("标题", task.get("title", "")),
            ("状态", CAT_LABEL.get(st, "进行中") + ("（未完成已过期）" if st == "expired" else "")),
            ("备注", task.get("note") or "（无）"),
            ("截止时间", fmt_dt(task.get("deadline"))),
            ("创建时间", fmt_dt(task.get("created_at"))),
            ("完成时间", fmt_dt(task.get("completed_at")) if task.get("completed_at") else "—"),
            ("作废时间", fmt_dt(task.get("cancelled_at")) if task.get("cancelled_at") else "—"),
        ]
        frm = ttk.Frame(self.win, padding=14)
        frm.pack(fill="both", expand=True)
        for i, (k, v) in enumerate(lines):
            ttk.Label(frm, text=k, font=("Microsoft YaHei UI", 9, "bold")).grid(
                row=i, column=0, sticky="nw", pady=2, padx=(0, 10))
            ttk.Label(frm, text=v, wraplength=280, justify="left").grid(
                row=i, column=1, sticky="nw", pady=2)
        ttk.Button(frm, text="关闭", command=self.win.destroy).grid(
            row=len(lines), column=1, sticky="e", pady=(12, 0))


# ============================================================
# 四、自测 / 冒烟 / 主入口
# ============================================================

def run_selftest():
    """存储与分类逻辑自测（不开界面）"""
    import tempfile
    fails = []
    def ok(name, cond, detail=""):
        print(("  ok  " if cond else "FAIL  ") + name + (("  -> " + detail) if detail else ""))
        if not cond:
            fails.append(name)

    tmp = tempfile.mkdtemp(prefix="sched_selftest_")
    global DATA_FILE
    DATA_FILE = os.path.join(tmp, "schedule.json")

    print("[1] 存储读写（人类可读 JSON）")
    tasks = [new_task("测试任务", note="备注内容", deadline="2099-01-01 09:00")]
    save_tasks(tasks)
    ok("文件已创建", os.path.exists(DATA_FILE))
    with open(DATA_FILE, encoding="utf-8") as f:
        raw = f.read()
    ok("JSON 含缩进(人类可读)", "\n  " in raw)
    ok("JSON 中文未转义", "备注内容" in raw)
    loaded = load_tasks()
    ok("重读一致", loaded == tasks, str(loaded))

    print("[2] 状态分类")
    past = new_task("已过期任务", deadline="2000-01-01 08:00")
    ok("过去截止 -> expired", classify(past) == "expired")
    future = new_task("未来任务", deadline="2099-12-31 23:59")
    ok("未来截止 -> active", classify(future) == "active")
    done = new_task("完成任务")
    done["status"] = "done"
    done["completed_at"] = now_iso()
    ok("完成 -> done", classify(done) == "done")
    canc = new_task("作废任务")
    canc["status"] = "cancelled"
    canc["cancelled_at"] = now_iso()
    ok("作废 -> cancelled", classify(canc) == "cancelled")
    no_dl = new_task("无截止")
    ok("无截止 -> active", classify(no_dl) == "active")

    print("[3] 历史归属日期")
    ok("过期任务历史日期=截止日", history_date(past) is not None)
    ok("完成任务历史日期=完成日", history_date(done) is not None)

    print("[4] 时间解析")
    ok("'2026-08-30 18:00' 可解析", parse_dt("2026-08-30 18:00") is not None)
    ok("'2026/8/3' 可解析", parse_dt("2026/8/3") is not None)
    ok("非法格式返回 None", parse_dt("随便写") is None)

    print("[5] 分类三类型齐全（含自动归入历史）")
    mix = [past, done, canc, future, no_dl]
    cats = {classify(t) for t in mix}
    ok("含 expired/done/cancelled/active", {"expired", "done", "cancelled", "active"} <= cats,
        str(cats))

    print("\n结果: %s" % ("全部通过" if not fails else "%d 项失败: %s" % (len(fails), fails)))
    return 0 if not fails else 1


def run_smoke():
    """构建界面后自动关闭（冒烟测试，验证 GUI 可正常构建）"""
    tk, ttk, _, _ = need_tk()
    root = tk.Tk()
    root.withdraw()          # 不显示窗口
    app = App(root)
    root.update_idletasks()
    root.after(1200, root.destroy)
    root.mainloop()
    print("GUI 冒烟测试通过（界面构建成功并正常关闭）")
    return 0


def main():
    if "--selftest" in sys.argv:
        sys.exit(run_selftest())
    if "--smoke" in sys.argv:
        sys.exit(run_smoke())
    tk, ttk, _, _ = need_tk()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
