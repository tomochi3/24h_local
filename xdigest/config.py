"""設定ファイル（TOML）の読み込み。"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG = Path("~/.config/xdigest/config.toml").expanduser()
DEFAULT_TOKEN_FILE = Path("~/.config/xdigest/x_bearer_token").expanduser()


@dataclass
class Config:
    accounts: list[str]
    output_dir: Path = Path("~/XDigest").expanduser()
    lookback_hours: int = 24              # 初回（前回の続きが分からないとき）にさかのぼる時間
    max_posts_per_account: int = 40       # 1回の実行で1アカウントから読む最大件数（X APIの課金対策）
    include_replies: bool = False
    include_retweets: bool = False
    include_images: bool = True
    skip_empty: bool = True               # 新しい投稿が0件ならPDFを作らない
    run_hour: int = 7                     # 毎日何時に作るか（Macのローカル時刻）
    run_minute: int = 0
    ntfy_topic: str = ""                  # 空なら通知しない
    ntfy_server: str = "https://ntfy.sh"
    ntfy_attach_pdf: bool = False         # 通知にPDFを添付する（ntfy.shでは一時的に公開サーバーに置かれる）
    public_url: str = ""                  # 通知のリンク先（例: http://macbook:8766）
    serve_port: int = 8766
    token_file: Path = DEFAULT_TOKEN_FILE
    extra: dict = field(default_factory=dict)

    @property
    def pdf_dir(self) -> Path:
        return self.output_dir / "pdf"

    @property
    def state_file(self) -> Path:
        return self.output_dir / "state.json"

    def bearer_token(self) -> str:
        token = os.environ.get("X_BEARER_TOKEN", "").strip()
        if token:
            return token
        try:
            return self.token_file.read_text(encoding="utf-8").strip()
        except OSError:
            raise SystemExit(
                f"X APIのBearer Tokenがありません。{self.token_file} に保存するか、"
                "環境変数 X_BEARER_TOKEN を設定してください。") from None


_PATH_KEYS = {"output_dir", "token_file"}


def load_config(path: Path | str | None = None) -> Config:
    path = Path(path).expanduser() if path else DEFAULT_CONFIG
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"設定ファイルがありません: {path}（config.example.toml をコピーして作ってください）") from None
    known = set(Config.__dataclass_fields__) - {"extra"}
    kwargs = {}
    extra = {}
    for key, value in raw.items():
        if key in known:
            kwargs[key] = Path(value).expanduser() if key in _PATH_KEYS else value
        else:
            extra[key] = value
    accounts = [a.strip().lstrip("@") for a in kwargs.get("accounts", []) if a.strip()]
    if not accounts:
        raise SystemExit("accounts に1つ以上のXアカウント（@なしのユーザー名）を書いてください。")
    kwargs["accounts"] = accounts
    return Config(**kwargs, extra=extra)
