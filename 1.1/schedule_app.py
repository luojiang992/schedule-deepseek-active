# -*- coding: utf-8 -*-
"""
轻量级桌面日程管理软件（单文件版）v1.1.0
========================================
新增/变更(v1.1.0):
  1. 剩余时间: 「进行中」视图实时显示距截止时间的剩余(已过)时长, 样式 X天X时X分
  2. 数据位置: JSON 直接存放在程序(exe/脚本)所在目录, 不再使用 %APPDATA%
  3. 修改功能: 进行中/已过期的日程可修改(标题/备注/截止时间)
  4. DPI 感知: 启用 Windows 每显示器 DPI 感知 v2 + tk 缩放, 高分辨率屏不模糊
  5. 子日程: 日程下可建多个子日程(单层, 不可嵌套), 子项可独立勾选完成/取消

数据: 程序目录/schedule.json(人类可读)。--data-dir 可覆盖目录。
界面: tkinter(仅标准库)。视图: 「今日/进行中」/「历史」。

命令行:
    schedule_app.py                  # 正常启动
    schedule_app.py --data-dir DIR   # 指定数据目录
    schedule_app.py --selftest       # 逻辑自测(不开界面)
    schedule_app.py --smoke          # GUI 冒烟(构建后自动关闭)
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
VERSION = "1.1.0"

# PyInstaller 冻结(打包)运行时: 注入随包带入的 tcl/tk 运行时路径,
# 必须在 import tkinter 之前设置(本程序 tkinter 为懒加载, 此处安全)。
if getattr(sys, "frozen", False):
    _base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    os.environ.setdefault("TCL_LIBRARY", os.path.join(_base, "tcl"))
    os.environ.setdefault("TK_LIBRARY", os.path.join(_base, "tk"))

# ============================================================
# 一、数据存储
# ============================================================

def get_data_dir(_frozen=None, _exe=None):
    """数据目录解析: --data-dir > 程序所在目录 > %APPDATA%\\DeepSeekSchedule(兜底)。
    _frozen/_exe 仅供自测注入, 正常运行传 None 即可。"""
    if "--data-dir" in sys.argv:
        i = sys.argv.index("--data-dir")
        if i + 1 < len(sys.argv):
            return os.path.abspath(sys.argv[i + 1])
    if _frozen is None:
        _frozen = getattr(sys, "frozen", False)
    if _exe is None:
        _exe = sys.executable
    if _frozen:
        d = os.path.dirname(_exe)                    # exe 所在目录
    else:
        d = os.path.dirname(os.path.abspath(__file__))  # 脚本所在目录
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".write_probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return d
    except Exception:
        # 程序目录不可写(如放在 Program Files)时兜底到用户目录
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "DeepSeekSchedule")


DATA_FILE = os.path.join(get_data_dir(), "schedule.json")


def now_iso():
    return datetime.datetime.now().isoformat(timespec="minutes")


def parse_dt(text):
    """解析日期时间, 支持 'YYYY-MM-DD HH:MM' / 'YYYY-MM-DD' / ISO(带 T) 等。失败返回 None"""
    if not text:
        return None
    text = str(text).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M", "%Y/%m/%d"):
        try:
            return datetime.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def new_task(title, note="", deadline=None):
    """新建父日程记录"""
    return {
        "id": uuid.uuid4().hex,
        "title": title.strip(),
        "note": (note or "").strip(),
        "deadline": deadline,          # "YYYY-MM-DD HH:MM" 或 None
        "created_at": now_iso(),
        "status": "active",            # active | done | cancelled
        "completed_at": None,
        "cancelled_at": None,
        "children": [],                # 子日程(单层, 不再嵌套)
    }


def new_child(title):
    """新建子日程"""
    return {
        "id": uuid.uuid4().hex,
        "title": title.strip(),
        "done": False,
        "created_at": now_iso(),
    }


def get_children(task):
    """取子日程列表(兼容旧数据缺 children 字段)"""
    kids = task.get("children")
    return kids if isinstance(kids, list) else []


def update_task(task, title, note, deadline):
    """修改父日程(标题/备注/截止时间)"""
    task["title"] = title.strip()
    task["note"] = (note or "").strip()
    task["deadline"] = deadline
    return task


def normalize_task(t):
    """补齐缺失字段(兼容手动编辑 JSON / 旧版本数据), 保证程序不崩溃"""
    for k, v in {"id": uuid.uuid4().hex, "title": "", "note": "", "deadline": None,
                 "created_at": now_iso(), "status": "active", "completed_at": None,
                 "cancelled_at": None, "children": []}.items():
        t.setdefault(k, v)
    if not isinstance(t.get("children"), list):
        t["children"] = []
    for c in t["children"]:
        c.setdefault("id", uuid.uuid4().hex)
        c.setdefault("title", "")
        c.setdefault("done", False)
        c.setdefault("created_at", now_iso())
    return t


def load_tasks():
    """读取 JSON; 文件损坏时备份 .bak 并返回空列表"""
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [normalize_task(t) for t in data]
        return []
    except Exception:
        try:
            shutil.copy2(DATA_FILE, DATA_FILE + ".bak")
        except Exception:
            pass
        return []


def save_tasks(tasks):
    """原子写 JSON(先写临时文件再替换), 人类可读(indent=2)"""
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


# ============================================================
# 二、业务逻辑(分类 / 倒计时 / 历史)
# ============================================================

def classify(task, now=None):
    """返回: 'done'已完成 / 'cancelled'作废 / 'expired'已过期 / 'active'进行中"""
    status = task.get("status", "active")
    if status != "active":
        return status
    if task.get("deadline"):
        dt = parse_dt(task["deadline"])
        if dt is not None and dt < (now or datetime.datetime.now()):
            return "expired"
    return "active"


def fmt_remain(deadline, now=None):
    """距截止时间的剩余(已过)时长, 样式: X天X时X分 / 已过X天X时 / —"""
    dt = parse_dt(deadline)
    if dt is None:
        return "—"
    now = now or datetime.datetime.now()
    diff = dt - now
    if diff.total_seconds() < 0:
        e = -diff
        days, secs = e.days, e.seconds
        hours, mins = secs // 3600, (secs % 3600) // 60
        if days:
            return "已过%d天%d时" % (days, hours)
        if hours:
            return "已过%d时%d分" % (hours, mins)
        return "已过%d分" % max(1, mins)
    days, secs = diff.days, diff.seconds
    hours, mins = secs // 3600, (secs % 3600) // 60
    if days:
        return "%d天%d时%d分" % (days, hours, mins)
    if hours:
        return "%d时%d分" % (hours, mins)
    if mins:
        return "%d分" % mins
    return "不足1分"


def dl_sort_key(task):
    """按截止时间排序(无截止排最后)"""
    dt = parse_dt(task.get("deadline"))
    return dt if dt is not None else datetime.datetime.max


def history_date(task):
    """历史记录归属日期: 完成→完成时间; 作废→作废时间; 过期→截止时间"""
    if task.get("status") == "done":
        return parse_dt(task.get("completed_at"))
    if task.get("status") == "cancelled":
        return parse_dt(task.get("cancelled_at"))
    return parse_dt(task.get("deadline"))


def fmt_dt(text):
    dt = parse_dt(text)
    return dt.strftime("%Y-%m-%d %H:%M") if dt else (text or "—")


def day_key(dt):
    return dt.strftime("%Y-%m-%d") if dt else None


def enable_dpi_awareness():
    """Windows 高 DPI 感知: 每显示器 DPI 感知 v2(需在任何窗口创建前调用)"""
    if os.name != "nt":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


# ============================================================
# 三、图形界面
# ============================================================

def need_tk():
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    return tk, ttk, messagebox, filedialog


CAT_LABEL = {"done": "✅ 已完成", "cancelled": "🚫 作废", "expired": "⏰ 已过期"}
CHILD_SEP = "::c::"          # 子行 iid 分隔符: <父id>::c::<子id>


def child_iid(task, child):
    return task["id"] + CHILD_SEP + child["id"]


def split_child_iid(iid):
    if CHILD_SEP in iid:
        return tuple(iid.split(CHILD_SEP, 1))
    return (iid, None)


class App:
    def __init__(self, root):
        self.root = root
        root.title("%s v%s" % (APP_NAME, VERSION))

        # DPI 缩放: tk scaling 使字体按物理尺寸渲染; 窗口几何按 DPI 放大
        self.dpi_scale = 1.0
        try:
            dpi = root.winfo_fpixels("1i")
            root.tk.call("tk", "scaling", max(dpi / 72.0, 1.0))
            self.dpi_scale = max(dpi / 96.0, 1.0)
        except Exception:
            pass
        s = self.dpi_scale
        root.geometry("%dx%d" % (int(960 * s), int(620 * s)))
        root.minsize(int(760 * s), int(500 * s))

        self.tasks = load_tasks()
        self.dark = False

        self._build_ui()
        self.apply_theme()
        self.refresh_all()
        self._startup_remind()
        # 每 30 秒刷新剩余时间(倒计时滚动)
        self.root.after(30000, self._tick)

    def _tick(self):
        try:
            if self.nb.index("current") == 0:
                self.refresh_main()
        except Exception:
            pass
        try:
            self.root.after(30000, self._tick)
        except Exception:
            pass

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
        bar1.pack(fill="x", padx=4, pady=(4, 2))
        bar2 = ttk.Frame(self.tab_main)
        bar2.pack(fill="x", padx=4, pady=(0, 4))
        for btn, cmd in (
                ("＋ 添加日程", self.on_add),
                ("✎ 修改", self.on_edit),
                ("✓ 标记完成", lambda: self.on_mark("done")),
                ("🚫 标记作废", lambda: self.on_mark("cancelled")),
                ("🗑 删除", self.on_delete_main)):
            ttk.Button(bar1, text=btn, command=cmd).pack(side="left", padx=(0, 6))
        for btn, cmd in (
                ("＋ 子日程", self.on_add_child),
                ("✓ 子项完成/取消", self.on_toggle_child),
                ("⟳ 刷新", self.refresh_main)):
            ttk.Button(bar2, text=btn, command=cmd).pack(side="left", padx=(0, 6))
        self.theme_btn = ttk.Button(bar2, text="🌙 深色", command=self.toggle_theme)
        self.theme_btn.pack(side="right")

        wrap = ttk.Frame(self.tab_main)
        wrap.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        cols = ("status", "deadline", "remain", "note")
        self.tree_main = ttk.Treeview(wrap, columns=cols, show="tree headings",
                                      selectmode="browse")
        self.tree_main.heading("#0", text="标题")
        self.tree_main.column("#0", width=int(260 * self.dpi_scale), anchor="w",
                              stretch=True)
        for cid, text, w, anchor in (
                ("status", "状态", 90, "center"),
                ("deadline", "截止时间", 150, "center"),
                ("remain", "剩余时间", 140, "center"),
                ("note", "备注", 200, "w")):
            self.tree_main.heading(cid, text=text)
            self.tree_main.column(cid, width=int(w * self.dpi_scale), anchor=anchor,
                                  stretch=(cid == "note"))
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree_main.yview)
        self.tree_main.configure(yscrollcommand=sb.set)
        self.tree_main.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree_main.bind("<Double-1>", lambda e: self.on_detail_main())

        self.status_bar = tk.Label(self.tab_main, text="", anchor="w",
                                   font=("Microsoft YaHei UI", 9))
        self.status_bar.pack(fill="x", padx=6, pady=(0, 4))

        # --- Tab2: 历史 ---
        self.tab_hist = ttk.Frame(nb)
        nb.add(self.tab_hist, text="  历史记录  ")
        bar3 = ttk.Frame(self.tab_hist)
        bar3.pack(fill="x", padx=4, pady=4)
        ttk.Label(bar3, text="类别:").pack(side="left")
        self.hist_cat = ttk.Combobox(bar3, state="readonly", width=13,
                                     values=["全部", "✅ 已完成", "🚫 作废", "⏰ 已过期"])
        self.hist_cat.current(0)
        self.hist_cat.pack(side="left", padx=(2, 10))
        self.hist_cat.bind("<<ComboboxSelected>>", lambda e: self.refresh_hist())
        ttk.Label(bar3, text="日期:").pack(side="left")
        self.hist_range = ttk.Combobox(bar3, state="readonly", width=10,
                                       values=["全部", "今天", "昨天", "近7天", "近30天"])
        self.hist_range.current(0)
        self.hist_range.pack(side="left", padx=(2, 10))
        self.hist_range.bind("<<ComboboxSelected>>", lambda e: self.refresh_hist())
        ttk.Button(bar3, text="🗑 彻底删除", command=self.on_delete_hist).pack(side="left", padx=6)
        ttk.Button(bar3, text="⇩ 导出 CSV", command=self.on_export_csv).pack(side="left", padx=6)
        ttk.Button(bar3, text="ⓘ 详情", command=self.on_detail_hist).pack(side="left", padx=6)

        wrap2 = ttk.Frame(self.tab_hist)
        wrap2.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        cols2 = ("cat", "title", "rec_date", "deadline", "note")
        self.tree_hist = ttk.Treeview(wrap2, columns=cols2, show="headings",
                                      selectmode="browse")
        for cid, text, w, anchor in (
                ("cat", "类型", 100, "center"),
                ("title", "标题", 260, "w"),
                ("rec_date", "记录日期", 130, "center"),
                ("deadline", "截止时间", 150, "center"),
                ("note", "备注", 240, "w")):
            self.tree_hist.heading(cid, text=text)
            self.tree_hist.column(cid, width=int(w * self.dpi_scale), anchor=anchor,
                                  stretch=(cid == "note"))
        sb2 = ttk.Scrollbar(wrap2, orient="vertical", command=self.tree_hist.yview)
        self.tree_hist.configure(yscrollcommand=sb2.set)
        self.tree_hist.pack(side="left", fill="both", expand=True)
        sb2.pack(side="right", fill="y")
        self.tree_hist.bind("<Double-1>", lambda e: self.on_detail_hist())

        self._tag_trees()

    def _tag_trees(self):
        self.tree_main.tag_configure("normal", background=self.c("row_normal"),
                                     foreground=self.c("fg"))
        self.tree_main.tag_configure("due_soon", background=self.c("row_soon"),
                                     foreground=self.c("fg"))
        self.tree_main.tag_configure("overdue", background=self.c("row_over"),
                                     foreground=self.c("fg"))
        self.tree_main.tag_configure("child", background=self.c("row_normal"),
                                     foreground=self.c("fg"))
        self.tree_main.tag_configure("child_done", background=self.c("row_normal"),
                                     foreground=self.c("fg_done"))
        self.tree_hist.tag_configure("done", background=self.c("row_normal"),
                                     foreground=self.c("fg_done"))
        self.tree_hist.tag_configure("cancelled", background=self.c("row_normal"),
                                     foreground=self.c("fg_cancel"))
        self.tree_hist.tag_configure("expired", background=self.c("row_over"),
                                     foreground=self.c("fg"))

    # ---------- 主题 ----------
    def c(self, key):
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
                        rowheight=int(28 * self.dpi_scale), borderwidth=0)
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
        sel = self.tree_main.selection()
        now = datetime.datetime.now()
        overdue = [t for t in self.tasks if classify(t, now) == "expired"]
        active = [t for t in self.tasks if classify(t, now) == "active"]
        due_soon = [t for t in active if t.get("deadline")
                    and 0 <= (parse_dt(t["deadline"]) - now).total_seconds() <= 24 * 3600]

        self.tree_main.delete(*self.tree_main.get_children())
        order = sorted(overdue, key=dl_sort_key) + sorted(active, key=dl_sort_key)
        n_child = 0
        for t in order:
            st = classify(t, now)
            tag = "overdue" if st == "expired" else ("due_soon" if t in due_soon else "normal")
            self.tree_main.insert("", "end", iid=t["id"], text=t["title"], values=(
                "已过期" if tag == "overdue" else ("即将到期" if tag == "due_soon" else "进行中"),
                fmt_dt(t.get("deadline")),
                fmt_remain(t.get("deadline"), now),
                t.get("note", "")), tags=(tag,))
            for c in get_children(t):
                n_child += 1
                self.tree_main.insert(t["id"], "end", iid=child_iid(t, c),
                                      text=c.get("title", ""), values=(
                    "子✓完成" if c.get("done") else "子·进行",
                    "—", "—", ""),
                    tags=("child_done" if c.get("done") else "child",))
        if sel:
            try:
                self.tree_main.selection_set(sel[0])
            except Exception:
                pass
        self.status_bar.configure(
            text="进行中 %d 项 · 子日程 %d 项 · 24h内到期 %d 项 · 已过期 %d 项"
                 % (len(active), n_child, len(due_soon), len(overdue)))

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
                if not {"今天": days == 0, "昨天": days == 1,
                        "近7天": 0 <= days <= 7, "近30天": 0 <= days <= 30}[rng]:
                    continue
            rows.append((t, st, d))
        rows.sort(key=lambda r: (r[2] or datetime.datetime.min), reverse=True)
        self.tree_hist.delete(*self.tree_hist.get_children())
        for t, st, d in rows:
            note = t.get("note", "") or ""
            nk = len(get_children(t))
            if nk:
                note += ("" if not note else "\n") + "含%d个子日程" % nk
            self.tree_hist.insert("", "end", iid=t["id"], values=(
                CAT_LABEL[st], t["title"],
                fmt_dt(d.isoformat(timespec="minutes")) if d else "—",
                fmt_dt(t.get("deadline")), note), tags=(st,))

    # ---------- 选择解析 ----------
    def _selected_task_and_child(self):
        """返回 (父任务, 子日程或None); 无选择返回 (None, None)"""
        sel = self.tree_main.selection()
        if not sel:
            return None, None
        pid, cid = split_child_iid(sel[0])
        task = next((t for t in self.tasks if t["id"] == pid), None)
        if task is None:
            return None, None
        if cid is None:
            return task, None
        child = next((c for c in get_children(task) if c.get("id") == cid), None)
        return task, child

    def on_add(self):
        AddDialog(self)

    def on_edit(self):
        task, child = self._selected_task_and_child()
        if child is not None:
            self._info("子日程暂不支持修改，可删除后重新添加。")
            return
        if task is None:
            self._info("请先选择一个日程。")
            return
        AddDialog(self, task=task)

    def on_mark(self, status):
        task, child = self._selected_task_and_child()
        if child is not None:
            self._info("子日程请用「✓ 子项完成/取消」单独标记。")
            return
        if task is None:
            self._info("请先选择一个日程。")
            return
        label = "完成" if status == "done" else "作废"
        if not self._ask("确认", "确定将「%s」标记为%s吗？" % (task["title"], label)):
            return
        task["status"] = status
        task["completed_at"] = now_iso() if status == "done" else task.get("completed_at")
        task["cancelled_at"] = now_iso() if status == "cancelled" else task.get("cancelled_at")
        if status == "done":
            for c in get_children(task):
                c["done"] = True
        save_tasks(self.tasks)
        self.refresh_all()

    def on_add_child(self):
        task, child = self._selected_task_and_child()
        if task is None:
            self._info("请先选择要添加子日程的父日程。")
            return
        AddChildDialog(self, task)

    def on_toggle_child(self):
        task, child = self._selected_task_and_child()
        if child is None:
            self._info("请选择一条子日程（父日程下的缩进行）。")
            return
        child["done"] = not child.get("done", False)
        save_tasks(self.tasks)
        self.refresh_main()

    def on_delete_main(self):
        task, child = self._selected_task_and_child()
        if task is None:
            self._info("请先在列表中选择一项。")
            return
        if child is not None:
            if self._ask("确认删除", "确定删除子日程「%s」吗？" % child.get("title")):
                task["children"] = [c for c in get_children(task)
                                    if c.get("id") != child.get("id")]
                save_tasks(self.tasks)
                self.refresh_all()
            return
        if self._ask("确认删除", "确定彻底删除「%s」吗？其子日程将一并删除。" % task["title"]):
            self.tasks.remove(task)
            save_tasks(self.tasks)
            self.refresh_all()

    def on_delete_hist(self):
        sel = self.tree_hist.selection()
        if not sel:
            self._info("请先在历史列表中选择一条记录。")
            return
        task = next((t for t in self.tasks if t["id"] == sel[0]), None)
        if task is None:
            return
        if self._ask("确认删除", "确定彻底删除这条历史记录「%s」吗？" % task["title"]):
            self.tasks.remove(task)
            save_tasks(self.tasks)
            self.refresh_all()

    def on_detail_main(self):
        task, _ = self._selected_task_and_child()
        if task:
            DetailDialog(self.root, task)

    def on_detail_hist(self):
        sel = self.tree_hist.selection()
        if sel:
            task = next((t for t in self.tasks if t["id"] == sel[0]), None)
            if task:
                DetailDialog(self.root, task)

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
                         fmt_dt(history_date(t).isoformat(timespec="minutes")
                                if history_date(t) else ""),
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
                       "（详见「进行中」视图红色/黄色条目与剩余时间列）" % (len(expired), len(due_today)))

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
    """添加/修改日程对话框(task=None 为添加, 否则为修改)"""

    def __init__(self, app, task=None):
        tk, ttk, _, _ = need_tk()
        self.app = app
        self.task = task
        self.win = tk.Toplevel(app.root)
        self.win.title("修改日程" if task else "添加日程")
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
        ttk.Button(btns, text="保存修改" if task else "保存",
                   command=self._save).pack(side="left", padx=4)
        ttk.Button(btns, text="取消", command=self.win.destroy).pack(side="left", padx=4)

        frm.columnconfigure(1, weight=1)
        self.win.bind("<Return>", lambda e: self._save())
        self.win.bind("<Escape>", lambda e: self.win.destroy())

        if task:  # 修改模式: 预填
            self.title.insert(0, task.get("title", ""))
            self.note.insert("1.0", task.get("note", ""))
            if task.get("deadline"):
                self.deadline.insert(0, task["deadline"])

    def _quick(self, delta):
        if delta < 0:
            self.deadline.delete(0, "end")
            return
        d = datetime.datetime.now() + datetime.timedelta(days=delta)
        d = d.replace(hour=9 if delta != 1 else 18, minute=0, second=0, microsecond=0)
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
        if self.task is None:
            t = new_task(title, note=self.note.get("1.0", "end").strip(), deadline=dl or None)
            self.app.tasks.append(t)
        else:
            update_task(self.task, title, self.note.get("1.0", "end").strip(), dl or None)
        save_tasks(self.app.tasks)
        self.app.refresh_all()
        self.win.destroy()


class AddChildDialog:
    """添加子日程对话框（子日程仅标题, 单层不可嵌套）"""

    def __init__(self, app, parent):
        tk, ttk, _, _ = need_tk()
        self.app = app
        self.parent = parent
        self.win = tk.Toplevel(app.root)
        self.win.title("添加子日程")
        self.win.geometry("400x150")
        self.win.transient(app.root)
        self.win.grab_set()

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
        save_tasks(self.app.tasks)
        self.app.refresh_all()
        self.win.destroy()


class DetailDialog:
    """日程详情（只读, 含子日程列表）"""

    def __init__(self, parent, task):
        tk, ttk, _, _ = need_tk()
        self.win = tk.Toplevel(parent)
        self.win.title("日程详情")
        self.win.geometry("460x360")
        self.win.transient(parent)
        self.win.grab_set()
        st = classify(task)
        lines = [
            ("标题", task.get("title", "")),
            ("状态", CAT_LABEL.get(st, "进行中") + ("（未完成已过期）" if st == "expired" else "")),
            ("备注", task.get("note") or "（无）"),
            ("截止时间", fmt_dt(task.get("deadline"))),
            ("剩余时间", fmt_remain(task.get("deadline"))),
            ("创建时间", fmt_dt(task.get("created_at"))),
            ("完成时间", fmt_dt(task.get("completed_at")) if task.get("completed_at") else "—"),
            ("作废时间", fmt_dt(task.get("cancelled_at")) if task.get("cancelled_at") else "—"),
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
            ttk.Label(frm, text=v, wraplength=300, justify="left").grid(
                row=i, column=1, sticky="nw", pady=2)
        ttk.Button(frm, text="关闭", command=self.win.destroy).grid(
            row=len(lines), column=1, sticky="e", pady=(12, 0))


# ============================================================
# 四、自测 / 冒烟 / 主入口
# ============================================================

def run_selftest():
    """存储/分类/倒计时/子日程/编辑 逻辑自测（不开界面）"""
    fails = []
    def ok(name, cond, detail=""):
        print(("  ok  " if cond else "FAIL  ") + name + (("  -> " + detail) if detail else ""))
        if not cond:
            fails.append(name)

    # 自测临时目录放在当前工作目录(避免沙箱/权限限制系统临时目录)
    tmp = os.path.join(os.getcwd(), ".sched_selftest_" + uuid.uuid4().hex[:8])
    os.makedirs(tmp, exist_ok=True)
    global DATA_FILE
    DATA_FILE = os.path.join(tmp, "schedule.json")

    print("[1] 存储读写（人类可读 JSON）")
    tasks = [new_task("测试任务", note="备注内容", deadline="2099-01-01 09:00")]
    save_tasks(tasks)
    ok("文件已创建", os.path.exists(DATA_FILE))
    with open(DATA_FILE, encoding="utf-8") as f:
        raw = f.read()
    ok("JSON 含缩进", "\n  " in raw)
    ok("中文未转义", "备注内容" in raw)
    ok("重读一致", load_tasks() == tasks)

    print("[2] 状态分类")
    past = new_task("已过期任务", deadline="2000-01-01 08:00")
    ok("过去截止 -> expired", classify(past) == "expired")
    future = new_task("未来任务", deadline="2099-12-31 23:59")
    ok("未来截止 -> active", classify(future) == "active")
    done = new_task("完成任务")
    done["status"] = "done"; done["completed_at"] = now_iso()
    ok("完成 -> done", classify(done) == "done")
    canc = new_task("作废任务")
    canc["status"] = "cancelled"; canc["cancelled_at"] = now_iso()
    ok("作废 -> cancelled", classify(canc) == "cancelled")
    no_dl = new_task("无截止")
    ok("无截止 -> active", classify(no_dl) == "active")

    print("[3] 倒计时格式化（日/时/分）")
    t0 = datetime.datetime(2099, 1, 1, 9, 0)
    ok("3天2时1分", fmt_remain("2099-01-04 11:01", t0) == "3天2时1分",
       fmt_remain("2099-01-04 11:01", t0))
    ok("2时0分", fmt_remain("2099-01-01 11:00", t0) == "2时0分",
       fmt_remain("2099-01-01 11:00", t0))
    ok("30分", fmt_remain("2099-01-01 09:30", t0) == "30分", fmt_remain("2099-01-01 09:30", t0))
    ok("不足1分", fmt_remain("2099-01-01 09:00:30", t0) == "不足1分",
       fmt_remain("2099-01-01 09:00:30", t0))
    ok("已过4天1时", fmt_remain("2099-01-01 09:00", datetime.datetime(2099, 1, 5, 10, 0))
       == "已过4天1时")
    ok("无截止 -> —", fmt_remain(None) == "—")

    print("[4] 子日程")
    t = new_task("父任务")
    c1 = new_child("子任务1")
    t["children"].append(c1)
    ok("子日程创建", t["children"][0]["title"] == "子任务1" and c1.get("done") is False)
    c1["done"] = True
    ok("子日程完成标记", t["children"][0]["done"] is True)
    ok("get_children 兼容旧数据", get_children({"id": "x", "title": "旧"}) == [])
    ok("child_iid 唯一且可拆分",
       split_child_iid(child_iid(t, c1)) == (t["id"], c1["id"]))

    print("[5] 修改日程")
    t2 = new_task("旧标题", note="旧备注", deadline="2099-01-01 09:00")
    update_task(t2, "新标题", "新备注", None)
    ok("标题/备注更新", t2["title"] == "新标题" and t2["note"] == "新备注")
    ok("截止清空", t2["deadline"] is None)

    print("[6] 数据归一化（旧版/手动编辑兼容）")
    legacy = {"id": "abc", "title": "旧版任务"}
    norm = normalize_task(legacy)
    ok("缺失字段补全", norm.get("children") == [] and norm.get("status") == "active"
       and norm.get("note") == "")
    old = {"id": "d1", "title": "旧", "children": [{"title": "旧子项"}]}
    n2 = normalize_task(old)
    ok("子项字段补全", n2["children"][0].get("done") is False
       and bool(n2["children"][0].get("id")))

    print("[7] 数据目录解析（程序目录优先, 不再用 APPDATA）")
    exe_dir = os.path.join(os.getcwd(), ".sched_exe_test")
    os.makedirs(exe_dir, exist_ok=True)
    try:
        ok("冻结版 -> exe 所在目录",
           get_data_dir(_frozen=True, _exe=os.path.join(exe_dir, "日程管理.exe"))
           == os.path.abspath(exe_dir), get_data_dir(_frozen=True))
        ok("源码版 -> 脚本所在目录",
           get_data_dir(_frozen=False) == os.path.dirname(os.path.abspath(__file__)),
           get_data_dir(_frozen=False))
    finally:
        shutil.rmtree(exe_dir, ignore_errors=True)

    print("\n结果: %s" % ("全部通过" if not fails else "%d 项失败: %s" % (len(fails), fails)))
    try:
        shutil.rmtree(tmp, ignore_errors=True)
    except Exception:
        pass
    return 0 if not fails else 1


def run_smoke():
    """构建界面后自动关闭（验证 GUI 可构建, 含 DPI 感知路径）"""
    enable_dpi_awareness()
    tk, ttk, _, _ = need_tk()
    root = tk.Tk()
    root.withdraw()
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
    enable_dpi_awareness()
    tk, ttk, _, _ = need_tk()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
