#!/usr/bin/env python3
"""裸个人页默认「跟读包」：专栏 → 文章 → 回答（增量、去重、受上限）。

用法:
  python scripts/zhihu.py follow <个人主页>
  python scripts/zhihu.py route https://www.zhihu.com/people/<slug>
  --no-since-last  关闭默认增量
  单栏目仍用 --columns / --posts / --answers / --collections / --history
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")

from zhihu_fetch.fetch.collection import parse_people_slug
from zhihu_fetch.core.url import classify_zhihu_url

_VALUE_FLAGS = {
    "--kind",
    "--column",
    "--collection",
    "--max-items",
    "--max-answers",
    "--per-column",
    "--per-collection",
    "--max-collections",
    "--max-columns",
    "--min-voteup",
    "--days",
    "--since",
}


def _drop_flags(argv, flags):
    out = []
    skip_value = False
    for arg in argv:
        if skip_value:
            skip_value = False
            continue
        if arg in flags:
            if arg in _VALUE_FLAGS:
                skip_value = True
            continue
        out.append(arg)
    return out


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/zhihu.py follow <个人主页> [--no-since-last] [过滤参数...]")
        print("默认抓专栏 + 文章 + 回答；默认带 --since-last")
        sys.exit(1)

    raw = sys.argv[1]
    rest = list(sys.argv[2:])
    no_inc = "--no-since-last" in rest
    rest = [arg for arg in rest if arg != "--no-since-last"]
    if not no_inc and "--since-last" not in rest:
        rest = ["--since-last", *rest]

    target = classify_zhihu_url(raw)
    slug = target.slug or parse_people_slug(raw)
    if not slug:
        print("无法从输入中提取个人主页 slug")
        sys.exit(1)
    people = f"https://www.zhihu.com/people/{slug}"
    print(f"[跟读] {people}")
    print("[跟读] 专栏 → 文章 → 回答（默认增量；--no-since-last 关闭）")

    from zhihu import run_module

    col_args = _drop_flags(rest, {"--kind", "--max-answers"})
    run_module("zhihu_fetch.fetch.columns", [people, *col_args])
    post_args = _drop_flags(rest, {"--kind", "--column", "--max-columns", "--per-column"})
    run_module("zhihu_fetch.fetch.posts", [people, "--kind", "both", *post_args])


if __name__ == "__main__":
    main()
