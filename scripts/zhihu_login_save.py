#!/usr/bin/env python3
"""知乎登录 + 保存 cookie 到文件"""
import asyncio
import os
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("请安装 playwright")
    sys.exit(1)

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
"""

COOKIE_FILE = os.path.join(os.path.expanduser('~'), '.openclaw', 'workspace', 'zhihu_cookies.json')

async def main():
    user_data_dir = os.path.join(os.path.expanduser('~'), '.openclaw', 'workspace', 'chrome_user_data')
    os.makedirs(user_data_dir, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1440, 'height': 900},
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        await context.add_init_script(STEALTH_SCRIPT)
        page = context.pages[0] if context.pages else await context.new_page()

        print("浏览器已打开，请登录知乎...")
        await page.goto('https://www.zhihu.com/', wait_until='domcontentloaded', timeout=30000)

        # 等待 z_c0 cookie
        for i in range(180):
            await asyncio.sleep(2)
            cookies = await context.cookies('https://www.zhihu.com')
            cookie_dict = {c['name']: c['value'] for c in cookies}

            if 'z_c0' in cookie_dict:
                print("\n登录成功! 保存 cookies...")
                # 保存到文件
                with open(COOKIE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(cookie_dict, f, ensure_ascii=False, indent=2)
                print(f"Cookies 已保存到: {COOKIE_FILE}")

                # 验证
                await page.goto('https://www.zhihu.com/collection/3146240766', wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(3)
                content = await page.evaluate('() => document.body.innerText')
                if '请登录后查看' not in content:
                    print("收藏夹访问验证通过!")
                break

            mins = (i * 2) // 60
            secs = (i * 2) % 60
            print(f"  等待登录... ({mins}分{secs}秒)", end='\r')
        else:
            print("\n超时")

        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
