#!/usr/bin/env python3
"""
fit_bvp.py -- does a batter's history against THIS starter predict a home run?

THE QUESTION, IN THE OWNER'S WORDS (2026-09-12): "austin riley yesterday had a history of
8 hr's vs nola, hit his 9th. and that was never accounted for and seems like a huge tell."

It is not accounted for. The board has never carried a batter-vs-pitcher term. Before one is
added, it gets measured the same way every other signal in _SIG was measured -- on the
2015-2024 Statcast table, leak-free, in the per-slate z-space build15 actually scores in.

WHY THIS SCRIPT IS PARANOID ABOUT SAMPLE
    The same week this was asked, Josue De Paula anchored three tickets off a Kasper card
    with ONE batted ball on it (pb 100.0 / hh 100.0 -> powraw 10,000 vs a field median of
    191). That is the identical failure mode pointed the other way: a rate with nothing
    under it. An unregressed BvP term is WORSE, because the denominators are smaller -- a
    man who is 2-for-3 with a homer off tonight's starter would read 0.333 HR/meeting and
    rocket up a board built on raw rates. So every form tested here is regressed toward the
    batter's OWN baseline, and the raw form is tested too, on purpose, to show what it does.

WHAT IS MEASURED (all expanding and as-of-date -- a row never sees its own outcome or any
later meeting, so nothing here is hindsight):
    m        prior meetings between this batter and this starter
    h        prior HR by this batter in those meetings
    b_rate   the batter's own prior HR/game, itself shrunk to the league rate so a September
             call-up's first week does not read 1.000 or 0.000
    lift_K   (h + K*b_rate)/(m + K) - b_rate      <- the tested signal, for a grid of K
             K is the meeting count at which the matchup is believed half as much as the
             batter's own baseline. K=0 is the raw unregressed rate difference.

    The subtraction matters and is the whole point: the question is never "does he homer a
    lot", the model already knows that. It is "does he homer MORE off THIS arm than off
    everyone else". Riley's 8 off Nola only counts as a tell to the extent it is above the
    rate at which Riley homers generally.

REPORTED
    1. standalone grouped-CV AUC of each lift_K, and of the raw counts h and m, so a K that
       only works because it is smuggling in "this is a veteran with many meetings" shows up
    2. incremental AUC over the 5-signal proxy baseline that produced the live _SIG weights
    3. the implied _SIG weight if it were added
    4. the same thing restricted to rows with m >= floor, for a range of floors -- the
       operational question is not "does BvP predict" but "above how many meetings", and how
       often a slate even contains such a matchup
    5. a Riley check: the highest-lift rows in the table and whether they actually homered

WHAT THIS CANNOT ANSWER
    The table carries no odds, so every number is "predicts HR", never "beats the price".
    A term can be real and still be fully in the market -- BvP is the single most quoted
    stat on a broadcast, so if anything is already priced, it is this one. Treat a positive
    result here as permission to test against price, not as an edge.

    pip install pandas numpy pyarrow scikit-learn
    python3 fit_bvp.py "table/*.parquet"
"""
import sys, glob, warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score

BASE = ['b_brl', 'b_hh', 'b_la', 'b_xwobacon', 'p_brl']   # the 5-signal proxy basket fit_savant.py used
MIN_BIP = 20            # same trailing-window requirement as fit_savant.py, so the baseline is comparable
K_BAT = 60              # games of shrinkage on the batter's OWN baseline (his rate is also an estimate)
K_GRID = [0, 5, 10, 15, 25, 40, 60, 100, 200]
FLOORS = [0, 1, 3, 5, 10, 15, 20, 30]


def hr_(t):
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
    gk = GroupKFold(n_splits=n)
    aucs, coefs = [], []
    for tr, te in gk.split(X, y, groups):
        m = LogisticRegression(max_iter=2000, C=1.0)
        m.fit(X[tr], y[tr])
        aucs.append(roc_auc_score(y[te], m.predict_proba(X[te])[:, 1]))
        coefs.append(m.coef_[0])
    return float(np.mean(aucs)), float(np.std(aucs)), np.mean(coefs, axis=0)


def build_bvp(d, league):
    """Expanding, leak-free BvP history. Every column here is strictly PRIOR to the row's own game."""
    d = d.sort_values(['game_date', 'game_pk']).reset_index(drop=True)

    # --- prior meetings and prior HR vs THIS starter -------------------------------------
    pair = d.groupby(['batter_id', 'sp_id'])
    d['m'] = pair.cumcount()                                  # games before this one
    d['h'] = pair['hr'].cumsum() - d['hr']                    # HR before this one (own outcome removed)

    # --- the batter's OWN prior rate, shrunk to league so early careers are not 0.000/1.000
    bat = d.groupby('batter_id')
    n_b = bat.cumcount()
    h_b = bat['hr'].cumsum() - d['hr']
    d['b_rate'] = (h_b + K_BAT * league) / (n_b + K_BAT)

    for K in K_GRID:
        d['lift_%d' % K] = ((d['h'] + K * d['b_rate']) / (d['m'] + K).replace(0, np.nan)
                            - d['b_rate']).fillna(0.0)
    return d


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else None
    cand = sorted(glob.glob(src)) if src else sorted(glob.glob('**/savant_training*.parquet', recursive=True))
    if not cand:
        sys.exit('!! no savant_training*.parquet found')
    src = cand[0]

    print(f'reading {src} ...', flush=True)
    df = pd.read_parquet(src)
    need = ['batter_id', 'sp_id', 'game_date', 'game_pk', 'hr']
    miss = [c for c in need if c not in df.columns]
    if miss:
        sys.exit(f'!! table is missing {miss} -- cannot build BvP history from it')
    df = df.dropna(subset=['batter_id', 'sp_id']).copy()
    df['game_date'] = pd.to_datetime(df['game_date'])
    league = float(df['hr'].mean())
    print(f'  {len(df):,} batter-games | {int(df.hr.sum()):,} HR ({100*league:.2f}%) '
          f'| {df.game_date.min().date()} .. {df.game_date.max().date()}')

    hr_('1. BUILDING LEAK-FREE BvP HISTORY')
    d = build_bvp(df, league)
    print(f'  distinct batter-starter pairs: {d.groupby(["batter_id","sp_id"]).ngroups:,}')
    for f in FLOORS:
        g = d[d.m >= f]
        print('  rows with m >= %-3d : %8d (%5.1f%% of table) | HR %5.2f%%'
              % (f, len(g), 100*len(g)/len(d), 100*g.hr.mean() if len(g) else 0))
    print('\n  THE SHAPE OF THE PROBLEM: the deep-history matchups the question is about are rare.')
    print('  Whatever the signal is worth, it can only be worth it on that slice of a slate.')

    hr_('2. STANDALONE AUC -- does BvP predict a home run AT ALL?')
    feats = sorted(set(BASE) & set(d.columns))
    dd = d.dropna(subset=feats + ['b_n']).copy()
    dd = dd[dd['b_n'] >= MIN_BIP]
    if 'p_n' in dd.columns:
        dd = dd[dd['p_n'] >= MIN_BIP]
    dd = dd.sort_values('game_date').reset_index(drop=True)
    y = dd['hr'].astype(int).values
    groups = dd['game_date'].values
    print(f'  usable rows (>= {MIN_BIP} BIP both sides, complete features): {len(dd):,} '
          f'| {int(dd.hr.sum()):,} HR')

    print('\n  %-12s %8s  %s' % ('signal', 'AUC', 'read'))
    for c in ['m', 'h'] + ['lift_%d' % K for K in K_GRID]:
        Z = zbyslate(dd, [c]).values
        a, s, _ = cv_auc(Z, y, groups)
        tag = ('raw meeting count' if c == 'm' else
               'raw prior HR count' if c == 'h' else
               'UNREGRESSED rate diff -- the De Paula form' if c == 'lift_0' else
               'shrunk, K=%s' % c.split('_')[1])
        print('  %-12s %8.4f  %s' % (c, a, tag))
    print('\n  0.5000 is a coin flip. For scale: the whole 5-signal basket is ~0.596 on this table.')

    hr_('3. INCREMENTAL -- does it add anything the board does not already have?')
    Zb = zbyslate(dd, feats).values
    ab, sb, _ = cv_auc(Zb, y, groups)
    print(f'  baseline {feats} : AUC {ab:.4f} (sd {sb:.4f})')
    best = None
    for K in K_GRID:
        c = 'lift_%d' % K
        Z = zbyslate(dd, feats + [c]).values
        a, s, coef = cv_auc(Z, y, groups)
        pos = np.clip(coef, 0, None)
        w = pos[-1] / pos.sum() if pos.sum() > 0 else 0.0
        print('  + %-10s : AUC %.4f (%+.4f)  coef %+.4f  implied _SIG weight %.4f'
              % (c, a, a - ab, coef[-1], w))
        if best is None or a > best[1]:
            best = (c, a, w)
    print('\n  DECISION RULE, SET BEFORE LOOKING: ship only if the best incremental AUC clears the')
    print('  baseline by more than the fold sd above (%.4f). Anything smaller is noise dressed as' % sb)
    print('  a finding, and this board already carries one unfitted weight (W_PSW) too many.')

    hr_('4. THE SAME THING, ONLY ON DEEP MATCHUPS')
    print('  If BvP is real anywhere it is where the history is thick. Restricting to m >= floor,')
    print('  best-K incremental AUC on that slice (n shown -- watch it collapse):')
    cbest = best[0]
    for f in FLOORS[1:]:
        g = dd[dd.m >= f]
        if len(g) < 5000 or g.hr.sum() < 300 or g.game_date.nunique() < 50:
            print('  m >= %-3d : n=%-7d -- too few to fit' % (f, len(g)))
            continue
        yg = g['hr'].astype(int).values; gg = g['game_date'].values
        a0, s0, _ = cv_auc(zbyslate(g, feats).values, yg, gg)
        a1, s1, _ = cv_auc(zbyslate(g, feats + [cbest]).values, yg, gg)
        print('  m >= %-3d : n=%-7d HR=%-6d  base %.4f -> +%s %.4f  (%+.4f, fold sd %.4f)'
              % (f, len(g), int(g.hr.sum()), a0, cbest, a1, a1 - a0, s0))

    hr_('5. THE RILEY CHECK -- the biggest tells in ten seasons, and what they did')
    top = d[d.m >= 15].nlargest(25, 'lift_%d' % K_GRID[3])[
        ['game_date', 'batter', 'm', 'h', 'b_rate', 'lift_%d' % K_GRID[3], 'hr']]
    with pd.option_context('display.width', 160, 'display.max_columns', 20):
        print(top.to_string(index=False))
    deep = d[(d.m >= 15) & (d.h >= 5)]
    if len(deep):
        print('\n  rows with >= 15 meetings AND >= 5 prior HR off that arm: %d' % len(deep))
        print('    they homered %.2f%% of the time' % (100 * deep.hr.mean()))
        print('    those same batters homered %.2f%% of the time overall'
              % (100 * d[d.batter_id.isin(deep.batter_id.unique())].hr.mean()))
        print('    league %.2f%%' % (100 * league))
        print('\n  The middle number is the honest comparison. A "he owns this guy" row belongs to a')
        print('  hitter who owns most guys -- that is why he got 15 meetings against a starter who')
        print('  kept his job. Beating the LEAGUE rate is not the test. Beating his OWN is.')

    print('\ndone.', flush=True)


if __name__ == '__main__':
    main()
