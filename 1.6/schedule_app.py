# -*- coding: utf-8 -*-
"""
轻量级桌面日程管理软件（单文件版）v1.6.0 —— 入口
模块化实现位于 schedapp/ 包内。
"""
import sys
import os

from schedapp import paths, winapi
from schedapp.paths import AUTOSTART_NAME


def main():
    if "--selftest" in sys.argv:
        from schedapp.selftest import run_selftest
        sys.exit(run_selftest())
    if "--smoke" in sys.argv:
        from schedapp.smoke import run_smoke
        sys.exit(run_smoke())
    if "--autostart-set" in sys.argv:      # 提权回调: 写 HKCU + HKLM 后退出
        i = sys.argv.index("--autostart-set")
        if i + 1 < len(sys.argv):
            val = sys.argv[i + 1] == "1"
            try:
                winapi.set_autostart(val)
            except Exception:
                pass
            try:
                winapi.set_autostart(val, hklm=True)
            except Exception:
                pass
        sys.exit(0)
    if winapi.ensure_single_instance():
        return
    # 启动即获取管理员权限(UAC); 设 DSH_SCHED_SKIP_ELEVATE=1 可跳过(测试/受限环境)
    if not winapi.is_admin() and os.environ.get("DSH_SCHED_SKIP_ELEVATE") != "1":
        winapi.relaunch_elevated()
        return
    winapi.enable_dpi_awareness()
    from schedapp.app import App, need_tk
    tk, ttk, _, _, _ = need_tk()
    root = tk.Tk()
    App(root, with_tray=True)
    root.mainloop()


if __name__ == "__main__":
    main()
