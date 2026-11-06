import io
import json
import plistlib
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import pytest

from xdigest import pipeline, summarize
from xdigest.config import Config, load_config
from xdigest.render import build_html
from xdigest.service import plists
from xdigest.xapi import XClient, build_posts, expand_text

NOW = datetime(2026, 11, 6, 22, 0, tzinfo=timezone.utc)

TIMELINE = {
    "data": [
        {"id": "200", "created_at": "2026-11-06T10:00:00.000Z", "text": "新しい論文 https://t.co/abc https://t.co/pic",
         "entities": {"urls": [
             {"url": "https://t.co/abc", "expanded_url": "https://arxiv.org/abs/2611.00001"},
             {"url": "https://t.co/pic", "expanded_url": "https://x.com/hillbig/status/200/photo/1"}]},
         "attachments": {"media_keys": ["3_1"]},
         "public_metrics": {"like_count": 120, "retweet_count": 30},
         "referenced_tweets": [{"type": "quoted", "id": "150"}]},
        {"id": "201", "created_at": "2026-11-06T12:00:00.000Z", "text": "短い本文…",
         "note_tweet": {"text": "長文の全文 <script>"}, "public_metrics": {}},
    ],
    "includes": {
        "media": [{"media_key": "3_1", "type": "photo", "url": "https://pbs.twimg.com/media/a.jpg"}],
        "tweets": [{"id": "150", "created_at": "2026-11-05T00:00:00.000Z", "text": "引用元", "author_id": "9"}],
        "users": [{"id": "9", "username": "someone"}],
    },
    "meta": {"result_count": 2},
}


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeX:
    def __init__(self):
        self.calls = []

    def __call__(self, req, timeout=None):
        url = urllib.parse.urlsplit(req.full_url)
        q = urllib.parse.parse_qs(url.query)
        self.calls.append((url.path, q))
        if url.path.endswith("/users/by"):
            return FakeResp(json.dumps({"data": [{"id": "42", "username": "hillbig"}]}).encode())
        return FakeResp(json.dumps(TIMELINE).encode())


def test_expand_text_restores_urls_and_drops_media_links():
    t = TIMELINE["data"][0]
    assert expand_text(t) == "新しい論文 https://arxiv.org/abs/2611.00001"
    assert expand_text(TIMELINE["data"][1]) == "長文の全文 <script>"


def test_build_posts_images_and_quotes():
    posts = build_posts(TIMELINE, "hillbig")
    assert posts[0].images == ["https://pbs.twimg.com/media/a.jpg"]
    assert posts[0].quoted.username == "someone"
    assert posts[0].url == "https://x.com/hillbig/status/200"


def test_run_uses_cached_ids_and_since_id(tmp_path):
    cfg = Config(accounts=["hillbig"], output_dir=tmp_path, summarizer="none")
    fake = FakeX()
    out = pipeline.run(cfg, client=XClient("t", opener=fake), now=NOW)
    assert out and out.exists()
    first = [c for c in fake.calls if "tweets" in c[0]][0][1]
    assert "start_time" in first and "since_id" not in first
    assert first["exclude"] == ["replies,retweets"]
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["user_ids"] == {"hillbig": "42"} and state["since_id"] == {"hillbig": "201"}

    fake2 = FakeX()
    pipeline.run(cfg, client=XClient("t", opener=fake2), now=NOW)
    assert not any(c[0].endswith("/users/by") for c in fake2.calls)   # 2回目はユーザー検索しない
    second = [c for c in fake2.calls if "tweets" in c[0]][0][1]
    assert second["since_id"] == ["201"] and "start_time" not in second


def test_html_escapes_and_links_topics():
    posts = build_posts(TIMELINE, "hillbig")
    summary = {"overview": "まとめ<b>", "topics": [{"title": "論文", "summary": "s", "post_ids": ["200", "999"]}],
               "accounts": [{"username": "@hillbig", "summary": "論文紹介"}]}
    doc = build_html(posts, ["hillbig", "nobody"], summary, start=None, end=NOW)
    assert "<script>" not in doc and "&lt;script&gt;" in doc
    assert "まとめ&lt;b&gt;" in doc
    assert 'href="#p200"' in doc and "#p999" not in doc
    assert "論文紹介" in doc and "この期間の投稿はありません" in doc
    assert '<a href="https://arxiv.org/abs/2611.00001">' in doc


def test_summarize_fallback_and_none(monkeypatch):
    posts = build_posts(TIMELINE, "hillbig")
    assert summarize.summarize(posts, "none") is None

    def boom(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(summarize, "summarize_codex", boom)
    monkeypatch.setattr(summarize, "summarize_claude", lambda p, m: {"overview": "ok", "topics": [], "accounts": []})
    assert summarize.summarize(posts, "auto", log=lambda *a: None)["overview"] == "ok"


def test_child_env_strips_api_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "y")
    env = summarize._child_env()
    assert "ANTHROPIC_API_KEY" not in env and "OPENAI_API_KEY" not in env


def test_load_config(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('accounts = ["@hillbig", " "]\noutput_dir = "~/X"\nrun_hour = 6\n', encoding="utf-8")
    cfg = load_config(p)
    assert cfg.accounts == ["hillbig"] and cfg.run_hour == 6 and str(cfg.output_dir).endswith("/X")
    p.write_text("accounts = []\n")
    with pytest.raises(SystemExit):
        load_config(p)


def test_launchd_plists(tmp_path):
    cfg = Config(accounts=["a"], output_dir=tmp_path, run_hour=6, run_minute=30)
    out = plists(cfg, "/c.toml", python="/py", workdir="/w", path_env="/bin")
    run = plistlib.loads(out["com.xdigest.run"])
    assert run["StartCalendarInterval"] == {"Hour": 6, "Minute": 30}
    assert run["ProgramArguments"] == ["/py", "-m", "xdigest", "--config", "/c.toml", "run"]
    serve = plistlib.loads(out["com.xdigest.serve"])
    assert serve["KeepAlive"] is True and serve["ProgramArguments"][-1] == "serve"


def test_serve_requires_key(tmp_path):
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer
    from xdigest.serve import make_handler

    (tmp_path / "2026-11-07_0700.pdf").write_bytes(b"%PDF-1.4")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(tmp_path, "secret"))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with pytest.raises(urllib.error.HTTPError):
            opener.open(base + "/")
        page = opener.open(base + "/?key=secret").read().decode()
        assert "2026-11-07_0700" in page
        req = urllib.request.Request(base + "/pdf/2026-11-07_0700.pdf", headers={"Cookie": "xdigest=secret"})
        assert opener.open(req).read() == b"%PDF-1.4"
        with pytest.raises(urllib.error.HTTPError):
            opener.open(base + "/pdf/..%2Fstate.json?key=secret")
    finally:
        srv.shutdown()
