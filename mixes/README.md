# mixes — DJ Mix

複数曲にまたがる判断（曲順・つなぎ）のコードを置く。1曲単位の下ごしらえは `src/trackprep/`。データ（曲・plan・書き出し）は repo に置かない。

## データの置き場所

曲とそれに付く情報（判断・測定結果・plan・edit）は `~/Music/suno/` の1か所に置く。repo にはコードだけを置く。

```
~/Music/suno/
  tracks/<タイトル>_<suno_id 先頭8桁>/   1曲1フォルダ（同名タイトルの別生成と衝突しないよう suno_id を付ける）
    <タイトル>.mp3     原曲。読み取り専用（chmod a-w）
    structure.md       区間・層・本人の判断（誰がいつ決めたか）・気づき
    measure/           その場で測った結果。画面に出すだけで終わらせず、ファイルで残す
    re-edit.yaml       re-edit の plan
    edits/             書き出した edit と <edit>.cues.json
    cache -> ~/.cache/trackprep/<track_id>   重い派生物（analyze・stem・warp）。再生成できる、消えてよい
  mixes/<mix名>/       Mix の plan と書き出し
```

| 種類 | 置き場所 | 扱い |
|------|---------|------|
| 曲フォルダ | `~/Music/suno/tracks/` | 原曲以外の本人の判断は作り直せない。**バックアップ未整備**（`/home` は snapper の対象外） |
| 派生物（解析・stem・warp） | `~/.cache/trackprep/` | track_id は原曲の内容のハッシュなので、原曲を移動しても引ける |
| 実験スクリプト・試聴クリップ | repo の `tmp/djmix/` | git 非追跡。方式が固まったら trackprep へ昇格 |

Mixxx はパスで曲を管理する。曲を移すときは Mixxx を閉じ、`~/.mixxx/mixxxdb.sqlite` の `track_locations.location`/`directory` も書き換える（キューを保つため）。
