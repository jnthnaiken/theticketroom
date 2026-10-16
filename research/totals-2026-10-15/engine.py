"""Totals engine: online opponent-adjusted Poisson ratings from layered signals.

Every feature for match i is computed from matches strictly before i's date (ratings are updated
after the whole date is scored, so same-day games never see each other).
"""
import numpy as np, pandas as pd
from math import lgamma

D = '/home/claude/tot/data/'


def load():
    m = pd.read_pickle(D + 'joined.pkl').copy()
    m = m.sort_values(['date', 'league']).reset_index(drop=True)
    # market O/U 2.5: the pre-match snapshot we could actually bet (Avg 2019+, BbAv before), and closing
    m['o_pre'] = m['Avg>2.5'].fillna(m['BbAv>2.5'])
    m['u_pre'] = m['Avg<2.5'].fillna(m['BbAv<2.5'])
    m['o_cl'] = m['AvgC>2.5']; m['u_cl'] = m['AvgC<2.5']
    m['o_b365'] = m['B365>2.5']; m['u_b365'] = m['B365<2.5']
    for s in ('pre', 'cl'):
        io, iu = 1 / m['o_' + s], 1 / m['u_' + s]
        m['pm_' + s] = io / (io + iu)          # devigged market P(over 2.5)
    # 1X2 pre-match average (Avg 2019+, BbAv before)
    for k in 'HDA':
        m['x' + k] = m['Avg' + k].fillna(m['BbAv' + k])
    m['tot'] = m.FTHG + m.FTAG
    m['over'] = (m.tot > 2.5).astype(int)
    m['d'] = pd.to_datetime(m.date)
    return m


def pois_pmf(l, kmax=11):
    k = np.arange(kmax)
    lg = np.array([lgamma(x + 1) for x in k])
    return np.exp(-l[:, None] + k[None, :] * np.log(np.maximum(l[:, None], 1e-9)) - lg[None, :])


def score_matrix(lh, la, rho=0.0, kmax=11):
    """Dixon-Coles adjusted joint pmf, shape (n, kmax, kmax)."""
    ph, pa = pois_pmf(lh, kmax), pois_pmf(la, kmax)
    M = ph[:, :, None] * pa[:, None, :]
    if rho:
        M[:, 0, 0] *= 1 - lh * la * rho
        M[:, 0, 1] *= 1 + lh * rho
        M[:, 1, 0] *= 1 + la * rho
        M[:, 1, 1] *= 1 - rho
        M = np.clip(M, 0, None); M /= M.sum((1, 2), keepdims=True)
    return M


def p_over(lh, la, line=2.5, rho=0.0):
    M = score_matrix(lh, la, rho)
    k = np.arange(M.shape[1])
    tot = k[:, None] + k[None, :]
    return (M * (tot > line)).sum((1, 2))


def p_team_over(l, line):
    P = pois_pmf(l)
    k = np.arange(P.shape[1])
    return (P * (k > line)).sum(1)


SIG = {  # per-team-match signal columns: (for_home, for_away)
    'g': ('FTHG', 'FTAG'),
    'xg': ('hxG', 'axG'),
    'npxg': ('hnpxG', 'anpxG'),
    'sot': ('HST', 'AST'),
    'sh': ('HS', 'AS'),
}


def ratings(m, w, k=0.06, carry=0.75, home=None):
    """Online multiplicative attack/defence ratings.

    signal per side = sum_j w[j] * s_j * scale_j  (each signal rescaled to goal units by league mean ratio)
    exp_home = mu_h(league) * A[h] * Dd[a];  update log A[h] += k*(log(obs+.5)-log(exp+.5)) etc.
    carry: at a new season each rating is pulled toward 1 (log *= carry). Promoted teams start at
    the league's promoted prior (learned online: mean rating newcomers end their first season with).
    Returns pre-match expected (lh, la) per row, and the league mu used.
    """
    n = len(m)
    lg = m.league.values; ss = m.season.values; dates = m.date.values
    H = m.HomeTeam.values; A_ = m.AwayTeam.values
    # combined observed "goal-equivalent" signal per side
    sh = np.zeros(n); sa = np.zeros(n)
    for key, wt in w.items():
        if not wt:
            continue
        ch, ca = SIG[key]
        vh = m[ch].values.astype(float); va = m[ca].values.astype(float)
        # scale signal to goals using all-history means per league (a constant, no outcome leak of note)
        sc = (m.FTHG.mean() + m.FTAG.mean()) / (np.nanmean(vh) + np.nanmean(va))
        sh += wt * np.nan_to_num(vh * sc, nan=0); sa += wt * np.nan_to_num(va * sc, nan=0)
    tw = sum(w.values())
    sh /= tw; sa /= tw
    att, dfn = {}, {}
    mu = {}  # league -> [home mean, away mean] EW
    last_season = {}
    newc = {}  # league -> promoted prior (log att, log def)
    out_h = np.zeros(n); out_a = np.zeros(n)
    i = 0
    while i < n:
        j = i
        while j < n and dates[j] == dates[i]:
            j += 1
        # predict the date block
        for r in range(i, j):
            L = lg[r]
            if L not in mu:
                mu[L] = [1.5, 1.15]
            for t in (H[r], A_[r]):
                key = (L, t)
                if key not in att:
                    pa_, pd_ = newc.get(L, (-0.15, 0.12))
                    att[key], dfn[key] = pa_, pd_
                    last_season[key] = ss[r]
                elif last_season[key] != ss[r]:
                    att[key] *= carry; dfn[key] *= carry; last_season[key] = ss[r]
            hk, ak = (L, H[r]), (L, A_[r])
            out_h[r] = mu[L][0] * np.exp(att[hk] + dfn[ak])
            out_a[r] = mu[L][1] * np.exp(att[ak] + dfn[hk])
        # update after the block
        for r in range(i, j):
            L = lg[r]; hk, ak = (L, H[r]), (L, A_[r])
            eh, ea = out_h[r], out_a[r]
            gh = np.log(sh[r] + .5) - np.log(eh + .5)
            ga = np.log(sa[r] + .5) - np.log(ea + .5)
            att[hk] += k * gh; dfn[ak] += k * gh
            att[ak] += k * ga; dfn[hk] += k * ga
            mu[L][0] = .995 * mu[L][0] + .005 * sh[r]
            mu[L][1] = .995 * mu[L][1] + .005 * sa[r]
        i = j
    return out_h, out_a


def logloss(y, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))
