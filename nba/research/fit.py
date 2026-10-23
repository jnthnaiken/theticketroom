"""Walk-forward conditional-logit search over feature sets. Metric: mean -log p(actual first scorer) over 10 starters."""
import json, math, sys, itertools
import numpy as np
from scipy.optimize import minimize
X = np.load('X.npy').astype(np.float64); M = json.load(open('meta.json')); NM = M['names']; G = M['games']
y = np.array([g['y'] for g in G]); season = np.array([g['season'] for g in G])
ok = y >= 0

def fit(idx, Xtr, ytr, l2=1e-3):
    A = Xtr[:, :, idx]
    def f(w):
        u = A @ w; m = u.max(1, keepdims=True); e = np.exp(u - m); s = e.sum(1)
        nll = np.sum(np.log(s) + m[:, 0] - u[np.arange(len(ytr)), ytr]) + l2 * w @ w * len(ytr)
        pr = e / s[:, None]; g = (A * pr[:, :, None]).sum(1) - A[np.arange(len(ytr)), ytr]
        return nll, g.sum(0) + 2 * l2 * w * len(ytr)
    return minimize(f, np.zeros(len(idx)), jac=True, method='L-BFGS-B').x

def evaluate(feats, seasons=range(2017, 2026), ret_p=False):
    idx = [NM.index(f) for f in feats]; tot, n, per, P = 0.0, 0, {}, {}
    for S in seasons:
        tr = ok & (season < S); te = ok & (season == S)
        w = fit(idx, X[tr], y[tr])
        u = X[te][:, :, idx] @ w; u -= u.max(1, keepdims=True); p = np.exp(u); p /= p.sum(1, keepdims=True)
        ll = -np.log(p[np.arange(te.sum()), y[te]]); per[S] = ll.mean(); tot += ll.sum(); n += te.sum()
        if ret_p:
            for gi, row in zip(np.where(te)[0], p): P[gi] = row
    return (tot / n, per, w) if not ret_p else (tot / n, per, w, P)

if __name__ == '__main__':
    BASE = ['x_ef', 'x_tf', 'x_fs', 'x_fbc', 'x_fg', 'x_j', 'x_new', 't_tip', 't_first']
    b, per, w = evaluate(BASE)
    print(f'uniform {math.log(10):.4f}   base(production features, one-stage) {b:.4f}')
    print('  per season', {k: round(v, 4) for k, v in per.items()})
    extra = [f for f in NM if f not in BASE]
    print('\n== add one feature at a time ==')
    res = []
    for f in extra:
        s, _, w = evaluate(BASE + [f]); res.append((s, f, w[-1])); print(f'{f:12s} {s:.4f}  delta {s - b:+.4f}  w={w[-1]:+.3f}')
    # forward selection
    print('\n== forward selection ==')
    cur, curs = list(BASE), b
    while True:
        best = None
        for f in [f for f in extra if f not in cur]:
            s, _, _ = evaluate(cur + [f])
            if best is None or s < best[0]: best = (s, f)
        if not best or best[0] > curs - 0.0005: break
        cur.append(best[1]); curs = best[0]; print(f'+ {best[1]:12s} -> {curs:.4f}')
    s, per, w = evaluate(cur)
    print('final', round(s, 4), dict(zip(cur, np.round(w, 3))))
    print('per season', {k: round(v, 4) for k, v in per.items()})
    json.dump({'final': cur}, open('selected.json', 'w'))
