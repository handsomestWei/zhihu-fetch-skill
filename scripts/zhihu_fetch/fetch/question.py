#!/usr/bin/env python3
"""问题页：按默认排序拉回答列表，交给 batch。

用法:
  python scripts/zhihu.py question https://www.zhihu.com/question/{id}
  python scripts/zhihu.py route https://www.zhihu.com/question/{id}
"""
from __future__ import annotations

import os
import re
import sys
import time
import urllib.parse

sys.stdout.reconfigure(encoding="utf-8")

from zhihu_fetch.core.filters import (
    build_select_kwargs,
    describe_filters,
    remember_fetched,
    take_counted,
)
from zhihu_fetch.core.limits import describe_limit, resolve_limit
from zhihu_fetch.core.paths import get_default_paths
from zhihu_fetch.core.seen import record_urls
from zhihu_fetch.core.summary import bump, empty_summary, finish, note
from zhihu_fetch.fetch.collection import _request_json, load_cookies, optional_arg, save_json
from zhihu_fetch.fetch.posts import normalize_answer

ANSWERS_INCLUDE = (
    "data[*].is_normal,content,voteup_count,created_time,updated_time,author,question"
)


def extract_question_id(raw):
    text = str(raw).strip()
    match = re.search(r"/question/(\d+)", text)
    if match:
        return match.group(1)
    if re.fullmatch(r"\d+", text):
        return text
    return None


def fetch_question_title(qid, cookie_str=""):
    url = f"https://www.zhihu.com/api/v4/questions/{qid}"
    try:
        data, _status = _request_json(
            url,
            cookie_str=cookie_str,
            referer=f"https://www.zhihu.com/question/{qid}",
        )
    except Exception as exc:
        print(f"[question] 标题 {exc}")
        return ""
    return (data.get("title") or "").strip()


def fetch_question_answers(qid, max_items=0, cookie_str="", select_kwargs=None):
    print(f"[API] 获取问题 {qid} 回答")
    ctx = select_kwargs or build_select_kwargs()
    items = []
    stats = {}
    offset = 0
    limit = 20
    title = ""

    while True:
        params = urllib.parse.urlencode(
            {
                "include": ANSWERS_INCLUDE,
                "limit": limit,
                "offset": offset,
                "sort_by": "default",
            }
        )
        url = f"https://www.zhihu.com/api/v4/questions/{qid}/answers?{params}"
        try:
            data, _status = _request_json(
                url,
                cookie_str=cookie_str,
                referer=f"https://www.zhihu.com/question/{qid}",
            )
        except Exception as exc:
            print(f"[question] {exc}")
            break
        rows = data.get("data") or []
        paging = data.get("paging") or {}
        if not rows:
            break
        for row in rows:
            if not title:
                title = ((row.get("question") or {}).get("title") or "").strip()
            info = take_counted(normalize_answer(row), ctx, stats)
            if not info:
                continue
            info["source_feed"] = "question"
            info["question_id"] = str(qid)
            items.append(info)
            if max_items and len(items) >= max_items:
                items = items[:max_items]
                print(
                    f"  [question] 有效 {len(items)}，跳过空 {stats.get('skipped_empty', 0)}，"
                    f"已抓 {stats.get('skipped_seen', 0)}，过滤 {stats.get('skipped_filter', 0)}"
                )
                return items, title, stats
        print(
            f"  [question] 本页 {len(rows)}，有效累计 {len(items)}，"
            f"跳过空 {stats.get('skipped_empty', 0)}，已抓 {stats.get('skipped_seen', 0)}，"
            f"过滤 {stats.get('skipped_filter', 0)}"
        )
        if paging.get("is_end", True):
            break
        offset += limit
        time.sleep(0.35)
    return items, title, stats


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/zhihu.py question <问题URL或ID> [--max-items N]")
        print("      --since-last 只补新；--min-voteup / --days / --since 过滤")
        sys.exit(1)

    qid = extract_question_id(sys.argv[1])
    if not qid:
        print("无法从输入中提取问题 ID")
        sys.exit(1)

    max_items = resolve_limit(
        "question.max_answers",
        int(optional_arg("--max-items"))
        if (optional_arg("--max-items") or "").isdigit()
        else None,
    )
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
    summary = empty_summary(f"question:{qid}")

    items, title, stats = fetch_question_answers(
        qid, max_items, cookie_str, select_kwargs=select_kwargs
    )
    if not title:
        title = fetch_question_title(qid, cookie_str)
    bump(summary, "skipped_empty", stats.get("skipped_empty", 0))
    bump(summary, "skipped_seen", stats.get("skipped_seen", 0))
    bump(summary, "success", len(items))

    if not items:
        print("没有可抓取的回答（可能被过滤、已抓过，或需要登录）")
        note(summary, "无有效回答")
        if not cookie_str:
            bump(summary, "need_login")
        finish(summary, workspace)
        sys.exit(0)

    out = os.path.join(workspace, f"zhihu_question_{qid}.json")
    save_json(
        out,
        {
            "total": len(items),
            "question_id": qid,
            "title": title,
            "source": f"https://www.zhihu.com/question/{qid}",
            "kind": "question",
            "items": items,
        },
    )
    record_urls(items, f"question:{qid}", workspace, index=select_kwargs.get("index"))
    remember_fetched(select_kwargs, items)
    summary["outputs"].append(out)
    print(f"问题「{title or qid}」回答 {len(items)} 条（上限 {describe_limit(max_items)}）")
    if not cookie_str:
        bump(summary, "need_login")
        note(summary, "未检测到 Cookie")
    finish(summary, workspace)


if __name__ == "__main__":
    main()
