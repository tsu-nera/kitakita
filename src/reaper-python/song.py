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
    arped,
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
# gain_db は全トラック一律で -1.6dB トリム済み(相対バランスは不変)。
#   デチューン3層は唸りの山で位相が揃い、そこだけ瞬間的にピークが立つ。lead の
#   変奏を plain と同じエネルギーへ埋め戻したところ drop2 が +1.08dBFS まで振れた
#   (18サンプル clip)。lead だけ下げてもピークは素直に落ちない(2dB 下げて 0.87dB)
#   ため、ミックス全体の頭を下げた。master trim ではなく各トラックの gain_db を
#   動かすのは、track volume なら kita sync が REAPER へ反映でき sim と乖離しないため。
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# オーソドックスなトランス・ドラム (16分グリッド):
#   step:  1 e & a 2 e & a 3 e & a 4 e & a
#   kick   x . . . x . . . x . . . x . . .   4つ打ち
#   clap   . . . . x . . . . . . . x . . .   2拍4拍
#   ohat   . . x . . . x . . . x . . . x .   オフビート・オープンハット
# -----------------------------------------------------------------------------

kick = Track("kick", Sampler("Drum - Kick - One Shots/DPT_Kick_One_Shot_Acidtech.wav"),
             steps("x...x...x...x...", vel=120), gain_db=-9.6, group="drums")
clap = Track("clap", Sampler("Drum - Clap - One Shots/DPT_Clap_One_Shot_Sola.wav"),
             steps("....x.......x...", vel=105), gain_db=-12.4, group="drums")
ohat = Track("ohat", Sampler("Drum - Hat Open - One Shot/DPT_Hat_Open_One_Shot_Azureshort.wav"),
             steps("..x...x...x...x.", vel=95), gain_db=-13.6, group="drums")
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
), gain_db=-12.6, duck=Duck("kick", depth_db=-14.0, attack=0.01, release=0.30))

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
    gain_db=-8.6, duck=Duck("kick", depth_db=-14.0, attack=0.01, release=0.30))

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

LEAD_CLIP = PROG.melody(MELODY, octave=4, vel=100, gate=0.9)
LEAD_REVERB = Reverb(room_size=0.80, damping=0.4, send_db=-9.0, hpf=300)

# デチューンレイヤー (Issue #2)。ReaSynth は unison/detune を持たないので、supersaw の
#   「太い壁」は同じ旋律を cent 単位でずらしたトラックの重ねで作る(#2 の黎明期方式 —
#   JP-8000 以前のトランスも実際こうやって作られていた)。
#   ±14cent は A4(440Hz) で約 3.5Hz の唸り。速すぎると濁り、遅すぎると 1本に聞こえる。
#   3本の合計エネルギーが上がるぶん各層の gain を下げ、lead 全体の RMS を単層時へ
#   揃える。値は kita check で実測して決めた(全体トリム後で -20.7 dBFS)。
DETUNE_CENTS = (0.0, -14.0, +14.0)
LEAD_LAYER_GAIN = -18.6


def lead_layer(name: str, detune: float) -> Track:
    return Track(name, Synth(wave="saw", detune=detune), LEAD_CLIP,
                 gain_db=LEAD_LAYER_GAIN, group="lead", reverb=LEAD_REVERB)


LEADS = [lead_layer(n, c) for n, c in
         zip(("lead", "lead_dn", "lead_up"), DETUNE_CENTS)]
lead = LEADS[0]

# lead の変奏 (Issue #2)。MELODY 1本へ変換を掛けたものをセクションで差し替える。
#   arped(root-3度-5度への分解)は不採用 — 和音を駆け上がる走句になってチップチューン風に
#   寄り、トランスらしさが消える。gated は音程を動かさず時間軸だけを刻むので、和声が
#   静止したまま推進力だけが増える。
#   デチューン3層すべてに同じ変奏を掛ける(層ごとに articulation が違うと厚みでなく
#   別パートに聞こえる)。
#   vel/gate は「変奏で落ちるエネルギーを埋め戻す」ために決まる。ゲートは音を間引き、
#   arped は音価を刻むので、plain と同じ vel/gate のままだと曲の山である drop/drop2 で
#   lead が一番小さくなる(トリム前の実測: plain -19.1 に対し gated -21.7 /
#   arped -22.5 dBFS)。vel と gate を上げて plain へ揃える。gate をこれ以上上げると
#   16分スロットが隙間なく鳴ってトランスゲートの「切れ」が薄れるため、
#   不足ぶんは vel(上限127)で埋める。
GATE16 = "x.xx x.xx x.xx x.xx"
lead_gated = PROG.melody(gated(MELODY, GATE16), octave=4, vel=127, gate=0.8)
LEAD_GATED_OVERRIDE = {t: lead_gated for t in LEADS}

# drop2 のアルペジオ (Issue #2)。gated の「音程は動かず時間だけ刻む」に対して、
#   arped は「時間の刻みはそのままで音程が動く」— trance gate の後に置くと、
#   同じ16分の推進力を保ったまま情報だけが増えるので、最後の一段になる。
#   shape は既定の (0,2,4) でなく (0,2,4,7)。3音だと16分4つの拍に対して周期が
#   ずれ続け、スケールを駆け上がる走句=チップチューン風に聞こえる(#2 で却下した形)。
#   4音なら1拍で1周し、各拍頭が必ず旋律音そのものに戻るので、旋律が保たれたまま
#   分散和音の装飾になる。7=オクターブ上で、トランスのアルペジオらしい開きが出る。
#   vel/gate は gated と同じ理由で「埋め戻し」の値(上のコメント参照)。arped は
#   音価が最も短く落ち込みも最大(-22.5 dBFS)なので、vel は上限まで使う。
lead_arped = PROG.melody(arped(MELODY, shape=(0, 2, 4, 7)),
                         octave=4, vel=127, gate=0.7)
LEAD_ARPED_OVERRIDE = {t: lead_arped for t in LEADS}

# -----------------------------------------------------------------------------
# pads (Issue #3): 和声の説明役。「今 Am です」を耳に伝えるだけの伴奏で、
#   リズムは持たない(全音符)。bass も lead も pads も親は PROG ひとつで、
#   pads はそこから root/3度/5度を引く(bass は root だけ、lead は旋律)。
#   issue body の A Phrygian は #2 で不採用になったので natural minor の
#   i–VI–III–VII をそのまま和音化する。
#   voicing は fold(既定)で base オクターブ内へ畳む。root position のままだと
#   F=F4-A4-C5, G=G4-B4-D5 と上へ流れて lead(C5〜A5)の音域へ刺さるが、畳むと
#   A3-C4-E4 → A3-C4-F4 → C4-E4-G4 → B3-D4-G4 と転回形になり、上端が G4 で
#   止まって lead の下限 C5 と分離する(声部進行も滑らかになる副産物つき)。
#   音作り: saw を cutoff 800Hz で暗くし、面として後ろに置く。kick では
#   bass(-14dB)より浅く沈める(パッドは深く沈めると穴が空く)。
#   gain は kita check で比較して素の -20.0 を採り、全体トリム -1.6dB を足して
#   -21.6 にしてある(#2 のトリムは全トラック一律なので pads も従う)。素で -17 だと
#   breakdown が core_a と並んでドラムを抜いた意味が消え、-20 なら落差が残る。
#   ただし sim は LPF を模さないので実機ではこれより暗く小さく鳴る
#   (耳で数dB持ち上げる余地がある)。
#   遅いアタックは Synth に席が無い(かつ sim の attack は 5ms 固定)ため、
#   ここでは扱わない — 音価4拍 + LPF でパッドとしては成立する。
# -----------------------------------------------------------------------------
pads = Track("pads", Synth(wave="saw", sustain=1.0, cutoff=800, resonance=0.1),
             PROG.chords(motif([ROOT], [4]), octave=3, vel=90),
             gain_db=-21.6, duck=Duck("kick", depth_db=-6.0, attack=0.01, release=0.25))

CORE = DRUMS + [subbass, midbass] + LEADS
ALL = CORE + [pads]

# 展開 (Issue #5, #2, #12, #3): トランスの定石 core → breakdown → build → drop。
#   drums の抜き差しと lead の articulation を別々に動かし、drop で初めて両方が揃う。
#     core_a    full,  lead=plain   旋律の提示。pads はまだ入れない
#     breakdown drums+midbass 抜き, plain   pads が入る。抜けた穴を和音が埋める
#       midbass を抜くのは「拍がずれて聞こえる」実測への対処。midbass は各拍
#       [休符,16分×3] で拍頭に音を1つも持たず(実測: 拍頭の音 0/96)、kick が
#       拍を示す前提のパターン。kick が居ない breakdown では duck も点が立たず
#       (191点→1点, 最小ゲイン 0.20→1.00)、pump による拍の手がかりも消えるため、
#       3連16分の1つ目が拍頭に聞こえて16分(0.109s)ぶん前へずれて感じる。
#     build     kick+clap 復帰, plain  ohat はまだ入れず「戻りきっていない」感を残す
#     drop      full,  lead=gated   ohat が戻り lead が16分ゲートへ
#     drop2     full,  lead=arped   同じ16分のまま音程が動き出す = 最後の一段
#   lead は全区間 MELODY 1本で、変わるのは articulation だけ。
#   pads は breakdown で入って以降そのまま。入りが breakdown の合図になり、
#   drums が戻ってからは和声の糊として残る。
song = Song(bpm=138, sample_root=SAMPLES, tracks=ALL, sections=[
    section("core_a", 16, CORE),
    section("breakdown", 8, [subbass] + LEADS + [pads]),
    section("build", 8, [kick, clap, subbass, midbass] + LEADS + [pads]),
    section("drop", 8, ALL, override=LEAD_GATED_OVERRIDE),
    section("drop2", 8, ALL, override=LEAD_ARPED_OVERRIDE),
])
