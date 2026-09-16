#!/usr/bin/env python3
"""soccer_ev_fit.py -- EVCAL-SOCCER-2026-09-16. Walk-forward EV calibration for the soccer board,
built the way baseball's is (ev_weights_v1.json, EVDRAFT-2026-09-10) and football's will be
(nfl/nfl_ev_fit.py, EVCAL-NFL-2026-09-11).

Owner: "can you do the same walk-forward learning for both that we did with baseball?"

    p = sigmoid(b0 + b_lim*L + b_lim2*L^2 + b_ez*z)
    L = logit(implied prob of the HELD price)     z = the board's edge_z, re-standardised within the night

Soccer has no model probability (football has khr = p_model); its model half is edge_z (xG side), so
that is the model term, exactly as baseball feeds z(kas_v1) rather than a probability.

ROWS. Every graded archive (soccer/boards/<date>.json and soccer/settled/<date>.json, date in
soccer_season.json graded_nights), one row per priced player who was a CONFIRMED STARTER, at +100
or longer. That is the only kind of player the board can bet: CONFLOCK freezes a slip on confirmed
legs and PLUSMONEY-2026-09-11 drafts nothing shorter than evens. Bench players are excluded -- an
anytime-scorer bet on a player who never comes on is a void at most books, and the archive cannot
tell a void from a loss for them.

CHECKS.
  * walk-forward: for each night after the first WARM, fit on EARLIER nights only, rank that night,
    flat 1u on the top-N. Compared with the live ranking (TOTAL) and the price alone.
  * leave-one-night-out, as nfl_ev_fit.py does.

⚠️ A CANDIDATE IS NOT LIVE. Writes soccer/ev_weights_soccer_v1.json with "proposed": null. Promotion
is the owner's call, then a separate change wires it into soccer_mock.py.

    python3 soccer_ev_fit.py [--topn 8] [--warm 6] [--out ev_weights_soccer_v1.json] [--nowrite]
"""
import glob, io, json, math, os, sys, random

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'nfl'))
from nfl_ev_fit import implied, dec, logit, sig, clip, _solve, roi   # one implementation of the maths

LAMBDA = 1.0
L_CLIP = (-4.0, 1.5)
Z_CLIP = (-3.0, 3.0)
MIN_ODDS = 100


def features(r):
    L = clip(logit(implied(r['odds'])), L_CLIP)
    return [1.0, L, L * L, clip(r['z'], Z_CLIP)]


def load_rows(here=HERE):
    season = json.load(io.open(os.path.join(here, 'soccer_season.json'), encoding='utf-8'))
    graded = set(season.get('graded_nights') or [])
    seen, rows = set(), []
    files = sorted(glob.glob(os.path.join(here, 'settled', '*.json'))) + sorted(glob.glob(os.path.join(here, 'boards', '*.json')))
    for f in files:
        D = json.load(io.open(f, encoding='utf-8'))
        date = (D.get('meta') or {}).get('date')
        if date not in graded or date in seen:
            continue
        seen.add(date)
        P = D.get('players') or {}
        P = P if isinstance(P, dict) else {p.get('nm'): p for p in P}
        night = []
        for n, p in P.items():
            o = p.get('odds')
            if o is None or p.get('out') or p.get('void') or p.get('status') != 'confirmed':
                continue
            if not isinstance(p.get('edge_z'), (int, float)):
                continue
            night.append(dict(date=date, name=n, odds=int(o), ez=float(p['edge_z']),
                              total=float(p.get('TOTAL') or 0), y=1 if p.get('hr') else 0))
        if len(night) < 2:
            continue
        m = sum(r['ez'] for r in night) / len(night)
        sd = (sum((r['ez'] - m) ** 2 for r in night) / len(night)) ** .5 or 1.0
        for r in night:
            r['z'] = (r['ez'] - m) / sd
        rows += [r for r in night if r['odds'] >= MIN_ODDS]
    return rows


def fit(rows, lam=LAMBDA, iters=50):
    X = [features(r) for r in rows]
    y = [r['y'] for r in rows]
    k = 4
    w = [logit(max(1e-3, min(1 - 1e-3, sum(y) / len(y)))), 0.0, 0.0, 0.0]
    for _ in range(iters):
        g = [0.0] * k
        H = [[0.0] * k for _ in range(k)]
        for xi, yi in zip(X, y):
            p = sig(sum(a * b for a, b in zip(w, xi)))
            for i in range(k):
                g[i] += (yi - p) * xi[i]
                for j in range(k):
                    H[i][j] += p * (1 - p) * xi[i] * xi[j]
        for i in range(1, k):
            g[i] -= lam * w[i]
            H[i][i] += lam
        step = _solve(H, g)
        w = [a + s for a, s in zip(w, step)]
        if max(abs(s) for s in step) < 1e-8:
            break
    return w


def p_cal(w, r):
    return sig(sum(a * b for a, b in zip(w, features(r))))


def rankings(w, te):
    return {
        'cal_ev': sorted(te, key=lambda r: -(p_cal(w, r) * dec(r['odds']) - 1)),
        'live_total': sorted(te, key=lambda r: -r['total']),
        'price': sorted(te, key=lambda r: -implied(r['odds'])),
    }


def boot(picks, n=2000, seed=11):
    by = {}
    for r in picks:
        by.setdefault(r['date'], []).append(r)
    ds = sorted(by)
    random.seed(seed)
    out = []
    for _ in range(n):
        s = [r for d in random.choices(ds, k=len(ds)) for r in by[d]]
        out.append(roi(s))
    out.sort()
    return out[int(.05 * n)], out[int(.95 * n)]


def walk_forward(rows, topn, warm):
    nights = sorted({r['date'] for r in rows})
    out = {'cal_ev': [], 'live_total': [], 'price': []}
    ll = {'cal': 0.0, 'base': 0.0, 'n': 0}
    for i, d in enumerate(nights):
        if i < warm:
            continue
        tr = [r for r in rows if r['date'] < d]
        te = [r for r in rows if r['date'] == d]
        w = fit(tr)
        base = sum(r['y'] for r in tr) / len(tr)
        for r in te:
            p = p_cal(w, r)
            ll['cal'] -= math.log(p if r['y'] else 1 - p)
            ll['base'] -= math.log(base if r['y'] else 1 - base)
            ll['n'] += 1
        for k, v in rankings(w, te).items():
            out[k].extend(v[:topn])
    res = {}
    for k, v in out.items():
        lo, hi = boot(v) if v else (None, None)
        res[k] = dict(bets=len(v), goals=sum(r['y'] for r in v), roi=roi(v), lo=lo, hi=hi)
    res['_logloss'] = dict(calibrated=ll['cal'] / ll['n'], base_rate=ll['base'] / ll['n'], rows=ll['n'],
                           nights=len(nights) - warm)
    return res


def lono(rows, topn):
    nights = sorted({r['date'] for r in rows})
    out = {'cal_ev': [], 'live_total': [], 'price': []}
    for d in nights:
        tr = [r for r in rows if r['date'] != d]
        te = [r for r in rows if r['date'] == d]
        for k, v in rankings(fit(tr), te).items():
            out[k].extend(v[:topn])
    return {k: dict(bets=len(v), roi=roi(v)) for k, v in out.items()}


def main(argv):
    opt = lambda k, dflt: argv[argv.index(k) + 1] if k in argv else dflt
    topn, warm = int(opt('--topn', 8)), int(opt('--warm', 6))
    outp = opt('--out', os.path.join(HERE, 'ev_weights_soccer_v1.json'))
    rows = load_rows()
    nights = sorted({r['date'] for r in rows})
    goals = sum(r['y'] for r in rows)
    print(f'soccer_ev_fit: {len(rows)} confirmed starters at +{MIN_ODDS} or longer, {goals} scored, '
          f'{len(nights)} graded nights ({nights[0]} .. {nights[-1]})')
    w = fit(rows)
    print('  full-sample fit  b0 %+.3f  b_lim %+.3f  b_lim2 %+.3f  b_ez %+.3f' % tuple(w))
    wf = walk_forward(rows, topn, warm)
    lg = wf.pop('_logloss')
    print(f'  WALK-FORWARD (fit on earlier nights only), {lg["nights"]} nights, top-{topn} per night, flat 1u:')
    for k, v in wf.items():
        print(f'    {k:11s} bets {v["bets"]:4d}  scored {v["goals"]:3d} ({v["goals"]/max(v["bets"],1):.1%})  '
              f'ROI {v["roi"]:+.1%}  90% [{v["lo"]:+.0%}, {v["hi"]:+.0%}]')
    print(f'    log loss on {lg["rows"]} held-out rows: calibrated {lg["calibrated"]:.4f} vs base rate {lg["base_rate"]:.4f}')
    lo = lono(rows, topn)
    for k, v in lo.items():
        print(f'    LONO {k:11s} bets {v["bets"]:4d}  ROI {v["roi"]:+.1%}')
    if '--nowrite' in argv:
        return 0
    doc = {
        'model': 'ev_soccer_v1', 'proposed': None,
        'inputs': ['logit_implied', 'logit_implied_sq', 'edge_z_night'],
        'coef': dict(zip(['b0', 'b_lim', 'b_lim2', 'b_ez'], [round(x, 6) for x in w])),
        'fit': {'rows': len(rows), 'goals': goals, 'nights': len(nights), 'first': nights[0], 'last': nights[-1],
                'filter': 'confirmed starters, odds >= +%d' % MIN_ODDS, 'lambda': LAMBDA,
                'l_clip': list(L_CLIP), 'z_clip': list(Z_CLIP),
                'walk_forward_top%d' % topn: wf, 'walk_forward_logloss': lg,
                'leave_one_night_out_top%d' % topn: lo},
    }
    json.dump(doc, io.open(outp, 'w', encoding='utf-8'), indent=1)
    print(f'  wrote CANDIDATE {os.path.basename(outp)} (proposed: null -- not live)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
