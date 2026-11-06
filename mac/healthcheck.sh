#!/bin/bash
# 1時間ごとに launchd から呼ばれる。空き容量が少ない・バッテリーが熱い・サービスが止まっている時に ntfy で通知。
# 同じ警告は1日1回まで。
MIN_FREE_GB="${MIN_FREE_GB:-20}"
STATE="$HOME/.local/share/macserver"
mkdir -p "$STATE"
alerts=()

free_gb=$(df -g / | awk 'NR==2 {print $4}')
[ "${free_gb:-0}" -lt "$MIN_FREE_GB" ] && alerts+=("空き容量が ${free_gb}GB です")

for label in com.pingpong-editor.app; do
  if [ -f "$HOME/Library/LaunchAgents/$label.plist" ] && \
     ! launchctl print "gui/$(id -u)/$label" 2>/dev/null | grep -q "state = running"; then
    alerts+=("$label が動いていません")
  fi
done

# ふた閉め運用なのに macOS アップデート等で disablesleep が戻っていたら、閉じた瞬間にスリープしてしまう
if [ "${LID_CLOSED:-0}" = 1 ] && ! pmset -g | grep -Eq 'SleepDisabled[[:space:]]+1'; then
  alerts+=("ふた閉め設定が外れています（sudo pmset -a disablesleep 1）")
fi

temp=$(ioreg -r -n AppleSmartBattery 2>/dev/null | awk -F'= ' '/"Temperature" =/ {print int($2/100); exit}')
[ -n "$temp" ] && [ "$temp" -ge 45 ] && alerts+=("バッテリー温度が ${temp}℃ です")

echo "$(date '+%F %T') free=${free_gb}GB temp=${temp:-?}C alerts=${#alerts[@]}"
[ ${#alerts[@]} -eq 0 ] && exit 0
[ -z "$NTFY_TOPIC" ] && { printf '  %s\n' "${alerts[@]}"; exit 0; }

msg=$(printf '%s\n' "${alerts[@]}")
key="$STATE/alert-$(date +%F)-$(printf '%s' "$msg" | shasum | cut -c1-8)"
[ -e "$key" ] && exit 0
curl -fsS -H "Title: MacBookサーバー" -H "Tags: warning" -d "$msg" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null && touch "$key"
