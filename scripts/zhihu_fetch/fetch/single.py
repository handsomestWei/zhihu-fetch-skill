#!/usr/bin/env python3
"""
知乎抓取入口：单篇正文多级降级；其它链接转给统一路由。
用法: python fetch_zhihu.py <文章/回答URL或文章ID>
"""

import re
import sys

sys.stdout.reconfigure(encoding="utf-8")


def extract_url(url_or_id):
    """统一为完整 URL"""
    if url_or_id.startswith("http"):
        return url_or_id
    if url_or_id.isdigit():
        return f"https://zhuanlan.zhihu.com/p/{url_or_id}"
    return url_or_id


def _save(output, filename):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"\n已保存到 {filename}")


def _is_single_item(kind, raw, url):
    if kind in {"article", "answer"}:
        return True
    if raw.isdigit() or re.search(r"/p/\d+", url):
        return True
    return False


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/zhihu.py fetch <知乎URL或文章ID>")
        print("单篇: 专栏文章 /p/ 或回答链接；其它链接会转到 route")
        print("示例: python scripts/zhihu.py fetch https://zhuanlan.zhihu.com/p/2015027745743189513")
        sys.exit(1)

    raw = sys.argv[1]
    url = extract_url(raw)
    from zhihu_fetch.core.url import classify_zhihu_url

    target = classify_zhihu_url(url if url.startswith("http") else raw)
    if not _is_single_item(target.kind, raw, url):
        from zhihu_fetch.fetch.route import main as route_main

        route_main()
        return

    is_answer = target.kind == "answer" or bool(re.search(r"/answer/(\d+)", url))
    article_match = re.search(r"/p/(\d+)", url)
    item_id = (
        target.answer_id
        or (re.search(r"/answer/(\d+)", url).group(1) if is_answer else None)
        or (article_match.group(1) if article_match else raw)
    )

    if is_answer:
        print("=" * 50)
        print("[1/3] 尝试回答 API（带 Cookie）...")
        print("=" * 50)
        try:
            from zhihu_fetch.body.api import fetch_answer_via_api, format_output, html_to_text

            data = fetch_answer_via_api(item_id, referer=url)
            question = data.get("question") or {}
            title = question.get("title") or f"回答 {item_id}"
            author = ((data.get("author") or {}).get("name")) or "未知作者"
            content_html = data.get("content") or ""
            content = html_to_text(content_html) if content_html else ""
            if content:
                output = format_output(title, author, str(data.get("created_time", "")), url, content)
                print(output)
                _save(output, f"zhihu_answer_{item_id}.txt")
                print("\n✅ 回答 API 成功")
                return
        except Exception as e:
            print(f"❌ 回答 API 失败: {e}")
    else:
        print("=" * 50)
        print("[1/3] 尝试 API 直连（带 Cookie）...")
        print("=" * 50)
        try:
            from zhihu_fetch.body.api import fetch_via_api, format_output, html_to_text

            data = fetch_via_api(item_id)
            title = data.get("title", "未知标题")
            author = data.get("author", {}).get("name", "未知作者")
            publish_time = str(data.get("created", "未知时间"))
            content_html = data.get("content", "")
            content = html_to_text(content_html) if content_html else ""
            if content:
                output = format_output(title, author, publish_time, url, content)
                print(output)
                _save(output, f"zhihu_{item_id}.txt")
                print("\n✅ API 直连成功")
                return
        except Exception as e:
            print(f"❌ API 直连失败: {e}")

    print("\n" + "=" * 50)
    print("[2/3] 尝试 Playwright 隐身模式...")
    print("=" * 50)
    try:
        import asyncio
        from zhihu_fetch.body.stealth import fetch_zhihu_stealth, format_output as stealth_format

        result = asyncio.run(fetch_zhihu_stealth(url))
        if result and result.get("content"):
            output = stealth_format(result["title"], result["author"], url, result["content"])
            print(output)
            _save(output, f"zhihu_{item_id}.txt")
            print("\n✅ 隐身模式成功")
            return
    except Exception as e:
        print(f"❌ 隐身模式失败: {e}")

    print("\n" + "=" * 50)
    print("[3/3] 尝试 Playwright 交互模式（需要手动操作）...")
    print("=" * 50)
    try:
        import asyncio
        from zhihu_fetch.body.interactive import fetch_zhihu_interactive, format_output as interactive_format

        result = asyncio.run(fetch_zhihu_interactive(url))
        if result and result.get("content"):
            output = interactive_format(result, url)
            print(output)
            _save(output, f"zhihu_{item_id}.txt")
            print("\n✅ 交互模式成功")
            return
    except Exception as e:
        print(f"❌ 交互模式失败: {e}")

    print("\n❌ 所有方式均失败，请检查网络、登录态或链接是否有效")


if __name__ == "__main__":
    main()
