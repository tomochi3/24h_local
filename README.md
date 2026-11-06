# 24h — 使っていない MacBook を24時間サーバーにする

MacBook（2018年・Intel・メモリ8GB・SSD 256GB）を家に置きっぱなしにして、次の2つを常時動かします。

| サービス | 何をする | いつ動く | スマホから |
|---|---|---|---|
| ① **xdigest**（このリポジトリ） | X の指定アカウント（岡野原大輔さんなど）の投稿を集め、原文のままPDFにする | 毎朝7:00に1回（数分） | `http://<Mac>:8766` でPDF一覧・ntfy通知 |
| ② **卓球動画編集**（[tomochi3/ai_edit_TT](https://github.com/tomochi3/ai_edit_TT)） | スマホから送った試合動画をAIでカット・得点判定し、スマホで選別・書き出し | 常時待機、動画が来たら処理 | `http://<Mac>:8765/?key=...` |

```
iPhone ──Tailscale(VPN)──▶ MacBook（ふた開け・電源つなぎっぱなし）
                            ├─ launchd: com.pingpong-editor.app  :8765  ← ai_edit_TT
                            ├─ launchd: com.xdigest.run   毎朝7:00 → X API → PDF
                            ├─ launchd: com.xdigest.serve :8766  ← PDF閲覧
                            └─ launchd: com.macserver.healthcheck 1時間ごと（容量・停止・温度 → ntfy）
```

- 卓球動画のAI判定は **Codex / Claude Code の月額プランのログイン** を使います（ai_edit_TT の方針）。xdigest はAIを使いません。
- 料金が別にかかるのは **X API だけ**（従量課金、後述）。
- 外から使うときは Tailscale のみ。ルーターのポート開放はしません。
- 8GBメモリでも2つ同時に問題なく動きます。重いのは ai_edit_TT の動画書き出しだけで、xdigest は1日1回数分です。

---

## 0. 全体の順番

1. macOS を更新し、ai_edit_TT の README「**初期化したMacBookを自宅サーバーにする**」の手順1〜5を実行
   （Homebrew・Python・ffmpeg・gh・Tailscale・Codex・Claude のインストールとログインまで。②の準備も兼ねます）
2. このリポジトリで「Mac本体の常時稼働設定」（下の1）
3. ② ai_edit_TT の `install-service`（ai_edit_TT README の手順6）
4. ① xdigest の設定と登録（下の2）

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

## 2. ① X ダイジェスト PDF（xdigest）

### 2-1. X API の準備（初回だけ）

X の投稿を安定して読むには公式APIが必要です（スクレイピングは規約違反・アカウント凍結のリスクがあり、すぐ壊れます）。

1. <https://developer.x.com> でアプリを作成
2. Developer Console で **クレジットを購入**（2026年は従量課金が標準）。使いすぎ防止に上限額も設定
3. アプリの **Bearer Token** をコピーし、MacBook に保存:

```bash
mkdir -p ~/.config/xdigest && chmod 700 ~/.config/xdigest
pbpaste > ~/.config/xdigest/x_bearer_token && chmod 600 ~/.config/xdigest/x_bearer_token
```

**料金の目安**: 他人の投稿は1件あたり約 $0.005 で、返ってきた件数に課金されます。
5アカウント × 1日10投稿 なら 月 1,500件 ≈ **$7.5/月**。
xdigest は前回の続き（`since_id`）からだけ取得し、ユーザーIDも初回だけ調べて保存するので、同じ投稿に二重に払いません。
`max_posts_per_account`（既定40）が1回あたりの上限です。実行ログに概算額が出ます。単価は変わることがあるので Developer Console で確認してください。

### 2-2. インストール

```bash
cd "$HOME/Apps/24h"
brew install pango                     # PDF作成（WeasyPrint）に必要
"$(brew --prefix python@3.12)/bin/python3.12" -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.example.toml ~/.config/xdigest/config.toml
open -e ~/.config/xdigest/config.toml   # accounts に読みたいアカウントを書く
```

`config.toml` の主な項目:

| 項目 | 既定 | 説明 |
|---|---|---|
| `accounts` | `["hillbig"]` | @なしのユーザー名 |
| `run_hour` / `run_minute` | 7 / 0 | 毎日作る時刻 |
| `include_replies` / `include_retweets` | false | 返信・リポストも入れるか |
| `max_posts_per_account` | 40 | 1回あたりの上限（＝料金の上限） |
| `ntfy_topic` | 空 | できたらスマホに通知 |
| `public_url` | 空 | 通知のリンク先。例 `http://macbook:8766`（Tailscale名） |

### 2-3. 試しに1回作る → 自動化

```bash
cd "$HOME/Apps/24h"
.venv/bin/python -m xdigest run            # ~/XDigest/pdf/2026-11-07_0700.pdf ができる
open ~/XDigest/pdf
.venv/bin/python -m xdigest install        # 毎朝の実行と閲覧サーバーを launchd に登録
```

表示された `http://<Mac名>:8766/?key=...` をスマホの Safari で開き、「ホーム画面に追加」しておくと便利です。
外出先では、ホスト部分を Tailscale の名前か `100.x.x.x` に置き換えます。

PDFの中身（A5サイズ・スマホで読みやすい大きさ）:

1. **アカウント一覧**（各件数）
2. **アカウントごとの投稿（原文のまま・時系列）** — 本文（長文ポストも全文・短縮URLは元に戻す）、画像、引用ポスト、♥/RT数、「Xで開く」リンク

### 2-4. 管理

```bash
cd "$HOME/Apps/24h"
.venv/bin/python -m xdigest url                  # スマホ用URLを再表示
tail -n 50 ~/XDigest/run.log                     # 毎朝の実行ログ
launchctl kickstart "gui/$(id -u)/com.xdigest.run"   # 今すぐ実行（スケジュールとは別に）
.venv/bin/python -m xdigest uninstall            # 登録解除（PDFは残る）
git pull && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m xdigest install   # 更新
```

- Mac がスリープ・電源オフで7:00を逃した場合は、次に起きたときに1回実行されます。
- 新しい投稿が0件の日はPDFを作りません（`skip_empty = false` で毎日作る）。

## 3. ② 卓球動画編集サーバー（ai_edit_TT）

手順は ai_edit_TT の README「初期化したMacBookを自宅サーバーにする」にまとまっています。要点だけ:

```bash
cd "$HOME/Apps/ai_edit_TT"
.venv/bin/python tools/smoke_video.py --output-dir /tmp/pingpong-smoke   # ffmpeg の確認
.venv/bin/python -m pingpong_editor install-service "$HOME/卓球動画"
.venv/bin/python -m pingpong_editor show-url "$HOME/卓球動画"
```

- ポートは 8765（xdigest は 8766 なのでぶつかりません）
- 256GBは動画ですぐ埋まります。healthcheck が20GBを切ったら通知するので、古い元動画を消すか外付けSSDに移してください
- 状態確認: `launchctl print "gui/$(id -u)/com.pingpong-editor.app"`、ログ: `tail -f ~/卓球動画/server.log`

## 開発

```bash
python -m pip install -r requirements.txt pytest
python -m pytest -q
```

X API と AI CLI はテストでは偽物に置き換えているので、トークンなしで実行できます。
