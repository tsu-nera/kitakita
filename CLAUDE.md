# Claude Code 設定

このプロジェクトはStrudel（ライブコーディング音楽環境）を使った音楽制作環境です。

## Strudelドキュメント検索

Strudelの関数・文法について質問されたら、**Web検索ではなくローカルドキュメントを検索**してください。

### 検索場所

```
tmp/strudel/website/src/pages/
```

### 検索コマンド例

```bash
# 関数名で検索（例: fit）
grep -r "\.fit\(" tmp/strudel/website/src/pages/

# トピックで検索（例: duck）
grep -r "duck" tmp/strudel/website/src/pages/learn/
```

### 主要ファイル

| トピック | ファイル |
|---------|---------|
| サンプル操作 (fit, loopAt, chop) | `learn/samples.mdx` |
| エフェクト | `learn/effects.mdx` |
| シンセ | `learn/synths.mdx` |
| ミニノーテーション | `learn/mini-notation.mdx` |
| スケール・音階 | `learn/tonal.mdx` |
| 時間操作 | `learn/time-modifiers.mdx` |
| レシピ・実践例 | `recipes/recipes.mdx` |

## REAPERドキュメント検索

`src/reaper-python/` はコード駆動（isobar 作曲 → MIDI → reapy で REAPER 制御）。
REAPER の関数・API について質問されたら、**Web検索でなくローカルを検索**してください。
（GUI の操作手順だけはローカルに無いため Web 検索可）

### 検索場所（優先度順）

| 層 | 検索場所 |
|----|---------|
| reapy-next / isobar / mido / reathon の API（最頻出） | `src/reaper-python/.venv/lib/python3.12/site-packages/{reapy,isobar,mido,reathon}/` |
| ReaScript API（reapy が薄く下層 `RPR_*` を直接呼ぶとき） | `tmp/reaper/reascripthelp.html` |

### 検索コマンド例

```bash
# reapy のメソッドを探す（例: add_track）
grep -rn "def add_track" src/reaper-python/.venv/lib/python3.12/site-packages/reapy/

# ReaScript API を探す（例: tempo 関連の RPR_ 関数）
grep -i "RPR_.*Tempo" tmp/reaper/reascripthelp.html
```

> MCP は導入しない。reapy 接続（`reapy.configure_reaper()` 設定済み）を直接叩くのが上位互換のため（Issue #8）。

## プロジェクト構成

- `src/strudel/` - Strudelパターンファイル (.str)
- `src/reaper-python/` - pure Python + REAPER ワークフロー（isobar/reapy）
- `tmp/strudel/` - Strudelリポジトリ（ドキュメント参照用、git 非追跡）
- `tmp/reaper/` - ReaScript API ドキュメント（git 非追跡）
- `doc/` - プロジェクトドキュメント

## VSCode拡張機能

このプロジェクトは `roipoussiere.tidal-strudel` 拡張機能を使用。
カスタムビルドの詳細は [doc/VSCODE_STRUDEL.md](doc/VSCODE_STRUDEL.md) を参照。

## 利用可能なサンプル

dough-samplesをオンライン読み込み設定済み：
- tidal-drum-machines (bd, sd, hh, oh, cp)
- piano
- Dirt-Samples
- EmuSP12
- VCSL
- mridangam
