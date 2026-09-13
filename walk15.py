#!/usr/bin/env python3
"""
walk15.py — the SELF-LEARNING WALK over 2015-2024, one season at a time.

WHY THIS EXISTS
---------------
Owner, 2026-09-13: "run a self-learning program that backtest our model and system
over the past 15 years. learn as you go, season by season, making adjustments as you
go to perfect it based on what the program learns."

lab15.py measured the decade all at once. That is a photograph. This is the film: it
starts in 2015 knowing nothing, and for every season after it

    1. TRAINS on every season strictly before this one
    2. VALIDATES competing configurations on the most recent COMPLETED season
    3. COMMITS to one configuration -- and writes down what it changed and why
    4. TESTS it on the new season, which no part of step 1-3 has ever seen
    5. folds the result into what it knows and walks to the next season

Nothing at step 4 informs step 3 for the same season. That is the whole discipline: if
the learner is ever allowed to see the season it is being graded on, every number it
prints afterwards is fiction.

WHAT IT IS ALLOWED TO LEARN
---------------------------
  - the FEATURE SET          (batter only / + opposing starter / + prior-HR and rest)
  - the TRAINING WINDOW      (every past season, or only the last 3 or 5)
  - the DRAFT BAND           which p̂ range to take legs from -- the substantive one,
                             because the 81 priced nights say our edge lives in a band

WHAT IT IS FORBIDDEN TO LEARN
-----------------------------
The slip SHAPE. lab15 established that at 1,616 slates every shape's return is
statistically indistinguishable from zero -- the treble needs ~115,000 slates at
k=0.90. A learner allowed to pick a shape by measured return would be fitting noise
and would look brilliant doing it. Shape is reported under the exact k-ladder
(k, k^2-1, k^3-1) instead, and chosen by the owner on variance tolerance.

The rule: the learner may tune what is measurable and may not chase what is not.

THE OPPONENT
------------
Without prices there is no book to beat, so the learner is scored against the model we
actually ship -- the live 5-signal _SIG basket, frozen, refit-free, calibrated on the
same training data. Legs are priced at k_book/p̂_frozen. If the learner finds bats the
shipped model underrates, it earns; if not, it does not. That is a real, non-circular
objective: "how much does this season's model beat the one in production, at the
production model's own prices."

    python3 walk15.py "table/*.parquet"
    python3 walk15.py --selftest
"""
import sys, glob, math, json, argparse, warnings
warnings.filterwarnings('ignore')
import numpy as np
import pandas as pd

from lab15 import (prepare, load, slate_z, auc, la_window, LIVE5, BAT, PIT,
                   MIN_SLATE, poisson_binomial)

SEED = 17
EXTRAS = ['b_hr_rate_prior', 'b_hr_rate_30', 'b_games_prior', 'b_rest', 'b_month', 'b_new']

FEATSETS = {
    'bat9':            (BAT, []),
    'bat9+pit9':       (BAT + PIT, []),
    'bat9+extras':     (BAT, EXTRAS),
    'bat9+pit9+extras': (BAT + PIT, EXTRAS),
}
WINDOWS = {'expanding': None, 'last5': 5, 'last3': 3}
BANDS = {'all': (0.00, 1.00), 'short': (0.15, 1.00), 'mid': (0.09, 0.15),
         'long': (0.04, 0.09), 'wide-mid': (0.06, 0.15)}
LEGS = 3
RISK = 2.0


def hdr(t): print('\n' + '=' * 78); print(t); print('=' * 78, flush=True)
def sub(t): print('\n--- ' + t + ' ' + '-' * max(0, 72 - len(t)), flush=True)


# ---------------------------------------------------------------- primitives
_ZCACHE = {}


def _z(df, feats):
    """Per-slate z-scores depend only on the slate, never on the train/test split, so
    they are computed once per feature set instead of ~110 times over 316k rows."""
    k = tuple(feats)
    if k not in _ZCACHE: _ZCACHE[k] = slate_z(df, feats)
    return _ZCACHE[k]


def _extras(df, extras):
    """Standardise the extras ONCE, globally.

    WHY (run #1 of the walk ground for 20 minutes on a single season): the Statcast
    columns arrive per-slate z-scored, but b_games_prior runs 0..160 and b_month 4..10.
    Handing lbfgs a design matrix with that condition number makes it crawl for
    thousands of iterations. Scaling is computed from FEATURE VALUES ONLY -- it never
    touches `hr` -- so it carries no outcome information across the walk boundary.
    """
    if not extras: return None
    k = ('X',) + tuple(extras)
    if k not in _ZCACHE:
        V = df[extras].values.astype(float)
        mu = V.mean(axis=0); sd = V.std(axis=0); sd[sd == 0] = 1.0
        _ZCACHE[k] = (V - mu) / sd
    return _ZCACHE[k]


def fit_apply(df, tr, te, feats, extras):
    """Fit logistic on tr, return calibrated probabilities for te.

    Calibration is fitted INSIDE tr on a held-out slice, never on te. lab15 run #1 is
    the cautionary tale: uncalibrated p̂ made a mis-calibrated scorer look like
    correlated legs and silently shifted the whole k axis.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.isotonic import IsotonicRegression
    Z = _z(df, feats)
    E = _extras(df, extras)
    X = np.hstack([Z.values, E]) if extras else Z.values
    y = df['hr'].values.astype(int)

    # inner split of the training data, by slate, for the calibrator
    d = df.loc[tr, 'game_date']
    u = np.array(sorted(pd.unique(d))); rs = np.random.RandomState(SEED); rs.shuffle(u)
    cut = set(u[:max(1, len(u) // 5)])
    cal = d.isin(cut).values
    tr_idx = np.where(tr)[0]
    core = tr_idx[~cal]; hold = tr_idx[cal]
    if len(hold) < 500 or len(core) < 500:
        core, hold = tr_idx, tr_idx

    m = LogisticRegression(max_iter=400)
    m.fit(X[core], y[core])
    ir = IsotonicRegression(out_of_bounds='clip', y_min=1e-4, y_max=1 - 1e-4)
    ir.fit(m.predict_proba(X[hold])[:, 1], y[hold])

    m2 = LogisticRegression(max_iter=400); m2.fit(X[tr_idx], y[tr_idx])
    p_te = ir.predict(m2.predict_proba(X[np.where(te)[0]])[:, 1])
    return p_te, m2.coef_[0], (list(Z.columns) + extras)


def frozen_apply(df, tr, te):
    """The SHIPPED _SIG basket, fixed weights, only calibrated. The control, and the book."""
    from sklearn.isotonic import IsotonicRegression
    if 'FROZEN' not in _ZCACHE:
        d2 = df.copy(); d2['b_la'] = la_window(d2['b_la'])
        Z = slate_z(d2, [c for c, _ in LIVE5])
        _ZCACHE['FROZEN'] = sum(w * Z['z_' + c] for c, w in LIVE5).values
    raw = _ZCACHE['FROZEN']
    y = df['hr'].values.astype(int)
    ir = IsotonicRegression(out_of_bounds='clip', y_min=1e-4, y_max=1 - 1e-4)
    ir.fit(raw[np.where(tr)[0]], y[np.where(tr)[0]])
    return ir.predict(raw[np.where(te)[0]])


def draft(sub_df, p, pf, y, band, legs=LEGS):
    """Top `legs` by the learner's score, one per game, inside the p̂ band.

    Band membership is judged on the FROZEN probability, because in the real world the
    band is a price band -- the book's number, not ours.
    """
    P, PF, H = [], [], []
    for d, g in sub_df.groupby('game_date', sort=False):
        i = g.index.values
        if len(i) < MIN_SLATE: continue
        pp, ff, hh = p[i], pf[i], y[i]
        gk = sub_df.loc[i, 'game_pk'].values
        ok = np.where((ff >= band[0]) & (ff < band[1]))[0]
        if len(ok) < legs: continue
        ok = ok[np.argsort(-pp[ok])]
        pick, used = [], set()
        for j in ok:
            if gk[j] in used: continue
            used.add(gk[j]); pick.append(j)
            if len(pick) == legs: break
        if len(pick) < legs: continue
        pick = np.array(pick)
        P.append(pp[pick]); PF.append(ff[pick]); H.append(hh[pick])
    return np.array(P), np.array(PF), np.array(H)


def edge_of(PF, H):
    """Ratio-of-sums: observed hits over what the FROZEN book expected. >1 = we beat it.

    Ratio-of-sums, not mean-of-ratios: a +2400 leg contributes 1/0.04 = 25 to a mean of
    ratios and detonates the estimate. This is the stable form, which matters because
    the learner SELECTS on it.
    """
    if len(PF) == 0: return float('nan'), 0
    return float(H.sum() / PF.sum()), int(H.size)


def shape_returns(PF, H, k):
    """Exact returns at book margin k, priced off the FROZEN model. unit = risk/ncombo."""
    if len(PF) == 0: return {}
    dec = k / np.clip(PF, 1e-6, 1)
    combos = {'singles': [(0,), (1,), (2,)], 'doubles': [(0, 1), (0, 2), (1, 2)],
              'by2s&3': [(0, 1), (0, 2), (1, 2), (0, 1, 2)], 'treble': [(0, 1, 2)]}
    out = {}
    for lab, cs in combos.items():
        unit = RISK / len(cs); net = np.zeros(len(PF))
        for c in cs:
            won = H[:, list(c)].all(axis=1); pay = dec[:, list(c)].prod(axis=1)
            net += np.where(won, unit * (pay - 1.0), -unit)
        se = net.std() / math.sqrt(len(net)) / RISK * 100
        out[lab] = (net.mean() / RISK * 100, se, float(net.sum()))
    return out


# ---------------------------------------------------------------- the walk
def run_walk(df, k_book, quiet=False):
    y = df['hr'].values.astype(int)
    seasons = sorted(df['season'].unique())
    season = df['season'].values
    rows, journal, prev = [], [], None

    hdr('THE WALK — each season decided using only the seasons before it')
    print(f'  seasons {seasons[0]}..{seasons[-1]}   book margin k_book = {k_book:.2f}')
    print('  2015 is pure burn-in (nothing to train on). 2016 is the first validation')
    print('  season, so the first graded test season is 2017.\n')
    print(f'  {"season":<8}{"train":<12}{"chosen":<34}{"valAUC":>8}{"testAUC":>9}'
          f'{"legs hit":>10}{"EDGE":>8}')

    for s in seasons:
        if s <= seasons[1]: continue                      # need >=1 train + 1 val season
        past = [x for x in seasons if x < s]
        val_s = past[-1]
        inner = [x for x in past if x < val_s]
        if not inner: continue

        # ---- step 2: choose a configuration on the most recent COMPLETED season ----
        best, best_auc = None, -1
        for fname, (feats, extras) in FEATSETS.items():
            for wname, w in WINDOWS.items():
                use = inner if w is None else inner[-w:]
                tr = np.isin(season, use); va = season == val_s
                if tr.sum() < 5000: continue
                pv, _, _ = fit_apply(df, tr, va, feats, extras)
                a = auc(y[va], pv)
                if a > best_auc: best_auc, best = a, (fname, wname, feats, extras, w)
        if best is None: continue
        fname, wname, feats, extras, w = best

        # ---- the band is chosen on the validation season too, never on the test ----
        trv = np.isin(season, inner if w is None else inner[-w:])
        vam = season == val_s
        pv, _, _ = fit_apply(df, trv, vam, feats, extras)
        fv = frozen_apply(df, trv, vam)
        dv = df[vam].reset_index(drop=True)
        pv_, fv_, yv_ = pv, fv, y[vam]
        best_band, best_edge = 'all', -9
        for bname, b in BANDS.items():
            _, PF, H = draft(dv, pv_, fv_, yv_, b)
            e, n = edge_of(PF, H)
            if n >= 300 and not math.isnan(e) and e > best_edge:
                best_edge, best_band = e, bname

        # ---- step 3/4: refit on ALL of train, test on the unseen season ----
        use = past if w is None else past[-w:]
        tr = np.isin(season, use); te = season == s
        pt, coef, names = fit_apply(df, tr, te, feats, extras)
        ft = frozen_apply(df, tr, te)
        dt = df[te].reset_index(drop=True)
        yt = y[te]
        P, PF, H = draft(dt, pt, ft, yt, BANDS[best_band])
        edge, nlegs = edge_of(PF, H)
        # the frozen model drafting for itself, same band -- the control
        Pf, PFf, Hf = draft(dt, ft, ft, yt, BANDS[best_band])
        edge_f, _ = edge_of(PFf, Hf)
        ta = auc(yt, pt); ta_f = auc(yt, ft)

        cfg = f'{fname}/{wname}/band={best_band}'
        print(f'  {s:<8}{str(use[0])+"-"+str(use[-1]):<12}{cfg:<34}{best_auc:>8.4f}'
              f'{ta:>9.4f}{(H.mean()*100 if H.size else float("nan")):>9.1f}%{edge:>8.3f}')

        ch = []
        if prev:
            if prev['feats'] != fname: ch.append(f'features {prev["feats"]} -> {fname}')
            if prev['win'] != wname: ch.append(f'window {prev["win"]} -> {wname}')
            if prev['band'] != best_band: ch.append(f'band {prev["band"]} -> {best_band}')
        journal.append({'season': int(s), 'cfg': cfg, 'changes': ch, 'valAUC': best_auc,
                        'testAUC': ta, 'testAUC_frozen': ta_f, 'edge': edge,
                        'edge_frozen': edge_f, 'nlegs': nlegs, 'slates': len(P),
                        'band': best_band, 'feats': fname, 'win': wname,
                        'shapes': shape_returns(PF, H, k_book),
                        'shapes_frozen': shape_returns(PFf, Hf, k_book),
                        'top': sorted(zip(names, coef), key=lambda t: -abs(t[1]))[:6]})
        prev = journal[-1]
        rows.append((s, PF, H))
    return journal, rows


def report(journal, rows, k_book):
    sub('the learning journal — what it changed, and when')
    for j in journal:
        print(f'\n  {j["season"]}  {j["cfg"]}')
        if j['changes']:
            for c in j['changes']: print(f'      ADJUSTED: {c}')
        else:
            print('      (no change — last season\'s configuration validated best again)')
        print(f'      test AUC {j["testAUC"]:.4f} vs frozen {j["testAUC_frozen"]:.4f} '
              f'({j["testAUC"]-j["testAUC_frozen"]:+.4f})   '
              f'edge {j["edge"]:.3f} vs frozen-drafting-itself {j["edge_frozen"]:.3f}')
        print('      heaviest terms: ' + ', '.join(f'{n}{c:+.3f}' for n, c in j['top'][:4]))

    sub('did it actually improve? learner vs the shipped model, season by season')
    print(f'  {"season":<8}{"AUC learner":>12}{"AUC frozen":>12}{"delta":>9}'
          f'{"EDGE learner":>14}{"EDGE frozen":>13}')
    for j in journal:
        print(f'  {j["season"]:<8}{j["testAUC"]:>12.4f}{j["testAUC_frozen"]:>12.4f}'
              f'{j["testAUC"]-j["testAUC_frozen"]:>+9.4f}{j["edge"]:>14.3f}{j["edge_frozen"]:>13.3f}')
    da = [j['testAUC'] - j['testAUC_frozen'] for j in journal]
    print(f'\n  mean AUC gain over the shipped basket: {np.mean(da):+.4f} '
          f'(+/-{np.std(da)/math.sqrt(len(da)):.4f} SE over {len(da)} seasons)')

    # pooled edge across the whole walk
    PF = np.vstack([r[1] for r in rows]); H = np.vstack([r[2] for r in rows])
    e, n = edge_of(PF, H)
    se = math.sqrt(H.mean() * (1 - H.mean()) / n) / PF.mean()
    print(f'  pooled EDGE over the whole walk: {e:.3f} +/- {se:.3f} on {n:,} legs')
    print(f'  -> at a book margin of k_book={k_book:.2f}, realised k = {e*k_book:.3f} '
          f'+/- {se*k_book:.3f}')
    print('     EDGE is observed hits over what the SHIPPED model expected. 1.000 means')
    print('     the learner found nothing the production model was missing.')

    sub(f'what the shapes would have returned, priced off the shipped model at k={k_book:.2f}')
    print('  READ THE ERROR BAR. lab15: no shape is distinguishable from zero even at')
    print('  1,616 slates. This is reported, not optimised — the learner never sees it.')
    print(f'  {"shape":<10}{"ROI":>10}{"SE":>9}{"t":>7}   verdict')
    for lab in ['singles', 'doubles', 'by2s&3', 'treble']:
        tot = shape_returns(PF, H, k_book).get(lab)
        if not tot: continue
        roi, se2, net = tot
        t = roi / se2 if se2 else 0
        print(f'  {lab:<10}{roi:>9.1f}%{se2:>8.1f}%{t:>7.2f}   '
              f'{"real" if abs(t) > 2 else "not distinguishable from zero"}')
    print('\n  The exact ladder at the realised k is the honest estimate:')
    kk = e * k_book
    print(f'    single {kk-1:+.1%}   double {kk**2-1:+.1%}   treble {kk**3-1:+.1%}')
    print('  At k<1 fewer legs is better; at k>1 more legs is better. That is algebra,')
    print('  not a backtest, and it is the only part of the shape question with a signal.')


def final_fit(df, journal):
    hdr('THE LEARNED CONFIGURATION — what to actually ship')
    last = journal[-1]
    print(f'  The walk converged on: {last["cfg"]}')
    tally = {}
    for j in journal: tally[j['cfg']] = tally.get(j['cfg'], 0) + 1
    print('  seasons each configuration held:')
    for c, n in sorted(tally.items(), key=lambda t: -t[1]): print(f'    {n:>2}x  {c}')
    feats, extras = FEATSETS[last['feats']]
    y = df['hr'].values.astype(int)
    allm = np.ones(len(df), dtype=bool)
    _, coef, names = fit_apply(df, allm, allm, feats, extras)
    print(f'\n  refit on all {len(df):,} rows, ordered by |coef| in per-slate z space:')
    for nm, c in sorted(zip(names, coef), key=lambda t: -abs(t[1]))[:16]:
        print(f'    {nm:<22}{c:>+9.4f}')
    z = [(n, c) for n, c in zip(names, coef) if n.startswith('z_')]
    tot = sum(abs(c) for _, c in z) or 1.0
    print('\n  the z-space terms renormalised to a _SIG-style basket summing to 1:')
    for nm, c in sorted(z, key=lambda t: -abs(t[1]))[:8]:
        print(f'    {nm[2:]:<16}{abs(c)/tot:>7.3f}   {"(+)" if c > 0 else "(-) INVERTED"}')
    json.dump({'cfg': last['cfg'], 'coef': dict(zip(names, map(float, coef)))},
              open('walk15_final.json', 'w'), indent=1)
    print('\n  wrote walk15_final.json')


# ---------------------------------------------------------------- selftest
def selftest():
    hdr('SELF-TEST — a planted regime change the learner must actually find')
    rs = np.random.RandomState(5)
    rows = []
    for s in range(2015, 2023):
        for d in range(60):
            date = pd.Timestamp(f'{s}-04-01') + pd.Timedelta(days=d)
            for b in range(80):
                sk = rs.normal(0, 1); nz = rs.normal(0, 1)
                # THE PLANT: before 2019 the signal is b_hh; from 2019 it moves to b_la.
                lp = -2.2 + (0.55 * sk if s < 2019 else 0.55 * nz)
                pr = 1 / (1 + math.exp(-lp))
                rows.append(dict(batter_id=b, game_date=date, game_pk=s * 10000 + d * 100 + b // 5,
                                 hr=int(rs.rand() < pr), b_hh=sk, b_la=25 + 6 * nz,
                                 b_brl=rs.normal(), b_xwobacon=rs.normal(), b_fb=rs.normal(),
                                 b_pull=rs.normal(), b_sweet=rs.normal(), b_swstr=rs.normal(),
                                 b_csw=rs.normal(), p_hh=rs.normal(), p_brl=rs.normal(),
                                 p_fb=rs.normal(), p_pull=rs.normal(), p_sweet=rs.normal(),
                                 p_la=rs.normal(), p_xwobacon=rs.normal(), p_swstr=rs.normal(),
                                 p_csw=rs.normal(), b_n=50, p_n=50))
    df = prepare(pd.DataFrame(rows))
    print('\nPLANT: the true driver is b_hh through 2018 and b_la from 2019 on.')
    print('A learner that is really learning must re-weight toward b_la after 2019,')
    print('and its test AUC must stay up while the FROZEN basket (which leans on')
    print('b_hh at 0.432 and cannot adapt) falls away after the switch.\n')
    j, rows2 = run_walk(df, 0.90)
    pre = [x for x in j if x['season'] < 2019]
    post = [x for x in j if x['season'] >= 2020]
    if not pre or not post:
        print('!! not enough seasons on either side of the plant'); return 1
    gp = np.mean([x['testAUC'] - x['testAUC_frozen'] for x in pre])
    gq = np.mean([x['testAUC'] - x['testAUC_frozen'] for x in post])
    print(f'\n  mean AUC advantage over frozen BEFORE the switch: {gp:+.4f}')
    print(f'  mean AUC advantage over frozen AFTER  the switch: {gq:+.4f}')
    ok = gq > gp + 0.02
    print(f'\n  SELF-TEST {"PASS" if ok else "FAIL"}: the learner {"adapted to" if ok else "MISSED"}'
          f' the regime change while the frozen basket could not')
    la = [c for n, c in post[-1]['top'] if n == 'z_b_la']
    print(f'  final season leans on z_b_la: {la[0]:+.3f}' if la else
          '  (z_b_la not in the final top terms)')
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('table', nargs='?')
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--k-book', type=float, default=0.90,
                    help='book margin on a leg; 0.89 is what the 81 priced nights measured')
    a = ap.parse_args()
    if a.selftest: sys.exit(selftest())
    if not a.table: sys.exit('!! give a parquet glob, or --selftest')
    df = prepare(load(a.table))
    j, rows = run_walk(df, a.k_book)
    report(j, rows, a.k_book)
    final_fit(df, j)
    json.dump([{k: v for k, v in x.items() if k != 'top'} for x in j],
              open('walk15_journal.json', 'w'), indent=1, default=float)
    hdr('WHAT THIS STILL DOES NOT SETTLE')
    print('  The opponent is our own shipped model, not a sportsbook. EDGE>1 means the')
    print('  learner beats production at production\'s prices -- necessary for the board')
    print('  to improve, nowhere near sufficient for it to win. A real book prices with')
    print('  information we do not have in this table (lineups, weather, late money) and')
    print('  charges vig on top. The 81 priced nights remain the only evidence on that,')
    print('  and they say k<1 in every band we can measure.')
    print('\n  wrote walk15_journal.json')


if __name__ == '__main__':
    main()
