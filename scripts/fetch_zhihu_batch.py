#!/usr/bin/env python3
"""
知乎收藏夹批量文章抓取（最终版）
功能：
1. Playwright 隐身模式抓取完整内容
2. 图片下载到本地
3. HTML 转 Markdown 格式优化
4. 断点续传支持
5. Cookie 文件认证

用法: python fetch_zhihu_batch.py <列表文件> [输出目录] [图片目录]
"""
import asyncio
import json
import re
import sys
import os
import urllib.request
import hashlib
import random

sys.stdout.reconfigure(encoding='utf-8')

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("请先安装 playwright: pip install playwright && playwright install chromium")
    sys.exit(1)

# Stealth 脚本 - 绕过检测
STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
"""

COOKIE_KEEPALIVE_INTERVAL_MIN = 5   # 最小刷新间隔（更频繁）
COOKIE_KEEPALIVE_INTERVAL_MAX = 8   # 最大刷新间隔
COOKIE_EXPIRE_WARN_SECONDS = 1800   # z_c0 过期前30分钟开始警告
MAX_RECOVERY_ATTEMPTS = 3           # Cookie失效最大恢复尝试次数
CONSECUTIVE_FAIL_THRESHOLD = 5      # 连续失败阈值
CONSECUTIVE_FAIL_INTERRUPT = True   # 连续失败是否中断

def get_default_paths():
    """获取默认路径"""
    workspace = os.environ.get('OPENCLAW_WORKSPACE',
                               os.path.join(os.path.expanduser('~'), '.openclaw', 'workspace'))
    return {
        'workspace': workspace,
        'cookie_file': os.path.join(workspace, 'zhihu_cookies.json'),
        'images_dir': None,  # 默认放到文章目录内
        'user_data_dir': os.path.join(workspace, 'chrome_user_data'),
    }

def save_cookies(cookies_dict):
    """保存 cookie 到文件"""
    cookie_file = get_default_paths()['cookie_file']
    with open(cookie_file, 'w', encoding='utf-8') as f:
        json.dump(cookies_dict, f, ensure_ascii=False, indent=2)

def load_cookies():
    """加载 cookie（支持两种格式：简单dict或扩展格式含expires）"""
    cookie_file = get_default_paths()['cookie_file']
    if not os.path.exists(cookie_file):
        return None
    try:
        with open(cookie_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # 判断格式：如果值是 dict 则是扩展格式，提取 value
        if not data:
            return None
        result = {}
        for k, v in data.items():
            if isinstance(v, dict):
                result[k] = v.get('value', '')
            else:
                result[k] = v
        return result
    except Exception:
        return None

def parse_z_c0_expiry(cookies_dict):
    """解析 z_c0 cookie 的过期时间（秒级时间戳）"""
    z_c0 = cookies_dict.get('z_c0', '')
    if not z_c0:
        return None
    try:
        # z_c0 格式通常是 base64 编码，内含时间戳
        # 尝试从 cookie 文件中读取 expires 字段
        cookie_file = get_default_paths()['cookie_file']
        with open(cookie_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # 如果是扩展格式（带 expires 字段）
        if isinstance(data, dict) and 'z_c0' in data:
            z_c0_data = data['z_c0']
            if isinstance(z_c0_data, dict) and 'expires' in z_c0_data:
                return z_c0_data['expires']
    except Exception:
        pass
    return None

def cookie_ttl_seconds(cookies_dict):
    """计算 cookie 剩余有效时间（秒）"""
    import time
    expiry = parse_z_c0_expiry(cookies_dict)
    if expiry:
        return max(0, expiry - time.time())
    return None  # 无法判断

async def save_browser_cookies(context):
    """从浏览器上下文提取并保存 cookie（扩展格式，含过期时间）"""
    cookie_file = get_default_paths()['cookie_file']
    try:
        cookies = await context.cookies()
        # 保存为扩展格式：{name: {value, expires, domain, path}}
        cookie_data = {}
        cookie_dict = {}
        for c in cookies:
            cookie_dict[c['name']] = c['value']
            cookie_data[c['name']] = {
                'value': c['value'],
                'expires': c.get('expires', -1),
                'domain': c.get('domain', ''),
                'path': c.get('path', '/'),
            }
        # 同时保存两种格式
        with open(cookie_file, 'w', encoding='utf-8') as f:
            json.dump(cookie_data, f, ensure_ascii=False, indent=2)
        return cookie_dict
    except Exception as e:
        print(f"  [!] 保存Cookie失败: {e}")
        return None

def download_image(url, save_dir):
    """下载图片到本地，返回文件名"""
    try:
        # 清理 URL
        url = url.split('?')[0] if '?' in url else url
        
        # 生成文件名
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        ext = '.jpg'
        if '.png' in url:
            ext = '.png'
        elif '.gif' in url:
            ext = '.gif'
        elif '.webp' in url:
            ext = '.webp'
        
        filename = f"{url_hash}{ext}"
        filepath = os.path.join(save_dir, filename)
        
        # 如果已下载过，直接返回
        if os.path.exists(filepath):
            return filename
        
        # 下载图片
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://zhuanlan.zhihu.com/',
        })
        
        with urllib.request.urlopen(req, timeout=10) as response:
            with open(filepath, 'wb') as f:
                f.write(response.read())
        
        return filename
    except Exception:
        return None

def html_to_markdown(html_content, images_dir=None):
    """将知乎文章 HTML 转换为干净的 Markdown"""
    if not html_content:
        return '', []
    
    import html as html_lib
    
    text = html_content
    downloaded_images = []
    image_sources = {}  # 保存图片原始链接
    
    # 1. 图片 - 下载到本地，保留原始链接
    def img_replace(m):
        tag = m.group(0)
        src_match = re.search(r'data-original="([^"]+)"', tag) or re.search(r'src="([^"]+)"', tag)
        alt_match = re.search(r'alt="([^"]*)"', tag)
        
        src = src_match.group(1) if src_match else ''
        alt = alt_match.group(1) if alt_match else ''
        
        if not src:
            return ''
        
        # 下载图片
        if images_dir:
            local_name = download_image(src, images_dir)
            if local_name:
                downloaded_images.append(local_name)
                image_sources[local_name] = src  # 保存原始链接
                # 返回本地路径 + 原始链接注释
                return f'\n\n![{alt}]({local_name})\n\n<!-- image_source: {src} -->\n\n'
        
        return f'\n\n![{alt}]({src})\n\n'
    
    text = re.sub(r'<img[^>]*>', img_replace, text)
    
    # 2. 标题 - 保留层级
    for i in range(6, 0, -1):
        def heading_replace(m, level=i):
            content = m.group(1).strip()
            content = re.sub(r'<[^>]+>', '', content)
            return f'\n\n{"#" * level} {content}\n\n'
        text = re.sub(rf'<h{i}[^>]*>(.*?)</h{i}>', heading_replace, text, flags=re.DOTALL)
    
    # 3. 段落
    def para_replace(m):
        content = m.group(1).strip()
        if not content:
            return ''
        return f'\n\n{content}\n\n'
    text = re.sub(r'<p[^>]*>(.*?)</p>', para_replace, text, flags=re.DOTALL)
    text = re.sub(r'<br\s*/?>', '\n', text)
    
    # 4. 加粗/斜体
    text = re.sub(r'<(?:b|strong)[^>]*>(.*?)</(?:b|strong)>', r'**\1**', text, flags=re.DOTALL)
    text = re.sub(r'<(?:i|em)[^>]*>(.*?)</(?:i|em)>', r'*\1*', text, flags=re.DOTALL)
    
    # 5. 代码块
    def code_block_replace(m):
        code = m.group(1)
        code = re.sub(r'<[^>]+>', '', code)
        code = html_lib.unescape(code)
        return f'\n\n```\n{code}\n```\n\n'
    text = re.sub(r'<pre[^>]*>\s*<code[^>]*>(.*?)</code>\s*</pre>', code_block_replace, text, flags=re.DOTALL)
    
    # 6. 行内代码
    def inline_code_replace(m):
        code = m.group(1)
        code = re.sub(r'<[^>]+>', '', code)
        code = html_lib.unescape(code)
        return f'`{code}`'
    text = re.sub(r'<code[^>]*>(.*?)</code>', inline_code_replace, text, flags=re.DOTALL)
    
    # 7. 链接
    def link_replace(m):
        href = m.group(1)
        content = m.group(2)
        content = re.sub(r'<[^>]+>', '', content)
        if href and content:
            return f'[{content}]({href})'
        return content or ''
    text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', link_replace, text, flags=re.DOTALL)
    
    # 8. 引用
    def quote_replace(m):
        content = m.group(1).strip()
        content = re.sub(r'<[^>]+>', '', content)
        lines = content.split('\n')
        quoted = '\n'.join(f'> {line}' for line in lines if line.strip())
        return f'\n\n{quoted}\n\n'
    text = re.sub(r'<blockquote[^>]*>(.*?)</blockquote>', quote_replace, text, flags=re.DOTALL)
    
    # 9. 列表
    def li_replace(m):
        content = m.group(1).strip()
        content = re.sub(r'<[^>]+>', '', content)
        return f'\n- {content}'
    text = re.sub(r'<li[^>]*>(.*?)</li>', li_replace, text, flags=re.DOTALL)
    text = re.sub(r'<ul[^>]*>(.*?)</ul>', r'\1\n', text, flags=re.DOTALL)
    text = re.sub(r'<ol[^>]*>(.*?)</ol>', r'\1\n', text, flags=re.DOTALL)
    
    # 10. 移除剩余 HTML（保留注释）
    # 先提取注释
    comments = re.findall(r'<!--.*?-->', text, re.DOTALL)
    # 移除所有 HTML 标签
    text = re.sub(r'<[^>]+>', '', text)
    # 恢复注释
    for comment in comments:
        text += '\n\n' + comment
    text = html_lib.unescape(text)
    
    # 清理空白
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    
    return text, downloaded_images, image_sources

def load_progress(progress_file):
    """加载进度（兼容旧格式）"""
    if os.path.exists(progress_file):
        try:
            with open(progress_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # 兼容旧格式：failed 可能是简单 URL 列表
            if 'failed' in data and data['failed']:
                if isinstance(data['failed'][0], str):
                    # 旧格式：转为新格式
                    data['failed'] = [{'url': u, 'reason': 'unknown'} for u in data['failed']]
            return data
        except Exception:
            pass
    return {'completed': [], 'failed': []}

def save_progress(progress_file, progress):
    """保存进度"""
    with open(progress_file, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)

def add_failure(progress, progress_file, url, reason, title='', index=0):
    """记录失败项到进度文件"""
    import time
    # 避免重复记录
    failed_urls = {f['url'] for f in progress.get('failed', [])}
    if url not in failed_urls:
        progress.setdefault('failed', []).append({
            'url': url,
            'reason': reason,
            'title': title[:100] if title else '',
            'index': index,
            'timestamp': int(time.time()),
        })
        save_progress(progress_file, progress)

async def main():
    # 解析参数
    if len(sys.argv) < 2:
        print("用法: python fetch_zhihu_batch.py <列表文件> [输出目录] [图片目录]")
        print("示例: python fetch_zhihu_batch.py zhihu_collection_123.json")
        sys.exit(1)
    
    list_file = sys.argv[1]
    paths = get_default_paths()
    
    # 输出目录
    if len(sys.argv) >= 3:
        output_dir = sys.argv[2]
    else:
        collection_id = os.path.splitext(os.path.basename(list_file))[0].replace('zhihu_collection_', '')
        output_dir = os.path.join(paths['workspace'], f'zhihu_articles_{collection_id}')
    
    # 图片目录
    images_dir = sys.argv[3] if len(sys.argv) >= 4 else os.path.join(output_dir, 'images')
    
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)
    
    # 加载列表
    with open(list_file, 'r', encoding='utf-8') as f:
        collection = json.load(f)
    
    items = collection.get('items', [])
    total = len(items)
    
    # 加载进度
    progress_file = os.path.join(output_dir, '_progress.json')
    progress = load_progress(progress_file)
    completed_urls = set(progress.get('completed', []))
    failed_urls = {f['url'] for f in progress.get('failed', [])}
    
    # --no-interrupt 模式：不因连续失败中断
    no_interrupt = '--no-interrupt' in sys.argv
    if no_interrupt:
        global CONSECUTIVE_FAIL_INTERRUPT
        CONSECUTIVE_FAIL_INTERRUPT = False
        print("[模式] 连续失败不中断")
    
    # --retry-failed 模式：只重试失败项
    retry_failed = '--retry-failed' in sys.argv
    if retry_failed:
        print("[模式] 重试失败项")
        # 清空 failed 列表，让脚本重新尝试
        progress['failed'] = []
        failed_urls = set()
        save_progress(progress_file, progress)
    
    print(f"总文章数: {total}")
    print(f"已完成: {len(completed_urls)}")
    print(f"已失败: {len(failed_urls)}")
    print(f"输出目录: {output_dir}")
    print(f"图片目录: {images_dir}")
    print()
    
    print("启动浏览器（持久化上下文）...")
    
    async with async_playwright() as p:
        # 使用持久化上下文（更稳定的登录状态）
        context = await p.chromium.launch_persistent_context(
            paths['user_data_dir'],
            headless=True,
            args=['--disable-blink-features=AutomationControlled'],
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1440, 'height': 900},
        )
        await context.add_init_script(STEALTH_SCRIPT)
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        # 注入 cookie 文件到浏览器上下文（解决持久化上下文不自动加载的问题）
        saved_cookies = load_cookies()
        if saved_cookies:
            cookie_list = []
            for name, value in saved_cookies.items():
                if isinstance(value, dict):
                    # 扩展格式
                    cookie_list.append({
                        'name': name,
                        'value': value.get('value', ''),
                        'domain': value.get('domain', '.zhihu.com'),
                        'path': value.get('path', '/'),
                    })
                else:
                    # 简单格式
                    cookie_list.append({
                        'name': name,
                        'value': value,
                        'domain': '.zhihu.com',
                        'path': '/',
                    })
            await context.add_cookies(cookie_list)
            print(f"已注入 {len(cookie_list)} 个 cookie 到浏览器")
        
        async def keepalive_cookie(aggressive=False):
            """刷新 cookie 保活 - 模拟真实用户行为
            
            Args:
                aggressive: 是否激进保活（访问文章页+更长停留）
            """
            try:
                if aggressive:
                    # 激进保活：访问随机文章，模拟阅读
                    # 从已完成的文章中随机选一篇访问
                    if completed_urls:
                        sample_url = random.choice(list(completed_urls))
                    else:
                        sample_url = 'https://zhuanlan.zhihu.com/p/6859032468'
                    await page.goto(sample_url, wait_until='domcontentloaded', timeout=20000)
                    # 模拟阅读行为：等待+滚动
                    await page.wait_for_timeout(random.uniform(2, 5))
                    await page.evaluate('window.scrollBy(0, 500)')
                    await page.wait_for_timeout(random.uniform(1, 3))
                    await page.evaluate('window.scrollBy(0, -200)')
                    await page.wait_for_timeout(random.uniform(0.5, 1.5))
                else:
                    # 常规保活：访问列表页
                    test_urls = [
                        'https://www.zhihu.com/hot',
                        'https://www.zhihu.com/follow',
                        'https://www.zhihu.com/explore',
                    ]
                    test_url = random.choice(test_urls)
                    await page.goto(test_url, wait_until='domcontentloaded', timeout=15000)
                    await page.wait_for_timeout(random.uniform(1, 3))
                    await page.evaluate('window.scrollBy(0, 300)')
                    await page.wait_for_timeout(random.uniform(0.5, 1.5))
                
                # 检查是否被重定向到验证页面或登录页
                if 'unhuman' not in page.url and '/signin' not in page.url:
                    # 保存最新 cookie 到文件
                    await save_browser_cookies(context)
                    return True
            except Exception:
                pass
            return False
        
        async def check_cookie_ttl():
            """主动检测 z_c0 cookie 的剩余有效期（秒）
            Returns: (ttl_seconds, is_expiring_soon)
            """
            try:
                cookies = await context.cookies()
                import time
                now = time.time()
                for c in cookies:
                    if c['name'] == 'z_c0':
                        expires = c.get('expires', -1)
                        if expires > 0:
                            ttl = expires - now
                            return (ttl, ttl < COOKIE_EXPIRE_WARN_SECONDS)
                        # expires <= 0 表示会话cookie，无法判断
                        return (None, False)
            except Exception:
                pass
            return (None, False)

        async def check_and_recover_cookie():
            """检查 cookie 状态，尝试自动恢复"""
            for attempt in range(MAX_RECOVERY_ATTEMPTS):
                print(f"  [恢复] 尝试 {attempt+1}/{MAX_RECOVERY_ATTEMPTS}...")
                # 先尝试激进保活
                if await keepalive_cookie(aggressive=True):
                    # 验证恢复是否成功
                    try:
                        await page.goto('https://www.zhihu.com', wait_until='domcontentloaded', timeout=15000)
                        await page.wait_for_timeout(2000)
                        if 'unhuman' not in page.url and '/signin' not in page.url:
                            print(f"  [恢复] ✅ Cookie 已恢复！")
                            return True
                    except Exception:
                        pass
                # 短暂等待后重试
                await asyncio.sleep(random.uniform(3, 8))
            return False
        
        # 启动时检查 cookie 是否有效
        print("检查 Cookie 有效性...")
        try:
            await page.goto('https://www.zhihu.com', wait_until='domcontentloaded', timeout=15000)
            await page.wait_for_timeout(3000)  # 增加等待时间
            
            current_url = page.url
            current_title = await page.title()
            print(f"  当前 URL: {current_url}")
            print(f"  当前标题: {current_title[:50]}")
            
            if 'unhuman' in current_url or '/signin' in current_url:
                print("[!] Cookie 已失效，尝试刷新...")
                refreshed = await keepalive_cookie()
                if not refreshed:
                    print("[FAIL] 需要重新登录")
                    print("运行: python zhihu_relogin.py")
                    await context.close()
                    return
                print("[OK] Cookie 已刷新")
            else:
                print("[OK] Cookie 有效")
        except Exception as e:
            print(f"[!] 检查 Cookie 时出错: {e}")
        
        success = 0
        fail = 0
        skip = 0
        consecutive_fails = 0           # 连续失败计数
        pending_failures = []           # 内存缓存的失败记录（未确定原因）
        next_keepalive = random.randint(COOKIE_KEEPALIVE_INTERVAL_MIN, COOKIE_KEEPALIVE_INTERVAL_MAX)
        
        def flush_pending_failures():
            """将缓存的失败记录写入进度文件（视为文章本身问题）"""
            if not pending_failures:
                return
            for pf in pending_failures:
                add_failure(progress, progress_file, pf['url'], pf['reason'], pf['title'], pf['index'])
            print(f"  [记录] {len(pending_failures)} 条失败写入进度文件")
            pending_failures.clear()

        def record_failure(url, reason, title, index):
            """记录失败：先缓存，检查连续失败阈值"""
            nonlocal consecutive_fails
            consecutive_fails += 1
            pending_failures.append({
                'url': url,
                'reason': reason,
                'title': title,
                'index': index,
            })
            
            if CONSECUTIVE_FAIL_INTERRUPT and consecutive_fails >= CONSECUTIVE_FAIL_THRESHOLD:
                print(f"  [!] 连续失败 {consecutive_fails} 次，达到阈值，中断抓取")
                print(f"  [!] 缓存的失败记录已丢弃（可能是登录/网络问题）")
                return True  # 需要中断
            return False

        def record_success():
            """成功时：重置连续失败计数，将缓存的失败记录写入文件"""
            nonlocal consecutive_fails
            if consecutive_fails > 0:
                consecutive_fails = 0
            if pending_failures:
                flush_pending_failures()

        for i, item in enumerate(items):
            url = item.get('url', '')
            title = item.get('title', f'文章{i+1}')
            
            # 跳过已完成
            if url in completed_urls:
                skip += 1
                continue
            
            # 主动检测 Cookie TTL（提前刷新）
            ttl, is_expiring = await check_cookie_ttl()
            if is_expiring:
                ttl_min = int(ttl / 60) if ttl else '?'
                print(f"  [TTL] ⚠️ Cookie 将在 {ttl_min} 分钟后过期，提前刷新...")
                await keepalive_cookie(aggressive=True)

            # 定时刷新 cookie（随机间隔）
            if (success + fail) >= next_keepalive:
                # 每3次常规保活做1次激进保活
                aggressive = (success + fail) % (COOKIE_KEEPALIVE_INTERVAL_MAX * 3) < COOKIE_KEEPALIVE_INTERVAL_MAX
                kind = "激进" if aggressive else "常规"
                print(f"  [刷新] {kind}保活 cookie...")
                await keepalive_cookie(aggressive=aggressive)
                next_keepalive = success + fail + random.randint(COOKIE_KEEPALIVE_INTERVAL_MIN, COOKIE_KEEPALIVE_INTERVAL_MAX)
            
            print(f"[{i+1}/{total}] {title[:60]}")
            
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_timeout(2000)
                
                # 检查是否被重定向到验证页面或登录页
                if 'unhuman' in page.url or '/signin' in page.url:
                    print(f"  [!] Cookie 失效，尝试自动恢复...")
                    recovered = await check_and_recover_cookie()
                    if recovered:
                        print(f"  [OK] Cookie 已恢复，继续抓取")
                        # 重新访问当前文章
                        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                        await page.wait_for_timeout(2000)
                        if 'unhuman' in page.url or '/signin' in page.url:
                            print(f"  [!] 恢复后仍无法访问，跳过")
                            should_stop = record_failure(url, 'recovery_failed', title, i+1)
                            fail += 1
                            if should_stop:
                                break
                            continue
                    else:
                        print(f"  [FAIL] 自动恢复失败，需要手动登录")
                        print(f"  运行: python zhihu_relogin.py")
                        record_failure(url, 'cookie_expired', title, i+1)
                        # 保存当前进度后再退出
                        save_progress(progress_file, progress)
                        break
                
                # 滚动页面加载所有内容
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(1000)
                
                # 提取内容
                article_data = await page.evaluate('''() => {
                    const selectors = [
                        '.Post-RichTextContainer',
                        '.RichText.ztext.Post-RichText',
                        '.RichText',
                        'article',
                    ];
                    
                    let contentEl = null;
                    for (const sel of selectors) {
                        contentEl = document.querySelector(sel);
                        if (contentEl) break;
                    }
                    
                    if (!contentEl) contentEl = document.body;
                    
                    const titleEl = document.querySelector('.Post-Title');
                    const title = titleEl ? titleEl.innerText.trim() : '';
                    
                    const authorEl = document.querySelector('.AuthorInfo-name') || document.querySelector('.UserLink-link');
                    const author = authorEl ? authorEl.innerText.trim() : '';
                    
                    const html = contentEl ? contentEl.innerHTML : '';
                    const text = contentEl ? contentEl.innerText : '';
                    
                    return { title, author, html, text };
                }''')
                
                html_content = article_data.get('html', '')
                text_content = article_data.get('text', '')
                
                if text_content and len(text_content) > 100:
                    # 转换为 Markdown 并下载图片
                    markdown, images, image_sources = html_to_markdown(html_content, images_dir)
                    
                    final_title = article_data.get('title', '') or title
                    if not final_title.strip():
                        final_title = f'文章{i+1}'
                    
                    # 清理文件名
                    safe_title = re.sub(r'[\\/:*?"<>|]', '_', final_title)[:80]
                    filename = f"{i+1:04d}_{safe_title}.md"
                    filepath = os.path.join(output_dir, filename)
                    
                    author = item.get('author', '') or article_data.get('author', '')
                    voteup = item.get('voteup', 0)
                    
                    # 构建图片源链接列表
                    img_sources_str = ''
                    if image_sources:
                        img_sources_list = [f'{k}: {v}' for k, v in image_sources.items()]
                        img_sources_str = '\n'.join(img_sources_list)
                    
                    # 写入文件
                    output = f"""---
title: "{final_title}"
author: "{author}"
source: zhihu
url: "{url}"
voteup: {voteup}
images: {len(images)}
---

# {final_title}

> 作者: {author} | 原文: [知乎链接]({url})

{markdown}
"""
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(output)
                    
                    # 单独保存图片源链接（可选）
                    if image_sources:
                        sources_file = os.path.join(output_dir, f"{i+1:04d}_{safe_title}_sources.txt")
                        with open(sources_file, 'w', encoding='utf-8') as f:
                            for local, original in image_sources.items():
                                f.write(f'{local} -> {original}\n')
                    
                    print(f"  [OK] {len(markdown)} 字, {len(images)} 张图片")
                    success += 1
                    record_success()
                    
                    # 更新进度
                    completed_urls.add(url)
                    progress['completed'] = list(completed_urls)
                    save_progress(progress_file, progress)
                else:
                    print(f"  [!] 内容为空或太短")
                    should_stop = record_failure(url, 'content_empty', title, i+1)
                    fail += 1
                    if should_stop:
                        break
                
                # 随机延迟 0-2 秒（微秒级精度）
                delay = random.uniform(0, 2)
                await asyncio.sleep(delay)
                
            except Exception as e:
                print(f"  [FAIL] {str(e)[:50]}")
                should_stop = record_failure(url, f'exception:{str(e)[:80]}', title, i+1)
                fail += 1
                if should_stop:
                    break
        
        # 结束前保存最新 cookie
        await save_browser_cookies(context)
        await context.close()
    
    print()
    print("=" * 60)
    print(f"完成! 成功: {success} | 失败: {fail} | 跳过: {skip}")
    print(f"总进度: {len(completed_urls)}/{total} ({len(completed_urls)*100//total}%)")
    failed_count = len(progress.get('failed', []))
    if failed_count:
        print(f"已记录失败: {failed_count} 条（可用 --retry-failed 重试）")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())

