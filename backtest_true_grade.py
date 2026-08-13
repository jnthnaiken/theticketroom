#!/usr/bin/env python3
"""backtest_true, stage 4 -- grade everything against TRUE outcomes.

Grades five boards per night with grade_night.grade_ticket VERBATIM (round-robin math,
american->decimal, DNP/ppd legs VOID as refunds -- the rule backtest_mix.py silently
disabled with its 'everyone played' approximation):

  shipped -- the night's D_<date>.json tickets as committed (the real product)
  old3 / new5 / mix75 / mkt -- cold re-drafts from backtest_true_draft.js

Plus the lower-variance read: flat 1u top-8 singles per night under each ranking, vs
top-8 market favorites. Prices are the night's baked odds -- the same set that fed
_zmkt, shared across conditions (internally consistent; NOT independent closing lines,
so no CLV claim is possible from this).
"""
import json, math, os
from grade_night import grade_ticket, dec, norm

OUT = json.load(open('bt_outcomes.json'))
nights = [d for d in json.load(open('bt_nights.json')) if d in OUT]
patches = json.load(open('bt_patches.json'))
CONDS = ['new5', 'old3', 'mkt', 'mix75']
KINDS = ['moon', 'biggest', 'builder', 'lunch', 'late', 'chef']

def grade_board(tickets, played, homered, ppd):
    tot, staked, per = 0.0, 0.0, {}
    for t in tickets:
        g = grade_ticket(t, homered, played, ppd, 1.0)
        if not g or g.get('won') is None: continue
        tot += g['net']; staked += g['stake']
        k = t.get('kind', '?')
        per[k] = per.get(k, 0.0) + g['net']
    return tot, staked, per

res = {c: {'net': 0.0, 'staked': 0.0, 'per': {}, 'nightly': []} for c in CONDS + ['shipped']}
sing = {c: {'net': 0.0, 'n': 0} for c in CONDS + ['mktrank']}
skipped = []

for dt in nights:
    o = OUT[dt]
    played, homered, ppd = set(o['p']), set(o['h']), set(o['ppd'])
    D0 = json.load(open(f'D_{dt}.json'))
    n, s, per = grade_board(D0.get('tickets', []), played, homered, ppd)
    res['shipped']['net'] += n; res['shipped']['staked'] += s; res['shipped']['nightly'].append(n)
    for k, v in per.items(): res['shipped']['per'][k] = res['shipped']['per'].get(k, 0.0) + v
    for c in CONDS:
        try:
            rec = json.load(open(f'bt_results/{dt}_{c}.json'))
        except Exception as e:
            skipped.append((dt, c, str(e))); res[c]['nightly'].append(0.0); continue
        if rec.get('err'):
            skipped.append((dt, c, rec['err'])); res[c]['nightly'].append(0.0); continue
        n, s, per = grade_board(rec['tickets'], played, homered, ppd)
        res[c]['net'] += n; res[c]['staked'] += s; res[c]['nightly'].append(n)
        for k, v in per.items(): res[c]['per'][k] = res[c]['per'].get(k, 0.0) + v
    P = D0['players']
    withodds = [nm for nm, p in P.items() if p.get('odds')]
    def flat(nms):
        net, cnt = 0.0, 0
        for nm in nms:
            nn = norm(P[nm].get('nm', nm))
            if nn not in played: continue          # DNP -> void, no stake
            cnt += 1
            net += (dec(P[nm]['odds']) - 1) if nn in homered else -1.0
        return net, cnt
    for c in CONDS:
        pt = patches[dt][c]
        top = sorted(withodds, key=lambda nm: -pt[nm][2])[:8]
        n2, c2 = flat(top); sing[c]['net'] += n2; sing[c]['n'] += c2
    topm = sorted(withodds, key=lambda nm: P[nm]['odds'])[:8]
    n2, c2 = flat(topm); sing['mktrank']['net'] += n2; sing['mktrank']['n'] += c2

def se(a):
    n = len(a)
    if n < 2: return 0.0
    m = sum(a) / n
    return (sum((x - m) ** 2 for x in a) / (n - 1)) ** 0.5 / math.sqrt(n) * n

print(f"=== TRUE-ENGINE BACKTEST | {len(nights)} nights {nights[0]}..{nights[-1]} ===")
print("engine: CURRENT index.html client drafter, cold start 10:00 ET, no locks/carry")
print("outcomes: StatsAPI boxscore PA + HR; DNP/ppd legs VOID via grade_night.grade_ticket")
print("prices: each night's baked odds, shared across all conditions\n")
LAB = {'shipped': 'SHIPPED board as committed (real product)',
       'old3':    'old _SIG .45/.35/.20 @ 50/50  (pre-refit)',
       'new5':    'new _SIG 5-signal @ 50/50     (LIVE model)',
       'mix75':   'new _SIG 5-signal @ 75/25',
       'mkt':     'market-only alpha=1.0         (PRICE BENCHMARK)'}
for c in ['shipped', 'old3', 'new5', 'mix75', 'mkt']:
    r = res[c]
    roi = (r['net'] / r['staked'] * 100) if r['staked'] else 0.0
    wins = sum(1 for x in r['nightly'] if x > 0)
    print(f"{LAB[c]:47s} net {r['net']:+8.1f}u  ROI {roi:+6.1f}%  +/-{se(r['nightly']):.0f}u SE  wins {wins}/{len(r['nightly'])}")
    print('    ' + '  '.join(f"{k} {r['per'].get(k, 0.0):+.1f}" for k in KINDS if k in r['per']))
print("\n--- flat 1u singles, top-8 per night (DNP = void, no stake) ---")
for c in ['old3', 'new5', 'mix75', 'mkt', 'mktrank']:
    s = sing[c]
    roi = s['net'] / s['n'] * 100 if s['n'] else 0
    nm = 'top-8 by market price (favorites)' if c == 'mktrank' else f'top-8 by TOTAL ({c})'
    print(f"  {nm:36s} net {s['net']:+8.1f}u on {s['n']} bets  ROI {roi:+6.1f}%")
print("\nEvery total above is jackpot-shaped (round robins); read the SE before the net.")
print("This answers 'does any basket beat the price ON THIS SAMPLE' -- it cannot prove an edge exists.")
if skipped: print('SKIPPED:', skipped)
json.dump({'res': res, 'singles': sing, 'skipped': skipped}, open('bt_grades.json', 'w'), indent=1)
