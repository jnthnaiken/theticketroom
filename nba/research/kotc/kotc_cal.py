#!/usr/bin/env python3
"""KOTCCAL-2026-10-27: fit King of the Court's PRA spread on 2025-26 and check its P(top) calibration.

    python3 kotc_cal.py pra_odds.psv out_dir

pra_odds.psv: BettingPros market 338 history (pull_bp162.js with MARKET=338): date|event|home|visitor|bp|name|pos|team|book|line|side|cost|main
Results: nba.com box scores (nba_nbacom) -> PRA per player-game.
1. Per player-game: main line (median across books), de-vigged over chance (median), actual PRA.
2. Fit sd = A*mean + B by maximum likelihood (Normal), mean backed out of line + over chance as live.
3. Every night: P(top PRA) with the fitted and the v1 spread; calibration (predicted vs actual leader), log loss,
   and how often the crowned pick and the favourite led the night; Tuesdays reported on their own.
"""
import json, math, os, sys, statistics as st, datetime, concurrent.futures as cf
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, '..', '..')]
import nba_nbacom as N, nba_kotc as K
ODDS, OUT = sys.argv[1:3]; os.makedirs(OUT, exist_ok=True)
BPT = {'UTH': 'UTA', 'NOR': 'NOP', 'NO': 'NOP', 'PHO': 'PHX', 'BRK': 'BKN', 'GS': 'GSW', 'NY': 'NYK', 'SA': 'SAS', 'WSH': 'WAS', 'CHO': 'CHA'}
ip = lambda c: 100 / (c + 100) if c > 0 else -c / (-c + 100)
def nk(s):
    import unicodedata, re
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower(); s = re.sub(r"[.'\-]", ' ', s)
    return ' '.join(w for w in s.split() if w not in ('jr', 'sr', 'ii', 'iii', 'iv'))
rows = {}
for l in open(ODDS):
    f = l.rstrip('\n').split('|')
    if len(f) < 13 or f[12] != '1': continue
    d, name, team, book, line, side, cost = f[0], f[5], BPT.get(f[7], f[7]), f[8], float(f[9]), f[10], float(f[11])
    rows.setdefault((d, team, name), {}).setdefault(book, {})[side] = (line, cost)
P = {}
for (d, t, n), bk in rows.items():
    ls, po = [], []
    for b in bk.values():
        if 'O' in b and 'U' in b and b['O'][0] == b['U'][0]:
            o, u = ip(b['O'][1]), ip(b['U'][1]); ls.append(b['O'][0]); po.append(o / (o + u))
    if ls: P[(d, t, n)] = dict(date=d, team=t, name=n, line=st.median(ls), pover=st.median(po))
dates = sorted({k[0] for k in P}); print('player-games priced', len(P), 'nights', len(dates), flush=True)
def night(d):
    out = {}
    try:
        for gid, a, h, stt, *_ in N.scoreboard(d):
            if stt != 'post': continue
            try:
                for b in N.parse(N.summary(gid))['box']:
                    if b['played']: out[(b['team'], nk(b['name']))] = b['pra']
            except Exception as e: print('  box', d, gid, str(e)[:80], flush=True)
    except Exception as e: print('  sb', d, str(e)[:80], flush=True)
    return d, out
res = {}
with cf.ThreadPoolExecutor(6) as ex:
    for d, o in ex.map(night, dates): res[d] = o
obs = []
for k, r in P.items():
    v = res.get(r['date'], {}).get((r['team'], nk(r['name'])))
    if v is not None: obs.append(dict(r, pra=v))
print('matched player-games', len(obs), flush=True)
json.dump(obs, open(os.path.join(OUT, 'pra_obs.json'), 'w'))
def mean_sd(r, A, B):
    sd0 = A * r['line'] + B; m = r['line'] + sd0 * K.ninv(r['pover']); return m, A * m + B
def nll(A, B):
    t = 0.0
    for r in obs:
        m, s = mean_sd(r, A, B); z = (r['pra'] - m) / s; t += 0.5 * z * z + math.log(s)
    return t / len(obs)
best = min(((A, B) for A in [x / 100 for x in range(8, 36, 2)] for B in [x / 2 for x in range(0, 15)]), key=lambda ab: nll(*ab))
print('fit sd = %.2f*mean + %.1f  nll %.4f   (v1 0.20*mean+2.5 nll %.4f)' % (best[0], best[1], nll(*best), nll(0.20, 2.5)), flush=True)
resid = [r['pra'] - mean_sd(r, *best)[0] for r in obs]; print('mean residual (bias) %.2f' % (sum(resid) / len(resid)))
# nightly calibration
by = {}
for r in obs: by.setdefault(r['date'], []).append(r)
def evaluate(A, B, label, only_tue=False):
    K.SD_A, K.SD_B = A, B; K.N_SIM = 20000
    ll = 0; n = 0; crown_hits = fav_hits = 0; bins = {}
    for d, L in sorted(by.items()):
        if only_tue and datetime.date.fromisoformat(d).weekday() != 1: continue
        if len(L) < 8: continue
        mx = max(r['pra'] for r in L); winners = [r['name'] for r in L if r['pra'] == mx]
        C = K.crown([dict(r) for r in L])
        pw = sum(c['p'] for c in C if c['name'] in winners); ll += -math.log(max(pw, 1e-4)); n += 1
        if next(c for c in C if c['crown'])['name'] in winners: crown_hits += 1
        if C[0]['name'] in winners: fav_hits += 1
        for c in C[:10]:
            b = min(int(c['p'] * 10), 9); bins.setdefault(b, [0, 0, 0.0]); bins[b][0] += 1; bins[b][1] += c['name'] in winners; bins[b][2] += c['p']
    cal = {f'{b*10}-{b*10+10}%': (v[0], round(v[2] / v[0], 3), round(v[1] / v[0], 3)) for b, v in sorted(bins.items())}
    print(f'{label}: nights {n}, log loss {ll / max(n, 1):.3f}, crowned pick led {crown_hits} ({crown_hits / max(n, 1):.1%}), favourite led {fav_hits} ({fav_hits / max(n, 1):.1%})', flush=True)
    print('   calibration (n, predicted, actual):', cal, flush=True)
for only in (False, True):
    evaluate(*best, f'FITTED sd {"Tuesdays" if only else "all nights"}', only)
    evaluate(0.20, 2.5, f'v1     sd {"Tuesdays" if only else "all nights"}', only)
json.dump({'SD_A': best[0], 'SD_B': best[1]}, open(os.path.join(OUT, 'fit.json'), 'w'))
