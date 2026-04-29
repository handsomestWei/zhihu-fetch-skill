#!/usr/bin/env python3
"""
知乎文章抓取 - Playwright 交互模式
打开有界面的浏览器，遇到验证码时可手动完成验证。登录状态会持久化保存。
用法: python fetch_zhihu_interactive.py <文章URL>
"""

import asyncio
import re
import sys
import os

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("请先安装 playwright: pip install playwright && playwright install chromium")
    sys.exit(1)


def get_user_data_dir():
    """获取浏览器用户数据目录（保存登录状态）"""
    workspace = os.environ.get('OPENCLAW_WORKSPACE',
                               os.path.join(os.path.expanduser('~'), '.openclaw', 'workspace'))
    data_dir = os.path.join(workspace, 'chrome_user_data')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def html_to_text(html_content):
    text = re.sub(r'<[^>]+>', ' ', html_content)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


async def fetch_zhihu_interactive(url):
    user_data_dir = get_user_data_dir()

    async with async_playwright() as p:
        print("启动浏览器（有界面模式）...")
        print("如遇验证码，请在浏览器中手动完成验证")

        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
            ]
        )

        # 移除 webdriver 属性
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = await context.new_page()

        try:
            print(f"正在访问: {url}")
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            await page.wait_for_timeout(3000)

            # 检查验证码
            page_content = await page.content()
            if '验证码' in page_content or 'captcha' in page_content.lower():
                print("\n" + "=" * 60)
                print("检测到验证码！请在浏览器中手动完成验证")
                print("完成后请在这里按回车继续...")
                print("=" * 60 + "\n")
                input()
                await page.wait_for_timeout(3000)

            # 等待页面加载
            print("等待页面完全加载...")
            await page.wait_for_timeout(5000)

            # 提取内容
            article_data = await page.evaluate('''() => {
                const getData = (selectors) => {
                    for (let sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText) return el.innerText.trim();
                    }
                    return '';
                };
                return {
                    title: getData(['h1.Post-Title', 'h1[class*="Title"]', 'article h1', 'h1']),
                    author: getData(['.AuthorInfo-name', 'a[class*="Author"]', 'span[class*="author"]']),
                    content: getData(['.Post-RichText', '.RichText', 'article', '[itemprop="articleBody"]']),
                    publishTime: (() => {
                        const el = document.querySelector('time') || document.querySelector('[datetime]');
                        return el ? (el.getAttribute('datetime') || el.innerText.trim()) : '';
                    })()
                };
            }''')

            # 如果未获取到内容，尝试获取整个页面文本
            if not article_data['content']:
                print("通过选择器未获取到内容，尝试获取全部文本...")
                all_text = await page.evaluate('() => document.body.innerText')
                article_data['content'] = all_text

            await context.close()
            return article_data

        except Exception as e:
            print(f"抓取失败: {e}")
            await context.close()
            return None


def format_output(data, url):
    return "\n".join([
        f"标题: {data.get('title', '未知标题')}",
        f"作者: {data.get('author', '未知作者')}",
        f"发布时间: {data.get('publishTime', '未知时间')}",
        f"原文链接: {url}",
        "",
        "=" * 50,
        "",
        data.get('content', ''),
    ])


async def main():
    if len(sys.argv) < 2:
        print("用法: python fetch_zhihu_interactive.py <文章URL>")
        sys.exit(1)

    url = sys.argv[1]
    print(f"正在使用交互模式获取: {url}")

    result = await fetch_zhihu_interactive(url)
    if result and result.get('content'):
        output = format_output(result, url)
        print(output)

        match = re.search(r'/p/(\d+)', url)
        article_id = match.group(1) if match else 'unknown'
        output_file = f"zhihu_{article_id}.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"\n已保存到 {output_file}")
    else:
        print("抓取失败")


if __name__ == "__main__":
    asyncio.run(main())
