#!/usr/bin/env python3
"""
知乎文章抓取 - API 直连方式
直接调用知乎 API，速度快，无需浏览器。
用法: python fetch_zhihu_api.py <文章URL或ID>
"""

import requests
import re
import sys
import json
import time


def extract_article_id(url_or_id):
    """从 URL 或直接 ID 中提取文章 ID"""
    match = re.search(r'/p/(\d+)', url_or_id)
    if match:
        return match.group(1)
    if url_or_id.isdigit():
        return url_or_id
    return url_or_id


def fetch_via_api(article_id, timeout=10):
    """通过知乎 API 获取文章内容"""
    api_url = f"https://zhuanlan.zhihu.com/api/articles/{article_id}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Referer': f'https://zhuanlan.zhihu.com/p/{article_id}',
    }

    response = requests.get(api_url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_via_page(url, timeout=15):
    """通过页面 HTML 中的 initialData 获取文章内容"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Upgrade-Insecure-Requests': '1',
    }

    session = requests.Session()
    response = session.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()

    # 从页面 script 中提取 initialData
    script_tags = re.findall(r'<script[^>]*>(.*?)</script>', response.text, re.DOTALL)
    for script in script_tags:
        if 'initialData' in script:
            start = script.find('{')
            end = script.rfind('}') + 1
            if start != -1 and end > start:
                data = json.loads(script[start:end])
                article = data.get('initialData', {}).get('data', {})
                if article:
                    return article
    return None


def html_to_text(html_content):
    """清理 HTML 标签，转为纯文本"""
    text = re.sub(r'<[^>]+>', ' ', html_content)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def format_output(title, author, publish_time, url, content):
    """统一输出格式"""
    parts = [
        f"标题: {title}",
        f"作者: {author}",
        f"发布时间: {publish_time}",
        f"原文链接: {url}",
        "",
        "=" * 50,
        "",
        content,
    ]
    return "\n".join(parts)


def main():
    if len(sys.argv) < 2:
        print("用法: python fetch_zhihu_api.py <文章URL或ID>")
        print("示例: python fetch_zhihu_api.py https://zhuanlan.zhihu.com/p/2015027745743189513")
        sys.exit(1)

    url_or_id = sys.argv[1]
    article_id = extract_article_id(url_or_id)
    full_url = f"https://zhuanlan.zhihu.com/p/{article_id}"

    print(f"正在获取文章 {article_id} ...")

    # 方式1: API 直连
    try:
        print("尝试 API 直连...")
        data = fetch_via_api(article_id)
        title = data.get('title', '未知标题')
        author = data.get('author', {}).get('name', '未知作者')
        publish_time = str(data.get('created', '未知时间'))
        content_html = data.get('content', '')
        content = html_to_text(content_html) if content_html else '无法获取内容'

        output = format_output(title, author, publish_time, full_url, content)
        print(output)

        # 保存到文件
        output_file = f"zhihu_{article_id}.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"\n已保存到 {output_file}")
        return

    except Exception as e:
        print(f"API 直连失败: {e}")

    # 方式2: 从页面提取
    try:
        print("尝试从页面提取...")
        time.sleep(2)
        article = fetch_via_page(full_url)
        if article:
            title = article.get('title', '未知标题')
            author = article.get('author', {}).get('name', '未知作者')
            content_html = article.get('content', '')
            content = html_to_text(content_html) if content_html else '无法获取内容'

            output = format_output(title, author, '未知时间', full_url, content)
            print(output)

            output_file = f"zhihu_{article_id}.txt"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"\n已保存到 {output_file}")
            return

    except Exception as e:
        print(f"页面提取失败: {e}")

    print("所有方式均失败，请尝试 Playwright 方式")


if __name__ == "__main__":
    main()
