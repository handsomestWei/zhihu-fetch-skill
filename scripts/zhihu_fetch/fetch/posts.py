#!/usr/bin/env python3
"""抓取个人页「文章」与「回答」列表，输出 batch 可用 JSON。

用法:
  python fetch_zhihu_posts.py <个人主页|/posts|/answers>
  python fetch_zhihu_posts.py <个人主页> --kind articles
  python fetch_zhihu_posts.py <个人主页> --kind answers
  python fetch_zhihu_posts.py <个人主页> --kind both --since-last
"""
from __future__ import annotations

import os
import sys
import time
import urllib.parse

sys.stdout.reconfigure(encoding="utf-8")

from zhihu_fetch.core.limits import describe_limit, resolve_limit
from zhihu_fetch.fetch.collection import _request_json, load_cookies, optional_arg, parse_people_slug, save_json
from zhihu_fetch.core.summary import bump, empty_summary, finish, note
from zhihu_fetch.core.paths import get_default_paths
from zhihu_fetch.core.seen import collect_column_urls, record_urls
from zhihu_fetch.core.url import classify_zhihu_url
from zhihu_fetch.core.times import attach_times
from zhihu_fetch.core.filters import (
    build_select_kwargs,
    describe_filters,
    remember_fetched,
    take_counted,
)


def normalize_article(item):
    if not isinstance(item, dict):
        return None
    article_id = item.get("id")
    url = (item.get("url") or "").split("?")[0]
    if article_id and "/p/" not in url:
        url = f"https://zhuanlan.zhihu.com/p/{article_id}"
    if url.startswith("http://"):
        url = "https://" + url[len("http://") :]
    if not url:
        return None
    author = ((item.get("author") or {}).get("name")) or ""
    return attach_times(
        {
            "url": url,
            "title": (item.get("title") or f"article_{article_id}").strip(),
            "author": author,
            "voteup": item.get("voteup_count", 0),
            "type": "article",
        },
        item,
    )


def normalize_answer(item):
    if not isinstance(item, dict):
        return None
    question = item.get("question") or {}
    qid = question.get("id")
    aid = item.get("id")
    if qid and aid:
        url = f"https://www.zhihu.com/question/{qid}/answer/{aid}"
    else:
        return None
    author = ((item.get("author") or {}).get("name")) or ""
    info = attach_times(
        {
            "url": url,
            "title": (question.get("title") or f"answer_{aid}").strip(),
            "author": author,
            "voteup": item.get("voteup_count", 0),
            "type": "answer",
            "question_id": str(qid),
        },
        item,
    )
    return info


def _paged(url_builder, normalize, cookie_str, referer, max_items, ctx, label):
    items = []
    stats = {}
    offset = 0
    limit = 20
    while True:
        url = url_builder(offset, limit)
        try:
            data, _status = _request_json(url, cookie_str=cookie_str, referer=referer)
        except Exception as exc:
            print(f"[{label}] {exc}")
            break
        rows = data.get("data") or []
        paging = data.get("paging") or {}
        if not rows:
            break
        for row in rows:
            info = take_counted(normalize(row), ctx, stats)
            if info:
                items.append(info)
        print(
            f"  [{label}] 本页 {len(rows)}，有效累计 {len(items)}，"
            f"跳过空 {stats.get('skipped_empty', 0)}，跳过已抓 {stats.get('skipped_seen', 0)}，"
            f"过滤 {stats.get('skipped_filter', 0)}，刷新 {stats.get('refresh', 0)}"
        )
        if max_items and len(items) >= max_items:
            items = items[:max_items]
            break
        if paging.get("is_end", True):
            break
        offset += limit
        time.sleep(0.35)
    return items, stats.get("skipped_empty", 0), stats.get("skipped_seen", 0)


def _article_ctx(seen=None, since_last=False, select_kwargs=None):
    if select_kwargs is not None:
        return select_kwargs
    overlap = set(seen or [])
    if not overlap:
        overlap = collect_column_urls()
    return build_select_kwargs(since_last=since_last, overlap_skip=overlap)


def fetch_member_articles(slug, max_items=0, cookie_str="", seen=None, since_last=False, select_kwargs=None):
    print(f"[API] 获取 {slug} 文章")
    ctx = _article_ctx(seen=seen, since_last=since_last, select_kwargs=select_kwargs)

    def builder(offset, limit):
        params = urllib.parse.urlencode({"offset": offset, "limit": limit})
        return f"https://www.zhihu.com/api/v4/members/{slug}/articles?{params}"

    return _paged(
        builder,
        normalize_article,
        cookie_str,
        f"https://www.zhihu.com/people/{slug}/posts",
        max_items,
        ctx,
        "articles",
    )


def fetch_member_answers(slug, max_items=0, cookie_str="", seen=None, since_last=False, select_kwargs=None):
    print(f"[API] 获取 {slug} 回答")
    if select_kwargs is not None:
        ctx = select_kwargs
    else:
        ctx = build_select_kwargs(since_last=since_last, overlap_skip=seen or set())
    include = (
        "data[*].is_normal,voteup_count,comment_count,question,author,"
        "created_time,updated_time"
    )

    def builder(offset, limit):
        params = urllib.parse.urlencode(
            {"offset": offset, "limit": limit, "include": include}
        )
        return f"https://www.zhihu.com/api/v4/members/{slug}/answers?{params}"

    return _paged(
        builder,
        normalize_answer,
        cookie_str,
        f"https://www.zhihu.com/people/{slug}/answers",
        max_items,
        ctx,
        "answers",
    )


def main():
    if len(sys.argv) < 2:
        print("用法: python fetch_zhihu_posts.py <个人主页|/posts|/answers> [--kind articles|answers|both]")
        print("      --since-last 只补新条目；文章默认排除已在专栏 JSON 里的 URL")
        print("      --min-voteup N  --days N  --since ISO  列表过滤")
        sys.exit(1)

    raw = sys.argv[1]
    target = classify_zhihu_url(raw)
    slug = target.slug or parse_people_slug(raw)
    if not slug:
        print("无法从输入中提取个人主页 slug")
        sys.exit(1)

    kind = (optional_arg("--kind") or "").strip().lower()
    if not kind:
        if target.kind == "answers":
            kind = "answers"
        elif target.kind == "posts":
            kind = "articles"
        else:
            kind = "both"
    if kind not in {"articles", "answers", "both"}:
        print("--kind 只能是 articles / answers / both")
        sys.exit(1)

    since_last = "--since-last" in sys.argv
    overlap = collect_column_urls() if kind in {"articles", "both"} else set()
    select_kwargs = build_select_kwargs(since_last=since_last, overlap_skip=overlap)
    filt = describe_filters(select_kwargs)
    if filt:
        print(f"[过滤] {filt}")
    if since_last:
        print(f"[增量] 已记录 URL {len(select_kwargs.get('seen_urls') or [])} 条")
    elif overlap:
        print(f"[去重] 对照已有专栏 URL {len(overlap)} 条（文章与专栏重叠）")
    max_articles = resolve_limit(
        "people.max_articles",
        int(optional_arg("--max-items")) if (optional_arg("--max-items") or "").isdigit() else None,
    )
    max_answers = resolve_limit(
        "people.max_answers",
        int(optional_arg("--max-answers")) if (optional_arg("--max-answers") or "").isdigit() else None,
    )

    workspace = get_default_paths()["workspace"]
    os.makedirs(workspace, exist_ok=True)
    cookie_str = load_cookies()
    summary = empty_summary(f"posts:{slug}:{kind}")

    all_items = []
    if kind in {"articles", "both"}:
        items, empty_n, seen_n = fetch_member_articles(
            slug, max_articles, cookie_str, select_kwargs=select_kwargs
        )
        bump(summary, "skipped_empty", empty_n)
        bump(summary, "skipped_seen", seen_n)
        bump(summary, "success", len(items))
        for item in items:
            item["source_feed"] = "posts"
        all_items.extend(items)
        out = os.path.join(workspace, f"zhihu_posts_{slug}.json")
        save_json(out, {"total": len(items), "source": f"https://www.zhihu.com/people/{slug}/posts", "kind": "articles", "items": items})
        summary["outputs"].append(out)
        record_urls(items, "posts", workspace, index=select_kwargs.get("index"))
        remember_fetched(select_kwargs, items)
        print(f"文章: {len(items)} 篇（上限 {describe_limit(max_articles)}）")

    if kind in {"answers", "both"}:
        items, empty_n, seen_n = fetch_member_answers(
            slug, max_answers, cookie_str, select_kwargs=select_kwargs
        )
        bump(summary, "skipped_empty", empty_n)
        bump(summary, "skipped_seen", seen_n)
        bump(summary, "success", len(items))
        for item in items:
            item["source_feed"] = "answers"
        all_items.extend(items)
        out = os.path.join(workspace, f"zhihu_answers_{slug}.json")
        save_json(out, {"total": len(items), "source": f"https://www.zhihu.com/people/{slug}/answers", "kind": "answers", "items": items})
        summary["outputs"].append(out)
        record_urls(items, "answers", workspace, index=select_kwargs.get("index"))
        remember_fetched(select_kwargs, items)
        print(f"回答: {len(items)} 条（上限 {describe_limit(max_answers)}）")

    if kind == "both":
        out = os.path.join(workspace, f"zhihu_posts_and_answers_{slug}.json")
        save_json(
            out,
            {
                "total": len(all_items),
                "source": f"https://www.zhihu.com/people/{slug}",
                "kind": "both",
                "items": all_items,
            },
        )
        summary["outputs"].append(out)

    if not cookie_str:
        bump(summary, "need_login")
        note(summary, "未检测到 Cookie，列表可能不完整；正文建议登录后 batch")
    finish(summary, workspace)


if __name__ == "__main__":
    main()
