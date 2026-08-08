# =============================================================================
# song.py — この曲の「正本(source of truth)」
#
# ここを編集すれば compose / sync / load / status / check すべてに反映される。
# Reaper は描画先(片方向)。手で Reaper を編集しても正本はここ。
#
# 反映フロー:
#   uv run kita compose   # song -> output/*.mid 生成
#   uv run kita sync      # トラック/バス/BPM/リージョンを冪等反映
#   uv run kita load      # output/*.mid を各トラックへ流し込み
#   uv run kita check     # 聴かずに計測(バランス + セクション別エネルギー)
# =============================================================================
from kita import (
    ROOT,
    Duck,
    Reverb,
    Sampler,
    Song,
    Synth,
    Track,
    gated,
    motif,
    progression,
    repeat_vary,
    rhythm,
    section,
    steps,
)

# 各トラックの sample はここからの相対パス。
# Windows 復帰時の元パス: 'C:\\Users\\fox10\\Music\\Samples\\Black Octopus\\Trance Vision'
# 合成音源で代用する場合: 'samples' (samples/gen_kick.py 等で生成)
SAMPLES = "/mnt/shared/DTM/Samples/Black Octopus/Trance Vision"

# -----------------------------------------------------------------------------
# オーソドックスなトランス・ドラム (16分グリッド):
#   step:  1 e & a 2 e & a 3 e & a 4 e & a
#   kick   x . . . x . . . x . . . x . . .   4つ打ち
#   clap   . . . . x . . . . . . . x . . .   2拍4拍
#   ohat   . . x . . . x . . . x . . . x .   オフビート・オープンハット
# -----------------------------------------------------------------------------

kick = Track("kick", Sampler("Drum - Kick - One Shots/DPT_Kick_One_Shot_Acidtech.wav"),
             steps("x...x...x...x...", vel=120), gain_db=-8.0, group="drums")
clap = Track("clap", Sampler("Drum - Clap - One Shots/DPT_Clap_One_Shot_Sola.wav"),
             steps("....x.......x...", vel=105), gain_db=-10.8, group="drums")
ohat = Track("ohat", Sampler("Drum - Hat Open - One Shot/DPT_Hat_Open_One_Shot_Azureshort.wav"),
             steps("..x...x...x...x.", vel=95), gain_db=-12.0, group="drums")
DRUMS = [kick, clap, ohat]

# -----------------------------------------------------------------------------
# 調性の唯一の定義 (Issue #2)。キー・スケール・小節ごとのルート度数をここだけに置き、
# subbass / midbass / lead が共有する。ルートの不一致が構造的に起きず、キーや
# スケールの変更もこの1行で済む (degree 0=A, 2=C, 5=F, 6=G)。
# 進行は Am→F→C→G = i–VI–III–VII。各 clip では ROOT が「その小節のルート」に解決される。
# 当初の A phrygian (i–i–VI–VII) は 2度の Bb が効きすぎてエキゾチックに寄るため不採用。
# natural minor の i–VI–III–VII は 90年代トランスで最も多い進行。
# -----------------------------------------------------------------------------
PROG = progression("A", "minor", [0, 5, 2, 6])

# -----------------------------------------------------------------------------
# sub bass (Issue #13): <80Hz の重量感だけを担う根音。元は RS5k サンプル
#   (DPT_..._Rez.wav = 実質 55Hz サイン)だったが、Synth(sine) へ repatriate した
#   (doc/adr/001 synth-first)。理由: sim(kita check)はサンプラのピッチを模さないため、
#   ルート進行を追う音は synth で作れば <80Hz 量・ルート・kick 住み分けを完全検証できる。
#   転がりは midbass(#12)へ譲り、sub は 1小節1音の pedal(最小限の動き)で根音を支える。
#   ルートは PROG を共有(Am→F→C→G)、octave1 で midbass のちょうど1オクターブ下
#   (A1=55/F1=44/C2=65/G2=98Hz)。sustain=1.0 で持続する土台。
#   ducking(#16): kick 拍で -9dB へ沈める beat-locked volume envelope を付け、
#   kick との加算を切ってから gain_db を -13.0 → -11.0 へ引き上げた(#13 時点の
#   天井は sidechain 非モデルだったための制約で、ducking 導入で外れた。sub の
#   低域絶対量が kick を上回らない範囲でのキャップは kita check で確認済み)。
# -----------------------------------------------------------------------------
subbass = Track("subbass", Synth(wave="sine", sustain=1.0), PROG.melody(
    [ROOT], [4],             # 1小節1音の pedal。ROOT は小節ごとに進行を追う
    octave=1, vel=100, gate=0.92,
), gain_db=-11.0, duck=Duck("kick", depth_db=-14.0, attack=0.01, release=0.30))

# -----------------------------------------------------------------------------
# mid bass (Issue #12): 中域(250–800Hz)の「転がるベース」を ReaSynth(saw) で新設。
#   sub は <80Hz 担当、midbass が中域を埋める。
#   リズム: 各拍 [休符, 16分×3] で kick 裏を転がす(頭を休符にして kick と住み分け)。
#   octave2(A2≈110Hz)で基音は低いが saw 倍音が 250–800Hz を満たす。
#   sustain=0.0 + gate=0.55 でプラッキーな短い減衰=転がり。
#   ReaSynth はフィルタ非搭載のため後段に JSFX resonant LPF(cutoff/resonance)を挿す。
#   ルート進行は subbass と同じ PROG。1小節ぶんの刻みを書けば、以降の小節は
#   clip 側がループしつつ ROOT を各小節のルートへ解決する。
#   → 音作り(saw→envelope→filter)はここで確立し、lead(#2) の音色改善へ流用する。
midbass = Track(
    "midbass",
    Synth(wave="saw", sustain=0.0, cutoff=1000, resonance=0.35),
    PROG.melody(rhythm(".xxx .xxx .xxx .xxx"), octave=2, vel=100, gate=0.55),
    gain_db=-7.0, duck=Duck("kick", depth_db=-14.0, attack=0.01, release=0.30))

# -----------------------------------------------------------------------------
# lead: トランスリード (Issue #2)。RS5k は C4 固定でメロディ不可のため ReaSynth(saw)。
#   degrees は PROG のスケール度数 (0=A, 2=C, 3=D, 4=E, 5=F, 6=G, 7=A の1オクターブ上)。
#   旋律 MELODY は 4小節 = 「各小節で動いて2拍伸ばす」形。跳躍は bar3 の E→A だけで、
#   残りは順次進行。repeat_vary で 8小節にし、最後の小節だけ末尾を C→A へ変えて閉じる。
#   各小節に2拍の持続音があるのが要点で、これが gated / arped を掛ける「地」になる
#   (刻みの多い素材だと旋律側の刻みと変換が衝突して効かない)。
#   展開はこの1素材へ変換を適用してブロックを差し替える形で作る。
#   リバーブ(#4): room0.80 = T60 2.4s ≈ 1.4小節。各小節の2拍持続音が次の小節まで
#   尾を引く長さで、トランスの「空間」の定番域。send は控えめの -9dB から。
#   ハイパスは 300Hz(lead は低域をほぼ持たないので実測差は出ないが、音域を下げた
#   ときに土台を濁さないための保険)。リバーブは Track に付くので、drop で
#   lead_gated へ差し替えても同じ量が掛かる — 16分の隙間を残響が埋める。
# -----------------------------------------------------------------------------
MELODY = repeat_vary(
    motif([4, 3, 4], [1, 1, 2]) + motif([5, 4, 2], [1, 1, 2])     # Am / F
    + motif([4, 7, 6], [1, 1, 2]) + motif([6, 4, 3], [1, 1, 2]),  # C  / G
    2, motif([2, 0], [1, 2]))

lead = Track("lead", Synth(wave="saw"),
             PROG.melody(MELODY, octave=4, vel=100, gate=0.9), gain_db=-12.0,
             reverb=Reverb(room_size=0.80, damping=0.4, send_db=-9.0, hpf=300))

# lead の変奏 (Issue #2)。MELODY 1本へ変換を掛けたものをセクションで差し替える。
#   arped(root-3度-5度への分解)は不採用 — 和音を駆け上がる走句になってチップチューン風に
#   寄り、トランスらしさが消える。gated は音程を動かさず時間軸だけを刻むので、和声が
#   静止したまま推進力だけが増える。
#   gate を 0.9 → 0.7 に下げるのは、16分に刻むと音価が短く隣と詰まるため。
GATE16 = "x.xx x.xx x.xx x.xx"
lead_gated = PROG.melody(gated(MELODY, GATE16), octave=4, vel=100, gate=0.7)

CORE = DRUMS + [subbass, midbass, lead]

# 展開 (Issue #5, #2, #12): トランスの定石 core → breakdown → build → drop。
#   drums の抜き差しと lead の articulation を別々に動かし、drop で初めて両方が揃う。
#     core_a    full,  lead=plain   旋律の提示
#     breakdown drums 抜き, plain   旋律だけを聴かせる
#     build     kick+clap 復帰, plain  ohat はまだ入れず「戻りきっていない」感を残す
#     drop      full,  lead=gated   ohat が戻り lead が16分ゲートへ = 唯一の全部入り
#   lead は全区間 MELODY 1本で、変わるのは articulation だけ。
song = Song(bpm=138, sample_root=SAMPLES, tracks=CORE, sections=[
    section("core_a", 16, CORE),
    section("breakdown", 8, [subbass, midbass, lead]),
    section("build", 8, [kick, clap, subbass, midbass, lead]),
    section("drop", 8, CORE, override={lead: lead_gated}),
])
