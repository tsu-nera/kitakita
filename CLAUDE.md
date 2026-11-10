# Claude Code 設定

音楽制作の実験を置く repo。プロジェクトごとに道具が違うので、手順は各 README にある。

## プロジェクト

| 状態 | 場所 | 内容 |
|------|------|------|
| 現役 | `src/trackprep/`, `mixes/` | Suno 曲の DJ Mix（下記） |
| 休止中（再開未定） | `src/reaper-python/` | kita: song.py（Python DSL）→ MIDI / sim 合成。REAPER 連携は 2026-09 に離脱決定。[README](src/reaper-python/README.md)（REAPER / reapy の検索手順も） |
| 休止中 | `src/strudel/`, `src/tidal/` | Strudel / Tidal のライブコーディング。[README](src/strudel/README.md)（ドキュメント検索・VSCode 拡張・サンプル） |

休止中のプロジェクトに触れるときは、まずその README を読む。`docs/adr/` は kita、`docs/*STRUDEL*.md` は Strudel のもの。

## DJ Mix のツール

1曲単位の下ごしらえは `src/trackprep/`（`cd src/trackprep && uv run trackprep <cmd>`）。

- `analyze <audio...>`: beat / downbeat・テンポ区間・anomaly・展開を解析（JSONL、キャッシュ）
- `stems <audio...>`: Demucs で drums / bass / other / vocals に分離（CPU で約4分）
- `warp <audio...> --bpm N [--stems]`: downbeat 基準で一定テンポへ伸縮（4/4、rubberband 必須）
- `show <audio|track_id>`: 解析結果の表示
- 境界: 1曲単位は trackprep、複数曲にまたがる判断（曲順・つなぎ）は `mixes/`。詳細は [src/trackprep/README.md](src/trackprep/README.md)
- データ（曲・判断・plan・edit）は `~/Music/suno/` に1曲1フォルダで置く。構成は [mixes/README.md](mixes/README.md)

## 用語

独自用語を作らない。DTM/トランス制作の一般名称をそのまま使う（例: transition FX、riser、reverse cymbal）。
一般名称が分からなければ「一般名称は未確認」と書く。訳語や短縮形を勝手に発明しない。
