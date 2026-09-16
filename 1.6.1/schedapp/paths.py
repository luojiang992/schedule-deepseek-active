# -*- coding: utf-8 -*-
"""路径/目录/设置常量与迁移"""
import os
import sys
import json
import shutil
import ctypes
from ctypes import wintypes

APP_NAME = "日程管理"
VERSION = "1.6.0"
AUTOSTART_NAME = "DeepSeek日程管理"
MAX_BG_SIZE = 8 * 1024 * 1024
SINGLE_INSTANCE_MUTEX = "DeepSeek日程管理_SingleInstance"
ICON_NAME = "256x256.ico"

# PyInstaller 冻结运行时: 注入 tcl/tk 路径
if getattr(sys, "frozen", False):
    _base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    os.environ.setdefault("TCL_LIBRARY", os.path.join(_base, "tcl"))
    os.environ.setdefault("TK_LIBRARY", os.path.join(_base, "tk"))


def get_data_base(_frozen=None, _exe=None):
    """数据基目录: --data-dir > 程序所在目录 > %APPDATA%\\DeepSeekSchedule(兜底)"""
    if "--data-dir" in sys.argv:
        i = sys.argv.index("--data-dir")
        if i + 1 < len(sys.argv):
            return os.path.abspath(sys.argv[i + 1])
    if _frozen is None:
        _frozen = getattr(sys, "frozen", False)
    if _exe is None:
        _exe = sys.executable
    d = os.path.dirname(_exe) if _frozen else os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
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


_DATA_BASE = get_data_base()
DATA_DIR = (_DATA_BASE if "--data-dir" in sys.argv
            else os.path.join(_DATA_BASE, "data"))     # 统一数据文件夹
TOOLS_DIR = os.path.join(_DATA_BASE, "tools")          # 外部工具 exe 文件夹

LEGACY_FILES = ("schedule.json", "settings.json", "notes.txt",
                "background.png", "symbols.json", "snippets.json")


def migrate_legacy(base, data_dir):
    """把散落在程序目录的旧数据文件迁移进 data/ 子文件夹"""
    try:
        if os.path.abspath(base) == os.path.abspath(data_dir):
            return
        os.makedirs(data_dir, exist_ok=True)
        for fn in LEGACY_FILES:
            src = os.path.join(base, fn)
            dst = os.path.join(data_dir, fn)
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.move(src, dst)
    except Exception:
        pass


migrate_legacy(_DATA_BASE, DATA_DIR)

DATA_FILE = os.path.join(DATA_DIR, "schedule.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
NOTES_ROOT = os.path.join(DATA_DIR, "notes")           # 便签 IDE 根目录
NOTES_FILE = os.path.join(NOTES_ROOT, "便签.txt")      # 默认便签
SYMBOLS_FILE = os.path.join(DATA_DIR, "symbols.json")
SNIPPETS_FILE = os.path.join(DATA_DIR, "snippets.json")
TEMPLATES_FILE = os.path.join(DATA_DIR, "templates.json")
QUICKTIMES_FILE = os.path.join(DATA_DIR, "quicktimes.json")

DEFAULT_SETTINGS = {
    "geometry": "",
    "dark": False,
    "autostart": False,
    "minimize_to_tray": False,
    "background": None,
    "window_alpha": 0.92,
    "symbol_hotkey": "Ctrl+Shift+G",
    "snippet_hotkey": "Ctrl+Shift+S",
    "notes_last_file": "",
}

REPEAT_NAMES = {"daily": "每天", "weekly": "每周", "monthly": "每月", "weekday": "工作日"}
REPEAT_CODES = {"不重复": None, "每天": "daily", "每周": "weekly",
                "每月": "monthly", "工作日": "weekday"}

DEFAULT_SYMBOL_ROWS = (
    "αβγδεζηθικλμνξοπρστυφχψω",
    "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ",
    "≈≠≤≥±∓×÷∂∇∞∫∑∏",
    "∈∉⊂⊇∪∩→⇒↔←↑↓",
    "√²³°′″·…—§½⅓",
    "⅔¼‰℃℉πφθλΣΩ",
)

MOD_ALT, MOD_CONTROL, MOD_SHIFT = 0x1, 0x2, 0x4
HOTKEY_PRESETS = {
    "Ctrl+Shift+G": (MOD_CONTROL | MOD_SHIFT, 0x47),
    "Ctrl+Shift+S": (MOD_CONTROL | MOD_SHIFT, 0x53),
    "Ctrl+Alt+G": (MOD_CONTROL | MOD_ALT, 0x47),
    "Ctrl+Alt+S": (MOD_CONTROL | MOD_ALT, 0x53),
    "Alt+F8": (MOD_ALT, 0x77),
    "Ctrl+F8": (MOD_CONTROL, 0x77),
    "无": (0, 0),
}
HK_SYMBOL = 0xB001
HK_SNIPPET = 0xB002

BOARD_COLORS = ["#000000", "#7f7f7f", "#c0c0c0", "#ffffff",
                "#ff0000", "#ff7f00", "#ffff00", "#7fff00",
                "#00ff00", "#00ff7f", "#00ffff", "#007fff",
                "#0000ff", "#7f00ff", "#ff00ff", "#ff007f",
                "#8b4513", "#cd853f", "#ffd700", "#ffa500",
                "#2e8b57", "#1e90ff", "#9400d3", "#dc143c"]

CAT_LABEL = {"done": "✅ 已完成", "cancelled": "🚫 作废", "expired": "⏰ 已过期"}

DEFAULT_QUICKTIMES = [
    {"label": "今天 18:00", "kind": "days", "delta": 0, "hour": 18, "minute": 0},
    {"label": "明天 09:00", "kind": "days", "delta": 1, "hour": 9, "minute": 0},
    {"label": "下周一 09:00", "kind": "weekday", "delta": 0, "hour": 9, "minute": 0},
    {"label": "下周末 09:00", "kind": "weekday", "delta": 5, "hour": 9, "minute": 0},
    {"label": "月末", "kind": "month_end", "delta": 0, "hour": 9, "minute": 0},
]


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


def icon_path():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(base, ICON_NAME)
    return p if os.path.exists(p) else None
