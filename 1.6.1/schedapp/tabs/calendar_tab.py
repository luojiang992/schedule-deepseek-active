# -*- coding: utf-8 -*-
"""「日历」标签页(tkcalendar): 查看日程与历史日程(周期/事件多日展开)"""
import datetime

from .. import model
from ..model import classify, CAT_LABEL


class CalendarTabMixin:
    def _build_calendar_tab(self, nb, tk, ttk):
        try:
            from tkcalendar import Calendar
        except Exception:
            self.tab_cal = ttk.Frame(nb)
            nb.add(self.tab_cal, text="  日历  ")
            ttk.Label(self.tab_cal, text="日历组件不可用（需要 tkcalendar 库）",
                      padding=20).pack()
            self.cal = None
            return
        self.tab_cal = ttk.Frame(nb)
        nb.add(self.tab_cal, text="  日历  ")
        body = ttk.Panedwindow(self.tab_cal, orient="horizontal")
        body.pack(fill="both", expand=True, padx=4, pady=4)
        left = ttk.Frame(body)
        body.add(left, weight=2)
        self.cal = Calendar(left, selectmode="day", date_pattern="yyyy-mm-dd",
                            firstweekday="monday", showothermonthdays=False,
                            font=("Microsoft YaHei UI", 9),
                            headersforeground="#2e86c1")
        self.cal.pack(fill="both", expand=True, padx=4, pady=4)
        for tag, bg in (("active", "#4cc9f0"), ("done", "#7ee2a8"),
                        ("cancelled", "#c792ea"), ("expired", "#ff7a7a")):
            try:
                self.cal.tag_config(tag, background=bg, foreground="black")
            except Exception:
                pass
        self.cal.bind("<<CalendarSelected>>", self._cal_selected)

        right = ttk.Frame(body)
        body.add(right, weight=1)
        self.cal_head = ttk.Label(right, text="", font=("Microsoft YaHei UI", 11, "bold"))
        self.cal_head.pack(anchor="w", pady=(2, 4))
        cols = ("type", "title", "time")
        self.cal_tree = ttk.Treeview(right, columns=cols, show="headings",
                                     selectmode="browse")
        for cid, text, w in (("type", "类型", 90), ("title", "标题", 220),
                             ("time", "时间", 170)):
            self.cal_tree.heading(cid, text=text)
            self.cal_tree.column(cid, width=w, anchor="w")
        self.cal_tree.pack(fill="both", expand=True)
        self.cal_tree.bind("<Double-1>", self._cal_open_detail)

    def refresh_calendar(self):
        if getattr(self, "cal", None) is None:
            return
        try:
            self.cal.calevent_remove("all")
        except Exception:
            pass
        now = datetime.datetime.now()
        today = datetime.date.today()
        self._cal_map = {}
        for t in self.tasks:
            st = classify(t, now)
            tag = st if st in ("active", "done", "cancelled", "expired") else "active"
            dates = model.iter_occurrences(t, today)
            for d in dates:
                ds = d.strftime("%Y-%m-%d")
                self._cal_map.setdefault(ds, []).append((t, st))
                try:
                    self.cal.calevent_create(d, t["title"][:18], tag)
                except Exception:
                    pass

    def _cal_selected(self, e=None):
        if getattr(self, "cal", None) is None:
            return
        try:
            d = self.cal.get_date()
        except Exception:
            d = None
        self._cal_fill(d)

    def _cal_fill(self, date_str):
        try:
            self.cal_tree.delete(*self.cal_tree.get_children())
            if not date_str:
                return
            self.cal_head.configure(text="%s 的日程" % date_str)
            items = self._cal_map.get(str(date_str), []) if hasattr(self, "_cal_map") else []
            for t, st in items:
                self.cal_tree.insert("", "end", iid=t["id"], values=(
                    CAT_LABEL.get(st, "进行中"), t["title"], self._task_time_text(t)))
            if not items:
                self.cal_tree.insert("", "end", values=("—", "当日无日程", "—"))
        except Exception:
            pass

    def _cal_open_detail(self, ev):
        from ..dialogs import DetailDialog
        sel = self.cal_tree.selection()
        if not sel:
            return
        task = next((t for t in self.tasks if t["id"] == sel[0]), None)
        if task:
            DetailDialog(self.root, task, self.dpi_scale)
