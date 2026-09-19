# ADR-003: 音源は pedalboard + VST3 (Surge XT) のオフライン合成とし、REAPER を音源から外す

## Status

Accepted (2026-09-19)

## Context

Issue #39。REAPER の評価期間が切れると**期限切れのナグ画面が出る。ダイアログは reapy API
ごと無期限にハングさせる**（ADR-002 の Consequences。#34 はこの対策に丸ごと費やされた）。
つまり期限切れ = 自動化の停止であり、ADR-002 が置いた「REAPER 実レンダを検証正本にする」
という決定の前提そのものが崩れる。

一方で REAPER が実際に担っているのは **ReaSynth / ReaSamplomatic5000 / JSFX の3つだけ**。
サンプル再生（kick / clap / ohat / transition FX）は sim が既に正しく行っており、
プラグインを要しない。必要なのはシンセ（subbass / midbass / lead×3 / pads）とフィルタだけ。

`pedalboard` は既に依存に入っており（0.9.24）VST3 をホストできる。**プラグインの出力
そのものが製品になるなら、ADR-002 が解こうとした「sim ≠ 実機」という問いは定義上消える。**
これが成り立つかどうかが後続の設計判断すべての土台になるため、実測で確かめた。

### 実測（2026-09-19、Surge XT 1.3.4-7 / pedalboard 0.9.24 / Python 3.12.13）

`extra/surge-xt-vst3` を導入（`/usr/lib/vst3/Surge XT.vst3`）。検証スクリプトは
`src/reaper-python/tmp/vst3_probe{,2,3,4,5,6}.py`（非追跡）。

**1. ロード** — `load_plugin` は GUI 無しで通る。`VST3Plugin` / `is_instrument=True` /
`parameters` 775 個。**1インスタンスあたり約 5 秒**。

**2. ピッチ** — 単音を合成して FFT（放物線補間）で基音を実測。

| note | 期待 | 実測 | 誤差 |
|---|---|---|---|
| 45 (A2) | 110.00 Hz | 110.00 Hz | +0.0 cent |
| 57 (A3) | 220.00 Hz | 220.00 Hz | +0.0 cent |
| 69 (A4) | 440.00 Hz | 440.00 Hz | +0.0 cent |
| 72 (C5) | 523.25 Hz | 523.18 Hz | -0.2 cent |

**3. song.py の MELODY** — `track_events(song, lead)` をそのまま渡し、24 イベントを合成。
16 ノートすべてで誤差 **±0.5 cent 以内**（25 cent 超は 0 / 16）。発音区間は 20（レガートで
連結されるため 24 未満）、最終発音 13.86s は指定尺 15.83s に収まる。尺も
`note_off @0.25/1.0/2.0s` に対し発音終了 0.28/1.03/2.03s で一致（差はリリース尾）。

**4. 速度** — lead 1本・全曲 64小節（111.3秒）が **1.26–1.48 秒**（realtime x75–88）。

| | 時間 |
|---|---|
| sim（全曲・全トラック） | 3.9 s |
| REAPER 実レンダ（master） | 1.07 s |
| pedalboard + Surge XT（lead 1本） | 1.32 s |
| pedalboard + Surge XT（シンセ6本、ロード除く） | 9.92 s |
| 同（プラグイン6本のロード込み・初回） | 39.9 s |
| 同（インスタンス使い回し・2回目） | 8.4 s |

**ロードが支配的**（6本で 30 秒）。プロセスを使い回せば 8.4 秒まで落ちる。

**5. パラメータ** — 775 個すべて属性としてコードから読み書きでき、音が実際に変わる。

```
a_filter_1_type = 'LP 24 dB' として a_filter_1_cutoff を振ったときのスペクトル重心:
  cutoff=  100 Hz -> centroid   104.0 Hz   RMS -39.71 dBFS
  cutoff=  800 Hz -> centroid   273.4 Hz   RMS -25.13 dBFS
  cutoff= 8012 Hz -> centroid  1583.6 Hz   RMS -23.90 dBFS
  cutoff=20027 Hz -> centroid  3297.5 Hz   RMS -23.82 dBFS
```

波形は `a_osc_1_type`（Classic / Sine / Wavetable / FM3 ... 12種）で切り替わる。

**6. フィルタ** — `pedalboard` 内蔵に `LowpassFilter` / `HighpassFilter` / `LadderFilter` /
`PeakFilter` / `HighShelfFilter` / `LowShelfFilter` / `IIRFilter` がある。
`LowpassFilter(800Hz)` を通すと 2–6kHz が -12.8 dB、6–16kHz が -22.6 dB（100–400Hz は
-0.27 dB）。シンセ内蔵フィルタと合わせて **#33 の LPF はこれで賄える**。

## Decision

**音源を pedalboard + VST3（Surge XT）のオフライン合成に置き、REAPER を音源から外す。**
sim と同じプロセス内でシンセを鳴らし、その出力をそのまま製品とする。

**ADR-002 は本 ADR が置き換える。** ADR-002 の「実レンダを検証正本にする（Path A）」は
「sim の再構成音と実機が一致しない」という問題を解くためのものだった。合成しているのが
製品そのものになる以上、一致させるべき「実機」が存在しない。ADR-002 の計測ロジック
（RMS / 帯域 / peak / セクション別エネルギー）はそのまま使える — 変わるのは wav の作り方だけ、
という ADR-002 自身の整理がここでも成り立つ。

## Consequences

**良い点**

- DAW / GUI / 起動待ち / ライセンス / ダイアログ番犬（#34 の2層対策）がすべて不要になる。
  ADR-002 が「最大のトレードオフ」と書いた**ヘッドレス不可の制約が消える** — CI でも
  夜間バッチでも回せる。
- sim を REAPER の signal path に追従させる負債が消える。`kita-sim-no-sampler-pitch` /
  `reaper-volume-envelope-fader-scaling` のような「sim が見えない穴」は原理的に無くなる。
- ReaSynth では作れなかったものが作れる（unison / wavetable / 2オシレータ / 内蔵エフェクト）。
  #2 のデチューンレイヤー方式は Surge の unison で置き換えられる可能性がある（未検証）。

**注意点 / 確認済みの落とし穴**

- **velocity は既定パッチで一切効かない。** `a_velocity_vca_gain` が既定 0.0 dB で、
  この状態では vel 1 と 127 の RMS が同値（幅 0.00 dB）。負の値を入れて初めて効く:

  | `a_velocity_vca_gain` | vel 1 | vel 32 | vel 64 | vel 100 | vel 127 | 幅 |
  |---|---|---|---|---|---|---|
  | 0.0 dB | -23.68 | -23.67 | -23.68 | -23.67 | -23.67 | 0.00 dB |
  | -12.0 dB | -35.55 | -32.65 | -29.63 | -26.23 | -23.67 | 11.88 dB |
  | -24.0 dB | -47.48 | -41.62 | -35.58 | -28.77 | -23.67 | 23.81 dB |
  | -48.0 dB | -71.30 | -59.58 | -47.49 | -33.88 | -23.67 | 47.62 dB |

  song.py は velocity で強弱を書き分けている（例: Hit は 127、lead は 100）。
  **このパラメータを設定しない限り、その書き分けは無視される。**

- **既定では合成が決定的でない。** 同じ MIDI を2回レンダすると波形の最大差が -9.7 dBFS
  （bit 一致せず）。オシレータの開始位相がフリーランのため。
  `a_osc_{1,2,3}_retrigger` を True にすると **-136.4 dBFS（float32 の量子化雑音レベル）**
  まで落ち、実質決定的になる。**レンダを再現可能にしたいなら retrigger は必須。**
  なお非決定のままでも RMS は ±0.006 dB、振幅スペクトルは相対 4.6e-4 で再現するので、
  計測（`kita check`）は retrigger 無しでも成立する。壊れるのは bit 比較の回帰テストだけ。

- **`raw_state` / `preset_data` の書き戻しは効かない。** getter は動く（67253 B / 50450 B）が、
  別インスタンスへ代入してもパラメータは既定値のまま（例外も出ず黙って無視される）。
  同一インスタンスへ戻しても同じ。**パッチの永続化はパラメータ値の dict で行う。**
  工場パッチの `.fxp`（`/usr/share/surge-xt/patches_factory/`、637個）も `load_preset` が
  `RuntimeError: Plugin failed to load data from preset file` で失敗する。
  → **音色はコード上のパラメータ辞書で定義する**（song.py が正本、という既存方針と整合）。

- **775 個の一括書き戻しは 33 個が失敗する。** getter が表示文字列を返す一方 setter が
  それを受け取らないパラメータがあるため（`a_amp_eg_decay` は `'250.0 ms'` を返すが
  同じ値を代入すると ValueError、`a_filter_1_subtype` も同様）。必要なパラメータだけを
  明示的に列挙して設定する運用にすれば踏まない。

- **プラグインのロードが 1本あたり約5秒、6本で30秒。** 合成自体（9.9秒）より重い。
  長命プロセスでインスタンスを使い回す前提にする（使い回せば2回目は 8.4 秒）。
  毎回プロセスを立ち上げる CLI 設計だと 40 秒コースになる。

- **Surge XT という外部パッケージへの依存が増える**（`extra/surge-xt-vst3`、
  `surge-xt-common` が 367 MB）。REAPER 依存と違ってライセンス期限も GUI も無いが、
  ゼロにはならない。VST3 が見つからない環境でのフォールバックは未設計。

- **未検証のまま残すもの**: Surge の unison が #2 のデチューンレイヤーを置き換えられるか、
  sidechain duck（#現行の Duck）をこの経路でどう作るか、サンプル系トラックとの
  ミックス/バスの組み立て。いずれも本 ADR の射程外。

## 適用実績

まだ無い。本 ADR は「できること」の確立までで、`kita` への組み込みは別 issue で行う。
