"""BBTUNE: tune the basketball board rules walk-forward. For each test season S (2022-25), every rule setting is scored
on seasons 2021..S-1 only; the best is then played blind in S. Compared with the current (baseball-copied) rules."""
import json, collections, itertools, math, sys
import numpy as np
B = json.load(open('/home/claude/fbr/bets.json'))
def dec(am): return 1 + (am / 100 if am > 0 else 100 / -am)
days = collections.defaultdict(list)
for b in B:
    if b['season'] >= 2021 and b['fd']: days[(b['season'], b['date'])].append({'gid': b['gid'], 'y': b['y'], 'pb': b['pb'], 'dfd': dec(b['fd']), 'am': b['fd']})
NIGHTS = sorted(days)
# precompute z per night
for k in NIGHTS:
    R = days[k]; v = [b['pb'] * b['dfd'] for b in R]; m = sum(v) / len(v); sd = (sum((x - m) ** 2 for x in v) / len(v)) ** .5 or 1e-9
    for b in R: b['z'] = (b['pb'] * b['dfd'] - m) / sd
    R.sort(key=lambda b: -b['z'])
def pool(R, z, cap, maxam, minam):
    out, per = [], collections.Counter()
    if len(R) < 8: return out
    for b in R:
        if b['z'] < z: break
        if per[b['gid']] >= cap or (maxam and b['am'] > maxam) or (minam and b['am'] < minam): continue
        out.append(b); per[b['gid']] += 1
    return out
def anchors_units(P, n): return sum((b['dfd'] - 1) if b['y'] else -1 for b in P[:n]), len(P[:n])
def rr(legs, unit):
    st = ret = 0.0
    for k in range(2, len(legs) + 1):
        for cb in itertools.combinations(legs, k):
            st += unit
            if all(b['y'] for b in cb): ret += unit * math.prod(b['dfd'] for b in cb)
    return ret - st, st
def moons(P, n, per_a, legs, diff):
    A = P[:n]; rest = P[n:]; M = []
    for a in A:
        ok = [b for b in rest if b['gid'] != a['gid']]; got = []
        for cb in itertools.combinations(ok, legs - 1):
            if len({a['gid']} | {x['gid'] for x in cb}) != legs: continue
            if got and len({id(x) for x in got[0]} - {id(x) for x in cb}) < diff: continue
            got.append(cb)
            if len(got) == per_a: break
        M += [[a, *cb] for cb in got]
    return M
ZS = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0); NS = (1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 99); CAPS = (1, 2, 4); MAXS = (None, 1500, 2000, 3000); MINS = (None, 500, 800)
# ---- anchors: per (setting, season) units & bets
grid = list(itertools.product(ZS, NS, CAPS, MAXS, MINS))
U = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0]))
for k in NIGHTS:
    S = k[0]
    for z, cap, mx, mn in itertools.product(ZS, CAPS, MAXS, MINS):
        P = pool(days[k], z, cap, mx, mn)
        for n in NS:
            u, c = anchors_units(P, n); r = U[(z, n, cap, mx, mn)][S]; r[0] += u; r[1] += c
CUR = (0.75, 4, 4, None, None)
def season_line(s): return ' '.join(f'{S%100}:{U[s][S][0]:+.0f}' for S in range(2021, 2026))
print('current anchors     ', CUR, season_line(CUR), f'total {sum(U[CUR][S][0] for S in range(2022, 2026)):+.0f}u (2022-25)')
wf = 0.0; wn = 0; picks = {}
for S in range(2022, 2026):
    best = max(grid, key=lambda s: sum(U[s][T][0] for T in range(2021, S)))
    picks[S] = best; wf += U[best][S][0]; wn += U[best][S][1]
    print(f'  {S}: chosen on 2021-{S-1}: z>={best[0]} anchors={best[1]} cap/game={best[2]} max=+{best[3]} min=+{best[4]} -> {S}: {U[best][S][0]:+.0f}u on {U[best][S][1]} bets')
cur = sum(U[CUR][S][0] for S in range(2022, 2026)); curn = sum(U[CUR][S][1] for S in range(2022, 2026))
print(f'ANCHORS walk-forward tuned 2022-25: {wf:+.0f}u on {wn} ({wf/wn:+.1%}) | current rules same seasons: {cur:+.0f}u on {curn} ({cur/curn:+.1%})')
top = sorted(grid, key=lambda s: -sum(U[s][T][0] for T in range(2021, 2026)))[:8]
print('best settings with full hindsight (for reference only):')
for s in top: print('   ', s, season_line(s), f'total {sum(U[s][T][0] for T in range(2021, 2026)):+.0f}u on {sum(U[s][T][1] for T in range(2021, 2026))}')
json.dump({str(k): v for k, v in picks.items()}, open('anchor_picks.json', 'w'))
