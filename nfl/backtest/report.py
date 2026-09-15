import os as _os, sys as _sys
_H = _os.path.dirname(_os.path.abspath(__file__))
for _p in (_os.path.join(_H, '..'), _os.path.join(_H, '..', '..', 'soccer')):
    if _p not in _sys.path: _sys.path.insert(0, _p)
_os.chdir(_os.path.join(_H, '..'))   # nfl/: the model files are read relative to it
OUT = lambda n: _os.path.join(_H, n)
import glob, numpy as np, pandas as pd
R = pd.concat([pd.read_pickle(f) for f in glob.glob(OUT('res_*.pkl'))], ignore_index=True)
R['med_odds'] = R.odds.apply(lambda o: float(np.median(o)))
rng = np.random.default_rng(1)
def ci(g):
    wk = g.groupby(['season', 'week']).agg(net=('net', 'sum'), stake=('stake', 'sum'))
    bs = []
    for _ in range(1000):
        s = wk.sample(len(wk), replace=True, random_state=int(rng.integers(1e9)))
        bs.append(s.net.sum() / s.stake.sum())
    return np.percentile(bs, [5, 95])
order = ['old_rawEV_nocap', 'mkt50_nocap', 'new_w50_nocap', 'new_w50_cap800', 'new_w50_cap500',
         'new_w50_cap400', 'new_w50_cap300', 'new_w100_cap500', 'new_w0_cap500']
rows = []
for season in sorted(R.season.unique()):
    for book in ['weak', 'same', 'rich', 'sharp']:
        for rule in order:
            g = R[(R.season == season) & (R.book == book) & (R.rule == rule)]
            if not len(g): continue
            lo, hi = ci(g)
            sg = g[g.legs == 1]; mg = g[g.legs > 1]
            rows.append(dict(season=season, book=book, rule=rule,
                             tickets=len(g), staked=g.stake.sum(), net=round(g.net.sum(), 1),
                             roi=g.net.sum() / g.stake.sum(), ci_lo=lo, ci_hi=hi,
                             singles_roi=sg.net.sum() / sg.stake.sum() if len(sg) else np.nan,
                             singles_hit=sg.won.mean() if len(sg) else np.nan,
                             moon_roi=mg.net.sum() / mg.stake.sum() if len(mg) else np.nan,
                             moon_cash=mg.won.mean() if len(mg) else np.nan,
                             median_leg=int(np.median(np.concatenate(g.odds.values))),
                             pct_legs_over500=float(np.mean(np.concatenate(g.odds.values) > 500))))
T = pd.DataFrame(rows)
T.to_csv(OUT('summary.csv'), index=False)
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 200)
fmt = T.copy()
for c in ['roi', 'ci_lo', 'ci_hi', 'singles_roi', 'moon_roi', 'singles_hit', 'moon_cash', 'pct_legs_over500']:
    fmt[c] = (100 * fmt[c]).round(1)
print(fmt.to_string(index=False))
