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
from zhihu_fetch.core.seen import collect_column_urls, collect_seen_urls, filter_new_items, record_urls
from zhihu_fetch.core.url import classify_zhihu_url


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
    return {
        "url": url,
        "title": (item.get("title") or f"article_{article_id}").strip(),
        "author": author,
        "voteup": item.get("voteup_count", 0),
        "type": "article",
    }


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
    return {
        "url": url,
        "title": (question.get("title") or f"answer_{aid}").strip(),
        "author": author,
        "voteup": item.get("voteup_count", 0),
        "type": "answer",
    }


def _paged(url_builder, normalize, cookie_str, referer, max_items, seen, label):
    items = []
    skipped_empty = 0
    skipped_seen = 0
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
        batch = []
        for row in rows:
            info = normalize(row)
            if not info:
                skipped_empty += 1
                continue
            batch.append(info)
        fresh, skipped = filter_new_items(batch, seen)
        skipped_seen += len(skipped)
        items.extend(fresh)
        print(
            f"  [{label}] 本页 {len(rows)}，有效累计 {len(items)}，"
            f"跳过空 {skipped_empty}，跳过已抓 {skipped_seen}"
        )
        if max_items and len(items) >= max_items:
            items = items[:max_items]
            break
        if paging.get("is_end", True):
            break
        offset += limit
        time.sleep(0.35)
    return items, skipped_empty, skipped_seen


def fetch_member_articles(slug, max_items=0, cookie_str="", seen=None):
    print(f"[API] 获取 {slug} 文章")
    seen = set() if seen is None else seen

    def builder(offset, limit):
        params = urllib.parse.urlencode({"offset": offset, "limit": limit})
        return f"https://www.zhihu.com/api/v4/members/{slug}/articles?{params}"

    return _paged(
        builder,
        normalize_article,
        cookie_str,
        f"https://www.zhihu.com/people/{slug}/posts",
        max_items,
        seen,
        "articles",
    )


def fetch_member_answers(slug, max_items=0, cookie_str="", seen=None):
    print(f"[API] 获取 {slug} 回答")
    seen = set() if seen is None else seen
    include = (
        "data[*].is_normal,voteup_count,comment_count,question,author,created_time"
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
        seen,
        "answers",
    )


def main():
    if len(sys.argv) < 2:
        print("用法: python fetch_zhihu_posts.py <个人主页|/posts|/answers> [--kind articles|answers|both]")
        print("      --since-last 只补新条目；文章默认排除已在专栏 JSON 里的 URL")
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
    if since_last:
        seen = collect_seen_urls(workspace)
        print(f"[增量] 已记录 URL {len(seen)} 条")
    elif kind in {"articles", "both"}:
        seen = collect_column_urls(workspace)
        print(f"[去重] 对照已有专栏 URL {len(seen)} 条（文章与专栏重叠）")
    else:
        seen = set()

    all_items = []
    if kind in {"articles", "both"}:
        items, empty_n, seen_n = fetch_member_articles(
            slug, max_articles, cookie_str, seen
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
        record_urls(items, "posts", workspace)
        print(f"文章: {len(items)} 篇（上限 {describe_limit(max_articles)}）")

    if kind in {"answers", "both"}:
        items, empty_n, seen_n = fetch_member_answers(
            slug, max_answers, cookie_str, seen
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
        record_urls(items, "answers", workspace)
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
