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
from collections import defaultdict

CFG = dict(
    WIN=180, Z_GATE=0.75, GAME_CAP=4, CHALK_N=0,
    ANCH=4, MOONS_PER_ANC=2, ANCH_PER_GAME=2, FAM_CAP=8,
    MOON_RISK=2.0, SINGLE_STAKE=1.0,
)

SIG = {'npxg90': 0.60, 'xgpershot': 0.20, 'finish90': 0.10, 'xa90': 0.10}

# 2026-08-26. Kickoffs UTC minutes, read off the ESPN scoreboard (not assumed).
# All five are 19:00Z / 3:00 PM ET.
KICKOFF = {'real-madrid-v-real-sociedad': 19 * 60, 'aek-athens-v-levski-sofia': 19 * 60,
           'lyon-v-fenerbahce': 19 * 60, 'nk-celje-v-slovan-bratislava': 19 * 60,
           'viking-v-dinamo-zagreb': 19 * 60}
# Only the La Liga tie has understat xG behind it; the four Champions League playoff ties are
# outside understat's five-league coverage, so 60 of 75 priced names score on the market term
# alone (has_xg False -> edge_raw 0). Designed fallback, but say it out loud on the board.
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

odds = {}
for line in open('ags.psv', encoding='utf-8'):
    if not line.strip():
        continue
    match, name, f = line.strip().split('|')
    odds[(match, name)] = frac_to_am(f)

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
    """Empirical-Bayes shrinkage toward the league mean, weighted by minutes.

    ⚠️ WITHOUT THIS THE BOARD IS NONSENSE. 2026-08-26 carries the textbook case: Carlos Espi's
    current-season row is 7 minutes with one goal -- npxG90 7.07 and 12.86 shots/90. Raw, he
    tops the board. Shrunk, he sits where 7 minutes of evidence belongs.
    """
    for lg in {p['league'] for p in players}:
        grp = [p for p in players if p['league'] == lg and p['has_xg']]
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
for (match, name), am in odds.items():
    recs, how = lookup(name)
    matched['missing' if how is None else how] += 1
    p = dict(name=name, match=match, league=LEAGUE[match], odds=am,
             implied=implied(am), kickoff=KICKOFF[match], has_xg=recs is not None)
    p.update(blend_seasons(recs) if recs else
             {k: None for k in ('npxg90', 'xgpershot', 'xa90', 'shots90', 'finish90')} |
             {'minutes': 0, 'pos': '?', 'team': '?'})
    players.append(p)

shrink(players, list(SIG.keys()))

for lg in {p['league'] for p in players}:
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
        p['TOTAL'] = 100 + 30 * p['blend']

_XI = None
try:
    _tn = json.load(open('teamnews.json', encoding='utf-8'))
    _XI = set(_tn.get('xi', {}))
    print(f"  team news: drafting from {len(_XI)} confirmed starters "
          f"({len(_tn.get('bench', {}))} benched, {len(_tn.get('absent', {}))} out of squad)")
except FileNotFoundError:
    print('  team news: none on disk -- drafting from the whole priced field')

bl = [p['blend'] for p in players]
m = sum(bl) / len(bl)
sd = math.sqrt(sum((x - m) ** 2 for x in bl) / (len(bl) - 1)) or 1.0
for p in players:
    p['gate_z'] = (p['blend'] - m) / sd

pool = [p for p in players if p['gate_z'] >= CFG['Z_GATE'] and (_XI is None or p['name'] in _XI)]
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


def span_ok(legs):
    ks = [l['kickoff'] for l in legs]
    return (max(ks) - min(ks)) <= CFG['WIN']


def draft(n_anchors):
    """Draft with exactly n anchors. Returns [] unless EVERY anchor ships its full pair."""
    anchors, per_g = [], defaultdict(int)
    for p in by_strength:
        if len(anchors) >= n_anchors:
            break
        if per_g[p['match']] < CFG['ANCH_PER_GAME']:
            anchors.append(p)
            per_g[p['match']] += 1
    if len(anchors) < n_anchors:
        return []
    used = {p['name'] for p in anchors}
    partners = [p for p in by_strength if p['name'] not in used]
    out, spent = [], set()
    for a in anchors:
        made, local = [], set()
        for _ in range(CFG['MOONS_PER_ANC']):
            legs, seen = [a], {a['match']}
            for cand in partners:
                if len(legs) == 3:
                    break
                if cand['match'] in seen or cand['name'] in spent or cand['name'] in local:
                    continue
                if span_ok(legs + [cand]):
                    legs.append(cand)
                    seen.add(cand['match'])
                    local.add(cand['name'])
            if len(legs) == 3:
                made.append(legs)
        if len(made) != CFG['MOONS_PER_ANC']:
            return []                      # all-or-none: this anchor count does not fit
        spent |= local
        for legs in made:
            out.append(dict(kind='moon', legs=legs, risk=CFG['MOON_RISK']))
    return out


# THINSLATE-2026-08-26 (owner's call). ANCH was fixed at 4, a number sized for a 15-game MLB
# slate. Once team news was wired the soccer field fell from 75 priced to 25 actually starting
# across 5 matches, the all-or-none demote fired on every anchor, and the board minted NOTHING.
# The fix is to let the board be smaller on a small slate rather than lower Z_GATE until a pool
# appears -- loosening the gate to hit a target ticket count is fitting the bar to the answer.
# Take the LARGEST anchor count the pool fully supports.
tickets = []
for _n in range(CFG['ANCH'], 0, -1):
    tickets = draft(_n)
    if tickets:
        if _n < CFG['ANCH']:
            print(f"  thin slate: {CFG['ANCH']} anchors do not fit; drafted {_n}")
        break

moon_anchors = [t['legs'][0] for t in tickets if t['kind'] == 'moon']
for a in {p['name']: p for p in moon_anchors}.values():
    tickets.append(dict(kind='builder', legs=[a], risk=CFG['SINGLE_STAKE']))

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


print("SOCCER BOARD -- 2026-08-26")
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

json.dump([{k: v for k, v in p.items() if k != 'legs'} for p in players],
          open('scored.json', 'w'), indent=1)
json.dump([{'kind': t['kind'], 'risk': t['risk'],
            'legs': [{'name': l['name'], 'odds': l['odds'], 'match': l['match'],
                      'TOTAL': round(l['TOTAL'], 1)} for l in t['legs']]} for t in tickets],
          open('tickets.json', 'w'), indent=1)
print("\n  wrote scored.json + tickets.json")
