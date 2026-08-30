"""Live smoke: question page → a few answers."""

from __future__ import annotations

from pathlib import Path

from zhihu_fetch.fetch.collection import load_cookies, parse_people_slug, save_json
from zhihu_fetch.fetch.posts import fetch_member_answers
from zhihu_fetch.fetch.question import extract_question_id, fetch_question_answers
from live_profile import LIVE_MAX_ANSWERS, LIVE_PROFILE_URL
from live.test_fetch import _write_items
from zhihu_fetch.core.paths import get_workspace_dir


def test_live_question_answers_sample():
    workspace = Path(get_workspace_dir())
    articles_dir = workspace / "zhihu_articles_live_question"
    images_dir = articles_dir / "images"
    articles_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    slug = parse_people_slug(LIVE_PROFILE_URL)
    assert slug
    cookie = load_cookies()
    answers, _empty, _seen = fetch_member_answers(slug, 1, cookie, set())
    assert answers, "抽检账号没有公开回答，无法反推问题页"
    qid = extract_question_id(answers[0]["url"])
    assert qid, answers[0]["url"]

    items, title, stats = fetch_question_answers(qid, LIVE_MAX_ANSWERS, cookie)
    print(
        f"question={qid} title={title!r} answers={len(items)} "
        f"skip_seen={stats.get('skipped_seen', 0)}"
    )
    assert items, "问题页回答列表为空"
    assert all("/answer/" in (item.get("url") or "") for item in items)
    save_json(
        str(workspace / f"zhihu_question_{qid}.json"),
        {
            "total": len(items),
            "question_id": qid,
            "title": title,
            "source": f"https://www.zhihu.com/question/{qid}",
            "kind": "question",
            "items": items,
        },
    )
    written = _write_items(items, articles_dir, images_dir)
    print(f"markdown: {len(written)} / items {len(items)}")
    assert written, "问题页列表已拿到，但正文都未能写成 Markdown"
