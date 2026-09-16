# -*- coding: utf-8 -*-
"""数据模型与业务逻辑(纯函数, 无 GUI 依赖)"""
import os
import re
import json
import uuid
import calendar
import datetime
import shutil

from . import paths
from .paths import (DATA_DIR, DATA_FILE, NOTES_ROOT, NOTES_FILE,
                    SYMBOLS_FILE, SNIPPETS_FILE, TEMPLATES_FILE, QUICKTIMES_FILE,
                    REPEAT_NAMES, REPEAT_CODES, CAT_LABEL, DEFAULT_SYMBOL_ROWS,
                    DEFAULT_QUICKTIMES)

CHILD_SEP = "::c::"


def child_iid(task, child):
    return task["id"] + CHILD_SEP + child["id"]


def split_child_iid(iid):
    if CHILD_SEP in iid:
        return tuple(iid.split(CHILD_SEP, 1))
    return (iid, None)


def now_iso():
    return datetime.datetime.now().isoformat(timespec="minutes")


def parse_dt(text):
    if not text:
        return None
    text = str(text).strip()
    if re.fullmatch(r"\d{1,4}", text):
        # 纯数字: 表示相对"开始时间"的偏移分钟数, 由调用方处理
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M", "%Y/%m/%d"):
        try:
            return datetime.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def is_minute_offset(text):
    """纯数字(如 150) = 相对开始时间的偏移分钟数"""
    if not text:
        return False
    t = str(text).strip()
    return bool(t) and bool(re.fullmatch(r"\d{1,5}", t))


def resolve_deadline(start_text, deadline_text):
    """事件: 截止时间填纯数字(如 150) 表示"起始时间 + 150 分钟"。
    返回 (截止文本, 提示) 或 (原样, "")。"""
    if is_minute_offset(deadline_text):
        st = parse_dt(start_text) if start_text else None
        if st is not None:
            mins = int(deadline_text.strip())
            end = st + datetime.timedelta(minutes=mins)
            return end.strftime("%Y-%m-%d %H:%M"), "截止 = 开始 + %d 分钟" % mins
    return deadline_text, ""


def validate_dates(start, end):
    s = parse_dt(start) if start else None
    e = parse_dt(end) if end else None
    if start and s is None:
        return False, "开始时间格式错误，请用 2026-08-30 09:00"
    if end and e is None:
        return False, "截止时间格式错误，请用 2026-08-30 18:00（纯数字=相对开始偏移分钟）"
    if s is not None and e is not None and s > e:
        return False, "开始时间不能晚于截止时间"
    return True, ""


def new_task(title, note="", deadline=None, repeat=None, start=None):
    return {
        "id": uuid.uuid4().hex,
        "title": title.strip(),
        "note": (note or "").strip(),
        "start": start,
        "deadline": deadline,
        "created_at": now_iso(),
        "status": "active",
        "completed_at": None,
        "cancelled_at": None,
        "children": [],
        "repeat": repeat,
        "pinned": False,
        "flag": None,
    }


def new_child(title):
    return {
        "id": uuid.uuid4().hex,
        "title": title.strip(),
        "done": False,
        "created_at": now_iso(),
    }


def get_children(task):
    kids = task.get("children")
    return kids if isinstance(kids, list) else []


def update_task(task, title, note, deadline, repeat=None, start=None):
    task["title"] = title.strip()
    task["note"] = (note or "").strip()
    task["start"] = start
    task["deadline"] = deadline
    task["repeat"] = repeat
    return task


def normalize_task(t):
    for k, v in {"id": uuid.uuid4().hex, "title": "", "note": "", "start": None,
                 "deadline": None, "created_at": now_iso(), "status": "active",
                 "completed_at": None, "cancelled_at": None, "children": [],
                 "repeat": None, "pinned": False, "flag": None}.items():
        t.setdefault(k, v)
    if not isinstance(t.get("children"), list):
        t["children"] = []
    for c in t["children"]:
        c.setdefault("id", uuid.uuid4().hex)
        c.setdefault("title", "")
        c.setdefault("done", False)
        c.setdefault("created_at", now_iso())
    return t


def load_tasks():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [normalize_task(t) for t in data]
        return []
    except Exception:
        try:
            shutil.copy2(DATA_FILE, DATA_FILE + ".bak")
        except Exception:
            pass
        return []


def save_tasks(tasks):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


def classify(task, now=None):
    status = task.get("status", "active")
    if status != "active":
        return status
    if task.get("deadline"):
        dt = parse_dt(task["deadline"])
        if dt is not None and dt < (now or datetime.datetime.now()):
            return "expired"
    return "active"


def next_occurrence(dt, repeat, now=None):
    now = now or datetime.datetime.now()
    d = dt
    if repeat == "daily":
        while d <= now:
            d += datetime.timedelta(days=1)
    elif repeat == "weekly":
        while d <= now:
            d += datetime.timedelta(days=7)
    elif repeat == "monthly":
        while d <= now:
            y = d.year + (1 if d.month == 12 else 0)
            m = 1 if d.month == 12 else d.month + 1
            last = calendar.monthrange(y, m)[1]
            d = d.replace(year=y, month=m, day=min(d.day, last))
    elif repeat == "weekday":
        while d <= now or d.weekday() >= 5:
            d += datetime.timedelta(days=1)
    else:
        while d <= now:
            d += datetime.timedelta(days=1)
    return d


def iter_occurrences(task, now=None, days=90):
    """周期性日程/事件在未来 days 天内的出现日期(含事件起止区间)。
    返回按日期升序去重后的 date 列表, 供日历标记。"""
    now = now or datetime.date.today()
    out = []
    st = parse_dt(task.get("start"))
    en = parse_dt(task.get("deadline"))
    # 事件区间: 开始~截止 逐日(仅多日区间; 单日仍由下方单点补充)
    if st is not None and en is not None and (en - st).days > 0:
        d = st.date()
        end = en.date()
        n = 0
        while d <= end and n < days:
            out.append(d)
            d += datetime.timedelta(days=1)
            n += 1
    for key in ("start", "deadline"):
        dt = parse_dt(task.get(key))
        if dt is not None:
            out.append(dt.date())
    # 周期日程: 从下一周期起逐周期展开
    rep = task.get("repeat")
    if rep:
        base = parse_dt(task.get("deadline")) or parse_dt(task.get("start"))
        if base is not None:
            cur = next_occurrence(base, rep, datetime.datetime.now())
            horizon = now + datetime.timedelta(days=days)
            n = 0
            while cur.date() <= horizon and n < 60:
                out.append(cur.date())
                cur = next_occurrence(cur, rep, cur)
                n += 1
    seen = set()
    result = []
    for d in out:
        if d not in seen:
            seen.add(d)
            result.append(d)
    return sorted(result)


def fmt_remain(deadline, now=None):
    dt = parse_dt(deadline)
    if dt is None:
        return "—"
    now = now or datetime.datetime.now()
    diff = dt - now
    if diff.total_seconds() < 0:
        e = -diff
        days, secs = e.days, e.seconds
        hours, mins = secs // 3600, (secs % 3600) // 60
        if days:
            return "已过%d天%d时" % (days, hours)
        if hours:
            return "已过%d时%d分" % (hours, mins)
        return "已过%d分" % max(1, mins)
    days, secs = diff.days, diff.seconds
    hours, mins = secs // 3600, (secs % 3600) // 60
    if days:
        return "%d天%d时%d分" % (days, hours, mins)
    if hours:
        return "%d时%d分" % (hours, mins)
    if mins:
        return "%d分" % mins
    return "不足1分"


def dl_sort_key(task):
    dt = parse_dt(task.get("deadline"))
    if dt is not None:
        return dt
    st = parse_dt(task.get("start"))
    return st if st is not None else datetime.datetime.max


def history_date(task):
    if task.get("status") == "done":
        return parse_dt(task.get("completed_at"))
    if task.get("status") == "cancelled":
        return parse_dt(task.get("cancelled_at"))
    return parse_dt(task.get("deadline"))


def fmt_dt(text):
    dt = parse_dt(text)
    return dt.strftime("%Y-%m-%d %H:%M") if dt else (text or "—")


def day_key(dt):
    return dt.strftime("%Y-%m-%d") if dt else None


def date_range_ok(rng, d, now=None):
    if rng in ("", "全部") or d is None:
        return True
    now = now or datetime.datetime.now()
    days = (now - d).days
    table = {"今天": days == 0, "昨天": days == 1, "近7天": 0 <= days <= 7,
             "近30天": 0 <= days <= 30, "30天以上": days > 30}
    return table.get(rng, True)


def kw_ok(task, kw):
    if not kw:
        return True
    kw = kw.lower()
    return (kw in task.get("title", "").lower()
            or kw in task.get("note", "").lower())


def flag_markers(task):
    m = ""
    if task.get("pinned"):
        m += "📌"
    f = task.get("flag")
    if f == "red":
        m += "🚩"
    elif f:
        m += "●" + f
    return m


def make_template_from(task):
    """历史记录 → 新日程模板: 沿用内容/周期/标记/置顶/子日程, 清空时间, 新 id"""
    t = new_task(task.get("title", ""), note=task.get("note", ""),
                 repeat=task.get("repeat"))
    t["flag"] = task.get("flag")
    t["pinned"] = task.get("pinned")
    t["children"] = [dict(c) for c in get_children(task)]
    return t


# ---------- 符号 / 句子 / 模板 / 快捷时间 ----------

def load_symbol_rows():
    if os.path.exists(SYMBOLS_FILE):
        try:
            with open(SYMBOLS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            rows = data.get("rows") if isinstance(data, dict) else None
            if isinstance(rows, list) and rows:
                return [str(r) for r in rows]
        except Exception:
            pass
    return list(DEFAULT_SYMBOL_ROWS)


def save_symbol_rows(rows):
    paths.save_text_file(SYMBOLS_FILE, json.dumps({"rows": rows},
                                                  ensure_ascii=False, indent=2))


def load_snippets():
    if os.path.exists(SNIPPETS_FILE):
        try:
            with open(SNIPPETS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            items = data.get("items") if isinstance(data, dict) else None
            if isinstance(items, list):
                return [str(x) for x in items]
        except Exception:
            pass
    return []


def save_snippets(items):
    paths.save_text_file(SNIPPETS_FILE, json.dumps({"items": items},
                                                   ensure_ascii=False, indent=2))


def load_templates():
    """日程模板列表: [{name, title, note, start, deadline, repeat, flag, pinned}, ...]"""
    if os.path.exists(TEMPLATES_FILE):
        try:
            with open(TEMPLATES_FILE, encoding="utf-8") as f:
                data = json.load(f)
            items = data.get("items") if isinstance(data, dict) else None
            if isinstance(items, list):
                return [dict(x) for x in items]
        except Exception:
            pass
    return []


def save_templates(items):
    paths.save_text_file(TEMPLATES_FILE, json.dumps({"items": items},
                                                    ensure_ascii=False, indent=2))


def load_quicktimes():
    if os.path.exists(QUICKTIMES_FILE):
        try:
            with open(QUICKTIMES_FILE, encoding="utf-8") as f:
                data = json.load(f)
            items = data.get("items") if isinstance(data, dict) else None
            if isinstance(items, list) and items:
                return [dict(x) for x in items]
        except Exception:
            pass
    return [dict(x) for x in DEFAULT_QUICKTIMES]


def save_quicktimes(items):
    paths.save_text_file(QUICKTIMES_FILE, json.dumps({"items": items},
                                                     ensure_ascii=False, indent=2))


def apply_quicktime(qt, now=None):
    """快捷时间条目 -> datetime"""
    now = now or datetime.datetime.now()
    kind = qt.get("kind", "days")
    hour = int(qt.get("hour", 9))
    minute = int(qt.get("minute", 0))
    if kind == "weekday":
        dow = int(qt.get("delta", 0))
        days = (dow - now.weekday()) % 7
        if days == 0:
            days = 7
        d = (now + datetime.timedelta(days=days)).replace(
            hour=hour, minute=minute, second=0, microsecond=0)
        return d
    if kind == "month_end":
        last = calendar.monthrange(now.year, now.month)[1]
        return now.replace(day=last, hour=hour, minute=minute, second=0,
                           microsecond=0)
    days = int(qt.get("delta", 0))
    return (now + datetime.timedelta(days=days)).replace(
        hour=hour, minute=minute, second=0, microsecond=0)


# ---------- 便签目录(IDE) ----------

def ensure_notes_root():
    os.makedirs(NOTES_ROOT, exist_ok=True)
    if not os.path.exists(NOTES_FILE):
        paths.save_text_file(NOTES_FILE, "")


def scan_notes():
    """扫描 data/notes 下的 .txt 笔记与分类文件夹(含空分类)。
    返回 [(相对路径, 绝对路径, 名称, 是否文件夹)]"""
    ensure_notes_root()
    out = []
    for root, dirs, files in os.walk(NOTES_ROOT):
        dirs.sort()
        rel_root = os.path.relpath(root, NOTES_ROOT)
        for d in sorted(dirs):
            full = os.path.join(root, d)
            rel = os.path.relpath(full, NOTES_ROOT)
            out.append((rel, full, d, True))
        for fn in sorted(files):
            if fn.lower().endswith(".txt"):
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, NOTES_ROOT)
                out.append((rel, full, fn, False))
    return out


def _del(path):
    """删除文件(配合工作区删除日志使用)"""
    if os.path.exists(path):
        os.remove(path)
