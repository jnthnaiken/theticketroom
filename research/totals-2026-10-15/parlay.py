import numpy as np, pandas as pd, sys
from sim import *
from engine import score_matrix

m = pd.read_pickle('../data/feats.pkl'); imp = pd.read_pickle('../data/implied.pkl'); m = m.join(imp, how='inner')
m = m[m.season >= 2019].copy()


def legs_table(seasons, hl=4, cols=('own', 'opp'), use_layer=True):
    L = luck_table(m, hl)
    o = walk(m, L, list(cols), first=2019, seasons=seasons)
    o = o[o.o_maxc.notna() & o.pm_cl.notna()].copy()
    if use_layer:
        M = score_matrix(o.alh.values, o.ala.values, RHO); M0 = score_matrix(o.ilh.values, o.ila.values, RHO)
        k = np.arange(M.shape[1]); ov = (k[:, None] + k[None, :]) > 2.5
        o['p'] = np.clip(o.pm_cl + ((M * ov).sum((1, 2)) - (M0 * ov).sum((1, 2))), .01, .99)
    else:
        o['p'] = o.pm_cl
    # both sides as candidate legs
    a = pd.DataFrame({'date': o.date, 'idx': o.index, 'side': 'O', 'p': o.p, 'price': o.o_maxc, 'win': o.over == 1, 'season': o.season})
    b = pd.DataFrame({'date': o.date, 'idx': o.index, 'side': 'U', 'p': 1 - o.p, 'price': o.u_maxc, 'win': o.over == 0, 'season': o.season})
    t = pd.concat([a, b]); t['edge'] = t.p * t.price - 1
    return t


def parlay(t, n_legs=2, min_edge=0.0, min_p=0.0, rank='edge', max_price=None):
    rows = []
    q = t[(t.edge > min_edge) & (t.p >= min_p)]
    if max_price:
        q = q[q.price <= max_price]
    for d, g in q.groupby('date'):
        g = g.sort_values(rank, ascending=False).drop_duplicates('idx')
        if len(g) < n_legs:
            continue
        L = g.head(n_legs)
        price = L.price.prod(); win = L.win.all()
        rows.append((d, L.season.iloc[0], price, win, (L.p.prod() * price) - 1))
    r = pd.DataFrame(rows, columns=['date', 'season', 'price', 'win', 'ev'])
    r['pl'] = np.where(r.win, r.price - 1, -1.0)
    return r


def report(r, label):
    if not len(r):
        print(label, 'no parlays'); return
    print(f"{label:48s} n={len(r):4d} hit={r.win.mean():.3f} avg_price={r.price.mean():5.2f} roi={r.pl.mean():+.3f} units={r.pl.sum():+7.1f} "
          f"by season {dict((int(s), round(g.pl.sum(), 1)) for s, g in r.groupby('season'))}")


if __name__ == '__main__':
    seasons = range(2020, 2023) if sys.argv[1:] != ['holdout'] else range(2023, 2027)
    T = legs_table(seasons)
    T0 = legs_table(seasons, use_layer=False)
    for nl in (2, 3):
        for me, mp, rk in [(0.0, 0, 'edge'), (0.02, 0, 'edge'), (0.0, 0.5, 'edge'), (0.0, 0.55, 'p'), (0.02, 0.5, 'p'), (0.03, 0.0, 'edge')]:
            report(parlay(T, nl, me, mp, rk), f'luck  legs={nl} edge>{me} p>={mp} rank={rk}')
            report(parlay(T0, nl, me, mp, rk), f'ctrl  legs={nl} edge>{me} p>={mp} rank={rk}')
