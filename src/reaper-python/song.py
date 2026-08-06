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
    Sampler,
    Song,
    Synth,
    Track,
    progression,
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
# スケールの変更もこの1行で済む (degree 0=A, 4=E, 5=F, 6=G)。
# 進行は A→A→F→G = i–i–VI–VII。各 clip では ROOT が「その小節のルート」に解決される。
# スケールは固定でない — natural minor 等へ差し替えて候補を比べてよい。
# -----------------------------------------------------------------------------
PROG = progression("A", "phrygian", [0, 0, 5, 6])

# -----------------------------------------------------------------------------
# sub bass (Issue #13): <80Hz の重量感だけを担う根音。元は RS5k サンプル
#   (DPT_..._Rez.wav = 実質 55Hz サイン)だったが、Synth(sine) へ repatriate した
#   (doc/adr/001 synth-first)。理由: sim(kita check)はサンプラのピッチを模さないため、
#   ルート進行を追う音は synth で作れば <80Hz 量・ルート・kick 住み分けを完全検証できる。
#   転がりは midbass(#12)へ譲り、sub は 1小節1音の pedal(最小限の動き)で根音を支える。
#   ルートは PROG を共有(A→A→F→G)、octave1 で midbass のちょうど1オクターブ下
#   (A1=55/F2=87/G2=98Hz)。sustain=1.0 で持続する土台。
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
#   degrees は PROG のスケール度数 (0=A, 1=Bb, 2=C, 3=D, 4=E, 5=F, 7=A の1オクターブ上)。
#   durations は各音の拍数(合計32拍=8小節で1フレーズ)。
#   ここは #11 時点の「長めの音価のレガート単音」のまま。Phase 2 で
#   モチーフ反復 + 末尾変奏(repeat_vary)と 16分ゲート(rhythm)へ書き換える。
#   音色(resonant LPF / デチューンレイヤー)も Phase 2。
# -----------------------------------------------------------------------------
lead = Track("lead", Synth(wave="saw"), PROG.melody(
    [0, 1, 2, 3, 2, 1, 0, 4, 3, 1, 0,  0, 1, 2, 5, 4, 3, 4, 2, 1, 0],
    [2, 1, 1, 2, 1, 1, 2, 2, 2, 1, 1,  2, 1, 1, 2, 1, 1, 2, 2, 2, 2],
    octave=4, vel=100, gate=0.9,
), gain_db=-12.0)

CORE = DRUMS + [subbass, midbass, lead]

# 展開 (Issue #5, #2, #12): コアループ → drums を抜いた 8小節 breakdown
#   (sub + midbass + lead が主役) → コアループ。lead は全区間で鳴らし続ける。
song = Song(bpm=138, sample_root=SAMPLES, tracks=CORE, sections=[
    section("core_a", 16, CORE),
    section("breakdown", 8, [subbass, midbass, lead]),
    section("core_b", 16, CORE),
])
