# -*- coding: utf-8 -*-
"""删除日志辅助: python log_del.py "<shell>" "<command>" "<purpose>"
按 renew.md 要求, 把 shell 删除指令记录到工作区 deletion_log.json"""
import sys, os, json, datetime

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deletion_log.json")


def main():
    shell = sys.argv[1] if len(sys.argv) > 1 else ""
    command = sys.argv[2] if len(sys.argv) > 2 else ""
    purpose = sys.argv[3] if len(sys.argv) > 3 else ""
    data = {"entries": []}
    try:
        with open(LOG, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
            data = {"entries": []}
    except Exception:
        data = {"entries": []}
    data["entries"].append({
        "time": datetime.datetime.now().isoformat(timespec="seconds"),
        "shell": shell,
        "command": command,
        "purpose": purpose,
    })
    with open(LOG, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
