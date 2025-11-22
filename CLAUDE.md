# Claude作業ログ

このファイルには、Claudeとの作業で行った設定や変更内容を記録します。

## VSCode拡張機能でStrudelサンプルをオンライン読み込み

**日付**: 2025-11-21
**目的**: VSCode拡張機能（roipoussiere.tidal-strudel）でdough-samplesをオンラインから読み込む

### 背景

- VSCodeでStrudel拡張機能を使用している
- デフォルトでは限定的なサンプルのみ利用可能
- dough-samplesをローカルサーバーで動かすのはサイズが大きいため断念
- GitHubから直接オンラインで読み込むように変更

### 実施した変更

#### 1. vscode-strudel-bundle.js の修正

**ファイル**: `vscode-strudel-bundle.js` (28-41行目)

**変更前**:
```javascript
await initStrudel({
  prebake: () => samples('github:tidalcycles/Dirt-Samples'),
});
```

**変更後**:
```javascript
// Initialize Strudel with dough-samples (online)
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

#### 2. piano.str の修正

**ファイル**: `src/strudel/piano.str`

**変更前**:
```javascript
async function loadSamples() {
  const ds = "https://raw.githubusercontent.com/felixroos/dough-samples/main/";
  return Promise.all([
    samples(`${ds}/tidal-drum-machines.json`),
    samples(`${ds}/piano.json`),
    samples(`${ds}/Dirt-Samples.json`),
    samples(`${ds}/EmuSP12.json`),
    samples(`${ds}/vcsl.json`),
    samples(`${ds}/mridangam.json`),
  ]);
}

note("c a f e").s("piano")
```

**変更後**:
```javascript
// pianoサンプルはui/watch.htmlで読み込み済み
note("c a f e").s("piano")
```

**理由**: サンプルの読み込みはvscode-strudel-bundle.jsで一括管理するため、.strファイル内での読み込みは不要。

### デプロイ手順

#### 1. ビルド

```bash
npm run build:vscode
```

これで `dist-vscode/strudel.js` が生成されます。

#### 2. VSCode拡張機能へコピー

```bash
# バックアップ（任意）
cp ~/.vscode/extensions/roipoussiere.tidal-strudel-0.2.1/dist/strudel.js \
   ~/.vscode/extensions/roipoussiere.tidal-strudel-0.2.1/dist/strudel.js.old

# 新しいビルドをコピー
cp dist-vscode/strudel.js \
   ~/.vscode/extensions/roipoussiere.tidal-strudel-0.2.1/dist/strudel.js
```

**Windowsの場合**:
```bash
cp dist-vscode/strudel.js \
   /c/Users/fox10/.vscode/extensions/roipoussiere.tidal-strudel-0.2.1/dist/strudel.js
```

#### 3. VSCodeをリロード

`Ctrl+Shift+P` → "Developer: Reload Window"

### 利用可能なサンプル

変更後、以下のサンプルが利用可能：

- **tidal-drum-machines**: bd, sd, hh, oh, cp など
- **piano**: piano:0, piano:1, piano:2 など
- **Dirt-Samples**: 全てのTidalCyclesサンプル
- **EmuSP12**: エミュレーターサンプル
- **VCSL**: 楽器サンプル
- **mridangam**: ムリダンガムサンプル

### 使用例

```javascript
// ピアノ
note("c a f e").s("piano")

// ドラム
s("bd sd hh oh")

// 複雑なパターン
stack(
  s("bd!4"),
  s("sd!8").gain(0.8),
  note("c e g").s("piano")
)
```

### トラブルシューティング

#### サンプルが読み込まれない場合

1. ビルドが最新か確認:
   ```bash
   ls -lh dist-vscode/strudel.js
   ```

2. 拡張機能のファイルが更新されているか確認:
   ```bash
   md5sum dist-vscode/strudel.js \
          ~/.vscode/extensions/roipoussiere.tidal-strudel-*/dist/strudel.js
   ```

   両方のハッシュ値が一致していること。

3. VSCodeをリロードしたか確認

4. ブラウザのコンソールでエラーを確認:
   - `Ctrl+Shift+P` → "Developer: Toggle Developer Tools"
   - Console タブでエラーメッセージを確認

#### オフラインで使いたい場合

dough-samplesをローカルで動かす方法は `doc/STRUDEL_SAMPLES.md` を参照。

### 注意事項

- **ui/watch.html**: ブラウザモードを使う場合のみ修正が必要。VSCodeのみ使用する場合は修正不要。
- **バージョンアップ時**: VSCode拡張機能がアップデートされた場合、再度コピーが必要。
- **オンライン接続**: サンプルをGitHubから読み込むため、初回はインターネット接続が必要。その後はブラウザキャッシュで動作。

### 関連ドキュメント

- [STRUDEL_SAMPLES.md](doc/STRUDEL_SAMPLES.md) - サンプル仕様書
- [dough-samples リポジトリ](https://github.com/felixroos/dough-samples)
- [VSCode拡張機能](https://marketplace.visualstudio.com/items?itemName=roipoussiere.tidal-strudel)

---

## 今後の作業メモ

- [ ] 他のサンプルバンク（Freesound等）の追加を検討
- [ ] カスタムサンプルの管理方法を整理（@strudel/sampler使用）
- [ ] サンプルのプリロード最適化
