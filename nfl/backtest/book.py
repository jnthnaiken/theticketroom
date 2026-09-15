"""Stage 2: synthetic books. NO real prices exist for 2021-2025, so a book is a MODEL of the market
at a stated sharpness. The backtest is run under every one, and the answer is read across them."""
import os as _os, sys as _sys
_H = _os.path.dirname(_os.path.abspath(__file__))
for _p in (_os.path.join(_H, '..'), _os.path.join(_H, '..', '..', 'soccer')):
    if _p not in _sys.path: _sys.path.insert(0, _p)
_os.chdir(_os.path.join(_H, '..'))   # nfl/: the model files are read relative to it
OUT = lambda n: _os.path.join(_H, n)

import sys, numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
import nfl_mock as M


D = pd.read_pickle(OUT('weeks_2021_2022_2023_2024_2025.pkl'))
D = D[D.pos.isin(['RB', 'WR', 'TE', 'QB'])].copy()
# our own probability, exactly as the live scorer computes it (roster-normalised, wind trim)
parts = []
for (s, w), g in D.groupby(['season', 'week']):
    g = M.model_prob(g)
    g['wf'] = g.apply(M.wx_mult, axis=1)
    g['p_ours'] = (g.p_model * g.wf).clip(0.005, 0.90)
    parts.append(g)
D = pd.concat(parts, ignore_index=True)
lg = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))
sg = lambda x: 1 / (1 + np.exp(-x))

D['f_tch'] = np.log1p(D.tchpg); D['f_i10'] = np.log1p(D.i10pg); D['f_td'] = np.log1p(D.tdpg)
D['f_bg'] = np.log1p(D.basis_games); D['f_new'] = (D.basis != 'season').astype(float)
D['f_our'] = lg(D.p_ours)
for p in ['QB', 'RB', 'TE', 'WR']: D['p_' + p] = (D.pos == p).astype(float)
RICH = ['f_our', 'f_tch', 'f_i10', 'i10_share', 'f_td', 'imp', 'total_line', 'home', 'f_bg', 'f_new',
        'p_QB', 'p_RB', 'p_TE', 'p_WR']
D['o_tch'] = np.log1p(D.tch_game); D['o_i10'] = np.log1p(D.i10_game)
ORAC = RICH + ['o_tch', 'o_i10']
D = D.dropna(subset=['imp', 'total_line']).copy()
D['f_rz'] = D.rz_pg.fillna(D.rz_pg.median())

rng = np.random.default_rng(7)
D['p_book_rich'] = np.nan; D['p_book_sharp'] = np.nan
for s in sorted(D.season.unique()):
    tr = (D.season != s) & D.played; te = D.season == s
    for name, F in [('cal', ['f_our']), ('rich', RICH), ('orac', ORAC)]:
        X = D.loc[tr, F].values; mu, sd = X.mean(0), X.std(0) + 1e-9
        m = LogisticRegression(max_iter=3000, C=1.0).fit((X - mu) / sd, D.loc[tr, 'td_game'])
        D.loc[te, 'p_' + name] = m.predict_proba((D.loc[te, F].values - mu) / sd)[:, 1]
# same  = the book knows exactly what we know (our model, honestly calibrated)
# weak  = the book knows LESS than we do (ours + noise) -- the only world where we have an edge
# rich  = ours plus prior TD rate, sample size, game line: a little more than we know
# sharp = rich pulled a fifth of the way toward same-game usage: materially more than we know
KAPPA = float(sys.argv[1]) if len(sys.argv) > 1 else 0.2
D['p_book_same'] = D.p_cal
D['p_book_weak'] = sg(lg(D.p_cal) + rng.normal(0, 0.6, len(D)))
D['p_book_rich'] = D.p_rich
D['p_book_sharp'] = sg((1 - KAPPA) * lg(D.p_rich) + KAPPA * lg(D.p_orac))
D.to_pickle(OUT('books.pkl'))
T = D[D.played & (D.season == 2025)]
print('2025, played rows', len(T))
for c in ['p_ours', 'p_book_weak', 'p_book_same', 'p_book_rich', 'p_book_sharp']:
    print(f'  {c:14} AUC {roc_auc_score(T.td_game, T[c]):.3f}  mean {T[c].mean():.3f}  (hit {T.td_game.mean():.3f})')

# ---- RECALIBRATION, on the rows a book actually prices -----------------------------------------
# A linear logistic is miscalibrated at the ends: the first cut had the +150..+500 band hitting ~2pp
# ABOVE its own probability, which after a flat margin priced the middle of the card at roughly zero
# vig -- a free edge for any rule living there. Each book is recalibrated leave-one-season-out on its
# offered top-8 with a SMOOTH map (cubic in logit). Isotonic was tried and rejected: its step
# function hands dozens of players the same price, and our model then picks inside each tie with
# information the book threw away -- a manufactured edge.
for b in ['weak', 'same', 'rich', 'sharp']:
    col = 'p_book_' + b
    off = D[D.played].sort_values(col, ascending=False).groupby(['season', 'week', 'team']).head(8)
    new = D[col].copy()
    feats = lambda p: np.column_stack([lg(p), lg(p) ** 2, lg(p) ** 3])
    for s in sorted(D.season.unique()):
        tr = off[off.season != s]
        X = feats(tr[col].values); mu, sd = X.mean(0), X.std(0)
        m = LogisticRegression(max_iter=3000, C=10.0).fit((X - mu) / sd, tr.td_game)
        te = (D.season == s).values
        new[te] = m.predict_proba((feats(D.loc[te, col].values) - mu) / sd)[:, 1]
    D[col] = np.clip(new, 0.01, 0.95)
D.to_pickle(OUT('books.pkl'))
print('recalibrated')
