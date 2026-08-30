#!/usr/bin/env python3
"""List filters: min voteup and since-date, plus fetch/skip/refresh decision."""
from __future__ import annotations

import sys
import time

from zhihu_fetch.core.limits import cli_int, config_int
from zhihu_fetch.core.seen import canonical_url
from zhihu_fetch.core.times import content_updated_of, to_unix


def resolve_min_voteup(argv=None):
    cli = cli_int("--min-voteup", argv)
    if cli is not None:
        return cli
    return max(0, config_int("filter.min_voteup", 0))


def resolve_since_unix(argv=None):
    argv = sys.argv if argv is None else argv
    raw = None
    if "--since" in argv:
        idx = argv.index("--since")
        if idx + 1 < len(argv) and not str(argv[idx + 1]).startswith("--"):
            raw = argv[idx + 1]
    if raw:
        ts = to_unix(raw)
        if ts:
            return ts
        try:
            ts = to_unix(raw + "T00:00:00+08:00")
            if ts:
                return ts
        except Exception:
            pass
    days = cli_int("--days", argv)
    if days is None:
        days = config_int("filter.since_days", 0)
    if days:
        return int(time.time()) - int(days) * 86400
    return 0


def passes_filters(item, min_voteup=0, since_unix=0):
    try:
        vote = int((item or {}).get("voteup") or 0)
    except (TypeError, ValueError):
        vote = 0
    if min_voteup and vote < min_voteup:
        return False
    if since_unix:
        ts = content_updated_of(item)
        if ts and ts < since_unix:
            return False
    return True


def decide_fetch(item, *, index_urls, seen_urls, since_last, overlap_skip=None):
    """Return new | refresh | skip | empty."""
    url = canonical_url((item or {}).get("url"))
    if not url:
        return "empty"
    incoming = content_updated_of(item)
    rec = (index_urls or {}).get(url)
    stored = 0
    if isinstance(rec, dict):
        stored = int(rec.get("content_updated") or 0)
    if rec and incoming and incoming > stored:
        if stored:
            item["refresh"] = True
            return "refresh"
        rec["content_updated"] = incoming
    if overlap_skip and url in overlap_skip:
        return "skip"
    if since_last and (url in (seen_urls or set()) or rec):
        return "skip"
    return "new"


def select_fetch_items(
    items,
    *,
    index_urls,
    seen_urls,
    since_last,
    overlap_skip=None,
    min_voteup=0,
    since_unix=0,
):
    """Split a page of items into fetchable vs skipped. Mutates fetchable with refresh."""
    fetchable = []
    skipped_seen = 0
    skipped_filter = 0
    skipped_empty = 0
    refresh_n = 0
    for item in items or []:
        if not passes_filters(item, min_voteup, since_unix):
            skipped_filter += 1
            continue
        decision = decide_fetch(
            item,
            index_urls=index_urls,
            seen_urls=seen_urls,
            since_last=since_last,
            overlap_skip=overlap_skip,
        )
        if decision == "empty":
            skipped_empty += 1
            continue
        if decision == "skip":
            skipped_seen += 1
            continue
        if decision == "refresh":
            refresh_n += 1
        fetchable.append(item)
    return fetchable, skipped_empty, skipped_seen, skipped_filter, refresh_n


def build_select_kwargs(*, since_last=False, overlap_skip=None, workspace=None, argv=None):
    from zhihu_fetch.core.seen import collect_seen_urls, load_index

    index = load_index(workspace)
    seen = collect_seen_urls(workspace) if since_last else set()
    return {
        "index": index,
        "index_urls": index.setdefault("urls", {}),
        "seen_urls": seen,
        "since_last": since_last,
        "overlap_skip": set(overlap_skip or []),
        "min_voteup": resolve_min_voteup(argv),
        "since_unix": resolve_since_unix(argv),
        "accepted": set(),
    }


def select_kwargs_for_call(ctx):
    return {
        key: ctx[key]
        for key in (
            "index_urls",
            "seen_urls",
            "since_last",
            "overlap_skip",
            "min_voteup",
            "since_unix",
        )
    }


def take_item(item, ctx):
    """Decide one normalized item. Returns (decision, item_or_none)."""
    url = canonical_url((item or {}).get("url"))
    if not url:
        return "empty", None
    accepted = ctx.setdefault("accepted", set())
    if url in accepted:
        return "skip", None
    fetchable, empty, seen, filt, _refresh = select_fetch_items(
        [item], **select_kwargs_for_call(ctx)
    )
    if filt:
        return "filter", None
    if empty:
        return "empty", None
    if seen:
        return "skip", None
    if not fetchable:
        return "skip", None
    accepted.add(url)
    chosen = fetchable[0]
    return ("refresh" if chosen.get("refresh") else "new"), chosen


def take_counted(info, ctx, stats):
    """Like take_item, but increments skipped_empty / skipped_seen / skipped_filter / refresh."""
    if not info:
        stats["skipped_empty"] = stats.get("skipped_empty", 0) + 1
        return None
    decision, item = take_item(info, ctx)
    if decision == "empty":
        stats["skipped_empty"] = stats.get("skipped_empty", 0) + 1
        return None
    if decision == "filter":
        stats["skipped_filter"] = stats.get("skipped_filter", 0) + 1
        return None
    if decision == "skip":
        stats["skipped_seen"] = stats.get("skipped_seen", 0) + 1
        return None
    if decision == "refresh":
        stats["refresh"] = stats.get("refresh", 0) + 1
    return item


def remember_fetched(ctx, items):
    """Keep in-memory index/seen in sync after a list write (same run)."""
    urls = ctx.setdefault("index_urls", {})
    seen = ctx.setdefault("seen_urls", set())
    accepted = ctx.setdefault("accepted", set())
    for item in items or []:
        url = canonical_url((item or {}).get("url"))
        if not url:
            continue
        seen.add(url)
        accepted.add(url)
        rec = urls.get(url) or {"sources": []}
        ts = content_updated_of(item)
        if ts:
            rec["content_updated"] = ts
        urls[url] = rec


def describe_filters(ctx):
    parts = []
    if ctx.get("min_voteup"):
        parts.append(f"赞≥{ctx['min_voteup']}")
    if ctx.get("since_unix"):
        parts.append(f"since={ctx['since_unix']}")
    if ctx.get("since_last"):
        parts.append("增量")
    return "，".join(parts) if parts else ""
