"""Offline tests for crawl-limit config resolution."""

from __future__ import annotations

import json

from fetch_limits import (
    DEFAULTS,
    config_int,
    resolve_limit,
    save_config,
    wants_unlimited,
    workspace_config_path,
)


def test_defaults_match_skill_config():
    assert config_int("collection.max_items") == DEFAULTS["collection"]["max_items"]
    assert config_int("batch.max_items") == DEFAULTS["batch"]["max_items"]
    assert config_int("column.items_per_column") == DEFAULTS["column"]["items_per_column"]


def test_cli_overrides_config():
    assert resolve_limit("batch.max_items", cli_value=3, argv=["prog"]) == 3
    assert resolve_limit("batch.max_items", cli_value=None, argv=["prog"]) == DEFAULTS["batch"]["max_items"]


def test_all_flag_unlimited():
    assert resolve_limit("history.max_items", cli_value=99, argv=["prog", "--all"]) == 0
    assert wants_unlimited(["prog", "--all"]) is True


def test_workspace_overlay_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIHU_WORKSPACE", str(tmp_path))
    save_config("workspace", [("collection.max_items", "7")])
    assert workspace_config_path() == str(tmp_path / "zhihu_fetch_config.json")
    data = json.loads((tmp_path / "zhihu_fetch_config.json").read_text(encoding="utf-8"))
    assert data["collection"]["max_items"] == 7
    assert resolve_limit("collection.max_items", argv=["prog"]) == 7
    assert resolve_limit("collection.items_per_collection", argv=["prog"]) == DEFAULTS["collection"]["items_per_collection"]
