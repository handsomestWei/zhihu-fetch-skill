"""Live smoke tests against real Zhihu.

Profile URL comes solely from live_profile.py.

1. List public collections, skip empty ones, cap at LIVE_MAX_ITEMS.
2. From each remaining collection, fetch LIVE_ITEMS_PER_COLLECTION items
   (needs login for the items API; without Cookie we skip and fall back).
3. Write Markdown + images; skip empty / blocked bodies.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import requests

from fetch_zhihu_api import extract_article_id, fetch_via_api, fetch_via_page
from fetch_zhihu_batch import extra_frontmatter, html_to_markdown
from fetch_zhihu_collection import (
    collection_is_empty,
    fetch_via_api_with_status,
    list_member_favlists,
    load_cookies,
    parse_people_slug,
    save_json,
)
from live_profile import (
    LIVE_ITEMS_PER_COLLECTION,
    LIVE_LOOKBACK_DAYS,
    LIVE_MAX_ITEMS,
    LIVE_PROFILE_URL,
)
from workspace_paths import get_workspace_dir

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
HISTORY_SCRIPT = SCRIPTS / "fetch_zhihu_history.py"
ANSWER_API = "https://www.zhihu.com/api/v4/answers/{id}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.zhihu.com/",
}


def _subprocess_env():
    return {k: v for k, v in os.environ.items() if k != "ZHIHU_WORKSPACE"}


def _run_history(workspace: Path, max_items: int):
    cutoff = datetime.now(ZoneInfo("Asia/Shanghai")) - timedelta(days=LIVE_LOOKBACK_DAYS)
    out_json = workspace / "live_test_history.json"
    result = subprocess.run(
        [
            sys.executable,
            str(HISTORY_SCRIPT),
            LIVE_PROFILE_URL,
            cutoff.strftime("%Y-%m-%dT00:00:00+08:00"),
            str(out_json),
            "--fresh",
            "--max-items",
            str(max_items),
        ],
        cwd=str(SCRIPTS),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        env=_subprocess_env(),
    )
    return result, out_json


def _fetch_answer(url: str) -> tuple[str, str, str]:
    answer_id = url.rstrip("/").split("/")[-1]
    response = requests.get(
        ANSWER_API.format(id=answer_id),
        params={"include": "content,excerpt,author,question"},
        headers={**HEADERS, "Referer": url},
        timeout=15,
    )
    if response.status_code != 200:
        raise RuntimeError(f"回答 API HTTP {response.status_code}: {url}")
    payload = response.json()
    question = payload.get("question") or {}
    title = question.get("title") or f"回答 {answer_id}"
    author = ((payload.get("author") or {}).get("name")) or ""
    html = payload.get("content") or payload.get("excerpt") or ""
    return title, author, html


def _fetch_article(url: str) -> tuple[str, str, str]:
    article_id = extract_article_id(url)
    data = {}
    try:
        data = fetch_via_api(article_id, timeout=15)
    except Exception:
        data = {}
    html = data.get("content") or ""
    if len(html) < 20:
        cookie = load_cookies()
        if cookie:
            response = requests.get(
                f"https://zhuanlan.zhihu.com/api/articles/{article_id}",
                headers={**HEADERS, "Cookie": cookie, "Referer": url},
                timeout=15,
            )
            if response.status_code == 200:
                data = response.json()
                html = data.get("content") or ""
    if len(html) < 20:
        data = fetch_via_page(url, timeout=15) or data or {}
        html = data.get("content") or ""
    title = data.get("title") or f"文章 {article_id}"
    author = ((data.get("author") or {}).get("name")) or ""
    return title, author, html


def _write_markdown(item: dict, index: int, output_dir: Path, images_dir: Path) -> Path | None:
    url = (item.get("url") or "").strip()
    if not url:
        print(f"skip empty url index={index}")
        return None
    if "/p/" in url:
        title, author, html = _fetch_article(url)
    else:
        title, author, html = _fetch_answer(url)
    if not html or len(html) < 20:
        print(f"skip empty body: {url}")
        return None

    markdown, images, _sources = html_to_markdown(html, str(images_dir))
    if not markdown.strip():
        print(f"skip empty markdown: {url}")
        return None

    author = item.get("author") or author
    voteup = item.get("voteup", 0)
    final_title = (title or "").strip() or f"文章{index}"
    safe_title = re.sub(r'[\\/:*?"<>|]', "_", final_title)[:80]
    filepath = output_dir / f"{index:04d}_{safe_title}.md"
    filepath.write_text(
        f"""---
title: {json.dumps(final_title, ensure_ascii=False)}
author: {json.dumps(author, ensure_ascii=False)}
source: zhihu
url: {json.dumps(url, ensure_ascii=False)}
voteup: {voteup}
images: {len(images)}
{extra_frontmatter(item)}
---

# {final_title}

> 作者: {author} | 原文: [知乎链接]({url})

{markdown}
""",
        encoding="utf-8",
    )
    return filepath


def _write_items(items: list[dict], output_dir: Path, images_dir: Path) -> list[Path]:
    written = []
    for i, item in enumerate(items, start=1):
        try:
            path = _write_markdown(item, i, output_dir, images_dir)
        except Exception as exc:
            print(f"skip failed body {item.get('url')}: {exc}")
            continue
        if path is None:
            continue
        written.append(path)
        print(f"wrote {path.name} ({path.stat().st_size} bytes)")
    return written


def test_live_collections_sample_two_each_skip_empty():
    workspace = Path(get_workspace_dir())
    articles_dir = workspace / "zhihu_articles_live_test"
    images_dir = articles_dir / "images"
    articles_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    slug = parse_people_slug(LIVE_PROFILE_URL)
    assert slug, LIVE_PROFILE_URL
    print(f"workspace: {workspace}")
    print(f"max_collections: {LIVE_MAX_ITEMS} per_collection: {LIVE_ITEMS_PER_COLLECTION}")

    favlists = list_member_favlists(slug)
    empty = [fav for fav in favlists if collection_is_empty(fav)]
    nonempty = [fav for fav in favlists if not collection_is_empty(fav)]
    sampled = nonempty[:LIVE_MAX_ITEMS]
    print(f"favlists={len(favlists)} empty_skipped={len(empty)} nonempty={len(nonempty)}")
    for fav in empty:
        print(f"skip empty collection {fav['id']} {fav['title']}")
    assert favlists, "未能列出公开收藏夹"
    assert sampled, "有效收藏夹为空（全是空夹）"

    save_json(
        str(workspace / f"zhihu_favlists_{slug}.json"),
        {
            "source": LIVE_PROFILE_URL,
            "total": len(favlists),
            "empty_skipped": len(empty),
            "items": favlists,
        },
    )

    cookie = load_cookies()
    sampled_items: list[dict] = []
    auth_blocked = False
    for fav in sampled:
        items, status = fetch_via_api_with_status(
            fav["id"], LIVE_ITEMS_PER_COLLECTION, cookie
        )
        if status in (401, 403) and not cookie:
            print(f"collection items API HTTP {status} without cookie; skip remaining")
            auth_blocked = True
            break
        if not items:
            print(f"skip collection with no valid items: {fav['id']} {fav['title']}")
            continue
        items = items[:LIVE_ITEMS_PER_COLLECTION]
        save_json(
            str(workspace / f"zhihu_collection_{fav['id']}.json"),
            {
                "total": len(items),
                "collection_id": fav["id"],
                "title": fav["title"],
                "items": items,
            },
        )
        for item in items:
            item = dict(item)
            item["collection_id"] = fav["id"]
            item["collection_title"] = fav["title"]
            sampled_items.append(item)
        print(f"collection {fav['title']}: {len(items)} items")

    source = "collections"
    if not sampled_items:
        print("收藏夹条目需要登录，回退个人动态列表")
        hist, out_json = _run_history(workspace, LIVE_MAX_ITEMS)
        print(hist.stdout)
        if hist.returncode != 0:
            pytest.fail(
                "收藏夹条目不可用，且个人动态抓取失败。\n"
                f"stdout={hist.stdout[-800:]}\n"
                f"stderr={hist.stderr[-800:]}"
            )
        sampled_items = json.loads(out_json.read_text(encoding="utf-8")).get("items") or []
        source = "history-fallback"
        assert sampled_items, "动态列表也没有有效条目"

    written = _write_items(sampled_items, articles_dir, images_dir)
    image_files = [p for p in images_dir.iterdir() if p.is_file()]
    print(
        f"source={source} auth_blocked={auth_blocked} "
        f"items={len(sampled_items)} markdown={len(written)} images={len(image_files)}"
    )
    assert written, "没有写出任何 Markdown（空项已跳过）"
    for img in image_files[:5]:
        assert img.stat().st_size > 0
