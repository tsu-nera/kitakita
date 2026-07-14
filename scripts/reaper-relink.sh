#!/usr/bin/env bash
# REAPER の出力ポートが BT sink から外れて無音になったとき張り直す。
# 原因: pipewire-jack 経由の REAPER は JACK クライアントで、BT 再接続や
# WirePlumber 再起動で sink ノードが作り直されるとリンクが消える（自動再接続の対象外）。
# 詳細は memory: reaper-jack-link-on-bt-reconnect
set -euo pipefail

# 既定 sink が BT でなくても、最初に見つかった bluez_output を対象にする
sink="$(pw-link -i | grep -m1 '^bluez_output\.' | sed 's/:playback_F[LR]$//')"
if [[ -z "${sink:-}" ]]; then
  echo "BT sink (bluez_output.*) が見つかりません。ヘッドホンの接続を確認してください。" >&2
  exit 1
fi

if ! pw-link -o | grep -q '^REAPER:out1$'; then
  echo "REAPER の出力ポートが見つかりません。REAPER が起動しているか確認してください。" >&2
  exit 1
fi

# 既に張られていてもエラーにしない（冪等）
pw-link "REAPER:out1" "${sink}:playback_FL" 2>/dev/null || true
pw-link "REAPER:out2" "${sink}:playback_FR" 2>/dev/null || true

echo "relinked: REAPER:out1/2 -> ${sink}:playback_FL/FR"
