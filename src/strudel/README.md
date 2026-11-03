# strudel

Strudel（ライブコーディング音楽環境）のパターンファイル（`.str`）。Tidal は `src/tidal/`。
参照用の Strudel リポジトリは `tmp/strudel/`（git 非追跡）。

## ドキュメント検索

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

## VSCode拡張機能

Strudel / Tidal の編集は `roipoussiere.tidal-strudel` 拡張機能を使用。
カスタムビルドの詳細は [docs/VSCODE_STRUDEL.md](../../docs/VSCODE_STRUDEL.md) を参照。

## 利用可能なサンプル

dough-samplesをオンライン読み込み設定済み：
- tidal-drum-machines (bd, sd, hh, oh, cp)
- piano
- Dirt-Samples
- EmuSP12
- VCSL
- mridangam
