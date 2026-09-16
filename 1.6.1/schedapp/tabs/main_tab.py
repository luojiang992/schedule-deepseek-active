# -*- coding: utf-8 -*-
"""「今日 / 进行中」标签页"""
import datetime

from .. import model
from ..model import (classify, parse_dt, fmt_dt, fmt_remain, dl_sort_key,
                     flag_markers, get_children, child_iid, split_child_iid,
                     new_task, new_child, update_task, save_tasks, now_iso,
                     next_occurrence, REPEAT_NAMES)


class MainTabMixin:
    def _build_main_tab(self, nb, tk, ttk):
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
        cols = ("status", "time", "remain", "note")
        self.tree_main = ttk.Treeview(wrap, columns=cols, show="tree headings",
                                      selectmode="browse")
        self.tree_main.heading("#0", text="标题")
        self.tree_main.column("#0", width=int(250 * self.dpi_scale), anchor="w",
                              stretch=True)
        for cid, text, w, anchor in (
                ("status", "状态", 90, "center"),
                ("time", "开始 ~ 截止", 230, "center"),
                ("remain", "剩余时间", 140, "center"),
                ("note", "备注", 180, "w")):
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
        self._tag_main_tree()

    def _tag_main_tree(self):
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

    def _roll_recurring(self, now):
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

    def _task_time_text(self, t):
        st = fmt_dt(t.get("start"))
        en = fmt_dt(t.get("deadline"))
        if st and en:
            return "%s ~ %s" % (st, en)
        if st:
            return "开始 %s" % st
        if en:
            return en
        return "—"

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
            dl_text = self._task_time_text(t)
            rp = t.get("repeat")
            if rp and REPEAT_NAMES.get(rp):
                dl_text += "(%s)" % REPEAT_NAMES[rp]
                summ = model.repeat_summary(t)
                if summ:
                    dl_text += " " + summ
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
        from ..dialogs import AddDialog
        AddDialog(self)

    def on_edit(self):
        from ..dialogs import AddDialog
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
            # 周期日程: 已完期数+1, 记录本次完成时间, 截止推进到下一周期, 保持待办
            task["completed_at"] = now_iso()
            model.complete_recurring(task)
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
        from ..dialogs import AddChildDialog
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
        task, child = self._selected_task_and_child()
        if child is not None:
            self._info("子日程暂不支持标记。")
            return
        if task is None:
            self._info("请先选择一个日程。")
            return
        tk, _, _, _, _ = self._need_tk()
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
            _, hexv = self._need_tk()[4].askcolor(parent=self.root,
                                                  title="选择标记颜色")
            if not hexv:
                return
            task["flag"] = hexv
        else:
            task["flag"] = kind
        if task["flag"] == "red":
            task["pinned"] = True
        save_tasks(self.tasks)
        self.refresh_main()

    def on_pin(self):
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

    def on_detail_main(self):
        from ..dialogs import DetailDialog
        task, _ = self._selected_task_and_child()
        if task:
            DetailDialog(self.root, task, self.dpi_scale)
