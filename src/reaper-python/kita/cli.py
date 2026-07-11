"""kita — single CLI entry point (`uv run kita <cmd>`).

song.py(正本) を読み、compose / sync / load / transport / check 等を実行する。
reapy(要 REAPER 起動) は必要なコマンドの中でだけ import する — compose / check /
render / suggest / bands はオフラインで動く。
"""
from __future__ import annotations

import argparse
from pathlib import Path

from kita.model import load_song


def main() -> None:
    parser = argparse.ArgumentParser(prog="kita")
    parser.add_argument("--song", help="song.py のパス (default: reaper-python/song.py)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("compose", help="song -> output/*.mid")
    p_sync = sub.add_parser("sync", help="トラック/バス/BPM/リージョンを冪等反映")
    p_sync.add_argument("--dry", action="store_true")
    sub.add_parser("load", help="output/*.mid を各トラックへ")
    sub.add_parser("play")
    sub.add_parser("stop")
    sub.add_parser("panic", help="all notes off")
    p_bpm = sub.add_parser("bpm")
    p_bpm.add_argument("value", type=float)
    p_loop = sub.add_parser("loop", help="ループ範囲: セクション名 | 拍数 | off")
    p_loop.add_argument("arg")
    sub.add_parser("status", help="Reaper と song の差分表示")
    sub.add_parser("check", help="聴かずに計測: バランス + セクション別エネルギー")
    sub.add_parser("suggest", help="目標バランスへ寄せる gain_db を提案")
    p_render = sub.add_parser("render", help="全曲オフライン合成 wav")
    p_render.add_argument("out")
    p_bands = sub.add_parser("bands", help="サンプル帯域スペクトル")
    p_bands.add_argument("target", help="track名 or wav パス")
    p_proc = sub.add_parser("reaper", help="REAPER プロセス制御")
    p_proc.add_argument("args", nargs="*", help="start [project.rpp] | stop | restart | status")

    args = parser.parse_args()

    if args.cmd == "reaper":  # song 不要
        from kita.reaper import proc
        proc.main(args.args)
        return

    song = load_song(args.song)

    if args.cmd == "compose":
        from kita import midi
        midi.compose_all(song)
    elif args.cmd == "sync":
        from kita.reaper import reconcile
        reconcile.reconcile(song, dry=args.dry)
    elif args.cmd == "load":
        from kita.reaper import load as _load
        _load.load(song)
    elif args.cmd == "play":
        from kita.reaper import transport
        transport.play()
    elif args.cmd == "stop":
        from kita.reaper import transport
        transport.stop()
    elif args.cmd == "panic":
        from kita.reaper import transport
        transport.panic()
    elif args.cmd == "bpm":
        from kita.reaper import transport
        transport.set_bpm(args.value)
    elif args.cmd == "loop":
        from kita.reaper import transport
        transport.loop(song, args.arg)
    elif args.cmd == "status":
        import sys

        from kita.reaper import reconcile
        sys.exit(0 if reconcile.status(song) else 1)
    elif args.cmd == "check":
        from kita import sim
        sim.check(song)
    elif args.cmd == "suggest":
        from kita import sim
        sim.suggest(song)
    elif args.cmd == "render":
        from kita import sim
        sim.render(song, Path(args.out))
    elif args.cmd == "bands":
        from kita import sim
        sim.bands(song, args.target)


if __name__ == "__main__":
    main()
