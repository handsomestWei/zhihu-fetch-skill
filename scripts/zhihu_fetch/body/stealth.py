#!/usr/bin/env python3
"""
知乎文章抓取 - Playwright 隐身模式
使用反检测技术的无头浏览器，模拟真实用户行为。
用法: python fetch_zhihu_stealth.py <文章URL>
"""

import asyncio
import re
import json
import random
import sys

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("请先安装 playwright: pip install playwright && playwright install chromium")
    sys.exit(1)


STEALTH_SCRIPT = """
// 移除 webdriver 标记
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// 伪造 plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5]
});

// 伪造 languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['zh-CN', 'zh', 'en']
});

// 移除 automation 属性
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;

// 伪造 chrome 对象
window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
"""


def html_to_text(html_content):
    text = re.sub(r'<[^>]+>', ' ', html_content)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_from_initial_data(html):
    """从页面 HTML 中提取 __INITIAL_DATA__"""
    match = re.search(r'window\.__INITIAL_DATA__\s*=\s*({.*?});', html, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            article = data.get('data', {})
            if article:
                title = article.get('title', '')
                author = article.get('author', {}).get('name', '')
                content_html = article.get('content', '')
                content = html_to_text(content_html) if content_html else ''
                if content:
                    return {'title': title, 'author': author, 'content': content}
        except json.JSONDecodeError:
            pass
    return None


async def fetch_zhihu_stealth(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--disable-gpu',
            ]
        )

        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1440, 'height': 900},
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
            extra_http_headers={
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"macOS"',
            }
        )

        await context.add_init_script(STEALTH_SCRIPT)
        page = await context.new_page()

        try:
            # 先访问知乎首页，模拟真实用户
            print("模拟用户行为，访问知乎首页...")
            await page.goto('https://www.zhihu.com/', wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(random.randint(2000, 4000))
            await page.evaluate('window.scrollBy(0, 300)')
            await page.wait_for_timeout(random.randint(1000, 2000))

            # 访问目标文章
            print(f"正在访问文章: {url}")
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            await page.wait_for_timeout(random.randint(5000, 8000))

            # 模拟阅读滚动
            for _ in range(3):
                await page.evaluate(f'window.scrollBy(0, {random.randint(200, 500)})')
                await page.wait_for_timeout(random.randint(500, 1500))

            print("正在提取内容...")

            # 尝试从 initial data 提取
            html = await page.content()
            result = extract_from_initial_data(html)
            if result:
                await browser.close()
                return result

            # 从 DOM 提取
            result = await page.evaluate('''() => {
                const getData = (selectors) => {
                    for (let sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText) return el.innerText.trim();
                    }
                    return '';
                };
                return {
                    title: getData(['h1.Post-Title', 'h1[class*="Title"]', 'h1']),
                    author: getData(['.AuthorInfo-name', 'a[class*="Author"]']),
                    content: getData(['.Post-RichText', '.RichText', 'article', 'main'])
                };
            }''')

            await browser.close()
            return result if result.get('content') else None

        except Exception as e:
            print(f"抓取失败: {e}")
            await browser.close()
            return None


def format_output(title, author, url, content):
    return "\n".join([
        f"标题: {title}",
        f"作者: {author}",
        f"原文链接: {url}",
        "",
        "=" * 50,
        "",
        content,
    ])


async def main():
    if len(sys.argv) < 2:
        print("用法: python fetch_zhihu_stealth.py <文章URL>")
        sys.exit(1)

    url = sys.argv[1]
    print(f"正在使用隐身模式获取: {url}")

    result = await fetch_zhihu_stealth(url)
    if result:
        output = format_output(result['title'], result['author'], url, result['content'])
        print(output)

        # 从 URL 提取 ID 用于文件名
        match = re.search(r'/p/(\d+)', url)
        article_id = match.group(1) if match else 'unknown'
        output_file = f"zhihu_{article_id}.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"\n已保存到 {output_file}")
    else:
        print("抓取失败，请尝试交互模式")


if __name__ == "__main__":
    asyncio.run(main())
