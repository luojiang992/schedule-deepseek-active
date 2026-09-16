# -*- coding: utf-8 -*-
"""逻辑自测(不开界面)"""
import os
import sys
import uuid
import shutil
import datetime

from . import paths, model
from .paths import (MOD_ALT, MOD_CONTROL, HOTKEY_PRESETS, DEFAULT_SETTINGS,
                    DEFAULT_SYMBOL_ROWS)


def run_selftest():
    fails = []
    def ok(name, cond, detail=""):
        print(("  ok  " if cond else "FAIL  ") + name + (("  -> " + detail) if detail else ""))
        if not cond:
            fails.append(name)

    tmp = os.path.join(os.getcwd(), ".sched_selftest_" + uuid.uuid4().hex[:8])
    os.makedirs(tmp, exist_ok=True)
    # 重定向数据目录(需同时更新 paths 与 model 的导入副本)
    paths.DATA_DIR = tmp
    paths.DATA_FILE = os.path.join(tmp, "schedule.json")
    paths.SETTINGS_FILE = os.path.join(tmp, "settings.json")
    paths.NOTES_ROOT = os.path.join(tmp, "notes")
    paths.NOTES_FILE = os.path.join(tmp, "notes", "便签.txt")
    paths.SYMBOLS_FILE = os.path.join(tmp, "symbols.json")
    paths.SNIPPETS_FILE = os.path.join(tmp, "snippets.json")
    paths.TEMPLATES_FILE = os.path.join(tmp, "templates.json")
    paths.QUICKTIMES_FILE = os.path.join(tmp, "quicktimes.json")
    for k in ("DATA_DIR", "DATA_FILE", "SETTINGS_FILE", "NOTES_ROOT", "NOTES_FILE",
              "SYMBOLS_FILE", "SNIPPETS_FILE", "TEMPLATES_FILE", "QUICKTIMES_FILE"):
        setattr(model, k, getattr(paths, k))

    print("[1] 存储读写")
    tasks = [model.new_task("测试任务", note="备注内容", deadline="2099-01-01 09:00")]
    model.save_tasks(tasks)
    ok("文件已创建", os.path.exists(paths.DATA_FILE))
    ok("重读一致", model.load_tasks() == tasks)

    print("[2] 状态分类")
    ok("过期", model.classify(model.new_task("x", deadline="2000-01-01 08:00")) == "expired")
    ok("进行中", model.classify(model.new_task("x", deadline="2099-12-31 23:59")) == "active")

    print("[3] 倒计时")
    t0 = datetime.datetime(2099, 1, 1, 9, 0)
    ok("3天2时1分", model.fmt_remain("2099-01-04 11:01", t0) == "3天2时1分")
    ok("无截止 -> —", model.fmt_remain(None) == "—")

    print("[4] 事件校验与偏移分钟")
    ok("开始+截止合法", model.validate_dates("2026-08-30 09:00", "2026-08-30 18:00")[0])
    ok("只有开始(事件)", model.validate_dates("2026-08-30 09:00", "")[0])
    ok("开始晚于截止拒绝", not model.validate_dates("2026-08-31 09:00", "2026-08-30 18:00")[0])
    ok("150 = 偏移分钟", model.is_minute_offset("150"))
    ok("偏移解析: 12:00+150=14:30",
       model.resolve_deadline("2026-08-30 12:00", "150")[0] == "2026-08-30 14:30")

    print("[5] 周期推进")
    ok("daily", model.next_occurrence(datetime.datetime(2026, 8, 30, 18, 0), "daily",
                                      datetime.datetime(2026, 9, 1, 10, 0))
       == datetime.datetime(2026, 9, 1, 18, 0))
    ok("weekday 跳过周末", model.next_occurrence(
        datetime.datetime(2026, 8, 28, 18, 0), "weekday",
        datetime.datetime(2026, 8, 29, 0, 0)) == datetime.datetime(2026, 8, 31, 18, 0))

    print("[6] 标记/模板")
    t = model.new_task("任务")
    t["flag"] = "red"
    ok("红旗", model.flag_markers(t) == "🚩")
    src = model.new_task("历史任务", note="备注A", repeat="weekly",
                         deadline="2099-01-01 09:00")
    src["flag"] = "red"
    src["children"] = [model.new_child("子1")]
    src["status"] = "done"
    tmpl = model.make_template_from(src)
    ok("模板新任务", tmpl["status"] == "active" and tmpl["id"] != src["id"]
       and tmpl["title"] == "历史任务" and len(tmpl["children"]) == 1)
    ok("模板时间清空", tmpl["start"] is None and tmpl["deadline"] is None)

    print("[7] 设置/符号/句子/模板/快捷时间 JSON")
    paths.save_settings(dict(DEFAULT_SETTINGS))
    ok("设置往返", paths.load_settings() == dict(DEFAULT_SETTINGS))
    model.save_symbol_rows(list(DEFAULT_SYMBOL_ROWS))
    ok("符号往返", model.load_symbol_rows() == list(DEFAULT_SYMBOL_ROWS))
    model.save_snippets(["你好", "谢谢"])
    ok("句子往返", model.load_snippets() == ["你好", "谢谢"])
    model.save_templates([{"name": "开会", "title": "周会", "note": "", "start": None,
                           "deadline": None, "repeat": "weekly"}])
    ok("模板往返", model.load_templates()[0]["name"] == "开会")
    model.save_quicktimes([{"label": "测试", "kind": "days", "delta": 1,
                            "hour": 9, "minute": 30}])
    qt = model.load_quicktimes()[0]
    d = model.apply_quicktime(qt, datetime.datetime(2026, 8, 29, 12, 0))
    ok("快捷时间: 明天09:30", d == datetime.datetime(2026, 8, 30, 9, 30))

    print("[8] 便签目录扫描")
    model.ensure_notes_root()
    os.makedirs(os.path.join(paths.NOTES_ROOT, "工作"), exist_ok=True)
    paths.save_text_file(os.path.join(paths.NOTES_ROOT, "工作", "会议.txt"), "hi")
    os.makedirs(os.path.join(paths.NOTES_ROOT, "空分类"), exist_ok=True)
    found = model.scan_notes()
    ok("扫描到子目录笔记", any(r[0] == os.path.join("工作", "会议.txt") and not r[3]
                              for r in found))
    ok("空分类文件夹也显示", any(r[0] == "空分类" and r[3] for r in found))

    print("[9] 日历出现日期(周期/事件)")
    ev = model.new_task("事件", start="2026-08-30 09:00", deadline="2026-09-01 18:00")
    dates = model.iter_occurrences(ev, datetime.date(2026, 8, 29))
    ok("事件区间逐日(8/30~9/1)", [d.day for d in dates] == [30, 31, 1]
       and dates[-1].month == 9, str(dates))
    rep = model.new_task("周期", deadline="2026-08-28 09:00", repeat="weekly")
    ds = model.iter_occurrences(rep, datetime.date(2026, 8, 29))
    ok("周期展开≥10个且间隔7天", len(ds) >= 10 and (ds[1] - ds[0]).days == 7,
       "n=%d" % len(ds))

    print("[10] LaTeX 检测与渲染")
    spans = model_import_latex_spans()
    ok("检测 $..$ 片段", len(spans) == 2, str(spans))
    path, size, err = latex_render("\\frac{a}{b}", True)
    ok("matplotlib mathtext 渲染成功", path is not None and err is None,
       err or "")

    print("[11] 数据目录与迁移")
    exe_dir = os.path.join(os.getcwd(), ".sched_exe_test")
    os.makedirs(exe_dir, exist_ok=True)
    data_dir = os.path.join(exe_dir, "data")
    try:
        ok("冻结版基目录", paths.get_data_base(
            _frozen=True, _exe=os.path.join(exe_dir, "日程管理.exe"))
           == os.path.abspath(exe_dir))
        legacy = os.path.join(exe_dir, "notes.txt")
        paths.save_text_file(legacy, "旧便签内容")
        paths.migrate_legacy(exe_dir, data_dir)
        ok("旧文件迁移进 data/", os.path.exists(os.path.join(data_dir, "notes.txt")))
    finally:
        shutil.rmtree(exe_dir, ignore_errors=True)

    print("\n结果: %s" % ("全部通过" if not fails else "%d 项失败: %s" % (len(fails), fails)))
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if not fails else 1


def model_import_latex_spans():
    from . import render_latex
    return render_latex.find_latex_spans("公式 $x^2$ 与 $$\\frac{a}{b}$$ 测试")


def latex_render(expr, display):
    from . import render_latex
    return render_latex.render_latex_png(expr, display)
