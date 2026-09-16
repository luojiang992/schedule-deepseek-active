# -*- coding: utf-8 -*-
"""App 主类: 组装各标签页 Mixin + 共享基础设施"""
import os
import re
import ctypes
from ctypes import wintypes

from . import model, paths, winapi
from .paths import (APP_NAME, VERSION, NOTES_FILE, DATA_DIR, HOTKEY_PRESETS,
                    HK_SYMBOL, HK_SNIPPET, CAT_LABEL)
from .tabs.main_tab import MainTabMixin
from .tabs.history_tab import HistoryTabMixin
from .tabs.notes_tab import NotesTabMixin
from .tabs.calendar_tab import CalendarTabMixin
from .tabs.board_tab import BoardTabMixin
from .tabs.tools_tab import ToolsTabMixin


def need_tk():
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog, colorchooser
    return tk, ttk, messagebox, filedialog, colorchooser


def _hex_to_rgb(s):
    s = (s or "#f4f6f7").lstrip("#")
    try:
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return (0xf4, 0xf6, 0xf7)


class App(MainTabMixin, HistoryTabMixin, NotesTabMixin, CalendarTabMixin,
          BoardTabMixin, ToolsTabMixin):
    def __init__(self, root, with_tray=False):
        self.root = root
        self.settings = model.paths.load_settings()
        root.title(APP_NAME)

        self.dpi_scale = 1.0
        try:
            dpi = root.winfo_fpixels("1i")
            root.tk.call("tk", "scaling", max(dpi / 72.0, 1.0))
            self.dpi_scale = max(dpi / 96.0, 1.0)
        except Exception:
            pass
        s = self.dpi_scale
        self._restore_geometry(default="%dx%d" % (int(1200 * s), int(800 * s)))
        root.minsize(int(900 * s), int(580 * s))

        self.tasks = model.load_tasks()
        self.tray = None
        self.sym_win = None
        self.snip_win = None
        self.active_popup = None
        self._geo_job = None
        self._search_job = None
        self._notes_render_job = None
        self._latex_hide_job = None
        self._bg_size = (0, 0)
        self.bg_win = None
        self.bg_canvas_win = None
        self.bg_photo_full = None
        self._prev_fg = None
        self._toast_win = None
        self._toast_lbl = None
        self._toast_job = None

        # 画板状态
        self.board_base = None
        self.board_strokes = []
        self.board_color = "#ff0000"
        self.board_eraser = False
        self.board_width = 6
        self.board_drawing = None
        self.board_photo = None

        self._build_ui()
        self.apply_theme()
        self.refresh_all()
        self._startup_remind()

        root.bind("<Configure>", self._on_configure)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind_all("<Control-g>", lambda e: self.toggle_symbols())
        if with_tray and os.name == "nt":
            self._init_tray()
            self.apply_hotkeys()
        self.root.after(30000, self._tick)

    # ---------- 工具 ----------
    def _need_tk(self):
        return need_tk()

    def sz(self, v):
        return int(v * getattr(self, "dpi_scale", 1.0))

    def refresh_all(self):
        self.refresh_main()
        self.refresh_hist()
        self.refresh_calendar()

    # ---------- 窗口 / 背景(双窗口) / 半透明 ----------
    def _restore_geometry(self, default):
        g = self.settings.get("geometry") or default
        try:
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
                paths.save_settings(self.settings)
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
            self._sync_bg_win()
        except Exception:
            pass
        if self._geo_job:
            try:
                self.root.after_cancel(self._geo_job)
            except Exception:
                pass
        self._geo_job = self.root.after(700, self._save_geometry)

    def _render_bg(self):
        """背景图绘制在主窗口正后方的不透明背景窗口上, 完整不透明度"""
        path = self.settings.get("background")
        if not path or not os.path.exists(path):
            self._hide_bg_win()
            return
        try:
            from PIL import Image, ImageTk
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            if w < 20 or h < 20:
                return
            if self.bg_win is None:
                tk, _, _, _, _ = need_tk()
                self.bg_win = tk.Toplevel(self.root)
                self.bg_win.overrideredirect(True)
                self.bg_canvas_win = tk.Canvas(self.bg_win, highlightthickness=0, bd=0)
                self.bg_canvas_win.pack(fill="both", expand=True)
                try:
                    self.bg_win.lower(self.root)
                except Exception:
                    pass
            img = Image.open(path).convert("RGBA")
            img.thumbnail((2048, 2048), Image.LANCZOS)
            iw, ih = img.size
            scale = max(w / iw, h / ih)
            img = img.resize((max(1, int(iw * scale)), max(1, int(ih * scale))),
                             Image.LANCZOS)
            left = (img.width - w) // 2
            top = (img.height - h) // 2
            img = img.crop((left, top, left + w, top + h))
            self.bg_photo_full = ImageTk.PhotoImage(img.convert("RGB"))
            self.bg_canvas_win.delete("all")
            self.bg_canvas_win.create_image(0, 0, anchor="nw", image=self.bg_photo_full)
            self._sync_bg_win()
            try:
                self.bg_win.deiconify()
            except Exception:
                pass
            # 修复: 改变窗口大小时背景窗可能被置顶 -> 每次同步后强制压回主窗口下方
            try:
                self.bg_win.lower(self.root)
            except Exception:
                pass
        except Exception:
            self._hide_bg_win()

    def _sync_bg_win(self):
        if self.bg_win is None:
            return
        try:
            x = self.root.winfo_rootx()
            y = self.root.winfo_rooty()
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            if w > 20 and h > 20:
                self.bg_win.geometry("%dx%d+%d+%d" % (w, h, x, y))
                try:
                    self.bg_win.lower(self.root)
                except Exception:
                    pass
        except Exception:
            pass

    def _hide_bg_win(self):
        if self.bg_win is not None:
            try:
                self.bg_win.withdraw()
            except Exception:
                pass

    def _destroy_bg_win(self):
        if self.bg_win is not None:
            try:
                self.bg_win.destroy()
            except Exception:
                pass
            self.bg_win = None

    def _apply_alpha(self):
        try:
            v = float(self.settings.get("window_alpha", 0.92))
            v = max(0.7, min(1.0, v))
            bg = self.settings.get("background")
            if bg and os.path.exists(bg):
                v = min(v, 0.75)
            self.root.attributes("-alpha", v)
        except Exception:
            pass

    # ---------- 界面搭建 ----------
    def _build_ui(self):
        tk, ttk, _, _, _ = need_tk()
        self.font_base = ("Microsoft YaHei UI", 10)
        nb = ttk.Notebook(self.root, padding=(12, 8))
        nb.pack(fill="both", expand=True, padx=4, pady=(4, 0))
        self.nb = nb
        self._build_main_tab(nb, tk, ttk)
        self._build_history_tab(nb, tk, ttk)
        self._build_notes_tab(nb, tk, ttk)
        self._build_calendar_tab(nb, tk, ttk)
        self._build_board_tab(nb, tk, ttk)
        self._build_tools_tab(nb, tk, ttk)

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
        try:
            self.line_canvas.configure(bg=self.c("card"))
        except Exception:
            pass
        self._tag_main_tree()
        self._apply_alpha()

    def toggle_theme(self):
        self.settings["dark"] = not self.dark
        paths.save_settings(self.settings)
        self.apply_theme()
        self.refresh_all()

    # ---------- 托盘 / 全局热键 ----------
    def _init_tray(self):
        try:
            tk, _, _, _, _ = need_tk()
            self.tray_menu = tk.Menu(self.root, tearoff=0)
            self.tray_menu.add_command(label="显示主窗口", command=self.show_window)
            self.tray_menu.add_separator()
            self.tray_menu.add_command(label="退出", command=self.quit_app)
            self.tray = winapi.TrayIcon(APP_NAME, self.show_window,
                                        self._tray_right, icon=paths.icon_path())
        except Exception:
            self.tray = None

    def apply_hotkeys(self):
        if self.tray is None:
            return
        for hid, key_name, cb in (
                (HK_SYMBOL, self.settings.get("symbol_hotkey"), self.toggle_symbols),
                (HK_SNIPPET, self.settings.get("snippet_hotkey"), self.toggle_snippets)):
            try:
                self.tray.unregister_hotkey(hid)
            except Exception:
                pass
            mod, vk = model.paths.HOTKEY_PRESETS.get(key_name, (0, 0))
            if mod or vk:
                try:
                    self.tray.register_hotkey(hid, mod, vk, cb)
                except Exception:
                    pass

    def _tray_right(self):
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
            if self.bg_win is not None:
                try:
                    self.bg_win.deiconify()
                except Exception:
                    pass
        except Exception:
            pass

    def on_close(self):
        self._save_geometry()
        self._save_notes()
        if self.settings.get("minimize_to_tray") and self.tray is not None:
            self.root.withdraw()
            self._hide_bg_win()
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
        self._destroy_bg_win()
        try:
            self.root.destroy()
        except Exception:
            pass

    # ---------- 设置 / toast ----------
    def open_settings(self, symbols_tab=False):
        from .dialogs import SettingsDialog
        SettingsDialog(self, symbols_tab=symbols_tab)

    def _toast(self, msg):
        tk, _, _, _, _ = need_tk()
        try:
            if self._toast_win is None or not self._toast_win.winfo_exists():
                self._toast_win = tk.Toplevel(self.root)
                self._toast_win.overrideredirect(True)
                self._toast_win.configure(bg="#2c3e50")
                self._toast_lbl = tk.Label(self._toast_win, text="", bg="#2c3e50",
                                           fg="#ffffff", padx=16, pady=9,
                                           font=("Microsoft YaHei UI", 10))
                self._toast_lbl.pack()
            self._toast_lbl.configure(text=msg)
            try:
                x = self.root.winfo_rootx() + self.root.winfo_width() - 360
                y = self.root.winfo_rooty() + self.root.winfo_height() - 70
                self._toast_win.geometry("+%d+%d" % (max(0, x), max(0, y)))
            except Exception:
                pass
            self._toast_win.deiconify()
            self._toast_win.lift()
            self._toast_win.attributes("-topmost", True)
            if self._toast_job:
                try:
                    self.root.after_cancel(self._toast_job)
                except Exception:
                    pass
            self._toast_job = self.root.after(2500, self._toast_hide)
        except Exception:
            pass

    def _toast_hide(self):
        try:
            if self._toast_win is not None:
                self._toast_win.withdraw()
        except Exception:
            pass

    # ---------- 符号小窗 / 句子粘贴板(可全局) ----------
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
        self._prev_fg = winapi.get_foreground_hwnd()
        self.sym_win = tk.Toplevel(self.root)
        self.sym_win.title("符号输入（%s 全局唤起）" % self.settings.get("symbol_hotkey"))
        self.sym_win.attributes("-topmost", True)
        try:
            self.sym_win.attributes("-toolwindow", True)
        except Exception:
            pass
        self.active_popup = self.sym_win
        for row in model.load_symbol_rows():
            f = tk.Frame(self.sym_win)
            f.pack(fill="x", padx=5, pady=1)
            for ch in row:
                tk.Button(f, text=ch, width=2, font=("Segoe UI", 12),
                          command=lambda c=ch: self._insert_text(c)).pack(
                    side="left", padx=1, pady=1)
        btns = tk.Frame(self.sym_win)
        btns.pack(fill="x", pady=3)
        tk.Button(btns, text="编辑符号列表…", command=self._open_symbols_editor).pack(side="left", padx=10)
        tk.Button(btns, text="关闭", command=self.sym_win.destroy).pack(side="right", padx=10)
        self.sym_win.protocol("WM_DELETE_WINDOW", self.sym_win.destroy)

    def _open_symbols_editor(self):
        if getattr(self, "sym_win", None) is not None:
            try:
                self.sym_win.destroy()
            except Exception:
                pass
            self.sym_win = None
        self.open_settings(symbols_tab=True)

    def toggle_snippets(self):
        if getattr(self, "snip_win", None) is not None:
            try:
                if self.snip_win.winfo_exists():
                    self.snip_win.destroy()
                    self.snip_win = None
                    return
            except Exception:
                self.snip_win = None
        tk, ttk, _, _, _ = need_tk()
        self._prev_fg = winapi.get_foreground_hwnd()
        self.snip_win = tk.Toplevel(self.root)
        self.snip_win.title("快捷句子（%s 全局唤起）" % self.settings.get("snippet_hotkey"))
        self.snip_win.attributes("-topmost", True)
        try:
            self.snip_win.attributes("-toolwindow", True)
        except Exception:
            pass
        self.active_popup = self.snip_win
        self.snip_list = tk.Listbox(self.snip_win, width=46, height=12,
                                    font=("Microsoft YaHei UI", 10))
        self.snip_list.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        for it in model.load_snippets():
            self.snip_list.insert("end", it)
        self.snip_list.bind("<Double-1>", lambda e: self._snip_insert_selected())
        edrow = ttk.Frame(self.snip_win)
        edrow.pack(fill="x", padx=6, pady=4)
        self.snip_entry = tk.Entry(edrow, font=("Microsoft YaHei UI", 10))
        self.snip_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.snip_entry.bind("<Return>", lambda e: self._snip_add())
        ttk.Button(edrow, text="添加", command=self._snip_add).pack(side="left", padx=2)
        ttk.Button(edrow, text="删除选中", command=self._snip_del).pack(side="left", padx=2)
        ttk.Button(edrow, text="插入选中", command=self._snip_insert_selected).pack(side="left", padx=2)
        self.snip_win.protocol("WM_DELETE_WINDOW", self.snip_win.destroy)

    def _snip_items(self):
        return list(self.snip_list.get(0, "end"))

    def _snip_save(self):
        model.save_snippets(self._snip_items())

    def _snip_add(self):
        text = self.snip_entry.get().strip()
        if text:
            self.snip_list.insert("end", text)
            self.snip_entry.delete(0, "end")
            self._snip_save()

    def _snip_del(self):
        sel = self.snip_list.curselection()
        if sel:
            self.snip_list.delete(sel[0])
            self._snip_save()

    def _snip_insert_selected(self):
        sel = self.snip_list.curselection()
        if sel:
            self._insert_text(self.snip_list.get(sel[0]))

    def _insert_text(self, text):
        w = self.root.focus_get()
        if w is not None:
            try:
                if str(w.winfo_class()) in ("Text", "Entry"):
                    w.insert("insert", text)
                    return
            except Exception:
                pass
        win = self.active_popup
        if win is not None:
            try:
                win.withdraw()
            except Exception:
                pass
            winapi.force_foreground(getattr(self, "_prev_fg", None))
            self.root.after(150, lambda: winapi.send_unicode_char(text))
            self.root.after(380, lambda: self._reshow_popup(win))

    def _reshow_popup(self, win):
        try:
            win.deiconify()
            win.lift()
            win.attributes("-topmost", True)
        except Exception:
            pass

    # ---------- 提醒 / 定时刷新 ----------
    def _startup_remind(self):
        import datetime
        now = datetime.datetime.now()
        expired = [t for t in self.tasks if model.classify(t, now) == "expired"]
        due_today = [t for t in self.tasks
                     if model.classify(t, now) == "active" and t.get("deadline")
                     and model.day_key(model.parse_dt(t["deadline"])) == model.day_key(now)]
        if expired or due_today:
            self._info("今日提醒\n\n已过期未完成: %d 项\n今日到期: %d 项\n"
                       "（详见「进行中」视图红色/黄色条目与剩余时间列）"
                       % (len(expired), len(due_today)))

    def _tick(self):
        try:
            if self.nb.index("current") == 0:
                self.refresh_main()
            self.refresh_calendar()
        except Exception:
            pass
        try:
            self.root.after(30000, self._tick)
        except Exception:
            pass

    # ---------- 弹窗 ----------
    def _ask(self, title, msg):
        _, _, messagebox, _, _ = need_tk()
        return messagebox.askyesno(title, msg, parent=self.root)

    def _ask3(self, title, msg):
        _, _, messagebox, _, _ = need_tk()
        return messagebox.askyesnocancel(title, msg, parent=self.root)

    def _info(self, msg):
        _, _, messagebox, _, _ = need_tk()
        messagebox.showinfo(APP_NAME, msg, parent=self.root)

    def _err(self, msg):
        _, _, messagebox, _, _ = need_tk()
        messagebox.showerror(APP_NAME, msg, parent=self.root)
