# trackprep

1曲単位の下ごしらえ（DJ 用語の track prep。解析・STEM 分離・一定テンポ化）をする CLI。Suno に依存しない。
2曲以上にまたがる判断（曲順・つなぐ位置・つなぎ方）は `mixes/` の担当で、ここには入れない。
beat / downbeat は [beat_this](https://github.com/CPJKU/beat_this)（CPU のみ、1曲数十秒）、特徴量は librosa、STEM 分離は Demucs（`htdemucs`、CPU で1曲約4分）、伸縮は rubberband で行う。

## 使い方

```bash
cd src/trackprep && uv sync
uv run trackprep analyze <audio...> [--force] [--full]   # MP3 / M4A / WAV。結果を stdout に JSONL で出す
uv run trackprep stems <audio...> [--force]               # Demucs で drums/bass/other/vocals に分離
uv run trackprep warp <audio...> --bpm 142 [--stems] [--force]   # 一定テンポへ小節ごとに伸縮
uv run trackprep show <audio|track_id> [--plot out.png]
uv run pytest                                   # 合成音源テスト（beat_this は走らない）
```

成果物は `$XDG_CACHE_HOME/trackprep/`（無ければ `~/.cache/trackprep/`）に置く。git 管理外。
`track_id` は音声ファイルの中身の sha256 先頭 16 桁（ファイル名を変えても同じ）。

```
<cache>/<track_id>.json                       # analyze
<cache>/<track_id>/stems/{drums,bass,other,vocals}.wav
<cache>/<track_id>/warp/<bpm>/mix.wav         # bpm は小数1桁（例: 142.0）
<cache>/<track_id>/warp/<bpm>/{drums,bass,other,vocals}.wav   # --stems 指定時
<cache>/<track_id>/warp/<bpm>/warp.json       # 出力済みのときに返す JSON
```

## analyze の出力（agent 向け）

- 入力 1 件につき JSON を 1 行（JSONL、`ensure_ascii=False`、改行・インデントなし）stdout に出す。順序は入力順。入力が 1 件ならそのまま JSON として読める。
- 解析済みはキャッシュから読んで返す（再解析しない）。`--force` で再解析・保存し直してから返す。
- 既定は要約: キャッシュ JSON から `beats` / `downbeats` / `bars` を除いたもの。`--full` でキャッシュ JSON と同じ全量。
- stdout は JSON 行だけ。`analyzing` / `saved` / `skip (cached)` / `not found` などの進捗・エラーは stderr。
- 存在しないパスは stdout に何も出さず stderr にメッセージを出して次へ進む。1 件でも失敗があれば終了コード 1、全件成功なら 0。
- `show` は人間向けテキスト表のまま（機械可読な出力は `analyze` に一本化）。

```bash
uv run trackprep analyze a.mp3 | jq .tempo_segments
```

## JSON の項目（`schema: 1`）

| 項目 | 内容 |
|------|------|
| `track_id`, `path`, `title`, `duration` | 識別子・絶対パス・タグの曲名（無ければファイル名）・秒 |
| `source` | `suno_id`（comment に `made with suno` と `id=<uuid>` があるときだけ） |
| `analyzer` | `beats`（`beat_this final0`）と trackprep のバージョン |
| `beats`, `downbeats` | 秒の配列 |
| `tempo_segments` | `from_bar`, `to_bar`, `bpm_start`, `bpm_end`。拍間隔の異常点で切り、32拍窓の BPM が 1.0 以上動く所でも切る |
| `anomalies` | 拍間隔が中央値の 0.5 倍未満 / 1.5 倍超の箇所（`bar`, `time`, `kind: beat_irregular`）。連続分は1件にまとめる |
| `bars` | 小節ごとの `bar`, `time`, `rms`, `low`(40-100Hz), `high`(6kHz 以上), `kick`。rms/low/high は完全な小節（拍数が最頻値の小節）の p95 で割り [0,1] に clip。stem がキャッシュにあるときだけ `drum_kicks`（int, キックありの拍数）と `four_on_floor`（bool）が付く。判定は drums stem の 40-120 Hz を拍ごとに見て（拍の -15〜+50 ms のピーク）、全拍の p90 − 15 dB 以上ならキックあり。`four_on_floor` は拍数 4 の小節で 4 拍すべてにキックがある場合 |
| `phrase_offset_bar` | 8小節 phrase の起点小節（1〜8）。低域の変化が最も揃う起点 |
| `sections` | phrase 単位の推定区間 `label`, `from_bar`, `to_bar`。ラベルは `intro` / `breakdown` / `break` / `groove` / `drop` |
| `ending` | `kind`（`abrupt` / `fade`）と `decay_sec`。最後の大音量から -40dB まで 5 秒未満なら `abrupt` |
| `key` | Krumhansl-Schmuckler の推定と `confidence: "low"`（和風の音階では当たりにくい） |

## stems

- 入力 1 件につき JSON 1 行: `{"track_id", "model": "htdemucs", "stems": {"drums": "<path>", ...}}`。分離済みなら飛ばす（`--force` でやり直す）。WAV は PCM_16。
- 解析キャッシュがあれば `bars[]` に `drum_kicks` / `four_on_floor` を書き足す（分離済みで飛ばした場合も）。解析キャッシュが無ければ stderr に `trackprep analyze` を案内するが、分離は成功扱い。analyze は stem があれば同じ項目を付ける。`show` は付いている曲だけ `dkick` / `4otf` 列を出す。
- 進捗・エラーは stderr、終了コードは analyze と同じ。

## warp

downbeat を基準に1小節ずつ伸縮して、全小節が同じ長さの音源にする（一定テンポなら Mixxx の beatgrid と sync がそのまま正しく動く）。

- **4/4拍子（1小節4拍）前提**。3拍子や変拍子は扱わない。
- **rubberband の CLI がシステムに必要**（Arch: `pacman -S rubberband`）。無ければ stderr に案内を出して終了コード 1。
- 解析結果が無ければ先に analyze を実行する。`--stems` で STEM が無いと自動では分離せず、`trackprep stems <file>` を案内してその曲は失敗（終了コード 1）。
- 写像: downbeat `d[k]` → `d[0] + k * BAR`（`BAR = 4*60/bpm`）。最初の downbeat より前は伸縮せず、最後の downbeat より後は最後の小節と同じ比率。mix と各 STEM に同じ写像を使う。44100 Hz・ステレオ・PCM_16。
- anomaly 区間（`beats` の乱れ、breakdown など）の downbeat は捨て、前後の正常な downbeat の間を周辺の正常な小節長の中央値で等間隔に補間する。曲頭・曲尾にかかる場合は外挿。analyze のキャッシュは書き換えない。
- 補正後の最後の小節長が周辺の正常な小節長の中央値の 75% 未満なら、最後の downbeat を捨てる（末尾の中途半端な小節。最後の downbeat より後は前の小節と同じ比率で伸ばす）。最初の小節も同じ条件で最初の downbeat を捨てる（最初の downbeat より前は伸縮しない）。捨てた downbeat は `downbeats_src` にも `interpolated_bars` にも入らない。
- 出力済みなら再計算せず `warp.json` の内容を返す（`--force` で作り直す）。

出力 JSON（入力 1 件につき 1 行）:

| 項目 | 内容 |
|------|------|
| `track_id`, `bpm`, `bar_sec` | `bar_sec = 4*60/bpm` |
| `first_downbeat_sec` | warp 後の最初の downbeat（元の音源と同じ位置） |
| `max_stretch` | 小節ごとの伸縮率 `BAR/元の小節長` の `max(\|率-1\|)`（0.026 は 2.6%）。警告の閾値は判定しない |
| `interpolated_bars` | 補間で埋めた小節番号（補正後の列での 1 始まり） |
| `downbeats_src` | 写像に使った補正後の downbeat（元の音源の秒） |
| `mix`, `stems` | 出力 WAV のパス |

warp 後の k 小節目は `first_downbeat_sec + (k-1) * bar_sec`。

**analyze の小節番号 → warp 後の位置**: 補間で downbeat の数が変わると、analyze の小節番号（`sections` / `bars`）と warp 後の小節番号がずれうる。`bars[n-1].time`（元の秒）に最も近い `downbeats_src` の要素の位置 k（1 始まり）が warp 後の小節番号で、位置は上の式で出す。

## 注意

- 解析結果の beats / downbeats は 10 ms 単位に丸めて保存される。warp の基準点もこの精度。

- `sections` のラベルは低域・RMS の閾値による**推定**。必ず耳で確認すること。
- MP3 の encoder delay は補正しない（beat_this と特徴量が同じ読み込み経路なので相対位置は揃う）。
