"""Reconcile Reaper to match song.py — idempotent. Plus the drift report.

Re-running is safe: tracks are matched by name (created only if missing),
the RS5k sample / volume / BPM are set only when they differ, and section
regions are rewritten only when they drift.
"""
from __future__ import annotations

import reapy
from reapy import reascript_api as RPR

from kita.duck import duck_points_song
from kita.model import Sampler, Song, Synth, Track, group_runs
from kita.reaper.bridge import (
    FILTER_FX,
    SAMPLER_FX,
    SYNTH_FX,
    ensure_volume_envelope,
    envelope_points,
    filter_index,
    find_track,
    get_file0,
    get_volume_envelope,
    list_regions,
    norm,
    sampler_index,
    set_envelope_points,
    synth_index,
    synth_param_indices,
)

# ReaSynth を wave=<key> にするための正規化パラメータ。全 "* mix" を明示リセット
# してから当該波形だけ上げる(前回別波形で残った mix を消すため)。Sustain を上げて
# ノートを持続させ、素の ReaSynth では鳴らない(全 mix=0 初期値)状態を避ける。
_WAVE_MIX = {"saw": "saw mix", "square": "square mix",
             "triangle": "triangle mix", "sine": "extra sine mix"}
_ALL_MIX = ("saw mix", "square mix", "triangle mix", "extra sine mix")


def build_layout(song: Song) -> list[dict]:
    """上から並べる Reaper トラック列を導出する。

    各エントリ: name / kind('bus'|'sample') / depth(I_FOLDERDEPTH) / track。
    group ごとに親バス(depth=+1)を挿し、最後の子で folder を閉じる(depth=-1)。
    """
    layout: list[dict] = []
    for gname, ts in group_runs(song.tracks):
        if gname is not None:
            layout.append(dict(name=gname, kind="bus", depth=1, track=None))
            for i, t in enumerate(ts):
                layout.append(dict(name=t.name, kind="sample",
                                   depth=(-1 if i == len(ts) - 1 else 0), track=t))
        else:
            for t in ts:
                layout.append(dict(name=t.name, kind="sample", depth=0, track=t))
    return layout


def desired_regions(song: Song) -> list[tuple[str, float, float]]:
    """セクション境界 → (name, start_sec, end_sec)。sections 無しなら空。"""
    if not song.sections:
        return []
    return [(sec.name, song.bar_to_sec(b0), song.bar_to_sec(b1))
            for sec, b0, b1 in song.section_bounds()]


def regions_match(existing: list[tuple[str, float, float, int]],
                  desired: list[tuple[str, float, float]], tol: float = 1e-3) -> bool:
    if len(existing) != len(desired):
        return False
    ex = sorted(existing, key=lambda r: r[1])
    return all(en == dn and abs(es - ds) < tol and abs(ee - de) < tol
               for (en, es, ee, _), (dn, ds, de) in zip(ex, desired))


def _reconcile_volume(track, spec_t: Track) -> str:
    """トラック音量 (D_VOL) を song の gain_db に合わせ、状態文字列を返す。"""
    want_vol = spec_t.gain_linear
    if abs(RPR.GetMediaTrackInfo_Value(track.id, "D_VOL") - want_vol) < 1e-3:
        return "vol="
    RPR.SetMediaTrackInfo_Value(track.id, "D_VOL", want_vol)
    return "vol+"


def _reconcile_sample(track, spec_t: Track, want_file: str) -> str:
    """sample トラックの RS5k/FILE0/音量を song に合わせ、状態文字列を返す。"""
    fx_idx = sampler_index(track)
    if fx_idx < 0:
        fx_idx = RPR.TrackFX_AddByName(track.id, SAMPLER_FX, False, -1)
        if fx_idx < 0:
            raise RuntimeError(f"could not add {SAMPLER_FX} to {spec_t.name}")
        fxstate = "fx+"
    else:
        fxstate = "fx="

    if norm(get_file0(track, fx_idx)) == norm(want_file):
        sstate = "sample="
    else:
        RPR.TrackFX_SetNamedConfigParm(track.id, fx_idx, "FILE0", want_file)
        RPR.TrackFX_SetNamedConfigParm(track.id, fx_idx, "DONE", "")
        sstate = "sample+"

    return f"{fxstate} {sstate} {_reconcile_volume(track, spec_t)}"


def _reconcile_synth(track, spec_t: Track) -> str:
    """synth (lead) トラックへ ReaSynth を挿し、wave に応じた mix / 音量へ寄せる。"""
    inst: Synth = spec_t.instrument
    fx_idx = synth_index(track)
    if fx_idx < 0:
        fx_idx = RPR.TrackFX_AddByName(track.id, SYNTH_FX, False, -1)
        if fx_idx < 0:
            raise RuntimeError(f"could not add {SYNTH_FX} to {spec_t.name}")
        fxstate = "fx+"
    else:
        fxstate = "fx="

    params = synth_param_indices(track, fx_idx)
    want = _WAVE_MIX.get(inst.wave, "saw mix")
    for mix in _ALL_MIX:  # 選択波形以外を 0、選択波形を 1 に
        if mix in params:
            RPR.TrackFX_SetParamNormalized(track.id, fx_idx, params[mix],
                                           1.0 if mix == want else 0.0)
    if "sustain" in params:  # 音源ごとの sustain(lead=1.0持続 / midbass=0.0プラック)
        RPR.TrackFX_SetParamNormalized(track.id, fx_idx, params["sustain"], inst.sustain)

    fstate = _reconcile_filter(track, inst)
    return (f"{fxstate} wave={inst.wave} sus={inst.sustain:.1f} {fstate} "
            f"{_reconcile_volume(track, spec_t)}")


def _reconcile_filter(track, inst: Synth) -> str:
    """ReaSynth の後段に JSFX resonant LPF を冪等制御する。

    inst.cutoff=None ならフィルタを外し、Hz 指定ならフィルタを挿して
    Frequency(param0, 生Hz)/Resonance(param1, 0..1) を寄せる。
    """
    idx = filter_index(track)
    if inst.cutoff is None:
        if idx >= 0:
            RPR.TrackFX_Delete(track.id, idx)
            return "filt-"
        return "filt="
    if idx < 0:
        idx = RPR.TrackFX_AddByName(track.id, FILTER_FX, False, -1)
        if idx < 0:
            raise RuntimeError(f"could not add {FILTER_FX} to {track.name}")
        added = "filt+"
    else:
        added = "filt="
    RPR.TrackFX_SetParam(track.id, idx, 0, float(inst.cutoff))
    RPR.TrackFX_SetParam(track.id, idx, 1, float(inst.resonance))
    return f"{added}({inst.cutoff:.0f}Hz/r{inst.resonance:.2f})"


def _duck_target_points(song: Song, spec_t: Track) -> list[tuple[float, float]]:
    """spec_t.duck の点列に track の gain_linear を掛けた、envelope に書くべき値。

    Volume エンベロープは有効時にトラックフェーダーを置き換えるため、
    duck_gain 単独ではなく gain_linear * duck_gain を書く必要がある。
    """
    gain = spec_t.gain_linear
    return [(t, gain * v) for t, v in duck_points_song(song, spec_t)]


def _duck_points_match(existing: list[tuple[float, float]],
                       desired: list[tuple[float, float]], tol: float = 1e-3) -> bool:
    if len(existing) != len(desired):
        return False
    return all(abs(et - dt) < tol and abs(ev - dv) < tol
               for (et, ev), (dt, dv) in zip(existing, desired))


def _reconcile_duck(track, song: Song, spec_t: Track) -> str:
    """Volume エンベロープの ducking 点列を song に合わせ、状態文字列を返す。"""
    if spec_t.duck is None:
        env = get_volume_envelope(track)
        if env is not None and envelope_points(env):
            set_envelope_points(env, [])
            return "duck-"
        return "duck="

    desired = _duck_target_points(song, spec_t)
    env = ensure_volume_envelope(track)
    if _duck_points_match(envelope_points(env), desired):
        return "duck="
    set_envelope_points(env, desired)
    return f"duck+({spec_t.duck.depth_db:+.1f}dB/{len(desired)}pt)"


def _reconcile_regions(p, song: Song, dry: bool) -> None:
    desired = desired_regions(song)
    existing = list_regions(p)
    if regions_match(existing, desired):
        print(f"  regions {len(desired)} ok")
        return
    if dry:
        print(f"[dry] regions: rewrite {len(existing)} -> {len(desired)} "
              f"({', '.join(n for n, _, _ in desired) or 'none'})")
        return
    for _, _, _, idx in existing:
        RPR.DeleteProjectMarker(p.id, idx, True)
    for name, start, end in desired:
        p.add_region(start, end, name)
    print(f"  regions rewritten: {', '.join(n for n, _, _ in desired) or '(none)'}")


def reconcile(song: Song, dry: bool = False) -> None:
    for t in song.tracks:
        if isinstance(t.instrument, Sampler) and not song.sample_path(t).exists():
            raise FileNotFoundError(song.sample_path(t))

    p = reapy.Project()
    layout = build_layout(song)
    known = {e["name"] for e in layout}

    if dry:
        if abs(p.bpm - song.bpm) > 1e-6:
            print(f"[dry] bpm: {p.bpm} -> {song.bpm}")
        for e in layout:
            tag = "exists" if find_track(p, e["name"]) is not None else "create"
            print(f"[dry] {e['name']:6s} {e['kind']:6s} depth={e['depth']:+d} ({tag})")
        print(f"[dry] order: {' > '.join(e['name'] for e in layout)}")
        for t in song.tracks:
            if t.duck is not None:
                n_pts = len(_duck_target_points(song, t))
                print(f"[dry] {t.name:6s} duck <- {t.duck.source} "
                      f"depth={t.duck.depth_db:+.1f}dB ({n_pts}pt planned)")
        _reconcile_regions(p, song, dry=True)
        extra = [t.name for t in p.tracks if t.name not in known]
        if extra:
            print(f"[dry] not in song (untouched): {extra}")
        return

    if abs(p.bpm - song.bpm) > 1e-6:
        p.bpm = song.bpm
        print(f"  bpm -> {song.bpm}")

    # 1) 存在を担保しつつ各トラックを reconcile
    for e in layout:
        track = find_track(p, e["name"])
        tstate = "exists" if track is not None else "created"
        if track is None:
            track = p.add_track(name=e["name"])
        if e["kind"] == "bus":
            detail = "bus"
        elif isinstance(e["track"].instrument, Synth):
            detail = _reconcile_synth(track, e["track"])
        else:
            detail = _reconcile_sample(track, e["track"], str(song.sample_path(e["track"])))
        if e["kind"] != "bus":
            detail = f"{detail} {_reconcile_duck(track, song, e['track'])}"
        print(f"  {e['name']:6s} {tstate:7s} {detail}")

    # 2) layout 順へ並べ替え(左から確定。目的トラックを位置 idx へ引き上げる)
    for idx, e in enumerate(layout):
        track = find_track(p, e["name"])
        RPR.SetOnlyTrackSelected(track.id)
        RPR.ReorderSelectedTracks(idx, 0)

    # 3) folder 階層(I_FOLDERDEPTH)を設定。並べ替え後に行う
    for e in layout:
        track = find_track(p, e["name"])
        RPR.SetMediaTrackInfo_Value(track.id, "I_FOLDERDEPTH", float(e["depth"]))

    # 4) セクション境界のリージョン
    _reconcile_regions(p, song, dry=False)

    extra = [t.name for t in p.tracks if t.name not in known]
    if extra:
        print(f"note: {len(extra)} track(s) not in song (left untouched): {extra}")
    print(f"done. reaper tracks: {p.n_tracks}")


def status(song: Song) -> bool:
    """Drift report。Reaper が song と一致していれば True。"""
    p = reapy.Project()
    by_name = {t.name: t for t in p.tracks}
    ok = True

    if abs(p.bpm - song.bpm) > 1e-6:
        print(f"bpm     : {p.bpm} (song {song.bpm})  DRIFT")
        ok = False
    else:
        print(f"bpm     : {p.bpm}  ok")
    bus_names = song.bus_names
    print(f"tracks  : reaper={p.n_tracks} song={len(song.tracks)} bus={len(bus_names)}")

    for b in bus_names:
        present = "ok" if b in by_name else "MISSING"
        if b not in by_name:
            ok = False
        print(f"  {b:5s} bus (folder) {present}")

    for st in song.tracks:
        t = by_name.get(st.name)
        if t is None:
            print(f"  {st.name:5s} MISSING (not in Reaper)")
            ok = False
            continue
        if isinstance(st.instrument, Synth):
            if synth_index(t) < 0:
                print(f"  {st.name:5s} no {SYNTH_FX}")
                ok = False
            else:
                print(f"  {st.name:5s} fx=ok items={t.n_items} synth=ok "
                      f"(wave={st.instrument.wave})")
            continue
        fx_idx = sampler_index(t)
        if fx_idx < 0:
            print(f"  {st.name:5s} no {SAMPLER_FX}")
            ok = False
            continue
        cur = get_file0(t, fx_idx)
        want = str(song.sample_path(st))
        sample_ok = norm(cur) == norm(want)
        flag = "ok" if sample_ok else "SAMPLE-DRIFT"
        if not sample_ok:
            ok = False
        print(f"  {st.name:5s} fx=ok items={t.n_items} sample={flag}"
              f"  ({song.sample_path(st).name})")
        if not sample_ok:
            print(f"        reaper: {cur or '(empty)'}")

    for st in song.tracks:
        t = by_name.get(st.name)
        if t is None:
            continue
        env = get_volume_envelope(t)
        existing = envelope_points(env) if env is not None else []
        if st.duck is None:
            flag = "ok" if not existing else "DRIFT (stale points)"
            if existing:
                ok = False
            print(f"  {st.name:5s} duck none  {flag}")
            continue
        desired = _duck_target_points(song, st)
        duck_ok = _duck_points_match(existing, desired)
        flag = "ok" if duck_ok else "DRIFT"
        if not duck_ok:
            ok = False
        print(f"  {st.name:5s} duck<-{st.duck.source:6s} "
              f"points={len(existing)}/{len(desired)}  {flag}")

    desired = desired_regions(song)
    existing = list_regions(p)
    if regions_match(existing, desired):
        print(f"regions : {len(desired)} ok "
              f"({', '.join(n for n, _, _ in desired) or 'none'})")
    else:
        ok = False
        print(f"regions : DRIFT (reaper={[(r[0]) for r in existing]} "
              f"song={[n for n, _, _ in desired]})")

    known = {t.name for t in song.tracks} | set(bus_names)
    extra = [n for n in by_name if n not in known]
    if extra:
        print(f"extra   : not in song: {extra}")

    print("=> in sync" if ok else "=> drift detected")
    return ok
