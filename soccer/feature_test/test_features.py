#!/usr/bin/env python3
"""test_features.py -- FEATTEST-2026-09-17. Does anything beyond the price (and the current xG
score) predict who scores?

Every model is a ridge logistic on top of the price:  p = sigmoid(b0 + b1*L + b2*L^2 + sum(b_k*x_k))
L = logit(implied probability). A feature only matters if it moves p AWAY from what the price
already says, so the price terms are always in, and each candidate is judged by what it ADDS.

Checks
  1. full-sample coefficient and z (Wald)             -- is there any signal at all
  2. walk-forward log loss vs price-only               -- does it predict nights it never saw
     (fit on earlier nights, score the next; bootstrap over nights for the 90% band)
  3. walk-forward top-8 ROI, flat 1u                   -- does it pick better bets

    python3 build_rows.py && python3 test_features.py
"""
import io, json, math, os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'nfl'))
from nfl_ev_fit import implied, dec, logit, sig, clip, _solve, roi

LAM = 1.0
WARM = 6
TOPN = 8
B = 2000

CANDS = {
    'xg_score (live)': ['z'],
    'home': ['home'],
    'team_attack': ['team_att', 'team_miss'],
    'opp_defence': ['opp_def', 'opp_miss'],
    'team_exp_goals': ['team_xg', 'team_miss', 'opp_miss'],
    'minutes': ['mins', 'pl_miss'],
    'penalties': ['pens', 'pl_miss'],
    'player_form': ['form', 'pl_miss'],
    'team_form': ['team_form', 'team_miss'],
}
ALL = ['z', 'home', 'team_xg', 'mins', 'pens', 'form', 'team_form', 'team_miss', 'opp_miss', 'pl_miss']


def X(r, keys, mu, sd):
    L = clip(logit(implied(r['odds'])), (-4.0, 1.5))
    return [1.0, L, L * L] + [(r[k] - mu[k]) / sd[k] for k in keys]


def scaler(rows, keys):
    mu, sd = {}, {}
    for k in keys:
        v = [r[k] for r in rows]
        mu[k] = sum(v) / len(v)
        sd[k] = (sum((a - mu[k]) ** 2 for a in v) / len(v)) ** .5 or 1.0
    return mu, sd


def fit(rows, keys, iters=40, want_se=False):
    mu, sd = scaler(rows, keys)
    Xs = [X(r, keys, mu, sd) for r in rows]
    y = [r['y'] for r in rows]
    k = 3 + len(keys)
    w = [logit(sum(y) / len(y))] + [0.0] * (k - 1)
    for _ in range(iters):
        g = [0.0] * k
        H = [[0.0] * k for _ in range(k)]
        for xi, yi in zip(Xs, y):
            p = sig(sum(a * b for a, b in zip(w, xi)))
            q = p * (1 - p)
            for i in range(k):
                g[i] += (yi - p) * xi[i]
                for j in range(i, k):
                    H[i][j] += q * xi[i] * xi[j]
        for i in range(k):
            for j in range(i):
                H[i][j] = H[j][i]
        for i in range(3, k):
            g[i] -= LAM * w[i]
            H[i][i] += LAM
        step = _solve(H, g)
        w = [a + s for a, s in zip(w, step)]
        if max(abs(s) for s in step) < 1e-8:
            break
    se = None
    if want_se:
        se = []
        for i in range(k):
            e = [0.0] * k
            e[i] = 1.0
            se.append(math.sqrt(max(_solve([row[:] for row in H], e)[i], 0)))
    return dict(w=w, mu=mu, sd=sd, keys=keys, se=se)


def pr(m, r):
    return sig(sum(a * b for a, b in zip(m['w'], X(r, m['keys'], m['mu'], m['sd']))))


def ll(p, y):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -math.log(p if y else 1 - p)


def walk(rows, keys):
    """per-night held-out log loss, and the top-N picks by EV."""
    nights = sorted({r['date'] for r in rows})
    per, picks = {}, []
    for i, d in enumerate(nights):
        if i < WARM:
            continue
        tr = [r for r in rows if r['date'] < d]
        te = [r for r in rows if r['date'] == d]
        m = fit(tr, keys)
        per[d] = [ll(pr(m, r), r['y']) for r in te]
        picks += sorted(te, key=lambda r: -(pr(m, r) * dec(r['odds']) - 1))[:TOPN]
    return per, picks


def boot_diff(a, b):
    ds = sorted(a)
    random.seed(7)
    out = []
    for _ in range(B):
        s = random.choices(ds, k=len(ds))
        n = sum(len(a[d]) for d in s)
        out.append((sum(sum(b[d]) for d in s) - sum(sum(a[d]) for d in s)) / n)
    out.sort()
    return out[int(.05 * B)], out[int(.95 * B)]


def boot_roi(picks):
    by = {}
    for r in picks:
        by.setdefault(r['date'], []).append(r)
    ds = sorted(by)
    random.seed(11)
    out = sorted(roi([r for d in random.choices(ds, k=len(ds)) for r in by[d]]) for _ in range(B))
    return out[int(.05 * B)], out[int(.95 * B)]


def main():
    rows = json.load(io.open(os.path.join(HERE, 'rows.json'), encoding='utf-8'))
    nights = sorted({r['date'] for r in rows})
    print(f'{len(rows)} bettable legs (confirmed starters, +100 or longer), {sum(r["y"] for r in rows)} scored, '
          f'{len(nights)} nights {nights[0]}..{nights[-1]}; walk-forward scores the last {len(nights) - WARM}')
    base_per, base_picks = walk(rows, [])
    nb = sum(len(v) for v in base_per.values())
    base_ll = sum(map(sum, base_per.values())) / nb
    print(f'\nprice-only held-out log loss {base_ll:.4f} on {nb} legs\n')
    print(f'{"feature":17s}{"coef":>8s}{"z":>7s}   {"log-loss gain":>14s}  {"90% band":>18s}')
    out = {}
    for name, keys in list(CANDS.items()) + [('ALL TOGETHER', ALL)]:
        full = fit(rows, keys, want_se=True)
        per, picks = walk(rows, keys)
        gain = (sum(map(sum, base_per.values())) - sum(map(sum, per.values()))) / nb
        lo, hi = boot_diff(per, base_per)
        c, s = full['w'][3], full['se'][3]
        tag = '' if name == 'ALL TOGETHER' else f'{c:+8.3f}{c / s:+7.2f}'
        print(f'{name:17s}{tag:15s}   {gain:+14.4f}  [{lo:+.4f}, {hi:+.4f}]')
        out[name] = dict(keys=keys, coef=dict(zip(['b0', 'bL', 'bL2'] + keys, [round(x, 4) for x in full['w']])),
                         z=dict(zip(keys, [round(a / b, 2) for a, b in zip(full['w'][3:], full['se'][3:])])),
                         wf_logloss_gain=round(gain, 5), band90=[round(lo, 5), round(hi, 5)])
        if name == 'ALL TOGETHER':
            all_picks = picks
            for k, a, b in zip(keys, full['w'][3:], full['se'][3:]):
                print(f'    {k:12s} coef {a:+.3f}  z {a / b:+.2f}')

    print(f'\nWALK-FORWARD TOP-{TOPN} PER NIGHT, flat 1u ({len(nights) - WARM} nights)')
    held = [r for r in rows if r['date'] >= nights[WARM]]
    by = {}
    for r in held:
        by.setdefault(r['date'], []).append(r)
    live = [r for d in sorted(by) for r in sorted(by[d], key=lambda r: -r['total'])[:TOPN]]
    price = [r for d in sorted(by) for r in sorted(by[d], key=lambda r: -implied(r['odds']))[:TOPN]]
    xg_only = walk(rows, ['z'])[1]
    res = {}
    for nm, pk in [('live TOTAL (today)', live), ('price only', price), ('price + xG (EV)', xg_only),
                   ('price-only EV', base_picks), ('all features EV', all_picks)]:
        lo, hi = boot_roi(pk)
        res[nm] = dict(bets=len(pk), goals=sum(r['y'] for r in pk), roi=round(roi(pk), 4), band90=[round(lo, 3), round(hi, 3)])
        print(f'  {nm:20s} {len(pk):4d} bets  {sum(r["y"] for r in pk):3d} scored ({sum(r["y"] for r in pk) / len(pk):.0%})'
              f'  ROI {roi(pk):+.1%}  90% [{lo:+.0%}, {hi:+.0%}]')
    json.dump(dict(rows=len(rows), nights=nights, warm=WARM, topn=TOPN, base_logloss=base_ll,
                   features=out, roi=res), io.open(os.path.join(HERE, 'results.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
