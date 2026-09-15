"""Stage 1: weekly player tables 2021-2025 with outcomes. No prices anywhere."""
import os as _os, sys as _sys
_H = _os.path.dirname(_os.path.abspath(__file__))
for _p in (_os.path.join(_H, '..'), _os.path.join(_H, '..', '..', 'soccer')):
    if _p not in _sys.path: _sys.path.insert(0, _p)
_os.chdir(_os.path.join(_H, '..'))   # nfl/: the model files are read relative to it
OUT = lambda n: _os.path.join(_H, n)

import functools, sys, pandas as pd, numpy as np
import nfl_stats as S
S.load_pbp = functools.lru_cache(None)(S.load_pbp)
S.load_sched = functools.lru_cache(None)(S.load_sched)
S.load_roster = functools.lru_cache(None)(S.load_roster)
_ld = S.load_depth
@functools.lru_cache(None)
def _depth_asof(season, before=None):
    # no peeking: the depth chart as it stood before the season opened (the live board only ever
    # applies it to week-1 'prior' rows, and the live build sees the pre-season chart)
    return _ld(season, before=pd.Timestamp(f'{season}-09-01', tz='UTC'))
S.load_depth = _depth_asof

@functools.lru_cache(None)
def status(season):
    p = S._get(f'{S.NFLVERSE}/weekly_rosters/roster_weekly_{season}.csv', f'ros{season}.csv')
    r = pd.read_csv(p, usecols=['week', 'gsis_id', 'status'], low_memory=False)
    return r.dropna(subset=['gsis_id']).drop_duplicates(['week', 'gsis_id'])

rows = []
for season in [int(x) for x in sys.argv[1:]]:
    pbp = S.load_pbp(season)
    t = S.touch_rows(pbp)
    for week in range(1, 19):
        try:
            b = S.build(season, week)
        except SystemExit:
            continue
        tw = t[t.week == week].groupby('pid').agg(td_game=('td', 'max'), tch_game=('td', 'size'),
                                                   i10_game=('i10', 'sum')).reset_index()
        # anytime TD also counts a QB rushing TD -- touch_rows keeps rushers, so it is in td
        b = b.merge(tw, on='pid', how='left')
        st = status(season); st = st[st.week == week][['gsis_id', 'status']].rename(columns={'gsis_id': 'pid'})
        b = b.merge(st, on='pid', how='left')
        b['td_game'] = b.td_game.fillna(0).astype(int)
        b['tch_game'] = b.tch_game.fillna(0).astype(int)
        b['i10_game'] = b.i10_game.fillna(0).astype(int)
        b['played'] = (b.tch_game > 0) | (b.status == 'ACT')
        b['season'] = season; b['week'] = week
        rows.append(b)
        print(season, week, len(b), int(b.td_game.sum()), flush=True)
D = pd.concat(rows, ignore_index=True)
D.to_pickle(OUT(f'weeks_{"_".join(sys.argv[1:])}.pkl'))
print(D.shape)
