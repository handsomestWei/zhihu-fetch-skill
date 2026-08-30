#!/usr/bin/env python3
"""抓取用户「他的专栏」：多专栏列表 → 每栏文章（层级 JSON）。

用法:
  python fetch_zhihu_columns.py <个人主页或 /columns>
  python fetch_zhihu_columns.py <个人主页> --column 远东轶事
  python fetch_zhihu_columns.py <个人主页> --list-only
  python fetch_zhihu_columns.py https://www.zhihu.com/column/yuandong

不带条数时使用 zhihu_fetch_config.json 的 column.* 上限；--all 取消限制。
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse

sys.stdout.reconfigure(encoding="utf-8")

from zhihu_fetch.core.limits import describe_limit, resolve_limit
from zhihu_fetch.fetch.collection import (
    _request_json,
    load_cookies,
    optional_arg,
    parse_people_slug,
    save_json,
)
from zhihu_fetch.core.summary import bump, empty_summary, finish, note
from zhihu_fetch.core.paths import get_default_paths
from zhihu_fetch.core.seen import record_urls
from zhihu_fetch.core.times import attach_times
from zhihu_fetch.core.filters import (
    build_select_kwargs,
    describe_filters,
    remember_fetched,
    take_counted,
)


def extract_column_id(url_or_id):
    text = str(url_or_id).strip()
    match = re.search(r"(?:zhuanlan\.zhihu\.com|zhihu\.com/column)/([^/?#]+)", text)
    if match:
        token = match.group(1)
        if token not in {"p", "api"}:
            return token
    if re.fullmatch(r"[A-Za-z0-9_-]+", text) and not re.fullmatch(r"\d+", text):
        return text
    return None


def column_is_empty(col):
    count = col.get("contributions_count")
    if count is None:
        return False
    try:
        return int(count) <= 0
    except (TypeError, ValueError):
        return False


def column_matches(col, name):
    if not (name or "").strip():
        return True
    needle = name.strip().casefold()
    title = (col.get("title") or "").casefold()
    cid = str(col.get("id") or "").casefold()
    return needle == cid or needle in title


def normalize_column(row):
    col = row.get("column") if isinstance(row, dict) and "column" in row else row
    if not isinstance(col, dict):
        return None
    cid = str(col.get("id") or col.get("url_token") or "").strip()
    if not cid:
        return None
    count = row.get("contributions_count") if isinstance(row, dict) else None
    if count is None:
        count = col.get("articles_count") or col.get("items_count")
    return {
        "id": cid,
        "title": col.get("title") or cid,
        "url": f"https://www.zhihu.com/column/{cid}",
        "contributions_count": count,
        "type": "column",
    }


def normalize_column_article(item, column=None):
    if not isinstance(item, dict):
        return None
    inner = item.get("content") if isinstance(item.get("content"), dict) else item
    article_id = inner.get("id")
    url = (inner.get("url") or "").split("?")[0]
    if article_id and "zhuanlan.zhihu.com/p/" not in url:
        url = f"https://zhuanlan.zhihu.com/p/{article_id}"
    if not url:
        return None
    title = (inner.get("title") or inner.get("excerpt_title") or "").strip()
    author = ((inner.get("author") or {}).get("name")) or ""
    info = attach_times(
        {
            "url": url,
            "title": title or f"article_{article_id}",
            "author": author,
            "voteup": inner.get("voteup_count", 0),
            "type": inner.get("type") or "article",
        },
        inner,
    )
    if column:
        info["column_id"] = column.get("id") or ""
        info["column_title"] = column.get("title") or ""
    return info


def list_member_columns(slug, cookie_str=""):
    all_items = []
    offset = 0
    limit = 20
    while True:
        params = urllib.parse.urlencode({"offset": offset, "limit": limit})
        url = f"https://www.zhihu.com/api/v4/members/{slug}/column-contributions?{params}"
        try:
            data, _status = _request_json(
                url,
                cookie_str=cookie_str,
                referer=f"https://www.zhihu.com/people/{slug}/columns",
            )
        except Exception as exc:
            print(f"[columns] {exc}")
            break
        rows = data.get("data") or []
        paging = data.get("paging") or {}
        for row in rows:
            col = normalize_column(row)
            if col:
                all_items.append(col)
        if paging.get("is_end", True) or not rows:
            break
        offset += limit
        time.sleep(0.3)
    return all_items


def fetch_column_articles(column_id, max_items=0, cookie_str="", skip_urls=None, stats=None, select_kwargs=None):
    print(f"[API] 获取专栏 {column_id} 文章")
    all_items = []
    local_stats = stats if stats is not None else {}
    offset = 0
    limit = 20
    ctx = select_kwargs
    if ctx is None:
        ctx = build_select_kwargs(since_last=bool(skip_urls))
        if skip_urls:
            ctx["seen_urls"] = set(skip_urls)
            ctx["since_last"] = True
    http_403 = 0

    while True:
        url = (
            f"https://zhuanlan.zhihu.com/api/columns/{column_id}/articles"
            f"?limit={limit}&offset={offset}"
        )
        try:
            data, _status = _request_json(
                url,
                cookie_str=cookie_str,
                referer=f"https://zhuanlan.zhihu.com/{column_id}",
            )
        except urllib.error.HTTPError as exc:
            print(f"  [ERROR] HTTP {exc.code}")
            if exc.code == 403:
                http_403 += 1
            break
        except Exception as exc:
            print(f"  [ERROR] {exc}")
            break
        rows = data.get("data") or []
        paging = data.get("paging") or {}
        if not rows:
            break
        for row in rows:
            info = take_counted(normalize_column_article(row), ctx, local_stats)
            if not info:
                continue
            all_items.append(info)
            if max_items and len(all_items) >= max_items:
                print(
                    f"[API] 完成，有效 {len(all_items)} 条，跳过空项 {local_stats.get('skipped_empty', 0)}，"
                    f"已抓 {local_stats.get('skipped_seen', 0)}，过滤 {local_stats.get('skipped_filter', 0)}"
                )
                local_stats["http_403"] = http_403
                return all_items
        print(
            f"  本页 {len(rows)} 条，有效累计 {len(all_items)}，"
            f"跳过空 {local_stats.get('skipped_empty', 0)}，已抓 {local_stats.get('skipped_seen', 0)}，"
            f"过滤 {local_stats.get('skipped_filter', 0)}"
        )
        if paging.get("is_end", True):
            break
        offset += limit
        time.sleep(0.4)
    print(
        f"[API] 完成，有效 {len(all_items)} 条，跳过空项 {local_stats.get('skipped_empty', 0)}，"
        f"已抓 {local_stats.get('skipped_seen', 0)}，过滤 {local_stats.get('skipped_filter', 0)}"
    )
    local_stats["http_403"] = http_403
    return all_items


def _safe_filename(text):
    return re.sub(r'[\\/:*?"<>|]', "_", str(text))[:80] or "column"


def main():
    if len(sys.argv) < 2:
        print("用法: python fetch_zhihu_columns.py <个人主页|/columns|专栏URL> [--column 名称]")
        print("      python fetch_zhihu_columns.py <个人主页> --list-only")
        print("上限见 zhihu_fetch_config.json 的 column.* ；--all 取消限制；--since-last 只补新条目")
        print("      --min-voteup N  --days N  --since ISO  列表过滤")
        sys.exit(1)

    url_or_id = sys.argv[1]
    column_name = optional_arg("--column")
    per_raw = optional_arg("--per-column")
    max_col_raw = optional_arg("--max-columns")
    per_column = resolve_limit(
        "column.items_per_column",
        int(per_raw) if per_raw and str(per_raw).isdigit() else None,
    )
    max_columns = resolve_limit(
        "column.max_columns",
        int(max_col_raw) if max_col_raw and str(max_col_raw).isdigit() else None,
    )
    list_only = "--list-only" in sys.argv
    since_last = "--since-last" in sys.argv
    select_kwargs = build_select_kwargs(since_last=since_last)
    filt = describe_filters(select_kwargs)
    if filt:
        print(f"[过滤] {filt}")
    if since_last:
        print(f"[增量] 已记录 URL {len(select_kwargs.get('seen_urls') or [])} 条")

    workspace = get_default_paths()["workspace"]
    os.makedirs(workspace, exist_ok=True)
    cookie_str = load_cookies()

    slug = parse_people_slug(url_or_id)
    column_id = None if slug else extract_column_id(url_or_id)

    if slug:
        print(f"个人专栏页: https://www.zhihu.com/people/{slug}/columns")
        columns = list_member_columns(slug, cookie_str)
        empty = [c for c in columns if column_is_empty(c)]
        nonempty = [c for c in columns if not column_is_empty(c)]
        if column_name:
            matched = [c for c in nonempty if column_matches(c, column_name)]
            print(f"按名称筛选 {column_name!r}: {len(matched)} / {len(nonempty)}")
            nonempty = matched
        print(
            f"专栏: {len(columns)} 个，空栏跳过 {len(empty)}，有效 {len(nonempty)}"
        )
        for col in empty:
            print(f"  [跳过空栏] {col['id']} {col['title']}")
        if max_columns:
            nonempty = nonempty[:max_columns]
            print(f"本次最多处理 {len(nonempty)} 个专栏（上限 {describe_limit(max_columns)}）")

        tree = {
            "source": f"https://www.zhihu.com/people/{slug}/columns",
            "total": len(columns),
            "empty_skipped": len(empty),
            "column_filter": column_name or "",
            "columns": [],
        }

        run = empty_summary(f"columns:{slug}")
        bump(run, "skipped_empty", len(empty))

        if list_only:
            tree["columns"] = nonempty
            save_json(os.path.join(workspace, f"zhihu_columns_{slug}.json"), tree)
            print("仅列出专栏（--list-only）")
            finish(run, workspace)
            return

        print(f"每栏最多 {describe_limit(per_column)} 篇")
        for col in nonempty:
            print()
            print(f"=== {col['title']} ({col['id']}) ===")
            stats = {}
            items = fetch_column_articles(
                col["id"], per_column, cookie_str, select_kwargs=select_kwargs, stats=stats
            )
            bump(run, "skipped_empty", stats.get("skipped_empty", 0))
            bump(run, "skipped_seen", stats.get("skipped_seen", 0))
            bump(run, "http_403", stats.get("http_403", 0))
            if stats.get("http_403") and not cookie_str:
                bump(run, "need_login")
                note(run, f"专栏 {col['id']} 403，建议登录后重试")
            if not items:
                print(f"[跳过] 专栏 {col['id']} 无有效文章")
                continue
            capped = items if not per_column else items[:per_column]
            for item in capped:
                item["column_id"] = col["id"]
                item["column_title"] = col["title"]
            node = dict(col)
            node["items"] = capped
            node["fetched"] = len(capped)
            tree["columns"].append(node)
            out = os.path.join(workspace, f"zhihu_column_{_safe_filename(col['id'])}.json")
            save_json(
                out,
                {
                    "total": len(capped),
                    "column_id": col["id"],
                    "title": col["title"],
                    "source": col["url"],
                    "items": capped,
                },
            )
            record_urls(capped, f"column:{col['id']}", workspace, index=select_kwargs.get("index"))
            remember_fetched(select_kwargs, capped)
            bump(run, "success", len(capped))
            run["outputs"].append(out)

        tree_path = os.path.join(workspace, f"zhihu_columns_{slug}.json")
        save_json(tree_path, tree)
        run["outputs"].append(tree_path)
        if not cookie_str:
            bump(run, "need_login")
            note(run, "未检测到 Cookie")
        finish(run, workspace)
        return

    if not column_id:
        print("无法从输入中提取个人主页 slug 或专栏 ID")
        sys.exit(1)

    print(f"专栏 ID: {column_id}")
    print(f"每栏最多 {describe_limit(per_column)} 篇")
    run = empty_summary(f"column:{column_id}")
    col = {"id": column_id, "title": column_id, "url": f"https://www.zhihu.com/column/{column_id}"}
    stats = {}
    items = fetch_column_articles(column_id, per_column, cookie_str, select_kwargs=select_kwargs, stats=stats)
    bump(run, "skipped_empty", stats.get("skipped_empty", 0))
    bump(run, "skipped_seen", stats.get("skipped_seen", 0))
    bump(run, "http_403", stats.get("http_403", 0))
    if stats.get("http_403") and not cookie_str:
        bump(run, "need_login")
        note(run, "专栏文章 API 403，建议登录后重试")
    if not items:
        print("获取失败或专栏为空，已跳过。")
        note(run, "无有效文章")
        finish(run, workspace)
        sys.exit(0)
    capped = items if not per_column else items[:per_column]
    for item in capped:
        item["column_id"] = column_id
        item["column_title"] = column_id
    out = os.path.join(workspace, f"zhihu_column_{_safe_filename(column_id)}.json")
    save_json(
        out,
        {
            "total": len(capped),
            "column_id": column_id,
            "title": column_id,
            "source": col["url"],
            "items": capped,
        },
    )
    record_urls(capped, f"column:{column_id}", workspace, index=select_kwargs.get("index"))
    remember_fetched(select_kwargs, capped)
    bump(run, "success", len(capped))
    run["outputs"].append(out)
    finish(run, workspace)


if __name__ == "__main__":
    main()
