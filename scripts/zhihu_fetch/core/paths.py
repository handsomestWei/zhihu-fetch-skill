#!/usr/bin/env python3
"""Cookie、浏览器用户数据、默认输出目录的工作区解析。

优先级：
1. 环境变量 **ZHIHU_WORKSPACE**
2. 技能根目录下的 ``zhihu-fetch-workspace/``
"""

import os


def _find_skill_root():
    cur = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        if os.path.isfile(os.path.join(cur, "SKILL.md")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


SKILL_ROOT = _find_skill_root()
_DEFAULT_WORKSPACE = os.path.join(SKILL_ROOT, "zhihu-fetch-workspace")


def get_scripts_dir():
    return os.path.join(SKILL_ROOT, "scripts")


def get_workspace_dir():
    raw = (os.environ.get("ZHIHU_WORKSPACE") or "").strip()
    if raw:
        return os.path.abspath(os.path.expanduser(raw))
    return os.path.abspath(_DEFAULT_WORKSPACE)


def get_default_paths():
    workspace = get_workspace_dir()
    os.makedirs(workspace, exist_ok=True)
    return {
        "workspace": workspace,
        "cookie_file": os.path.join(workspace, "zhihu_cookies.json"),
        "user_data_dir": os.path.join(workspace, "chrome_user_data"),
    }
