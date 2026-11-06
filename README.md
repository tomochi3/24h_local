# 24h — 使っていない MacBook を24時間サーバーにする

MacBook（2018年・Intel・メモリ8GB・SSD 256GB）を家に置きっぱなしにして、**卓球動画編集サーバー**（[tomochi3/ai_edit_TT](https://github.com/tomochi3/ai_edit_TT)）を常時動かします。

| サービス | 何をする | スマホから |
|---|---|---|
| **卓球動画編集**（ai_edit_TT） | スマホから送った試合動画をAIでカット・得点判定し、スマホで選別・書き出し | `http://<Mac>:8765/?key=...` |

```
iPhone ──Tailscale(VPN)──▶ MacBook（ふた閉めOK・電源つなぎっぱなし）
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

1. 下の「**0-1. 初期セットアップ**」で macOS 更新・Homebrew・Python（pip）を入れる
2. ai_edit_TT の README「**初期化したMacBookを自宅サーバーにする**」の手順3〜5を実行
   （ffmpeg・gh・Tailscale・Codex・Claude のインストールとログインまで。手順1・2は0-1と同じなので済んでいればとばしてOK）
3. このリポジトリで「Mac本体の常時稼働設定」（下の1）
4. ai_edit_TT の `install-service`（下の2、ai_edit_TT README の手順6）

## 0-1. 初期セットアップ（2018年 Intel Mac で Python・pip を使えるようにする）

Mac の「ターミナル」（アプリケーション → ユーティリティ）で、上から順に1つずつ実行してください。
コマンドは1ブロックずつコピーして貼り付け、終わってから次へ進みます。

### ① macOS を更新する

アップルメニュー → システム設定 → 一般 → ソフトウェアアップデート で、出てくる最新版まで上げます。
2018年モデルで入れられる最新は **MacBook Pro なら macOS 15 Sequoia、MacBook Air なら macOS 14 Sonoma** です。
（Tailscale は macOS 13 以降が必要です）

確認:

```bash
sw_vers -productVersion   # 13 以上なら OK
uname -m                  # x86_64 と出れば Intel Mac
```

### ② Apple のコマンドラインツールを入れる

```bash
xcode-select --install
```

ダイアログで「インストール」を押して完了まで待ちます（数分〜20分）。「すでにインストールされています」と出たら次へ。Xcode 本体は不要です。

### ③ Homebrew を入れる

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

途中で Mac のログインパスワード（入力しても画面には出ません）と Return キーを求められます。
終わったら、Intel Mac 用のパス設定をします（Intel Mac の Homebrew は `/usr/local` に入ります。`/opt/homebrew` は Apple シリコン用なので使いません）。

```bash
eval "$(/usr/local/bin/brew shellenv)"
```

```bash
grep -qxF 'eval "$(/usr/local/bin/brew shellenv)"' ~/.zprofile 2>/dev/null || echo 'eval "$(/usr/local/bin/brew shellenv)"' >> ~/.zprofile
```

```bash
brew --version
```

### ④ Python 3.12 を入れる

```bash
brew install python@3.12
```

> Intel Mac は Homebrew のサポートが一段下がっていて（Tier 3）、ビルド済みのパッケージがないとソースからのビルドになり、**30分以上かかる・失敗する**ことがあります。
> 失敗したら、代わりに [python.org の macOS 用インストーラー](https://www.python.org/downloads/macos/)（Python 3.12 の「macOS 64-bit universal2 installer」）を入れてください。
> その場合は、インストール後に Finder で アプリケーション → Python 3.12 → **Install Certificates.command** をダブルクリックし（pip の SSL エラー対策）、以下の `PY=` を次の行に読み替えます。
> `PY=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12`

使う Python の場所を確認します。

```bash
PY="$(brew --prefix python@3.12)/bin/python3.12"
"$PY" --version   # Python 3.12.x と出れば OK
```

### ⑤ pip は「venv（仮想環境）」の中で使う

Homebrew の Python に直接 `pip install` すると、次のエラーで止まります。**これは正常な動作**です。

```
error: externally-managed-environment
```

`sudo pip` や `--break-system-packages` で無理に入れると、Homebrew の Python が壊れて後で困るので使いません。
代わりにアプリのフォルダごとに venv を作り、その中の pip を使います（ai_edit_TT の `.venv` もこの方式です）。

```bash
mkdir -p "$HOME/Apps/pytest-venv" && cd "$HOME/Apps/pytest-venv"
```

```bash
"$PY" -m venv .venv
```

```bash
.venv/bin/python -m pip install --upgrade pip
```

```bash
.venv/bin/python -m pip install numpy
.venv/bin/python -c "import numpy, platform; print('OK', numpy.__version__, platform.machine())"
```

`OK 2.x.x x86_64` のように出れば、pip が使える状態です。確認用フォルダは消して構いません: `rm -rf "$HOME/Apps/pytest-venv"`

ポイント:

- `pip` ではなく **`.venv/bin/python -m pip ...`** と書くと、どの Python に入るか迷いません（`pip: command not found` も起きません）
- いちいち `.venv/bin/` を付けたくないときは `source .venv/bin/activate`（やめるときは `deactivate`）
- macOS 標準の `/usr/bin/python3`（3.9）は古いので使いません。`which python3` が `/usr/bin/python3` を指していても、上のように `$PY` やフルパスで指定していれば問題ありません

### ⑥ うまくいかないとき

| 症状 | 対処 |
|---|---|
| `externally-managed-environment` | ⑤のとおり venv の中の pip を使う |
| `pip: command not found` / `pip3` が古い Python に入る | `.venv/bin/python -m pip` の形で実行する |
| `SSL: CERTIFICATE_VERIFY_FAILED` | python.org 版なら `Install Certificates.command` を実行。Homebrew 版なら `brew reinstall ca-certificates python@3.12` |
| `Building wheel for ...` が延々と続く・`clang` のエラー | ビルド済み（Intel 用 wheel）がない版を拾っている。まず `.venv/bin/python -m pip install --upgrade pip` してから再実行。それでもだめなら `xcode-select --install` 済みか確認 |
| `No matching distribution found`（例: 新しい PyTorch） | そのライブラリが Intel Mac 向けの配布をやめている。古い版を指定するか、Linux/クラウド側で動かす |
| `brew install` が途中で失敗 | ④の python.org インストーラーに切り替える |
| 新しいターミナルで `brew: command not found` | ③の `~/.zprofile` への追記をやり直し、ターミナルを開き直す |

## 1. Mac本体の常時稼働設定

```bash
mkdir -p "$HOME/Apps" && cd "$HOME/Apps"
gh repo clone tomochi3/24h
cd 24h
NTFY_TOPIC=ここに推測されにくいトピック名 bash mac/setup_server.sh
```

`mac/setup_server.sh` がやること:

- 電源アダプタ接続中はスリープしない（画面だけ10分で消灯）、停電から復帰したら自動で起動、フリーズ時に自動再起動
- **ふたを閉めたままでも動く**（`pmset -a disablesleep 1`。外部ディスプレイ・キーボード不要）。
  元に戻すときは `LID_CLOSED=0 bash mac/setup_server.sh`
- macOS の自動アップデートで勝手に再起動しないようにする
- SSH（リモートログイン）を有効化 → 外から `ssh <ユーザー>@<MacのTailscale名>` でメンテできる
- 1時間ごとの監視（`mac/healthcheck.sh`）: 空き容量が20GB未満、サービス停止、バッテリー45℃以上、ふた閉め設定が外れた（macOS アップデート後など）ときに ntfy に通知（同じ警告は1日1回）

手動でやること（スクリプトの最後にも表示されます）:

- **バッテリー**: 「バッテリー充電の最適化」をオン。電源つなぎっぱなしは膨張しやすいので、ときどき底面のふくらみを確認してください
- **ふたは閉めてOK**。ただしふたを閉めるとキーボード面から放熱できないので、硬い面の上か縦置きスタンドで、布やクッションの上は避けてください。動画のAI処理中は特に熱くなるので、最初の数日は温度通知に注意
- ふたを閉めた状態で停電すると、バッテリーで動き続け、切れたら電源復帰時に自動起動します
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
