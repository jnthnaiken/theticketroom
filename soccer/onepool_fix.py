"""
ONEPOOL-2026-08-31 -- the board is ONE POOL, not five leagues stapled together.

    owner, 2026-08-31: "no. it shouldnt be by league either. it should be one big pool.
                        just want to clarify cause you just made it sound like you were going
                        to do mls separate."

He is right, and I had it backwards. I had described per-league standardisation as a SAFETY
property -- the thing that would let ASA's MLS xG model coexist with Understat's without a
systematically hotter model dragging one league up. That is true as far as it goes, and it is
not worth what it costs.

## WHAT PER-LEAGUE STANDARDISATION ACTUALLY DID

Measured on the real 2026-08-31 slate, 75 priced players:

    league mean TOTAL:
        EPL          per-league  100.0     one-pool  105.7   n=15
        La_liga      per-league  100.0     one-pool  101.5   n=30
        Serie_A      per-league  100.0     one-pool   95.6   n=30

Every league lands on EXACTLY 100.0, and that is not a coincidence -- it is what z-scoring within
a group means. The old code could not tell a strong card from a weak one: it forced the average
Serie A player and the average EPL player to be the same player by construction, and then ranked
them against each other on the board as though that were a finding.

It also inflated whoever topped a thin group. Donyell Malen was the #1 name on the board at
TOTAL 187.7, twenty-four points clear of Raphinha, on a Serie A group where he was the standout.
Pooled he is 172.8, level with Raphinha, which is what the prices and the xG actually say.

The market term is the clearest case: `implied` is a probability. -138 means the same thing in
Milan and in Manchester. Standardising it per league deliberately threw away the one quantity on
the board that was already comparable.

## WHAT IT CHANGES ON THE BOARD

Same slate, fresh draft from each scored.json:

    PER-LEAGUE   3 slips   Raphinha + Krstovic + Jesus / Raphinha + Gyokeres + Scamacca
                           + builder Raphinha                        -- ONE anchor
    ONE POOL     6 slips   Raphinha + Jesus + Scamacca / Raphinha + Gyokeres + Dovbyk
                           Krstovic + Yamal + Havertz / Krstovic + Adeyemi + Jackson
                           + builders Raphinha, Krstovic             -- TWO anchors

The pool clears Z_GATE differently once the z-scores are honest, so a second anchor fits. That is
the board being fuller because the scoring got more truthful, not because a gate was loosened --
Z_GATE, GAME_CAP, WIN and ANCH are untouched. Compare LOOSEGATE thinking, which
soccer_draft.js's own comment rejects: "loosening the gate to hit a target ticket count is
fitting the bar to the answer."

## SHRINKAGE TOO

`shrink()` shrank each player toward HIS LEAGUE's minute-weighted mean. Same argument: the prior
on a rate stat is "what a footballer looks like", not "what a Ligue 1 footballer looks like", and
on a five-match card a league group can be a handful of players -- a prior estimated from six men
is barely a prior. One pool, one mean. SHRINK_K is unchanged at 900.

## ⚠️ THE THING THIS GIVES UP, STATED PLAINLY

Two xG models in one z-score. Understat covers the five European leagues; ASA covers MLS
(ASAXG-2026-08-31), and they are different models. Under per-league standardisation a
systematically hotter or colder model washed out inside its own group. Pooled, it does not: if
ASA reads high, every MLS player carries that bias into the edge term.

This is NOT measured yet and must not be assumed small. The 23-player ASA capture in
fixtures/asa-2026-08-31.json is selected (goalscorer-market names and penalty takers), so it
cannot answer the question -- comparing its npxG90 to Understat's would be comparing a hand-picked
tail to a full field. The honest check is a full-season pull from both and a distribution
comparison, and it should happen BEFORE the first slate that mixes them (2026-09-05 is the first
card with both, and it is a big one: 14 MLS fixtures alongside 22 European).

Recorded here so that check does not get skipped. Until then this change is a pure improvement on
a European-only board, where there is exactly one xG model and nothing to mix.

## NOT PINNED BY ANY TEST, AND WHY THAT IS NOT AS BAD AS IT SOUNDS

test_draft_golden.js pins the DRAFTER against fixtures/2026-08-26/scored.json -- a committed
soccer_mock OUTPUT. So it does not exercise this file, and it does not need updating: the golden
still asserts exactly what it always did, that soccer_draft.js reproduces the board that shipped
from that scoring. soccer_mock.py has no golden of its own. That is a real gap; it predates this
change and is written into PIPELINE as an open item rather than fixed in passing here.
"""
import sys

F = 'soccer_mock.py'
src = open(F, encoding='utf-8').read()
if 'ONEPOOL-2026-08-31' in src:
    sys.exit('ABORT: already applied')

# ---------------------------------------------------------------------------------------------
# 1. STANDARDISATION -- one pool.
OLD_STD = """for lg in {p['league'] for p in players}:
    grp = [p for p in players if p['league'] == lg]
    mz = standardize([p['implied'] for p in grp])
    sig_z = {k: standardize([p[k] for p in grp]) for k in SIG}
    for i, p in enumerate(grp):
        p['mkt_z'] = mz[i]
        p['edge_raw'] = sum(SIG[k] * sig_z[k][i] for k in SIG)
for lg in {p['league'] for p in players}:
    grp = [p for p in players if p['league'] == lg]
    ez = standardize([p['edge_raw'] for p in grp])
    for i, p in enumerate(grp):
        p['edge_z'] = ez[i]
        p['blend'] = 0.5 * p['mkt_z'] + 0.5 * p['edge_z']
        p['TOTAL'] = 100 + 30 * p['blend']"""

NEW_STD = """# 🚨 ONEPOOL-2026-08-31. ONE POOL, NOT FIVE LEAGUES STAPLED TOGETHER.
# Owner: "it shouldnt be by league either. it should be one big pool."
#
# These two loops used to run PER LEAGUE, and the cost of that is visible the moment you measure
# it. On the 2026-08-31 slate, 75 priced players:
#
#     league mean TOTAL   per-league          one-pool
#         EPL                 100.0            105.7    n=15
#         La_liga             100.0            101.5    n=30
#         Serie_A             100.0             95.6    n=30
#
# Every league landing on exactly 100.0 is not a coincidence, it is what z-scoring inside a group
# MEANS: the average Serie A player and the average EPL player were forced to be the same player
# by construction, and then ranked against each other on one board as if that were a finding. It
# also inflated whoever topped a thin group -- Donyell Malen led the whole board at 187.7,
# twenty-four clear of Raphinha, on a Serie A group he happened to top. Pooled he is 172.8, level
# with Raphinha, which is what the prices and the xG actually say.
#
# `implied` is the clearest case. It is a PROBABILITY: -138 means the same thing in Milan and in
# Manchester. Standardising it per league threw away the one quantity on the board that was
# already comparable across leagues.
#
# ⚠️ WHAT THIS GIVES UP: two xG models in one z-score. Understat covers the five European
# leagues, ASA covers MLS (ASAXG-2026-08-31). Per-league standardisation washed a systematically
# hotter or colder model out inside its own group; pooled, it does not. NOT MEASURED YET, and the
# 23-player ASA capture cannot answer it (it is a hand-picked tail). Do the full-season
# distribution comparison BEFORE the first mixed card -- 2026-09-05, 14 MLS fixtures alongside 22
# European. See onepool_fix.py.
#
# ⚠️ Z_GATE, GAME_CAP, WIN and ANCH are UNTOUCHED. The board drafting fuller (3 slips -> 6 on
# 08-31, one anchor -> two) is the scoring getting more truthful, not a gate being loosened.
# soccer_draft.js's own words: "loosening the gate to hit a target ticket count is fitting the bar
# to the answer."
grp = players
mz = standardize([p['implied'] for p in grp])
sig_z = {k: standardize([p[k] for p in grp]) for k in SIG}
for i, p in enumerate(grp):
    p['mkt_z'] = mz[i]
    p['edge_raw'] = sum(SIG[k] * sig_z[k][i] for k in SIG)
ez = standardize([p['edge_raw'] for p in grp])
for i, p in enumerate(grp):
    p['edge_z'] = ez[i]
    p['blend'] = 0.5 * p['mkt_z'] + 0.5 * p['edge_z']
    p['TOTAL'] = 100 + 30 * p['blend']"""

if src.count(OLD_STD) != 1:
    sys.exit('ABORT: the standardisation block does not look as expected')
src = src.replace(OLD_STD, NEW_STD, 1)

# ---------------------------------------------------------------------------------------------
# 2. SHRINKAGE -- one prior.
OLD_SHR = '''def shrink(players, keys, k=SHRINK_K):
    """Empirical-Bayes shrinkage toward the league mean, weighted by minutes.

    ⚠️ WITHOUT THIS THE BOARD IS NONSENSE. 2026-08-26 carries the textbook case: Carlos Espi's
    current-season row is 7 minutes with one goal -- npxG90 7.07 and 12.86 shots/90. Raw, he
    tops the board. Shrunk, he sits where 7 minutes of evidence belongs.
    """
    for lg in {p['league'] for p in players}:
        grp = [p for p in players if p['league'] == lg and p['has_xg']]
        if not grp:
            continue
        for key in keys:'''

NEW_SHR = '''def shrink(players, keys, k=SHRINK_K):
    """Empirical-Bayes shrinkage toward the POOL mean, weighted by minutes.

    ⚠️ WITHOUT THIS THE BOARD IS NONSENSE. 2026-08-26 carries the textbook case: Carlos Espi's
    current-season row is 7 minutes with one goal -- npxG90 7.07 and 12.86 shots/90. Raw, he
    tops the board. Shrunk, he sits where 7 minutes of evidence belongs.

    🚨 ONEPOOL-2026-08-31: the prior is the whole field, not the player's league. It used to
    shrink each man toward HIS LEAGUE's minute-weighted mean, which is the same mistake the
    standardisation below was making -- and worse here, because on a five-match card a league
    group can be six men, and a prior estimated from six men is barely a prior. The prior on a
    rate stat is "what a footballer looks like", not "what a Ligue 1 footballer looks like".
    SHRINK_K is unchanged at 900.
    """
    for _pool in (True,):
        grp = [p for p in players if p['has_xg']]
        if not grp:
            continue
        for key in keys:'''

if src.count(OLD_SHR) != 1:
    sys.exit('ABORT: shrink() does not look as expected')
src = src.replace(OLD_SHR, NEW_SHR, 1)

if "p['league'] == lg" in src:
    sys.exit('ABORT: a per-league grouping survived -- back out by hand')

open(F, 'w', encoding='utf-8').write(src)
print(f'onepool_fix: patched {F} ({len(src)} bytes)')
