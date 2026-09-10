#!/usr/bin/env python3
"""
kas_train_fit.py kas_train.parquet --calib calibration.jsonl -- KASV1-2026-09-10, stage 3.

Fits the Kasper challenger on the Statcast training table (kas_train_build.py) and writes a CANDIDATE
weights file for v1. Research only; nothing here touches the board, and a candidate is not live until
it is committed as kas_weights_v1.json with a `proposed` date (then challenge.py judges it on slates
after that date only).

SCOREBOARD = TOP-22 HIT RATE per slate (owner, 2026-09-10: "a full board is 22 bats"). AUC and log loss
are printed as diagnostics.

METHOD, identical to v0 (kasmodel.py) so the weights transfer:
  orient (negate SwStr, CSW, air density) -> z within slate -> clip +-3 -> missing = 0 ->
  L2 logistic with every coefficient >= 0 (an input may only push the way baseball says it does).
Holdout = the LAST season in the table, never seen by the fit that is evaluated on it. The weights
written out are refit on every season.

kHR has no pre-2026 history, so its weight is estimated on the 2026 log with the Statcast score held
as an offset: logit(hr) = a*score_v1 + b*z(kHR), a,b >= 0, and kHR enters v1 at b/a.
"""
import argparse, json, sys
import numpy as np
import pandas as pd
from scipy.optimize import minimize

BAT = ['c_dmg', 'c_hh', 'c_la', 'c_fb']
PIT = ['c_ars', 'c_sp_fb', 'c_sp_swstr', 'c_sp_csw']
PEN = ['c_pen_pa', 'c_pen_hr_side', 'c_pen_x', 'c_pen_top_out']
ENV = ['c_wind_out', 'c_temp', 'c_rho', 'c_park']
NEG = {'c_sp_swstr', 'c_sp_csw', 'c_rho'}
LAM = 5.0
WINSOR = 3.0


def zslate(df, cols, key):
    out = pd.DataFrame(index=df.index)
    g = df.groupby(key)
    for c in cols:
        x = pd.to_numeric(df[c], errors='coerce').astype(float)
        if c in NEG:
            x = -x
        mu = x.groupby(df[key]).transform('mean')
        m2 = (x * x).groupby(df[key]).transform('mean')
        sd = np.sqrt((m2 - mu * mu).clip(lower=0))            # population sd, NaN-skipping, vectorised
        z = (x - mu) / sd.replace(0, np.nan)
        out[c] = z.clip(-WINSOR, WINSOR).fillna(0.0)
    return out


def fit_nn(X, y, lam=LAM, offset=None):
    n, k = X.shape
    off = np.zeros(n) if offset is None else offset
    def f(w):
        t = X @ w[1:] + w[0] + off
        p = 1 / (1 + np.exp(-t)); eps = 1e-12
        ll = -np.sum(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps)) + 0.5 * lam * np.sum(w[1:] ** 2)
        g = p - y
        return ll, np.concatenate([[g.sum()], X.T @ g + lam * w[1:]])
    w0 = np.zeros(k + 1); w0[0] = -2.0
    r = minimize(f, w0, jac=True, method='L-BFGS-B', bounds=[(None, None)] + [(0, None)] * k,
                 options={'maxiter': 500})
    return r.x


def top22(score, y, slates, n=22):
    d = pd.DataFrame({'s': score, 'y': y, 'k': slates})
    hits = shown = 0
    per = {}
    for k, g in d.groupby('k'):
        if len(g) < n:
            continue
        h = int(g.nlargest(n, 's')['y'].sum()); per[k] = h; hits += h; shown += n
    return (hits / shown if shown else float('nan')), per


def auc(score, y):
    from scipy.stats import rankdata
    r = rankdata(score); npos = y.sum(); nneg = len(y) - npos
    return float((r[y == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def logloss(p, y):
    eps = 1e-12
    return float(-np.mean(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps)))


def boot(per_a, per_b, reps=2000, seed=3, n=22):
    ks = sorted(set(per_a) & set(per_b)); rng = np.random.default_rng(seed)
    a = np.array([per_a[k] for k in ks]); b = np.array([per_b[k] for k in ks])
    diffs = []
    for _ in range(reps):
        i = rng.integers(0, len(ks), len(ks)); diffs.append((a[i].sum() - b[i].sum()) / (n * len(ks)))
    diffs = np.sort(diffs)
    return (a.sum() - b.sum()) / (n * len(ks)), diffs[int(.025 * reps)], diffs[int(.975 * reps) - 1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('table')
    ap.add_argument('--calib', default='calibration.jsonl')
    ap.add_argument('--out', default='kas_weights_v1_candidate.json')
    ap.add_argument('--min-season', type=int, default=2016)
    a = ap.parse_args()

    T = pd.read_parquet(a.table)
    T = T[T['season'] >= a.min_season].copy()
    T['k'] = T['d'].astype(str)
    seasons = sorted(T['season'].unique())
    hold = seasons[-1]
    ALL = BAT + PIT + PEN + ENV
    print(f"table: {len(T):,} batter-games | {int(T.hr.sum()):,} HR ({100 * T.hr.mean():.2f}%) | "
          f"{T.k.nunique():,} slates | seasons {seasons} | holdout {hold}")
    print("coverage:", {c: round(float(T[c].notna().mean()), 3) for c in ALL})
    Z = zslate(T, ALL, 'k')
    y = T['hr'].astype(int).values
    tr = (T['season'] != hold).values; te = ~tr

    print(f"\n== HOLDOUT {hold}: fit on {seasons[0]}-{seasons[-2]}, judged on {hold} ({T[te].k.nunique()} slates) ==")
    sets = [('batter', BAT), ('batter+pitching', BAT + PIT), ('+bullpen', BAT + PIT + PEN),
            ('+weather/park', BAT + PIT + ENV), ('ALL', ALL)]
    per = {}
    for name, cols in sets:
        w = fit_nn(Z.loc[tr, cols].values, y[tr])
        s = Z.loc[te, cols].values @ w[1:]
        p = 1 / (1 + np.exp(-(s + w[0])))
        h, per[name] = top22(s, y[te], T.loc[te, 'k'].values)
        print(f"  {name:18s} top22 {100 * h:6.2f}%  AUC {auc(s, y[te]):.4f}  logloss {logloss(p, y[te]):.5f}  "
              f"weights {dict((c, round(float(v), 4)) for c, v in zip(cols, w[1:]))}")
    for lab, x, base in (('+bullpen vs batter+pitching', '+bullpen', 'batter+pitching'),
                         ('+weather/park vs batter+pitching', '+weather/park', 'batter+pitching'),
                         ('ALL vs batter+pitching', 'ALL', 'batter+pitching'),
                         ('batter+pitching vs batter', 'batter+pitching', 'batter')):
        m, lo, hi = boot(per[x], per[base])
        print(f"  {lab:34s} {100 * m:+.2f}pp  95% CI [{100 * lo:+.2f}, {100 * hi:+.2f}]")

    print("\n== one input at a time added to batter+pitching (holdout top-22 / AUC) ==")
    w = fit_nn(Z.loc[tr, BAT + PIT].values, y[tr]); s0 = Z.loc[te, BAT + PIT].values @ w[1:]
    h0, p0 = top22(s0, y[te], T.loc[te, 'k'].values); a0 = auc(s0, y[te])
    for c in PEN + ENV:
        cols = BAT + PIT + [c]
        w = fit_nn(Z.loc[tr, cols].values, y[tr]); s = Z.loc[te, cols].values @ w[1:]
        h, p1 = top22(s, y[te], T.loc[te, 'k'].values)
        m, lo, hi = boot(p1, p0)
        print(f"  + {c:15s} weight {w[-1]:.4f}  top22 {100 * (h - h0):+.2f}pp [{100 * lo:+.2f}, {100 * hi:+.2f}]  AUC {auc(s, y[te]) - a0:+.4f}")

    print("\n== leave-one-season-out (top-22, ALL vs batter+pitching) ==")
    for S in seasons:
        trS = (T['season'] != S).values; teS = ~trS
        r = {}
        for name, cols in (('bp', BAT + PIT), ('all', ALL)):
            w = fit_nn(Z.loc[trS, cols].values, y[trS]); s = Z.loc[teS, cols].values @ w[1:]
            r[name] = top22(s, y[teS], T.loc[teS, 'k'].values)[0]
        print(f"  {S}: batter+pitching {100 * r['bp']:.2f}%   ALL {100 * r['all']:.2f}%   diff {100 * (r['all'] - r['bp']):+.2f}pp")

    # ---- final Statcast weights on every season ----
    wF = fit_nn(Z[ALL].values, y)
    coef = {c: float(v) for c, v in zip(ALL, wF[1:])}
    print("\nFINAL Statcast weights (all seasons):", {c: round(v, 5) for c, v in coef.items()})

    # ---- kHR from the 2026 log, Statcast score as offset ----
    rows = [json.loads(l) for l in open(a.calib)]
    L = pd.DataFrame([r for r in rows if r.get('c_v') is not None and r.get('hr') in (0, 1)])
    kh = None
    if len(L):
        L['k'] = L['date']
        ZL = zslate(L, ALL + ['c_khr'], 'k')
        sL = ZL[ALL].values @ wF[1:]
        yL = L['hr'].astype(int).values
        g = fit_nn(np.column_stack([sL, ZL['c_khr'].values]), yL)
        aa, bb = g[1], g[2]
        kh = (bb / aa) if aa > 0 else 0.0
        coef['c_khr'] = float(kh)
        print(f"\n2026 log: {L.k.nunique()} nights, {len(L):,} bats, {int(yL.sum())} HR | offset fit a={aa:.4f} b(kHR)={bb:.4f} -> kHR weight {kh:.5f}")
        sV1 = ZL[ALL + ['c_khr']].values @ np.array([coef[c] for c in ALL + ['c_khr']])
        L['imp'] = L['odds'].apply(lambda o: np.nan if o is None or o != o else (100 / (o + 100) if o > 0 else -o / (-o + 100)))
        hV1, pV1 = top22(sV1, yL, L.k.values)
        hP, pP = top22(L['imp'].fillna(0).values, yL, L.k.values)
        print(f"  2026 top-22: v1 candidate {100 * hV1:.2f}%   price {100 * hP:.2f}%"
              f"   (v1's Statcast part never saw 2026; its kHR weight did)")
        if 'kas_v0' in L:
            h0_, p0_ = top22(L['kas_v0'].fillna(-9).values, yL, L.k.values)
            m, lo, hi = boot(pV1, p0_)
            print(f"  2026 top-22: v0 {100 * h0_:.2f}% (in-sample)  v1-v0 {100 * m:+.2f}pp [{100 * lo:+.2f}, {100 * hi:+.2f}]")
        m, lo, hi = boot(pV1, pP)
        print(f"  v1 - price {100 * m:+.2f}pp [{100 * lo:+.2f}, {100 * hi:+.2f}]")

    inputs = ALL + (['c_khr'] if kh is not None else [])
    out = {'model': 'kas_v1', 'proposed': None, 'inputs': inputs, 'negate': sorted(NEG), 'winsor': WINSOR,
           'missing': 0.0, 'coef': {c: round(coef[c], 6) for c in inputs}, 'intercept': round(float(wF[0]), 6),
           'fit': {'method': f'L2 logistic (lambda={LAM}), coefficients >= 0 after orientation; per-slate z; '
                             f'Statcast {seasons[0]}-{seasons[-1]}; kHR by offset fit on the 2026 log',
                   'rows': int(len(T)), 'hr': int(T.hr.sum()), 'slates': int(T.k.nunique())}}
    json.dump(out, open(a.out, 'w'), indent=1)
    print(f"\nwrote {a.out}")


if __name__ == '__main__':
    main()
