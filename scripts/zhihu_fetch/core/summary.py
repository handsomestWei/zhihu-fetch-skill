#!/usr/bin/env python3
"""Print and persist a short fetch-run summary for Agent replies."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from zhihu_fetch.core.paths import get_workspace_dir


def empty_summary(job=""):
    return {
        "job": job,
        "success": 0,
        "skipped_empty": 0,
        "skipped_seen": 0,
        "failed": 0,
        "http_403": 0,
        "need_login": 0,
        "notes": [],
        "outputs": [],
    }


def bump(summary, key, amount=1):
    summary[key] = int(summary.get(key) or 0) + amount


def note(summary, text):
    summary.setdefault("notes", []).append(text)


def classify_reason(reason):
    text = str(reason or "").lower()
    if "signin" in text or "login" in text or "未登录" in text or "需要登录" in text:
        return "need_login"
    if "403" in text or "forbidden" in text:
        return "http_403"
    if "empty" in text or "空" in text:
        return "skipped_empty"
    return "failed"


def merge_failed_reasons(summary, failed_rows):
    for row in failed_rows or []:
        reason = row.get("reason") if isinstance(row, dict) else row
        kind = classify_reason(reason)
        bump(summary, kind)


def print_summary(summary):
    print()
    print("=" * 60)
    print("抓取摘要")
    print("=" * 60)
    if summary.get("job"):
        print(f"任务: {summary['job']}")
    print(f"成功: {summary.get('success', 0)}")
    print(f"跳过(空项): {summary.get('skipped_empty', 0)}")
    print(f"跳过(已抓/去重): {summary.get('skipped_seen', 0)}")
    print(f"失败: {summary.get('failed', 0)}")
    print(f"403: {summary.get('http_403', 0)}")
    print(f"需登录: {summary.get('need_login', 0)}")
    for line in summary.get("notes") or []:
        print(f"- {line}")
    for path in summary.get("outputs") or []:
        print(f"输出: {path}")
    print("=" * 60)


def write_summary(summary, workspace=None, filename="zhihu_run_summary.json"):
    workspace = workspace or get_workspace_dir()
    os.makedirs(workspace, exist_ok=True)
    payload = dict(summary)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = os.path.join(workspace, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"摘要已写入: {path}")
    return path


def finish(summary, workspace=None):
    print_summary(summary)
    return write_summary(summary, workspace)
