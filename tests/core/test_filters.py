"""Offline tests for vote/time filters and content_updated refresh."""

from zhihu_fetch.core.filters import decide_fetch, passes_filters, resolve_min_voteup, resolve_since_unix
from zhihu_fetch.core.times import to_unix


def test_to_unix_seconds_and_iso():
    assert to_unix(1700000000) == 1700000000
    assert to_unix(1700000000000) == 1700000000
    assert to_unix("2020-01-01T00:00:00+00:00") == to_unix(1577836800)


def test_passes_filters_vote_and_since():
    item = {"voteup": 10, "content_updated": 2000}
    assert passes_filters(item, min_voteup=10, since_unix=1000)
    assert not passes_filters(item, min_voteup=11, since_unix=0)
    assert not passes_filters(item, min_voteup=0, since_unix=3000)
    assert passes_filters({"voteup": 1}, min_voteup=0, since_unix=3000)


def test_resolve_cli_filters():
    assert resolve_min_voteup(["prog", "--min-voteup", "8"]) == 8
    assert resolve_since_unix(["prog", "--since", "2020-01-01"]) > 0
    days = resolve_since_unix(["prog", "--days", "2"])
    assert days > 0


def test_decide_fetch_refresh_and_skip():
    url = "https://zhuanlan.zhihu.com/p/1"
    index = {url: {"content_updated": 100, "sources": ["posts"]}}
    item = {"url": url, "content_updated": 200}
    assert decide_fetch(item, index_urls=index, seen_urls=set(), since_last=True) == "refresh"
    assert item.get("refresh") is True

    stale = {"url": url, "content_updated": 100}
    assert decide_fetch(stale, index_urls=index, seen_urls={url}, since_last=True) == "skip"

    fresh = {"url": "https://zhuanlan.zhihu.com/p/2", "content_updated": 9}
    assert decide_fetch(fresh, index_urls=index, seen_urls=set(), since_last=True) == "new"


def test_decide_fetch_backfills_missing_timestamp_without_refresh():
    url = "https://zhuanlan.zhihu.com/p/9"
    rec = {"sources": ["posts"]}
    index = {url: rec}
    item = {"url": url, "content_updated": 50}
    assert decide_fetch(item, index_urls=index, seen_urls={url}, since_last=True) == "skip"
    assert rec["content_updated"] == 50
    assert not item.get("refresh")
