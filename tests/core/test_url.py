"""Offline tests for URL routing, incremental seen-set, and post/answer normalize."""

from zhihu_fetch.fetch.collection import collection_matches
from zhihu_fetch.fetch.posts import normalize_answer, normalize_article
from zhihu_fetch.core.seen import canonical_url, collect_column_urls, filter_new_items, record_urls
from zhihu_fetch.core.url import classify_zhihu_url


def test_classify_collection_and_people_tabs():
    assert classify_zhihu_url("https://www.zhihu.com/collection/12345").kind == "collection"
    people = classify_zhihu_url("https://www.zhihu.com/people/tian-yuan-dong")
    assert people.kind == "people"
    assert people.slug == "tian-yuan-dong"
    assert classify_zhihu_url("https://www.zhihu.com/people/tian-yuan-dong/columns").kind == "columns"
    assert classify_zhihu_url("https://www.zhihu.com/people/tian-yuan-dong/collections").kind == "collections"
    assert classify_zhihu_url("https://www.zhihu.com/people/tian-yuan-dong/posts").kind == "posts"
    assert classify_zhihu_url("https://www.zhihu.com/people/tian-yuan-dong/answers").kind == "answers"


def test_classify_article_and_answer():
    art = classify_zhihu_url("https://zhuanlan.zhihu.com/p/2015027745743189513")
    assert art.kind == "article"
    assert art.article_id == "2015027745743189513"
    ans = classify_zhihu_url("https://www.zhihu.com/question/1/answer/2")
    assert ans.kind == "answer"
    assert ans.answer_id == "2"
    assert ans.question_id == "1"
    q = classify_zhihu_url("https://www.zhihu.com/question/123456")
    assert q.kind == "question"
    assert q.question_id == "123456"


def test_classify_column_url():
    col = classify_zhihu_url("https://www.zhihu.com/column/yuandong")
    assert col.kind == "column"
    assert col.column_id == "yuandong"


def test_canonical_url_dedupes_answer_and_article_hosts():
    assert canonical_url("https://www.zhihu.com/question/9/answer/88?foo=1") == "https://www.zhihu.com/answer/88"
    assert canonical_url("https://api.zhihu.com/answers/88") == "https://www.zhihu.com/answer/88"
    assert canonical_url("http://zhuanlan.zhihu.com/p/12") == "https://zhuanlan.zhihu.com/p/12"


def test_filter_new_items_skips_seen(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIHU_WORKSPACE", str(tmp_path))
    seen = {"https://zhuanlan.zhihu.com/p/1"}
    fresh, skipped = filter_new_items(
        [
            {"url": "https://zhuanlan.zhihu.com/p/1", "title": "old"},
            {"url": "https://zhuanlan.zhihu.com/p/2", "title": "new"},
        ],
        seen,
    )
    assert [x["title"] for x in fresh] == ["new"]
    assert len(skipped) == 1
    assert "https://zhuanlan.zhihu.com/p/2" in seen


def test_collect_column_urls_from_json_and_index(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIHU_WORKSPACE", str(tmp_path))
    (tmp_path / "zhihu_column_yuandong.json").write_text(
        '{"items":[{"url":"https://zhuanlan.zhihu.com/p/99"}]}',
        encoding="utf-8",
    )
    record_urls([{"url": "https://zhuanlan.zhihu.com/p/100", "title": "x"}], "column:yuandong", str(tmp_path))
    seen = collect_column_urls(str(tmp_path))
    assert "https://zhuanlan.zhihu.com/p/99" in seen
    assert "https://zhuanlan.zhihu.com/p/100" in seen


def test_collection_matches_name_or_id():
    fav = {"id": "111", "title": "CS 笔记"}
    assert collection_matches(fav, "CS")
    assert collection_matches(fav, "111")
    assert not collection_matches(fav, "算法")
    assert collection_matches(fav, "")


def test_extract_question_id():
    from zhihu_fetch.fetch.question import extract_question_id

    assert extract_question_id("https://www.zhihu.com/question/99") == "99"
    assert extract_question_id("https://www.zhihu.com/question/99/answer/1") == "99"
    assert extract_question_id("99") == "99"


def test_normalize_article_and_answer():
    article = normalize_article({"id": 7, "title": "t", "url": "", "author": {"name": "a"}})
    assert article["url"] == "https://zhuanlan.zhihu.com/p/7"
    answer = normalize_answer(
        {
            "id": 22,
            "question": {"id": 11, "title": "问题"},
            "author": {"name": "b"},
            "voteup_count": 3,
        }
    )
    assert answer["url"] == "https://www.zhihu.com/question/11/answer/22"
    assert answer["title"] == "问题"
    assert normalize_answer({"id": 1}) is None
