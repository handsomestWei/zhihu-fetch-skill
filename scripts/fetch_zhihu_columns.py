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

from fetch_limits import describe_limit, resolve_limit
from fetch_zhihu_collection import (
    _request_json,
    load_cookies,
    optional_arg,
    parse_people_slug,
    save_json,
)
from workspace_paths import get_default_paths


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
    info = {
        "url": url,
        "title": title or f"article_{article_id}",
        "author": author,
        "voteup": inner.get("voteup_count", 0),
        "type": inner.get("type") or "article",
    }
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


def fetch_column_articles(column_id, max_items=0, cookie_str=""):
    print(f"[API] 获取专栏 {column_id} 文章")
    all_items = []
    skipped = 0
    offset = 0
    limit = 20
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
            break
        except Exception as exc:
            print(f"  [ERROR] {exc}")
            break
        rows = data.get("data") or []
        paging = data.get("paging") or {}
        if not rows:
            break
        for row in rows:
            info = normalize_column_article(row)
            if not info:
                skipped += 1
                continue
            all_items.append(info)
            if max_items and len(all_items) >= max_items:
                print(f"[API] 完成，有效 {len(all_items)} 条，跳过空项 {skipped}")
                return all_items
        print(f"  本页 {len(rows)} 条，有效累计 {len(all_items)}，跳过 {skipped}")
        if paging.get("is_end", True):
            break
        offset += limit
        time.sleep(0.4)
    print(f"[API] 完成，有效 {len(all_items)} 条，跳过空项 {skipped}")
    return all_items


def _safe_filename(text):
    return re.sub(r'[\\/:*?"<>|]', "_", str(text))[:80] or "column"


def main():
    if len(sys.argv) < 2:
        print("用法: python fetch_zhihu_columns.py <个人主页|/columns|专栏URL> [--column 名称]")
        print("      python fetch_zhihu_columns.py <个人主页> --list-only")
        print("上限见 zhihu_fetch_config.json 的 column.* ；--all 取消限制")
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

        if list_only:
            tree["columns"] = nonempty
            save_json(os.path.join(workspace, f"zhihu_columns_{slug}.json"), tree)
            print("仅列出专栏（--list-only）")
            return

        print(f"每栏最多 {describe_limit(per_column)} 篇")
        for col in nonempty:
            print()
            print(f"=== {col['title']} ({col['id']}) ===")
            items = fetch_column_articles(col["id"], per_column, cookie_str)
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
            save_json(
                os.path.join(workspace, f"zhihu_column_{_safe_filename(col['id'])}.json"),
                {
                    "total": len(capped),
                    "column_id": col["id"],
                    "title": col["title"],
                    "source": col["url"],
                    "items": capped,
                },
            )

        save_json(os.path.join(workspace, f"zhihu_columns_{slug}.json"), tree)
        return

    if not column_id:
        print("无法从输入中提取个人主页 slug 或专栏 ID")
        sys.exit(1)

    print(f"专栏 ID: {column_id}")
    print(f"每栏最多 {describe_limit(per_column)} 篇")
    col = {"id": column_id, "title": column_id, "url": f"https://www.zhihu.com/column/{column_id}"}
    items = fetch_column_articles(column_id, per_column, cookie_str)
    if not items:
        print("获取失败或专栏为空，已跳过。")
        sys.exit(0)
    capped = items if not per_column else items[:per_column]
    for item in capped:
        item["column_id"] = column_id
        item["column_title"] = column_id
    save_json(
        os.path.join(workspace, f"zhihu_column_{_safe_filename(column_id)}.json"),
        {
            "total": len(capped),
            "column_id": column_id,
            "title": column_id,
            "source": col["url"],
            "items": capped,
        },
    )


if __name__ == "__main__":
    main()
