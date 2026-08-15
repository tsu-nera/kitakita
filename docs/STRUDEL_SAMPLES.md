# Strudel サンプル仕様書

このドキュメントでは、Strudelで使用できるサンプルの種類、読み込み方法、オフライン利用の方法について説明します。

## 目次

1. [デフォルトで使えるサンプル](#デフォルトで使えるサンプル)
2. [サンプルの読み込み方法](#サンプルの読み込み方法)
3. [オフライン利用（dough-samples）](#オフライン利用dough-samples)
4. [カスタムサンプル（@strudel/sampler）](#カスタムサンプルstrudelsampler)
5. [プロジェクト設定](#プロジェクト設定)

---

## デフォルトで使えるサンプル

Strudelはデフォルトで以下のサンプルを提供しています：

### 1. ドラムサンプル (tidal-drum-machines)

| サンプル名 | 説明 |
|-----------|------|
| `bd` | Bass drum (バスドラム/キック) |
| `sd` | Snare drum (スネア) |
| `hh` | Closed hi-hat (クローズドハイハット) |
| `oh` | Open hi-hat (オープンハイハット) |
| `cp` | Clap (クラップ) |
| `rim` | Rimshot (リムショット) |
| `cr` | Crash (クラッシュ) |
| `rd` | Ride (ライド) |
| `ht` | High tom (ハイタム) |
| `mt` | Medium tom (ミドルタム) |
| `lt` | Low tom (ロータム) |

### 2. パーカッション

- `shakers`, `maracas`, `cabasas`
- `cowbell` (カウベル)
- `tambourine` (タンバリン)
- その他多数

### 3. 楽器サンプル (VCSL)

- `piano` (ピアノ)
- `bass` (ベース)
- その他の楽器サンプル

### 4. その他

- `misc` (雑多なサンプル)
- `fx` (エフェクト音)

### サンプルの使い方

```javascript
// 基本的な使い方
s("bd sd hh oh")

// バリエーション指定（番号）
s("bd:0 bd:1 bd:2 bd:3")

// ピアノの例
note("c a f e").s("piano")

// 複数サンプルのスタック
stack(
  s("bd!4"),
  s("sd!8").gain(0.8),
  s("hh!16")
)
```

---

## サンプルの読み込み方法

### GitHub から読み込み（デフォルト）

```javascript
await initStrudel({
  prebake: () => samples('github:tidalcycles/Dirt-Samples'),
});
```

### 利用可能なサンプルの確認

公式Dirt-Samplesリポジトリで確認：
- https://github.com/tidalcycles/Dirt-Samples

各フォルダ名がサンプル名（`bd/`, `sd/`, `piano/` など）で、中に複数のバリエーションが格納されています。

---

## オフライン利用（dough-samples）

### 概要

**dough-samples** は、Strudelで使える包括的なサンプルコレクションです。

- リポジトリ: https://github.com/felixroos/dough-samples
- 含まれるサンプル:
  - tidal-drum-machines
  - Dirt-Samples
  - piano
  - EmuSP12
  - VCSL
  - mridangam

### セットアップ手順

#### 1. リポジトリのクローン

```bash
git clone --recurse-submodules https://github.com/felixroos/dough-samples.git
```

**重要**: `--recurse-submodules` オプションが必須です。

#### 2. サーバーの起動

```bash
cd dough-samples
npx serve -p 6543 --cors
```

これで `http://localhost:6543` でサンプルが配信されます。

**要件**: Node.js v20以上

#### 3. Strudelでの読み込み

```javascript
const base = 'http://localhost:6543';
await initStrudel({
  prebake: () => Promise.all([
    samples(base + '/tidal-drum-machines.json', base + '/tidal-drum-machines/machines/'),
    samples(base + '/piano.json', base + '/piano/'),
    samples(base + '/Dirt-Samples.json', base + '/Dirt-Samples/'),
    samples(base + '/EmuSP12.json', base + '/tidal-drum-machines/machines/'),
    samples(base + '/vcsl.json', base + '/VCSL/'),
    samples(base + '/mridangam.json', base + '/mrid/')
  ])
});
```

### メリット

- オフラインで使用可能
- すべてのサンプルにアクセス可能
- ロード時間の短縮（ローカルから読み込み）

---

## カスタムサンプル（@strudel/sampler）

### 概要

**@strudel/sampler** は、自分のサンプルフォルダをStrudelで使えるようにするツールです。

- npm: https://www.npmjs.com/package/@strudel/sampler
- バージョン: 0.2.3
- デフォルトポート: 5432

### セットアップ

#### 1. インストール

```bash
npm install @strudel/sampler
```

#### 2. サーバーの起動

```bash
npx @strudel/sampler path/to/your-samples
```

これで `http://localhost:5432` でサンプルが配信されます。

#### 3. 自動生成される設定

`@strudel/sampler` は、フォルダ構造から自動的に `strudel.json` を生成します。

生成内容は `http://localhost:5432` で確認できます。

#### 4. Strudelでの読み込み

```javascript
await initStrudel({
  prebake: () => samples('http://localhost:5432/strudel.json', 'http://localhost:5432/')
});
```

### 両方使う場合

```javascript
const dough = 'http://localhost:6543';
const custom = 'http://localhost:5432';

await initStrudel({
  prebake: () => Promise.all([
    // 既製サンプル（dough-samples）
    samples(dough + '/piano.json', dough + '/piano/'),
    samples(dough + '/Dirt-Samples.json', dough + '/Dirt-Samples/'),
    // カスタムサンプル
    samples(custom + '/strudel.json', custom + '/')
  ])
});
```

---

## プロジェクト設定

### ui/watch.html の設定

**ファイル**: `ui/watch.html` (78-81行目)

**デフォルト設定**:
```javascript
await initStrudel({
  prebake: () => samples('github:tidalcycles/Dirt-Samples'),
});
```

**dough-samples 使用時**:
```javascript
const base = 'http://localhost:6543';
await initStrudel({
  prebake: () => Promise.all([
    samples(base + '/tidal-drum-machines.json', base + '/tidal-drum-machines/machines/'),
    samples(base + '/piano.json', base + '/piano/'),
    samples(base + '/Dirt-Samples.json', base + '/Dirt-Samples/'),
    samples(base + '/EmuSP12.json', base + '/tidal-drum-machines/machines/'),
    samples(base + '/vcsl.json', base + '/VCSL/'),
    samples(base + '/mridangam.json', base + '/mrid/')
  ])
});
```

### vscode-strudel-bundle.js の設定

**ファイル**: `vscode-strudel-bundle.js` (31-33行目)

同様の変更を適用します。

---

## まとめ

| 方法 | 用途 | ポート | 設定 |
|------|------|--------|------|
| GitHub | デフォルト（オンライン） | - | `samples('github:tidalcycles/Dirt-Samples')` |
| dough-samples | オフライン利用（既製） | 6543 | `samples(base + '/xxx.json', base + '/xxx/')` |
| @strudel/sampler | カスタムサンプル | 5432 | `samples('http://localhost:5432/strudel.json', ...)` |

### 推奨設定

- **開発時**: dough-samples（オフライン、全サンプル利用可能）
- **本番/公開**: GitHub（サーバー不要）
- **カスタム音源**: @strudel/sampler（自分のサンプル使用）

---

## 参考リンク

- [Strudel 公式ドキュメント - Samples](https://strudel.cc/learn/samples/)
- [Dirt-Samples リポジトリ](https://github.com/tidalcycles/Dirt-Samples)
- [dough-samples リポジトリ](https://github.com/felixroos/dough-samples)
- [@strudel/sampler npm](https://www.npmjs.com/package/@strudel/sampler)
- [Strudel PWA ガイド](https://strudel.cc/learn/pwa/)
