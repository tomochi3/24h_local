"""1回分の処理: 取得 → 要約 → PDF → 通知。"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .config import Config
from .render import JST, build_html, write_pdf
from .summarize import summarize
from .xapi import XApiError, XClient

POST_PRICE_USD = 0.005   # 他人の投稿1件あたりの目安（X API 従量課金）。正確な単価は developer portal で確認


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def notify(cfg: Config, title: str, message: str, *, pdf: Path | None = None, opener=urllib.request.urlopen):
    if not cfg.ntfy_topic:
        return
    url = f"{cfg.ntfy_server.rstrip('/')}/{cfg.ntfy_topic}"
    headers = {"Title": title.encode("utf-8"), "Tags": "newspaper"}
    if cfg.public_url and pdf:
        headers["Click"] = f"{cfg.public_url.rstrip('/')}/pdf/{pdf.name}"
    data = message.encode("utf-8")
    if pdf and cfg.ntfy_attach_pdf and pdf.suffix == ".pdf":
        headers["Filename"] = pdf.name
        headers["Message"] = message.encode("utf-8")
        data = pdf.read_bytes()
    try:
        opener(urllib.request.Request(url, data=data, headers=headers, method="PUT" if "Filename" in headers else "POST"),
               timeout=60).close()
    except Exception as e:  # 通知の失敗で本体を止めない
        print(f"通知に失敗しました: {e}")


def run(cfg: Config, *, client: XClient | None = None, now: datetime | None = None,
        dry_run: bool = False) -> Path | None:
    now = now or datetime.now(timezone.utc)
    state = load_state(cfg.state_file)
    client = client or XClient(cfg.bearer_token())

    ids: dict = state.setdefault("user_ids", {})
    missing = [a for a in cfg.accounts if a.lower() not in ids]
    if missing:
        found = client.lookup_users(missing)
        ids.update(found)
        for a in missing:
            if a.lower() not in found:
                print(f"@{a} が見つかりませんでした（名前の綴りを確認してください）")

    since: dict = state.setdefault("since_id", {})
    posts, errors = [], []
    for name in cfg.accounts:
        uid = ids.get(name.lower())
        if not uid:
            continue
        try:
            got = client.user_posts(uid, name, since_id=since.get(name.lower()),
                                    lookback_hours=cfg.lookback_hours, max_posts=cfg.max_posts_per_account,
                                    include_replies=cfg.include_replies, include_retweets=cfg.include_retweets,
                                    now=now)
        except XApiError as e:
            errors.append(f"@{name}: {e}")
            print(errors[-1])
            if e.status in (401, 402, 403, 429):
                break   # 認証切れ・クレジット切れ・レート制限は他のアカウントでも同じなので止める
            continue
        print(f"@{name}: {len(got)}件")
        posts.extend(got)
        if got:
            since[name.lower()] = max(got, key=lambda p: int(p.id)).id

    print(f"取得した投稿 {client.reads}件（概算 ${client.reads * POST_PRICE_USD:.3f}）")
    last_run = state.get("last_run")
    start = datetime.fromisoformat(last_run) if last_run else None

    if not posts and cfg.skip_empty:
        print("新しい投稿がないのでPDFは作りません")
        if errors:
            notify(cfg, "X ダイジェスト: エラー", "\n".join(errors))
        if not dry_run:
            state["last_run"] = now.isoformat()
            save_state(cfg.state_file, state)
        return None

    summary = summarize(posts, cfg.summarizer, claude_model=cfg.claude_model, codex_model=cfg.codex_model)
    html_text = build_html(posts, cfg.accounts, summary, start=start, end=now, include_images=cfg.include_images)
    out = write_pdf(html_text, cfg.pdf_dir / f"{now.astimezone(JST):%Y-%m-%d_%H%M}.pdf")
    print(f"保存しました: {out}")

    if not dry_run:
        state["last_run"] = now.isoformat()
        save_state(cfg.state_file, state)
    msg = f"{len(posts)}件の投稿" + ("（要約あり）" if summary else "（要約なし）")
    if errors:
        msg += "\n" + "\n".join(errors)
    notify(cfg, f"X ダイジェスト {now.astimezone(JST):%m/%d}", msg, pdf=out)
    return out
