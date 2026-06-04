# reaper-python

pure Python + REAPER でトランスの一部を作るワークフロー（Issue #6）。
isobar で作曲 → MIDI 書き出し → reapy で REAPER を制御して再生する。

## 環境構築

OS 非依存の部分とプラットフォーム固有の部分を分けて記載する。
（現状の検証環境は CachyOS。Windows での運用は未定）

### OS 共通

#### Python 依存

```bash
cd src/reaper-python
uv sync
```

主要依存: isobar(作曲) / mido(MIDI書出) / reapy-next(REAPER制御) / reathon。

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

## ワークフロー

```bash
uv run python samples/gen_kick.py  # 合成サンプル生成 (samples/*.wav は git 管理外)
uv run python isobar/compose.py    # MIDI 生成
uv run python reaper/setup.py      # arrangement.toml に従いトラック調整 (冪等)
uv run python reaper/load.py       # REAPER に読込
uv run python reaper/transport.py loop 16
uv run python reaper/transport.py play
```

アレンジの正本は `arrangement.toml`。

> **サンプルについて**: 本来は Windows 上の Black Octopus サンプルを使うが、
> Linux 環境ではそれが無いため `samples/gen_kick.py` で合成キックを生成して代用する。
> `samples/*.wav` は再生成可能なため git 管理外。`setup.py` は全トラックのサンプル
> 実在を要求するので、ワークフロー実行前に必ず生成しておくこと。

## ディレクトリ

| パス | 内容 |
|------|------|
| `isobar/` | 作曲 (compose.py / patterns) |
| `reaper/` | REAPER 制御 (setup / load / transport / control / status) |
| `arrangement.toml` | アレンジ正本 |
| `spec.py` | arrangement.toml のローダ |
