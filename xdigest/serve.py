"""作ったPDFをスマホから見るための小さなWebサーバー（Tailscale / 同じWi-Fi向け）。

初回に作るランダムなキーを知っている人だけが見られる。
`/?key=...` で開くとCookieが保存され、以後はキーなしでも見られる。
"""
from __future__ import annotations

import html
import secrets
import socket
import urllib.parse
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import Config


def access_key(cfg: Config) -> str:
    path = cfg.output_dir / "access_key"
    try:
        key = path.read_text(encoding="utf-8").strip()
        if key:
            return key
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_urlsafe(18)
    path.write_text(key, encoding="utf-8")
    path.chmod(0o600)
    return key


def share_url(cfg: Config) -> str:
    base = cfg.public_url.rstrip("/") if cfg.public_url else f"http://{socket.gethostname()}:{cfg.serve_port}"
    return f"{base}/?key={access_key(cfg)}"


def make_handler(pdf_dir: Path, key: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _authorized(self, query: dict) -> bool:
            if secrets.compare_digest(query.get("key", [""])[0], key):
                return True
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            return "xdigest" in cookie and secrets.compare_digest(cookie["xdigest"].value, key)

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urllib.parse.urlsplit(self.path)
            query = urllib.parse.parse_qs(url.query)
            if not self._authorized(query):
                return self._send(403, "キー付きのURLで開いてください".encode(), "text/plain; charset=utf-8")
            cookie = {"Set-Cookie": f"xdigest={key}; Max-Age=31536000; HttpOnly; SameSite=Lax; Path=/"}
            path = urllib.parse.unquote(url.path)
            if path == "/":
                files = sorted((p for p in pdf_dir.glob("*") if p.suffix in (".pdf", ".html")), reverse=True)
                rows = "".join(f'<li><a href="/pdf/{urllib.parse.quote(p.name)}">{html.escape(p.stem)}</a>'
                               f' <small>{p.stat().st_size // 1024}KB</small></li>' for p in files[:120])
                page = ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                        "<title>X ダイジェスト</title><style>body{font-family:-apple-system,sans-serif;"
                        "margin:16px;line-height:2}a{font-size:1.1em}</style><h1>📰 X ダイジェスト</h1>"
                        f"<ul>{rows or '<li>まだありません</li>'}</ul>")
                return self._send(200, page.encode(), "text/html; charset=utf-8", cookie)
            if path.startswith("/pdf/"):
                name = Path(path[5:]).name
                target = pdf_dir / name
                if name and target.is_file() and target.suffix in (".pdf", ".html"):
                    ctype = "application/pdf" if target.suffix == ".pdf" else "text/html; charset=utf-8"
                    return self._send(200, target.read_bytes(), ctype, cookie)
            self._send(404, b"not found", "text/plain")

    return Handler


def serve(cfg: Config, host: str = "0.0.0.0") -> None:
    cfg.pdf_dir.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, cfg.serve_port), make_handler(cfg.pdf_dir, access_key(cfg)))
    print(f"スマホで開くURL: {share_url(cfg)}", flush=True)
    server.serve_forever()
