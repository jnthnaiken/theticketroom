"""Walk-forward luck-adjusted market model + bet simulator for O/U 2.5 and (calibration-only) team totals.

lambda_side = implied market lambda * exp(b0 + b_own*own_luck + b_opp*opp_luck [+ shots layer])
fit by Poisson GLM with the market offset on all seasons strictly before the test season.
"""
import numpy as np, pandas as pd, statsmodels.api as sm
from engine import logloss, logit, score_matrix
from feats import team_long

RHO = -0.08


def luck_table(m, hl=4):
    t = team_long(m[['league', 'season', 'd', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG', 'hnpxG', 'anpxG', 'HST', 'AST']])
    g = t.groupby(['league', 'team'], sort=False)
    t['lf'] = t.gf - t.xf; t['lA'] = t.ga - t.xa
    t['sf_'] = t.gf - .30 * t.sf; t['sa_'] = t.ga - .30 * t.sa
    for c in ('lf', 'lA', 'sf_', 'sa_'):
        t[c + 'e'] = g[c].transform(lambda s: s.shift(1).ewm(halflife=hl, min_periods=3).mean())
    hs = t[t.home == 1].set_index('idx'); as_ = t[t.home == 0].set_index('idx')
    return pd.DataFrame({'own_h': hs.lfe, 'opp_h': as_.lAe, 'own_a': as_.lfe, 'opp_a': hs.lAe,
                         'sown_h': hs.sf_e, 'sopp_h': as_.sa_e, 'sown_a': as_.sf_e, 'sopp_a': hs.sa_e}).reindex(m.index)


def long_rows(m, L, cols):
    h = pd.DataFrame({'y': m.FTHG, 'off': np.log(m.ilh), 'season': m.season, 'idx': m.index, 'home': 1})
    a = pd.DataFrame({'y': m.FTAG, 'off': np.log(m.ila), 'season': m.season, 'idx': m.index, 'home': 0})
    for c in cols:
        h[c] = L[c + '_h'].values; a[c] = L[c + '_a'].values
    return pd.concat([h, a])


def walk(m, L, cols, first=2015, seasons=range(2019, 2023)):
    """Return m-rows for test seasons with adjusted lambdas alh, ala."""
    out = []
    for s in seasons:
        lr = long_rows(m[(m.season >= first) & (m.season < s)], L.loc[m[(m.season >= first) & (m.season < s)].index], cols).dropna()
        r = sm.GLM(lr.y, sm.add_constant(lr[cols]), family=sm.families.Poisson(), offset=lr.off).fit()
        te = m[m.season == s].copy()
        Lt = L.loc[te.index].fillna(0)
        eh = r.params['const'] + sum(r.params[c] * Lt[c + '_h'] for c in cols)
        ea = r.params['const'] + sum(r.params[c] * Lt[c + '_a'] for c in cols)
        te['alh'] = te.ilh * np.exp(eh); te['ala'] = te.ila * np.exp(ea)
        out.append(te)
    return pd.concat(out)


def probs(o):
    M = score_matrix(o.alh.values, o.ala.values, RHO); k = np.arange(M.shape[1])
    ov = (k[:, None] + k[None, :]) > 2.5
    o['p_over'] = (M * ov).sum((1, 2))
    # the same matrix at the market lambdas: removes the grid/DC approximation so edge = layer only
    M0 = score_matrix(o.ilh.values, o.ila.values, RHO)
    o['p0_over'] = (M0 * ov).sum((1, 2))
    # model P = market devig P shifted by the layer's change
    o['pq_over'] = np.clip(o.pm_pre + (o.p_over - o.p0_over), .01, .99)
    return o


def bets(o, price_o='o_pre', price_u='u_pre', p='pq_over', th=0.02):
    eo = o[p] * o[price_o] - 1; eu = (1 - o[p]) * o[price_u] - 1
    b = o.copy()
    b['side'] = np.where((eo > th) & (eo >= eu), 'O', np.where((eu > th), 'U', ''))
    b = b[b.side != ''].copy()
    b['price'] = np.where(b.side == 'O', b[price_o], b[price_u])
    b['win'] = np.where(b.side == 'O', b.over == 1, b.over == 0)
    b['edge'] = np.where(b.side == 'O', eo.loc[b.index], eu.loc[b.index])
    b['pl'] = np.where(b.win, b.price - 1, -1.0)
    return b
