# trackprep

DJ の track prep（beatgrid の確認・展開の把握）を自動化する楽曲解析 CLI。Suno に依存しない。
beat / downbeat は [beat_this](https://github.com/CPJKU/beat_this)（CPU のみ、1曲数十秒）、特徴量は librosa で取る。

## 使い方

```bash
cd src/trackprep && uv sync
uv run trackprep analyze <audio...> [--force]   # MP3 / M4A / WAV。解析済みは飛ばす
uv run trackprep show <audio|track_id> [--plot out.png]
uv run pytest                                   # 合成音源テスト（beat_this は走らない）
```

結果は `$XDG_CACHE_HOME/trackprep/<track_id>.json`（無ければ `~/.cache/trackprep/`）に 1 曲 1 ファイル。git 管理外。
`track_id` は音声ファイルの中身の sha256 先頭 16 桁（ファイル名を変えても同じ）。

## JSON の項目（`schema: 1`）

| 項目 | 内容 |
|------|------|
| `track_id`, `path`, `title`, `duration` | 識別子・絶対パス・タグの曲名（無ければファイル名）・秒 |
| `source` | `suno_id`（comment に `made with suno` と `id=<uuid>` があるときだけ） |
| `analyzer` | `beats`（`beat_this final0`）と trackprep のバージョン |
| `beats`, `downbeats` | 秒の配列 |
| `tempo_segments` | `from_bar`, `to_bar`, `bpm_start`, `bpm_end`。拍間隔の異常点で切り、32拍窓の BPM が 1.0 以上動く所でも切る |
| `anomalies` | 拍間隔が中央値の 0.5 倍未満 / 1.5 倍超の箇所（`bar`, `time`, `kind: beat_irregular`）。連続分は1件にまとめる |
| `bars` | 小節ごとの `bar`, `time`, `rms`, `low`(40-100Hz), `high`(6kHz 以上), `kick`。rms/low/high は曲内最大で正規化 |
| `phrase_offset_bar` | 8小節 phrase の起点小節（1〜8）。低域の変化が最も揃う起点 |
| `sections` | phrase 単位の推定区間 `label`, `from_bar`, `to_bar`。ラベルは `intro` / `breakdown` / `break` / `groove` / `drop` |
| `ending` | `kind`（`abrupt` / `fade`）と `decay_sec`。最後の大音量から -40dB まで 5 秒未満なら `abrupt` |
| `key` | Krumhansl-Schmuckler の推定と `confidence: "low"`（和風の音階では当たりにくい） |

## 注意

- `sections` のラベルは低域・RMS の閾値による**推定**。必ず耳で確認すること。
- MP3 の encoder delay は補正しない（beat_this と特徴量が同じ読み込み経路なので相対位置は揃う）。
