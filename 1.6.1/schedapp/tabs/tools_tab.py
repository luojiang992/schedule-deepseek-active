# -*- coding: utf-8 -*-
"""「工具」标签页: 调用 data 同级 tools/ 文件夹中的 exe / .lnk 快捷方式 / .url 网页链接, 支持搜索过滤"""
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
        ttk.Label(bar, text="🔍 搜索:").pack(side="left", padx=(10, 2))
        self.tools_search_var = tk.StringVar()
        self.tools_search = ttk.Entry(bar, textvariable=self.tools_search_var, width=18)
        self.tools_search.pack(side="left", padx=(0, 4))
        self.tools_search.bind("<KeyRelease>", lambda e: self._tools_apply_filter())
        ttk.Button(bar, text="✕", width=3, command=self.tools_clear_search).pack(side="left")
        ttk.Label(bar, text="工具目录: %s（放 exe / .lnk / .url 即可在此调用）" % TOOLS_DIR,
                  foreground=self.c("fg_done")).pack(side="left", padx=10)

        wrap = ttk.Frame(self.tab_tools)
        wrap.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self.tools_tree = ttk.Treeview(wrap, columns=("name", "size"), show="headings")
        self.tools_tree.heading("name", text="程序 / 快捷方式 / 网页链接")
        self.tools_tree.column("name", width=420, anchor="w")
        self.tools_tree.heading("size", text="大小 (KB)")
        self.tools_tree.column("size", width=100, anchor="e")
        self.tools_tree.pack(fill="both", expand=True)
        self.tools_tree.bind("<Double-1>", lambda e: self.on_tool_launch())
        self._tools_all = []
        self.refresh_tools()

    @staticmethod
    def _url_target(full):
        """读取 .url 快捷方式中的 URL 目标"""
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line.lower().startswith("url="):
                        return line[4:].strip()
        except Exception:
            pass
        return ""

    def refresh_tools(self):
        os.makedirs(TOOLS_DIR, exist_ok=True)
        self._tools_all = []
        for fn in sorted(os.listdir(TOOLS_DIR)):
            full = os.path.join(TOOLS_DIR, fn)
            low = fn.lower()
            if not os.path.isfile(full):
                continue
            if low.endswith(".exe"):
                kind = "程序"
            elif low.endswith(".lnk"):
                kind = "快捷方式"
            elif low.endswith(".url"):
                kind = "网页链接"
            else:
                continue
            try:
                size = os.path.getsize(full) // 1024
            except Exception:
                size = 0
            url = self._url_target(full) if low.endswith(".url") else ""
            self._tools_all.append((full, fn, kind, size, url))
        self._tools_apply_filter()

    def _tools_apply_filter(self):
        q = self.tools_search_var.get().strip().lower()
        self.tools_tree.delete(*self.tools_tree.get_children())
        for full, fn, kind, size, url in self._tools_all:
            if q and q not in fn.lower() and q not in url.lower():
                continue
            if kind == "网页链接":
                name = "%s (%s)" % (fn, url) if url else fn
            else:
                name = fn
            self.tools_tree.insert("", "end", iid=full,
                                   values=("%s (%s)" % (name, kind), size))

    def tools_clear_search(self):
        self.tools_search_var.set("")
        self._tools_apply_filter()
        self.tools_search.focus_set()

    def _tools_selected(self):
        sel = self.tools_tree.selection()
        if sel and os.path.isfile(sel[0]):
            return sel[0]
        return None

    def on_tool_launch(self):
        path = self._tools_selected()
        if not path:
            self._info("请先选择要启动的工具（tools 文件夹中的 exe / .lnk / .url）。")
            return
        is_url = path.lower().endswith(".url")
        try:
            if self.tools_admin_var.get() and not is_url:
                # 以管理员身份启动(UAC); ShellExecute 可解析 .lnk 目标
                shell32 = ctypes.windll.shell32
                shell32.ShellExecuteW.argtypes = [wintypes.HWND, wintypes.LPCWSTR,
                                                  wintypes.LPCWSTR, wintypes.LPCWSTR,
                                                  wintypes.LPCWSTR, ctypes.c_int]
                shell32.ShellExecuteW.restype = ctypes.c_void_p
                shell32.ShellExecuteW(None, "runas", path, None,
                                      os.path.dirname(path) or None, 1)
            else:
                # os.startfile 原生支持 .exe / .lnk; .url 会用默认浏览器打开
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
