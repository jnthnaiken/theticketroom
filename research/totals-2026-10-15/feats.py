"""Pre-match features (strictly from earlier dates) for totals research."""
import numpy as np, pandas as pd
from engine import load, ratings, p_over, logit
from scipy.optimize import brentq


def team_long(m):
    """One row per team per match with for/against signals."""
    base = ['idx', 'league', 'season', 'd']
    h = pd.DataFrame({'idx': m.index, 'league': m.league, 'season': m.season, 'd': m.d, 'team': m.HomeTeam,
                      'gf': m.FTHG, 'ga': m.FTAG, 'xf': m.hnpxG, 'xa': m.anpxG, 'sf': m.HST, 'sa': m.AST, 'home': 1})
    a = pd.DataFrame({'idx': m.index, 'league': m.league, 'season': m.season, 'd': m.d, 'team': m.AwayTeam,
                      'gf': m.FTAG, 'ga': m.FTHG, 'xf': m.anpxG, 'xa': m.hnpxG, 'sf': m.AST, 'sa': m.HST, 'home': 0})
    t = pd.concat([h, a]).sort_values(['team', 'league', 'd', 'idx']).reset_index(drop=True)
    g = t.groupby(['league', 'team'], sort=False)
    t['rest'] = g.d.diff().dt.days
    for n in (3, 6, 12):
        for c in ('gf', 'ga', 'xf', 'xa'):
            t[f'{c}{n}'] = g[c].transform(lambda s: s.shift(1).rolling(n, min_periods=max(2, n // 2)).mean())
    t['gtot6'] = t.gf6 + t.ga6
    t['xtot6'] = t.xf6 + t.xa6
    t['gtot3'] = t.gf3 + t.ga3
    t['xtot3'] = t.xf3 + t.xa3
    t['luck6'] = t.gtot6 - t.xtot6        # goals in his games above the chances made in them
    t['luck12'] = (t.gf12 + t.ga12) - (t.xf12 + t.xa12)
    t['n_prev'] = g.cumcount()
    return t


def market_lambdas(m):
    """Solve total lambda from devigged P(over 2.5) under Poisson, and split it with the 1X2 favourite share."""
    def tot_from_p(p):
        if not (0.02 < p < 0.98):
            return np.nan
        f = lambda L: 1 - np.exp(-L) * (1 + L + L * L / 2) - p
        return brentq(f, 0.2, 8)
    T = np.array([tot_from_p(p) if p == p else np.nan for p in m.pm_pre.values])
    ih, id_, ia = 1 / m.xH, 1 / m.xD, 1 / m.xA
    s = ih + id_ + ia
    ph, pa = ih / s, ia / s
    # crude split: home share from (ph - pa) via empirical slope ~ goal-diff; calibrated later if needed
    share = 0.5 + 0.42 * (ph - pa)
    return T, T * share, T * (1 - share), ph, pa


def build(rcfg=dict(w=dict(g=.15, npxg=.55, sot=.3), k=.03, carry=.6)):
    m = load()
    lh, la = ratings(m, rcfg['w'], rcfg['k'], rcfg['carry'])
    m['lh'], m['la'] = lh, la
    m['po_model'] = p_over(lh, la)
    T, mlh, mla, ph, pa = market_lambdas(m)
    m['mT'], m['mlh'], m['mla'], m['ph'], m['pa'] = T, mlh, mla, ph, pa
    t = team_long(m)
    hs = t[t.home == 1].set_index('idx'); as_ = t[t.home == 0].set_index('idx')
    for c in ('rest', 'gtot6', 'xtot6', 'gtot3', 'xtot3', 'luck6', 'luck12', 'n_prev', 'xf6', 'xa6', 'gf6', 'ga6'):
        m['h_' + c] = hs[c].reindex(m.index).values
        m['a_' + c] = as_[c].reindex(m.index).values
    # match-level engineered features
    m['f_mkt'] = logit(m.pm_pre)
    m['f_model_gap'] = (m.lh + m.la) - m.mT                    # rating total minus market total
    m['f_modlogit_gap'] = logit(m.po_model) - m.f_mkt
    m['f_luck'] = (m.h_luck6 + m.a_luck6) / 2                  # recent goals above xG in both sides' games
    m['f_luck12'] = (m.h_luck12 + m.a_luck12) / 2
    m['f_hot'] = (m.h_gtot3 + m.a_gtot3) / 2 - m.mT            # recent actual totals vs tonight's line
    m['f_xform'] = (m.h_xtot6 + m.a_xtot6) / 2 - m.mT          # recent chance totals vs tonight's line
    m['f_mismatch'] = (m.ph - m.pa).abs()
    m['f_rest'] = np.minimum(m.h_rest, 14) + np.minimum(m.a_rest, 14)
    m['f_short'] = ((m.h_rest <= 4) | (m.a_rest <= 4)).astype(float)
    m['f_early'] = (np.minimum(m.h_n_prev, m.a_n_prev) < 0).astype(float)
    wk = m.groupby(['league', 'season']).d.rank(method='dense')
    m['f_stage'] = wk / m.groupby(['league', 'season']).d.transform(lambda s: s.rank(method='dense').max())
    m['f_line'] = m.mT
    return m


if __name__ == '__main__':
    m = build()
    m.to_pickle('/home/claude/tot/data/feats.pkl')
    print(m[[c for c in m.columns if c.startswith('f_')]].describe().T[['count', 'mean', 'std']].round(3))
