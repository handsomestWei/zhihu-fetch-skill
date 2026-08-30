#!/usr/bin/env python3
"""从 Vault 里的「知乎收藏」原文镜像生成并列根目录「知乎笔记」。

不改写、不删除镜像。已有笔记默认跳过（--force 覆盖）。

用法:
  python scripts/zhihu.py notes [Vault路径]
  python scripts/zhihu.py notes --force
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from zhihu_fetch.export.classify import ZHIHU_MIRROR_ROOT, ZHIHU_NOTES_ROOT, ZHIHU_RESERVED_DIRS
from zhihu_fetch.export.obsidian import detect_obsidian_vault, parse_article_metadata

_QUOTE_RE = re.compile(r"^>\s+(.+)$", re.M)
_GUILLEMET_RE = re.compile(r"「([^」]{8,80})」")
_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_HEADING_RE = re.compile(r"^#+\s+.*$", re.M)


def _safe_name(text):
    return re.sub(r'[\\/:*?"<>|]', "_", (text or "").strip())[:80] or "untitled"


def extract_summary(body, limit=400):
    text = _IMG_RE.sub("", body or "")
    text = _HEADING_RE.sub("", text)
    paras = []
    for block in re.split(r"\n\s*\n", text):
        line = block.strip()
        if not line or line.startswith(">"):
            continue
        line = re.sub(r"\s+", " ", line)
        if line.startswith("作者:") or line.startswith("作者："):
            continue
        paras.append(line)
        if len(" ".join(paras)) >= limit:
            break
    summary = " ".join(paras).strip()
    if len(summary) > limit:
        summary = summary[: limit - 1] + "…"
    return summary


def extract_quotes(body, limit=8):
    seen = []
    for match in _QUOTE_RE.findall(body or ""):
        text = re.sub(r"\s+", " ", match).strip().strip('"“”')
        if 8 <= len(text) <= 120 and text not in seen:
            seen.append(text)
        if len(seen) >= limit:
            return seen
    for match in _GUILLEMET_RE.findall(body or ""):
        text = match.strip()
        if text not in seen:
            seen.append(text)
        if len(seen) >= limit:
            break
    return seen


def is_answer_url(url):
    return "/answer/" in (url or "")


def iter_mirror_notes(vault_path):
    mirror = os.path.join(vault_path, ZHIHU_MIRROR_ROOT)
    if not os.path.isdir(mirror):
        return
    for root, dirs, files in os.walk(mirror):
        dirs[:] = [d for d in dirs if d not in ZHIHU_RESERVED_DIRS and not d.startswith(".")]
        rel = os.path.relpath(root, mirror)
        category = rel.split(os.sep)[0] if rel not in {".", ""} else "未分类"
        if category in ZHIHU_RESERVED_DIRS:
            continue
        for name in files:
            if not name.endswith(".md") or name.startswith("_") or name == "抓取失败.md":
                continue
            yield category, os.path.join(root, name)


def note_body(meta, category, filename):
    title = meta.get("title") or os.path.splitext(filename)[0]
    author = meta.get("author") or ""
    url = meta.get("url") or ""
    body = meta.get("body") or ""
    summary = extract_summary(body)
    quotes = extract_quotes(body)
    stem = os.path.splitext(filename)[0]
    mirror_link = f"[[{ZHIHU_MIRROR_ROOT}/{category}/{stem}]]"
    author_link = f"[[{ZHIHU_NOTES_ROOT}/作者/{_safe_name(author)}|{author}]]" if author else ""
    question_link = ""
    if is_answer_url(url) and title:
        question_link = f"[[{ZHIHU_NOTES_ROOT}/问题/{_safe_name(title)}|{title}]]"

    quote_md = "\n".join(f"> {q}" for q in quotes) if quotes else "_（正文未抽出金句）_"
    lines = [
        "---",
        f'title: "{title}"',
        f'author: "{author}"',
        "source: zhihu-note",
        f'url: "{url}"',
        f'category: "{category}"',
        f'mirror: "{ZHIHU_MIRROR_ROOT}/{category}/{stem}"',
        "---",
        "",
        f"# {title}",
        "",
        f"- 原文镜像: {mirror_link}",
        f"- 作者: {author_link or author or '未知'}",
    ]
    if question_link:
        lines.append(f"- 问题: {question_link}")
    if url:
        lines.append(f"- 知乎: {url}")
    lines.extend(
        [
            "",
            "## 摘要",
            "",
            summary or "_（未能从原文抽出摘要）_",
            "",
            "## 金句",
            "",
            quote_md,
            "",
            "## 待补充",
            "",
            "_（Agent 或人工可在此继续写）_",
            "",
        ]
    )
    return "\n".join(lines), title, author


def _append_index(path, heading, link_line):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        text = open(path, encoding="utf-8").read()
        if link_line in text:
            return
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"- {link_line}\n")
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {heading}\n\n- {link_line}\n")


def write_notes(vault_path, force=False):
    notes_root = os.path.join(vault_path, ZHIHU_NOTES_ROOT)
    os.makedirs(notes_root, exist_ok=True)
    stats = {"total": 0, "written": 0, "skipped": 0, "missing": 0}
    for category, src in iter_mirror_notes(vault_path):
        stats["total"] += 1
        meta = parse_article_metadata(src)
        if not (meta.get("body") or "").strip():
            stats["missing"] += 1
            continue
        filename = os.path.basename(src)
        dest_dir = os.path.join(notes_root, category)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, filename)
        if os.path.exists(dest) and not force:
            stats["skipped"] += 1
            continue
        content, title, author = note_body(meta, category, filename)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(content)
        stats["written"] += 1
        note_link = f"[[{ZHIHU_NOTES_ROOT}/{category}/{os.path.splitext(filename)[0]}|{title}]]"
        if author:
            _append_index(
                os.path.join(notes_root, "作者", f"{_safe_name(author)}.md"),
                author,
                note_link,
            )
        url = meta.get("url") or ""
        if is_answer_url(url) and title:
            _append_index(
                os.path.join(notes_root, "问题", f"{_safe_name(title)}.md"),
                title,
                note_link,
            )
        print(f"  [OK] [{category}] {title[:40]}")
    return stats


def main():
    argv = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv
    if argv and argv[0] not in {"-h", "--help"}:
        vault_path = str(Path(argv[0]).expanduser().resolve())
    else:
        print("正在检测本地 Obsidian Vault...")
        candidates = detect_obsidian_vault()
        if not candidates:
            print("未检测到 Obsidian Vault，请手动指定路径")
            sys.exit(1)
        vault_path = candidates[0]
        print(f"检测到 Vault: {vault_path}")

    if not os.path.isdir(vault_path):
        print(f"Vault 路径不存在: {vault_path}")
        sys.exit(1)

    mirror = os.path.join(vault_path, ZHIHU_MIRROR_ROOT)
    if not os.path.isdir(mirror):
        print(f"未找到原文镜像目录: {mirror}")
        print("请先 python scripts/zhihu.py obsidian 把原文写入「知乎收藏」")
        sys.exit(1)

    print(f"原文镜像: {mirror}")
    print(f"笔记目录: {os.path.join(vault_path, ZHIHU_NOTES_ROOT)}（与镜像并列，不覆盖原文）")
    if force:
        print("[模式] --force 覆盖已有笔记")
    stats = write_notes(vault_path, force=force)
    print()
    print(f"镜像 {stats['total']} 篇，写入笔记 {stats['written']}，已有跳过 {stats['skipped']}，空文 {stats['missing']}")


if __name__ == "__main__":
    main()
