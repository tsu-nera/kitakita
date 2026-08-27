"""REAPER 実レンダ（Path A, #31）。sim ではなく REAPER 自身に計測用の音源を焼かせる。

背景: `kita check` の sim は「耳を持たない agent がミックスを検証する」ための正本を
オフラインで再構成する設計だったが、ReaSynth のレンダが通る（FFT 支配周波数が期待値と
一致、stems の和が master と -90dB 台で一致）ことを実測で確認できたため、正本を
「sim による再構成」から「REAPER 自身のレンダを計測する」へ移す（ADR-002）。

最大の落とし穴はダイアログ: レンダ中に REAPER がダイアログを出すと reapy API ごと
無応答になり、タイムアウトが無く無期限に待つ。モーダル中は `reapy.connect()` すら
返らない。内側(reapy)からは復旧できない — 復旧できるのはウィンドウ操作だけ。

対策は2層。
  層1 予防: ダイアログが出る条件を構造的に潰す
    - レンダ前に出力先の既存 wav を消す → 上書き確認が原理的に出ない
    - アクションは 42230 (auto-close) を使う。41824 は auto-close ではなく
      進捗ダイアログが残る
  層2 番犬: それでも出たら外側から閉じる
    - reapy 呼び出し (Main_OnCommand) は別スレッドへ投げ、メインスレッドは niri へ
      問い合わせる（コンポジタは REAPER の応答性と無関係に生きている）
    - REAPER のメイン窓でない窓が一定時間居座ったらダイアログとみなし
      `niri msg action close-window` で閉じる。**この経路は reapy を使わない** —
      reapy 越しに閉じようとすると、固まっている当の API を叩くことになり
      番犬自身も一緒に固まる（実際に踏んだ）
    - タイムアウトしたら「詰まった」ではなく明示的な失敗として返す

層2は「詰まらせない」ための保険で、成功させるのは層1。閉じられたダイアログの
レンダは中断されるので、番犬が発火した時点でその回は失敗として扱う。
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

from reapy import reascript_api as RPR

RENDER_AUTOCLOSE = 42230  # 41824 は auto-close ではない(進捗ダイアログが残る)
MAIN_WINDOW_MARK = " - REAPER v"

# レンダ中に出て当然の窓。閉じるとレンダ自体が中断される("Render Incomplete")ので
# 平常時の番犬対象から外す。進捗窓は "Rendering to file..." → "Finished in 0:01
# (108x realtime)" とタイトルが変わる。
BENIGN_PREFIXES = ("Rendering to file", "Finished in")

# 良性でない窓が出てもすぐには閉じない。描画途中の一瞬を拾わないための猶予。
DIALOG_GRACE_S = 2.0


def reaper_dialogs(include_benign: bool = False) -> list[tuple[int, str]]:
    """REAPER のダイアログ窓を (window_id, title) で返す。メイン窓は除く。

    niri へ問い合わせるので REAPER がモーダルで固まっていても応答する
    （reapy 越しには取得できない情報）。

    include_benign=True で進捗窓も含める。タイムアウト時の後始末に使う —
    進捗窓は "Rendering to file..." のタイトルのまま固まることがある
    （出力先が書き込み不可のときに実測で再現）ので、良性リストは平常時の
    番犬判定にしか使えない。
    """
    out = subprocess.run(
        ["niri", "msg", "--json", "windows"],
        capture_output=True, text=True, check=False,
    ).stdout
    try:
        wins = json.loads(out)
    except json.JSONDecodeError:
        return []
    dialogs = []
    for w in wins:
        if (w.get("app_id") or "") != "REAPER":
            continue
        title = w.get("title") or ""
        if MAIN_WINDOW_MARK in title:
            continue
        if not include_benign and title.startswith(BENIGN_PREFIXES):
            continue
        dialogs.append((w["id"], title))
    return dialogs


def close_window(wid: int) -> None:
    """niri でウィンドウを閉じる。reapy は使わない — 固まっている API を叩くと
    後片付けの側まで一緒に固まる。
    """
    subprocess.run(
        ["niri", "msg", "action", "close-window", "--id", str(wid)],
        capture_output=True, check=False,
    )


def drain_dialogs(tries: int = 5, wait: float = 0.4,
                  include_benign: bool = True) -> list[str]:
    """残っているダイアログを消えるまで閉じる。閉じた順にタイトルを返す。

    1つ閉じると次が出る場合があるので繰り返す(上書き確認 → 別の警告 など)。
    """
    closed: list[str] = []
    for _ in range(tries):
        dialogs = reaper_dialogs(include_benign=include_benign)
        if not dialogs:
            break
        for wid, title in dialogs:
            closed.append(title)
            close_window(wid)
        time.sleep(wait)
    return closed


def _select_all_tracks(proj_id) -> None:
    """ステム書き出しは選択中トラックが対象。全トラックを選ぶ。

    これを忘れると master と「たまたま選択されていた1本」しか出ない。
    """
    n = int(RPR.CountTracks(proj_id))
    for i in range(n):
        RPR.SetMediaTrackInfo_Value(RPR.GetTrack(proj_id, i), "I_SELECTED", 1)


def render(out_dir: Path, stems: bool = False, sr: int = 44100,
           timeout: float = 120.0, poll: float = 0.3) -> dict:
    """REAPER にレンダを投げ、所要時間とダイアログ有無を返す。

    現在開いているプロジェクトをレンダする(reapy.Project() で暗黙に取得)。
    stems=True なら全トラックを選択し `$track` ごとの wav を、False なら
    master 一本 (mix.wav) を出す。

    返り値: {"ok": bool, "elapsed": float, "dialogs": [title, ...], "out_dir": Path}
    ok=False は「詰まった」を検出して番犬が介入した回。中断されたレンダなので
    出力 wav は不完全な可能性があり、呼び出し側は使わないこと。
    """
    import reapy

    proj = reapy.Project()
    proj_id = proj.id

    out_dir.mkdir(parents=True, exist_ok=True)
    # 予防: 既存の出力を先に消す。残っていると上書き確認ダイアログが出て
    # reapy API ごと固まる
    for old in out_dir.glob("*.wav"):
        old.unlink()

    if stems:
        _select_all_tracks(proj_id)

    RPR.GetSetProjectInfo(proj_id, "RENDER_SETTINGS", 1 if stems else 0, True)
    RPR.GetSetProjectInfo(proj_id, "RENDER_BOUNDSFLAG", 1, True)  # entire project
    RPR.GetSetProjectInfo(proj_id, "RENDER_CHANNELS", 2, True)
    RPR.GetSetProjectInfo(proj_id, "RENDER_SRATE", sr, True)
    RPR.GetSetProjectInfo(proj_id, "RENDER_TAILFLAG", 0, True)
    RPR.GetSetProjectInfo(proj_id, "RENDER_ADDTOPROJ", 0, True)
    RPR.GetSetProjectInfo(proj_id, "RENDER_DITHER", 16, True)
    RPR.GetSetProjectInfo(proj_id, "RENDER_NORMALIZE", 0, True)
    RPR.GetSetProjectInfo_String(proj_id, "RENDER_FILE", str(out_dir), True)
    RPR.GetSetProjectInfo_String(proj_id, "RENDER_PATTERN",
                                 "$track" if stems else "mix", True)

    done = threading.Event()

    def fire() -> None:
        try:
            RPR.Main_OnCommand(RENDER_AUTOCLOSE, 0)
        finally:
            done.set()

    seen: list[str] = []
    first_seen: dict[int, float] = {}
    t0 = time.time()
    threading.Thread(target=fire, daemon=True).start()
    while not done.wait(poll):
        now = time.time()
        for wid, title in reaper_dialogs():
            first_seen.setdefault(wid, now)
            if now - first_seen[wid] >= DIALOG_GRACE_S:
                seen.append(title)
                close_window(wid)
        if now - t0 > timeout:
            # タイムアウト時は進捗窓も含めて全部落とす。良性リストは平常時の
            # 判定用で、そのタイトルのまま固まる経路が実在する(書き込み不可の
            # 出力先など)
            seen += drain_dialogs()
            return {"ok": False, "elapsed": now - t0, "dialogs": seen,
                    "out_dir": out_dir}

    return {"ok": not seen, "elapsed": time.time() - t0, "dialogs": seen,
            "out_dir": out_dir}
