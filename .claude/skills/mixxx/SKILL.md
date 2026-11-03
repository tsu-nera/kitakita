---
name: mixxx
description: Mixxx の DB（~/.mixxx/mixxxdb.sqlite の cues）を読み書きする時、Mixxx を曲付きで起動・再起動する時に使う。agent がラベル付きホットキューを書き、人が Mixxx の波形で確かめる、という DJ Mix 作業のやり取りの画面。
---

# Mixxx

## 書き込み前の手順

1. Mixxx が起動していないことを確認する: `pgrep -x mixxx`（出力があれば起動中）
2. DB をバックアップする
3. 書く

Mixxx は起動中の状態を終了時に DB へ書き戻すので、起動中に書いた分は消える。

## cue を書く

trackprep のキャッシュ（`~/.cache/trackprep/`）の `sections` からラベル付きホットキューを作る。上記の手順（起動チェック + バックアップ）は `write_cues.py` が実 DB に対して自動で行う。

```bash
cd .claude/skills/mixxx/scripts
python -I write_cues.py [--db <path>] <audio>...                    # 各ファイル自身の解析
python -I write_cues.py [--db <path>] --warp <orig> <bpm> <warped>  # orig の sections を warp 出力へ写す
```

- 対象曲の hotcue（type 1）は全部消して入れ直す。main cue / intro / outro / N60dB は触らない。
- `--db` 省略時は実 DB。起動チェックは実 DB のときだけ。検証はコピーに `--db` で行う（`cp ~/.mixxx/mixxxdb.sqlite <copy>`）。コピー相手なら Mixxx 起動中でも書ける。
- Mixxx に一度も読ませていないファイルは `library` に無く、書けない。

## 起動・再起動

`mixxx a.mp3 b.mp3` で a が Deck 1、b が Deck 2 に載る。再起動は終了させてから同じ形で起動する。

```bash
pkill -x mixxx   # 終了を待つ（pgrep -x mixxx が空になる）
mixxx a.mp3 b.mp3 &
```

## cues テーブルの形式

- `position` / `length` はインターリーブしたステレオのサンプル数（フレーム数×2）。秒 = position / 2 / `library.samplerate`。Suno の mp3 は 48000。
- `type`: 1=HotCue, 2=MainCue, 6=Intro, 7=Outro, 8=N60dBSound（無音でない範囲。Mixxx が解析時に自動で作る）。
- `hotcue` 列はパッド番号-1（0〜7）。hotcue 以外の type では -1。
- position は小数で保存される。quantize が有効なら、人が打ったホットキューは Mixxx 自身の beatgrid にスナップする（trackprep の downbeat とは十数 ms ずれる）。
- 曲の特定は `library` と `track_locations` を location（絶対パス）で join する。

## 人が打ったキューを読む

Mixxx を終了した後に `cues` を読む（終了時に保存されるため）。
