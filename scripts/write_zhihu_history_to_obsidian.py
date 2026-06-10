#!/usr/bin/env python3
"""
Import fetched Zhihu history notes into an Obsidian all-history folder.

Usage:
  python write_zhihu_history_to_obsidian.py <article-dir> <vault-path> [folder-name]

Use "." or omit folder-name to write under the Zhihu root category folders:
  {Vault}/知乎收藏/{category}/...

分类逻辑见 obsidian_classify.py（与 write_to_obsidian 共用）。
"""

import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from obsidian_classify import (
    analyze_content_categories,
    classify_article,
    detect_existing_categories,
)


def parse_frontmatter(path):
    content = Path(path).read_text(encoding="utf-8")
    if not content.startswith("---"):
        return {}, content
    end = content.find("---", 3)
    if end < 0:
        return {}, content
    raw = content[3:end].strip()
    body = content[end + 3 :].strip()
    meta = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        try:
            meta[key.strip()] = json.loads(value)
        except Exception:
            meta[key.strip()] = value.strip('"')
    return meta, body


def yaml_scalar(value):
    if value is None:
        return '""'
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def format_tags(category, interaction_action=None):
    """Build a YAML-safe tags line for Obsidian frontmatter."""
    tags = ["zhihu"]
    if category:
        tags.append(str(category).strip())
    action = (interaction_action or "").strip()
    if action:
        tags.append(action)
    return f"tags: {json.dumps(tags, ensure_ascii=False)}"


def safe_filename(text):
    text = re.sub(r'[\\/:*?"<>|]', "_", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:90] or "untitled"


def sortable_stamp(value, fallback_index):
    if not value:
        return f"unknown_{fallback_index:04d}"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.strftime("%Y%m%d_%H%M%S")
    except Exception:
        return re.sub(r"[^0-9A-Za-z]+", "_", str(value)).strip("_")[:32]


def interaction_date(value):
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.date().isoformat()
    except Exception:
        return ""


def rewrite_image_links(body, note_dir, zhihu_dir):
    image_dir = zhihu_dir / "images"

    def replace(match):
        alt = match.group(1)
        target = match.group(2)
        if re.match(r"https?://", target):
            return match.group(0)
        relative = os.path.relpath(image_dir / Path(target).name, note_dir)
        relative = Path(relative).as_posix()
        return f"![{alt}]({relative})"

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", replace, body)


def sync_images(source_dir, vault_zhihu_dir):
    source_images = Path(source_dir) / "images"
    if not source_images.exists():
        return 0
    target_images = Path(vault_zhihu_dir) / "images"
    target_images.mkdir(parents=True, exist_ok=True)
    copied = 0
    for src in source_images.iterdir():
        if not src.is_file():
            continue
        dst = target_images / src.name
        if not dst.exists():
            shutil.copy2(src, dst)
            copied += 1
    return copied


def build_url_index(history_dir):
    """Map existing note source URLs to note paths for repeat-safe imports."""
    index = {}
    if not history_dir.exists():
        return index
    for path in history_dir.rglob("*.md"):
        meta, _ = parse_frontmatter(path)
        url = meta.get("url")
        if url and url not in index:
            index[url] = path
    return index


def unique_path(path):
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for i in range(2, 1000):
        candidate = path.with_name(f"{stem}_{i}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Unable to find unique filename for {path}")


def resolve_history_root(zhihu_dir, folder_name):
    if folder_name in ("", ".", "root", "知乎收藏"):
        return zhihu_dir
    return zhihu_dir / folder_name


def main():
    if len(sys.argv) < 3:
        print("用法: python write_zhihu_history_to_obsidian.py <article-dir> <vault-path> [folder-name]")
        sys.exit(1)

    source_dir = Path(sys.argv[1]).expanduser().resolve()
    vault_path = Path(sys.argv[2]).expanduser().resolve()
    folder_name = sys.argv[3] if len(sys.argv) >= 4 else "."

    if not source_dir.exists():
        print(f"article dir not found: {source_dir}")
        sys.exit(1)
    if not vault_path.exists():
        print(f"vault path not found: {vault_path}")
        sys.exit(1)

    zhihu_dir = vault_path / "知乎收藏"
    history_dir = resolve_history_root(zhihu_dir, folder_name)
    history_dir.mkdir(parents=True, exist_ok=True)
    url_index = build_url_index(history_dir)

    md_files = sorted(p for p in source_dir.iterdir() if p.suffix == ".md" and not p.name.startswith("_"))
    existing = detect_existing_categories(str(vault_path))
    existing_keywords, template_rules = analyze_content_categories(
        [str(p) for p in md_files], existing
    )
    print(f"已有知乎分类: {list(existing['zhihu'].keys()) or '无'}")

    written = 0
    updated = 0
    skipped = 0
    for index, path in enumerate(md_files, 1):
        try:
            meta, body = parse_frontmatter(path)
            title = meta.get("title") or path.stem
            url = meta.get("url")
            category = meta.get("category") or classify_article(
                title, body[:500], existing_keywords, template_rules
            )
            filename = f"{safe_filename(title)}.md"
            dest_dir = history_dir / category
            dest_dir.mkdir(parents=True, exist_ok=True)
            existing_dest = url_index.get(url) if url else None
            if existing_dest:
                dest = existing_dest
                if dest.parent != dest_dir:
                    candidate = unique_path(dest_dir / filename)
                    dest.rename(candidate)
                    dest = candidate
                    url_index[url] = dest
            else:
                dest = unique_path(dest_dir / filename)

            ordered_keys = [
                "title",
                "author",
                "source",
                "url",
                "type",
                "category",
                "interaction_action",
                "interaction_time",
                "interaction_date",
                "activity_id",
                "voteup",
                "images",
            ]
            meta["category"] = category
            meta["interaction_date"] = interaction_date(meta.get("interaction_time"))
            frontmatter = []
            for key in ordered_keys:
                if key in meta and meta.get(key) not in (None, ""):
                    frontmatter.append(f"{key}: {yaml_scalar(meta.get(key))}")
            frontmatter.append(f"imported: {datetime.now().strftime('%Y-%m-%d')}")
            frontmatter.append(
                format_tags(category, meta.get("interaction_action"))
            )

            output = (
                "---\n"
                + "\n".join(frontmatter)
                + "\n---\n\n"
                + rewrite_image_links(body, dest_dir, zhihu_dir).strip()
                + "\n"
            )
            dest.write_text(output, encoding="utf-8")
            if existing_dest:
                updated += 1
            else:
                written += 1
                if url:
                    url_index[url] = dest
        except Exception as exc:
            skipped += 1
            print(f"  [!] 跳过 {path.name}: {exc}")

    copied_images = sync_images(source_dir, zhihu_dir)
    print(f"source: {source_dir}")
    print(f"destination: {history_dir}")
    print(f"written: {written}")
    print(f"updated: {updated}")
    print(f"skipped: {skipped}")
    print(f"new_images_copied: {copied_images}")


if __name__ == "__main__":
    main()
