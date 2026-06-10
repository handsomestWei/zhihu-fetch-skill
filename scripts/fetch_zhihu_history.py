#!/usr/bin/env python3
"""
Collect recent liked/collected Zhihu feed items from a profile activity page.

The output JSON matches fetch_zhihu_batch.py's input shape, with extra
interaction metadata preserved per item.

Usage:
  python fetch_zhihu_history.py <profile-url-or-slug> <cutoff-iso> [output-json] [--until <until-iso>]

Example:
  python fetch_zhihu_history.py duan-mu-yue-dao 2026-05-05T00:00:00+08:00

Timezone: cutoff/--until 建议带时区（如 +08:00）。若省略时区，默认 Asia/Shanghai；
可通过环境变量 ZHIHU_TIMEZONE 或 TZ 覆盖（如 Europe/Paris）。
"""

import asyncio
import datetime as dt
import json
import os
import re
import sys
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding="utf-8")

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("请先安装 playwright: pip install playwright && playwright install chromium")
    sys.exit(1)


WORKSPACE = os.environ.get(
    "OPENCLAW_WORKSPACE", os.path.join(os.path.expanduser("~"), ".openclaw", "workspace")
)

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
"""

LIKED_OR_COLLECTED_PREFIXES = ("赞同了", "喜欢了", "收藏了")
TARGET_TYPES = {"answer", "article"}


def load_cookies():
    cookie_file = os.path.join(WORKSPACE, "zhihu_cookies.json")
    if not os.path.exists(cookie_file):
        return None
    try:
        with open(cookie_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data:
            return None
        result = {}
        for k, v in data.items():
            if isinstance(v, dict):
                result[k] = v
            else:
                result[k] = {"value": v, "domain": ".zhihu.com", "path": "/"}
        return result
    except Exception:
        return None


def parse_slug(raw):
    raw = raw.strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        parts = [p for p in urlparse(raw).path.split("/") if p]
        if "people" in parts:
            idx = parts.index("people")
            if idx + 1 < len(parts):
                return parts[idx + 1]
    return raw.rstrip("/")


def default_timezone():
    """无时区 ISO 时间的默认解释；与 zhihu_login 等脚本一致优先中国时区。"""
    from zoneinfo import ZoneInfo

    name = (os.environ.get("ZHIHU_TIMEZONE") or os.environ.get("TZ") or "Asia/Shanghai").strip()
    if not name:
        name = "Asia/Shanghai"
    try:
        return ZoneInfo(name)
    except Exception:
        print(f"[!] invalid timezone {name!r}; fallback to Asia/Shanghai")
        return ZoneInfo("Asia/Shanghai")


def parse_cutoff(raw):
    value = raw.strip().replace(" ", "T")
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        tz = default_timezone()
        print(f"[!] time has no timezone; assuming {tz.key}")
        parsed = parsed.replace(tzinfo=tz)
    return parsed


def optional_arg(name, default=None):
    if name not in sys.argv:
        return default
    try:
        return sys.argv[sys.argv.index(name) + 1]
    except Exception:
        return default


def activity_ms(activity):
    try:
        return int(activity.get("id") or 0)
    except Exception:
        return 0


def iso_from_ms(ms):
    if not ms:
        return ""
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isoformat()


def web_url(target):
    target_type = target.get("type")
    if target_type == "article":
        url = target.get("url") or ""
        if "zhuanlan.zhihu.com/p/" in url:
            return url.split("?")[0]
        if target.get("id"):
            return f"https://zhuanlan.zhihu.com/p/{target['id']}"
    if target_type == "answer":
        question = target.get("question") or {}
        qid = question.get("id")
        aid = target.get("id")
        if qid and aid:
            return f"https://www.zhihu.com/question/{qid}/answer/{aid}"
    return None


def item_from_activity(activity):
    action = activity.get("action_text") or activity.get("verb") or activity.get("action") or ""
    target = activity.get("target") or {}
    target_type = target.get("type")
    if target_type not in TARGET_TYPES:
        return None
    if not action.startswith(LIKED_OR_COLLECTED_PREFIXES):
        return None

    url = web_url(target)
    if not url:
        return None

    if target_type == "answer":
        title = (target.get("question") or {}).get("title") or f"answer_{target.get('id')}"
    else:
        title = target.get("title") or f"article_{target.get('id')}"

    author = (target.get("author") or {}).get("name", "")
    ms = activity_ms(activity)
    return {
        "url": url,
        "title": title,
        "author": author,
        "voteup": target.get("voteup_count", 0),
        "type": target_type,
        "interaction_action": action,
        "interaction_time": iso_from_ms(ms),
        "activity_id": activity.get("id", ""),
    }


def state_path_for(output_json):
    return f"{output_json}.state.json"


def load_state(output_json):
    state_path = state_path_for(output_json)
    state = {}
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = {}
    if not state and os.path.exists(output_json):
        try:
            with open(output_json, "r", encoding="utf-8") as f:
                existing = json.load(f)
            state = {"items": existing.get("items", [])}
        except Exception:
            state = {}
    state.setdefault("items", [])
    state.setdefault("seen_activity_urls", [])
    state.setdefault("oldest_seen_ms", 0)
    state.setdefault("completed", False)
    return state


def save_checkpoint(
    output_json,
    profile_url,
    cutoff,
    until,
    items,
    seen_activity_urls,
    oldest_seen_ms,
    completed=False,
):
    items.sort(key=lambda item: item.get("interaction_time", ""), reverse=True)
    output = {
        "total": len(items),
        "source": profile_url,
        "cutoff": cutoff.isoformat(),
        "until": until.isoformat() if until else "",
        "filter": "liked_or_collected_answers_and_articles",
        "items": items,
    }
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    state = {
        "items": items,
        "seen_activity_urls": sorted(seen_activity_urls),
        "oldest_seen_ms": oldest_seen_ms,
        "completed": completed,
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    with open(state_path_for(output_json), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


async def main():
    if len(sys.argv) < 3:
        print("用法: python fetch_zhihu_history.py <profile-url-or-slug> <cutoff-iso> [output-json]")
        print("示例: python fetch_zhihu_history.py duan-mu-yue-dao 2026-05-05T00:00:00+02:00")
        sys.exit(1)

    slug = parse_slug(sys.argv[1])
    cutoff = parse_cutoff(sys.argv[2])
    cutoff_ms = int(cutoff.timestamp() * 1000)
    until_raw = optional_arg("--until")
    until = parse_cutoff(until_raw) if until_raw else None
    until_ms = int(until.timestamp() * 1000) if until else None
    output_json = (
        sys.argv[3]
        if len(sys.argv) >= 4 and not sys.argv[3].startswith("--")
        else os.path.join(WORKSPACE, f"zhihu_people_{slug}_history_since_{cutoff.date()}.json")
    )

    os.makedirs(WORKSPACE, exist_ok=True)
    profile_url = f"https://www.zhihu.com/people/{slug}"
    print(f"profile: {profile_url}")
    print(f"cutoff: {cutoff.isoformat()}")
    if until:
        print(f"until: {until.isoformat()}")

    state = {} if "--fresh" in sys.argv else load_state(output_json)
    items = state.get("items", [])
    seen_urls = {item.get("url") for item in items if item.get("url")}
    seen_activity_urls = set(state.get("seen_activity_urls", []))
    oldest_seen_ms = int(state.get("oldest_seen_ms") or 0)
    if state.get("completed"):
        print(f"[resume] previous run was complete; refreshing from the first feed page")
        seen_activity_urls = set()
        oldest_seen_ms = 0
    elif items or seen_activity_urls:
        print(
            f"[resume] loaded items={len(items)} feed_pages={len(seen_activity_urls)} "
            f"oldest={iso_from_ms(oldest_seen_ms)}"
        )
    response_tasks = []
    start_url = f"https://www.zhihu.com/api/v3/moments/{slug}/activities?limit=5&desktop=true&ws_qiangzhisafe=0"

    async def process_payload(payload):
        nonlocal oldest_seen_ms
        activities = payload.get("data") or []
        for activity in activities:
            ms = activity_ms(activity)
            if ms:
                oldest_seen_ms = ms if not oldest_seen_ms else min(oldest_seen_ms, ms)
            if until_ms and ms and ms >= until_ms:
                continue
            if ms and ms < cutoff_ms:
                continue
            item = item_from_activity(activity)
            if not item or item["url"] in seen_urls:
                continue
            seen_urls.add(item["url"])
            items.append(item)

    async def on_response(response):
        url = response.url
        if "/api/v3/moments/" not in url or "/activities" not in url:
            return
        if url in seen_activity_urls:
            return
        seen_activity_urls.add(url)
        try:
            payload = await response.json()
            await process_payload(payload)
            print(
                f"feed_pages={len(seen_activity_urls)} items={len(items)} "
                f"oldest={iso_from_ms(oldest_seen_ms)}"
            )
            save_checkpoint(
                output_json,
                profile_url,
                cutoff,
                until,
                items,
                seen_activity_urls,
                oldest_seen_ms,
                completed=False,
            )
        except Exception as exc:
            print(f"[!] failed to parse activity response: {exc}")

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            os.path.join(WORKSPACE, "chrome_user_data"),
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
        )
        await context.add_init_script(STEALTH_SCRIPT)
        page = context.pages[0] if context.pages else await context.new_page()

        saved_cookies = load_cookies()
        if saved_cookies:
            cookie_list = []
            for name, meta in saved_cookies.items():
                cookie_list.append({
                    "name": name,
                    "value": meta.get("value", ""),
                    "domain": meta.get("domain", ".zhihu.com"),
                    "path": meta.get("path", "/"),
                })
            await context.add_cookies(cookie_list)
            print(f"injected cookies: {len(cookie_list)}")

        def schedule_response(response):
            response_tasks.append(asyncio.create_task(on_response(response)))

        page.on("response", schedule_response)
        await page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        active_fetch_done = False
        next_url = start_url
        for _ in range(300):
            if oldest_seen_ms and oldest_seen_ms < cutoff_ms:
                break
            if next_url in seen_activity_urls:
                break
            payload = await page.evaluate(
                """async (url) => {
                    const response = await fetch(url, {credentials: 'include'});
                    const text = await response.text();
                    return {ok: response.ok, status: response.status, text};
                }""",
                next_url,
            )
            if not payload.get("ok"):
                print(
                    f"[!] activity fetch failed: HTTP {payload.get('status')} "
                    f"{payload.get('text', '')[:200]} — falling back to scroll capture"
                )
                break
            data = json.loads(payload["text"])
            seen_activity_urls.add(next_url)
            await process_payload(data)
            active_fetch_done = True
            print(
                f"feed_pages={len(seen_activity_urls)} items={len(items)} "
                f"oldest={iso_from_ms(oldest_seen_ms)}"
            )
            save_checkpoint(
                output_json,
                profile_url,
                cutoff,
                until,
                items,
                seen_activity_urls,
                oldest_seen_ms,
                completed=False,
            )
            paging = data.get("paging") or {}
            if paging.get("is_end"):
                break
            next_url = paging.get("next")
            if not next_url:
                break

        stable_rounds = 0
        last_page_count = 0
        if not active_fetch_done:
            for _ in range(120):
                if oldest_seen_ms and oldest_seen_ms < cutoff_ms:
                    break
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1500)
                if response_tasks:
                    await asyncio.gather(*response_tasks, return_exceptions=True)
                    response_tasks.clear()
                page_count = len(seen_activity_urls)
                if page_count == last_page_count:
                    stable_rounds += 1
                else:
                    stable_rounds = 0
                    last_page_count = page_count
                if stable_rounds >= 8:
                    break

        if response_tasks:
            await asyncio.gather(*response_tasks, return_exceptions=True)
        await context.close()

    if not seen_activity_urls:
        print("[FAIL] no Zhihu activity feed pages were captured; profile may be on safety verification")
        sys.exit(2)

    save_checkpoint(
        output_json,
        profile_url,
        cutoff,
        until,
        items,
        seen_activity_urls,
        oldest_seen_ms,
        completed=True,
    )

    counts = {}
    actions = {}
    for item in items:
        counts[item["type"]] = counts.get(item["type"], 0) + 1
        actions[item["interaction_action"]] = actions.get(item["interaction_action"], 0) + 1
    print(f"saved: {output_json}")
    print(f"items: {len(items)}")
    print(f"types: {counts}")
    print(f"actions: {actions}")


if __name__ == "__main__":
    asyncio.run(main())
