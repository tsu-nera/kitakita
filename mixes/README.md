# mixes — DJ Mix

複数曲にまたがる判断（曲順・つなぎ）の作り方を置く。1曲単位の下ごしらえは `src/trackprep/`。

## データの置き場所

「作り直せるか」と「誰が使うか」で分ける。音声ファイルは git に入れない。

| 種類 | 置き場所 | 扱い |
|------|---------|------|
| raw（Suno からの原曲） | `~/Music/kitakita/raw/` | 作り直せない。読み取り専用（`chmod a-w`）、バックアップ対象。ダウンロードしたらここへ移す |
| 派生物（解析・stem・warp） | `~/.cache/trackprep/` | 再生成できる。消えてよい |
| 編集物（DJ edit、採用した mix） | `~/Music/kitakita/edits/`, `~/Music/kitakita/mixes/` | 人が聴いて採用した完成品。Mixxx で使う・公開する |
| 作り方（plan、mix スクリプト） | repo の `mixes/<mix名>/` | git 管理。成果物はここから作り直せる状態にする |
| 実験物（試聴クリップ・診断） | repo の `tmp/djmix/` | git 非追跡。再起動では消えない（`/tmp` の scratchpad には置かない） |

Mixxx はパスで曲を管理する。raw を移すときは Mixxx を閉じ、`~/.mixxx/mixxxdb.sqlite` の `track_locations.location`/`directory` も書き換える（キューを保つため）。
