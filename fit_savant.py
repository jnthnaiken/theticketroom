#!/usr/bin/env python3
"""
fit_savant.py -- fit the 2015-2024 Statcast training table and report weights for _SIG.

Consumes savant_training_2015-04-01_2024-10-01.parquet (510,301 batter-games / 53,384 HR)
produced by build_savant_training.py via the "Savant Training Table" Action.

WHY THIS EXISTS: the table was built on 2026-08-02 and the fit that was supposed to consume
it left no committed trace, so build15.py has been scoring on _SIG weights that were never
fitted to it (0.45/0.35/0.20, "reasoned guesses" per README).

METHOD -- deliberately mirrors how build15.py actually scores, so the coefficients are
directly usable as _SIG weights:
  * Features are z-scored WITHIN game_date (per-slate), exactly like build15's per-slate
    standardization. Fitting on raw columns instead is the "raw-space" error already noted
    in backtest_season.py's SIG comment -- it makes rate features on different scales
    incomparable and mis-sizes the arsenal term.
  * Cross-validation is GROUPED BY game_date, so no slate is split across folds and a
    single hot night can't leak into its own validation score.
  * Reported weights are the positive-part-normalized coefficients, summing to 1.0 -- the
    same convention as _SIG.

PROXY MAPPING (stated plainly -- these are Statcast analogues, not the live inputs):
    _zxpow   expected power        <- b_brl    (batter barrel rate, trailing window)
    _zxwcon  expected contact qual <- b_xwobacon
    _zars    arsenal / opposing SP <- p_brl    (barrels ALLOWED by the opposing starter)
    _zhh     hard-hit rate         <- b_hh
    _zla     launch angle          <- b_la (raw) or the la_window bell -- section 5 picks
The live model's _zars is batter RV/100 x pitcher pitch mix and its _zxpow is park-neutral
xISO; neither exists in this table. The opposing-starter *allowed* profile is the closest
honest stand-in for "how favourable is the arm".

WHAT THIS CANNOT ANSWER: the table carries no historical odds, so every number here is
"predicts HR", never "beats the price". The market half of blend is untouched by this fit.

    pip install pandas numpy pyarrow scikit-learn
    python3 fit_savant.py savant_training_2015-04-01_2024-10-01.parquet
"""
import sys, glob, warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score

MIN_BIP = 20          # require a real trailing window on both sides
CORE = [('_zxpow', 'b_brl'), ('_zxwcon', 'b_xwobacon'), ('_zars', 'p_brl')]
BAT = ['b_brl', 'b_hh', 'b_fb', 'b_pull', 'b_sweet', 'b_la', 'b_xwobacon', 'b_swstr', 'b_csw']
PIT = ['p_brl', 'p_hh', 'p_fb', 'p_sweet', 'p_xwobacon', 'p_swstr', 'p_csw']


def hr(t):
    print('\n' + '=' * 78); print(t); print('=' * 78, flush=True)


def zbyslate(df, cols):
    """Z-score each feature WITHIN game_date -- build15 standardizes per slate, so the fit must too."""
    out = df[cols].copy()
    g = df.groupby('game_date')
    for c in cols:
        mu = g[c].transform('mean')
        sd = g[c].transform('std').replace(0, np.nan)
        out[c] = ((df[c] - mu) / sd).fillna(0.0)
    return out


def cv_auc(X, y, groups, n=5):
    """Grouped-by-date CV AUC. Returns (mean, sd, mean coefficients across folds)."""
    gk = GroupKFold(n_splits=n)
    aucs, coefs = [], []
    for tr, te in gk.split(X, y, groups):
        m = LogisticRegression(max_iter=2000, C=1.0)
        m.fit(X[tr], y[tr])
        aucs.append(roc_auc_score(y[te], m.predict_proba(X[te])[:, 1]))
        coefs.append(m.coef_[0])
    return float(np.mean(aucs)), float(np.std(aucs)), np.mean(coefs, axis=0)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else None
    if not src or glob.glob(src) == []:
        cand = sorted(glob.glob('**/savant_training*.parquet', recursive=True))
        if not cand:
            sys.exit('!! no savant_training*.parquet found')
        src = cand[0]
    else:
        src = sorted(glob.glob(src))[0]

    print(f'reading {src} ...', flush=True)
    df = pd.read_parquet(src)
    print(f'  {len(df):,} rows | {int(df.hr.sum()):,} HR ({100*df.hr.mean():.2f}%) '
          f'| {df.game_date.min().date()} .. {df.game_date.max().date()}')

    feats = sorted(set(BAT + PIT) & set(df.columns))
    need = ['b_n', 'p_n'] if 'p_n' in df.columns else ['b_n']
    d = df.dropna(subset=feats + need).copy()
    for c in need:
        d = d[d[c] >= MIN_BIP]
    d = d.sort_values('game_date').reset_index(drop=True)
    print(f'  usable after >={MIN_BIP} BIP on both sides and complete features: {len(d):,} rows '
          f'| {int(d.hr.sum()):,} HR ({100*d.hr.mean():.2f}%)')
    print(f'  slates: {d.game_date.nunique():,}   seasons: '
          f'{sorted(set(d.game_date.dt.year))}')

    y = d['hr'].astype(int).values
    groups = d['game_date'].values
    Z = zbyslate(d, feats)

    # ---------------- 1. the 3-signal core: the numbers that map onto _SIG ----------------
    hr('1. THREE-SIGNAL CORE  (the _SIG analogue)')
    core_cols = [c for _, c in CORE if c in Z.columns]
    auc, sd, coef = cv_auc(Z[core_cols].values, y, groups)
    print(f'  grouped-CV AUC {auc:.4f}  (+/- {sd:.4f} across 5 folds)')
    print('\n  fitted coefficients (per-slate z-space):')
    for (sig, col), b in zip(CORE, coef):
        print(f'    {sig:9s} <- {col:12s} {b:+.4f}')
    pos = np.clip(coef, 0, None)
    if pos.sum() > 0:
        w = pos / pos.sum()
        print('\n  >>> NORMALIZED WEIGHTS (positive part, sums to 1.0 -- _SIG convention):')
        print('  >>> _SIG = [' + ', '.join(f"('{s}', {v:.3f})" for (s, _), v in zip(CORE, w)) + ']')
        neg = [f'{s}' for (s, _), b in zip(CORE, coef) if b <= 0]
        if neg:
            print(f'  !!! non-positive coefficient(s): {", ".join(neg)} -- that signal did NOT '
                  f'predict HR on this data and its weight was clipped to 0.')
    print('\n  for reference, the three sets currently on record:')
    print('    build15.py (LIVE)   0.450 / 0.350 / 0.200')
    print('    README (7/31 refit) 0.130 / 0.500 / 0.370   [xISO, never applied to source]')
    print('    backtest_*.py       0.346 / 0.288 / 0.366')

    # ---------------- 2. does each signal earn its place ----------------
    hr('2. AUC LADDER  (does each term add anything)')
    ladder = [(['b_xwobacon'], 'contact quality alone'),
              (['b_brl'], 'power alone'),
              (['b_xwobacon', 'b_brl'], '+ power'),
              (core_cols, '+ opposing SP (the core)'),
              ([c for c in BAT if c in Z.columns], 'all batter features'),
              (feats, 'everything (batter + SP)')]
    prev = None
    for cols, label in ladder:
        cols = [c for c in cols if c in Z.columns]
        a, s, _ = cv_auc(Z[cols].values, y, groups)
        delta = f'  ({a-prev:+.4f})' if prev is not None and len(cols) > 1 else ''
        print(f'  {label:28s} n={len(cols):2d}  AUC {a:.4f} +/- {s:.4f}{delta}')
        prev = a
    print(f'\n  baseline (always predict the base rate) = 0.5000')

    # ---------------- 3. full model, so nothing is hidden ----------------
    hr('3. FULL MODEL COEFFICIENTS  (all features, per-slate z-space)')
    a, s, coef = cv_auc(Z[feats].values, y, groups)
    print(f'  grouped-CV AUC {a:.4f} +/- {s:.4f}\n')
    order = np.argsort(-np.abs(coef))
    for i in order:
        print(f'    {feats[i]:14s} {coef[i]:+.4f}')

    # ---------------- 5. what FORM should launch angle enter in ----------------
    # build15 already owns a bell curve for LA: la_window = exp(-((la-25)/14)^2), i.e. HR-optimal
    # around 25 degrees and falling off both sides. A raw linear b_la term instead says "higher is
    # always better", which is false at the extremes. Test both before wiring anything in.
    hr('5. LAUNCH-ANGLE FORM  (linear vs build15 la_window bell)')
    d['b_lawin'] = np.exp(-(((d['b_la'] - 25.0) / 14.0) ** 2))
    Z2 = zbyslate(d, feats + ['b_lawin'])
    lin = ['b_xwobacon', 'b_brl', 'b_hh', 'b_la']
    bel = ['b_xwobacon', 'b_brl', 'b_hh', 'b_lawin']
    a_lin, s_lin, _ = cv_auc(Z2[lin].values, y, groups)
    a_bel, s_bel, _ = cv_auc(Z2[bel].values, y, groups)
    print(f'  linear b_la     AUC {a_lin:.4f} +/- {s_lin:.4f}')
    print(f'  la_window bell  AUC {a_bel:.4f} +/- {s_bel:.4f}')
    LA_COL = 'b_la' if a_lin >= a_bel else 'b_lawin'
    print(f'  >>> USE: {LA_COL}   ({"linear" if LA_COL == "b_la" else "la_window bell, as build15 already computes"})')

    # ---------------- 6. the basket we would actually ship ----------------
    hr('6. FIVE-SIGNAL LIVE BASKET  (contact + power + arsenal + hh + la)')
    LIVE = [('_zxpow', 'b_brl'), ('_zxwcon', 'b_xwobacon'), ('_zars', 'p_brl'),
            ('_zhh', 'b_hh'), ('_zla', LA_COL)]
    lc = [c for _, c in LIVE]
    a5, s5, c5 = cv_auc(Z2[lc].values, y, groups)
    print(f'  grouped-CV AUC {a5:.4f} +/- {s5:.4f}\n')
    for (sig, col), b in zip(LIVE, c5):
        print(f'    {sig:8s} <- {col:12s} {b:+.4f}')
    p5 = np.clip(c5, 0, None)
    if p5.sum() > 0:
        w5 = p5 / p5.sum()
        print('\n  >>> _SIG = [' + ', '.join(f"('{s}', {v:.3f})" for (s, _), v in zip(LIVE, w5)) + ']')
    dropped = [s for (s, _), b in zip(LIVE, c5) if b <= 0]
    if dropped:
        print(f'  !!! clipped to zero (did not predict): {", ".join(dropped)}')

    # same basket without the arsenal term, since section 2 showed it adds ~nothing
    NOARS = [(s, c) for s, c in LIVE if s != '_zars']
    a4, s4, c4 = cv_auc(Z2[[c for _, c in NOARS]].values, y, groups)
    p4 = np.clip(c4, 0, None); w4 = p4 / p4.sum() if p4.sum() > 0 else p4
    print(f'\n  without _zars:  AUC {a4:.4f} +/- {s4:.4f}   (delta {a4-a5:+.4f})')
    print('  >>> _SIG = [' + ', '.join(f"('{s}', {v:.3f})" for (s, _), v in zip(NOARS, w4)) + ']')

    hr('4. CAVEATS -- read before touching _SIG')
    print('  * No odds in this table. These weights optimize "predicts HR", NOT "beats the')
    print('    price". build15 blends 0.5*market + 0.5*edge; this fit only informs the edge half.')
    print('  * b_brl / p_brl / b_xwobacon are Statcast ANALOGUES of _zxpow / _zars / _zxwcon,')
    print('    not the live inputs (park-neutral xISO, RV/100 x pitch mix, Kasper xwOBAcon).')
    print('    Treat the weights as the shape of the answer, not drop-in constants.')
    print('  * 2015-2024 rules/ball eras differ from 2026. A per-season fit would show drift.')
    print('  * Applying these to build15.py is a modelling decision, not a doc fix.')


if __name__ == '__main__':
    main()
