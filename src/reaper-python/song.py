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
from kita import Sampler, Song, Synth, Track, melody, section, steps

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
#   bass   . . x . . . x . . . x . . . x .   オフベース (kickの裏)
# -----------------------------------------------------------------------------

kick = Track("kick", Sampler("Drum - Kick - One Shots/DPT_Kick_One_Shot_Acidtech.wav"),
             steps("x...x...x...x...", vel=120), gain_db=-8.0, group="drums")
clap = Track("clap", Sampler("Drum - Clap - One Shots/DPT_Clap_One_Shot_Sola.wav"),
             steps("....x.......x...", vel=105), gain_db=-10.8, group="drums")
ohat = Track("ohat", Sampler("Drum - Hat Open - One Shot/DPT_Hat_Open_One_Shot_Azureshort.wav"),
             steps("..x...x...x...x.", vel=95), gain_db=-12.0, group="drums")
bass = Track("bass", Sampler("Bass - One Shot/DPT_A_Bass_One_Shot_Rez.wav"),
             steps("..x...x...x...x.", vel=100), gain_db=-9.0)

DRUMS = [kick, clap, ohat, bass]

# -----------------------------------------------------------------------------
# mid bass (Issue #12): 中域(250–800Hz)の「転がるベース」を ReaSynth(saw) で新設。
#   bass(サンプル)は <80Hz の sub 担当のまま、midbass が中域を埋める。
#   リズム: 各拍 [休符, 16分×3] で kick 裏を転がす(頭を休符にして kick と住み分け)。
#   octave2(A2≈110Hz)で基音は低いが saw 倍音が 250–800Hz を満たす。
#   sustain=0.0 + gate=0.55 でプラッキーな短い減衰=転がり。
#   ReaSynth はフィルタ非搭載のため後段に JSFX resonant LPF(cutoff/resonance)を挿す。
#   ルート進行: A→A→F→G (A Phrygian の i–i–VI–VII)。degree 4=E,5=F,6=G。
#   → 音作り(saw→envelope→filter)はここで確立し、lead(#2) の音色改善へ流用する。
# bar ごとのルート degree(A→A→F→G)。各拍を [休符, root, root, root] に展開して転がす。
_ROOTS = [0, 0, 5, 6]
midbass = Track("midbass", Synth(wave="saw", sustain=0.0, cutoff=1000, resonance=0.35), melody(
    "A", "phrygian",
    degrees=[d for root in _ROOTS for _ in range(4) for d in (None, root, root, root)],
    durations=[0.25] * 64,
    octave=2, vel=100, gate=0.55,
), gain_db=-7.0)

# -----------------------------------------------------------------------------
# lead: A Phrygian トランスリード (Issue #2)。RS5k は C4 固定でメロディ不可のため
#   ReaSynth(saw) を使う。degrees は A Phrygian のスケール度数 (0=A, 1=Bb, 2=C,
#   3=D, 4=E, 5=F, 7=A の1オクターブ上)。durations は各音の拍数(合計32拍=8小節で
#   1フレーズ)。長めの音価でトランスらしく歌わせ、breakdown では主役として残す。
# -----------------------------------------------------------------------------
lead = Track("lead", Synth(wave="saw"), melody(
    "A", "phrygian",
    degrees=[0, 1, 2, 3, 2, 1, 0, 4, 3, 1, 0,  0, 1, 2, 5, 4, 3, 4, 2, 1, 0],
    durations=[2, 1, 1, 2, 1, 1, 2, 2, 2, 1, 1,  2, 1, 1, 2, 1, 1, 2, 2, 2, 2],
    octave=4, vel=100, gate=0.9,
), gain_db=-12.0)

CORE = DRUMS + [midbass, lead]

# 展開 (Issue #5, #2, #12): コアループ → drums を抜いた 8小節 breakdown
#   (sub + midbass + lead が主役) → コアループ。lead は全区間で鳴らし続ける。
song = Song(bpm=138, sample_root=SAMPLES, tracks=CORE, sections=[
    section("core_a", 16, CORE),
    section("breakdown", 8, [bass, midbass, lead]),
    section("core_b", 16, CORE),
])
