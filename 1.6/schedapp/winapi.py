# -*- coding: utf-8 -*-
"""Windows 系统接口: 单实例 / DPI / 托盘 / 全局热键 / SendInput / 自启动"""
import os
import sys
import ctypes
from ctypes import wintypes

from .paths import APP_NAME, AUTOSTART_NAME, SINGLE_INSTANCE_MUTEX, ICON_NAME

MOD_ALT, MOD_CONTROL, MOD_SHIFT = 0x1, 0x2, 0x4


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


def is_admin():
    """当前进程是否以管理员身份运行"""
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_elevated(args=None):
    """以管理员身份(UAC)重新启动本程序。args: 附加命令行参数(字符串)或 None。"""
    if os.name != "nt":
        return
    try:
        params = args or ""
        if getattr(sys, "frozen", False):
            exe, p = sys.executable, params
        else:
            exe = sys.executable
            script = os.path.abspath(sys.argv[0])
            p = ('"%s"' % script) + ((" " + params) if params else "")
        shell32 = ctypes.windll.shell32
        shell32.ShellExecuteW.argtypes = [wintypes.HWND, wintypes.LPCWSTR,
                                          wintypes.LPCWSTR, wintypes.LPCWSTR,
                                          wintypes.LPCWSTR, ctypes.c_int]
        shell32.ShellExecuteW.restype = ctypes.c_void_p
        shell32.ShellExecuteW(None, "runas", exe, p, None, 1)
    except Exception:
        pass


def ensure_single_instance():
    """单实例: 已有实例运行时唤醒它(含托盘待机), 并让本进程退出。返回 True 表示应退出。"""
    if os.name != "nt":
        return False
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        k32.CreateMutexW.restype = wintypes.HANDLE
        h = k32.CreateMutexW(None, False, SINGLE_INSTANCE_MUTEX)
        if h and ctypes.get_last_error() == 183:
            u32 = ctypes.WinDLL("user32")
            u32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
            u32.FindWindowW.restype = wintypes.HWND
            u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            u32.SetForegroundWindow.argtypes = [wintypes.HWND]
            hwnd = u32.FindWindowW(None, APP_NAME)
            if hwnd:
                u32.ShowWindow(hwnd, 9)
                u32.SetForegroundWindow(hwnd)
            return True
        return False
    except Exception:
        return False


# ---------- 前台窗口 / 全局输入 ----------

def get_foreground_hwnd():
    if os.name != "nt":
        return None
    try:
        u = ctypes.windll.user32
        u.GetForegroundWindow.argtypes = []
        u.GetForegroundWindow.restype = wintypes.HWND
        return u.GetForegroundWindow()
    except Exception:
        return None


def force_foreground(hwnd):
    """把前台窗口还给指定句柄(含 AttachThreadInput, 后台进程也可切换)"""
    if os.name != "nt" or not hwnd:
        return
    try:
        u = ctypes.windll.user32
        u.SetForegroundWindow.argtypes = [wintypes.HWND]
        u.SetForegroundWindow.restype = wintypes.BOOL
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                               ctypes.POINTER(wintypes.DWORD)]
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD,
                                        wintypes.BOOL]
        u.AttachThreadInput.restype = wintypes.BOOL
        u.BringWindowToTop.argtypes = [wintypes.HWND]
        u.BringWindowToTop.restype = wintypes.BOOL
        u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        cur = u.GetForegroundWindow()
        cur_tid = u.GetWindowThreadProcessId(cur, None)
        tgt_tid = u.GetWindowThreadProcessId(hwnd, None)
        u.ShowWindow(hwnd, 9)                 # SW_RESTORE
        if cur_tid and cur_tid != tgt_tid:
            u.AttachThreadInput(cur_tid, tgt_tid, True)
            try:
                u.BringWindowToTop(hwnd)
                u.SetForegroundWindow(hwnd)
            finally:
                u.AttachThreadInput(cur_tid, tgt_tid, False)
        else:
            u.BringWindowToTop(hwnd)
            u.SetForegroundWindow(hwnd)
    except Exception:
        pass


def send_unicode_char(ch):
    """通过 SendInput(KEYEVENTF_UNICODE) 向当前焦点窗口输入一个字符(全局)"""
    if os.name != "nt" or not ch:
        return
    try:
        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.c_void_p)]

        class INPUT(ctypes.Structure):
            class _I(ctypes.Union):
                # union 需与最大成员 MOUSEINPUT(32 字节) 等宽, 否则 SendInput
                # 报 ERROR_INVALID_PARAMETER(87), 字符不会真正输入
                _fields_ = [("ki", KEYBDINPUT), ("mi", ctypes.c_byte * 32)]
            _anonymous_ = ("i",)
            _fields_ = [("type", wintypes.DWORD), ("i", _I)]

        KEYEVENTF_UNICODE = 0x0004
        KEYEVENTF_KEYUP = 0x0002
        inp = INPUT()
        inp.type = 1
        inp.ki.wVk = 0
        inp.ki.wScan = ord(ch)
        inp.ki.dwFlags = KEYEVENTF_UNICODE
        inp.ki.time = 0
        inp.ki.dwExtraInfo = None
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT),
                                     ctypes.c_int]
        user32.SendInput.restype = wintypes.UINT
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        inp.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    except Exception:
        pass


# ---------- 自启动 ----------

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


def _autostart_cmd():
    if getattr(sys, "frozen", False):
        return '"%s"' % sys.executable
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    entry = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "schedule_app.py")
    return '"%s" "%s"' % (pyw, entry)


def set_autostart(enabled, hklm=False):
    if os.name != "nt":
        return
    import winreg
    if hklm:
        try:
            key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE,
                                   r"Software\Microsoft\Windows\CurrentVersion\Run")
            try:
                if enabled:
                    winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ,
                                      _autostart_cmd())
                else:
                    try:
                        winreg.DeleteValue(key, AUTOSTART_NAME)
                    except FileNotFoundError:
                        pass
            finally:
                winreg.CloseKey(key)
        except Exception:
            pass
        return
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Run")
    try:
        if enabled:
            winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, _autostart_cmd())
        else:
            try:
                winreg.DeleteValue(key, AUTOSTART_NAME)
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)


def elevate_autostart(enabled):
    if os.name != "nt":
        return
    try:
        flag = "1" if enabled else "0"
        if getattr(sys, "frozen", False):
            exe, args = sys.executable, "--autostart-set %s" % flag
        else:
            exe, args = sys.executable, '"%s" --autostart-set %s' % (
                os.path.abspath(sys.argv[0]), flag)
        shell32 = ctypes.windll.shell32
        shell32.ShellExecuteW.argtypes = [wintypes.HWND, wintypes.LPCWSTR,
                                          wintypes.LPCWSTR, wintypes.LPCWSTR,
                                          wintypes.LPCWSTR, ctypes.c_int]
        shell32.ShellExecuteW.restype = ctypes.c_void_p
        shell32.ShellExecuteW(None, "runas", exe, args, None, 1)
    except Exception:
        pass


# ---------- 托盘 + 全局热键 ----------

_TRAY_WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND,
                                   wintypes.UINT, wintypes.WPARAM,
                                   wintypes.LPARAM)


class TrayIcon:
    """Windows 托盘图标 + 全局热键(纯 ctypes)。双击恢复, 右键菜单。"""

    NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
    NIF_MESSAGE, NIF_ICON, NIF_TIP = 1, 2, 4
    WM_TRAY = 0x8000
    WM_HOTKEY = 0x0312
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
        self._hotkeys = {}
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
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int,
                                          wintypes.UINT, wintypes.UINT]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.UnregisterHotKey.restype = wintypes.BOOL
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
        if msg == self.WM_HOTKEY:
            cb = self._hotkeys.get(wp)
            if cb:
                try:
                    cb()
                except Exception:
                    pass
            return 0
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

    def register_hotkey(self, hotkey_id, mod, vk, callback):
        self._hotkeys[hotkey_id] = callback
        return bool(ctypes.windll.user32.RegisterHotKey(self._hwnd, hotkey_id,
                                                        mod, vk))

    def unregister_hotkey(self, hotkey_id):
        self._hotkeys.pop(hotkey_id, None)
        if self._hwnd:
            try:
                ctypes.windll.user32.UnregisterHotKey(self._hwnd, hotkey_id)
            except Exception:
                pass

    def delete(self):
        for hid in list(self._hotkeys):
            self.unregister_hotkey(hid)
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
