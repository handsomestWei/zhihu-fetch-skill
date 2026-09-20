"""Offline tests for gone-resource skip (404 articles / dead images)."""

from zhihu_fetch.fetch.resources import (
    image_url_candidates,
    is_resource_gone,
    normalize_image_src,
    try_download_image,
)


def test_is_resource_gone_http_and_zhihu_copy():
    assert is_resource_gone(404)
    assert is_resource_gone(410)
    assert is_resource_gone(200, "你似乎来到了没有知识存在的荒原")
    assert is_resource_gone(0, "", "api_failed:404")
    assert is_resource_gone(0, "", '{"error":{"name":"ResourceNotFoundException"}}')
    assert not is_resource_gone(200, "正常正文" * 20)
    assert not is_resource_gone(403, "请登录")


def test_image_url_candidates_keep_equation_query():
    assert normalize_image_src("//pic1.zhimg.com/v2-a.jpg") == "https://pic1.zhimg.com/v2-a.jpg"
    eq = "https://www.zhihu.com/equation?tex=E%3Dmc%5E2"
    assert image_url_candidates(eq) == [eq]
    src = "https://pic1.zhimg.com/v2-a.jpg?source=1940ef5c"
    cands = image_url_candidates(src)
    assert cands[0] == src
    assert "https://pic1.zhimg.com/v2-a.jpg" in cands


def test_delay_window_and_cli(monkeypatch):
    from zhihu_fetch.fetch.batch import delay_window, item_delay_seconds, resolve_item_delay

    assert delay_window(1.5, 0.7) == (0.8, 2.2)
    monkeypatch.setattr("zhihu_fetch.fetch.batch.random.uniform", lambda a, b: (a + b) / 2)
    assert item_delay_seconds(3, 0.5) == 3.0
    base, jitter = resolve_item_delay(["prog", "--delay", "4", "--delay-jitter", "1"])
    assert base == 4
    assert jitter == 1


def test_try_download_image_skips_404(tmp_path, monkeypatch):
    calls = []

    def fake_urlopen(req, timeout=10):
        calls.append(req.full_url)
        import urllib.error
        from io import BytesIO

        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", hdrs={}, fp=BytesIO())

    monkeypatch.setattr("zhihu_fetch.fetch.resources.urllib.request.urlopen", fake_urlopen)
    name, status = try_download_image(
        "https://pic1.zhimg.com/v2-missing.jpg?source=1",
        str(tmp_path),
        log=False,
    )
    assert name is None
    assert status == 404
    assert calls
    assert not any(tmp_path.iterdir())


def test_html_to_markdown_omits_dead_image_url(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "zhihu_fetch.fetch.batch.try_download_image",
        lambda *args, **kwargs: (None, 404),
    )
    monkeypatch.setattr("zhihu_fetch.fetch.batch._cookie_header", lambda: "")
    from zhihu_fetch.fetch.batch import html_to_markdown

    html = '<p>hi</p><img src="https://pic1.zhimg.com/v2-dead.jpg" alt="图">'
    text, images, sources = html_to_markdown(html, str(tmp_path))
    assert "pic1.zhimg.com/v2-dead.jpg" not in text or "skipped_image" in text
    assert "![图](https://pic1.zhimg.com/v2-dead.jpg)" not in text
    assert "图片已失效" in text
    assert images == []
