# 24h_local — 使っていない MacBook を24時間サーバーにする

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

この MacBook は **Intel・macOS 12 Monterey（13 未満）** の前提です。この組み合わせでは Homebrew も Claude Code も使えないので、
ai_edit_TT の README の手順1〜4（Homebrew 前提）は使わず、下の「0-1」で全部入れます。

1. 下の「**0-1. 初期セットアップ**」（Python・pip・ffmpeg・gh・Codex・Tailscale・ai_edit_TT の取得まで）
2. このリポジトリで「Mac本体の常時稼働設定」（下の1）
3. ai_edit_TT の動作確認と `install-service`（下の2、ai_edit_TT README の手順6）

## 0-1. 初期セットアップ（Intel・macOS 12 で Homebrew を使わない）

### なぜ Homebrew を使わないか（調べた結果）

| ソフト | Intel・macOS 12 で | 根拠 |
|---|---|---|
| Homebrew | **実質使えない**。7.0（2026年9月）で Intel は Tier 3 になり、Intel 用のビルド済みパッケージが作られなくなった（全部ソースからビルド＝何時間もかかり失敗しやすい）。2027年9月以降は Intel で動かなくなる予定 | [Homebrew 7.0.0](https://brew.sh/2026/09/13/homebrew-7.0.0/)、[Support Tiers](https://docs.brew.sh/Support-Tiers) |
| Claude Code | **使えない**。macOS 13.0 以上 | [公式 System requirements](https://code.claude.com/docs/en/setup) |
| Codex CLI | 使える。公式は macOS 12 以上（Intel 版バイナリの最低 OS は 10.12） | [openai/codex docs/install.md](https://github.com/openai/codex/blob/main/docs/install.md) |
| Python | python.org の 3.12 インストーラーは macOS 10.13 以上 | CPython 3.12 の `Mac/BuildScript/resources/ReadMe.rtf` |
| GitHub CLI (gh) | 最新版（2.101 以降、Go 1.27）は macOS 13 以上。**2.100.0 までは macOS 12 で動く**（バイナリの最低 OS 12.0 を確認） | [Go 1.26 リリースノート](https://go.dev/doc/go1.26#darwin) |
| Tailscale | 最新版（1.104 以降、Go 1.27）は **macOS 13 以上**。**1.102.x までは macOS 12 で動く**（1.102.5 は Go 1.26 でビルド） | [Tailscale changelog](https://tailscale.com/changelog)、[Tailscale macOS](https://tailscale.com/docs/install/mac) |
| opencv-python-headless | 4.11 以降は macOS 13 以上用しかない。**macOS 12 で使えるのは 4.10.0.84 まで** | PyPI の wheel（`macosx_12_0_x86_64` は 4.10.0.84 が最後） |
| numpy | 最新版でも macOS 10.13 以上用の Intel 版あり | PyPI の wheel |

AI 判定は **Codex（ChatGPT の月額プラン）だけ**で動かします（ai_edit_TT は Codex か Claude の片方で動きます）。

Mac の「ターミナル」（アプリケーション → ユーティリティ）で、上から順に1ブロックずつ実行してください。

### ① macOS のバージョンを確認する

```bash
sw_vers -productVersion   # 12.x なら OK
uname -m                  # x86_64 なら Intel Mac
```

11 以下だと Tailscale と Codex が動かないので、システム環境設定 → ソフトウェアアップデート で 12 以上に上げてください。

### ② Apple のコマンドラインツール（git もここに入る）

```bash
xcode-select --install
```

ダイアログで「インストール」を押して完了まで待ちます。「すでにインストールされています」と出たら次へ。

```bash
git --version
```

### ③ 自分用のコマンド置き場を作る

gh・Codex・ffmpeg はここ（`~/.local/bin`）に置きます。sudo は不要です。

```bash
mkdir -p "$HOME/.local/bin"
grep -qxF 'export PATH="$HOME/.local/bin:$PATH"' ~/.zprofile 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zprofile
export PATH="$HOME/.local/bin:$PATH"
```

### ④ Python 3.12 を python.org から入れる

1. ブラウザで <https://www.python.org/downloads/macos/> を開く
2. **Python 3.12.x** の「**macOS 64-bit universal2 installer**」（.pkg）をダウンロードして、ダブルクリックでインストール
   （3.12 系でインストーラーがある一番新しいものを選ぶ。3.13 以降でも動くはずですが、ai_edit_TT は 3.12 で作られています）
3. インストール後に開く Finder で **Install Certificates.command** をダブルクリック（pip の SSL エラー対策）。
   閉じてしまった場合は次のコマンドで同じことができます

```bash
"/Applications/Python 3.12/Install Certificates.command"
```

確認:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 --version   # Python 3.12.x
```

### ⑤ pip は venv（仮想環境）の中で、ビルド済みだけを入れる

pip を使うときの決まりは2つです。

- **アプリのフォルダごとに `.venv` を作り、`.venv/bin/python -m pip ...` で入れる**（`sudo pip` はしない）
- **`--only-binary=:all:` を付ける**。付けないと、macOS 12 用がない新しい opencv（ソースのみ）を拾って何時間もビルドし、失敗します。付けると pip が macOS 12 で使える版（opencv 4.10.0.84）を自動で選びます

動作確認（あとで消してOK）:

```bash
mkdir -p "$HOME/Apps/piptest" && cd "$HOME/Apps/piptest"
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --only-binary=:all: numpy opencv-python-headless
.venv/bin/python -c "import numpy, cv2, platform; print('OK', numpy.__version__, cv2.__version__, platform.machine())"
```

`OK 2.x.x 4.10.0 x86_64` のように出れば pip は使える状態です。`rm -rf "$HOME/Apps/piptest"` で消せます。

### ⑥ ffmpeg（スコア表示用の `ass` 入り）

Homebrew の代わりに、Intel Mac 用の静的ビルド [evermeet.cx/ffmpeg](https://evermeet.cx/ffmpeg/) を使います（macOS 10.9 以上）。

1. ページから **ffmpeg** と **ffprobe** の zip（release 版）を両方ダウンロード
2. ダウンロードフォルダで両方を展開してから、次を実行

```bash
mv ~/Downloads/ffmpeg ~/Downloads/ffprobe "$HOME/.local/bin/"
xattr -d com.apple.quarantine "$HOME/.local/bin/ffmpeg" "$HOME/.local/bin/ffprobe" 2>/dev/null
chmod +x "$HOME/.local/bin/ffmpeg" "$HOME/.local/bin/ffprobe"
ffmpeg -version | head -1
ffmpeg -hide_banner -filters 2>/dev/null | grep -w ass
```

最後の行で `ass` の行が出れば OK です（evermeet 版に libass が入っていることはこの README を書いた時点では確認できていません。出なかったら知らせてください）。

### ⑦ GitHub CLI（gh 2.100.0。macOS 12 で動く最後の版）

```bash
cd /tmp && curl -fL -o gh.zip https://github.com/cli/cli/releases/download/v2.100.0/gh_2.100.0_macOS_amd64.zip
unzip -o -q gh.zip && mv gh_2.100.0_macOS_amd64/bin/gh "$HOME/.local/bin/" && rm -rf gh.zip gh_2.100.0_macOS_amd64
gh --version
```

```bash
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
```

`brew` や `gh upgrade` で新しい版に上げると macOS 13 以上が必要になって動かなくなるので、上げないでください。

### ⑧ Codex CLI

GitHub の公式リリースから Intel Mac 用を入れます。

```bash
cd /tmp && curl -fL -o codex.tgz https://github.com/openai/codex/releases/latest/download/codex-x86_64-apple-darwin.tar.gz
tar xzf codex.tgz && mv codex-x86_64-apple-darwin "$HOME/.local/bin/codex" && rm codex.tgz
codex --version
codex login
codex login status
```

ChatGPT の月額プランのアカウントでログインします。Codex を新しくするときは、このブロックをもう一度実行します。

### ⑨ Tailscale

公式サイトの「Download」や App Store から入る最新版は **macOS 13 以上専用**なので、macOS 12 では入りません（「このバージョンの macOS では使えません」と出る）。
macOS 12 で動く最後の版 **1.102.5** の Standalone 版を、バージョンを指定してダウンロードします。

```bash
cd /tmp && curl -fL -o Tailscale.pkg https://pkgs.tailscale.com/stable/Tailscale-1.102.5-macos.pkg
sudo installer -pkg Tailscale.pkg -target /
rm Tailscale.pkg
```

（`curl` が 404 で失敗したら、ブラウザで <https://pkgs.tailscale.com/stable/#macos> を開き、`Tailscale-1.102.x-macos.pkg` のうち一番新しいものをダウンロードしてダブルクリックで入れてください。1.104 以降は入りません。）

アプリケーションフォルダの Tailscale を開き、ログインと VPN（システム拡張）の許可をします。
「システム拡張がブロックされました」と出たら、システム環境設定 → セキュリティとプライバシー → 一般 で「許可」を押します。

Tailscale のメニュー（メニューバーのアイコン）→ Settings で **自動アップデートはオフ**にしておきます（macOS 12 のままでは新しい版は動かないため）。

スマホにも Tailscale を入れ、同じアカウントでログインしてください（スマホ側は最新版で問題ありません）。

### ⑩ ai_edit_TT を取得して、Python の部品を入れる

ai_edit_TT README の手順4の代わりに、次を使います（Homebrew の Python の代わりに python.org の Python、pip に `--only-binary=:all:`）。

```bash
mkdir -p "$HOME/Apps" "$HOME/卓球動画"
git clone https://github.com/tomochi3/ai_edit_TT.git "$HOME/Apps/ai_edit_TT"
cd "$HOME/Apps/ai_edit_TT"
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --only-binary=:all: -r requirements.txt
```

### ⑪ うまくいかないとき

| 症状 | 対処 |
|---|---|
| pip で `Building wheel for opencv...` が延々続く | `--only-binary=:all:` を付け忘れている。付けて入れ直す |
| `No matching distribution found` | そのライブラリに macOS 12・Intel 用のビルド済みがない。`--only-binary=:all:` のまま古い版を指定（例: `"opencv-python-headless<4.11"`） |
| `SSL: CERTIFICATE_VERIFY_FAILED` | ④の Install Certificates.command を実行 |
| `pip: command not found` | `pip` ではなく `.venv/bin/python -m pip` と書く |
| ffmpeg/gh/codex が「開発元を検証できない」で開けない | `xattr -d com.apple.quarantine "$HOME/.local/bin/<名前>"` |
| 新しいターミナルで `gh`・`codex`・`ffmpeg` が見つからない | ③の `~/.zprofile` 追記をやり直し、ターミナルを開き直す |
| Tailscale が「この Mac では使えない」「macOS 13 以降が必要」で入らない | 最新版（1.104 以降）を入れようとしている。⑨の手順で 1.102.5 を入れる |

## 1. Mac本体の常時稼働設定

```bash
mkdir -p "$HOME/Apps" && cd "$HOME/Apps"
gh repo clone tomochi3/24h_local 24h
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
- 古い動画の自動削除（同じく1時間ごと）: 空きが30GBを切ったら `~/卓球動画` の古い動画から順に消し、50GB空くまで続けます（下の「古い動画の自動削除」）

手動でやること（スクリプトの最後にも表示されます）:

- **バッテリー**: システム環境設定 → バッテリー → バッテリー → 「バッテリー充電の最適化」をオン。電源つなぎっぱなしは膨張しやすいので、ときどき底面のふくらみを確認してください
- **ふたは閉めてOK**。ただしふたを閉めるとキーボード面から放熱できないので、硬い面の上か縦置きスタンドで、布やクッションの上は避けてください。動画のAI処理中は特に熱くなるので、最初の数日は温度通知に注意
- ふたを閉めた状態で停電すると、バッテリーで動き続け、切れたら電源復帰時に自動起動します
- **自動ログイン**: システム環境設定 → ユーザとグループ → ログインオプション → 自動ログイン。launchd の LaunchAgent はログイン後に動きます。FileVault がオンだと自動ログインできないので、停電・再起動のあとは一度ログインが必要です（Tailscale も同様）
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
- `install-service` は登録したときの PATH を引き継ぐので、`which ffmpeg ffprobe codex` が全部表示されるターミナルで実行してください（Claude は使えないので Codex だけで判定します）
- 状態確認: `launchctl print "gui/$(id -u)/com.pingpong-editor.app"`、ログ: `tail -f ~/卓球動画/server.log`

## 3. 古い動画の自動削除

`mac/healthcheck.sh` が1時間ごとに空き容量を確認し、**空きが30GBを切ったら** `~/卓球動画` の中（サブフォルダも含む）の動画を **更新日時が古い順に** 消して、空きが50GBに戻るまで続けます。

- 対象は動画ファイルだけです（`.mp4` `.mov` `.m4v` `.mkv` `.avi` `.mts` `.webm`）。設定ファイルやログは消しません
- **3日以内に更新された動画は消しません**（転送中・編集中の動画を守るため）。開かれているファイルも飛ばします
- ゴミ箱には入れず、すぐに削除します（ゴミ箱だと容量が空かないため）。**消した動画は戻せません**
- 消したら ntfy に「何本・何GB消したか」を通知し、`~/.local/share/macserver/cleanup.log` に消したファイル名を残します
- 3日以内の動画しか残っておらず空きが足りないときは、警告を通知します
- 空き容量は `VIDEO_DIR` があるディスクで測ります（外付けSSDに置いた場合はそのSSDの空き）
- Mac は消した直後に空きが増えないことがあります（ローカルスナップショット）。消した分が空きに戻るまでの24時間は、その分を「空いた」とみなして追加では消しません

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
