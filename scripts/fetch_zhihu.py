#!/usr/bin/env python3
"""
知乎文章抓取 - 三级降级入口
按优先级尝试三种方式获取文章，自动降级。
用法: python fetch_zhihu.py <文章URL或ID>
"""

import sys
import re


def extract_url(url_or_id):
    """统一为完整 URL"""
    if url_or_id.startswith('http'):
        return url_or_id
    if url_or_id.isdigit():
        return f"https://zhuanlan.zhihu.com/p/{url_or_id}"
    return url_or_id


def main():
    if len(sys.argv) < 2:
        print("用法: python fetch_zhihu.py <文章URL或ID>")
        print("示例: python fetch_zhihu.py https://zhuanlan.zhihu.com/p/2015027745743189513")
        print("      python fetch_zhihu.py 2015027745743189513")
        sys.exit(1)

    url = extract_url(sys.argv[1])
    match = re.search(r'/p/(\d+)', url)
    article_id = match.group(1) if match else 'unknown'

    # 方式1: API 直连
    print("=" * 50)
    print("[1/3] 尝试 API 直连...")
    print("=" * 50)
    try:
        from fetch_zhihu_api import fetch_via_api, html_to_text, format_output
        data = fetch_via_api(article_id)
        title = data.get('title', '未知标题')
        author = data.get('author', {}).get('name', '未知作者')
        publish_time = str(data.get('created', '未知时间'))
        content_html = data.get('content', '')
        content = html_to_text(content_html) if content_html else ''

        if content:
            output = format_output(title, author, publish_time, url, content)
            print(output)
            output_file = f"zhihu_{article_id}.txt"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"\n✅ API 直连成功，已保存到 {output_file}")
            return
    except Exception as e:
        print(f"❌ API 直连失败: {e}")

    # 方式2: Playwright 隐身模式
    print("\n" + "=" * 50)
    print("[2/3] 尝试 Playwright 隐身模式...")
    print("=" * 50)
    try:
        import asyncio
        from fetch_zhihu_stealth import fetch_zhihu_stealth, format_output as stealth_format
        result = asyncio.run(fetch_zhihu_stealth(url))
        if result and result.get('content'):
            output = stealth_format(result['title'], result['author'], url, result['content'])
            print(output)
            output_file = f"zhihu_{article_id}.txt"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"\n✅ 隐身模式成功，已保存到 {output_file}")
            return
    except Exception as e:
        print(f"❌ 隐身模式失败: {e}")

    # 方式3: Playwright 交互模式
    print("\n" + "=" * 50)
    print("[3/3] 尝试 Playwright 交互模式（需要手动操作）...")
    print("=" * 50)
    try:
        import asyncio
        from fetch_zhihu_interactive import fetch_zhihu_interactive, format_output as interactive_format
        result = asyncio.run(fetch_zhihu_interactive(url))
        if result and result.get('content'):
            output = interactive_format(result, url)
            print(output)
            output_file = f"zhihu_{article_id}.txt"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"\n✅ 交互模式成功，已保存到 {output_file}")
            return
    except Exception as e:
        print(f"❌ 交互模式失败: {e}")

    print("\n❌ 所有方式均失败，请检查网络或文章链接是否有效")


if __name__ == "__main__":
    main()
