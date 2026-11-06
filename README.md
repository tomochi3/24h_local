# 24h_local — 使っていない MacBook を24時間サーバーにする

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

## 0. 初期化した Mac に必要なものを入れる

初期化直後の macOS には `pip` も `python3`（まともに使えるもの）も入っていません。ターミナルで上から順に実行してください。
git が入っていれば手順0-1は済んでいます。

### 0-1. Xcode コマンドラインツール（git・コンパイラ）

```bash
xcode-select -p || xcode-select --install
```

パスが表示されれば入っています。ダイアログが出たら「インストール」を押し、終わってから次へ。

### 0-2. Homebrew（ほかのソフトを入れる道具）

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

途中で Mac のログインパスワードと Enter を求められます。終わったら、次のターミナルでも `brew` が使えるように登録します（Intel Mac は `/usr/local`、Apple シリコンは `/opt/homebrew`）:

```bash
BREW=$(ls /opt/homebrew/bin/brew /usr/local/bin/brew 2>/dev/null | head -1); echo "eval \"\$($BREW shellenv)\"" >> ~/.zprofile; eval "$($BREW shellenv)"; brew --version
```

### 0-3. Python（pip 付き）・ffmpeg・gh

```bash
brew install python@3.13 ffmpeg gh
```

```bash
python3.13 --version && python3.13 -m pip --version && ffmpeg -version | head -1 && gh --version | head -1
```

- Homebrew の Python では、コマンド名は `pip` ではなく **`pip3`**（または `python3.13 -m pip`）です
- Homebrew の Python に直接 `pip install` するとエラー（externally-managed-environment）になります。ai_edit_TT は下の 0-6 で作る仮想環境（`.venv`）に入れてください

### 0-4. Tailscale・Codex・Claude Code

```bash
brew install --cask tailscale-app codex claude-code
```

`tailscale-app` が見つからないと言われたら、App Store で「Tailscale」を入れてください。

### 0-5. ログイン

```bash
gh auth login
```

「GitHub.com」→「HTTPS」→「Login with a web browser」を選び、表示されたコードをブラウザに入力します。

```bash
codex login
```

```bash
claude
```

Claude Code は起動すると最初にログインを聞かれます。月額プランのアカウントでログインしたら `/exit` で終了。
Tailscale はアプリケーションフォルダから起動してログインし、スマホにも同じアカウントで Tailscale を入れます。

### 0-6. リポジトリを取ってくる・ai_edit_TT の Python 環境を作る

```bash
mkdir -p "$HOME/Apps" && cd "$HOME/Apps" && gh repo clone tomochi3/24h_local && gh repo clone tomochi3/ai_edit_TT
```

```bash
cd "$HOME/Apps/ai_edit_TT" && python3.13 -m venv .venv && .venv/bin/python -m pip install --upgrade pip
```

この後の依存パッケージのインストールは ai_edit_TT の README のとおりに進めます。そこに `pip install ...` と書いてあれば、**`.venv/bin/python -m pip install ...`** に読み替えてください（`source .venv/bin/activate` してからなら `pip` のままで動きます）。

### 全体の順番

1. 上の 0-1〜0-6
2. このリポジトリで「Mac本体の常時稼働設定」（下の1）
3. ai_edit_TT の `install-service`（下の2、ai_edit_TT README の手順6）

## 1. Mac本体の常時稼働設定

```bash
cd "$HOME/Apps/24h_local"
NTFY_TOPIC=ここに推測されにくいトピック名 bash mac/setup_server.sh
```

`mac/setup_server.sh` がやること:

- 電源アダプタ接続中はスリープしない（画面だけ10分で消灯）、停電から復帰したら自動で起動、フリーズ時に自動再起動
- macOS の自動アップデートで勝手に再起動しないようにする
- SSH（リモートログイン）を有効化 → 外から `ssh <ユーザー>@<MacのTailscale名>` でメンテできる
- 1時間ごとの監視（`mac/healthcheck.sh`）: 空き容量が20GB未満、サービス停止、バッテリー45℃以上で ntfy に通知（同じ警告は1日1回）
- 古い動画の自動削除（同じく1時間ごと）: 空きが30GBを切ったら `~/卓球動画` の古い動画から順に消し、50GB空くまで続けます（下の「古い動画の自動削除」）

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
- 256GBは動画ですぐ埋まるので、古い動画は自動で消えます（下の「古い動画の自動削除」）。残したい動画はスマホに書き出すか外付けSSDに移してください
- 状態確認: `launchctl print "gui/$(id -u)/com.pingpong-editor.app"`、ログ: `tail -f ~/卓球動画/server.log`

## 3. 古い動画の自動削除

`mac/healthcheck.sh` が1時間ごとに空き容量を確認し、**空きが30GBを切ったら** `~/卓球動画` の中（サブフォルダも含む）の動画を **更新日時が古い順に** 消して、空きが50GBに戻るまで続けます。

- 対象は動画ファイルだけです（`.mp4` `.mov` `.m4v` `.mkv` `.avi` `.mts` `.webm`）。設定ファイルやログは消しません
- **3日以内に更新された動画は消しません**（転送中・編集中の動画を守るため）。開かれているファイルも飛ばします
- ゴミ箱には入れず、すぐに削除します（ゴミ箱だと容量が空かないため）。**消した動画は戻せません**
- 消したら ntfy に「何本・何GB消したか」を通知し、`~/.local/share/macserver/cleanup.log` に消したファイル名を残します
- 3日以内の動画しか残っておらず空きが足りないときは、警告を通知します

設定は `mac/setup_server.sh` を実行するときに変えられます（もう一度実行すれば上書きされます）:

```bash
NTFY_TOPIC=トピック名 CLEANUP_FREE_GB=40 CLEANUP_TARGET_GB=70 CLEANUP_MIN_AGE_DAYS=7 bash mac/setup_server.sh
```

| 変数 | 既定値 | 意味 |
|---|---|---|
| `VIDEO_DIR` | `~/卓球動画` | 自動削除の対象フォルダ |
| `CLEANUP_FREE_GB` | 30 | 空きがこれを下回ったら削除を始める |
| `CLEANUP_TARGET_GB` | 50 | 空きがこれに戻るまで消す |
| `CLEANUP_MIN_AGE_DAYS` | 3 | これより新しい動画は消さない |
| `CLEANUP` | 1 | `0` にすると自動削除しない |

> 消えた動画の試合は ai_edit_TT から開けなくなります。残したい試合は早めに書き出してください。書き出した動画も `~/卓球動画` の中にあれば削除の対象です。
