"""投稿を原文のまま、スマホでも読みやすいPDFにする（HTML → WeasyPrint）。"""
from __future__ import annotations

import html
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .xapi import Post

JST = timezone(timedelta(hours=9))
URL_RE = re.compile(r"https?://[^\s<>\"]+")

CSS = """
@page { size: A5; margin: 12mm 10mm 14mm;
        @bottom-center { content: counter(page) " / " counter(pages); font-size: 8pt; color: #888; } }
* { box-sizing: border-box; }
body { font-family: "Hiragino Sans", "Hiragino Kaku Gothic ProN", "Noto Sans CJK JP", "Noto Sans JP",
       "Yu Gothic", sans-serif; font-size: 10pt; line-height: 1.65; color: #1a1a1a; }
a { color: #1d6fd8; text-decoration: none; word-break: break-all; }
h1 { font-size: 18pt; margin: 0 0 2mm; }
h2 { font-size: 13pt; border-left: 4px solid #1d6fd8; padding-left: 3mm; margin: 6mm 0 3mm;
     page-break-after: avoid; }
h3 { font-size: 11pt; margin: 4mm 0 1mm; page-break-after: avoid; }
.meta { color: #666; font-size: 8.5pt; }
.account { page-break-before: always; }
.post { border-bottom: 1px solid #e3e3e3; padding: 2.5mm 0; page-break-inside: avoid; }
.post .text { white-space: pre-wrap; word-wrap: break-word; }
.post .foot { color: #777; font-size: 8pt; margin-top: 1mm; }
.quoted { border: 1px solid #ddd; border-radius: 2mm; padding: 2mm 3mm; margin-top: 2mm;
          font-size: 9pt; color: #333; }
.imgs img { max-width: 48%; max-height: 45mm; margin: 1.5mm 1.5mm 0 0; border-radius: 1.5mm; }
.empty { color: #888; }
.toc li { margin: 0.5mm 0; }
"""


def _linkify(text: str) -> str:
    out, pos = [], 0
    for m in URL_RE.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        url = m.group(0)
        out.append(f'<a href="{html.escape(url)}">{html.escape(url)}</a>')
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


def _time(dt: datetime) -> str:
    return dt.astimezone(JST).strftime("%m/%d %H:%M")


def _post_html(p: Post, include_images: bool) -> str:
    parts = [f'<div class="post" id="p{p.id}"><div class="text">{_linkify(p.text)}</div>']
    if include_images and p.images:
        parts.append('<div class="imgs">' + "".join(
            f'<img src="{html.escape(src)}">' for src in p.images[:4]) + "</div>")
    if p.quoted:
        q = p.quoted
        parts.append(f'<div class="quoted"><b>@{html.escape(q.username)}</b> '
                     f'<span class="meta">{_time(q.created_at)}</span><br>{_linkify(q.text)}</div>')
    reply = "返信 · " if p.is_reply else ""
    parts.append(f'<div class="foot">{reply}{_time(p.created_at)} · ♥ {p.likes:,} · RT {p.reposts:,} · '
                 f'<a href="{html.escape(p.url)}">Xで開く</a></div></div>')
    return "".join(parts)


def build_html(posts: list[Post], accounts: list[str], *,
               start: datetime | None, end: datetime, include_images: bool = True) -> str:
    by_user: dict[str, list[Post]] = defaultdict(list)
    for p in posts:
        by_user[p.username.lower()].append(p)
    period = (f"{start.astimezone(JST):%Y/%m/%d %H:%M} 〜 " if start else "") + f"{end.astimezone(JST):%Y/%m/%d %H:%M}"
    body = [f"<h1>X ダイジェスト {end.astimezone(JST):%Y/%m/%d}</h1>",
            f'<div class="meta">{html.escape(period)} · {len(accounts)}アカウント · {len(posts)}件の投稿</div>']

    body.append('<h2>アカウント</h2><ul class="toc">')
    for name in accounts:
        n = len(by_user.get(name.lower(), []))
        body.append(f'<li><a href="#u-{html.escape(name.lower())}">@{html.escape(name)}</a> '
                    f'<span class="meta">{n}件</span></li>')
    body.append("</ul>")

    for name in accounts:
        items = sorted(by_user.get(name.lower(), []), key=lambda p: p.created_at)
        body.append(f'<section class="account" id="u-{html.escape(name.lower())}">'
                    f'<h2>@{html.escape(name)} <span class="meta">{len(items)}件</span></h2>')
        if not items:
            body.append('<p class="empty">この期間の投稿はありません。</p>')
        body.extend(_post_html(p, include_images) for p in items)
        body.append("</section>")

    return ("<!doctype html><html lang=\"ja\"><head><meta charset=\"utf-8\">"
            f"<title>X ダイジェスト</title><style>{CSS}</style></head><body>"
            + "\n".join(body) + "</body></html>")


def write_pdf(html_text: str, pdf_path: Path) -> Path:
    """PDFを書き出す。WeasyPrint がなければHTMLだけ保存して、そのパスを返す。"""
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    html_path = pdf_path.with_suffix(".html")
    html_path.write_text(html_text, encoding="utf-8")
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as e:
        print(f"WeasyPrint が使えないため HTML だけ保存しました（{e}）: {html_path}")
        return html_path
    HTML(string=html_text, base_url=str(pdf_path.parent)).write_pdf(str(pdf_path))
    html_path.unlink(missing_ok=True)
    return pdf_path
