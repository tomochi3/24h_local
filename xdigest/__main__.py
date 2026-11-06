"""使い方:

  python -m xdigest run            # 今すぐ1回作る
  python -m xdigest serve          # PDF閲覧サーバー
  python -m xdigest install        # 毎日の自動実行と閲覧サーバーを launchd に登録（Mac）
  python -m xdigest uninstall
  python -m xdigest url            # スマホで開くURLを表示
"""
from __future__ import annotations

import argparse

from .config import DEFAULT_CONFIG, load_config


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="xdigest", description="Xの投稿をまとめてPDFにする")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG), help=f"設定ファイル（既定: {DEFAULT_CONFIG}）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="今すぐ1回作る")
    r.add_argument("--dry-run", action="store_true", help="前回位置（state）を更新しない")
    sub.add_parser("serve", help="PDF閲覧サーバーを起動")
    sub.add_parser("install", help="launchd に登録（Mac）")
    sub.add_parser("uninstall", help="launchd から解除（Mac）")
    sub.add_parser("url", help="スマホで開くURLを表示")
    args = ap.parse_args(argv)

    if args.cmd == "uninstall":
        from .service import uninstall
        return uninstall()
    cfg = load_config(args.config)
    if args.cmd == "run":
        from .pipeline import run
        run(cfg, dry_run=args.dry_run)
    elif args.cmd == "serve":
        from .serve import serve
        serve(cfg)
    elif args.cmd == "install":
        from .serve import share_url
        from .service import install
        install(cfg, args.config)
        print(f"毎日 {cfg.run_hour:02d}:{cfg.run_minute:02d} に作成します。")
        print(f"スマホで開くURL: {share_url(cfg)}")
    elif args.cmd == "url":
        from .serve import share_url
        print(share_url(cfg))


if __name__ == "__main__":
    main()
