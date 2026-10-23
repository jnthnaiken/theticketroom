"""Ticket-rule search on the walk-forward bet table. Flat 1u at FanDuel (unless noted)."""
import json, collections, itertools, math, sys
B = json.load(open('bets.json'))
def dec(am): return 1 + (am / 100 if am > 0 else 100 / -am)
for b in B:
    b['dfd'] = dec(b['fd']) if b['fd'] else None
    bb = [c for k, c in b['books'].items() if k != '0']
    b['best'] = max(bb) if bb else None
    b['dbest'] = dec(b['best']) if b['best'] else None
SEASONS = [2021, 2022, 2023, 2024, 2025]
B = [b for b in B if b['season'] in SEASONS + [2020]]
days = collections.defaultdict(list)
for b in B: days[(b['season'], b['date'])].append(b)

def run(prob='pb', ev_min=0.3, lo=None, hi=None, per_day=3, fallback=True, jumper=None, price='dfd',
        rank='ev', seasons=SEASONS, min_p=None, max_p=None):
    res = collections.defaultdict(lambda: [0, 0, 0.0])   # season -> picks, hits, units
    for (S, d), R in days.items():
        if S not in seasons: continue
        c = []
        for b in R:
            dd = b.get(price); pp = b.get(prob)
            if not dd or pp is None: continue
            am = b['fd'] if price == 'dfd' else b['best']
            if lo is not None and am < lo: continue
            if hi is not None and am > hi: continue
            if jumper is not None and b['jumper'] != jumper: continue
            if min_p is not None and pp < min_p: continue
            if max_p is not None and pp > max_p: continue
            e = pp * dd - 1
            c.append((e, pp, b, dd))
        key = {'ev': lambda x: -x[0], 'p': lambda x: -x[1], 'ratio': lambda x: -(x[1] * x[3])}[rank]
        c.sort(key=key)
        seen, out = set(), []
        for e, pp, b, dd in c:
            if e < ev_min or b['gid'] in seen: continue
            out.append((b, dd)); seen.add(b['gid'])
            if per_day and len(out) >= per_day: break
        if not out and fallback and c:
            best = max(c, key=lambda x: x[0])
            if best[0] > 0: out = [(best[2], best[3])]
        for b, dd in out:
            r = res[S]; r[0] += 1; r[1] += b['y']; r[2] += (dd - 1) if b['y'] else -1
    tot = [sum(res[s][i] for s in res) for i in range(3)]
    return tot, {s: res[s] for s in sorted(res)}

def fmt(name, out):
    (n, h, u), per = out
    roi = u / n if n else 0
    worst = min((v[2] for v in per.values()), default=0)
    seas = ' '.join(f'{s % 100}:{v[2]:+.0f}' for s, v in per.items())
    return f'{name:58s} n={n:5d} hit={h / max(n,1):5.1%} units={u:+8.1f} roi={roi:+6.1%} worst={worst:+6.1f} | {seas}'

if __name__ == '__main__':
    print(fmt('CHOSEN (pb, EV>=.30, 1/game, cap3, fallback)', run()))
