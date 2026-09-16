# -*- coding: utf-8 -*-
"""
轻量级桌面日程管理软件（单文件版）v1.3.0
========================================
v1.3.0 新增:
  1. 单实例: 已运行(含托盘待机)时再次双击 exe, 不新建进程, 直接唤醒既有窗口
  2. 托盘右键菜单定位修复(取真实光标坐标, 不再跳到屏幕左上角)
  3. 背景图置于最上层: 透明 PNG 露出原主题背景, 其余图片完整覆盖
  4. 所有子窗口(添加/修改/详情/设置/子日程)尺寸放大并按 DPI 缩放
  5. 打包使用用户提供的 256x256.ico(任务栏/托盘图标)
  6. 周期日程: 每天/每周/每月/工作日, 自动推进下一周期;
     「添加日程」整合快捷截止(今天/明天/下周一/下周末/月末)与周期选项, 显示距截止天数
  7. 标记与置顶: 🚩红旗(自动置顶)/🎨自定义颜色标记/📌置顶, 标记显示在备注之后;
     「标记完成」改名为「完成」
  8. 便签可打开 .txt/.md/.py 文件
  9. 符号小窗: Ctrl+G 或「Σ 符号」召唤, 一键输入希腊字母/常用数学符号

数据: 程序目录/schedule.json + settings.json + notes.txt。
依赖: tkinter(标准库) + Pillow(背景图/图标)。
命令行: --data-dir / --selftest / --smoke 同上。
"""

import os
import sys
import json
import uuid
import calendar
import datetime
import shutil
import ctypes
from ctypes import wintypes

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

APP_NAME = "日程管理"
VERSION = "1.3.0"
AUTOSTART_NAME = "DeepSeek日程管理"
MAX_BG_SIZE = 8 * 1024 * 1024
SINGLE_INSTANCE_MUTEX = "DeepSeek日程管理_SingleInstance"
ICON_NAME = "256x256.ico"

# PyInstaller 冻结(打包)运行时: 注入随包带入的 tcl/tk 运行时路径
if getattr(sys, "frozen", False):
    _base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    os.environ.setdefault("TCL_LIBRARY", os.path.join(_base, "tcl"))
    os.environ.setdefault("TK_LIBRARY", os.path.join(_base, "tk"))


# ============================================================
# 一、数据存储
# ============================================================

def get_data_dir(_frozen=None, _exe=None):
    """数据目录: --data-dir > 程序所在目录 > %APPDATA%\\DeepSeekSchedule(兜底)"""
    if "--data-dir" in sys.argv:
        i = sys.argv.index("--data-dir")
        if i + 1 < len(sys.argv):
            return os.path.abspath(sys.argv[i + 1])
    if _frozen is None:
        _frozen = getattr(sys, "frozen", False)
    if _exe is None:
        _exe = sys.executable
    d = os.path.dirname(_exe) if _frozen else os.path.dirname(os.path.abspath(__file__))
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".write_probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return d
    except Exception:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "DeepSeekSchedule")


DATA_DIR = get_data_dir()
DATA_FILE = os.path.join(DATA_DIR, "schedule.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
NOTES_FILE = os.path.join(DATA_DIR, "notes.txt")

DEFAULT_SETTINGS = {
    "geometry": "",
    "dark": False,
    "autostart": False,
    "minimize_to_tray": False,
    "background": None,
}

REPEAT_NAMES = {"daily": "每天", "weekly": "每周", "monthly": "每月", "weekday": "工作日"}
REPEAT_CODES = {"不重复": None, "每天": "daily", "每周": "weekly",
                "每月": "monthly", "工作日": "weekday"}


def now_iso():
    return datetime.datetime.now().isoformat(timespec="minutes")


def parse_dt(text):
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


def new_task(title, note="", deadline=None, repeat=None):
    """新建父日程记录"""
    return {
        "id": uuid.uuid4().hex,
        "title": title.strip(),
        "note": (note or "").strip(),
        "deadline": deadline,
        "created_at": now_iso(),
        "status": "active",
        "completed_at": None,
        "cancelled_at": None,
        "children": [],
        "repeat": repeat,          # None | daily | weekly | monthly | weekday
        "pinned": False,           # 置顶
        "flag": None,              # None | "red" | 自定义颜色hex
    }


def new_child(title):
    return {
        "id": uuid.uuid4().hex,
        "title": title.strip(),
        "done": False,
        "created_at": now_iso(),
    }


def get_children(task):
    kids = task.get("children")
    return kids if isinstance(kids, list) else []


def update_task(task, title, note, deadline, repeat=None):
    task["title"] = title.strip()
    task["note"] = (note or "").strip()
    task["deadline"] = deadline
    task["repeat"] = repeat
    return task


def normalize_task(t):
    for k, v in {"id": uuid.uuid4().hex, "title": "", "note": "", "deadline": None,
                 "created_at": now_iso(), "status": "active", "completed_at": None,
                 "cancelled_at": None, "children": [], "repeat": None,
                 "pinned": False, "flag": None}.items():
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
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k in DEFAULT_SETTINGS:
                    if k in data:
                        s[k] = data[k]
        except Exception:
            pass
    return s


def save_settings(settings):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SETTINGS_FILE)


def load_text_file(path):
    if not os.path.exists(path):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def save_text_file(path, content):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ============================================================
# 二、业务逻辑(分类 / 倒计时 / 周期 / 标记 / 历史)
# ============================================================

def classify(task, now=None):
    status = task.get("status", "active")
    if status != "active":
        return status
    if task.get("deadline"):
        dt = parse_dt(task["deadline"])
        if dt is not None and dt < (now or datetime.datetime.now()):
            return "expired"
    return "active"


def next_occurrence(dt, repeat, now=None):
    """周期日程: 从 dt 起推演到下一个晚于 now 的发生时刻"""
    now = now or datetime.datetime.now()
    d = dt
    if repeat == "daily":
        while d <= now:
            d += datetime.timedelta(days=1)
    elif repeat == "weekly":
        while d <= now:
            d += datetime.timedelta(days=7)
    elif repeat == "monthly":
        while d <= now:
            y = d.year + (1 if d.month == 12 else 0)
            m = 1 if d.month == 12 else d.month + 1
            last = calendar.monthrange(y, m)[1]
            d = d.replace(year=y, month=m, day=min(d.day, last))
    elif repeat == "weekday":        # 周一~周五
        while d <= now or d.weekday() >= 5:
            d += datetime.timedelta(days=1)
    else:
        while d <= now:
            d += datetime.timedelta(days=1)
    return d


def fmt_remain(deadline, now=None):
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
    dt = parse_dt(task.get("deadline"))
    return dt if dt is not None else datetime.datetime.max


def history_date(task):
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


def date_range_ok(rng, d, now=None):
    if rng in ("", "全部") or d is None:
        return True
    now = now or datetime.datetime.now()
    days = (now - d).days
    table = {"今天": days == 0, "昨天": days == 1, "近7天": 0 <= days <= 7,
             "近30天": 0 <= days <= 30, "30天以上": days > 30}
    return table.get(rng, True)


def kw_ok(task, kw):
    if not kw:
        return True
    kw = kw.lower()
    return (kw in task.get("title", "").lower()
            or kw in task.get("note", "").lower())


def flag_markers(task):
    """返回标记文本(显示在备注之后): 📌置顶 🚩红旗 ●自定义颜色"""
    m = ""
    if task.get("pinned"):
        m += "📌"
    f = task.get("flag")
    if f == "red":
        m += "🚩"
    elif f:
        m += "●" + f
    return m


def enable_dpi_awareness():
    if os.name != "nt":
        return
    try:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


# ============================================================
# 三、单实例 / 自启动 / 托盘
# ============================================================

def ensure_single_instance():
    """单实例: 已有实例运行时唤醒它(含托盘待机), 并让本进程退出。
    返回 True 表示当前进程应直接退出。"""
    if os.name != "nt":
        return False
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        k32.CreateMutexW.restype = wintypes.HANDLE
        h = k32.CreateMutexW(None, False, SINGLE_INSTANCE_MUTEX)
        if h and ctypes.get_last_error() == 183:      # ERROR_ALREADY_EXISTS
            u32 = ctypes.WinDLL("user32")
            u32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
            u32.FindWindowW.restype = wintypes.HWND
            u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            u32.SetForegroundWindow.argtypes = [wintypes.HWND]
            hwnd = u32.FindWindowW(None, APP_NAME)
            if hwnd:
                u32.ShowWindow(hwnd, 9)               # SW_RESTORE
                u32.SetForegroundWindow(hwnd)
            return True
        return False
    except Exception:
        return False


def get_autostart():
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
            winreg.QueryValueEx(k, AUTOSTART_NAME)
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def set_autostart(enabled):
    if os.name != "nt":
        return
    import winreg
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Run")
    try:
        if enabled:
            if getattr(sys, "frozen", False):
                cmd = '"%s"' % sys.executable
            else:
                pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
                if not os.path.exists(pyw):
                    pyw = sys.executable
                cmd = '"%s" "%s"' % (pyw, os.path.abspath(__file__))
            winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, AUTOSTART_NAME)
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)


def icon_path():
    """返回打包附带/工作目录的 ico 图标路径(用于托盘图标)"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(base, ICON_NAME)
    return p if os.path.exists(p) else None


_TRAY_WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND,
                                   wintypes.UINT, wintypes.WPARAM,
                                   wintypes.LPARAM)


class TrayIcon:
    """Windows 托盘图标(纯 ctypes + Shell_NotifyIcon)。双击恢复, 右键菜单。"""

    NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
    NIF_MESSAGE, NIF_ICON, NIF_TIP = 1, 2, 4
    WM_TRAY = 0x8000
    WM_LBUTTONDBLCLK = 0x0203
    WM_RBUTTONUP = 0x0205
    WM_DESTROY = 0x0012
    HWND_MESSAGE = -3
    IDI_APPLICATION = 32515
    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x10

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT),
                    ("lpfnWndProc", _TRAY_WNDPROC), ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                    ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                    ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR),
                    ("lpszClassName", wintypes.LPCWSTR),
                    ("hIconSm", wintypes.HICON)]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                    ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
                    ("uCallbackMessage", wintypes.UINT),
                    ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 128),
                    ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                    ("szInfo", wintypes.WCHAR * 256), ("uVersion", wintypes.UINT),
                    ("szInfoTitle", wintypes.WCHAR * 64),
                    ("dwInfoFlags", wintypes.DWORD),
                    ("guidItem", ctypes.c_byte * 16),
                    ("hBalloonIcon", wintypes.HICON)]

    def __init__(self, tip, on_double, on_right, icon=None):
        self._on_double = on_double
        self._on_right = on_right
        self._tip = (tip or "")[:127]
        self._icon = icon
        self._proc = _TRAY_WNDPROC(self._wnd_proc)
        self._hwnd = None
        self._nid = None
        self._class_atom = None
        self._create()

    def _create(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        shell32 = ctypes.windll.shell32
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
        shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD,
                                              ctypes.POINTER(self.NOTIFYICONDATAW)]
        shell32.Shell_NotifyIconW.restype = wintypes.BOOL
        user32.RegisterClassExW.argtypes = [ctypes.POINTER(self.WNDCLASSEXW)]
        user32.RegisterClassExW.restype = wintypes.ATOM
        user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR,
                                           wintypes.LPCWSTR, wintypes.DWORD,
                                           ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                           ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                           wintypes.HINSTANCE, wintypes.LPVOID]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPVOID]
        user32.LoadIconW.restype = wintypes.HICON
        user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR,
                                      wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                      wintypes.UINT]
        user32.LoadImageW.restype = wintypes.HICON
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.DestroyWindow.restype = wintypes.BOOL
        user32.UnregisterClassW.argtypes = [wintypes.ATOM, wintypes.HINSTANCE]
        user32.UnregisterClassW.restype = wintypes.BOOL
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                          wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = ctypes.c_longlong

        hinst = kernel32.GetModuleHandleW(None)
        cls = "TrayMsgWin_%d" % id(self)
        wc = self.WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(self.WNDCLASSEXW)
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.lpszClassName = cls
        atom = user32.RegisterClassExW(ctypes.byref(wc))
        if not atom:
            raise ctypes.WinError(ctypes.get_last_error())
        self._class_atom = atom

        self._hwnd = user32.CreateWindowExW(
            0, cls, None, 0, 0, 0, 0, 0, wintypes.HWND(self.HWND_MESSAGE),
            None, hinst, None)
        if not self._hwnd:
            raise ctypes.WinError(ctypes.get_last_error())

        nid = self.NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(self.NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = self.NIF_MESSAGE | self.NIF_ICON | self.NIF_TIP
        nid.uCallbackMessage = self.WM_TRAY
        if self._icon and os.path.exists(self._icon):
            nid.hIcon = user32.LoadImageW(None, self._icon, self.IMAGE_ICON,
                                          32, 32, self.LR_LOADFROMFILE)
        if not nid.hIcon:
            nid.hIcon = user32.LoadIconW(None, ctypes.c_void_p(self.IDI_APPLICATION))
        nid.szTip = self._tip
        self._nid = nid
        if not shell32.Shell_NotifyIconW(self.NIM_ADD, ctypes.byref(nid)):
            raise ctypes.WinError(ctypes.get_last_error())

    def _wnd_proc(self, hwnd, msg, wp, lp):
        if msg == self.WM_TRAY:
            ev = lp & 0xFFFF
            if ev == self.WM_LBUTTONDBLCLK:
                try:
                    self._on_double()
                except Exception:
                    pass
            elif ev == self.WM_RBUTTONUP:
                try:
                    self._on_right()
                except Exception:
                    pass
            return 0
        if msg == self.WM_DESTROY:
            return 0
        return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wp, lp)

    def delete(self):
        if self._nid is not None:
            try:
                ctypes.windll.shell32.Shell_NotifyIconW(self.NIM_DELETE,
                                                        ctypes.byref(self._nid))
            except Exception:
                pass
            self._nid = None
        if self._hwnd:
            try:
                ctypes.windll.user32.DestroyWindow(self._hwnd)
            except Exception:
                pass
            self._hwnd = None
        if self._class_atom:
            try:
                ctypes.windll.user32.UnregisterClassW(
                    self._class_atom,
                    ctypes.windll.kernel32.GetModuleHandleW(None))
            except Exception:
                pass
            self._class_atom = None


# ============================================================
# 四、图形界面
# ============================================================

def need_tk():
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog, colorchooser
    return tk, ttk, messagebox, filedialog, colorchooser


CAT_LABEL = {"done": "✅ 已完成", "cancelled": "🚫 作废", "expired": "⏰ 已过期"}
CHILD_SEP = "::c::"
SYMBOL_ROWS = (
    "αβγδεζηθικλμνξοπρστυφχψω",
    "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ",
    "≈≠≤≥±∓×÷∂∇∞∫∑∏",
    "∈∉⊂⊇∪∩→⇒↔←↑↓",
    "√²³°′″·…—§½⅓",
    "⅔¼‰℃℉πφθλΣΩ",
)


def child_iid(task, child):
    return task["id"] + CHILD_SEP + child["id"]


def split_child_iid(iid):
    if CHILD_SEP in iid:
        return tuple(iid.split(CHILD_SEP, 1))
    return (iid, None)


def _hex_to_rgb(s):
    s = (s or "#f4f6f7").lstrip("#")
    try:
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return (0xf4, 0xf6, 0xf7)


def _next_weekday(dow, hour=9):
    d = datetime.datetime.now()
    days = (dow - d.weekday()) % 7
    if days == 0:
        days = 7
    return (d + datetime.timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0)


def _next_saturday(hour=9):
    return _next_weekday(5, hour)


def _month_end(hour=9):
    d = datetime.datetime.now()
    last = calendar.monthrange(d.year, d.month)[1]
    return d.replace(day=last, hour=hour, minute=0, second=0, microsecond=0)


class App:
    def __init__(self, root, with_tray=False):
        self.root = root
        self.settings = load_settings()
        root.title(APP_NAME)          # 固定标题(单实例 FindWindow 依赖)

        self.dpi_scale = 1.0
        try:
            dpi = root.winfo_fpixels("1i")
            root.tk.call("tk", "scaling", max(dpi / 72.0, 1.0))
            self.dpi_scale = max(dpi / 96.0, 1.0)
        except Exception:
            pass
        s = self.dpi_scale
        self._restore_geometry(default="%dx%d" % (int(1180 * s), int(760 * s)))
        root.minsize(int(900 * s), int(580 * s))

        self.tasks = load_tasks()
        self.tray = None
        self.sym_win = None
        self._geo_job = None
        self._search_job = None
        self._bg_size = (0, 0)
        self._bg_photo = None

        self._build_ui()
        self.apply_theme()
        self.refresh_all()
        self._startup_remind()

        root.bind("<Configure>", self._on_configure)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind_all("<Control-g>", lambda e: self.toggle_symbols())
        if with_tray and os.name == "nt":
            self._init_tray()
        self.root.after(30000, self._tick)

    def sz(self, v):
        """按 DPI 缩放尺寸"""
        return int(v * getattr(self, "dpi_scale", 1.0))

    # ---------- 窗口记忆 / 背景 ----------
    def _restore_geometry(self, default):
        g = self.settings.get("geometry") or default
        try:
            import re
            m = re.match(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$", g)
            if m and int(m.group(1)) > 200 and int(m.group(2)) > 150 \
                    and abs(int(m.group(3))) < 30000 and abs(int(m.group(4))) < 30000:
                self.root.geometry(g)
            else:
                self.root.geometry(default)
        except Exception:
            self.root.geometry(default)

    def _save_geometry(self):
        try:
            if self.root.wm_state() == "iconic":
                return
            g = self.root.geometry()
            if g and "x" in g:
                self.settings["geometry"] = g
                save_settings(self.settings)
        except Exception:
            pass

    def _on_configure(self, ev):
        if ev.widget is not self.root:
            return
        if self.root.wm_state() == "iconic":
            return
        try:
            w, h = self.root.winfo_width(), self.root.winfo_height()
            if (w, h) != self._bg_size and w > 20 and h > 20:
                self._bg_size = (w, h)
                self._render_bg()
        except Exception:
            pass
        if self._geo_job:
            try:
                self.root.after_cancel(self._geo_job)
            except Exception:
                pass
        self._geo_job = self.root.after(700, self._save_geometry)

    def _render_bg(self):
        """背景图置于最上层: 透明 PNG 露出主题色基础背景, 其余图片完整覆盖"""
        c = getattr(self, "bg_canvas", None)
        if c is None:
            return
        path = self.settings.get("background")
        if not path or not os.path.exists(path):
            self._clear_bg()
            return
        try:
            from PIL import Image, ImageTk
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            if w < 20 or h < 20:
                return
            img = Image.open(path).convert("RGBA")
            img.thumbnail((2048, 2048), Image.LANCZOS)
            iw, ih = img.size
            scale = max(w / iw, h / ih)
            img = img.resize((max(1, int(iw * scale)), max(1, int(ih * scale))),
                             Image.LANCZOS)
            left = (img.width - w) // 2
            top = (img.height - h) // 2
            img = img.crop((left, top, left + w, top + h))
            base = Image.new("RGBA", (w, h), _hex_to_rgb(self.c("bg")) + (255,))
            base.alpha_composite(img)          # 用户图在上, 透明处露主题背景
            self._bg_photo = ImageTk.PhotoImage(base.convert("RGB"))
            c.delete("all")
            c.create_image(0, 0, anchor="nw", image=self._bg_photo)
            c.configure(bg=self.c("bg"))
        except Exception:
            self._clear_bg()

    def _clear_bg(self):
        c = getattr(self, "bg_canvas", None)
        if c is not None:
            try:
                c.delete("all")
                c.configure(bg=self.c("bg"))
            except Exception:
                pass

    # ---------- 界面搭建 ----------
    def _build_ui(self):
        tk, ttk, _, _, _ = need_tk()
        self.font_base = ("Microsoft YaHei UI", 10)

        self.bg_canvas = tk.Canvas(self.root, highlightthickness=0, bd=0)
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)

        nb = ttk.Notebook(self.root, padding=(12, 8))
        nb.pack(fill="both", expand=True, padx=4, pady=(4, 0))
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
                ("✓ 完成", lambda: self.on_mark("done")),
                ("🚫 作废", lambda: self.on_mark("cancelled")),
                ("🗑 删除", self.on_delete_main)):
            ttk.Button(bar1, text=btn, command=cmd).pack(side="left", padx=(0, 6))
        for btn, cmd in (
                ("＋ 子日程", self.on_add_child),
                ("✓ 子项完成/取消", self.on_toggle_child),
                ("🚩 标记", self.on_flag),
                ("📌 置顶", self.on_pin),
                ("⟳ 刷新", self.refresh_main)):
            ttk.Button(bar2, text=btn, command=cmd).pack(side="left", padx=(0, 6))
        ttk.Button(bar2, text="⚙ 设置", command=self.open_settings).pack(side="right")

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
                ("deadline", "截止时间", 165, "center"),
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
        self.hist_cat = ttk.Combobox(bar3, state="readonly", width=12,
                                     values=["全部", "✅ 已完成", "🚫 作废", "⏰ 已过期"])
        self.hist_cat.current(0)
        self.hist_cat.pack(side="left", padx=(2, 8))
        self.hist_cat.bind("<<ComboboxSelected>>", lambda e: self.refresh_hist())
        ttk.Label(bar3, text="日期:").pack(side="left")
        self.hist_range = ttk.Combobox(bar3, state="readonly", width=10,
                                       values=["全部", "今天", "昨天", "近7天",
                                               "近30天", "30天以上"])
        self.hist_range.current(0)
        self.hist_range.pack(side="left", padx=(2, 8))
        self.hist_range.bind("<<ComboboxSelected>>", lambda e: self.refresh_hist())
        ttk.Label(bar3, text="搜索:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(bar3, textvariable=self.search_var, width=14)
        self.search_entry.pack(side="left", padx=(2, 8))
        self.search_entry.bind("<KeyRelease>", self._on_search)
        ttk.Button(bar3, text="🗑 彻底删除", command=self.on_delete_hist).pack(side="left", padx=4)
        ttk.Button(bar3, text="⇩ 导出 CSV", command=self.on_export_csv).pack(side="left", padx=4)
        ttk.Button(bar3, text="ⓘ 详情", command=self.on_detail_hist).pack(side="left", padx=4)

        wrap2 = ttk.Frame(self.tab_hist)
        wrap2.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        cols2 = ("cat", "title", "rec_date", "deadline", "note")
        self.tree_hist = ttk.Treeview(wrap2, columns=cols2, show="headings",
                                      selectmode="browse")
        for cid, text, w, anchor in (
                ("cat", "类型", 100, "center"),
                ("title", "标题", 240, "w"),
                ("rec_date", "记录日期", 130, "center"),
                ("deadline", "截止时间", 150, "center"),
                ("note", "备注", 220, "w")):
            self.tree_hist.heading(cid, text=text)
            self.tree_hist.column(cid, width=int(w * self.dpi_scale), anchor=anchor,
                                  stretch=(cid == "note"))
        sb2 = ttk.Scrollbar(wrap2, orient="vertical", command=self.tree_hist.yview)
        self.tree_hist.configure(yscrollcommand=sb2.set)
        self.tree_hist.pack(side="left", fill="both", expand=True)
        sb2.pack(side="right", fill="y")
        self.tree_hist.bind("<Double-1>", lambda e: self.on_detail_hist())

        # --- Tab3: 便签 ---
        self.tab_notes = ttk.Frame(nb)
        nb.add(self.tab_notes, text="  便签  ")
        nbar = ttk.Frame(self.tab_notes)
        nbar.pack(fill="x", padx=4, pady=4)
        ttk.Button(nbar, text="💾 保存", command=self.on_notes_save).pack(side="left", padx=(0, 6))
        ttk.Button(nbar, text="📂 打开文件", command=self.on_notes_open).pack(side="left", padx=6)
        ttk.Button(nbar, text="⇩ 另存为 (.txt/.md)", command=self.on_notes_saveas).pack(side="left", padx=6)
        ttk.Button(nbar, text="Σ 符号", command=self.toggle_symbols).pack(side="left", padx=6)
        ttk.Button(nbar, text="🧹 清空全部内容", command=self.on_notes_clear).pack(side="left", padx=6)
        ttk.Label(nbar, text="便签文件: %s" % NOTES_FILE,
                  foreground=self.c("fg_done")).pack(side="right")
        nwrap = ttk.Frame(self.tab_notes)
        nwrap.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self.notes_text = tk.Text(nwrap, wrap="word", font=("Microsoft YaHei UI", 11),
                                  undo=True)
        nsb = ttk.Scrollbar(nwrap, orient="vertical", command=self.notes_text.yview)
        self.notes_text.configure(yscrollcommand=nsb.set)
        self.notes_text.pack(side="left", fill="both", expand=True)
        nsb.pack(side="right", fill="y")
        self.notes_text.insert("1.0", load_text_file(NOTES_FILE))

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

    @property
    def dark(self):
        return bool(self.settings.get("dark"))

    def apply_theme(self):
        tk, ttk, _, _, _ = need_tk()
        self.root.configure(bg=self.c("bg"))
        self._clear_bg()
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
        self.notes_text.configure(bg=self.c("card"), fg=self.c("fg"),
                                  insertbackground=self.c("fg"),
                                  selectbackground=self.c("select"))
        self._tag_trees()

    def toggle_theme(self):
        self.settings["dark"] = not self.dark
        save_settings(self.settings)
        self.apply_theme()
        self.refresh_all()

    # ---------- 托盘 ----------
    def _init_tray(self):
        try:
            tk, _, _, _, _ = need_tk()
            self.tray_menu = tk.Menu(self.root, tearoff=0)
            self.tray_menu.add_command(label="显示主窗口", command=self.show_window)
            self.tray_menu.add_separator()
            self.tray_menu.add_command(label="退出", command=self.quit_app)
            self.tray = TrayIcon(APP_NAME, self.show_window, self._tray_right,
                                 icon=icon_path())
        except Exception:
            self.tray = None

    def _tray_right(self):
        # 取真实光标坐标, 避免菜单跳到屏幕左上角
        try:
            pt = wintypes.POINT()
            user32 = ctypes.windll.user32
            user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
            user32.GetCursorPos.restype = wintypes.BOOL
            if user32.GetCursorPos(ctypes.byref(pt)):
                self.tray_menu.tk_popup(pt.x, pt.y)
                self.tray_menu.grab_release()
        except Exception:
            pass

    def show_window(self):
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

    def on_close(self):
        self._save_geometry()
        self._save_notes()
        if self.settings.get("minimize_to_tray") and self.tray is not None:
            self.root.withdraw()
        else:
            self.quit_app()

    def quit_app(self):
        self._save_geometry()
        self._save_notes()
        if self.tray is not None:
            try:
                self.tray.delete()
            except Exception:
                pass
        try:
            self.root.destroy()
        except Exception:
            pass

    # ---------- 设置 ----------
    def open_settings(self):
        SettingsDialog(self)

    # ---------- 便签 ----------
    def _notes_content(self):
        try:
            return self.notes_text.get("1.0", "end-1c")
        except Exception:
            return ""

    def _save_notes(self):
        try:
            save_text_file(NOTES_FILE, self._notes_content())
        except Exception:
            pass

    def on_notes_save(self):
        self._save_notes()
        self._info("便签已保存到:\n%s" % NOTES_FILE)

    def on_notes_open(self):
        tk, ttk, messagebox, filedialog, _ = need_tk()
        path = filedialog.askopenfilename(
            title="打开文本文件",
            filetypes=[("文本/Markdown/Python", "*.txt *.md *.py"),
                       ("文本文件", "*.txt"), ("Markdown", "*.md"),
                       ("Python", "*.py")])
        if not path:
            return
        if self._notes_content().strip():
            if not self._ask("确认", "当前便签有内容，打开文件将替换。继续吗？"):
                return
        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", load_text_file(path))

    def on_notes_saveas(self):
        tk, ttk, messagebox, filedialog, _ = need_tk()
        path = filedialog.asksaveasfilename(
            title="另存便签为", defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("Markdown", "*.md"),
                       ("所有文件", "*.*")],
            initialfile="便签.txt")
        if not path:
            return
        try:
            save_text_file(path, self._notes_content())
            self._info("已保存到:\n%s" % path)
        except Exception as e:
            self._err("保存失败: %s" % e)

    def on_notes_clear(self):
        if not self._ask("确认清空", "确定清空便签的全部内容吗？此操作不可恢复。"):
            return
        self.notes_text.delete("1.0", "end")
        self._save_notes()

    # ---------- 符号小窗 ----------
    def toggle_symbols(self):
        if getattr(self, "sym_win", None) is not None:
            try:
                if self.sym_win.winfo_exists():
                    self.sym_win.destroy()
                    self.sym_win = None
                    return
            except Exception:
                self.sym_win = None
        tk, _, _, _, _ = need_tk()
        self.sym_win = tk.Toplevel(self.root)
        self.sym_win.title("符号输入（Ctrl+G 开关）")
        self.sym_win.attributes("-topmost", True)
        for row in SYMBOL_ROWS:
            f = tk.Frame(self.sym_win)
            f.pack(fill="x", padx=5, pady=1)
            for ch in row:
                tk.Button(f, text=ch, width=2, font=("Segoe UI", 12),
                          command=lambda c=ch: self._insert_symbol(c)).pack(
                    side="left", padx=1, pady=1)
        tk.Button(self.sym_win, text="关闭", command=self.sym_win.destroy).pack(pady=4)

    def _insert_symbol(self, ch):
        w = self.root.focus_get()
        if w is not None:
            try:
                if str(w.winfo_class()) in ("Text", "Entry"):
                    w.insert("insert", ch)
                    return
            except Exception:
                pass
        try:
            self.notes_text.insert("insert", ch)
            self.notes_text.focus_set()
        except Exception:
            pass

    # ---------- 数据刷新 ----------
    def refresh_all(self):
        self.refresh_main()
        self.refresh_hist()

    def _roll_recurring(self, now):
        """周期日程过期后自动推进到下一周期(并落盘)"""
        changed = False
        for t in self.tasks:
            if t.get("repeat") and classify(t, now) == "expired":
                dt = parse_dt(t.get("deadline"))
                if dt is not None:
                    nd = next_occurrence(dt, t["repeat"], now)
                    t["deadline"] = nd.strftime("%Y-%m-%d %H:%M")
                    changed = True
        if changed:
            save_tasks(self.tasks)

    def refresh_main(self):
        sel = self.tree_main.selection()
        now = datetime.datetime.now()
        self._roll_recurring(now)
        overdue = [t for t in self.tasks if classify(t, now) == "expired"]
        active = [t for t in self.tasks if classify(t, now) == "active"]
        due_soon = []
        for t in active:
            dl = parse_dt(t.get("deadline"))
            if dl is not None and 0 <= (dl - now).total_seconds() <= 24 * 3600:
                due_soon.append(t)

        self.tree_main.delete(*self.tree_main.get_children())
        items = overdue + active
        items.sort(key=lambda t: (0 if t.get("pinned") else 1,
                                  0 if classify(t, now) == "expired" else 1,
                                  dl_sort_key(t)))
        n_child = 0
        for t in items:
            st = classify(t, now)
            tag = "overdue" if st == "expired" else ("due_soon" if t in due_soon else "normal")
            dl_text = fmt_dt(t.get("deadline"))
            rp = t.get("repeat")
            if rp and REPEAT_NAMES.get(rp):
                dl_text += "(%s)" % REPEAT_NAMES[rp]
            note = t.get("note", "")
            fm = flag_markers(t)
            if fm:
                note = (note + " " if note else "") + fm
            self.tree_main.insert("", "end", iid=t["id"], text=t["title"], values=(
                ("已过期" if tag == "overdue"
                 else ("即将到期" if tag == "due_soon" else "进行中")),
                dl_text,
                fmt_remain(t.get("deadline"), now),
                note), tags=(tag,))
            for c in get_children(t):
                n_child += 1
                self.tree_main.insert(t["id"], "end", iid=child_iid(t, c),
                                      text=c.get("title", ""), values=(
                    "子✓完成" if c.get("done") else "子·进行", "—", "—", ""),
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
        kw = self.search_var.get()
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
            if not kw_ok(t, kw):
                continue
            d = history_date(t)
            if not date_range_ok(rng, d, now):
                continue
            rows.append((t, st, d))
        rows.sort(key=lambda r: (r[2] or datetime.datetime.min), reverse=True)
        self.tree_hist.delete(*self.tree_hist.get_children())
        for t, st, d in rows:
            note = t.get("note", "") or ""
            fm = flag_markers(t)
            if fm:
                note = (note + " " if note else "") + fm
            nk = len(get_children(t))
            if nk:
                note += ("" if not note else "\n") + "含%d个子日程" % nk
            self.tree_hist.insert("", "end", iid=t["id"], values=(
                CAT_LABEL[st], t["title"],
                fmt_dt(d.isoformat(timespec="minutes")) if d else "—",
                fmt_dt(t.get("deadline")), note), tags=(st,))

    def _on_search(self, ev):
        if self._search_job:
            try:
                self.root.after_cancel(self._search_job)
            except Exception:
                pass
        self._search_job = self.root.after(250, self.refresh_hist)

    # ---------- 选择解析与操作 ----------
    def _selected_task_and_child(self):
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
        if status == "done" and task.get("repeat"):
            # 周期日程: 完成当前周期, 自动推进到下一周期, 保持待办
            dt = parse_dt(task.get("deadline"))
            task["completed_at"] = now_iso()
            if dt:
                nd = next_occurrence(dt, task["repeat"], datetime.datetime.now())
                task["deadline"] = nd.strftime("%Y-%m-%d %H:%M")
            for c in get_children(task):
                c["done"] = True
        else:
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

    def on_flag(self):
        """🚩 标记菜单: 红旗(自动置顶) / 自定义颜色 / 清除"""
        task, child = self._selected_task_and_child()
        if child is not None:
            self._info("子日程暂不支持标记。")
            return
        if task is None:
            self._info("请先选择一个日程。")
            return
        tk, _, _, _, _ = need_tk()
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="🚩 红旗（红色·自动置顶）",
                         command=lambda: self.set_flag(task, "red"))
        menu.add_command(label="🎨 自定义颜色…",
                         command=lambda: self.set_flag(task, "custom"))
        menu.add_separator()
        menu.add_command(label="✖ 清除标记", command=lambda: self.set_flag(task, None))
        try:
            menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            menu.grab_release()

    def set_flag(self, task, kind):
        if kind == "custom":
            _, hexv = need_tk()[4].askcolor(parent=self.root, title="选择标记颜色")
            if not hexv:
                return
            task["flag"] = hexv
        else:
            task["flag"] = kind           # "red" | None
        if task["flag"] == "red":
            task["pinned"] = True         # 红旗自带置顶
        save_tasks(self.tasks)
        self.refresh_main()

    def on_pin(self):
        """📌 置顶/取消置顶(取消红旗任务的置顶会同时清除红旗)"""
        task, child = self._selected_task_and_child()
        if child is not None:
            self._info("子日程暂不支持置顶。")
            return
        if task is None:
            self._info("请先选择一个日程。")
            return
        task["pinned"] = not task.get("pinned", False)
        if not task["pinned"] and task.get("flag") == "red":
            task["flag"] = None
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
            DetailDialog(self.root, task, self.dpi_scale)

    def on_detail_hist(self):
        sel = self.tree_hist.selection()
        if sel:
            task = next((t for t in self.tasks if t["id"] == sel[0]), None)
            if task:
                DetailDialog(self.root, task, self.dpi_scale)

    def on_export_csv(self):
        tk, ttk, messagebox, filedialog, _ = need_tk()
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

    def _ask(self, title, msg):
        _, _, messagebox, _, _ = need_tk()
        return messagebox.askyesno(title, msg, parent=self.root)

    def _info(self, msg):
        _, _, messagebox, _, _ = need_tk()
        messagebox.showinfo(APP_NAME, msg, parent=self.root)

    def _err(self, msg):
        _, _, messagebox, _, _ = need_tk()
        messagebox.showerror(APP_NAME, msg, parent=self.root)


class SettingsDialog:
    """设置中心"""

    def __init__(self, app):
        tk, ttk, _, _, _ = need_tk()
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title("设置")
        self.win.geometry("%dx%d" % (app.sz(560), app.sz(460)))
        self.win.transient(app.root)
        self.win.grab_set()
        self.dark_var = tk.BooleanVar(value=app.dark)
        self.autostart_var = tk.BooleanVar(value=app.settings.get("autostart"))
        self.tray_var = tk.BooleanVar(value=app.settings.get("minimize_to_tray"))

        frm = ttk.Frame(self.win, padding=14)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="外观", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
        ttk.Checkbutton(frm, text="深色模式", variable=self.dark_var,
                        command=self._on_dark).pack(anchor="w", pady=(4, 2))
        bgrow = ttk.Frame(frm)
        bgrow.pack(fill="x", pady=2)
        ttk.Label(bgrow, text="背景图片:").pack(side="left")
        ttk.Button(bgrow, text="选择图片…", command=self._on_bg_pick).pack(side="left", padx=4)
        ttk.Button(bgrow, text="移除背景", command=self._on_bg_remove).pack(side="left", padx=4)
        ttk.Label(frm, text="≤8MB；置于背景最上层，透明 PNG 会露出原主题背景",
                  foreground=app.c("fg_done")).pack(anchor="w", pady=(0, 6))

        ttk.Separator(frm).pack(fill="x", pady=6)
        ttk.Label(frm, text="常规", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
        ttk.Checkbutton(frm, text="开机自启动", variable=self.autostart_var,
                        command=self._on_autostart).pack(anchor="w", pady=(4, 2))
        ttk.Checkbutton(frm, text="关闭时最小化到托盘（托盘可恢复/退出）",
                        variable=self.tray_var,
                        command=self._on_tray).pack(anchor="w", pady=(0, 2))

        ttk.Separator(frm).pack(fill="x", pady=6)
        ttk.Label(frm, text="数据", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
        drow = ttk.Frame(frm)
        drow.pack(fill="x", pady=(4, 2))
        ttk.Button(drow, text="导出历史为 CSV", command=self._on_export).pack(side="left", padx=(0, 8))
        ttk.Button(drow, text="打开数据文件夹", command=self._on_open_dir).pack(side="left")
        ttk.Label(frm, text="数据位置: %s" % DATA_FILE, wraplength=520,
                  foreground=app.c("fg_done")).pack(anchor="w", pady=(2, 4))

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Label(btns, text="版本 v%s" % VERSION,
                  foreground=app.c("fg_done")).pack(side="left")
        ttk.Button(btns, text="关闭", command=self.win.destroy).pack(side="right")

    def _on_dark(self):
        self.app.settings["dark"] = self.dark_var.get()
        save_settings(self.app.settings)
        self.app.apply_theme()
        self.app.refresh_all()

    def _on_autostart(self):
        enabled = self.autostart_var.get()
        try:
            set_autostart(enabled)
            self.app.settings["autostart"] = enabled
            save_settings(self.app.settings)
        except Exception as e:
            self.app._err("设置开机自启动失败: %s" % e)

    def _on_tray(self):
        self.app.settings["minimize_to_tray"] = self.tray_var.get()
        save_settings(self.app.settings)

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
            save_settings(self.app.settings)
            self.app._render_bg()
            self.app._info("背景已应用。\n透明 PNG 会露出原主题背景。")
        except Exception as e:
            self.app._err("无法加载该图片: %s" % e)

    def _on_bg_remove(self):
        self.app.settings["background"] = None
        save_settings(self.app.settings)
        self.app._clear_bg()
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


class AddDialog:
    """添加/修改日程对话框: 整合周期日程与快捷截止选项"""

    def __init__(self, app, task=None):
        tk, ttk, _, _, _ = need_tk()
        self.app = app
        self.task = task
        self.win = tk.Toplevel(app.root)
        self.win.title("修改日程" if task else "添加日程")
        self.win.geometry("%dx%d" % (app.sz(580), app.sz(470)))
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
        self.deadline.bind("<KeyRelease>", lambda e: self._update_hint())
        ttk.Label(frm, text="格式: 2026-08-30 18:00（可留空 = 无截止）",
                  foreground=app.c("fg_done")).grid(row=3, column=1, sticky="w")
        self.hint = tk.Label(frm, text="", fg="#2e86c1", bg=app.c("bg"))
        self.hint.grid(row=4, column=1, sticky="w")

        quick = ttk.Frame(frm)
        quick.grid(row=5, column=1, sticky="w", pady=(2, 0))
        for label, delta in (("今天 18:00", 0), ("明天 09:00", 1),
                             ("下周一 09:00", 2), ("下周末 09:00", 3),
                             ("月末", 4), ("清除", -1)):
            ttk.Button(quick, text=label, width=11,
                       command=lambda d=delta: self._quick(d)).pack(side="left", padx=2, pady=1)

        ttk.Label(frm, text="周期").grid(row=6, column=0, sticky="w")
        self.repeat_var = tk.StringVar(value="不重复")
        self.repeat_box = ttk.Combobox(frm, textvariable=self.repeat_var,
                                       state="readonly", width=12,
                                       values=list(REPEAT_CODES.keys()))
        self.repeat_box.grid(row=6, column=1, sticky="w", pady=3)
        ttk.Label(frm, text="周期日程到期后自动推进到下一周期",
                  foreground=app.c("fg_done")).grid(row=7, column=1, sticky="w")

        self.err = tk.Label(frm, text="", fg="#c0392b", bg=app.c("bg"))
        self.err.grid(row=8, column=0, columnspan=2, sticky="w", pady=(4, 0))

        btns = ttk.Frame(frm)
        btns.grid(row=9, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="保存修改" if task else "保存",
                   command=self._save).pack(side="left", padx=4)
        ttk.Button(btns, text="取消", command=self.win.destroy).pack(side="left", padx=4)

        frm.columnconfigure(1, weight=1)
        self.win.bind("<Return>", lambda e: self._save())
        self.win.bind("<Escape>", lambda e: self.win.destroy())

        if task:
            self.title.insert(0, task.get("title", ""))
            self.note.insert("1.0", task.get("note", ""))
            if task.get("deadline"):
                self.deadline.insert(0, task["deadline"])
            rp = task.get("repeat")
            self.repeat_var.set(next((k for k, v in REPEAT_CODES.items() if v == rp),
                                     "不重复"))
        self._update_hint()

    def _quick(self, delta):
        if delta < 0:
            self.deadline.delete(0, "end")
            self._update_hint()
            return
        if delta == 0:
            d = (datetime.datetime.now().replace(hour=18, minute=0, second=0,
                                                 microsecond=0))
        elif delta == 1:
            d = (datetime.datetime.now() + datetime.timedelta(days=1)).replace(
                hour=9, minute=0, second=0, microsecond=0)
        elif delta == 2:
            d = _next_weekday(0, 9)      # 下周一
        elif delta == 3:
            d = _next_saturday(9)        # 下周末(周六)
        else:
            d = _month_end(9)            # 月末
        self.deadline.delete(0, "end")
        self.deadline.insert(0, d.strftime("%Y-%m-%d %H:%M"))
        self._update_hint()

    def _update_hint(self):
        dl = self.deadline.get().strip()
        if not dl:
            self.hint.configure(text="")
            return
        if parse_dt(dl) is None:
            self.hint.configure(text="格式不正确")
            return
        self.hint.configure(text="距 %s 还有 %s" % (dl, fmt_remain(dl)))

    def _save(self):
        title = self.title.get().strip()
        if not title:
            self.err.configure(text="标题不能为空！")
            return
        dl = self.deadline.get().strip()
        if dl and parse_dt(dl) is None:
            self.err.configure(text="截止时间格式错误，请用 2026-08-30 18:00")
            return
        repeat = REPEAT_CODES.get(self.repeat_var.get())
        if self.task is None:
            t = new_task(title, note=self.note.get("1.0", "end").strip(),
                         deadline=dl or None, repeat=repeat)
            self.app.tasks.append(t)
        else:
            update_task(self.task, title, self.note.get("1.0", "end").strip(),
                        dl or None, repeat=repeat)
        save_tasks(self.app.tasks)
        self.app.refresh_all()
        self.win.destroy()


class AddChildDialog:
    """添加子日程对话框（单层不可嵌套）"""

    def __init__(self, app, parent):
        tk, ttk, _, _, _ = need_tk()
        self.app = app
        self.parent = parent
        self.win = tk.Toplevel(app.root)
        self.win.title("添加子日程")
        self.win.geometry("%dx%d" % (app.sz(480), app.sz(200)))
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
    """日程详情（只读, 含子日程/周期/标记）"""

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
            ("周期", REPEAT_NAMES.get(rp, "不重复") if rp else "不重复"),
            ("标记", fm or "无"),
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
            ttk.Label(frm, text=v, wraplength=380, justify="left").grid(
                row=i, column=1, sticky="nw", pady=2)
        ttk.Button(frm, text="关闭", command=self.win.destroy).grid(
            row=len(lines), column=1, sticky="e", pady=(12, 0))


# ============================================================
# 五、自测 / 冒烟 / 主入口
# ============================================================

def run_selftest():
    """逻辑自测（不开界面）"""
    fails = []
    def ok(name, cond, detail=""):
        print(("  ok  " if cond else "FAIL  ") + name + (("  -> " + detail) if detail else ""))
        if not cond:
            fails.append(name)

    tmp = os.path.join(os.getcwd(), ".sched_selftest_" + uuid.uuid4().hex[:8])
    os.makedirs(tmp, exist_ok=True)
    global DATA_DIR, DATA_FILE, SETTINGS_FILE, NOTES_FILE
    DATA_DIR = tmp
    DATA_FILE = os.path.join(tmp, "schedule.json")
    SETTINGS_FILE = os.path.join(tmp, "settings.json")
    NOTES_FILE = os.path.join(tmp, "notes.txt")

    print("[1] 存储读写")
    tasks = [new_task("测试任务", note="备注内容", deadline="2099-01-01 09:00")]
    save_tasks(tasks)
    ok("文件已创建", os.path.exists(DATA_FILE))
    ok("中文未转义", "备注内容" in open(DATA_FILE, encoding="utf-8").read())
    ok("重读一致", load_tasks() == tasks)

    print("[2] 状态分类")
    ok("过去截止 -> expired", classify(new_task("x", deadline="2000-01-01 08:00")) == "expired")
    ok("未来截止 -> active", classify(new_task("x", deadline="2099-12-31 23:59")) == "active")

    print("[3] 倒计时格式化")
    t0 = datetime.datetime(2099, 1, 1, 9, 0)
    ok("3天2时1分", fmt_remain("2099-01-04 11:01", t0) == "3天2时1分")
    ok("已过4天1时", fmt_remain("2099-01-01 09:00",
       datetime.datetime(2099, 1, 5, 10, 0)) == "已过4天1时")
    ok("无截止 -> —", fmt_remain(None) == "—")

    print("[4] 子日程")
    t = new_task("父任务")
    c1 = new_child("子任务1")
    t["children"].append(c1)
    ok("创建/完成标记", t["children"][0]["title"] == "子任务1" and c1.get("done") is False)
    c1["done"] = True
    ok("get_children 兼容旧数据", get_children({"id": "x"}) == [])

    print("[5] 周期日程推进")
    ok("daily", next_occurrence(datetime.datetime(2026, 8, 30, 18, 0), "daily",
                                datetime.datetime(2026, 9, 1, 10, 0))
       == datetime.datetime(2026, 9, 1, 18, 0))
    ok("weekly", next_occurrence(datetime.datetime(2026, 8, 28, 9, 0), "weekly",
                                 datetime.datetime(2026, 9, 10, 0, 0))
       == datetime.datetime(2026, 9, 11, 9, 0))
    ok("monthly 月末截断", next_occurrence(datetime.datetime(2026, 1, 31, 9, 0), "monthly",
                                          datetime.datetime(2026, 3, 1, 0, 0))
       == datetime.datetime(2026, 3, 28, 9, 0))
    ok("weekday 跳过周末", next_occurrence(datetime.datetime(2026, 8, 28, 18, 0), "weekday",
                                          datetime.datetime(2026, 8, 29, 0, 0))
       == datetime.datetime(2026, 8, 31, 18, 0))

    print("[6] 标记与置顶")
    t2 = new_task("任务")
    t2["flag"] = "red"
    ok("红旗标记", flag_markers(t2) == "🚩")
    t2["pinned"] = True
    t2["flag"] = "#ff8800"
    ok("自定义颜色标记", "●#ff8800" in flag_markers(t2) and "📌" in flag_markers(t2))
    ok("无标记为空", flag_markers(new_task("x")) == "")

    print("[7] 归一化(旧版兼容)")
    norm = normalize_task({"id": "abc", "title": "旧"})
    ok("新字段补全", norm.get("repeat") is None and norm.get("pinned") is False
       and norm.get("flag") is None)

    print("[8] 设置读写")
    s = dict(DEFAULT_SETTINGS)
    s["dark"] = True
    save_settings(s)
    ok("设置往返", load_settings() == s)

    print("[9] 日期筛选与搜索")
    now = datetime.datetime(2026, 8, 29, 12, 0)
    ok("30天以上(31天前) True", date_range_ok("30天以上", now - datetime.timedelta(days=31), now))
    ok("30天以上(30天前) False", not date_range_ok("30天以上", now - datetime.timedelta(days=30), now))
    ok("关键词命中", kw_ok({"title": "周报", "note": ""}, "周报"))
    ok("关键词忽略大小写", kw_ok({"title": "任务", "note": "Meeting"}, "MEETING"))

    print("[10] 便签文件读写")
    save_text_file(NOTES_FILE, "第一行\n第二行 中文")
    ok("便签保存/读取", load_text_file(NOTES_FILE) == "第一行\n第二行 中文")
    ok("缺省为空", load_text_file(os.path.join(tmp, "none.txt")) == "")

    print("[11] 数据目录解析")
    exe_dir = os.path.join(os.getcwd(), ".sched_exe_test")
    os.makedirs(exe_dir, exist_ok=True)
    try:
        ok("冻结版 -> exe 目录",
           get_data_dir(_frozen=True, _exe=os.path.join(exe_dir, "日程管理.exe"))
           == os.path.abspath(exe_dir))
        ok("源码版 -> 脚本目录",
           get_data_dir(_frozen=False) == os.path.dirname(os.path.abspath(__file__)))
    finally:
        shutil.rmtree(exe_dir, ignore_errors=True)

    print("\n结果: %s" % ("全部通过" if not fails else "%d 项失败: %s" % (len(fails), fails)))
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if not fails else 1


def run_smoke():
    """GUI 冒烟 + 托盘创建测试"""
    enable_dpi_awareness()
    if os.name == "nt":
        try:
            ti = TrayIcon("日程管理冒烟测试", lambda: None, lambda: None,
                          icon=icon_path())
            print("托盘图标创建成功")
            ti.delete()
        except Exception as e:
            print("托盘创建失败: %s" % e)
            return 1
    tk, ttk, _, _, _ = need_tk()
    root = tk.Tk()
    root.withdraw()
    app = App(root, with_tray=False)
    root.update_idletasks()
    root.after(1200, root.destroy)
    root.mainloop()
    print("GUI 冒烟测试通过")
    return 0


def main():
    if "--selftest" in sys.argv:
        sys.exit(run_selftest())
    if "--smoke" in sys.argv:
        sys.exit(run_smoke())
    if ensure_single_instance():
        return                       # 已有实例在运行, 已唤醒它, 本进程退出
    enable_dpi_awareness()
    tk, ttk, _, _, _ = need_tk()
    root = tk.Tk()
    App(root, with_tray=True)
    root.mainloop()


if __name__ == "__main__":
    main()
