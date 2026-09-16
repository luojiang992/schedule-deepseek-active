# -*- coding: utf-8 -*-
"""调试: 构造 App + AddDialog, 捕获构造异常并检查按钮是否存在"""
import sys, traceback
sys.path.insert(0, r"D:\000MYfile\workspace\DScode")
import os
os.environ["DSH_SCHED_SKIP_ELEVATE"] = "1"

import tkinter as tk
from schedapp.app import App, need_tk
from schedapp import dialogs

tk_, ttk, _, _, _ = need_tk()
root = tk.Tk()
root.withdraw()
app = App(root, with_tray=False)
root.update_idletasks()

print("开始构造 AddDialog...", flush=True)
try:
    dlg = dialogs.AddDialog(app)
    root.update()
    print("AddDialog 构造成功", flush=True)
    # 检查按钮(递归遍历, ttk.Frame 不是 tk.Frame 的实例)
    def walk(w):
        for c in w.winfo_children():
            yield c
            yield from walk(c)

    bottom_frames = [w for w in dlg.win.winfo_children()
                     if w.winfo_class() == "TFrame"
                     and w.pack_info().get("side") == "bottom"]
    print("底部条 TFrame 数:", len(bottom_frames), flush=True)
    all_btns = [w.cget("text") for w in walk(dlg.win)
                if w.winfo_class() == "TButton"]
    print("窗口内全部 TButton:", all_btns, flush=True)
    dlg.win.destroy()
except Exception:
    print("AddDialog 构造异常:", flush=True)
    traceback.print_exc()

root.destroy()
print("done", flush=True)
