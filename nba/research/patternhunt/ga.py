"""PATTERN-HUNT: genetic search for layered betting rules + null calibration.
A rule = AND of up to 4 conditions 'feature j in quintile bins [lo..hi]' over every priced starter; bet 1u at FanDuel.
Fitness = t-statistic of profit on TRAIN (2020-22), min 400 bets. Top 50 distinct rules -> pick best on VALIDATE
(2023-24) -> report TEST (2025) once. NULL: same pipeline with the first scorer shuffled within each game (prices
kept), to measure how good the best pattern found in pure noise looks."""
import json, sys, numpy as np, collections
W = np.load('W.npy'); WM = json.load(open('Wmeta.json')); cols = WM['cols']; meta = WM['meta']
gid = np.array([m[0] for m in meta]); S = np.array([m[1] for m in meta]); y0 = np.array([m[5] for m in meta]); dfd = np.array([m[6] for m in meta])
TR, VA, TE = S <= 2022, (S >= 2023) & (S <= 2024), S == 2025
NB = 5
edges = [np.unique(np.quantile(W[TR, j], np.linspace(0, 1, NB + 1)[1:-1])) for j in range(W.shape[1])]
BIN = np.stack([np.searchsorted(edges[j], W[:, j], side='right') for j in range(W.shape[1])], 1).astype(np.int8)
nbins = np.array([len(e) + 1 for e in edges]); usable = np.where(nbins >= 2)[0]
import os
if os.environ.get('NOMODEL'):     # search only raw data layers: drop our model's outputs
    usable = np.array([j for j in usable if cols[j] not in ('p_model', 'pb', 'edge', 'pteam', 'share', 'ptip')])
def profit(y): return np.where(y == 1, dfd - 1, -1.0)
def mask(rule, rows):
    m = np.ones(rows.sum(), bool); Bs = BIN[rows]
    for j, lo, hi in rule: m &= (Bs[:, j] >= lo) & (Bs[:, j] <= hi)
    return m
def tstat(u):
    n = len(u)
    if n < 400: return -9.0, n, 0.0
    sd = u.std() or 1e-9; return u.mean() / (sd / np.sqrt(n)), n, u.mean()
def rand_cond(rng):
    j = int(rng.choice(usable)); k = nbins[j]
    while True:
        lo = int(rng.integers(0, k)); hi = int(rng.integers(lo, k))
        if not (lo == 0 and hi == k - 1): return (j, lo, hi)
def norm(rule):
    d = {}
    for j, lo, hi in rule: d[j] = (max(lo, d[j][0]), min(hi, d[j][1])) if j in d else (lo, hi)
    return tuple(sorted((j, lo, hi) for j, (lo, hi) in d.items() if lo <= hi))
def search(y, seed, gens=120, pop=300):
    rng = np.random.default_rng(seed); uTR = profit(y)[TR]; cache = {}
    def fit(r):
        if r not in cache: cache[r] = tstat(uTR[mask(r, TR)])[0] if r else -9.0
        return cache[r]
    P = [norm([rand_cond(rng) for _ in range(rng.integers(1, 5))]) for _ in range(pop)]
    for g in range(gens):
        P = sorted(set(P), key=lambda r: -fit(r)); elite = P[:30]; kids = list(elite)
        while len(kids) < pop:
            a = elite[rng.integers(len(elite))] if rng.random() < .7 else P[rng.integers(len(P))]
            r = list(a); op = rng.random()
            if op < .25 and len(r) < 4: r.append(rand_cond(rng))
            elif op < .4 and len(r) > 1: r.pop(rng.integers(len(r)))
            elif op < .7 and r:
                i = rng.integers(len(r)); j, lo, hi = r[i]; k = nbins[j]
                lo = int(np.clip(lo + rng.integers(-1, 2), 0, k - 1)); hi = int(np.clip(hi + rng.integers(-1, 2), lo, k - 1)); r[i] = (j, lo, hi)
            elif op < .85:
                b = P[rng.integers(min(len(P), 100))]; r = list(r) + [c for c in b if rng.random() < .5]; r = r[:4]
            else: r = [rand_cond(rng) for _ in range(rng.integers(1, 5))]
            r = norm(r)
            if r: kids.append(r)
        P = kids
    top = sorted(cache, key=lambda r: -cache[r])[:50]
    u = profit(y)
    best = max(top, key=lambda r: tstat(u[VA][mask(r, VA)])[0])
    tr = tstat(u[TR][mask(best, TR)]); va = tstat(u[VA][mask(best, VA)]); te = tstat(u[TE][mask(best, TE)])
    return best, tr, va, te
def shuffled(seed):
    """MARKET-TRUE null: each game's first scorer drawn from the de-vigged FanDuel probabilities of its starters
    (games where a bench player scored keep no winner). Prices unchanged, so every rule's true edge is the vig."""
    rng = np.random.default_rng(seed); y = np.zeros_like(y0)
    for g, ix in pd_groups.items():
        if y0[ix].sum() != 1: continue
        q = 1 / dfd[ix]; y[ix[rng.choice(len(ix), p=q / q.sum())]] = 1
    return y
pd_groups = collections.defaultdict(list)
for i, g in enumerate(gid): pd_groups[g].append(i)
pd_groups = {g: np.array(v) for g, v in pd_groups.items()}
def show(rule): return ' AND '.join(f'{cols[j]} in q{lo+1}-q{hi+1}' for j, lo, hi in rule)
if __name__ == '__main__':
    mode = sys.argv[1]; n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    out = []
    for k in range(n):
        y = y0 if mode == 'real' else shuffled(1000 + k)
        best, tr, va, te = search(y, seed=k)
        rec = {'mode': mode, 'k': k, 'rule': show(best), 'train': [round(tr[0], 2), int(tr[1]), round(tr[2], 4)],
               'val': [round(va[0], 2), int(va[1]), round(va[2], 4)], 'test': [round(te[0], 2), int(te[1]), round(te[2], 4)]}
        print(json.dumps(rec), flush=True); out.append(rec)
    json.dump(out, open(f'res_{mode}{os.environ.get("NOMODEL","")}.json', 'w'))
