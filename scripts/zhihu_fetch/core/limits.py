#!/usr/bin/env python3
"""Crawl-limit defaults: config files first, then these fallbacks.

Read order (later wins):
1. Built-in DEFAULTS below
2. Skill-root ``zhihu_fetch_config.json`` (对话里改上限并固化到技能，写这里)
3. Workspace ``zhihu_fetch_config.json`` (本机覆盖，不进 git)
4. 当次命令行：``--max-items N`` / ``--all``

``0`` after resolve means unlimited. ``--all`` or config ``unlimited: true``
turns every cap into unlimited.

用法:
  python scripts/zhihu.py limits
  python scripts/zhihu.py limits --set collection.items_per_collection=10
  python scripts/zhihu.py limits --set batch.max_items=50 --where workspace
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys

from zhihu_fetch.core.paths import SKILL_ROOT, get_workspace_dir

CONFIG_NAME = "zhihu_fetch_config.json"

DEFAULTS = {
    "unlimited": False,
    "collection": {
        "max_collections": 10,
        "items_per_collection": 20,
        "max_items": 20,
    },
    "column": {
        "max_columns": 5,
        "items_per_column": 20,
    },
    "history": {
        "max_items": 20,
    },
    "batch": {
        "max_items": 20,
    },
    "people": {
        "max_articles": 20,
        "max_answers": 20,
    },
    "question": {
        "max_answers": 20,
    },
    "filter": {
        "min_voteup": 0,
        "since_days": 0,
    },
}


def skill_config_path():
    return os.path.join(SKILL_ROOT, CONFIG_NAME)


def workspace_config_path():
    return os.path.join(get_workspace_dir(), CONFIG_NAME)


def _read_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception as exc:
        print(f"[!] 无法读取配置 {path}: {exc}")
        return None


def _deep_merge(base, overlay):
    out = copy.deepcopy(base)
    for key, value in (overlay or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_config():
    """Merged config: defaults < skill file < workspace file."""
    cfg = copy.deepcopy(DEFAULTS)
    skill = _read_json(skill_config_path())
    if skill:
        cfg = _deep_merge(cfg, skill)
    workspace = _read_json(workspace_config_path())
    if workspace:
        cfg = _deep_merge(cfg, workspace)
    return cfg


def config_int(dotted_key, default=0):
    cur = load_config()
    for part in dotted_key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    try:
        return int(cur)
    except (TypeError, ValueError):
        return default


def wants_unlimited(argv=None):
    argv = sys.argv if argv is None else argv
    if "--all" in argv:
        return True
    return bool(load_config().get("unlimited"))


def cli_int(flag, argv=None):
    """Return int after ``flag`` if present, else None."""
    argv = sys.argv if argv is None else argv
    if flag not in argv:
        return None
    idx = argv.index(flag)
    if idx + 1 >= len(argv) or str(argv[idx + 1]).startswith("--"):
        return None
    try:
        return max(0, int(argv[idx + 1]))
    except Exception:
        return None


def resolve_limit(dotted_key, cli_value=None, argv=None):
    """Resolved cap for one key. 0 = unlimited."""
    if wants_unlimited(argv):
        return 0
    if cli_value is not None:
        return max(0, int(cli_value))
    return max(0, config_int(dotted_key, 0))


def describe_limit(value):
    return "不限制" if not value else str(value)


def print_resolved(argv=None):
    cfg = load_config()
    print(f"skill config:     {skill_config_path()}")
    print(f"  exists: {os.path.exists(skill_config_path())}")
    print(f"workspace config: {workspace_config_path()}")
    print(f"  exists: {os.path.exists(workspace_config_path())}")
    print(f"unlimited: {wants_unlimited(argv)}")
    print("resolved:")
    print(json.dumps(cfg, ensure_ascii=False, indent=2))


def _set_dotted(data, dotted_key, value):
    parts = dotted_key.split(".")
    cur = data
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    if isinstance(value, str) and value.lower() in ("true", "false"):
        cur[parts[-1]] = value.lower() == "true"
    else:
        try:
            cur[parts[-1]] = int(value)
        except (TypeError, ValueError):
            cur[parts[-1]] = value
    return data


def save_config(where, updates):
    path = workspace_config_path() if where == "workspace" else skill_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    current = _read_json(path) or {}
    for dotted_key, value in updates:
        _set_dotted(current, dotted_key, value)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"已写入 {path}")
    return path


def main():
    parser = argparse.ArgumentParser(description="查看或固化知乎抓取上限")
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="key=value",
        help="写入配置，如 collection.items_per_collection=10（可重复）",
    )
    parser.add_argument(
        "--where",
        choices=("skill", "workspace"),
        default="skill",
        help="固化位置：skill=技能根配置（默认，对话固化）；workspace=本机覆盖",
    )
    args = parser.parse_args()
    if args.set:
        updates = []
        for spec in args.set:
            if "=" not in spec:
                print(f"[!] 无效 --set: {spec}（需要 key=value）")
                sys.exit(1)
            key, value = spec.split("=", 1)
            updates.append((key.strip(), value.strip()))
        save_config(args.where, updates)
    print_resolved()


if __name__ == "__main__":
    main()
