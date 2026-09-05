#!/usr/bin/env python3
"""soccer_mock.py -- PROTOTYPE scorer + drafter for the soccer board.

⚠️ THIS IS NOT THE PRODUCTION ENGINE. Python-side mock that scores a slate and drafts tickets
so we can look at a real board before committing to the client-engine work. The production
draft has to run through index.html's __assembleClient so server and browser never diverge --
that is the whole lesson of client_assemble.js.

⚠️ THE EDGE WEIGHTS ARE UNFITTED PLACEHOLDERS.

INPUTS   ags.psv   match|player|fractional-odds      (oddschecker, best odds)
         xg.psv    league|season|name|team|pos|games|min|goals|npg|npxG|npxG90|
                   shots|shots90|xGperShot|xA|xA90|key_passes|xGChain   (understat)
"""
import re, math, unicodedata, json
import subprocess as _subprocess, os as _os, shutil as _shutil
from collections import defaultdict

CFG = dict(
    # WIN60-2026-08-29 -- was 180. MUST match DEFAULTS.WIN in soccer_draft.js; two copies, one
    # rule. Team sheets land ~1h before kickoff, so a slip spanning three hours is never fully
    # confirmed at any one moment -- by the time the last leg's XI is known the first leg has
    # been playing for two hours and the slip can no longer be placed. 60 keeps every leg's
    # lineup risk inside the same hour. See the note on DEFAULTS.WIN for the owner's wording.
    #
    # WIN75 / ZGATE70-2026-08-30 -- owner: "just loosen both gates to .7 and 75 minutes". The
    # 08-30 card drafted NOTHING at 60/0.75: draftN is all-or-none and picks anchors
    # strength-first, so Lautaro Martinez -- the strongest man on the slate, in a ko-1125 window
    # holding only two pool matches -- zeroed every attempt down to n=1. Lazio's best gated at
    # +0.74 and Aubameyang was 75 minutes out; both new numbers clear exactly those margins.
    # BOTH VALUES MUST MATCH DEFAULTS IN soccer_draft.js. See claude/soccer-2026-08-30-emptydraft.md.
    WIN=75, Z_GATE=0.70, GAME_CAP=4, CHALK_N=0,
    ANCH=4, MOONS_PER_ANC=2, ANCH_PER_GAME=2, FAM_CAP=8,
    MOON_RISK=2.0, SINGLE_STAKE=1.0,
)

SIG = {'npxg90': 0.60, 'xgpershot': 0.20, 'finish90': 0.10, 'xa90': 0.10}

# FIXTURES-2026-08-27. KICKOFF and LEAGUE used to be hand-edited here every slate, which is a
# CODE edit to ship DATA -- PIPELINE.md open item 3. They now come from fixtures.json next to
# the inputs, and the hardcoded dicts below are only the fallback for an old slate directory.
# Kickoffs are UTC minutes past midnight, read off the ESPN scoreboard, never assumed.
import os as _os0
KICKOFF, LEAGUE = {}, {}
if _os0.path.exists('fixtures.json'):
    _fx = json.load(open('fixtures.json', encoding='utf-8'))
    for _m, _d in _fx['matches'].items():
        KICKOFF[_m] = int(_d['kickoff'])
        LEAGUE[_m] = _d['league']
    print(f"  fixtures.json: {len(KICKOFF)} matches, {_fx.get('date')}")
else:
    KICKOFF = {'real-madrid-v-real-sociedad': 19 * 60, 'aek-athens-v-levski-sofia': 19 * 60,
               'lyon-v-fenerbahce': 19 * 60, 'nk-celje-v-slovan-bratislava': 19 * 60,
               'viking-v-dinamo-zagreb': 19 * 60}
    LEAGUE = {'real-madrid-v-real-sociedad': 'La_liga', 'aek-athens-v-levski-sofia': 'UCL_PO',
              'lyon-v-fenerbahce': 'UCL_PO', 'nk-celje-v-slovan-bratislava': 'UCL_PO',
              'viking-v-dinamo-zagreb': 'UCL_PO'}


def norm(s):
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace('.', ' ').replace('-', ' ').replace("'", ' ')
    return re.sub(r'\s+', ' ', s).strip()


def toks(s):
    return sorted(w for w in norm(s).split() if len(w) > 2)


def frac_to_am(f):
    n, d = (float(x) for x in f.split('/'))
    v = n / d
    return round(v * 100) if v >= 1 else round(-100 / v)


def implied(am):
    return 100.0 / (am + 100) if am > 0 else (-am) / ((-am) + 100.0)


def dec(am):
    return 1 + am / 100.0 if am > 0 else 1 + 100.0 / abs(am)


def zscores(vals):
    got = [v for v in vals if v is not None]
    if len(got) < 2:
        return [0.0] * len(vals)
    m = sum(got) / len(got)
    sd = math.sqrt(sum((v - m) ** 2 for v in got) / (len(got) - 1)) or 1.0
    return [0.0 if v is None else (v - m) / sd for v in vals]


standardize = zscores

# PRICELEDGER-SOCCER-2026-09-04 -- INSERT ONLY, NEVER UPDATE. Owner: "build it so a name can
# only ever be inserted, never updated." ags.psv is MERGED into the committed per-slate
# prices.json rather than read as gospel; existing entries are HELD, new names are appended, and
# the merged ledger is written back so the next build has something to hold.
#
# It lives HERE, and not in soccer_rebuild_cli.js where PRICEONCE-SOCCER-2026-09-03 put it,
# because this is where the board's numbers come from. The rebuild CLI writes tickets.json only;
# soccer_payload.py rebuilds soccer_D.json from scored.json with no prior-board awareness, so a
# fresh ags.psv moved every price on the card whatever the re-draft held. Same shape as
# nfl_mock.py's load_prices(), on purpose -- one idea, not two.
PRICES = 'prices.json'
odds, _prev = {}, {}
if _os.path.exists(PRICES):
    _prev = json.load(open(PRICES, encoding='utf-8'))
for _k, _v in _prev.items():
    _m, _n = _k.split('|', 1)
    odds[(_m, _n)] = int(_v)
_pnew = _pheld = _pwould = 0
# SLATEROSTER-2026-09-04. THE SLATE, in ags.psv's own order. The ledger says what a name COSTS;
# this says who is on the card tonight. Collected in the loop that already reads the file.
slate = []
for line in open('ags.psv', encoding='utf-8'):
    if not line.strip():
        continue
    match, name, f = line.strip().split('|')
    am = frac_to_am(f)
    slate.append((match, name))
    if (match, name) not in odds:
        odds[(match, name)] = am                 # ADD: rule (1), and it must stay open
        _pnew += 1
    else:
        if odds[(match, name)] != am:
            _pwould += 1                         # the move is COUNTED, not applied
        _pheld += 1
json.dump({f'{m}|{n}': v for (m, n), v in sorted(odds.items())},
          open(PRICES, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
print(f'  prices: {_pnew} new, {_pheld} held by PRICEONCE [{_pwould} would have moved]')

xg_exact, xg_tok = defaultdict(list), defaultdict(list)
for line in open('xg.psv', encoding='utf-8'):
    if not line.strip():
        continue
    c = line.rstrip('\n').split('|')
    rec = dict(league=c[0], season=c[1], name=c[2], team=c[3], pos=c[4],
               games=int(c[5]), minutes=int(c[6]), goals=int(c[7]), npg=int(c[8]),
               npxg=float(c[9]), npxg90=float(c[10]), shots=float(c[11]),
               shots90=float(c[12]), xgpershot=float(c[13]), xa=float(c[14]),
               xa90=float(c[15]), kp=float(c[16]), xgchain=float(c[17]))
    xg_exact[norm(rec['name'])].append(rec)
    xg_tok[' '.join(toks(rec['name']))].append(rec)


def lookup(name):
    """SURNAME-ANCHORED (PIPELINE open item 1, ported from soccer_teamnews.match_one).

    The old rule accepted ANY token-subset match, which mapped Real Betis's `Pablo Garcia` to
    EPL's `Pablo` and Celtic's `Joao Pedro Jota` to Chelsea's `Joao Pedro` -- two different
    people each time. The last token of the ODDS name (the surname slot) must appear in the
    candidate's tokens.
    """
    k = norm(name)
    if k in xg_exact:
        return xg_exact[k], 'exact'
    w = [t for t in toks(name)]
    if not w:
        return None, None
    sur = norm(name).split()[-1]
    hits = []
    for t, v in xg_tok.items():
        ct = set(t.split())
        if sur not in ct:
            continue
        if ct <= set(w) or set(w) <= ct:
            hits.append(v)
    return (hits[0], 'token') if len(hits) == 1 else (None, None)


SHRINK_K = 900


def blend_seasons(recs):
    tot = sum(r['minutes'] for r in recs) or 1
    out = {}
    for k in ('npxg90', 'xgpershot', 'xa90', 'shots90'):
        out[k] = sum(r[k] * r['minutes'] for r in recs) / tot
    npg = sum(r['npg'] for r in recs)
    npxg = sum(r['npxg'] for r in recs)
    mins = sum(r['minutes'] for r in recs)
    out['finish90'] = (npg - npxg) * 90 / mins if mins else 0.0
    out['minutes'] = mins
    out['pos'] = recs[0]['pos']
    out['team'] = recs[-1]['team']
    return out


def shrink(players, keys, k=SHRINK_K):
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
        for key in keys:
            vals = [(p[key], p['minutes']) for p in grp if p[key] is not None]
            tm = sum(m for _, m in vals) or 1
            if not tm:
                continue
            mean = sum(v * m for v, m in vals) / tm
            for p in grp:
                if p[key] is None:
                    continue
                m = p['minutes']
                p[key] = (p[key] * m + mean * k) / (m + k)


players = []
matched = {'exact': 0, 'token': 0, 'missing': 0}
for match, name in slate:
    am = odds[(match, name)]
    # SLATEROSTER-2026-09-04. This walked `odds` -- the LEDGER -- which made a (match, name) key
    # permanent: once priced, never removable, because nothing ever deletes from prices.json. The
    # 2026-09-04 board carried a stale PSG card for Bradley Barcola at +120 through two rebuilds
    # AFTER the row was dropped from ags.psv, scored him twice, and let the ghost overwrite his
    # real Liverpool entry in soccer_D.json's name-keyed dict. The merge above is unchanged --
    # ADD when absent, HOLD when present, never update -- because the owner's insert-only rule is
    # about the PRICE. A ledger key with no ags.psv row is now simply unused.
    #
    # The warning below is unreachable from the ledger now and is kept for a hand-edited ags.psv
    # naming a match fixtures.json does not carry: that was a KeyError on LEAGUE[match] that took
    # the whole build down.
    if match not in LEAGUE or match not in KICKOFF:
        print(f'  ::warning::prices.json carries {match}|{name}, which is not on this slate -- skipped')
        continue
    recs, how = lookup(name)
    matched['missing' if how is None else how] += 1
    p = dict(name=name, match=match, league=LEAGUE[match], odds=am,
             implied=implied(am), kickoff=KICKOFF[match], has_xg=recs is not None)
    p.update(blend_seasons(recs) if recs else
             {k: None for k in ('npxg90', 'xgpershot', 'xa90', 'shots90', 'finish90')} |
             {'minutes': 0, 'pos': '?', 'team': '?'})
    players.append(p)

shrink(players, list(SIG.keys()))

# 🚨 ONEPOOL-2026-08-31. ONE POOL, NOT FIVE LEAGUES STAPLED TOGETHER.
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
    p['TOTAL'] = 100 + 30 * p['blend']

_XI = None
_TRUSTED = None
try:
    _tn = json.load(open('teamnews.json', encoding='utf-8'))
    _XI = set(_tn.get('xi', {}))
    # XIPARTIALMOCK-2026-09-05 -- see soccer_draft_cli.js. The per-match XI rule
    # (XIPARTIALGATE-2026-08-29) never reached this file; the pool gate below was a flat,
    # slate-wide `p['name'] in _XI`, so once ANY sheet published every player whose own match had
    # not published was dropped. This is the COLD-DRAFT path, i.e. the first build of a slate.
    # Measured 2026-09-05 (21 matches, 12 sheets out): 52 gated, flat admits 12, per-match 39.
    # `trusted` is per match from soccer_teamnews.py; older files lack it, so fall back to the
    # matches carrying any classified player -- never to an empty set, which disables the filter.
    _TRUSTED = {m for m, t in (_tn.get('trusted') or {}).items() if t}
    if not _tn.get('trusted'):
        _TRUSTED = set(_tn.get('xi', {}).values()) | set(_tn.get('bench', {}).values())
    print(f"  team news: {len(_XI)} confirmed starters across {len(_TRUSTED)} published sheet(s) "
          f"({len(_tn.get('bench', {}))} benched, {len(_tn.get('absent', {}))} out of squad); "
          f"matches without a sheet stay draftable")
except FileNotFoundError:
    print('  team news: none on disk -- drafting from the whole priced field')

# WRONGCLUB-2026-08-30. A priced player who is in NEITHER squad must not be drafted.
# Owner: *"that makes us look fucking retarded. fix it."*
#
# 2026-08-30 shipped Nicolas Jackson as an ANCHOR of Chelsea v Brighton -- 2 screamers and a
# builder -- and he plays for ASTON VILLA, who were not on the slate. ESPN and Sofascore agree
# to the man on both squads; oddschecker priced him anyway. squads.psv already held the proof
# and its only consumer was the CLUB LABEL, so `_side()` printed "--" and the drafter never
# asked. Same file, one more reader.
#
# ⚠️ ABSENCE IS ASSERTED ONLY ON surname_hits() == 0 -- UNMATCHED-2026-08-28's rule, which
# exists because "the join refused" and "he is not playing" look identical and the second one
# silently kills a live bet. A surname that merely fails to JOIN (Philogene-Bidace vs ESPN's
# Philogene) still hits, so he stays in the field and only loses his club label.
#
# ⚠️ NO squads.psv MEANS NO GATE, never an empty one -- the `_XI is None` trap three lines up,
# same shape. squads.psv is an optional input the workflow does not hard-error on.
_ABSENT = set()
if _os0.path.exists('squads.psv'):
    from soccer_teamnews import surname_hits as _sur
    _SQ = {}
    for _line in open('squads.psv', encoding='utf-8'):
        _c = _line.rstrip('\n').split('|')
        if len(_c) >= 3 and _c[0]:
            _SQ.setdefault(_c[0], []).append((_c[2], _c[1]))
    for _p in players:
        _sq = _SQ.get(_p['match'])
        if _sq and _sur(_p['name'], _sq) == 0:
            _ABSENT.add(_p['name'])
            # ⚠️ THE FLAG IS WHAT COUNTS, NOT THE PYTHON POOL BELOW. soccer_mock does not draft
            # -- it writes scored.json and shells out to soccer_draft_cli.js, which rebuilds the
            # pool in JS. Filtering the local `pool` list only changes this file's printout. The
            # row itself has to carry the fact, and `out` is the field OUTSQUAD-2026-08-29
            # already defined for exactly this.
            _p['out'] = True
    print(f'  squads: {sum(len(v) for v in _SQ.values())} roster names across {len(_SQ)} matches'
          f' -- {len(_ABSENT)} priced player(s) in NEITHER squad, not draftable'
          + (': ' + ', '.join(sorted(_ABSENT)) if _ABSENT else ''))
else:
    print('  squads: none on disk -- no wrong-club gate')

bl = [p['blend'] for p in players]
m = sum(bl) / len(bl)
sd = math.sqrt(sum((x - m) ** 2 for x in bl) / (len(bl) - 1)) or 1.0
for p in players:
    p['gate_z'] = (p['blend'] - m) / sd

# XIPARTIALMOCK-2026-09-05: per MATCH, not slate-wide. Mirrors soccer_draft.js buildPool().
pool = [p for p in players
        if p['gate_z'] >= CFG['Z_GATE']
        and (_XI is None or p['name'] in _XI or p['match'] not in _TRUSTED)
        and p['name'] not in _ABSENT]
pool.sort(key=lambda p: (-p['TOTAL'], p['name']))
capped, per_match = [], defaultdict(int)
for p in pool:
    if per_match[p['match']] < CFG['GAME_CAP']:
        capped.append(p)
        per_match[p['match']] += 1
pool = capped

tmin = min((p['TOTAL'] for p in pool), default=0)
tmax = max((p['TOTAL'] for p in pool), default=1)
for p in players:
    p['strength'] = (p['TOTAL'] - tmin) / (tmax - tmin) if tmax > tmin else 0.5

by_strength = sorted(pool, key=lambda p: (-p['strength'], p['name']))


# span_ok() and draft() were HERE. Removed STAGE2-2026-08-27 -- see the note below.
# They are not commented out and not kept 'just in case': a second copy of a rule set is
# exactly what goes stale. soccer_draft.js is the only draft now.


# ======================================================================================
# STAGE2-2026-08-27: THE DRAFT MOVED OUT OF THIS FILE.
# ======================================================================================
# It now lives in soccer_draft.js and is invoked through node, exactly the way regen15.py
# runs client_assemble.js on the baseball side. The reason is the same one, and it is the
# lesson this codebase has already paid for twice: a draft that exists once in Python for
# the archive and once in JavaScript for the browser is two implementations of one rule set,
# and they drift. assemble_tickets.py is the monument to that -- two board redesigns behind,
# still building a retired Grand Salami, and grade_night.py books whatever it produces.
#
# The live board has to re-draft when team news lands (Stage 2), and the only engine that
# runs in a browser is JavaScript. So JavaScript is where the rules go, and this file calls
# them rather than keeping a second copy in step by hand.
#
# `draft()`, `span_ok()` and the THINSLATE loop above are gone with it. Everything up to and
# including `strength` stays here: scoring is not drafting, and scored.json is the interface.
_scored = [{k: v for k, v in p.items() if k != 'legs'} for p in players]
json.dump(_scored, open('scored.json', 'w'), indent=1)

_cmd = [_shutil.which('node') or 'node',
        _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'soccer_draft_cli.js'),
        'scored.json', 'tickets.json']
if _XI is not None:
    _cmd.append('teamnews.json')
_rc = _subprocess.call(_cmd)
if _rc != 0:
    raise SystemExit(f'!! soccer_draft_cli.js exited {_rc} -- no board drafted. '
                     'This is a FAILED BUILD, not a board to publish.')
tickets = [dict(kind=t['kind'], risk=t['risk'],
                legs=[dict(l, TOTAL=l['TOTAL']) for l in t['legs']])
           for t in json.load(open('tickets.json'))]

# builders (one per distinct screamer anchor) are minted by soccer_draft.js alongside the
# moons, so `tickets` already carries them by the time it is read back.

# SCREAMERS-2026-08-26: the leftover section is RETIRED, matching the MLB Dingers retirement
# (family went 11-80 / -33.34u there). No `family` tickets are minted. "Screamers" is now the
# display name of the MOON section; the ledger kind stays `moon` so season.json reconciles.
drafted = {l['name'] for t in tickets for l in t['legs']}
floor = min((p['TOTAL'] for t in tickets for p in t['legs']), default=0)


def price(t):
    d = 1.0
    for l in t['legs']:
        d *= dec(l['odds'])
    return d


print("SOCCER BOARD")
print(f"  priced players {len(players)} across {len({p['match'] for p in players})} matches")
print(f"  xG join: exact {matched['exact']} | token {matched['token']} | missing {matched['missing']}"
      f"  ({100*(matched['exact']+matched['token'])/len(players):.0f}%)")
print(f"  pool after Z_GATE {CFG['Z_GATE']} + XI filter + GAME_CAP {CFG['GAME_CAP']}: {len(pool)}")
print(f"  weakest drafted TOTAL: {floor:.1f}")
print()
print(f"  {'TOP OF BOARD':32s}{'lg':9s}{'odds':>7s}{'TOTAL':>8s}{'mkt_z':>7s}{'edge_z':>8s}{'xG?':>5s}")
for p in sorted(players, key=lambda p: -p['TOTAL'])[:12]:
    print(f"    {p['name'][:28]:30s}{p['league']:9s}{p['odds']:+7d}{p['TOTAL']:8.1f}"
          f"{p['mkt_z']:+7.2f}{p['edge_z']:+8.2f}{'y' if p['has_xg'] else 'NO':>5s}")
print()
kinds = defaultdict(int)
for t in tickets:
    kinds[t['kind']] += 1
print(f"  TICKETS: {dict(kinds)}   total staked {sum(t['risk'] for t in tickets):.1f}u")
for t in tickets:
    if t['kind'] == 'moon':
        legs = ' + '.join(f"{l['name']} ({l['odds']:+d})" for l in t['legs'])
        print(f"    💥 screamer {price(t):7.1f}x  {legs}")
for t in tickets:
    if t['kind'] == 'builder':
        l = t['legs'][0]
        print(f"    ⚓️ anchor          {l['name']} ({l['odds']:+d})")

print("\n  scored.json written here; tickets.json written by soccer_draft.js")
