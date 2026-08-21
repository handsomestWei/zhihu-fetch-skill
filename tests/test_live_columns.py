"""Live smoke: a user's columns page → hierarchy JSON → few article bodies."""

from __future__ import annotations

from pathlib import Path

from fetch_zhihu_collection import load_cookies, parse_people_slug, save_json
from fetch_zhihu_columns import (
    column_is_empty,
    column_matches,
    fetch_column_articles,
    list_member_columns,
)
from live_profile import (
    LIVE_COLUMN_NAME,
    LIVE_ITEMS_PER_COLUMN,
    LIVE_MAX_COLUMNS,
    LIVE_PROFILE_URL,
)
from test_live_fetch import _write_items
from workspace_paths import get_workspace_dir


def test_live_user_columns_hierarchy_and_sample_articles():
    workspace = Path(get_workspace_dir())
    articles_dir = workspace / "zhihu_articles_live_columns"
    images_dir = articles_dir / "images"
    articles_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    slug = parse_people_slug(LIVE_PROFILE_URL)
    assert slug
    cookie = load_cookies()
    print(f"workspace: {workspace}")
    print(f"column_filter={LIVE_COLUMN_NAME!r} max_columns={LIVE_MAX_COLUMNS} per_column={LIVE_ITEMS_PER_COLUMN}")

    columns = list_member_columns(slug, cookie)
    empty = [col for col in columns if column_is_empty(col)]
    nonempty = [col for col in columns if not column_is_empty(col)]
    print(f"columns={len(columns)} empty_skipped={len(empty)} nonempty={len(nonempty)}")
    for col in empty:
        print(f"skip empty column {col['id']} {col['title']}")
    assert columns, "未能列出用户专栏"

    if LIVE_COLUMN_NAME:
        nonempty = [col for col in nonempty if column_matches(col, LIVE_COLUMN_NAME)]
        assert nonempty, f"没有匹配专栏名称: {LIVE_COLUMN_NAME}"

    sampled = nonempty[:LIVE_MAX_COLUMNS]
    assert sampled, "有效专栏为空"

    tree = {
        "source": f"{LIVE_PROFILE_URL.rstrip('/')}/columns",
        "total": len(columns),
        "empty_skipped": len(empty),
        "column_filter": LIVE_COLUMN_NAME,
        "columns": [],
    }
    sampled_items = []
    for col in sampled:
        items = fetch_column_articles(col["id"], LIVE_ITEMS_PER_COLUMN, cookie)
        items = items[:LIVE_ITEMS_PER_COLUMN]
        for item in items:
            item["column_id"] = col["id"]
            item["column_title"] = col["title"]
            sampled_items.append(item)
        node = dict(col)
        node["items"] = items
        node["fetched"] = len(items)
        tree["columns"].append(node)
        save_json(
            str(workspace / f"zhihu_column_{col['id']}.json"),
            {
                "total": len(items),
                "column_id": col["id"],
                "title": col["title"],
                "source": col["url"],
                "items": items,
            },
        )
        print(f"column {col['title']}: {len(items)} items")

    save_json(str(workspace / f"zhihu_columns_{slug}.json"), tree)
    assert tree["columns"], "层级 JSON 没有专栏节点"
    assert sampled_items, "专栏下列表没有文章"
    assert all(item.get("column_id") for item in sampled_items)
    assert all(len(node.get("items") or []) <= LIVE_ITEMS_PER_COLUMN for node in tree["columns"])

    written = _write_items(sampled_items, articles_dir, images_dir)
    print(f"markdown: {len(written)} / items {len(sampled_items)}")
    assert written, "专栏文章列表已拿到，但正文都未能写成 Markdown"
