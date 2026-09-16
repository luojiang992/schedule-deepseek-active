# -*- coding: utf-8 -*-
"""「历史记录」标签页"""
import datetime

from .. import model
from ..model import (classify, fmt_dt, history_date, date_range_ok, kw_ok,
                     flag_markers, get_children, CAT_LABEL, make_template_from)


class HistoryTabMixin:
    def _build_history_tab(self, nb, tk, ttk):
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
        ttk.Button(bar3, text="📋 复制为模板", command=self.on_history_copy_template).pack(side="left", padx=4)
        ttk.Button(bar3, text="⇩ 导出 CSV", command=self.on_export_csv).pack(side="left", padx=4)
        ttk.Button(bar3, text="ⓘ 详情", command=self.on_detail_hist).pack(side="left", padx=4)

        wrap2 = ttk.Frame(self.tab_hist)
        wrap2.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        cols2 = ("cat", "title", "rec_date", "deadline", "note")
        self.tree_hist = ttk.Treeview(wrap2, columns=cols2, show="headings",
                                      selectmode="browse")
        for cid, text, w, anchor in (
                ("cat", "类型", 100, "center"),
                ("title", "标题", 230, "w"),
                ("rec_date", "记录日期", 130, "center"),
                ("deadline", "时间", 220, "center"),
                ("note", "备注", 200, "w")):
            self.tree_hist.heading(cid, text=text)
            self.tree_hist.column(cid, width=int(w * self.dpi_scale), anchor=anchor,
                                  stretch=(cid == "note"))
        sb2 = ttk.Scrollbar(wrap2, orient="vertical", command=self.tree_hist.yview)
        self.tree_hist.configure(yscrollcommand=sb2.set)
        self.tree_hist.pack(side="left", fill="both", expand=True)
        sb2.pack(side="right", fill="y")
        self.tree_hist.bind("<Double-1>", lambda e: self.on_detail_hist())
        self.tree_hist.tag_configure("done", background=self.c("row_normal"),
                                     foreground=self.c("fg_done"))
        self.tree_hist.tag_configure("cancelled", background=self.c("row_normal"),
                                     foreground=self.c("fg_cancel"))
        self.tree_hist.tag_configure("expired", background=self.c("row_over"),
                                     foreground=self.c("fg"))

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
                self._task_time_text(t), note), tags=(st,))

    def _on_search(self, ev):
        if self._search_job:
            try:
                self.root.after_cancel(self._search_job)
            except Exception:
                pass
        self._search_job = self.root.after(250, self.refresh_hist)

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
            model.save_tasks(self.tasks)
            self.refresh_all()

    def on_history_copy_template(self):
        from ..dialogs import AddDialog
        sel = self.tree_hist.selection()
        if not sel:
            self._info("请先在历史列表中选择一条记录。")
            return
        task = next((t for t in self.tasks if t["id"] == sel[0]), None)
        if task is None:
            return
        AddDialog(self, task=make_template_from(task), template=True)

    def on_detail_hist(self):
        from ..dialogs import DetailDialog
        sel = self.tree_hist.selection()
        if sel:
            task = next((t for t in self.tasks if t["id"] == sel[0]), None)
            if task:
                DetailDialog(self.root, task, self.dpi_scale)

    def on_export_csv(self):
        tk, ttk, messagebox, filedialog, _ = self._need_tk()
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
                         self._task_time_text(t),
                         fmt_dt(history_date(t).isoformat(timespec="minutes")
                                if history_date(t) else ""),
                         t.get("created_at", "")))
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                import csv
                w = csv.writer(f)
                w.writerow(["类型", "标题", "备注", "时间", "记录日期", "创建时间"])
                w.writerows(rows)
            self._toast("已导出 %d 条历史记录" % len(rows))
        except Exception as e:
            self._err("导出失败: %s" % e)
