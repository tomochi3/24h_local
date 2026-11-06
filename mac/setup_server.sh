#!/bin/bash
# MacBook を24時間稼働サーバーにするための「本体側」の設定。
# 何度実行しても同じ結果になります。途中で管理者パスワードを聞かれます。
#   bash mac/setup_server.sh                # 電源設定・容量監視
#   NTFY_TOPIC=xxxx bash mac/setup_server.sh  # 容量が減ったらスマホに通知
#   LID_CLOSED=0 bash mac/setup_server.sh     # ふたを閉じたら普通にスリープする設定に戻す
#   CLEANUP=0 NTFY_TOPIC=xxxx bash mac/setup_server.sh  # 古い動画の自動削除をしない
set -euo pipefail
[ "$(uname)" = "Darwin" ] || { echo "macOS で実行してください"; exit 1; }
REPO="$(cd "$(dirname "$0")/.." && pwd)"

echo "== 1. 電源設定（電源アダプタ接続中: スリープしない・停電復帰で自動起動） =="
sudo pmset -c sleep 0 disksleep 0 displaysleep 10 powernap 0 womp 1 tcpkeepalive 1
sudo pmset -a autorestart 1 2>/dev/null || echo "  (この機種は autorestart 非対応)"
sudo systemsetup -setrestartfreeze on >/dev/null 2>&1 || true
pmset -g custom | sed -n '/AC Power/,$p' | head -20

echo "== 1b. ふたを閉めたままでも動かす（外部ディスプレイなし） =="
LID_CLOSED="${LID_CLOSED:-1}"
if [ "$LID_CLOSED" = 1 ]; then
  # ふたを閉じてもスリープしない（停電でバッテリー駆動になっても動き続け、切れたら autorestart で復帰）
  sudo pmset -a disablesleep 1
  echo "  ふたを閉じてもスリープしません（画面はふたを閉じると消えます）"
else
  sudo pmset -a disablesleep 0
  echo "  ふたを閉じたら通常どおりスリープします"
fi
pmset -g | grep -i SleepDisabled || true

echo "== 2. 自動アップデートでの勝手な再起動を防ぐ（セキュリティ更新のダウンロードは継続） =="
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticallyInstallMacOSUpdates -bool false

echo "== 3. リモートログイン（SSH。Tailscale 経由でメンテ用） =="
if sudo systemsetup -setremotelogin on >/dev/null 2>&1; then
  echo "  SSH を有効にしました"
else
  echo "  自動で有効にできませんでした。システム環境設定 → 共有 → リモートログイン をオンにしてください（macOS 13 以降は システム設定 → 一般 → 共有）"
fi

echo "== 4. 容量・稼働監視と古い動画の自動削除（1時間ごと） =="
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.local/share/macserver"
PLIST="$HOME/Library/LaunchAgents/com.macserver.healthcheck.plist"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.macserver.healthcheck</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$REPO/mac/healthcheck.sh</string></array>
  <key>EnvironmentVariables</key><dict>
    <key>NTFY_TOPIC</key><string>${NTFY_TOPIC:-}</string>
    <key>LID_CLOSED</key><string>$LID_CLOSED</string>
    <key>VIDEO_DIR</key><string>${VIDEO_DIR:-$HOME/卓球動画}</string>
    <key>CLEANUP</key><string>${CLEANUP:-1}</string>
    <key>CLEANUP_FREE_GB</key><string>${CLEANUP_FREE_GB:-30}</string>
    <key>CLEANUP_TARGET_GB</key><string>${CLEANUP_TARGET_GB:-50}</string>
    <key>CLEANUP_MIN_AGE_DAYS</key><string>${CLEANUP_MIN_AGE_DAYS:-3}</string>
  </dict>
  <key>StartInterval</key><integer>3600</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$HOME/.local/share/macserver/healthcheck.log</string>
  <key>StandardErrorPath</key><string>$HOME/.local/share/macserver/healthcheck.log</string>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/com.macserver.healthcheck" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "  登録しました: $PLIST"

cat <<'MSG'

== 手動で確認・設定すること ==
 - システム環境設定 → バッテリー → バッテリー → 「バッテリー充電の最適化」をオン（常時充電による膨張対策）
 - システム環境設定 → ユーザとグループ → ログインオプション → 自動ログイン（FileVault オンだと選べません。
   その場合は停電・再起動のあとに一度ログインが必要です）
 - ふたを閉めて置く場合: 布団・クッションの上や棚の奥は避け、硬い面の上か縦置きスタンドで。
   ふたを閉めるとキーボード面から放熱できず熱がこもりやすいので、最初の数日は ntfy の温度通知に注意
 - Tailscale にログインし、スマホにも同じアカウントで Tailscale を入れる
MSG
