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
# -----------------------------------------------------------------------------

kick = Track("kick", Sampler("Drum - Kick - One Shots/DPT_Kick_One_Shot_Acidtech.wav"),
             steps("x...x...x...x...", vel=120), gain_db=-8.0, group="drums")
clap = Track("clap", Sampler("Drum - Clap - One Shots/DPT_Clap_One_Shot_Sola.wav"),
             steps("....x.......x...", vel=105), gain_db=-10.8, group="drums")
ohat = Track("ohat", Sampler("Drum - Hat Open - One Shot/DPT_Hat_Open_One_Shot_Azureshort.wav"),
             steps("..x...x...x...x.", vel=95), gain_db=-12.0, group="drums")
DRUMS = [kick, clap, ohat]

# bar ごとのルート degree (A→A→F→G = A Phrygian の i–i–VI–VII)。sub と midbass が
# 共有し、両者のルートが必ず一致するようにする (degree 4=E, 5=F, 6=G)。
_ROOTS = [0, 0, 5, 6]

# -----------------------------------------------------------------------------
# sub bass (Issue #13): <80Hz の重量感だけを担う根音。元は RS5k サンプル
#   (DPT_..._Rez.wav = 実質 55Hz サイン)だったが、Synth(sine) へ repatriate した
#   (doc/adr/001 synth-first)。理由: sim(kita check)はサンプラのピッチを模さないため、
#   ルート進行を追う音は synth で作れば <80Hz 量・ルート・kick 住み分けを完全検証できる。
#   転がりは midbass(#12)へ譲り、sub は 1小節1音の pedal(最小限の動き)で根音を支える。
#   ルートは _ROOTS を共有(A→A→F→G)、octave1 で midbass のちょうど1オクターブ下
#   (A1=55/F2=87/G2=98Hz)。sustain=1.0 で持続する土台。
# -----------------------------------------------------------------------------
sub = Track("sub", Synth(wave="sine", sustain=1.0), melody(
    "A", "phrygian",
    degrees=_ROOTS,          # 1小節1音の pedal
    durations=[4, 4, 4, 4],
    octave=1, vel=100, gate=0.92,
), gain_db=-13.0)  # sustained sine は連続低域で headroom を食う(sidechain 非モデル)。
#   kita check スイープで clip 手前の天井(mix peak≒-0.2)。kick は依然低域リード
#   (sub<80Hz≒26% / kick≒61%)。これ以上の存在感は sidechain/kick 調整が要る。

# -----------------------------------------------------------------------------
# mid bass (Issue #12): 中域(250–800Hz)の「転がるベース」を ReaSynth(saw) で新設。
#   sub は <80Hz 担当、midbass が中域を埋める。
#   リズム: 各拍 [休符, 16分×3] で kick 裏を転がす(頭を休符にして kick と住み分け)。
#   octave2(A2≈110Hz)で基音は低いが saw 倍音が 250–800Hz を満たす。
#   sustain=0.0 + gate=0.55 でプラッキーな短い減衰=転がり。
#   ReaSynth はフィルタ非搭載のため後段に JSFX resonant LPF(cutoff/resonance)を挿す。
#   ルート進行は sub と同じ _ROOTS。各拍を [休符, root, root, root] に展開して転がす。
#   → 音作り(saw→envelope→filter)はここで確立し、lead(#2) の音色改善へ流用する。
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

CORE = DRUMS + [sub, midbass, lead]

# 展開 (Issue #5, #2, #12): コアループ → drums を抜いた 8小節 breakdown
#   (sub + midbass + lead が主役) → コアループ。lead は全区間で鳴らし続ける。
song = Song(bpm=138, sample_root=SAMPLES, tracks=CORE, sections=[
    section("core_a", 16, CORE),
    section("breakdown", 8, [sub, midbass, lead]),
    section("core_b", 16, CORE),
])
