#!/usr/bin/env python3
"""
知乎收藏夹文章列表抓取（智能版）
自动选择最佳方式获取收藏夹全部文章：
1. 优先使用 API（带 Cookie 认证，可获取全部）
2. 如果 API 失败，降级到 Playwright DOM 提取

用法: 
  python fetch_zhihu_collection.py <收藏夹URL或ID> [最大数量]
  
示例:
  python fetch_zhihu_collection.py https://www.zhihu.com/collection/3146240766
  python fetch_zhihu_collection.py 3146240766
  python fetch_zhihu_collection.py 3146240766 500
"""
import asyncio
import json
import re
import sys
import os
import time
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')

# 默认路径
WORKSPACE = os.environ.get('OPENCLAW_WORKSPACE',
                           os.path.join(os.path.expanduser('~'), '.openclaw', 'workspace'))
COOKIE_FILE = os.path.join(WORKSPACE, 'zhihu_cookies.json')

def extract_collection_id(url_or_id):
    """从 URL 或 ID 提取收藏夹 ID"""
    match = re.search(r'(\d+)', str(url_or_id))
    return match.group(1) if match else None

def load_cookies():
    """加载 cookie 文件"""
    if not os.path.exists(COOKIE_FILE):
        return None
    try:
        with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        if 'z_c0' not in cookies:
            return None
        return '; '.join(f'{k}={v}' for k, v in cookies.items())
    except Exception:
        return None

# ==================== 方式一：API 获取（完整版）====================

def fetch_via_api(collection_id, max_items=0, cookie_str=''):
    """通过 API 获取收藏夹文章列表（可获取全部）"""
    print(f"[API] 使用 API 方式获取收藏夹 {collection_id}")
    
    all_items = []
    offset = 0
    limit = 20
    
    while True:
        url = f'https://www.zhihu.com/api/v4/collections/{collection_id}/items?offset={offset}&limit={limit}'
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': f'https://www.zhihu.com/collection/{collection_id}',
            'Cookie': cookie_str,
        }
        
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode('utf-8'))
        except Exception as e:
            print(f"  [ERROR] {e}")
            break
        
        items = data.get('data', [])
        paging = data.get('paging', {})
        is_end = paging.get('is_end', True)
        
        if items:
            for item in items:
                content = item.get('content', {})
                info = {
                    'url': content.get('url', ''),
                    'title': content.get('title', ''),
                    'author': content.get('author', {}).get('name', ''),
                    'voteup': content.get('voteup_count', 0),
                    'type': content.get('type', ''),
                }
                if info['url']:
                    all_items.append(info)
            
            print(f"  获取 {len(items)} 条，累计 {len(all_items)} 条")
            
            if max_items and len(all_items) >= max_items:
                all_items = all_items[:max_items]
                break
        else:
            break
        
        if is_end:
            break
        
        offset += limit
        time.sleep(0.5)
    
    print(f"[API] 完成，共获取 {len(all_items)} 篇文章")
    return all_items

# ==================== 方式二：Playwright DOM 提取（基础版）====================

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
"""

async def fetch_via_dom(collection_id, max_items=0):
    """通过 Playwright DOM 提取收藏夹文章列表（基础版；条目过多时可能不完整）"""
    print(f"[DOM] 使用 Playwright DOM 方式获取收藏夹 {collection_id}")
    
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[DOM] 请先安装 playwright: pip install playwright && playwright install chromium")
        return []
    
    collection_url = f'https://www.zhihu.com/collection/{collection_id}'
    all_items = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1440, 'height': 900},
        )
        await context.add_init_script(STEALTH_SCRIPT)
        
        # 加载 cookie
        cookie_str = load_cookies()
        if cookie_str:
            cookies_dict = dict(item.split('=', 1) for item in cookie_str.split('; '))
            cookie_list = [{'name': n, 'value': v, 'domain': '.zhihu.com', 'path': '/'} for n, v in cookies_dict.items()]
            await context.add_cookies(cookie_list)
        
        page = await context.new_page()
        
        print(f"  访问: {collection_url}")
        await page.goto(collection_url, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)
        
        # 检查是否被重定向到验证页面
        if 'unhuman' in page.url:
            print("[DOM] 被检测为爬虫，需要重新登录")
            await browser.close()
            return []
        
        # 滚动加载所有内容
        print("  滚动加载...")
        last_count = 0
        no_new_count = 0
        while no_new_count < 5:
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await page.wait_for_timeout(1500)
            
            items = await page.query_selector_all('.ContentItem')
            current_count = len(items)
            
            if current_count == last_count:
                no_new_count += 1
            else:
                no_new_count = 0
                last_count = current_count
            
            if max_items and current_count >= max_items:
                break
        
        # 提取文章信息
        items = await page.query_selector_all('.ContentItem')
        print(f"  找到 {len(items)} 个内容项")
        
        for item in items[:max_items] if max_items else items:
            try:
                title_el = await item.query_selector('.ContentItem-title a')
                author_el = await item.query_selector('.AuthorInfo-name')
                
                title = await title_el.inner_text() if title_el else ''
                url = await title_el.get_attribute('href') if title_el else ''
                author = await author_el.inner_text() if author_el else ''
                
                if url:
                    if url.startswith('/'):
                        url = f'https://www.zhihu.com{url}'
                    all_items.append({
                        'url': url,
                        'title': title,
                        'author': author,
                        'voteup': 0,
                        'type': '',
                    })
            except Exception:
                continue
        
        await browser.close()
    
    print(f"[DOM] 完成，共获取 {len(all_items)} 篇文章")
    return all_items

# ==================== 主程序 ====================

def main():
    if len(sys.argv) < 2:
        print("用法: python fetch_zhihu_collection.py <收藏夹URL或ID> [最大数量]")
        print("示例: python fetch_zhihu_collection.py 31462407")
        print("      python fetch_zhihu_collection.py https://www.zhihu.com/collection/31462407")
        sys.exit(1)
    
    url_or_id = sys.argv[1]
    max_items = int(sys.argv[2]) if len(sys.argv) >= 3 else 0
    
    collection_id = extract_collection_id(url_or_id)
    if not collection_id:
        print("无法从输入中提取收藏夹 ID")
        sys.exit(1)
    
    print(f"收藏夹 ID: {collection_id}")
    if max_items:
        print(f"最大数量: {max_items}")
    print()
    
    # 方式一：尝试 API
    cookie_str = load_cookies()
    if cookie_str:
        items = fetch_via_api(collection_id, max_items, cookie_str)
        if items:
            # 保存结果
            output_file = os.path.join(WORKSPACE, f'zhihu_collection_{collection_id}.json')
            output = {
                'total': len(items),
                'items': items,
            }
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            print(f"\n已保存到: {output_file}")
            return
    
    # 方式二：降级到 Playwright DOM
    print("\n[API] 尝试失败，降级到 Playwright DOM 方式...")
    items = asyncio.run(fetch_via_dom(collection_id, max_items))
    
    if items:
        # 保存结果
        output_file = os.path.join(WORKSPACE, f'zhihu_collection_{collection_id}.json')
        output = {
            'total': len(items),
            'items': items,
        }
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\n已保存到: {output_file}")
    else:
        print("\n获取失败，请检查：")
        print("1. Cookie 是否有效（运行 zhihu_relogin.py 重新登录）")
        print("2. 收藏夹 URL 是否正确")
        print("3. 网络是否正常")

if __name__ == "__main__":
    main()
