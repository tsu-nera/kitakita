# ADR-001: agent 駆動 DTM では synth-first を既定にし、synth 由来サンプルは自前 synth へ repatriate する

## Status

Accepted (2026-07-19)

## Context

このリポジトリ（`src/reaper-python/`）の核心は「モデル（agent）は音を聴けない → `kita check` の
オフライン sim でミックスを数値検証する」ことにある。この制約下で音源を選ぶとき、判断軸は
「synth と sample のどちらが音がいいか」ではなく **「耳を持たない作者にとって、その音がどれだけ
legible（検証可能）か」** になる。

従来の DTM が sample-first なのは人間に耳があるからで、agent 前提だとこの前提が反転する。

- **synth（ReaSynth + JSFX）**: wave/cutoff/resonance/envelope をすべて agent が数値で設計する。
  sim は同じパラメータから完全再構成でき、`kita check` が真実を返す。**legible-by-construction**。
- **sample**: agent にとって不透明な blob。解析で測った量だけが見え、測っていない性質は不可視。
  さらに、pitch/chop 等の変形は 1つずつ sim にモデル化しないと「検証の穴」＝負債になる。
  実例として現状の sim（`_render_events`）はサンプラのピッチシフトを模していない（Issue #13 で
  この限界が表面化した）。

サンプルライブラリの中身は本質的に2種類ある。**録音由来**（生楽器・foley・実機の走り＝ synth で
安く再現できない）と、**synth 由来（rendered）**（誰かがシンセで作って WAV に焼いただけ＝定義上
再現可能で、freeze した瞬間に pitch/filter/envelope という一番欲しい可変性を捨てている）。
このプロジェクトの購入パック（"Trance Vision" 等）の bass/pluck/lead 系はほぼ後者。

## Decision

**agent 駆動 DTM では synth-first を既定とする。sample は「還元不能な音色キャラが今の synth palette
では届かない一点物」に限定し、synth 由来サンプルは届く範囲から順に自前 synth パッチへ repatriate
する。**

- 音源ごとの判定基準は provenance の推測ではなく **reachability**:
  「今ある synth palette で、その音の役割を定義する測定量（スペクトル/transient/pitch/envelope）に
  届くか?」。provenance は強い prior（サイン＋わずかな倍音、saw の倍音列＋レゾナンスピーク →
  ほぼ確実に synth 由来＝置換容易）だが、最終基準は解析で測れる target への到達可能性。
- 置き換えワークフローは provenance を推測せずに回す: **サンプルを reference target として解析
  → synth をそこへ寄せて合わせ込む → サンプルは捨てる**。
- 置き換えの上限は synth palette の広さに縛られる。今の palette（saw/square/tri/sine + JSFX
  resonant LPF 一枚）で届くもの（sub＝サイン、素の saw/square pluck、単純 LPF ベース）から
  repatriate し、届かないもの（supersaw/detune、saturation、multi-osc レイヤ）は palette を
  太らせるための reference として残す。**palette 拡張自体が置換可能領域を広げる投資**。

## Consequences

**良い点**

- ミックス判断が「不透明 blob 同士の相関」から「agent が設計した legible な音同士の推論」へ格上げされ、
  `kita check` の検証が真実に近づく。
- pitch/filter/envelope が freeze されず live parameter に戻るため、進行追従・音作りの改善が
  song.py 上の数値変更だけで可能になる。
- 解析（何がその音を良くしているかを測る力）への投資は、使うのが sample でも生成でも効くため将来まで
  価値が持続する。逆に巨大な sample 再生/chop パイプラインへの投資は生成が良くなるほど減価する。

**注意点 / トレードオフ**

- 現 palette は薄いため、質感の要る音は当面サンプルのまま残る。無理な synth 化は音の劣化を招く。
- 「reachability に届くか」の判断には解析（`kita bands` 等）が要り、感覚での即断はしない。
- provenance 不明なサンプルが多いので、判定は必ず測定に基づける（推測で synth 化しない）。

## 適用実績

- Issue #12: mid bass を ReaSynth(saw) + JSFX resonant LPF で新設（synth-first）。
- Issue #13: sub bass を RS5k サンプル（実質 55Hz サイン波）から Synth(sine) へ repatriate。
  sim が pitch を完全再現でき、`kita check` で低域量・ルート・kick 住み分けを検証可能にした。
