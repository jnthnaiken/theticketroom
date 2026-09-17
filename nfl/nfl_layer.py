#!/usr/bin/env python3
"""nfl_layer.py -- NFLLAYER-2026-09-17. The soccer layered scorer model, ported to anytime TD, and
the BLEND of it with the live usage model (nfl_model.json) that the scorer now uses as p_model.

Owner: "can you run the same algorithm you did with soccer on football?" -> "the two combined
clearly seems to be the way to go" -> "yes" (ship it for DET@BUF, 2026-09-17).

THE LAYERED MODEL

    lambda = team TDs expected tonight            a + b * implied team total
           x his share of the team's work          EW touch share (carries + targets), half-life 8
                                                   games, shrunk (K=1) toward half his position's mean
           x how dangerous his touches are          EW xTD per touch, half-life 17, shrunk (K=60 touches)
             relative to the league                 toward his position's mean, / league mean
    P_layer = 1 - exp(-lambda), calibrated

  xTD per touch = P(TD | carry or target, yards to goal), the lookup below, fitted on 2016-18
  play-by-play only. The off-season counts as OFF weeks on the decay clock, so last season carries in.

THE BLEND (what the board uses)

    p_model = sigmoid(B0 + B1 * logit(p_live) + B2 * log(lambda))

  p_live is the old p_model exactly as before (model_prob, team-normalised, wind trim applied).

MEASURED (research: scratchpad nflm/, walk-forward, the live backtest's own population, 37,675
player-games 2021-25; nfl_model.json was fit on 2021-24 so 2025 is the only clean live season):

                         AUC all   AUC 2025   log loss 22-25   top-8/week hit
    live model            .757      .766         .371            55.7%
    layered model         .754      .763         .357            56.9%
    blend (fit 22-24)       -       .771         .356 (2025)
  Both terms significant in every season and in 2025 alone (p < .001). Inside the likeliest 40%
  (the band the board bets) the layered model out-ranks the live one in all five seasons.
  Real prices, 2026 week 1 (219 priced, 53 scorers): layered AUC .741, price .736, board TOTAL .508.
  NOT shown: that any of this is profitable. The betting backtest has not been re-run on it.

NFL_LAYER=0 turns the blend off (p_model reverts to the live model alone).
"""
import os, numpy as np, pandas as pd

HL, HQ, K, KQ, OFF = 8.0, 17.0, 1.0, 60.0, 6
BANDS = [0, 1, 2, 3, 5, 7, 10, 15, 20, 30, 40, 60, 80, 100]
XTD = {  # P(TD) by yard band (0,1] (1,2] (2,3] (3,5] (5,7] (7,10] (10,15] ... (80,100], 2016-18
    'r': [0.5505, 0.4430, 0.3462, 0.2536, 0.1591, 0.1111, 0.0588, 0.0281, 0.0177, 0.0047, 0.0048, 0.0024, 0.0017],
    't': [0.5704, 0.4612, 0.4422, 0.3959, 0.3545, 0.2503, 0.1689, 0.1155, 0.0639, 0.0320, 0.0123, 0.0065, 0.0040],
}
POSQ = {'QB': 0.03905, 'RB': 0.03465, 'TE': 0.05408, 'WR': 0.04342}   # xTD per touch, 2016-25
LGQ = 0.04028
TSP = {'QB': 0.06357, 'RB': 0.17621, 'TE': 0.05995, 'WR': 0.08566}    # mean touch share when active
TEAM = (-0.64645, 0.13540)          # touch TDs per team-game = a + b * implied total, 2016-25
CAL = (0.22318, 1.29650)            # P_layer calibration, fit 2022-25
BLEND = (0.86971, 0.46295, 0.97466) # B0, B1 (logit p_live), B2 (log lambda), fit 2022-25

COLS = ['game_id', 'season', 'season_type', 'week', 'posteam', 'yardline_100', 'rush_attempt',
        'pass_attempt', 'rush_touchdown', 'pass_touchdown', 'rusher_player_id', 'receiver_player_id',
        'two_point_attempt']

lg = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))
sg = lambda x: 1 / (1 + np.exp(-x))
clock = lambda s, w: (s - 2016) * (18 + OFF) + w


def _pbp(season, required):
    import nfl_stats as S
    try:
        p = S._get(f'{S.NFLVERSE}/pbp/play_by_play_{season}.csv.gz', f'pbp{season}.csv.gz')
        d = pd.read_csv(p, usecols=COLS, low_memory=False)
    except Exception:
        if required:
            raise
        return None
    return d[(d.season_type == 'REG') & (d.two_point_attempt.fillna(0) == 0)]


_GAMES = {}


def games(season, week):
    """One row per player-game with his touch share and xTD, every game before (season, week).

    CACHED per (season, week): one live build scores once, but the backtest replays 115 slates x
    several rules through score(), and re-reading four 20MB play-by-play files each time turned a
    ten-minute sweep into hours."""
    if (season, week) in _GAMES:
        return _GAMES[(season, week)]
    parts = []
    for s in range(season - 3, season + 1):
        d = _pbp(s, required=(s < season))
        if d is None or not len(d):
            continue
        if s == season:
            d = d[d.week < week]
        for kind, m, pid, td in (('r', d.rush_attempt == 1, 'rusher_player_id', 'rush_touchdown'),
                                 ('t', d.pass_attempt == 1, 'receiver_player_id', 'pass_touchdown')):
            x = d[m & d[pid].notna() & d.yardline_100.notna()]
            band = pd.cut(x.yardline_100.clip(1, 99), BANDS, labels=False).astype(int)
            parts.append(pd.DataFrame({'game_id': x.game_id, 'season': x.season, 'week': x.week,
                                       'team': x.posteam, 'pid': x[pid],
                                       'xtd': np.array(XTD[kind])[band.values]}))
    if not parts:
        _GAMES[(season, week)] = pd.DataFrame(columns=['pid', 't', 'tshare', 'xtd', 'tch'])
        return _GAMES[(season, week)]
    T = pd.concat(parts, ignore_index=True)
    g = T.groupby(['season', 'week', 'game_id', 'team', 'pid']).agg(xtd=('xtd', 'sum'), tch=('xtd', 'size')).reset_index()
    g['tshare'] = g.tch / g.groupby(['game_id', 'team']).tch.transform('sum')
    g['t'] = clock(g.season, g.week)
    _GAMES[(season, week)] = g
    return g


def lam(d, season, week, hist=None):
    """lambda for every row of a nfl_stats.build() frame (needs pid, pos, imp)."""
    g = games(season, week) if hist is None else hist
    t = clock(season, week)
    g = g[g.t < t]
    w8 = np.exp(-np.log(2) / HL * (t - g.t))
    w17 = np.exp(-np.log(2) / HQ * (t - g.t))
    st = pd.DataFrame({'pid': g.pid, 'S_ts': g.tshare * w8, 'W': w8, 'S_x': g.xtd * w17, 'S_tch': g.tch * w17})
    st = st.groupby('pid').sum()
    x = d[['pid']].join(st, on='pid').fillna(0)
    pos = d.pos.where(d.pos.isin(list(POSQ)), 'WR')
    ts = (x.S_ts + K * pos.map(TSP) * 0.5) / (x.W + K)
    qn = (x.S_x + KQ * pos.map(POSQ)) / (x.S_tch + KQ)
    tdx = (TEAM[0] + TEAM[1] * d.imp).clip(0.5, 6)
    return (tdx * ts * qn / LGQ).clip(1e-4, 5).values


def apply(d, season, week):
    """d already carries p_model (live model x wind). Adds lam / p_layer / p_live and replaces
    p_model with the blend."""
    if os.environ.get('NFL_LAYER', '1') == '0':
        print('NFLLAYER: off (NFL_LAYER=0) -- live usage model alone')
        return d
    d = d.copy()
    L = lam(d, season, week)
    d['lam'] = L
    d['p_layer'] = sg(CAL[0] + CAL[1] * lg(1 - np.exp(-L)))
    d['p_live'] = d.p_model
    d['p_model'] = sg(BLEND[0] + BLEND[1] * lg(d.p_live) + BLEND[2] * np.log(L)).clip(0.005, 0.90)
    top = d.sort_values('p_model', ascending=False).head(6)
    print('NFLLAYER blend: ' + ', '.join(f'{r.full_name} {r.p_model:.0%} (live {r.p_live:.0%}, layer {r.p_layer:.0%})'
                                         for _, r in top.iterrows()))
    return d
