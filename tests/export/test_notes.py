"""Offline tests: notes go to 知乎笔记, never rewrite 知乎收藏 mirrors."""

from pathlib import Path

from zhihu_fetch.export.classify import ZHIHU_MIRROR_ROOT, ZHIHU_NOTES_ROOT
from zhihu_fetch.export.notes import extract_quotes, extract_summary, write_notes


def test_extract_summary_and_quotes():
    body = "# 标题\n\n第一段摘要内容足够长。\n\n> 这是一句可抽出的金句内容\n\n第二段。"
    summary = extract_summary(body)
    assert "第一段" in summary
    quotes = extract_quotes(body)
    assert any("金句" in q for q in quotes)


def test_write_notes_sibling_root_keeps_mirror(tmp_path):
    vault = tmp_path / "vault"
    cat = vault / ZHIHU_MIRROR_ROOT / "编程与开发"
    cat.mkdir(parents=True)
    mirror = cat / "示例文章.md"
    mirror.write_text(
        """---
title: "示例文章"
author: "甲"
source: zhihu
url: "https://zhuanlan.zhihu.com/p/1"
category: "编程与开发"
---

# 示例文章

正文里有一段可当摘要的说明，用来生成笔记。

> 金句应当被单独列出在笔记里
""",
        encoding="utf-8",
    )
    original = mirror.read_text(encoding="utf-8")
    stats = write_notes(str(vault), force=False)
    assert stats["written"] == 1
    note = vault / ZHIHU_NOTES_ROOT / "编程与开发" / "示例文章.md"
    assert note.is_file()
    text = note.read_text(encoding="utf-8")
    assert "知乎收藏/编程与开发/示例文章" in text
    assert "[[知乎笔记/作者/甲" in text
    assert mirror.read_text(encoding="utf-8") == original
    assert not (vault / ZHIHU_MIRROR_ROOT / "编程与开发" / "示例文章.md").read_text(encoding="utf-8").startswith("# 示例文章\n\n## 摘要")

    stats2 = write_notes(str(vault), force=False)
    assert stats2["skipped"] == 1
    assert stats2["written"] == 0
