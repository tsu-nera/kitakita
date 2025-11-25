# VSCode Strudel拡張機能 カスタムビルド

## 概要

`roipoussiere.tidal-strudel` 拡張機能をカスタムビルドし、dough-samplesをオンライン読み込みするよう変更済み。

## ビルド・デプロイ

```bash
# ビルド
npm run build:vscode

# 拡張機能へコピー（Windows）
cp dist-vscode/strudel.js \
   /c/Users/fox10/.vscode/extensions/roipoussiere.tidal-strudel-0.2.1/dist/strudel.js

# VSCodeをリロード
# Ctrl+Shift+P → "Developer: Reload Window"
```

## 変更箇所

**ファイル**: `vscode-strudel-bundle.js`

```javascript
const ds = 'https://raw.githubusercontent.com/felixroos/dough-samples/main/';
await initStrudel({
  prebake: () => Promise.all([
    samples(`${ds}tidal-drum-machines.json`, `${ds}tidal-drum-machines/machines/`),
    samples(`${ds}piano.json`, `${ds}piano/`),
    samples(`${ds}Dirt-Samples.json`, `${ds}Dirt-Samples/`),
    samples(`${ds}EmuSP12.json`, `${ds}tidal-drum-machines/machines/`),
    samples(`${ds}vcsl.json`, `${ds}VCSL/`),
    samples(`${ds}mridangam.json`, `${ds}mrid/`)
  ])
});
```

## 注意

- 拡張機能アップデート時は再デプロイが必要
- 初回はインターネット接続が必要（以降はキャッシュ）
