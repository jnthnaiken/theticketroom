"""FBL-REBUILD layer search. Conditional logit over the 10 starters, walk-forward by season (train on every earlier
season). SELECT on 2017-22, HOLD OUT 2023-25 (never looked at during selection). Ground-up forward selection from
the empty model over the union of the old feature set (fbr/X.npy) and the FirstBasketLand families (X3.npy)."""
import json, math, sys
import numpy as np
from scipy.optimize import minimize
X0 = np.load('/home/claude/fbr/X.npy').astype(np.float64); M0 = json.load(open('/home/claude/fbr/meta.json'))
X3 = np.load('X3.npy').astype(np.float64); M3 = json.load(open('meta3.json'))
assert all(a['names'] == b['names'] for a, b in zip(M0['games'], M3['games']))
X = np.concatenate([X0, X3], axis=2); NM = ['o_' + n for n in M0['names']] + M3['names']
y = np.array([g['y'] for g in M3['games']]); season = np.array([int(g['season']) for g in M3['games']]); ok = y >= 0
SEL, HOLD = range(2017, 2023), range(2023, 2026)

def fit(idx, Xtr, ytr, l2=1e-3):
    A = Xtr[:, :, idx]
    def f(w):
        u = A @ w; m = u.max(1, keepdims=True); e = np.exp(u - m); s = e.sum(1)
        nll = np.sum(np.log(s) + m[:, 0] - u[np.arange(len(ytr)), ytr]) + l2 * w @ w * len(ytr)
        pr = e / s[:, None]; g = (A * pr[:, :, None]).sum(1) - A[np.arange(len(ytr)), ytr]
        return nll, g.sum(0) + 2 * l2 * w * len(ytr)
    return minimize(f, np.zeros(len(idx)), jac=True, method='L-BFGS-B').x

def evaluate(feats, seasons):
    if not feats: return math.log(10), {}
    idx = [NM.index(f) for f in feats]; tot, n, per = 0.0, 0, {}
    for S in seasons:
        tr = ok & (season < S); te = ok & (season == S)
        w = fit(idx, X[tr], y[tr])
        u = X[te][:, :, idx] @ w; u -= u.max(1, keepdims=True); p = np.exp(u); p /= p.sum(1, keepdims=True)
        ll = -np.log(p[np.arange(te.sum()), y[te]]); per[S] = round(ll.mean(), 4); tot += ll.sum(); n += te.sum()
    return tot / n, per

if __name__ == '__main__':
    PROD = ['o_x_ef', 'o_x_tf', 'o_x_fs', 'o_x_fbc', 'o_x_fg', 'o_x_j', 'o_x_new', 'o_t_tip', 'o_t_first']
    pb, _ = evaluate(PROD, SEL); ph, pper = evaluate(PROD, HOLD)
    print(f'uniform {math.log(10):.4f} | production select {pb:.4f} hold {ph:.4f} {pper}')
    fbl = M3['names']; fb_, _ = evaluate(fbl, SEL); fh, fper = evaluate(fbl, HOLD)
    print(f'all FBL families only: select {fb_:.4f} hold {fh:.4f} {fper}')
    for fam in 'tmpf':
        fs = [n for n in fbl if n.startswith(fam + '_')]
        s, _ = evaluate(fs, SEL); print(f'  family {fam.upper()} alone ({len(fs)}): select {s:.4f}')
    al, _ = evaluate(NM, SEL); ah, aper = evaluate(NM, HOLD)
    print(f'everything ({len(NM)}): select {al:.4f} hold {ah:.4f} {aper}')
    print('\n== ground-up forward selection (select seasons only) ==')
    cur, curs = [], math.log(10)
    while True:
        best = None
        for f in [f for f in NM if f not in cur]:
            s, _ = evaluate(cur + [f], SEL)
            if best is None or s < best[0]: best = (s, f)
        if not best or best[0] > curs - 0.0003: break
        cur.append(best[1]); curs = best[0]; print(f'+ {best[1]:12s} -> {curs:.4f}', flush=True)
    h, hper = evaluate(cur, HOLD)
    print('FINAL', cur, f'select {curs:.4f} hold {h:.4f}', hper, '| production hold', round(ph, 4))
    json.dump({'final': cur}, open('selected3.json', 'w'))
