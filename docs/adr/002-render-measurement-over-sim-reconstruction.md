# ADR-002: 耳を持たない agent の検証正本は REAPER 実レンダの計測（Path A）とし、sim 再構成（Path B）は採らない

## Status

Accepted (2026-08-27)

## Context

Issue #31: `kita check` はこれまで sim.py がオフラインで音を再構成し、その上で計測していた。
だが sim は REAPER の全 FX/エンベロープ/スケーリングを Python で再実装する必要があり、
乖離のたびに sim 側を直すコストが積み上がる（例: `kita-sim-no-sampler-pitch` — RS5k の
ピッチシフトを sim は見えない。`reaper-volume-envelope-fader-scaling` — envelope の
scaling mode を sim が正しく模していないと無音化を検出できない）。

選択肢は2つだった。

- **Path B（sim 再構成）**: sim.py を REAPER の signal path により忠実に近づけ続ける。
  差分が出るたびに個別対応が要り、REAPER 側の挙動を後追いし続ける宿命がある。
- **Path A（実レンダ計測）**: REAPER 自身にレンダさせ、出力 wav を計測する。REAPER の
  signal path をそのまま使うので「sim が REAPER と一致しているか」という問いが消える。

Path A を採らなかった理由はこれまで「レンダの自動実行がダイアログで無期限にハングし得る」
という運用上のリスクだった。2026-08-27 に走行中 REAPER v7.78 + reapy で以下を実測し、
この障害を解消できることを確認した。

1. **ReaSynth のレンダが通る**（最後の関門）。ReaSynth を挿した2トラック（A4/E5）を
   レンダし、FFT 支配周波数が 440.00 Hz / 659.00 Hz（期待 659.26、FFT 分解能内）で一致。
   ステム書き出しも通り、master = sum(stems) の誤差 -90.3 dBFS。
2. **実曲（111.3秒 / 10トラック）のレンダ時間**: master 1.06秒、stems 11本 4.62秒。
   現行 `kita check`(sim) は 4.2秒なので互角以上— Path A へ移しても計測サイクルは
   遅くならない。
3. **レンダアクションは 42230**。`41824` は auto-close ではない
   （`kbd_getTextFromCmd` で確認）:
   - `41824` = File: Render project, using the most recent render settings
   - `42230` = File: Render project, using the most recent render settings,
     auto-close render dialog
4. **ダイアログ問題の解法**（Consequences 参照）。予防層＋番犬層の2層で、ダイアログ0の
   平常時5/5、意図的にハングを誘発したケースも20秒で明示的な失敗として復旧できることを
   確認した。

## Decision

**耳を持たない agent が音を判断する正本は、REAPER 自身のレンダを計測する Path A とする。**
`src/reaper-python/kita/reaper/render.py` が REAPER にレンダを投げ、出力 wav を
`kita render --reaper` から取得できるようにする。ダイアログでの無期限ハングは
予防層＋番犬層の2層対策で構造的に防ぐ。

sim.py の計測部（RMS / 帯域 / peak / セクション別エネルギー）は Path A の出力 wav に
対してもそのまま使う。変わるのは「その wav をどう作るか」（sim の合成 → REAPER の
実レンダ）だけで、計測ロジック自体に変更はない。

sim.py の合成部（signal path の Python 再実装）を実際に削って Path A へ完全移行する
作業は本 ADR のスコープ外。別 issue で扱う規模の変更のため、ここでは「Path A が
使えること」の確立までとする。

## Consequences

**良い点**

- sim を REAPER の signal path に追従させ続ける負債が消える。REAPER 自身がレンダするので
  FX/エンベロープ/スケーリングの再実装・乖離修正が不要になる。RS5k ピッチシフトのような
  「sim が見えない」既知の穴も、実レンダなら原理的に存在しない。
- 計測サイクルの速度は sim と同等かそれ以上（実曲で master 1.06秒 / stems 4.62秒 vs
  sim 4.2秒）。

**注意点 / トレードオフ**

- **ダイアログ問題とその2層対策**（本決定を可能にした中核）。レンダ中に REAPER が
  ダイアログを出すと reapy API ごと無応答になり、タイムアウトが無く無期限に待つ。
  モーダル中は `reapy.connect()` すら返らない。**内側(reapy)からは復旧できない** —
  復旧できるのはウィンドウ操作（niri の `close-window`）だけ。対策は2層:
  - 層1 予防: 出力先の既存 wav をレンダ前に消す（上書き確認を原理的に出さない）。
    アクションは 42230 (auto-close) を使う。
  - 層2 番犬: reapy 呼び出しを別スレッドへ投げ、メインスレッドが niri へポーリングし、
    REAPER のメイン窓でない窓が居座ったらダイアログとみなして閉じる。この経路は
    reapy を一切使わない（reapy 越しに閉じようとすると、固まっている当の API を
    叩くことになり番犬自身も一緒に固まる — 実際に踏んだ）。タイムアウトしたら
    良性窓（進捗窓）も含めて全部閉じ、明示的な失敗として返す。良性リストは平常時の
    判定にしか使えない — REAPER は "Rendering to file..." のタイトルのまま固まる
    ことがある（出力先が書き込み不可のときに実測で再現）。
  層1だけで平常時5/5ダイアログ0。層2は書き込み不可ディレクトリでハングを誘発した
  ケースを20秒で失敗として返し、残骸を片付けた直後の通常レンダも1.07秒で成功した。
- REAPER の実起動が前提になる。`compose` / `check` / `render`(sim) はオフラインで
  動く既存の約束を壊さないよう、`kita render --reaper` は reapy import をこの
  分岐の中だけに閉じる。
- レンダは REAPER の現在のプロジェクト状態（`kita sync` で反映済みのもの）を対象にする。
  song.py と REAPER 側の drift があれば計測結果も drift する（`kita status` で
  別途検出する既存の責務のまま）。

## 適用実績

- `src/reaper-python/kita/reaper/render.py` を新設。`kita render <out> --reaper`
  [--stems] から呼べる。
- スモークテスト: 実曲(10トラック)で master 1.07秒 / stems 11本 4.53秒。ダイアログ
  残留なし。
