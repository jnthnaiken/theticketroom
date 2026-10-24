"""FBL-REBUILD layer filter: within the production value pool (z>=0.75, cap 4/game), does any FirstBasketLand stat
(or old feature) split the bets into better/worse ROI -- consistently in SELECT (2021-23) and HOLD (2024-25)?"""
import json, collections, numpy as np
from search import X, NM, M3
from bt import B, dec
idx = {(str(g['gid']), n): (gi, j) for gi, g in enumerate(M3['games']) for j, n in enumerate(g['names'])}
days = collections.defaultdict(list)
for b in B:
    if b['season'] >= 2021 and b['fd']: days[(b['season'], b['date'])].append(b)
pool = []
for (S, d), R in days.items():
    key = lambda b: b['pb'] * dec(b['fd']); v = [key(b) for b in R]
    if len(v) < 8: continue
    m = sum(v) / len(v); sd = (sum((x - m) ** 2 for x in v) / len(v)) ** .5 or 1e-9; per = collections.Counter()
    for b in sorted(R, key=lambda b: -key(b)):
        if (key(b) - m) / sd < 0.75 or per[b['gid']] >= 4: continue
        per[b['gid']] += 1; k = idx.get((str(b['gid']), b['name']))
        if k: pool.append((S, (dec(b['fd']) - 1) if b['y'] else -1.0, X[k[0], k[1]]))
print('pool bets', len(pool))
U = np.array([p[1] for p in pool]); Sn = np.array([p[0] for p in pool]); F = np.array([p[2] for p in pool])
sel = Sn <= 2023; hold = ~sel
print(f'all pool: select {U[sel].mean():+.1%} (n={sel.sum()}) hold {U[hold].mean():+.1%} (n={hold.sum()})')
res = []
for i, n in enumerate(NM):
    f = F[:, i]
    if np.std(f) < 1e-6: continue
    q1, q2 = np.quantile(f[sel], [1/3, 2/3])
    lo, hi = f <= q1, f >= q2
    s_hi, s_lo = U[sel & hi].mean(), U[sel & lo].mean(); h_hi, h_lo = U[hold & hi].mean(), U[hold & lo].mean()
    res.append((s_hi - s_lo, n, s_hi, s_lo, h_hi, h_lo, (sel & hi).sum(), (hold & hi).sum()))
res.sort(key=lambda r: -abs(r[0]))
print(f'{"feature":12s} {"sel top3rd":>10s} {"sel bot3rd":>10s} {"hold top":>9s} {"hold bot":>9s}  same sign?')
for d, n, sh, sl, hh, hl, a, b in res[:20]:
    print(f'{n:12s} {sh:+10.1%} {sl:+10.1%} {hh:+9.1%} {hl:+9.1%}  {"YES" if (sh - sl) * (hh - hl) > 0 else "no"}')
