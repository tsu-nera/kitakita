"""song.py -> 配置ビュー(HTML)を生成する(#40)。

`song.py` を編集しても何をどこに配置したのか人間には見えない。REAPER がその役目を
担っていたが起動待ち・GUI 往復のコストが見合わないため(#39 でユーザーが REAPER を
外す方針を決定)、この layer は REAPER を一切呼ばない。試聴音は kita/sim.py の
render_full_mix(numpy + pedalboard、REAPER 非依存) で全曲を1本合成する。

描画の原則(Issue #40):
  形 = モデルの構造(固定): 実線の帯 = Section.play、縁取りの箱 = Song.hits(one-shot)、
       右端の縦棒 = align="end"、左端の縦棒 = align="start"
  色 = track.group の出現順(ハッシュにしないのは、名前を変えたときに全色が
       変わるのを避けるため)。group=None は "ungrouped" として最後にまとめる。
       どのグループも特別扱いしない。

トラック名・セクション名・グループ名は一切ハードコードしない — すべて song から
出現順に拾う。
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np

from kita import sim
from kita.model import BEATS_PER_BAR, Hit, Sampler, Song, Synth, group_runs

# 出現順に配る固定パレット。ハッシュでなく出現順にするのは、track.group の名前を
# 変えたときに全色が変わるのを避けるため。色数が尽きたら循環する。
# soft(背景)は CSS 側で color-mix(base, panel) から作るので、ここは base 色だけでよい
# — light/dark どちらの --panel に対しても自動で読める濃さになる。
PALETTE = [
    "#3F6E9B",  # steel
    "#2F7A72",  # teal
    "#B0701A",  # amber
    "#8B5CB0",  # purple
    "#B0435C",  # rose
    "#4C8C3C",  # green
    "#3C8C8C",  # cyan
    "#8C7A3C",  # olive
]

UNGROUPED = "ungrouped"


def _hit_bar_range(song: Song, hit: Hit) -> tuple[float, float]:
    """hit の [start_bar, end_bar) を bar 単位で返す。

    位置解決は Song._hit_abs_beat(実装は model.py 側の唯一の正本)を再利用する
    — at="<section>:<bar>.<beat>" のパースやセクション境界の解決を書き直さない。
    """
    beat0 = song._hit_abs_beat(hit)
    length_bars = song.sample_beats(song.track(hit.track)) / BEATS_PER_BAR
    bar0 = beat0 / BEATS_PER_BAR
    return bar0, bar0 + length_bars


def _groups(song: Song) -> list[tuple[str, list]]:
    """(group key, tracks) を出現順で返す。group=None は最後に "ungrouped" へまとめる。

    group_runs は非連続 group を Song.__post_init__ で既に弾いているので、ここでは
    「None のランを合流させる」ことだけ考えればよい。
    """
    ordered: dict[str, list] = {}
    ungrouped: list = []
    for g, tracks in group_runs(song.tracks):
        if g is None:
            ungrouped.extend(tracks)
            continue
        ordered.setdefault(g, []).extend(tracks)
    result = list(ordered.items())
    if ungrouped:
        result.append((UNGROUPED, ungrouped))
    return result


def _boundary_chips(song: Song) -> list[dict]:
    """セクション境界のうち、hit が跨いでいるものだけをチップとして抽出する(#40 の3)。

    区間は「その境界を跨ぐ hit 全部が収まる範囲」を hits の実尺から計算し、前後に
    1小節ずつ余白を足す(手書き数値は使わない)。

    align="end" の hit は境界ちょうどで鳴り終わり、align="start" の hit は境界
    ちょうどから鳴り始めるよう設計されている(model.py 参照) — つまり典型的には
    「境界に接する」のであって厳密に内側へ跨がない。wav 尺換算の丸め誤差で
    end_bar/start_bar が境界の前後どちらにブレるかは不定なので、判定は
    境界への近接(接する場合を含む)を許容誤差付きで見る。
    """
    EPS = 1e-2  # bar 単位。wav 尺 -> bar 換算の丸め誤差を吸収する
    bounds = song.section_bounds()
    hit_ranges = [(h,) + _hit_bar_range(song, h) for h in song.hits]
    chips = []
    for i in range(len(bounds) - 1):
        boundary = bounds[i][2]  # bounds[i] = (section, start, end)
        before, after = bounds[i][0].name, bounds[i + 1][0].name
        crossing = [(s, e) for _, s, e in hit_ranges
                    if s - EPS <= boundary <= e + EPS]
        if not crossing:
            continue
        lo = min(s for s, _ in crossing)
        hi = max(e for _, e in crossing)
        pad = 1.0
        b0 = max(0.0, lo - pad)
        b1 = min(float(song.total_bars), hi + pad)
        chips.append({
            "id": f"t_{before}-{after}",
            "label": f"{before} → {after}",
            "b0": b0,
            "b1": b1,
        })
    return chips


def build_data(song: Song) -> dict:
    """song から配置データ(dict)を作る。音声合成には触れない(即時)。"""
    groups = _groups(song)
    color_of = {g: PALETTE[i % len(PALETTE)] for i, (g, _) in enumerate(groups)}

    tracks = []
    for t in song.tracks:
        gkey = t.group if t.group is not None else UNGROUPED
        kind = "Synth" if isinstance(t.instrument, Synth) else "Sampler"
        sample = t.instrument.sample if isinstance(t.instrument, Sampler) else None
        tracks.append({
            "name": t.name,
            "group": gkey,
            "color": color_of[gkey],
            "gain_db": t.gain_db,
            "kind": kind,
            "sample": sample,
            "duck": t.duck.source if t.duck is not None else None,
            "reverb": t.reverb is not None,
        })

    sections = []
    for sec, b0, b1 in song.section_bounds():
        sections.append({
            "name": sec.name,
            "start": b0,
            "end": b1,
            "play": list(sec.play.keys()),
            "rms_db": None,
            "peak_db": None,
        })

    hits = []
    for h in song.hits:
        s, e = _hit_bar_range(song, h)
        hits.append({
            "track": h.track,
            "at": h.at,
            "align": h.align,
            "velocity": h.velocity,
            "start_bar": s,
            "end_bar": e,
        })

    chips = _boundary_chips(song)

    clips: dict[str, dict] = {"_full": {"b0": 0.0, "b1": float(song.total_bars)}}
    for s in sections:
        clips[f"s_{s['name']}"] = {"b0": s["start"], "b1": s["end"]}
    for c in chips:
        clips[c["id"]] = {"b0": c["b0"], "b1": c["b1"]}

    return {
        "bpm": song.bpm,
        "total_bars": song.total_bars,
        "bar_sec": song.bar_to_sec(1),
        "length_sec": song.bar_to_sec(song.total_bars),
        "groups": [{"key": g, "label": g, "color": color_of[g]} for g, _ in groups],
        "tracks": tracks,
        "sections": sections,
        "hits": hits,
        "chips": chips,
        "clips": clips,
        "audio": {},          # clip id -> out_dir 相対パス。存在するものだけ埋める
        "bar_peak_db": [],    # --audio 時、または既存 _full 音声があるときだけ埋める
        "energy_lo": -30.0,
        "energy_hi": 0.0,
    }


# ---------- audio ----------

def _write_wav(path: Path, stereo: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    x16 = (np.clip(stereo.T, -1, 1) * 32767).astype("<i2")  # (N,2) へ転置=インタリーブ
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sim.SR)
        w.writeframes(x16.tobytes())


def _to_mp3(wav_path: Path) -> str:
    """ffmpeg で mp3 化してファイル名を返す。ffmpeg が無ければ wav のまま続行する。"""
    ffmpeg = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
    if not Path(ffmpeg).exists():
        print(f"warning: ffmpeg が見つからないため {wav_path.name} を wav のまま使う")
        return wav_path.name
    mp3_path = wav_path.with_suffix(".mp3")
    try:
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(wav_path), str(mp3_path)],
            check=True,
        )
    except (subprocess.CalledProcessError, OSError) as e:
        print(f"warning: ffmpeg 変換に失敗 ({e}) — {wav_path.name} を wav のまま使う")
        return wav_path.name
    wav_path.unlink()
    return mp3_path.name


def _fill_energy(song: Song, data: dict, mono: np.ndarray) -> None:
    """全曲 mono バッファから小節ごとのピークとセクション RMS/peak を埋める。"""
    sr = sim.SR
    bar_peaks = []
    for b in range(song.total_bars):
        s0 = int(song.bar_to_sec(b) * sr)
        s1 = int(song.bar_to_sec(b + 1) * sr)
        seg = mono[s0:s1]
        bar_peaks.append(sim.peak_db(seg) if seg.size else -120.0)
    data["bar_peak_db"] = bar_peaks
    data["energy_lo"] = math.floor(min(bar_peaks) - 3) if bar_peaks else -30.0
    data["energy_hi"] = 0.0
    for s in data["sections"]:
        s0 = int(song.bar_to_sec(s["start"]) * sr)
        s1 = int(song.bar_to_sec(s["end"]) * sr)
        seg = mono[s0:s1]
        if seg.size:
            s["rms_db"] = sim.rms_db(seg)
            s["peak_db"] = sim.peak_db(seg)


def render_audio(song: Song, out_dir: Path, data: dict) -> None:
    """sim.render_full_mix で全曲合成し、小節境界でオフライン分割して wav/mp3 を書く。

    REAPER には一切触れない — #39 を受けたユーザー決定により、この試聴音そのものが
    正本(「再構成すべき実機が無い」)。
    """
    mix, _ = sim.render_full_mix(song, stereo=True)  # (2, N)
    _fill_energy(song, data, mix.mean(axis=0))

    audio_dir = out_dir / "audio"
    audio_map: dict[str, str] = {}
    sr = sim.SR
    for clip_id, rng in data["clips"].items():
        s0 = max(0, int(song.bar_to_sec(rng["b0"]) * sr))
        s1 = min(mix.shape[-1], int(song.bar_to_sec(rng["b1"]) * sr))
        if s1 <= s0:
            continue
        wav_path = audio_dir / f"{clip_id}.wav"
        _write_wav(wav_path, mix[:, s0:s1])
        name = _to_mp3(wav_path)
        audio_map[clip_id] = f"audio/{name}"
    data["audio"] = audio_map


def _find_existing_audio(song: Song, out_dir: Path, data: dict) -> None:
    """--audio 無し実行: 前回生成済みの音声ファイルを指すだけ(合成しない)。

    エネルギー/セクション統計は前回の arrangement.json から引き継ぐ。mp3 化で元の
    wav は消えているので測り直す術が無く、測り直すには全曲合成(数秒)が要るため
    「見るだけ」の即時性が壊れる。引き継ぐのは小節数とセクション構成が前回と
    一致するときだけ — song.py の構造が変わっていたら古い数値は捨てる
    (音声ファイル自体が古くなるのと同じ範囲の陳腐化に留める)。
    """
    audio_dir = out_dir / "audio"
    if audio_dir.exists():
        audio_map: dict[str, str] = {}
        for clip_id in data["clips"]:
            for ext in (".mp3", ".wav"):
                p = audio_dir / f"{clip_id}{ext}"
                if p.exists():
                    audio_map[clip_id] = f"audio/{p.name}"
                    break
        data["audio"] = audio_map

    prev_path = out_dir / "arrangement.json"
    if not prev_path.exists():
        return
    try:
        prev = json.loads(prev_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not prev.get("bar_peak_db"):
        return
    same = (prev.get("total_bars") == data["total_bars"]
            and [s["name"] for s in prev.get("sections", [])]
            == [s["name"] for s in data["sections"]])
    if not same:
        return
    data["bar_peak_db"] = prev["bar_peak_db"]
    data["energy_lo"] = prev.get("energy_lo", -30.0)
    data["energy_hi"] = prev.get("energy_hi", 0.0)
    prev_sec = {s["name"]: s for s in prev["sections"]}
    for s in data["sections"]:
        src = prev_sec.get(s["name"], {})
        s["rms_db"] = src.get("rms_db")
        s["peak_db"] = src.get("peak_db")


# ---------- html ----------

def render_html(data: dict) -> str:
    return _TEMPLATE.replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False))


def generate(song: Song, out_dir: Path, audio: bool = False) -> Path:
    """配置データ + HTML を out_dir へ書く。戻り値は生成した HTML のパス。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    data = build_data(song)
    if audio:
        render_audio(song, out_dir, data)
    else:
        _find_existing_audio(song, out_dir, data)

    json_path = out_dir / "arrangement.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    html_path = out_dir / "arrangement.html"
    html_path.write_text(render_html(data), encoding="utf-8")
    return html_path


_TEMPLATE = (Path(__file__).with_name("view_template.html")).read_text(encoding="utf-8")
