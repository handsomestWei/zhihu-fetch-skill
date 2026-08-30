#!/usr/bin/env python3
"""Workspace URL index: incremental skip + cross-source dedupe."""
from __future__ import annotations

import glob
import json
import os
import re
from datetime import datetime, timezone

from zhihu_fetch.core.paths import get_workspace_dir

INDEX_NAME = "zhihu_url_index.json"
_URL_RE = re.compile(r'(?m)^url:\s*["\']?(\S+?)["\']?\s*$')


def canonical_url(url):
    text = (url or "").split("?")[0].strip()
    if text.startswith("http://"):
        text = "https://" + text[len("http://") :]
    if text.startswith("/"):
        text = "https://www.zhihu.com" + text
    match = re.search(r"/answer/(\d+)", text) or re.search(r"/answers/(\d+)", text)
    if match:
        return f"https://www.zhihu.com/answer/{match.group(1)}"
    match = re.search(r"/p/(\d+)", text)
    if match:
        return f"https://zhuanlan.zhihu.com/p/{match.group(1)}"
    return text


def index_path(workspace=None):
    return os.path.join(workspace or get_workspace_dir(), INDEX_NAME)


def load_index(workspace=None):
    path = index_path(workspace)
    if not os.path.exists(path):
        return {"urls": {}}
    try:
        data = json.loads(open(path, encoding="utf-8").read())
        if isinstance(data, dict):
            data.setdefault("urls", {})
            return data
    except Exception:
        pass
    return {"urls": {}}


def save_index(index, workspace=None):
    workspace = workspace or get_workspace_dir()
    os.makedirs(workspace, exist_ok=True)
    path = index_path(workspace)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path


def _add_item_urls(payload, seen):
    if not isinstance(payload, dict):
        return
    for item in payload.get("items") or []:
        url = canonical_url(item.get("url") if isinstance(item, dict) else "")
        if url:
            seen.add(url)
    for col in payload.get("columns") or []:
        if isinstance(col, dict):
            _add_item_urls(col, seen)


def urls_from_json_file(path):
    seen = set()
    try:
        payload = json.loads(open(path, encoding="utf-8").read())
    except Exception:
        return seen
    if isinstance(payload, dict):
        for url in payload.get("completed") or []:
            url = canonical_url(url)
            if url:
                seen.add(url)
        _add_item_urls(payload, seen)
    return seen


def urls_from_markdown_dir(directory):
    seen = set()
    if not directory or not os.path.isdir(directory):
        return seen
    for root, _dirs, files in os.walk(directory):
        if "chrome_user_data" in root.replace("\\", "/"):
            continue
        for name in files:
            if not name.endswith(".md"):
                continue
            try:
                text = open(os.path.join(root, name), encoding="utf-8").read(4000)
            except Exception:
                continue
            match = _URL_RE.search(text)
            if match:
                url = canonical_url(match.group(1))
                if url:
                    seen.add(url)
    return seen


def collect_column_urls(workspace=None):
    """URLs already listed under column JSON (article/column overlap)."""
    workspace = workspace or get_workspace_dir()
    seen = set()
    for pattern in ("zhihu_column_*.json", "zhihu_columns_*.json"):
        for path in glob.glob(os.path.join(workspace, pattern)):
            seen.update(urls_from_json_file(path))
    index = load_index(workspace)
    for url, rec in (index.get("urls") or {}).items():
        sources = rec.get("sources") if isinstance(rec, dict) else []
        if any(str(src).startswith("column:") for src in sources or []):
            key = canonical_url(url)
            if key:
                seen.add(key)
    return seen


def collect_seen_urls(workspace=None, extra_dirs=None):
    workspace = workspace or get_workspace_dir()
    seen = set()
    index = load_index(workspace)
    for url in (index.get("urls") or {}):
        url = canonical_url(url)
        if url:
            seen.add(url)
    patterns = [
        os.path.join(workspace, "zhihu_*.json"),
        os.path.join(workspace, "*", "_progress.json"),
        os.path.join(workspace, "_progress.json"),
    ]
    for pattern in patterns:
        for path in glob.glob(pattern):
            name = os.path.basename(path)
            if name in {INDEX_NAME, "zhihu_cookies.json", "zhihu_fetch_config.json"}:
                continue
            seen.update(urls_from_json_file(path))
    seen.update(urls_from_markdown_dir(workspace))
    for directory in extra_dirs or []:
        seen.update(urls_from_markdown_dir(directory))
    return seen


def filter_new_items(items, seen):
    """Drop empty/duplicate URLs. Mutates seen with newly accepted URLs."""
    fresh = []
    skipped = []
    for item in items or []:
        url = canonical_url((item or {}).get("url"))
        if not url:
            skipped.append(item)
            continue
        item = dict(item)
        item["url"] = url
        if url in seen:
            skipped.append(item)
            continue
        seen.add(url)
        fresh.append(item)
    return fresh, skipped


def record_urls(items, source, workspace=None, index=None):
    from zhihu_fetch.core.times import content_updated_of

    workspace = workspace or get_workspace_dir()
    index = index if index is not None else load_index(workspace)
    urls = index.setdefault("urls", {})
    now = datetime.now(timezone.utc).isoformat()
    added = 0
    for item in items or []:
        url = canonical_url((item or {}).get("url"))
        if not url:
            continue
        rec = urls.get(url) or {"sources": []}
        sources = rec.setdefault("sources", [])
        if source and source not in sources:
            sources.append(source)
        rec["updated_at"] = now
        if item.get("title"):
            rec["title"] = item.get("title")
        ts = content_updated_of(item)
        if ts:
            rec["content_updated"] = ts
        if item.get("refresh"):
            rec["refreshed_at"] = now
        urls[url] = rec
        added += 1
    index["updated_at"] = now
    save_index(index, workspace)
    return added
