#!/usr/bin/env python3
"""知乎抓取统一命令入口。

用法（在技能根目录）:
  python scripts/zhihu.py <命令> [参数...]
  python scripts/zhihu.py route <知乎URL>
"""
from __future__ import annotations

import asyncio
import importlib
import inspect
import os
import sys

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

COMMANDS = {
    "route": "zhihu_fetch.fetch.route",
    "collection": "zhihu_fetch.fetch.collection",
    "columns": "zhihu_fetch.fetch.columns",
    "posts": "zhihu_fetch.fetch.posts",
    "follow": "zhihu_fetch.fetch.follow",
    "question": "zhihu_fetch.fetch.question",
    "history": "zhihu_fetch.fetch.history",
    "batch": "zhihu_fetch.fetch.batch",
    "fetch": "zhihu_fetch.fetch.single",
    "api": "zhihu_fetch.body.api",
    "stealth": "zhihu_fetch.body.stealth",
    "interactive": "zhihu_fetch.body.interactive",
    "login": "zhihu_fetch.auth.login",
    "relogin": "zhihu_fetch.auth.relogin",
    "login-save": "zhihu_fetch.auth.login_save",
    "obsidian": "zhihu_fetch.export.obsidian",
    "notes": "zhihu_fetch.export.notes",
    "history-obsidian": "zhihu_fetch.export.history",
    "failures": "zhihu_fetch.export.failures",
    "limits": "zhihu_fetch.core.limits",
}

ALIASES = {
    "single": "fetch",
    "re-login": "relogin",
    "write-obsidian": "obsidian",
    "write-history": "history-obsidian",
    "write-failures": "failures",
}


def _print_help():
    print("用法: python scripts/zhihu.py <命令> [参数...]")
    print("命令:")
    print("  route              识别链接并转到对应流水线")
    print("  collection         收藏夹列表")
    print("  columns            用户专栏")
    print("  posts              个人文章 / 回答")
    print("  follow             裸主页跟读包（专栏+文章+回答）")
    print("  question           问题页高赞回答列表")
    print("  history            点赞/收藏动态")
    print("  batch              批量正文与图片")
    print("  fetch              单篇文章/回答")
    print("  api / stealth / interactive   单篇调试")
    print("  login / relogin / login-save  登录")
    print("  obsidian           原文镜像写入 Vault/知乎收藏")
    print("  notes              从知乎收藏生成并列的知乎笔记")
    print("  history-obsidian / failures")
    print("  limits             查看或固化抓取上限")


def run_module(modname, argv):
    module = importlib.import_module(modname)
    entry = getattr(module, "cli", None) or getattr(module, "main")
    old = sys.argv
    sys.argv = [modname, *argv]
    try:
        result = entry()
        if inspect.iscoroutine(result):
            asyncio.run(result)
    finally:
        sys.argv = old


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help", "help"}:
        _print_help()
        sys.exit(0 if argv else 1)
    name = ALIASES.get(argv[0], argv[0])
    modname = COMMANDS.get(name)
    if not modname:
        print(f"未知命令: {argv[0]}")
        _print_help()
        sys.exit(1)
    run_module(modname, argv[1:])


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
