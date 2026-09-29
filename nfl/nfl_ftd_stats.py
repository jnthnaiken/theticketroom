#!/usr/bin/env python3
"""nfl_ftd_stats.py -- FTDSTATS-2026-09-29. The first-touchdown chance from FOOTBALL alone, no prices.

Owner: "stop trying to predict based on price". So nothing here reads an odds number: not the anytime
price, not the first-TD price, not the spread. Every input is from nflverse play-by-play.

THE MODEL -- a conditional logit over every candidate in a game ("which of these men scores first"),
fit on 2019-2025 regular seasons (1,700+ games whose first scorer was a skill player), inputs:
    ls        ln(his share of his team's carries+targets), last 10 games he played
    lrz       ln(his share of the team's carries+targets inside the 10 + .02), same window
    ltd       ln(his touchdowns per game + .05), same window
    RB/TE/QB  position (WR is the base)
    home      his team is at home
    team_td   his offence's TDs a game + the TDs the opponent's defence allows a game (last 12)
    team_epa  his offence's EPA a play + the EPA a play the opponent's defence allows (last 12)
    early     his offence's TDs on its first two drives + the opponent defence's, a game (last 12)
Out of sample (fit 2019-23, tested 2024-26, 548 games): the top man in each game scored first 16.8%
of the time; one man a week off the whole slate, 23% (9 of 39). The same model with the betting line
added did no better (log-loss 2.658 vs 2.659) -- the football carries what the line carries.
claude/ftdstats-2026-09-29.md.
"""
import math, os, re, unicodedata
import numpy as np, pandas as pd

NFLVERSE = 'https://github.com/nflverse/nflverse-data/releases/download'
B = dict(ls=0.7776, lrz=0.0896, ltd=0.1662, RB=-0.3412, TE=0.1291, QB=0.1224, home=0.1666,
         team_td=-0.1517, team_epa=1.6903, early=0.3124)          # conditional logit, 2019-2025
FILL = dict(o_ntd=2.582, d_ntd=2.578, o_td2=0.491, d_td2=0.489)     # league means, for a thin team history
COVER = 0.90          # share of games whose first TD goes to a listed skill player (D/ST, OL etc. take the rest)
COLS = ['game_id', 'season', 'season_type', 'week', 'posteam', 'defteam', 'play_type', 'epa', 'fixed_drive',
        'fixed_drive_result', 'rusher_player_id', 'receiver_player_id', 'yardline_100', 'touchdown', 'td_team',
        'td_player_id', 'return_touchdown', 'order_sequence', 'play_id']


def norm(s):
    s = unicodedata.normalize('NFKD', str(s))
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r'\s+(jr|jnr|sr|snr|ii|iii|iv|v)\.?\s*$', '', s)
    return re.sub(r'[^a-z]', '', s)


def _get(url, dest, cache):
    import urllib.request
    os.makedirs(cache, exist_ok=True)
    p = os.path.join(cache, dest)
    if not os.path.exists(p) or os.path.getsize(p) < 100:      # a 404 raises; this only catches an empty write
        urllib.request.urlretrieve(url, p)
    return p


def load(season, week, cache='.cache'):
    """play-by-play for the last two seasons and this one, THIS season cut to weeks before `week` (no leakage)."""
    fr = []
    for y in (season - 2, season - 1, season):        # a man back from a lost season still has his last 10
        try:
            p = _get(f'{NFLVERSE}/pbp/play_by_play_{y}.csv.gz', f'pbp{y}.csv.gz', cache)
        except Exception:
            continue
        d = pd.read_csv(p, usecols=lambda c: c in COLS, low_memory=False)
        d = d[(d.season_type == 'REG') | d.season_type.isna()]
        if y == season:
            d = d[d.week < week]
        fr.append(d)
    P = pd.concat(fr).sort_values(['season', 'week', 'game_id', 'order_sequence', 'play_id'])
    ros = []
    for y in (season - 1, season):
        try:
            p = _get(f'{NFLVERSE}/weekly_rosters/roster_weekly_{y}.csv', f'ros{y}.csv', cache)
            ros.append(pd.read_csv(p, usecols=['season', 'week', 'team', 'full_name', 'gsis_id'], low_memory=False))
        except Exception:
            pass
    R = pd.concat(ros).dropna(subset=['gsis_id']) if ros else pd.DataFrame(columns=['season', 'week', 'team', 'full_name', 'gsis_id'])
    return P, R


def tables(P):
    """player -> (s_all, s_rz, td/g) over his last 10 games; team -> offence/defence form over the last 12."""
    pl = P[P.play_type.isin(['run', 'pass']) & P.posteam.notna()].copy()
    pl['pid'] = pl.rusher_player_id.fillna(pl.receiver_player_id)
    pl['rz'] = (pl.yardline_100 <= 10).astype(int)
    gt = pl[pl.pid.notna()].groupby(['game_id', 'posteam']).agg(topp=('play_type', 'size'), trz=('rz', 'sum')).reset_index()
    pg = pl[pl.pid.notna()].groupby(['season', 'week', 'game_id', 'posteam', 'pid']).agg(
        opp=('play_type', 'size'), rz=('rz', 'sum')).reset_index().merge(gt, on=['game_id', 'posteam'])
    tds = P[(P.touchdown == 1) & P.td_player_id.notna() & (P.td_team == P.posteam) & (P.return_touchdown != 1)]
    tds = tds.groupby(['game_id', 'td_player_id']).size().rename('ptd').reset_index()
    pg = pg.merge(tds, left_on=['game_id', 'pid'], right_on=['game_id', 'td_player_id'], how='left')
    pg['ptd'] = pg.ptd.fillna(0)
    pg = pg.sort_values(['season', 'week'])
    last = pg.groupby('pid').tail(10)
    pl_t = last.groupby('pid').agg(n=('opp', 'size'), opp=('opp', 'sum'), topp=('topp', 'sum'), rz=('rz', 'sum'),
                                   trz=('trz', 'sum'), ptd=('ptd', 'mean'), team=('posteam', 'last'))
    pl_t = pl_t[pl_t.n >= 2]
    pl_t['s_all'] = pl_t.opp / pl_t.topp
    pl_t['s_rz'] = np.where(pl_t.trz > 0, pl_t.rz / pl_t.trz.replace(0, np.nan), np.nan)
    # team form
    tg = pl.groupby(['season', 'week', 'game_id', 'posteam', 'defteam']).epa.mean().rename('epa').reset_index()
    dr = pl.groupby(['game_id', 'posteam', 'fixed_drive']).fixed_drive_result.first().reset_index()
    dr = dr.sort_values(['game_id', 'posteam', 'fixed_drive'])
    dr['k'] = dr.groupby(['game_id', 'posteam']).cumcount() + 1
    td2 = dr[dr.k <= 2].assign(td=lambda x: (x.fixed_drive_result == 'Touchdown').astype(int)) \
        .groupby(['game_id', 'posteam']).td.sum().rename('td2')
    ntd = P[(P.touchdown == 1) & P.td_team.notna()].groupby(['game_id', 'td_team']).size().rename('ntd')
    tg = tg.join(td2, on=['game_id', 'posteam']).join(ntd.rename_axis(['game_id', 'posteam']), on=['game_id', 'posteam'])
    tg = tg.fillna({'td2': 0, 'ntd': 0}).sort_values(['season', 'week'])
    off = tg.groupby('posteam').tail(12).groupby('posteam').agg(n=('epa', 'size'), o_epa=('epa', 'mean'),
                                                                   o_ntd=('ntd', 'mean'), o_td2=('td2', 'mean'))
    de = tg.groupby('defteam').tail(12).groupby('defteam').agg(n=('epa', 'size'), d_epa=('epa', 'mean'),
                                                                  d_ntd=('ntd', 'mean'), d_td2=('td2', 'mean'))
    off = off[off.n >= 4]; de = de[de.n >= 4]
    return pl_t, off, de


def score(scored, season, week, cache='.cache', data=None):
    """{(match, norm name): P(first TD)} for every man in scored.json, from football alone."""
    P, R = data if data is not None else load(season, week, cache)
    pl_t, off, de = tables(P)
    R = R.assign(k=R.full_name.map(norm)).sort_values(['season', 'week'])
    idmap = {}
    for r in R.itertuples():
        idmap[(r.k, r.team)] = r.gsis_id
        idmap.setdefault((r.k, None), r.gsis_id)
    out = {}
    for m in sorted({s['match'] for s in scored}):
        away, home = m.split('-at-')
        rows = []
        for s in scored:
            if s['match'] != m:
                continue
            team = s.get('team'); opp = home if team == away else away
            k = norm(s['name'])
            pid = idmap.get((k, team)) or idmap.get((k, None))
            f = pl_t.loc[pid] if pid in pl_t.index else None
            if f is not None:
                s_all, s_rz, ptd = float(f.s_all), (float(f.s_rz) if f.s_rz == f.s_rz else 0.0), float(f.ptd)
            else:                                     # no usable history -> the board's own usage numbers
                s_all = (s.get('tchpg') or 0) / 58.5
                s_rz = min(1.0, (s.get('i10pg') or 0) / 6.0)
                ptd = 0.1
            if s_all <= 0:
                continue
            o = off.loc[team] if team in off.index else None
            d = de.loc[opp] if opp in de.index else None
            team_td = (o.o_ntd if o is not None else FILL['o_ntd']) + (d.d_ntd if d is not None else FILL['d_ntd'])
            team_epa = (o.o_epa if o is not None else 0.0) + (d.d_epa if d is not None else 0.0)
            early = (o.o_td2 if o is not None else FILL['o_td2']) + (d.d_td2 if d is not None else FILL['d_td2'])
            pos = (s.get('pos') or '').upper()
            z = (B['ls'] * math.log(min(0.7, max(0.01, s_all))) + B['lrz'] * math.log(s_rz + 0.02)
                 + B['ltd'] * math.log(ptd + 0.05) + B['RB'] * (pos == 'RB') + B['TE'] * (pos == 'TE')
                 + B['QB'] * (pos == 'QB') + B['home'] * (team == home) + B['team_td'] * team_td
                 + B['team_epa'] * team_epa + B['early'] * early)
            rows.append((norm(s['name']), z))
        if not rows:
            continue
        mx = max(z for _, z in rows)
        W = sum(math.exp(z - mx) for _, z in rows)
        for n, z in rows:
            out[(m, n)] = COVER * math.exp(z - mx) / W
    return out
