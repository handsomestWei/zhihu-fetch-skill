#!/usr/bin/env python3
"""知乎登录辅助 - 严格检测 z_c0 cookie"""
import asyncio
import os
import sys

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


def get_default_paths():
    """与 fetch_zhihu_batch / zhihu_relogin 一致"""
    workspace = os.environ.get(
        "OPENCLAW_WORKSPACE",
        os.path.join(os.path.expanduser("~"), ".openclaw", "workspace"),
    )
    return {
        "workspace": workspace,
        "user_data_dir": os.path.join(workspace, "chrome_user_data"),
    }


def optional_verify_url():
    """登录后的可选二次校验：任意需登录才可看的知乎页面，须为完整 http(s) URL。"""
    raw = (os.environ.get("ZHIHU_VERIFY_URL") or "").strip()
    if not raw and len(sys.argv) > 1:
        raw = sys.argv[1].strip()
    if not raw:
        return None
    if not (raw.startswith("http://") or raw.startswith("https://")):
        print(
            f"\n[!] 可选验证须使用完整 URL（以 http:// 或 https:// 开头），已忽略: {raw!r}"
        )
        return None
    return raw


async def main():
    paths = get_default_paths()
    user_data_dir = paths["user_data_dir"]
    os.makedirs(paths["workspace"], exist_ok=True)

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
        print("重要：必须用手机号+验证码或扫码登录，不要用第三方登录")
        await page.goto('https://www.zhihu.com/', wait_until='domcontentloaded', timeout=30000)

        # 检测 z_c0 cookie
        logged_in = False
        for i in range(180):  # 最多等6分钟
            await asyncio.sleep(2)
            try:
                cookies = await context.cookies('https://www.zhihu.com')
                cookie_names = [c['name'] for c in cookies]
                
                if 'z_c0' in cookie_names:
                    print("\n检测到 z_c0 cookie，登录成功！")
                    logged_in = True
                    break
                
                mins = (i * 2) // 60
                secs = (i * 2) % 60
                print(f"  等待登录... ({mins}分{secs}秒) - 已有cookies: {len(cookies)}", end='\r')
            except Exception:
                pass

        if logged_in:
            verify_url = optional_verify_url()
            if verify_url:
                print(f"\n可选验证：打开指定页面 {verify_url}")
                await page.goto(
                    verify_url, wait_until="domcontentloaded", timeout=30000
                )
                await asyncio.sleep(3)
                content = await page.evaluate("() => document.body.innerText")
                if "请登录后查看" not in content:
                    print("可选验证：页面未出现「请登录后查看」，认为当前会话可访问该页。")
                else:
                    print("可选验证：页面仍提示需登录，请检查账号或稍后重试。")
        else:
            print("\n超时未检测到 z_c0，请确保已完成登录")

        await context.close()
        print("浏览器已关闭")

if __name__ == "__main__":
    asyncio.run(main())
