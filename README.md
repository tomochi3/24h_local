# 24h — 使っていない MacBook を24時間サーバーにする

MacBook（2018年・Intel・メモリ8GB・SSD 256GB）を家に置きっぱなしにして、**卓球動画編集サーバー**（[tomochi3/ai_edit_TT](https://github.com/tomochi3/ai_edit_TT)）を常時動かします。

| サービス | 何をする | スマホから |
|---|---|---|
| **卓球動画編集**（ai_edit_TT） | スマホから送った試合動画をAIでカット・得点判定し、スマホで選別・書き出し | `http://<Mac>:8765/?key=...` |

```
iPhone ──Tailscale(VPN)──▶ MacBook（ふた開け・電源つなぎっぱなし）
                            ├─ launchd: com.pingpong-editor.app  :8765  ← ai_edit_TT
                            └─ launchd: com.macserver.healthcheck 1時間ごと（容量・停止・温度 → ntfy）
```

- AI判定は **Codex / Claude Code の月額プランのログイン** を使います（ai_edit_TT の方針）。
- 外から使うときは Tailscale のみ。ルーターのポート開放はしません。

> **X の投稿まとめ（xdigest）は [tomochi3/smallx](https://github.com/tomochi3/smallx) に移りました。**
> GitHub Actions で毎朝動き、<https://tomochi3.github.io/smallx/> に原文のまま載るので、この MacBook は不要です。
> 以前この MacBook に `xdigest install` していた場合は、次で登録を消してください。
>
> ```bash
> for l in com.xdigest.run com.xdigest.serve; do launchctl bootout "gui/$(id -u)/$l"; rm -f ~/Library/LaunchAgents/$l.plist; done
> ```

---

## 0. 全体の順番

1. macOS を更新し、ai_edit_TT の README「**初期化したMacBookを自宅サーバーにする**」の手順1〜5を実行
   （Homebrew・Python・ffmpeg・gh・Tailscale・Codex・Claude のインストールとログインまで）
2. このリポジトリで「Mac本体の常時稼働設定」（下の1）
3. ai_edit_TT の `install-service`（下の2、ai_edit_TT README の手順6）

## 1. Mac本体の常時稼働設定

```bash
mkdir -p "$HOME/Apps" && cd "$HOME/Apps"
gh repo clone tomochi3/24h
cd 24h
NTFY_TOPIC=ここに推測されにくいトピック名 bash mac/setup_server.sh
```

`mac/setup_server.sh` がやること:

- 電源アダプタ接続中はスリープしない（画面だけ10分で消灯）、停電から復帰したら自動で起動、フリーズ時に自動再起動
- macOS の自動アップデートで勝手に再起動しないようにする
- SSH（リモートログイン）を有効化 → 外から `ssh <ユーザー>@<MacのTailscale名>` でメンテできる
- 1時間ごとの監視（`mac/healthcheck.sh`）: 空き容量が20GB未満、サービス停止、バッテリー45℃以上で ntfy に通知（同じ警告は1日1回）

手動でやること（スクリプトの最後にも表示されます）:

- **バッテリー**: 「バッテリー充電の最適化」をオン。電源つなぎっぱなしは膨張しやすいので、ときどき底面のふくらみを確認してください
- **ふたは開けたまま**、風通しのよい場所に。画面ロック・消灯はOK
- **自動ログイン**: launchd の LaunchAgent はログイン後に動きます。FileVault がオンだと自動ログインできないので、停電・再起動のあとは一度ログインが必要です（Tailscale も同様）
- スマホの ntfy アプリで `NTFY_TOPIC` と同じトピックを購読

## 2. 卓球動画編集サーバー（ai_edit_TT）

手順は ai_edit_TT の README「初期化したMacBookを自宅サーバーにする」にまとまっています。要点だけ:

```bash
cd "$HOME/Apps/ai_edit_TT"
.venv/bin/python tools/smoke_video.py --output-dir /tmp/pingpong-smoke   # ffmpeg の確認
.venv/bin/python -m pingpong_editor install-service "$HOME/卓球動画"
.venv/bin/python -m pingpong_editor show-url "$HOME/卓球動画"
```

- ポートは 8765
- 256GBは動画ですぐ埋まります。healthcheck が20GBを切ったら通知するので、古い元動画を消すか外付けSSDに移してください
- 状態確認: `launchctl print "gui/$(id -u)/com.pingpong-editor.app"`、ログ: `tail -f ~/卓球動画/server.log`
