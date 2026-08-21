#!/usr/bin/env python3
"""
知乎收藏夹列表抓取（智能版）

- 个人主页：列出公开收藏夹，自动跳过空夹
- 单个收藏夹：优先 API，失败再走浏览器内 fetch（不再只靠过时 DOM）
- 条目：无 URL / 非回答与文章 → 跳过；回答标题回退到问题标题
- 计数：max_items 只统计有效条目

用法:
  python fetch_zhihu_collection.py <收藏夹URL或ID> [最大数量]
  python fetch_zhihu_collection.py <个人主页URL> [--list-only]
  python fetch_zhihu_collection.py <个人主页URL> --per-collection 2 [--max-collections 10]
"""
import asyncio
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

from fetch_limits import describe_limit, resolve_limit
from workspace_paths import get_default_paths

FAVLIST_INCLUDE = (
    "data[*].answer_count,follower_count,updated_time,description,is_public"
)
STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
"""


def extract_collection_id(url_or_id):
    text = str(url_or_id)
    match = re.search(r"/collection/(\d+)", text)
    if match:
        return match.group(1)
    if re.fullmatch(r"\d+", text.strip()):
        return text.strip()
    return None


def parse_people_slug(raw):
    text = str(raw).strip()
    if text.startswith("http://") or text.startswith("https://"):
        parts = [p for p in urllib.parse.urlparse(text).path.split("/") if p]
        if "people" in parts:
            idx = parts.index("people")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        return None
    if re.fullmatch(r"\d+", text) or "/collection/" in text:
        return None
    return text


def load_cookies():
    """Return Cookie header string, or empty string if missing."""
    cookie_file = get_default_paths()["cookie_file"]
    if not os.path.exists(cookie_file):
        return ""
    try:
        with open(cookie_file, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        if not cookies or "z_c0" not in cookies:
            return ""
        parts = []
        for name, value in cookies.items():
            if isinstance(value, dict):
                value = value.get("value", "")
            if value:
                parts.append(f"{name}={value}")
        return "; ".join(parts)
    except Exception:
        return ""


def collection_is_empty(fav):
    """Public favlists expose answer_count; 0 means no crawlable items."""
    if "answer_count" in fav and fav.get("answer_count") is not None:
        try:
            return int(fav.get("answer_count") or 0) <= 0
        except (TypeError, ValueError):
            return False
    return False


def normalize_item_url(url):
    url = (url or "").split("?")[0].strip()
    if url.startswith("http://"):
        url = "https://" + url[len("http://") :]
    if url.startswith("/"):
        url = "https://www.zhihu.com" + url
    return url


def normalize_collection_item(content):
    """Skip empty / unsupported items; fill answer titles from the question."""
    if not isinstance(content, dict):
        return None
    ctype = content.get("type") or ""
    url = normalize_item_url(content.get("url") or "")
    title = (content.get("title") or "").strip()
    if ctype == "article":
        article_id = content.get("id")
        if "zhuanlan.zhihu.com/p/" not in url and article_id:
            url = f"https://zhuanlan.zhihu.com/p/{article_id}"
        title = title or f"article_{article_id}"
    elif ctype == "answer":
        question = content.get("question") or {}
        qid = question.get("id")
        aid = content.get("id")
        if qid and aid:
            url = f"https://www.zhihu.com/question/{qid}/answer/{aid}"
        title = (question.get("title") or title or f"answer_{aid}").strip()
    elif url:
        if "/p/" in url:
            ctype = "article"
        elif "/answer/" in url:
            ctype = "answer"
        else:
            return None
    else:
        return None
    if not url:
        return None
    author = ((content.get("author") or {}).get("name")) or ""
    return {
        "url": url,
        "title": title,
        "author": author,
        "voteup": content.get("voteup_count", 0),
        "type": ctype,
    }


def _request_json(url, cookie_str="", referer="https://www.zhihu.com/"):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": referer,
        "Accept": "application/json, text/plain, */*",
    }
    if cookie_str:
        headers["Cookie"] = cookie_str
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8")), response.status


def list_member_favlists(slug, cookie_str=""):
    """List public collections for a people slug (works without login)."""
    all_items = []
    offset = 0
    limit = 20
    while True:
        params = urllib.parse.urlencode(
            {"offset": offset, "limit": limit, "include": FAVLIST_INCLUDE}
        )
        url = f"https://www.zhihu.com/api/v4/members/{slug}/favlists?{params}"
        try:
            data, _status = _request_json(
                url,
                cookie_str=cookie_str,
                referer=f"https://www.zhihu.com/people/{slug}/collections",
            )
        except Exception as exc:
            print(f"[favlists] {exc}")
            break
        rows = data.get("data") or []
        paging = data.get("paging") or {}
        for row in rows:
            fav = {
                "id": str(row.get("id") or ""),
                "title": row.get("title") or "",
                "is_public": bool(row.get("is_public", True)),
                "answer_count": row.get("answer_count"),
                "follower_count": row.get("follower_count"),
                "updated_time": row.get("updated_time"),
                "description": row.get("description") or "",
                "url": f"https://www.zhihu.com/collection/{row.get('id')}",
            }
            if fav["id"]:
                all_items.append(fav)
        if paging.get("is_end", True) or not rows:
            break
        offset += limit
        time.sleep(0.3)
    return all_items


def fetch_via_api(collection_id, max_items=0, cookie_str=""):
    items, _status = fetch_via_api_with_status(collection_id, max_items, cookie_str)
    return items


def fetch_via_api_with_status(collection_id, max_items=0, cookie_str=""):
    """Fetch collection items via API. status is HTTP code or 0 on other errors."""
    print(f"[API] 获取收藏夹 {collection_id}")
    all_items = []
    skipped = 0
    offset = 0
    limit = 20
    last_status = 0

    while True:
        url = (
            f"https://www.zhihu.com/api/v4/collections/{collection_id}/items"
            f"?offset={offset}&limit={limit}"
        )
        try:
            data, last_status = _request_json(
                url,
                cookie_str=cookie_str,
                referer=f"https://www.zhihu.com/collection/{collection_id}",
            )
        except urllib.error.HTTPError as exc:
            last_status = exc.code
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
            info = normalize_collection_item(row.get("content") or {})
            if not info:
                skipped += 1
                continue
            all_items.append(info)
            if max_items and len(all_items) >= max_items:
                print(
                    f"[API] 完成，有效 {len(all_items)} 条，跳过空项 {skipped}"
                )
                return all_items, last_status

        print(f"  本页 {len(rows)} 条，有效累计 {len(all_items)}，跳过 {skipped}")
        if paging.get("is_end", True):
            break
        offset += limit
        time.sleep(0.5)

    print(f"[API] 完成，有效 {len(all_items)} 条，跳过空项 {skipped}")
    return all_items, last_status


async def fetch_via_browser(collection_id, max_items=0):
    """In-page fetch of the items API using the persistent Chrome profile."""
    print(f"[浏览器] 获取收藏夹 {collection_id}")
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[浏览器] 请先安装 playwright")
        return []

    paths = get_default_paths()
    all_items = []
    skipped = 0

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            paths["user_data_dir"],
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
        )
        await context.add_init_script(STEALTH_SCRIPT)
        page = context.pages[0] if context.pages else await context.new_page()

        cookie_str = load_cookies()
        if cookie_str:
            cookie_list = []
            for part in cookie_str.split("; "):
                if "=" not in part:
                    continue
                name, value = part.split("=", 1)
                cookie_list.append(
                    {"name": name, "value": value, "domain": ".zhihu.com", "path": "/"}
                )
            if cookie_list:
                await context.add_cookies(cookie_list)

        collection_url = f"https://www.zhihu.com/collection/{collection_id}"
        print(f"  访问: {collection_url}")
        await page.goto(collection_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        if "unhuman" in page.url or "/signin" in page.url:
            print("[浏览器] 需要登录")
            await context.close()
            return []

        offset = 0
        limit = 20
        while True:
            api_url = (
                f"https://www.zhihu.com/api/v4/collections/{collection_id}/items"
                f"?offset={offset}&limit={limit}"
            )
            payload = await page.evaluate(
                """async (url) => {
                    const response = await fetch(url, {credentials: 'include'});
                    const text = await response.text();
                    return {ok: response.ok, status: response.status, text};
                }""",
                api_url,
            )
            if not payload.get("ok"):
                print(f"  [浏览器] HTTP {payload.get('status')}")
                break
            data = json.loads(payload.get("text") or "{}")
            rows = data.get("data") or []
            paging = data.get("paging") or {}
            if not rows:
                break
            for row in rows:
                info = normalize_collection_item(row.get("content") or {})
                if not info:
                    skipped += 1
                    continue
                all_items.append(info)
                if max_items and len(all_items) >= max_items:
                    await context.close()
                    print(
                        f"[浏览器] 完成，有效 {len(all_items)} 条，跳过空项 {skipped}"
                    )
                    return all_items
            if paging.get("is_end", True):
                break
            offset += limit
            await asyncio.sleep(0.4)

        await context.close()

    print(f"[浏览器] 完成，有效 {len(all_items)} 条，跳过空项 {skipped}")
    return all_items


def fetch_collection_items(collection_id, max_items=0, allow_browser=True):
    cookie_str = load_cookies()
    items, status = fetch_via_api_with_status(collection_id, max_items, cookie_str)
    if items:
        return items
    if status in (401, 403) and not cookie_str:
        print("[跳过] 无 Cookie，收藏夹条目 API 未授权，不启动浏览器")
        return []
    if allow_browser:
        print("\n[API] 无有效条目，降级到浏览器...")
        return asyncio.run(fetch_via_browser(collection_id, max_items))
    return []


def save_json(path, payload):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"已保存到: {path}")


def optional_arg(name, default=None):
    if name not in sys.argv:
        return default
    idx = sys.argv.index(name)
    if idx + 1 < len(sys.argv) and not sys.argv[idx + 1].startswith("--"):
        return sys.argv[idx + 1]
    return default


def main():
    if len(sys.argv) < 2:
        print("用法: python fetch_zhihu_collection.py <收藏夹URL或ID|个人主页> [最大数量]")
        print("      python fetch_zhihu_collection.py <个人主页> --per-collection [N]")
        print("      python fetch_zhihu_collection.py <个人主页> --list-only")
        print("      上限见 zhihu_fetch_config.json；--all 取消限制")
        sys.exit(1)

    url_or_id = sys.argv[1]
    positional_max = int(sys.argv[2]) if len(sys.argv) >= 3 and sys.argv[2].isdigit() else None
    max_items = resolve_limit("collection.max_items", positional_max)
    per_raw = optional_arg("--per-collection")
    per_collection = resolve_limit(
        "collection.items_per_collection",
        int(per_raw) if per_raw and str(per_raw).isdigit() else None,
    )
    max_col_raw = optional_arg("--max-collections")
    max_collections = resolve_limit(
        "collection.max_collections",
        int(max_col_raw) if max_col_raw and str(max_col_raw).isdigit() else None,
    )
    list_only = "--list-only" in sys.argv

    workspace = get_default_paths()["workspace"]
    os.makedirs(workspace, exist_ok=True)

    slug = parse_people_slug(url_or_id)
    if slug:
        print(f"个人主页: https://www.zhihu.com/people/{slug}")
        favlists = list_member_favlists(slug, load_cookies())
        empty = [c for c in favlists if collection_is_empty(c)]
        nonempty = [c for c in favlists if not collection_is_empty(c)]
        print(f"收藏夹: {len(favlists)} 个，空夹跳过 {len(empty)}，有效 {len(nonempty)}")
        for fav in empty:
            print(f"  [跳过空夹] {fav['id']} {fav['title']}")
        if max_collections:
            nonempty = nonempty[:max_collections]
            print(f"本次最多处理 {len(nonempty)} 个有效收藏夹（上限 {describe_limit(max_collections)}）")

        summary = {
            "source": f"https://www.zhihu.com/people/{slug}",
            "total": len(favlists),
            "empty_skipped": len(empty),
            "items": favlists,
        }
        save_json(os.path.join(workspace, f"zhihu_favlists_{slug}.json"), summary)

        if list_only:
            print("仅列出收藏夹（--list-only）")
            return
        if "--per-collection" not in sys.argv:
            print(
                "仅列出收藏夹。抓取条目请加 --per-collection"
                f"（默认每夹 {describe_limit(per_collection)} 篇）"
            )
            return

        for fav in nonempty:
            cid = fav["id"]
            print()
            print(f"=== {fav['title']} ({cid}) 抽 {describe_limit(per_collection)} 篇 ===")
            items = fetch_collection_items(cid, per_collection)
            if not items:
                print(f"[跳过] 收藏夹 {cid} 无有效条目")
                continue
            capped = items if not per_collection else items[:per_collection]
            save_json(
                os.path.join(workspace, f"zhihu_collection_{cid}.json"),
                {
                    "total": len(capped),
                    "collection_id": cid,
                    "title": fav["title"],
                    "items": capped,
                },
            )
        return

    collection_id = extract_collection_id(url_or_id)
    if not collection_id:
        print("无法从输入中提取收藏夹 ID 或个人主页 slug")
        sys.exit(1)

    print(f"收藏夹 ID: {collection_id}")
    print(f"最大数量: {describe_limit(max_items)}（配置 collection.max_items，可用 --all 取消）")
    print()

    items = fetch_collection_items(collection_id, max_items)
    if not items:
        print("\n获取失败或收藏夹为空，已跳过。")
        print("若条目 API 返回 401，请运行 python scripts/zhihu_relogin.py")
        sys.exit(0)

    save_json(
        os.path.join(workspace, f"zhihu_collection_{collection_id}.json"),
        {"total": len(items), "collection_id": collection_id, "items": items},
    )


if __name__ == "__main__":
    main()
