# reaper-python

pure Python + REAPER でトランスを作るワークフロー（Issue #6）。

- **正本は `song.py`**（Python DSL で `Song` を宣言的に構築）。REAPER は片方向の描画先で、手で REAPER を編集しても正本はここ。
- 展開はセクション（`section()`）で表現し、REAPER のリージョンとして反映される。
- モデル/人間が聴かずにミックスと展開を検証できるよう、オフライン計測（`kita check`）を備える。

## アーキテクチャ

```
song.py (正本: Song を構築する宣言的コード)
  └─ kita/
      model.py     Song/Section/Track/Sampler/Event — 安定インターフェース
      patterns.py  Clip ビルダー (steps/euclid)。パターン解釈はここだけが知る
      midi.py      Song → output/*.mid (セクションを連結、1トラック1ファイル)
      sim.py       オフライン合成 + 計測 (check/suggest/render/bands)
      cli.py       `uv run kita <cmd>`
      reaper/      reapy で REAPER を冪等制御 (sync/load/transport/proc)
```

音楽的な語彙を増やすとき（fill、メロディ、オートメーション…）はスキーマ定義ではなく
`patterns.py` に Clip ビルダーを足す。パイプライン（midi/sim/reaper）は `Song` と
`Event` しか見ないので変更不要。

## ワークフロー

```bash
uv run kita compose        # song.py -> output/*.mid
uv run kita sync           # トラック/バス/RS5k/BPM/リージョンを冪等反映 (--dry で予告)
uv run kita load           # output/*.mid を各トラックへ流し込み
uv run kita check          # 聴かずに計測: バランス + セクション別エネルギーカーブ
uv run kita loop breakdown # セクション名でループ範囲を設定 (拍数/off も可)
uv run kita play / stop / panic / bpm 140
uv run kita status         # 走行中 REAPER と song.py の差分表示
uv run kita suggest        # 目標バランスへ寄せる gain_db を提案
uv run kita render out.wav # 全曲オフライン合成 (A/B・試聴用)
uv run kita bands bass     # サンプルの帯域スペクトル
uv run kita reaper start|stop|restart|status   # REAPER プロセス制御 (Linux)
```

`compose / check / suggest / render / bands` はオフラインで動く（REAPER 不要）。
それ以外は REAPER 起動中 + reapy ブリッジが必要。

> **サンプルについて**: `song.py` の `SAMPLES`（sample_root）配下の wav を参照する。
> 無い環境では `uv run python samples/gen_kick.py` で合成キックを生成し
> sample_root を `'samples'` に向けて代用する。`sync` は全サンプルの実在を要求する。

## 環境構築

OS 非依存の部分とプラットフォーム固有の部分を分けて記載する。
（現状の検証環境は CachyOS。Windows での運用は未定）

### OS 共通

#### Python 依存

```bash
cd src/reaper-python
uv sync
```

主要依存: mido(MIDI書出) / numpy(計測) / reapy-next(REAPER制御) / isobar(将来のメロディ生成用) / reathon。

> **Python は 3.12 系に固定**（`pyproject.toml` の `requires-python = ">=3.11,<3.13"`）。
> reapy-next が依存する標準ライブラリ `lib2to3` は **Python 3.13 で削除された**ため、
> 3.13/3.14 では import に失敗する。これは OS 共通の CPython 仕様。
> システム既定が 3.13+ でも uv が自動で 3.12 を選ぶ。

#### reapy 連携

reapy-next は REAPER 内蔵の ReaScript Python 経由で動く dist API を使う。
**REAPER 起動中に**一度だけ初期設定する:

```bash
# REAPER を起動した状態で実行
uv run python -c "import reapy; reapy.configure_reaper()"
# REAPER を再起動すると設定が反映される
```

これで `reaper.ini` に Python ライブラリと reapy サーバーが自動設定される。接続確認:

```bash
uv run python -c "import reapy; print(reapy.Project().n_tracks)"
# REAPER と繋がっていればトラック数が表示される
```

> **dist API の制約**: `EnumProjectMarkers*` のような `char**` 出力は名前が取れない。
> リージョン名の読み取りには `GetRegionOrMarker` 系 (REAPER 7+) を使う
> （`kita/reaper/bridge.py:list_regions`）。

### CachyOS / Arch 系 Linux 固有

> 元は Windows 前提で構築。CachyOS 移行に伴う再構築メモ。
> このサブセクションが OS 固有部分。別 OS 運用時はここだけ差し替える。

#### REAPER 本体

```bash
sudo pacman -S reaper   # 公式 extra リポジトリ
```

REAPER の Python プラグインを使う場合は `python` パッケージが必要（CachyOS は標準導入）。

#### オーディオ (ALSA / JACK / PipeWire)

CachyOS は **PipeWire** が音声を統合管理している。REAPER は JACK 接続を前提に
起動するため、**PipeWire の JACK 互換ブリッジ**を使うのが最もシンプル。

```
アプリ (REAPER / ブラウザ ...)
  └─ サウンドサーバー: PipeWire ← JACK と PulseAudio を統合・置換
       └─ ALSA (カーネルのドライバ層)
            └─ オーディオハードウェア
```

**採用方針: PipeWire-JACK ブリッジ**（`jack2` ではなく `pipewire-jack`）

```bash
# jack2 が入っている場合は衝突するので pipewire-jack に置換する
# (両者は同じ libjack.so を提供するため共存不可)
sudo pacman -S pipewire-jack   # jack2 の削除を促されたら yes
```

- 利点: 低遅延を保ちつつ、REAPER とブラウザ等の音声を同時に鳴らせる。
  `jackd` を手動起動する必要がない。
- 確認: REAPER 起動後、`pw-cli ls Node | grep REAPER` で JACK クライアントとして
  登録されていれば正常。REAPER 側は Options → Preferences → Audio → Device で
  Audio system が JACK になっていること。

## ディレクトリ

| パス | 内容 |
|------|------|
| `song.py` | 曲の正本（DSL） |
| `kita/` | ライブラリ + CLI |
| `samples/` | 合成サンプル生成（wav は git 管理外） |
| `output/` | 生成 MIDI（git 管理外） |
