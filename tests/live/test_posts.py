"""Live smoke: profile posts + answers, skip URLs already in column JSON."""

from __future__ import annotations

from pathlib import Path

from zhihu_fetch.fetch.collection import load_cookies, parse_people_slug, save_json
from zhihu_fetch.fetch.posts import fetch_member_answers, fetch_member_articles
from live_profile import LIVE_MAX_ANSWERS, LIVE_MAX_ARTICLES, LIVE_PROFILE_URL
from live.test_fetch import _write_items
from zhihu_fetch.core.paths import get_workspace_dir
from zhihu_fetch.core.seen import canonical_url, collect_column_urls, filter_new_items


def test_live_user_posts_and_answers_sample():
    workspace = Path(get_workspace_dir())
    articles_dir = workspace / "zhihu_articles_live_posts"
    images_dir = articles_dir / "images"
    articles_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    slug = parse_people_slug(LIVE_PROFILE_URL)
    assert slug
    cookie = load_cookies()
    column_seen = collect_column_urls(str(workspace))
    print(
        f"workspace={workspace} cookie={'yes' if cookie else 'no'} "
        f"column_urls={len(column_seen)}"
    )

    articles, empty_a, seen_a = fetch_member_articles(
        slug, LIVE_MAX_ARTICLES, cookie, set(column_seen)
    )
    answers, empty_b, seen_b = fetch_member_answers(
        slug, LIVE_MAX_ANSWERS, cookie, set()
    )
    print(
        f"articles={len(articles)} skip_empty={empty_a} skip_seen={seen_a} "
        f"answers={len(answers)} skip_empty={empty_b} skip_seen={seen_b}"
    )
    assert articles or answers, "个人页文章/回答列表都为空"

    if articles:
        overlap, _skipped = filter_new_items(list(articles), set(column_seen))
        assert len(overlap) == len(articles), "文章列表未按专栏 URL 去重"
        save_json(
            str(workspace / f"zhihu_posts_{slug}.json"),
            {
                "total": len(articles),
                "source": f"{LIVE_PROFILE_URL.rstrip('/')}/posts",
                "kind": "articles",
                "items": articles,
            },
        )
        assert all("/p/" in (item.get("url") or "") for item in articles)

    if answers:
        save_json(
            str(workspace / f"zhihu_answers_{slug}.json"),
            {
                "total": len(answers),
                "source": f"{LIVE_PROFILE_URL.rstrip('/')}/answers",
                "kind": "answers",
                "items": answers,
            },
        )
        assert all("/answer/" in (item.get("url") or "") for item in answers)
        assert all(canonical_url(item["url"]).startswith("https://www.zhihu.com/answer/") for item in answers)

    sampled = articles + answers
    written = _write_items(sampled, articles_dir, images_dir)
    print(f"markdown: {len(written)} / items {len(sampled)}")
    assert written, "文章/回答列表已拿到，但正文都未能写成 Markdown"
