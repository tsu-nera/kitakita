# mixes — DJ Mix

複数曲にまたがる判断（曲順・つなぎ）のコードを置く。1曲単位の下ごしらえは `src/trackprep/`。データ（曲・plan・書き出し）は repo に置かない。

## データの置き場所

曲とそれに付く情報（判断・測定結果・plan・edit）は `~/Music/kitakita/` の1か所に置く。repo にはコードだけを置く。

```
~/Music/kitakita/
  tracks/<タイトル>_<suno_id 先頭8桁>/   1曲1フォルダ（同名タイトルの別生成と衝突しないよう suno_id を付ける）
    <タイトル>.mp3     原曲。読み取り専用（chmod a-w）
    structure.yaml     区間（隙間なく覆う）・役割・層・誰がいつ決めたか・気づき・edit の評価
    edits/<edit>.arrangement.md   edit の小節 → 原曲の小節と役割の対応表（render.py が書く）
    measure/           その場で測った結果。画面に出すだけで終わらせず、ファイルで残す
    re-edit.yaml       re-edit の plan
    edits/             書き出した edit と <edit>.cues.json
    cache -> ~/.cache/trackprep/<track_id>   重い派生物（analyze・stem・warp）。再生成できる、消えてよい
  mixes/<mix名>/       Mix の plan と書き出し
```

| 種類 | 置き場所 | 扱い |
|------|---------|------|
| 曲フォルダ | `~/Music/kitakita/tracks/` | 原曲以外の本人の判断は作り直せない。**バックアップ未整備**（`/home` は snapper の対象外） |
| 派生物（解析・stem・warp） | `~/.cache/trackprep/` | track_id は原曲の内容のハッシュなので、原曲を移動しても引ける |
| 実験スクリプト・試聴クリップ | repo の `tmp/djmix/` | git 非追跡。方式が固まったら trackprep へ昇格 |

## re-edit の型

Suno の曲はトランスの音色でポップスの形（キックの無い intro、短い break の繰り返し、テンポが崩れる締め）になりやすい。re-edit は原曲の区間を次の枠に当てはめる。既定であって、曲の持ち味は耳で判断して残す（2026-11-11、2曲の観察から。5曲ほどで見直す）。

| 枠 | 小節 | 中身 |
|---|---|---|
| drum intro | 16 | ドラムだけ（mix in。Mixxx の intro マーカー） |
| intro | 16（前後数小節は可） | 原曲の intro ＋ 下にドラム。メロディのフレーズの頭に合わせる |
| groove | 16〜32 | 4つ打ちの groove・verse |
| breakdown（短） | 8 | 任意 |
| drop 1 | 16 | |
| main breakdown | 16 以上 | build-up を含む |
| drop 2 | 16 | サビを含んでよい |
| 最後の drop | 8〜16 | 任意 |
| outro | 16 | 上物を少しずつ抜き、ドラムが残る（mix out。outro マーカー） |

- break（8小節以上）は最大2回（短 1 ＋ main 1）。3回以上あれば、つなげるか削る
- Suno は最後にポップスの締め（テンポが崩れる・太鼓の一撃）を置く。**締めの直前の区間（vocal 無し、drop に聞こえることもある）は原曲の outro として扱い**、outro の素材にする（Breath 122–127、鼓みの間 123–130）
- 捨てる: ポップスの締め（テンポが崩れる部分と、その前打ち）
- ループで小節を足すときは、締めへの前打ちを含む小節をフレーズの最後にだけ置く

Mixxx はパスで曲を管理する。曲を移すときは Mixxx を閉じ、`~/.mixxx/mixxxdb.sqlite` の `track_locations.location`/`directory` も書き換える（キューを保つため）。
