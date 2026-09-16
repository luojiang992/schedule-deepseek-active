# -*- coding: utf-8 -*-
"""GUI 冒烟 + 托盘/全局热键测试"""
import os

from . import paths, winapi
from .paths import HK_SYMBOL, MOD_CONTROL, MOD_SHIFT


def run_smoke():
    winapi.enable_dpi_awareness()
    if os.name == "nt":
        try:
            ti = winapi.TrayIcon("日程管理冒烟测试", lambda: None, lambda: None,
                                 icon=paths.icon_path())
            ok1 = ti.register_hotkey(HK_SYMBOL, MOD_CONTROL | MOD_SHIFT, 0x47,
                                     lambda: None)
            print("托盘创建: 成功; 全局热键注册: %s" % ok1)
            ti.unregister_hotkey(HK_SYMBOL)
            ti.delete()
        except Exception as e:
            print("托盘/热键失败: %s" % e)
            return 1
    from .app import App, need_tk
    tk, ttk, _, _, _ = need_tk()
    root = tk.Tk()
    root.withdraw()
    app = App(root, with_tray=False)
    root.update_idletasks()
    root.after(1500, root.destroy)
    root.mainloop()
    print("GUI 冒烟测试通过（全部标签页构建成功）")
    return 0
