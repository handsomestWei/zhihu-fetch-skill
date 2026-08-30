#!/usr/bin/env python3
"""统一入口：识别知乎链接并转到对应模块。

用法:
  python scripts/zhihu.py route <URL> [原命令参数...]
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")

from zhihu_fetch.core.url import classify_zhihu_url


def _run(modname, args):
    print(f"[路由] {modname} {' '.join(args)}")
    from zhihu import run_module

    run_module(modname, args)
    sys.exit(0)


def _rest():
    return [arg for arg in sys.argv[2:]]


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/zhihu.py route <知乎URL> [参数]")
        print("识别: /collection/ /columns /posts /answers /p/ 回答链接 /question/ 个人主页")
        sys.exit(1)

    raw = sys.argv[1]
    rest = _rest()
    flags = set(rest)
    target = classify_zhihu_url(raw)
    kind = target.kind

    if "--posts" in flags:
        kind = "posts"
    elif "--answers" in flags:
        kind = "answers"
    elif "--columns" in flags or "--column" in rest:
        kind = "columns"
    elif "--collections" in flags or "--collection" in rest:
        kind = "collections"
    elif "--history" in flags:
        kind = "history"
    elif "--kind" in rest:
        kind = "posts"

    print(f"[路由] kind={kind} slug={target.slug or '-'} url={target.url or raw}")

    if kind == "article":
        _run("zhihu_fetch.fetch.single", [target.url or raw, *rest])
    if kind == "answer":
        _run("zhihu_fetch.fetch.single", [target.url or raw, *rest])
    if kind == "collection":
        _run("zhihu_fetch.fetch.collection", [target.url or raw, *rest])
    if kind == "collections":
        _run("zhihu_fetch.fetch.collection", [target.people_url() or raw, *rest])
    if kind == "column":
        _run("zhihu_fetch.fetch.columns", [target.url or raw, *rest])
    if kind == "columns":
        _run("zhihu_fetch.fetch.columns", [target.people_url() or raw, *rest])
    if kind == "posts":
        extra = [] if "--kind" in rest else ["--kind", "articles"]
        _run("zhihu_fetch.fetch.posts", [target.people_url() or raw, *extra, *rest])
    if kind == "answers":
        extra = [] if "--kind" in rest else ["--kind", "answers"]
        _run("zhihu_fetch.fetch.posts", [target.people_url() or raw, *extra, *rest])
    if kind == "history":
        _run("zhihu_fetch.fetch.history", [target.people_url() or raw, *rest])
    if kind == "question":
        _run("zhihu_fetch.fetch.question", [target.url or raw, *rest])
    if kind == "people":
        _run("zhihu_fetch.fetch.follow", [target.people_url() or raw, *rest])

    print(f"无法识别链接: {raw}")
    sys.exit(1)


if __name__ == "__main__":
    main()
