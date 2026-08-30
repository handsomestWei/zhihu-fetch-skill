#!/usr/bin/env python3
"""Parse Zhihu timestamps (unix seconds / ms / ISO)."""
from __future__ import annotations

from datetime import datetime, timezone


def to_unix(value):
    if value is None or value == "":
        return 0
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        ts = int(value)
        if ts > 10**12:
            ts //= 1000
        return ts if ts > 0 else 0
    text = str(value).strip()
    if not text:
        return 0
    if text.isdigit():
        return to_unix(int(text))
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        text = text + "T00:00:00+08:00"
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return 0


def content_updated_of(item):
    """Best-effort content timestamp in unix seconds."""
    if not isinstance(item, dict):
        return 0
    for key in (
        "content_updated",
        "updated_time",
        "updated",
        "created_time",
        "created",
    ):
        ts = to_unix(item.get(key))
        if ts:
            return ts
    return 0


def attach_times(info, source=None):
    src = source if isinstance(source, dict) else info
    ts = content_updated_of(src) or content_updated_of(info)
    if ts:
        info["content_updated"] = ts
    return info
