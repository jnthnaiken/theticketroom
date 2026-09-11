#!/usr/bin/env python3
"""nfl_ev_fit.py -- EVCAL-NFL-2026-09-11. Calibrate football EV the way baseball's is, once the data exists.

Owner: "can you calibrate football's ev too?"

WHAT BASEBALL DOES (ev_weights_v1.json, EVDRAFT-2026-09-10). EV is not model_p x price. It is
    p = sigmoid(b0 + b_lim*L + b_lim2*L^2 + b_kz*z)          L = logit(implied prob of the HELD price)
fit on graded outcomes: 17,577 bats over 78 nights, every one with the price the board actually held.
Because the PRICE is an input, the fit learns how far to trust the model against the market at each
end of the price range -- the concave L^2 term is what stops a +2000 man from topping the board on a
model/market disagreement the model has no business winning.

WHY FOOTBALL CANNOT DO THAT TODAY. The fit needs graded rows WITH a held price. nflverse has
outcomes back to 1999 and no prop prices at all (nfl-backtest-2026-08-24.md); the only priced,
graded football rows that exist are the ones this board has archived itself:
    2026-09-09 + 2026-09-10  ->  47 priced rows, 6 touchdowns.
A three-coefficient logistic on 6 events is noise. So this script is the calibration AND its gate:

  * it reads every GRADED archive (nfl/boards/<date>.json whose date is in nfl_season.json
    graded_nights -- settle writes `hr` onto those boards), one row per priced, non-scratched player:
    held odds, the model's own probability (`khr` = p_model x 100) and whether he scored;
  * below MIN_ROWS / MIN_NIGHTS it reports what it has and writes NOTHING;
  * above them it fits, runs a leave-one-night-out check (calibrated EV vs raw-model EV vs the
    price, top-N flat 1u), and writes nfl/ev_weights_nfl_v1.json with "proposed": null.

⚠️ A CANDIDATE IS NOT LIVE. nfl_mock.py only uses a weights file whose "proposed" is a date --
the same convention as kas_weights_v*.json. Promotion is the owner's call on the leave-one-night-out
numbers, never automatic.

Pure python on purpose: tests.yml installs no numpy.
    python3 nfl_ev_fit.py [--boards boards] [--season nfl_season.json] [--out ev_weights_nfl_v1.json]
"""
import glob, io, json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MIN_ROWS = 1500        # ~230 priced graded rows a week (13-game Sunday + prime-time) -> about week 7
MIN_NIGHTS = 6
LAMBDA = 1.0           # ridge on the non-intercept terms
L_CLIP = (-4.0, 1.5)   # logit(implied): +5400 .. about -450
M_CLIP = (-6.0, 1.5)
TOPN = 8


def implied(a):
    a = float(a)
    return 100.0 / (a + 100.0) if a > 0 else -a / (-a + 100.0)


def dec(a):
    a = float(a)
    return 1 + a / 100.0 if a > 0 else 1 + 100.0 / (-a)


def logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def sig(x):
    return 1 / (1 + math.exp(-x)) if x > -30 else 0.0


def clip(x, lo_hi):
    return min(max(x, lo_hi[0]), lo_hi[1])


def features(odds, p_model):
    L = clip(logit(implied(odds)), L_CLIP)
    M = clip(logit(p_model), M_CLIP)
    return [1.0, L, L * L, M]


def load_rows(boards_dir, season_path):
    season = json.load(io.open(season_path, encoding='utf-8')) if os.path.exists(season_path) else {}
    graded = set(season.get('graded_nights') or [])
    rows = []
    for b in sorted(glob.glob(os.path.join(boards_dir, '*.json'))):
        D = json.load(io.open(b, encoding='utf-8'))
        date = (D.get('meta') or {}).get('date')
        if date not in graded:
            continue
        for n, p in (D.get('players') or {}).items():
            if p.get('odds') is None or p.get('khr') is None or p.get('out') or p.get('void'):
                continue
            pm = float(p['khr']) / 100.0
            if not (0 < pm < 1):
                continue
            rows.append(dict(date=date, name=n, odds=int(p['odds']), p_model=pm, y=1 if p.get('hr') else 0))
    return rows


def _solve(A, b):
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[piv] = M[piv], M[c]
        if abs(M[c][c]) < 1e-12:
            raise ValueError('singular')
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                for k in range(c, n + 1):
                    M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] for i in range(n)]


def fit(rows, lam=LAMBDA, iters=50):
    """Ridge logistic by Newton-Raphson. Returns [b0, b_lim, b_lim2, b_m]."""
    X = [features(r['odds'], r['p_model']) for r in rows]
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


def p_cal(w, odds, p_model):
    return sig(sum(a * b for a, b in zip(w, features(odds, p_model))))


def roi(picks):
    if not picks:
        return None
    return sum((dec(r['odds']) - 1) if r['y'] else -1.0 for r in picks) / len(picks)


def lono(rows, topn=TOPN):
    """Leave-one-night-out: fit on the other nights, pick the top-N of the held-out night by
    calibrated EV / raw-model EV / shortest price, flat 1u each."""
    nights = sorted({r['date'] for r in rows})
    out = {'cal_ev': [], 'raw_ev': [], 'price': []}
    for d in nights:
        tr = [r for r in rows if r['date'] != d]
        te = [r for r in rows if r['date'] == d]
        if not tr or not te or not any(r['y'] for r in tr):
            continue
        w = fit(tr)
        by = {
            'cal_ev': sorted(te, key=lambda r: -(p_cal(w, r['odds'], r['p_model']) * dec(r['odds']) - 1)),
            'raw_ev': sorted(te, key=lambda r: -(r['p_model'] * dec(r['odds']) - 1)),
            'price': sorted(te, key=lambda r: -implied(r['odds'])),
        }
        for k, v in by.items():
            out[k].extend(v[:topn])
    return {k: dict(bets=len(v), roi=roi(v)) for k, v in out.items()}


def main(argv):
    opt = lambda k, dflt: argv[argv.index(k) + 1] if k in argv else dflt
    boards = opt('--boards', os.path.join(HERE, 'boards'))
    season = opt('--season', os.path.join(HERE, 'nfl_season.json'))
    outp = opt('--out', os.path.join(HERE, 'ev_weights_nfl_v1.json'))
    rows = load_rows(boards, season)
    nights = sorted({r['date'] for r in rows})
    tds = sum(r['y'] for r in rows)
    print(f'nfl_ev_fit: {len(rows)} priced graded rows, {tds} TDs, {len(nights)} night(s) {nights}')
    if len(rows) < MIN_ROWS or len(nights) < MIN_NIGHTS:
        print(f'  NOT ENOUGH TO CALIBRATE: need {MIN_ROWS} rows over {MIN_NIGHTS} nights. '
              f'Nothing written; the board keeps raw-model EV.')
        return 0
    w = fit(rows)
    check = lono(rows)
    doc = {
        'model': 'ev_nfl_v1', 'proposed': None,
        'inputs': ['logit_implied', 'logit_implied_sq', 'logit_p_model'],
        'coef': dict(zip(['b0', 'b_lim', 'b_lim2', 'b_m'], [round(x, 6) for x in w])),
        'fit': {'rows': len(rows), 'tds': tds, 'nights': len(nights), 'first': nights[0], 'last': nights[-1],
                'lambda': LAMBDA, 'l_clip': list(L_CLIP), 'm_clip': list(M_CLIP),
                'leave_one_night_out_top%d_flat' % TOPN: check},
    }
    json.dump(doc, io.open(outp, 'w', encoding='utf-8'), indent=1)
    print(f'  wrote CANDIDATE {os.path.basename(outp)} (proposed: null -- not live): {doc["coef"]}')
    for k, v in check.items():
        print(f'    LONO top-{TOPN}  {k:7s} bets {v["bets"]:4d}  ROI {v["roi"]:+.1%}' if v['roi'] is not None else f'    {k}: no bets')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
