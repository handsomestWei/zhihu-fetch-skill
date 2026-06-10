#!/usr/bin/env python3
"""
知乎文章写入 Obsidian 知识库
自动检测 Obsidian Vault 路径，根据内容智能分类，结合已有目录结构。

用法:
  python write_to_obsidian.py <文章目录> [Obsidian Vault 路径]

Vault 解析优先级（从高到低）:
  1. 命令行第二个参数
  2. 环境变量 OBSIDIAN_VAULT（单个 Vault 根路径；也可用 ZHIHU_OBSIDIAN_VAULT 作为别名）
  3. 常见目录扫描（多个命中时可交互选择）
"""

import os
import re
import sys
import hashlib
import subprocess
from datetime import datetime
from pathlib import Path

from obsidian_classify import (
    analyze_content_categories,
    classify_article,
    detect_existing_categories,
)


def env_vault_candidate_paths():
    """
    从环境变量读取 Vault 候选路径。
    OBSIDIAN_VAULT 为主；ZHIHU_OBSIDIAN_VAULT 为别名。多个路径用 os.pathsep 分隔（少见）。
    """
    keys = ("OBSIDIAN_VAULT", "ZHIHU_OBSIDIAN_VAULT")
    ordered = []
    seen = set()
    for key in keys:
        raw = os.environ.get(key, "").strip()
        if not raw:
            continue
        for part in raw.split(os.pathsep):
            part = part.strip().strip('"').strip("'")
            if not part:
                continue
            p = Path(part).expanduser()
            try:
                rp = p.resolve()
            except Exception:
                rp = p
            key_str = str(rp)
            if key_str in seen:
                continue
            seen.add(key_str)
            ordered.append(rp)
    return ordered


def detect_obsidian_vault():
    """
    自动检测本地 Obsidian Vault 路径。
    检测策略：
    1. 环境变量 OBSIDIAN_VAULT（及别名 ZHIHU_OBSIDIAN_VAULT）
    2. 常见路径扫描（用户目录与各盘符常见目录）
    """
    candidates = []

    env_paths = env_vault_candidate_paths()
    env_resolved_existing = set()
    for p in env_paths:
        if p.exists():
            env_resolved_existing.add(str(p.resolve()))

    common_paths = []
    common_paths.extend(env_paths)

    home = Path.home()
    common_paths.extend([
        home / "Documents" / "Obsidian Vault",
        home / "Documents" / "Obsidian",
        home / "Obsidian Vault",
        home / "Obsidian",
        home / "MyVault",
        home / "vault",
    ])

    for drive in ["C:", "D:", "E:"]:
        common_paths.append(Path(f"{drive}/Obsidian Vault"))
        common_paths.append(Path(f"{drive}/vault"))
        common_paths.append(Path(f"{drive}/Documents/Obsidian Vault"))

    seen_paths = set()
    uniq = []
    for p in common_paths:
        try:
            k = str(p.resolve())
        except Exception:
            k = str(p)
        if k not in seen_paths:
            seen_paths.add(k)
            uniq.append(p)

    for p in uniq:
        if not p.exists():
            continue
        rs = str(p.resolve())
        has_obsidian_meta = (p / ".obsidian").exists()
        # 显式配置的路径：即使暂未生成 .obsidian 也纳入（少见）；其余须有 .obsidian
        if has_obsidian_meta or rs in env_resolved_existing:
            candidates.append(rs)

    # 去重并返回
    candidates = list(dict.fromkeys(candidates))
    return candidates


def parse_article_metadata(filepath):
    """解析文章的 frontmatter"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    meta = {}
    if content.startswith('---'):
        end = content.find('---', 3)
        if end > 0:
            frontmatter = content[3:end].strip()
            for line in frontmatter.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    meta[key.strip()] = value.strip().strip('"')
            meta['body'] = content[end+3:].strip()
    else:
        meta['body'] = content

    return meta


def clean_content_for_obsidian(content):
    """清理内容使其适合 Obsidian"""
    # 更新图片路径：![](filename.jpg) -> ![](images/filename.jpg)
    content = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'![\1](images/\2)', content)
    
    content = re.sub(r'<img[^>]*>', '[图片]', content)
    content = re.sub(r'<video[^>]*>', '[视频]', content)
    content = re.sub(r'<iframe[^>]*>', '[嵌入内容]', content)
    return content


def sync_images(source_dir, vault_path):
    """同步图片到 Obsidian Vault"""
    # 查找图片目录
    source_images_dir = os.path.join(source_dir, 'images')
    if not os.path.exists(source_images_dir):
        # 尝试其他可能的路径
        source_images_dir = os.path.join(os.path.dirname(source_dir), 'zhihu_images')
    
    if not os.path.exists(source_images_dir):
        print("  [!] 未找到图片目录，跳过图片同步")
        return 0
    
    # 目标图片目录
    obsidian_images_dir = os.path.join(vault_path, '知乎收藏', 'images')
    os.makedirs(obsidian_images_dir, exist_ok=True)
    
    # 复制图片
    images = os.listdir(source_images_dir)
    copied = 0
    
    for img in images:
        src = os.path.join(source_images_dir, img)
        dst = os.path.join(obsidian_images_dir, img)
        
        if not os.path.exists(dst):
            try:
                import shutil
                shutil.move(src, dst)
                copied += 1
            except Exception:
                pass
    
    print(f"  [OK] 同步 {copied} 张图片到 Obsidian")
    return copied


def write_to_obsidian(article_files, vault_path, source_dir):
    """将文章写入 Obsidian Vault"""
    zhihu_dir = os.path.join(vault_path, '知乎收藏')
    os.makedirs(zhihu_dir, exist_ok=True)

    # 检测已有分类
    existing = detect_existing_categories(vault_path)
    print(f"\n已有知乎分类: {list(existing['zhihu'].keys()) or '无'}")
    print(f"Vault 一级目录: {list(existing['vault'].keys())[:10]}")

    # 分析内容生成分类规则
    existing_keywords, template_rules = analyze_content_categories(article_files, existing)

    stats = {'total': 0, 'success': 0, 'skip': 0, 'categories': {}}

    for filepath in article_files:
        stats['total'] += 1

        try:
            meta = parse_article_metadata(filepath)
            title = meta.get('title', os.path.basename(filepath))
            author = meta.get('author', '')
            url = meta.get('url', '')
            body = meta.get('body', '')

            if not body:
                print(f"  [!] 空内容，跳过: {title}")
                stats['skip'] += 1
                continue

            # 智能分类
            category = classify_article(title, body[:500], existing_keywords, template_rules)

            # 分类目录
            cat_dir = os.path.join(zhihu_dir, category)
            os.makedirs(cat_dir, exist_ok=True)

            # 生成 Obsidian 兼容的 Markdown
            obsidian_content = f"""---
title: "{title}"
author: "{author}"
source: zhihu
url: "{url}"
category: "{category}"
imported: {datetime.now().strftime('%Y-%m-%d')}
tags: [zhihu, {category}]
---

# {title}

> 作者: {author} | [原文链接]({url}) | 分类: {category}

{clean_content_for_obsidian(body)}
"""

            # 文件名
            safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)[:80]
            filename = f"{safe_title}.md"
            dest_path = os.path.join(cat_dir, filename)

            # 避免覆盖
            if os.path.exists(dest_path):
                file_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                filename = f"{safe_title}_{file_hash}.md"
                dest_path = os.path.join(cat_dir, filename)

            with open(dest_path, 'w', encoding='utf-8') as f:
                f.write(obsidian_content)

            # 删除源文件（剪切模式）
            try:
                os.remove(filepath)
            except Exception:
                pass

            stats['success'] += 1
            stats['categories'][category] = stats['categories'].get(category, 0) + 1
            print(f"  [OK] [{category}] {title[:40]}")

        except Exception as e:
            print(f"  [FAIL] 错误: {e}")
            stats['skip'] += 1

    return stats


def main():
    if len(sys.argv) < 2:
        print("用法: python write_to_obsidian.py <文章目录> [Obsidian Vault 路径]")
        print("")
        print("参数:")
        print("  文章目录       - fetch_zhihu_batch.py 输出的目录")
        print("  Obsidian Vault - Vault 根目录（可选；亦可设置环境变量见下）")
        print("")
        print("Vault 优先级: 命令行第 2 参数 > 环境变量 OBSIDIAN_VAULT > 常见目录扫描")
        print("")
        print("示例:")
        print("  python write_to_obsidian.py zhihu_articles_314624076")
        print("  python write_to_obsidian.py zhihu_articles_314624076 \"D:\\\\My Vault\"")
        print("  # Windows PowerShell 示例：")
        print('  $env:OBSIDIAN_VAULT="D:\\\\Notes\\\\MyVault"; python write_to_obsidian.py .\\\\zhihu_articles_xxx')
        sys.exit(1)

    source_dir = sys.argv[1]

    if not os.path.exists(source_dir):
        print(f"文章目录不存在: {source_dir}")
        sys.exit(1)

    # Vault 路径：命令行 > 环境变量（在 detect_obsidian_vault 内合并）> 自动扫描
    if len(sys.argv) > 2:
        vault_path = str(Path(sys.argv[2]).expanduser().resolve())
    else:
        print("正在检测本地 Obsidian Vault...")
        candidates = detect_obsidian_vault()
        if not candidates:
            print("未检测到 Obsidian Vault，请手动指定路径")
            sys.exit(1)
        if len(candidates) == 1:
            vault_path = candidates[0]
            print(f"检测到 Vault: {vault_path}")
        else:
            print(f"检测到多个 Vault:")
            for i, c in enumerate(candidates):
                print(f"  [{i+1}] {c}")
            choice = input("请选择编号 (默认 1): ").strip() or '1'
            vault_path = candidates[int(choice) - 1]
            print(f"已选择: {vault_path}")

    if not os.path.exists(vault_path):
        print(f"Vault 路径不存在: {vault_path}")
        sys.exit(1)

    # 收集文章文件
    article_files = []
    for f in sorted(os.listdir(source_dir)):
        if f.endswith('.md') and not f.startswith('_'):
            article_files.append(os.path.join(source_dir, f))

    if not article_files:
        print("没有找到文章文件")
        sys.exit(1)

    print(f"\n找到 {len(article_files)} 篇文章")
    print(f"目标 Vault: {vault_path}")
    print("=" * 60)

    stats = write_to_obsidian(article_files, vault_path, source_dir)
    
    # 同步图片
    print("\n同步图片...")
    sync_images(source_dir, vault_path)

    print("\n" + "=" * 60)
    print("写入完成！")
    print(f"  总计: {stats['total']}")
    print(f"  成功: {stats['success']}")
    print(f"  跳过: {stats['skip']}")
    print(f"\n分类统计:")
    for cat, count in sorted(stats['categories'].items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count} 篇")
    print("=" * 60)


if __name__ == "__main__":
    main()




