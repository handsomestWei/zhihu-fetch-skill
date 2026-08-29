"""Offline tests for column list filtering."""

from zhihu_fetch.fetch.columns import column_is_empty, column_matches, extract_column_id, normalize_column_article


def test_extract_column_id():
    assert extract_column_id("https://www.zhihu.com/column/yuandong") == "yuandong"
    assert extract_column_id("https://zhuanlan.zhihu.com/yuandong") == "yuandong"
    assert extract_column_id("yuandong") == "yuandong"


def test_column_matches_title_and_id():
    col = {"id": "yuandong", "title": "远东轶事"}
    assert column_matches(col, "远东轶事")
    assert column_matches(col, "yuandong")
    assert column_matches(col, "远东")
    assert not column_matches(col, "不存在")
    assert column_matches(col, "")


def test_column_is_empty():
    assert column_is_empty({"contributions_count": 0})
    assert not column_is_empty({"contributions_count": 103})
    assert not column_is_empty({})


def test_normalize_column_article_skips_empty_url():
    assert normalize_column_article({}) is None
    item = normalize_column_article(
        {
            "id": 1,
            "title": "hello",
            "url": "https://zhuanlan.zhihu.com/p/1",
            "voteup_count": 3,
            "author": {"name": "a"},
            "type": "article",
        },
        {"id": "yuandong", "title": "远东轶事"},
    )
    assert item["column_id"] == "yuandong"
    assert item["url"].endswith("/p/1")
