#!/usr/bin/env python3
"""
lab15.py — the PRICE-FREE lab over the 2015-2024 Statcast table.

WHY THIS EXISTS
---------------
Owner, 2026-09-13: "lets just do it without the prices then. lets just focus on
perfecting the model and draft system."

We own ten years of outcomes (510,301 batter-games / 1,840 slates) and eighty-one
nights of prices. Anything that needs a price is out of reach. This script is
everything that does NOT need one, and it turns out that is most of what matters:

  §1  how good can the SCORER get on these features (ceiling, and what _SIG leaves behind)
  §2  does that answer drift across ball eras
  §3  when the DRAFT picks N legs on a slate, are the hits independent or correlated
  §4  given that real correlation, which slip SHAPE wins — as a function of edge k

§3 and §4 are the point. The doubles-vs-trebles decision currently rests on 69
reconstructed soccer slips. Here it rests on every slate since 2015, because the
joint hit distribution of our own picks is a pure outcome question. Price enters §4
only as a SWEPT PARAMETER k (how much each leg beats its price), never as data — so
the output is not "what did we earn in 2017", it is "at what k does the treble
overtake the double, given how our legs actually clump".

THE ONE SUBSTITUTION, STATED PLAINLY
------------------------------------
Without a market there is no "+900". The stand-in for price is the model's own
out-of-fold predicted rate p̂. A p̂=4% bat is the analogue of a longshot, p̂=12% of a
short one. That is legitimate for structure work — a round robin's joint
distribution is a function of probabilities, and k carries the price — but it means
§3/§4 CANNOT tell us whether we beat a book. Only the 81 priced nights can do that.

LEAKAGE
-------
Every feature in the table is already strictly pre-game (trailing window, closed
left). Everything this script adds on top (prior HR rate, rest, game index) is built
with a shift so a row never sees its own outcome. All probabilities used downstream
are OUT-OF-FOLD from CV grouped by game_date, so no slate is scored by a model that
trained on it.

RUN
---
    python3 lab15.py "table/*.parquet"          # the real thing
    python3 lab15.py --selftest                 # synthetic data, verifies the math
"""
import sys, os, glob, math, json, argparse, warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- config
SEED = 17
N_FOLDS = 5
MIN_N = 20            # min trailing BIP on both sides, mirrors fit_savant.py
MIN_SLATE = 60        # a slate needs this many usable bats to be draftable

# the LIVE shipped basket, mapped onto this table's Statcast analogues.
# build15.py: _SIG=[('_zxpow',.029),('_zxwcon',.193),('_zars',.011),('_zhh',.432),('_zla',.335)]
LIVE5 = [('b_brl', .029), ('b_xwobacon', .193), ('p_brl', .011), ('b_hh', .432), ('b_la', .335)]

BAT = ['b_hh', 'b_brl', 'b_fb', 'b_pull', 'b_sweet', 'b_la', 'b_xwobacon', 'b_swstr', 'b_csw']
PIT = ['p_hh', 'p_brl', 'p_fb', 'p_pull', 'p_sweet', 'p_la', 'p_xwobacon', 'p_swstr', 'p_csw']

la_window = lambda la: np.exp(-((la - 25.0) / 14.0) ** 2)


def hr(title):
    print('\n' + '=' * 78); print(title); print('=' * 78, flush=True)


def sub(title):
    print('\n--- ' + title + ' ' + '-' * max(0, 72 - len(title)), flush=True)


# ---------------------------------------------------------------- load
def load(pattern):
    files = sorted(glob.glob(pattern))
    if not files:
        sys.exit(f'!! no files matched {pattern!r}')
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    print(f'loaded {len(files)} file(s): {len(df):,} rows, {len(df.columns)} cols')
    print('columns:', ', '.join(df.columns))
    return df


def prepare(df):
    """Filter to usable rows and add the leak-free extras the table doesn't carry."""
    df['game_date'] = pd.to_datetime(df['game_date'])
    df = df.sort_values(['game_date', 'game_pk', 'batter_id']).reset_index(drop=True)
    n0 = len(df)

    # --- extras, all built with a shift so a row never sees its own outcome ---
    df['season'] = df['game_date'].dt.year
    g = df.groupby(['batter_id', 'season'], sort=False)
    prior_hr = g['hr'].transform(lambda s: s.shift(1).expanding().sum())
    prior_g = g['hr'].transform(lambda s: s.shift(1).expanding().count())
    df['b_hr_rate_prior'] = (prior_hr / prior_g.replace(0, np.nan))
    df['b_games_prior'] = prior_g.fillna(0)
    roll_hr = g['hr'].transform(lambda s: s.shift(1).rolling(30, min_periods=10).sum())
    df['b_hr_rate_30'] = roll_hr / 30.0
    df['b_rest'] = g['game_date'].transform(lambda s: (s - s.shift(1)).dt.days).fillna(1).clip(0, 10)
    df['b_month'] = df['game_date'].dt.month

    have = [c for c in BAT + PIT if c in df.columns]
    need = have + ['hr', 'game_date', 'game_pk', 'batter_id']
    m = df[need].notna().all(axis=1)
    if 'b_n' in df.columns: m &= (df['b_n'] >= MIN_N)
    if 'p_n' in df.columns: m &= (df['p_n'] >= MIN_N)
    df = df[m].reset_index(drop=True)

    # bats with no prior game this season get the league-ish fallback, flagged
    df['b_new'] = df['b_hr_rate_prior'].isna().astype(float)
    lg = df['hr'].mean()
    df['b_hr_rate_prior'] = df['b_hr_rate_prior'].fillna(lg)
    df['b_hr_rate_30'] = df['b_hr_rate_30'].fillna(df['b_hr_rate_prior'])

    print(f'usable: {len(df):,} of {n0:,} rows | {df["hr"].mean()*100:.2f}% HR | '
          f'{df["game_date"].nunique():,} slates | {df["season"].min()}..{df["season"].max()}')
    return df


def slate_z(df, cols):
    """Z-score WITHIN game_date — the space build15.py actually scores in."""
    out = pd.DataFrame(index=df.index)
    g = df.groupby('game_date', sort=False)
    for c in cols:
        mu = g[c].transform('mean'); sd = g[c].transform('std').replace(0, np.nan)
        out['z_' + c] = ((df[c] - mu) / sd).fillna(0.0)
    return out


# ---------------------------------------------------------------- §1 model
def fold_ids(dates, k=N_FOLDS):
    """Grouped by slate: a game_date lives entirely in one fold."""
    u = np.array(sorted(pd.unique(dates)))
    rs = np.random.RandomState(SEED); rs.shuffle(u)
    assign = {d: i % k for i, d in enumerate(u)}
    return dates.map(assign).values


def auc(y, p):
    y = np.asarray(y); p = np.asarray(p)
    n1 = y.sum(); n0 = len(y) - n1
    if n1 == 0 or n0 == 0: return float('nan')
    r = pd.Series(p).rank().values
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def logloss(y, p):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def oof_model(X, y, folds, kind):
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import HistGradientBoostingClassifier
    p = np.zeros(len(y)); coefs = []
    for f in range(N_FOLDS):
        tr, te = folds != f, folds == f
        if kind == 'logit':
            m = LogisticRegression(max_iter=2000, C=1.0)
            m.fit(X[tr], y[tr]); coefs.append(m.coef_[0])
        else:
            m = HistGradientBoostingClassifier(
                max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
                min_samples_leaf=200, l2_regularization=1.0,
                early_stopping=True, validation_fraction=0.12, random_state=SEED)
            m.fit(X[tr], y[tr])
        p[te] = m.predict_proba(X[te])[:, 1]
    return p, (np.mean(coefs, axis=0) if coefs else None)


def section_model(df):
    hr('SECTION 1 — THE SCORER: how much is _SIG leaving on the table?')
    y = df['hr'].values.astype(int)
    folds = fold_ids(df['game_date'])

    # (a) the LIVE basket, exactly as shipped: fixed weights, per-slate z, la through the bell
    d2 = df.copy()
    d2['b_la'] = la_window(d2['b_la'])
    Z = slate_z(d2, [c for c, _ in LIVE5])
    live = sum(w * Z['z_' + c] for c, w in LIVE5).values

    feats = [c for c in BAT + PIT if c in df.columns]
    extras = ['b_hr_rate_prior', 'b_hr_rate_30', 'b_games_prior', 'b_rest', 'b_month', 'b_new']
    Zf = slate_z(df, feats)
    Xf = Zf.values
    Xe = np.hstack([Xf, df[extras].values])

    res = {}
    res['live5   (shipped _SIG, fixed wts)'] = (live, None)
    for lab, X, kind in [
        ('logit16 (all Statcast, refit)', Xf, 'logit'),
        ('logit22 (+ prior-HR / rest)  ', Xe, 'logit'),
        ('gbm16   (nonlinear)          ', Xf, 'gbm'),
        ('gbm22   (+ prior-HR / rest)  ', Xe, 'gbm'),
    ]:
        p, c = oof_model(X, y, folds, kind)
        res[lab] = (p, c)

    sub('out-of-fold, CV grouped by slate')
    print(f'  {"model":<34}{"AUC":>8}{"logloss":>10}{"vs live5":>10}')
    base = auc(y, live)
    for lab, (p, _) in res.items():
        a = auc(y, p)
        ll = logloss(y, p) if p.min() >= 0 and p.max() <= 1 else float('nan')
        print(f'  {lab:<34}{a:>8.4f}{ll:>10.5f}{a-base:>+10.4f}')

    # which features the best linear model actually leans on
    pf, cf = res['logit22 (+ prior-HR / rest)  ']
    names = ['z_' + c for c in feats] + extras
    order = np.argsort(-np.abs(cf))
    sub('logit22 coefficients (per-slate z space), |coef| descending')
    for i in order[:14]:
        print(f'  {names[i]:<22}{cf[i]:>+9.4f}')

    # incremental value of each block
    sub('does the OPPOSING STARTER earn its place?')
    bonly = [c for c in BAT if c in df.columns]
    pb, _ = oof_model(slate_z(df, bonly).values, y, folds, 'gbm')
    pa, _ = oof_model(Xf, y, folds, 'gbm')
    print(f'  batter features only        AUC {auc(y,pb):.4f}')
    print(f'  + opposing starter          AUC {auc(y,pa):.4f}  ({auc(y,pa)-auc(y,pb):+.4f})')

    best_lab = max(res, key=lambda k: auc(y, res[k][0]))
    print(f'\n  BEST: {best_lab.strip()}  (AUC {auc(y,res[best_lab][0]):.4f})')
    return res, best_lab, y


def section_calibration(df, p, y):
    sub('calibration of the chosen scorer (does p̂ mean what it says?)')
    q = pd.qcut(p, 10, labels=False, duplicates='drop')
    print(f'  {"decile":<10}{"n":>8}{"pred":>9}{"actual":>9}{"ratio":>8}')
    for d in range(int(q.max()) + 1):
        m = q == d
        print(f'  {d+1:<10}{m.sum():>8}{p[m].mean()*100:>8.2f}%{y[m].mean()*100:>8.2f}%'
              f'{(y[m].mean()/p[m].mean() if p[m].mean() else 0):>8.3f}')


# ---------------------------------------------------------------- §2 drift
def section_drift(df, p, y):
    hr('SECTION 2 — ERA DRIFT: is one weight set right for ten seasons?')
    print(f'  {"season":<9}{"slates":>8}{"bats":>9}{"HR%":>8}{"AUC":>8}')
    for s, g in df.groupby('season'):
        i = g.index.values
        print(f'  {s:<9}{g["game_date"].nunique():>8}{len(g):>9}'
              f'{y[i].mean()*100:>7.2f}%{auc(y[i], p[i]):>8.4f}')
    print('\n  A season whose AUC sits well below the rest is a ball/rules era the')
    print('  fitted weights do not describe. Flat = one weight set is fine.')


# ---------------------------------------------------------------- §3 draft
def poisson_binomial(ps):
    """Exact P(k hits) for independent legs with probabilities ps."""
    d = np.zeros(len(ps) + 1); d[0] = 1.0
    for p in ps:
        d[1:] = d[1:] * (1 - p) + d[:-1] * p
        d[0] *= (1 - p)
    return d


def build_slips(df, p, y, n_legs=3, policy='gamecap', lo=None, name=''):
    """One slip per slate under a selection policy. Returns (P, H) arrays of shape (slates, n_legs)."""
    rs = np.random.RandomState(SEED)
    P, H = [], []
    for d, g in df.groupby('game_date', sort=False):
        idx = g.index.values
        if len(idx) < MIN_SLATE: continue
        pp, hh, gk = p[idx], y[idx], df.loc[idx, 'game_pk'].values
        order = np.argsort(-pp)

        if policy == 'top':                      # top N, no constraint
            pick = order[:n_legs]
        elif policy == 'gamecap':                # top N, one per game (the moon rule)
            pick, used = [], set()
            for i in order:
                if gk[i] in used: continue
                used.add(gk[i]); pick.append(i)
                if len(pick) == n_legs: break
            pick = np.array(pick)
        elif policy == 'samegame':               # N from ONE game — the correlation control
            best = None
            for k in pd.unique(gk):
                m = np.where(gk == k)[0]
                if len(m) < n_legs: continue
                m = m[np.argsort(-pp[m])][:n_legs]
                if best is None or pp[m].sum() > pp[best].sum(): best = m
            if best is None: continue
            pick = best
        elif policy == 'anchor':                 # 1 short + (N-1) longshots, distinct games
            pick, used = [order[0]], {gk[order[0]]}
            band = [i for i in order if lo[0] <= pp[i] <= lo[1] and gk[i] not in used]
            for i in band:
                if gk[i] in used: continue
                used.add(gk[i]); pick.append(i)
                if len(pick) == n_legs: break
            if len(pick) < n_legs: continue
            pick = np.array(pick)
        elif policy == 'band':                   # all legs from the longshot band, distinct games
            pick, used = [], set()
            for i in order:
                if not (lo[0] <= pp[i] <= lo[1]): continue
                if gk[i] in used: continue
                used.add(gk[i]); pick.append(i)
                if len(pick) == n_legs: break
            if len(pick) < n_legs: continue
            pick = np.array(pick)
        elif policy == 'random':                 # control: random bats, distinct games
            perm = rs.permutation(len(idx)); pick, used = [], set()
            for i in perm:
                if gk[i] in used: continue
                used.add(gk[i]); pick.append(i)
                if len(pick) == n_legs: break
            pick = np.array(pick)
        else:
            raise ValueError(policy)

        if len(pick) < n_legs: continue
        P.append(pp[pick]); H.append(hh[pick])
    return np.array(P), np.array(H), name


def dispersion(P, H, label):
    """Observed k-hit distribution vs the exact independent expectation."""
    n = P.shape[1]
    obs = np.bincount(H.sum(axis=1), minlength=n + 1).astype(float)
    exp = np.zeros(n + 1)
    for ps in P: exp += poisson_binomial(ps)
    N = len(P)
    print(f'\n  {label}   ({N} slates, mean leg p̂ {P.mean()*100:.2f}%)')
    print(f'    {"hits":<7}{"observed":>11}{"independent":>13}{"obs/exp":>10}')
    for k in range(n + 1):
        r = obs[k] / exp[k] if exp[k] > 0.5 else float('nan')
        print(f'    {k:<7}{obs[k]:>11.0f}{exp[k]:>13.1f}{r:>10.3f}')
    # chi-square against independence
    m = exp > 5
    chi = float(((obs[m] - exp[m]) ** 2 / exp[m]).sum())
    # pairwise correlation of leg outcomes
    cors = []
    for i in range(n):
        for j in range(i + 1, n):
            a, b = H[:, i], H[:, j]
            if a.std() > 0 and b.std() > 0: cors.append(np.corrcoef(a, b)[0, 1])
    rho = float(np.mean(cors)) if cors else 0.0
    var_o = H.sum(axis=1).var()
    var_e = float(sum((ps * (1 - ps)).sum() for ps in P) / N)
    print(f'    chi2 vs independence {chi:.1f} (df {int(m.sum())-1})   mean pairwise rho {rho:+.4f}')
    print(f'    variance of hit count: observed {var_o:.4f} vs independent {var_e:.4f} '
          f'({"OVER" if var_o>var_e else "UNDER"}-dispersed)')
    return {'obs': obs.tolist(), 'exp': exp.tolist(), 'rho': rho, 'chi2': chi,
            'var_obs': float(var_o), 'var_exp': var_e, 'n': int(N)}


def section_depth(df, p, y):
    """How fast does hit rate decay as the draft reaches further down the board?"""
    sub('rank decay — hit rate by position on the slate (the Z_GATE question)')
    ranks, hits = [], []
    for d, g in df.groupby('game_date', sort=False):
        idx = g.index.values
        if len(idx) < MIN_SLATE: continue
        o = np.argsort(-p[idx])
        ranks.append(np.arange(len(o))); hits.append(y[idx][o])
    R = np.concatenate(ranks); Hh = np.concatenate(hits)
    print(f'    {"rank":<12}{"n":>9}{"HR rate":>10}{"vs slate avg":>14}')
    basev = Hh.mean()
    for lo, hi in [(0, 1), (1, 3), (3, 6), (6, 10), (10, 20), (20, 40), (40, 80), (80, 10**6)]:
        m = (R >= lo) & (R < hi)
        if m.sum() < 200: continue
        lab = f'{lo+1}' if hi - lo == 1 else f'{lo+1}-{hi}'
        print(f'    {lab:<12}{m.sum():>9}{Hh[m].mean()*100:>9.2f}%{Hh[m].mean()/basev:>13.2f}x')
    print('    A flat tail means the board can be drafted deeper for free.')
    print('    A steep one means the gate is load-bearing and should not move.')


def section_legcount(df, p, y):
    """Does clumping get worse as the slip gets longer?"""
    sub('does clumping compound with slip length? (top-N, one per game)')
    print(f'    {"legs":<7}{"slates":>8}{"mean p̂":>9}{"rho":>9}{"var obs":>10}{"var ind":>10}{"ratio":>8}')
    for n in (2, 3, 4, 5):
        P, H, _ = build_slips(df, p, y, n, 'gamecap', None, '')
        if len(P) < 50: continue
        cors = []
        for i in range(n):
            for j in range(i + 1, n):
                a, b = H[:, i], H[:, j]
                if a.std() > 0 and b.std() > 0: cors.append(np.corrcoef(a, b)[0, 1])
        rho = float(np.mean(cors)) if cors else 0.0
        vo = H.sum(axis=1).var()
        ve = float(sum((ps * (1 - ps)).sum() for ps in P) / len(P))
        print(f'    {n:<7}{len(P):>8}{P.mean()*100:>8.2f}%{rho:>+9.4f}{vo:>10.4f}{ve:>10.4f}{vo/ve:>8.3f}')
    print('    ratio > 1 = the slip is riskier than its price assumes at every length.')


def section_draft(df, p, y, band):
    hr('SECTION 3 — THE DRAFT: are our legs independent, or do they clump?')
    print('  A round robin is priced as if the legs are independent. If they are')
    print('  NEGATIVELY correlated the treble is worth less than its price implies;')
    print('  if POSITIVELY correlated it is worth more. This is the whole argument,')
    print('  and it needs no odds at all.')
    print(f'\n  longshot band for anchor/band policies: p̂ in [{band[0]*100:.1f}%, {band[1]*100:.1f}%]')
    section_depth(df, p, y)
    section_legcount(df, p, y)
    out = {}
    for pol, lab in [('gamecap', 'top-3, one per game  (the moon rule)'),
                     ('top',     'top-3, unconstrained'),
                     ('samegame','top-3 from ONE game  (correlation control)'),
                     ('anchor',  'anchor + 2 longshots, distinct games'),
                     ('band',    '3 longshots, distinct games'),
                     ('random',  'random 3, distinct games  (null control)')]:
        P, H, _ = build_slips(df, p, y, 3, pol, band, lab)
        if len(P) < 50:
            print(f'\n  {lab}: only {len(P)} slates — skipped'); continue
        out[pol] = dispersion(P, H, lab)
        out[pol]['P'], out[pol]['H'] = P, H
    return out


# ---------------------------------------------------------------- §4 structure
def structure_returns(P, H, k, risk=2.0):
    """Return per slate for each slip shape, if every leg beats its price by factor k.

    Book prices leg i at implied q = p̂/k, so decimal odds = k/p̂ and the single's
    EV multiple is exactly k. Payouts use the REALISED outcomes in H, so whatever
    correlation exists between our legs is carried through untouched.
    """
    n = P.shape[1]
    dec = k / np.clip(P, 1e-6, 1)                       # decimal odds per leg
    combos = {
        'singles  (3 x 1)':      [(0,), (1,), (2,)],
        'doubles  (3 x 2)':      [(0, 1), (0, 2), (1, 2)],
        'by 2s & 3 (CURRENT)':   [(0, 1), (0, 2), (1, 2), (0, 1, 2)],
        'treble   (1 x 3)':      [(0, 1, 2)],
    }
    res = {}
    for lab, cs in combos.items():
        unit = risk / len(cs)                            # unit = risk / ncombo, same as the code
        net = np.zeros(len(P))
        for c in cs:
            won = H[:, list(c)].all(axis=1)
            pay = dec[:, list(c)].prod(axis=1)
            net += np.where(won, unit * (pay - 1.0), -unit)
        res[lab] = (net.mean(), net.mean() / risk * 100, net.std(), float((net > 0).mean()))
    return res


def section_structure(draft, k_grid):
    hr('SECTION 4 — THE SHAPE: at what edge does the treble start to pay?')
    print('  k = how much each leg beats its price. k<1 the book wins the leg, k>1 we do.')
    print('  Payouts use REAL outcomes, so the clumping measured in §3 is priced in.')
    print('  Measured k on live MLB moon legs: ~0.89.  Soccer moon legs: ~1.13.')
    for pol in ['gamecap', 'anchor', 'band']:
        if pol not in draft: continue
        d = draft[pol]; P, H = d['P'], d['H']
        sub(f'{pol}  ({d["n"]} slates, mean leg p̂ {P.mean()*100:.2f}%, rho {d["rho"]:+.4f})')
        print(f'    {"k":<7}' + ''.join(f'{lab:>22}' for lab in
              ['singles', 'doubles', 'by 2s & 3 (CURRENT)', 'treble']))
        cross = None
        for k in k_grid:
            r = structure_returns(P, H, k)
            row = [r['singles  (3 x 1)'], r['doubles  (3 x 2)'],
                   r['by 2s & 3 (CURRENT)'], r['treble   (1 x 3)']]
            print(f'    {k:<7.2f}' + ''.join(f'{x[1]:>21.1f}%' for x in row))
            if cross is None and row[3][1] > row[1][1]: cross = k
        print(f'\n    treble first beats doubles-only at k = '
              f'{cross if cross else ">" + str(k_grid[-1])}')
        best = {}
        for k in k_grid:
            r = structure_returns(P, H, k)
            best[k] = max(r, key=lambda s: r[s][1])
        print('    best shape by k: ' + ', '.join(f'{k:.2f}->{best[k].split("(")[0].strip()}'
                                                  for k in k_grid))
        # the owner's actual complaint is variance, not mean -- so show it
        for kk in (0.90, 1.00):
            if kk not in k_grid: continue
            r = structure_returns(P, H, kk)
            print(f'\n    at k={kk:.2f} — what the ride feels like:')
            print(f'      {"shape":<24}{"ROI":>9}{"sd/night":>11}{"cash nights":>13}')
            for lab in ['singles  (3 x 1)', 'doubles  (3 x 2)',
                        'by 2s & 3 (CURRENT)', 'treble   (1 x 3)']:
                m, roi, sd, cash = r[lab]
                print(f'      {lab:<24}{roi:>8.1f}%{sd:>11.2f}{cash*100:>12.1f}%')


# ---------------------------------------------------------------- selftest
def selftest():
    """Synthetic slates with a KNOWN correlation, to prove the §3/§4 math."""
    hr('SELF-TEST — synthetic data with known structure')
    rs = np.random.RandomState(3)
    n_slates, per = 400, 90
    rows = []
    for s in range(n_slates):
        date = pd.Timestamp('2020-04-01') + pd.Timedelta(days=s)
        # a slate-level shock makes legs on the SAME slate positively correlated
        shock = rs.normal(0, 0.55)
        for b in range(per):
            skill = rs.normal(0, 1)
            lp = -2.3 + 0.45 * skill + shock
            pr = 1 / (1 + math.exp(-lp))
            rows.append(dict(batter_id=b, game_date=date, game_pk=s * 100 + b // 6,
                             hr=int(rs.rand() < pr), b_hh=skill + rs.normal(0, .4),
                             b_la=25 + 6 * skill, b_brl=skill, b_xwobacon=skill + rs.normal(0, .4),
                             b_fb=rs.normal(), b_pull=rs.normal(), b_sweet=rs.normal(),
                             b_swstr=rs.normal(), b_csw=rs.normal(),
                             p_hh=rs.normal(), p_brl=rs.normal(), p_fb=rs.normal(),
                             p_pull=rs.normal(), p_sweet=rs.normal(), p_la=rs.normal(),
                             p_xwobacon=rs.normal(), p_swstr=rs.normal(), p_csw=rs.normal(),
                             b_n=50, p_n=50))
    df = prepare(pd.DataFrame(rows))
    y = df['hr'].values.astype(int)
    folds = fold_ids(df['game_date'])
    X = slate_z(df, [c for c in BAT + PIT if c in df.columns]).values
    p, _ = oof_model(X, y, folds, 'logit')
    print(f'\nsynthetic AUC {auc(y,p):.4f} (should be well above 0.5)')

    print('\nEXPECTATION: a per-slate shock makes legs POSITIVELY correlated, so the')
    print('observed 3-hit count must come in ABOVE the independent expectation and')
    print('the hit count must be OVER-dispersed. If it does not, the math is wrong.')
    band = (float(np.quantile(p, .55)), float(np.quantile(p, .85)))
    d = section_draft(df, p, y, band)
    ok = d['gamecap']['var_obs'] > d['gamecap']['var_exp'] and d['gamecap']['rho'] > 0
    print(f'\n  SELF-TEST {"PASS" if ok else "FAIL"}: positive rho and over-dispersion recovered')

    print('\nEXPECTATION: with positive correlation the treble should look BETTER than')
    print('independence implies, so its crossover k should sit at or below 1.00.')
    section_structure(d, [0.85, 0.95, 1.00, 1.05, 1.15])
    print('\nAlso checking the degenerate case: at k=1 a SINGLE must return ~0%.')
    r = structure_returns(d['gamecap']['P'], d['gamecap']['H'], 1.0)
    s = r['singles  (3 x 1)'][1]
    print(f'  singles at k=1.00: {s:+.2f}%  ->  {"PASS" if abs(s) < 3 else "FAIL"} (want ~0)')
    return 0 if ok and abs(s) < 3 else 1


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('table', nargs='?', help='glob for the parquet table')
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--band', default='0.04,0.09',
                    help='longshot p̂ band, the analogue of +650..+1100')
    a = ap.parse_args()
    if a.selftest: sys.exit(selftest())
    if not a.table: sys.exit('!! give a parquet glob, or --selftest')

    df = prepare(load(a.table))
    res, best, y = section_model(df)
    p = res[best][0]
    section_calibration(df, p, y)
    section_drift(df, p, y)
    band = tuple(float(x) for x in a.band.split(','))
    draft = section_draft(df, p, y, band)
    section_structure(draft, [0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.20])

    hr('WHAT THIS DOES NOT SETTLE')
    print('  No odds are used anywhere above. §4 sweeps k rather than measuring it,')
    print('  so nothing here says we beat a book. The 81 priced nights are still the')
    print('  only evidence on that, and they say k<1 in every band we can measure.')
    print('  What IS settled here: the scorer ceiling, whether _SIG leaves signal')
    print('  behind, and whether our legs clump — the last of which decides the shape.')

    slim = {k: {kk: vv for kk, vv in v.items() if kk not in ('P', 'H')}
            for k, v in draft.items()}
    json.dump(slim, open('lab15_draft.json', 'w'), indent=1)
    print('\nwrote lab15_draft.json')


if __name__ == '__main__':
    main()
