#!/bin/bash
# 1時間ごとに launchd から呼ばれる。
#  1. 空き容量が CLEANUP_FREE_GB を切ったら、VIDEO_DIR の古い動画から順に消して CLEANUP_TARGET_GB まで空ける
#  2. 空き容量が少ない・バッテリーが熱い・サービスが止まっている時に ntfy で通知（同じ警告は1日1回まで）
MIN_FREE_GB="${MIN_FREE_GB:-20}"            # これを下回ったら警告
VIDEO_DIR="${VIDEO_DIR:-$HOME/卓球動画}"     # 自動削除の対象フォルダ（中のサブフォルダも含む）
CLEANUP="${CLEANUP:-1}"                     # 0 にすると自動削除しない
CLEANUP_FREE_GB="${CLEANUP_FREE_GB:-30}"    # 空きがこれを下回ったら削除を始める
CLEANUP_TARGET_GB="${CLEANUP_TARGET_GB:-50}" # 空きがこれに戻るまで古い順に消す
CLEANUP_MIN_AGE_DAYS="${CLEANUP_MIN_AGE_DAYS:-3}" # これより新しい動画は消さない（転送中・編集中を守る）
STATE="$HOME/.local/share/macserver"
mkdir -p "$STATE"
alerts=()
notes=()

# 指定したパスがあるディスクの空き容量（KB）
free_kb() { df -k "${1:-/}" | awk 'NR==2 {print $4}'; }

# ファイルの「最終更新時刻<TAB>サイズ<TAB>パス」を出す（macOS / Linux 両対応）
list_videos() {
  find "$VIDEO_DIR" -type f \
    \( -iname '*.mp4' -o -iname '*.mov' -o -iname '*.m4v' -o -iname '*.mkv' \
       -o -iname '*.avi' -o -iname '*.mts' -o -iname '*.webm' \) \
    -mtime +"$CLEANUP_MIN_AGE_DAYS" -print0 |
  if stat -f '%m' / >/dev/null 2>&1; then
    xargs -0 stat -f $'%m\t%z\t%N'
  else
    xargs -0 stat -c $'%Y\t%s\t%n'
  fi
}

# 前回までに消したのに、まだ空きとして戻ってきていない量（KB）。
# macOS はローカルスナップショットのせいで消してもすぐ空きが増えないことがあるため、
# これを空きとみなして、毎時間同じ不足分を何度も消してしまうのを防ぐ。24時間たったら忘れる。
PENDING="$STATE/cleanup.pending"   # 中身: 記録した時刻(epoch) 記録時の空き(KB) 未回収の量(KB)
pending_kb() {
  local now=$(date +%s) at=0 free_then=0 pending=0 gained
  [ -f "$PENDING" ] && read -r at free_then pending < "$PENDING"
  if [ $((now - ${at:-0})) -ge 86400 ]; then echo 0; return; fi
  gained=$(( $1 - free_then ))
  [ "$gained" -gt 0 ] && pending=$((pending - gained))
  [ "$pending" -lt 0 ] && pending=0
  echo "$pending"
}

cleanup_videos() {
  [ "$CLEANUP" = "1" ] && [ -d "$VIDEO_DIR" ] || return 0
  local start_kb pending want_kb free n=0 freed=0 mtime size path
  # 動画フォルダがあるディスクで測る（外付けSSDに置いた場合も正しく判断する）
  start_kb=$(free_kb "$VIDEO_DIR")
  pending=$(pending_kb "$start_kb")
  [ $((start_kb + pending)) -ge $((CLEANUP_FREE_GB * 1024 * 1024)) ] && return 0
  want_kb=$((CLEANUP_TARGET_GB * 1024 * 1024))
  free=$start_kb
  while IFS=$'\t' read -r mtime size path; do
    # 空きが戻ったら終了。空きがすぐ増えなくても、消した量（前回までの未回収分を含む）が足りた時点で止める
    [ "$free" -ge "$want_kb" ] && break
    [ $((start_kb + pending + freed)) -ge "$want_kb" ] && break
    [ -f "$path" ] || continue
    # 開かれている（書き込み中・再生中の）ファイルは飛ばす
    if command -v lsof >/dev/null && lsof -- "$path" >/dev/null 2>&1; then continue; fi
    rm -f -- "$path" || continue
    echo "$(date '+%F %T') deleted ${path} ($((size / 1024 / 1024))MB)" >> "$STATE/cleanup.log"
    n=$((n + 1)); freed=$((freed + size / 1024))
    free=$(free_kb "$VIDEO_DIR")
  done < <(list_videos 2>/dev/null | sort -n)
  if [ "$n" -gt 0 ]; then
    local unreclaimed=$((pending + freed - (free - start_kb)))
    [ "$unreclaimed" -lt 0 ] && unreclaimed=0
    echo "$(date +%s) $free $unreclaimed" > "$PENDING"
    notes+=("古い動画を${n}本（$((freed / 1024 / 1024))GB分）消しました。空きは $((free / 1024 / 1024))GB です（記録: $STATE/cleanup.log）")
  fi
  [ "$free" -lt "$want_kb" ] && [ $((start_kb + pending + freed)) -lt "$want_kb" ] && \
    alerts+=("古い動画を消しても空きが $((free / 1024 / 1024))GB しかありません（${CLEANUP_MIN_AGE_DAYS}日以内の動画と開いている動画は残しています）")
}

cleanup_videos

free_gb=$(( $(free_kb) / 1024 / 1024 ))
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

echo "$(date '+%F %T') free=${free_gb}GB temp=${temp:-?}C alerts=${#alerts[@]} notes=${#notes[@]}"
[ ${#alerts[@]} -eq 0 ] && [ ${#notes[@]} -eq 0 ] && exit 0
[ -z "$NTFY_TOPIC" ] && { printf '  %s\n' "${notes[@]}" "${alerts[@]}"; exit 0; }

# 削除したお知らせは毎回送る（同じ内容にはならない）
if [ ${#notes[@]} -gt 0 ]; then
  curl -fsS -H "Title: MacBookサーバー" -H "Tags: wastebasket" -d "$(printf '%s\n' "${notes[@]}")" \
    "https://ntfy.sh/$NTFY_TOPIC" >/dev/null
fi
[ ${#alerts[@]} -eq 0 ] && exit 0
msg=$(printf '%s\n' "${alerts[@]}")
key="$STATE/alert-$(date +%F)-$(printf '%s' "$msg" | shasum | cut -c1-8)"
[ -e "$key" ] && exit 0
curl -fsS -H "Title: MacBookサーバー" -H "Tags: warning" -d "$msg" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null && touch "$key"
