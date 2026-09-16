# -*- coding: utf-8 -*-
"""「工具」标签页: 调用 data 同级 tools/ 文件夹中的外部 exe / .lnk 快捷方式"""
import os
import ctypes
from ctypes import wintypes

from ..paths import TOOLS_DIR


class ToolsTabMixin:
    def _build_tools_tab(self, nb, tk, ttk):
        self.tab_tools = ttk.Frame(nb)
        nb.add(self.tab_tools, text="  工具  ")
        bar = ttk.Frame(self.tab_tools)
        bar.pack(fill="x", padx=4, pady=4)
        ttk.Button(bar, text="▶ 启动选中", command=self.on_tool_launch).pack(side="left", padx=(0, 6))
        self.tools_admin_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="以管理员身份启动", variable=self.tools_admin_var).pack(side="left", padx=4)
        ttk.Button(bar, text="⟳ 重新扫描", command=self.refresh_tools).pack(side="left", padx=6)
        ttk.Button(bar, text="📁 打开 tools 文件夹", command=self.on_tools_open_dir).pack(side="left", padx=6)
        ttk.Label(bar, text="工具目录: %s（放 exe 或 .lnk 快捷方式即可在此调用）" % TOOLS_DIR,
                  foreground=self.c("fg_done")).pack(side="left", padx=10)

        wrap = ttk.Frame(self.tab_tools)
        wrap.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self.tools_tree = ttk.Treeview(wrap, columns=("name", "size"), show="headings")
        self.tools_tree.heading("name", text="程序 / 快捷方式")
        self.tools_tree.column("name", width=360, anchor="w")
        self.tools_tree.heading("size", text="大小 (KB)")
        self.tools_tree.column("size", width=120, anchor="e")
        self.tools_tree.pack(fill="both", expand=True)
        self.tools_tree.bind("<Double-1>", lambda e: self.on_tool_launch())
        self.refresh_tools()

    def refresh_tools(self):
        self.tools_tree.delete(*self.tools_tree.get_children())
        os.makedirs(TOOLS_DIR, exist_ok=True)
        for fn in sorted(os.listdir(TOOLS_DIR)):
            full = os.path.join(TOOLS_DIR, fn)
            low = fn.lower()
            if os.path.isfile(full) and (low.endswith(".exe") or low.endswith(".lnk")):
                try:
                    size = os.path.getsize(full) // 1024
                except Exception:
                    size = 0
                kind = "快捷方式" if low.endswith(".lnk") else "程序"
                self.tools_tree.insert("", "end", iid=full,
                                       values=("%s (%s)" % (fn, kind), size))

    def _tools_selected(self):
        sel = self.tools_tree.selection()
        if sel and os.path.isfile(sel[0]):
            return sel[0]
        return None

    def on_tool_launch(self):
        path = self._tools_selected()
        if not path:
            self._info("请先选择要启动的工具（tools 文件夹中的 exe 或 .lnk 快捷方式）。")
            return
        try:
            if self.tools_admin_var.get():
                # 以管理员身份启动(UAC); ShellExecute 可解析 .lnk 目标
                shell32 = ctypes.windll.shell32
                shell32.ShellExecuteW.argtypes = [wintypes.HWND, wintypes.LPCWSTR,
                                                  wintypes.LPCWSTR, wintypes.LPCWSTR,
                                                  wintypes.LPCWSTR, ctypes.c_int]
                shell32.ShellExecuteW.restype = ctypes.c_void_p
                shell32.ShellExecuteW(None, "runas", path, None,
                                      os.path.dirname(path) or None, 1)
            else:
                # os.startfile 原生支持 .lnk 快捷方式与 .exe
                os.startfile(path)
            self._toast("已启动: %s" % os.path.basename(path))
        except Exception as e:
            self._err("启动失败: %s" % e)

    def on_tools_open_dir(self):
        os.makedirs(TOOLS_DIR, exist_ok=True)
        try:
            os.startfile(TOOLS_DIR)
        except Exception:
            pass
