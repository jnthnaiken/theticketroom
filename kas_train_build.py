#!/usr/bin/env python3
"""
kas_train_build.py RAWDIR --out kas_train.parquet -- KASV1-2026-09-10, stage 2.

Turns the per-season pulls (kas_train_pull.py) into one row per STARTING batter per game, carrying the
Kasper challenger's inputs computed the way the live log computes them (calibrate.py c_* columns via
shadow_inputs.py), each one strictly from data BEFORE that game's date:

  batter vs the SP's hand, season to date   c_dmg (ISO/xwOBAcon, bip>=40)  c_hh  c_la (bell)  c_fb
  starter vs the batter's side, season to date (split if >=300 pitches, else all)
                                            c_sp_fb  c_sp_swstr  c_sp_csw
  batter run value by pitch type x SP usage c_ars
  bullpen                                   c_sp_bf  c_pen_pa  c_pen_hr  c_pen_hr_side  c_pen_top_out
                                            c_pen_air  c_pen_x
  environment                               c_wind_out  c_temp  c_rho  c_dome  c_park

Deliberate differences from live, stated so a reader doesn't have to discover them:
  * kHR does not exist before 2026 -- its weight comes from the 2026 log (kas_train_fit.py).
  * "Active pen" = pitchers with a relief appearance for the team in the prior 30 days (live: the
    active roster that day). "Best arms" = most high-leverage relief entries (inning>=7, within 3 runs)
    season to date (live: saves+holds). Both are the closest things Statcast can say.
  * Park by hand = HR/PA at the venue by batter side over the prior 3 seasons vs league, shrunk
    (live: build15's static table). If this weight earns anything, the live side should switch to it.
  * Weather = Open-Meteo ARCHIVE (reanalysis) at the ET first-pitch hour (live: historical-forecast).
"""
import argparse, glob, json, math, os, sys
import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shadow_inputs import (CF_AZ, _talias, air_density, LG_HR_BF, SHRINK_BF, PA_SLOT1, PA_STEP, SP_BF_DEF,
                           RELIEF_SHARE, OPENER_BF, D1_PITCHES_OUT, TOP_ARMS, MIN_DMG_BIP, MIN_SPLIT_PIT)

WHIFFS = {'swinging_strike', 'swinging_strike_blocked', 'foul_tip', 'missed_bunt'}
CALLED = {'called_strike'}
NON_AB = {'walk', 'intent_walk', 'hit_by_pitch', 'sac_fly', 'sac_bunt', 'catcher_interf', 'sac_fly_double_play',
          'sac_bunt_double_play', 'truncated_pa'}
HITS = {'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}
TYPES = ['FF', 'SI', 'FC', 'SL', 'ST', 'SV', 'CU', 'KC', 'CS', 'CH', 'FS', 'FO', 'SC', 'KN', 'EP']
PEN_LOOKBACK = 30
PARK_PRIOR_SEASONS = 3
PARK_SHRINK_PA = 3000
MIN_TYPE_PITCHES = 30


def cum_asof(left, right, by, cols, on='d'):
    """For each left row, the cumulative sums of `cols` in `right` (daily sums per `by`) over dates
    STRICTLY BEFORE left[on]. right: one row per (by..., on)."""
    r = right.copy()
    l = left.reset_index()
    for b in by:                                   # merge_asof refuses null `by` keys
        r[b] = r[b].astype('string').fillna('')
        l[b] = l[b].astype('string').fillna('')
    r = r.sort_values(on)
    r[cols] = r.groupby(by, observed=True)[cols].cumsum()
    l = l.sort_values(on)
    m = pd.merge_asof(l, r[by + [on] + cols], on=on, by=by, allow_exact_matches=False, direction='backward')
    return m.set_index('index').reindex(left.index)[cols]


def prep(R):
    R = R.dropna(subset=['batter', 'pitcher', 'game_pk', 'at_bat_number']).copy()
    for c in ('events', 'description', 'stand', 'p_throws', 'bb_type', 'inning_topbot', 'pitch_type', 'home_team',
              'away_team'):
        R[c] = R[c].astype('string')
    R['d'] = pd.to_datetime(R['game_date'])
    top = R['inning_topbot'].eq('Top')
    R['bat_team'] = np.where(top, R['away_team'], R['home_team'])
    R['fld_team'] = np.where(top, R['home_team'], R['away_team'])
    R['bip'] = R['bb_type'].notna().astype('int8')
    R['hh'] = (R['bip'].eq(1) & (R['launch_speed'] >= 95)).astype('int8')
    R['fb'] = R['bb_type'].eq('fly_ball').fillna(False).astype('int8')
    R['air'] = R['bb_type'].isin(['fly_ball', 'popup', 'line_drive']).fillna(False).astype('int8')
    R['gb'] = R['bb_type'].eq('ground_ball').fillna(False).astype('int8')
    R['la_v'] = np.where(R['bip'].eq(1), R['launch_angle'], np.nan)
    R['xw_v'] = np.where(R['bip'].eq(1), R['estimated_woba_using_speedangle'], np.nan)
    ev = R['events'].fillna('')
    R['pa_end'] = ev.ne('').astype('int8')
    R['ab'] = (R['pa_end'].eq(1) & ~ev.isin(NON_AB)).astype('int8')
    R['xb'] = ev.map({'double': 1, 'triple': 2, 'home_run': 3}).fillna(0).astype('int8')   # TB - H
    R['hr'] = ev.eq('home_run').astype('int8')
    R['whiff'] = R['description'].isin(WHIFFS).astype('int8')
    R['csw'] = (R['whiff'].eq(1) | R['description'].isin(CALLED)).astype('int8')
    R['one'] = np.int8(1)
    R['la_n'] = R['la_v'].notna().astype('int8'); R['la_s'] = np.nan_to_num(R['la_v'])
    R['xw_n'] = R['xw_v'].notna().astype('int8'); R['xw_s'] = np.nan_to_num(R['xw_v'])
    R = R.sort_values(['game_pk', 'at_bat_number', 'pitch_number'])
    return R


def season_rows(R, sched, W, parkfac):
    S = int(R['d'].dt.year.iloc[0])
    # ---------- starters and batter-games ----------
    first = R.groupby(['game_pk', 'fld_team'], sort=False).head(1)
    sp = first[['game_pk', 'fld_team', 'pitcher', 'p_throws']].rename(columns={'pitcher': 'sp', 'p_throws': 'sp_hand'})
    bfirst = R.groupby(['game_pk', 'bat_team', 'batter'], sort=False).head(1)[
        ['game_pk', 'd', 'bat_team', 'fld_team', 'batter', 'at_bat_number', 'home_team']]
    bfirst['slot'] = bfirst.groupby(['game_pk', 'bat_team'])['at_bat_number'].rank(method='first').astype(int)
    G = bfirst[bfirst['slot'] <= 9].copy()
    hrs = R.groupby(['game_pk', 'batter'])['hr'].max().rename('hr_out')
    G = G.join(hrs, on=['game_pk', 'batter']).merge(sp, on=['game_pk', 'fld_team'], how='left')
    vs_sp = R.merge(sp, left_on=['game_pk', 'fld_team', 'pitcher'], right_on=['game_pk', 'fld_team', 'sp'])
    side = vs_sp.groupby(['game_pk', 'batter'])['stand'].first().rename('side_vs_sp')
    anyside = R.groupby(['game_pk', 'batter'])['stand'].agg(lambda s: s.mode().iat[0]).rename('side_any')
    G = G.join(side, on=['game_pk', 'batter']).join(anyside, on=['game_pk', 'batter'])
    G['side'] = G['side_vs_sp'].fillna(G['side_any'])
    G = G.reset_index(drop=True)

    # ---------- batter vs hand, season to date ----------
    bd = R.groupby(['batter', 'p_throws', 'd'], observed=True)[['bip', 'hh', 'fb', 'la_s', 'la_n', 'xw_s', 'xw_n', 'ab', 'xb']].sum().reset_index()
    left = G[['batter', 'sp_hand', 'd']].rename(columns={'sp_hand': 'p_throws'})
    B = cum_asof(left, bd, ['batter', 'p_throws'], ['bip', 'hh', 'fb', 'la_s', 'la_n', 'xw_s', 'xw_n', 'ab', 'xb'])
    with np.errstate(divide='ignore', invalid='ignore'):
        G['c_hh'] = np.where(B['bip'] > 0, 100 * B['hh'] / B['bip'], np.nan)
        G['c_fb'] = np.where(B['bip'] > 0, 100 * B['fb'] / B['bip'], np.nan)
        la = np.where(B['la_n'] > 0, B['la_s'] / B['la_n'], np.nan)
        G['c_la'] = np.exp(-((la - 25.0) / 14.0) ** 2)
        iso = np.where(B['ab'] > 0, B['xb'] / B['ab'], np.nan)
        xwc = np.where(B['xw_n'] > 0, B['xw_s'] / B['xw_n'], np.nan)
        ok = (B['bip'] >= MIN_DMG_BIP) & (xwc > 0.05) & (iso >= 0.02) & (iso <= 0.60)
        G['c_dmg'] = np.where(ok, iso / xwc, np.nan)
    G['b_bip'] = B['bip'].values

    # ---------- starter vs side (split >= MIN_SPLIT_PIT pitches, else all) ----------
    pd_side = R.groupby(['pitcher', 'stand', 'd'], observed=True)[['one', 'whiff', 'csw', 'bip', 'fb']].sum().reset_index()
    pd_all = R.groupby(['pitcher', 'd'], observed=True)[['one', 'whiff', 'csw', 'bip', 'fb']].sum().reset_index()
    l2 = G[['sp', 'side', 'd']].rename(columns={'sp': 'pitcher', 'side': 'stand'})
    PS = cum_asof(l2, pd_side, ['pitcher', 'stand'], ['one', 'whiff', 'csw', 'bip', 'fb'])
    PA_ = cum_asof(l2[['pitcher', 'd']], pd_all, ['pitcher'], ['one', 'whiff', 'csw', 'bip', 'fb'])
    use = (PS['one'] >= MIN_SPLIT_PIT).values
    with np.errstate(divide='ignore', invalid='ignore'):
        for k, num, den, mult in (('c_sp_fb', 'fb', 'bip', 100), ('c_sp_swstr', 'whiff', 'one', 100), ('c_sp_csw', 'csw', 'one', 100)):
            a_ = np.where(PS[den] > 0, mult * PS[num] / PS[den], np.nan)
            b_ = np.where(PA_[den] > 0, mult * PA_[num] / PA_[den], np.nan)
            G[k] = np.where(use, a_, b_)

    # ---------- pitch-mix matchup: batter RV/100 by type x SP usage ----------
    R['pt'] = R['pitch_type'].where(R['pitch_type'].isin(TYPES), 'OT')
    R['rv'] = R['delta_run_exp'].fillna(0).astype('float32')
    bt = R.pivot_table(index=['batter', 'd'], columns='pt', values=['rv', 'one'], aggfunc='sum', fill_value=0, observed=True)
    bt.columns = [f"{a}_{b}" for a, b in bt.columns]; bt = bt.reset_index()
    ut = R.pivot_table(index=['pitcher', 'd'], columns='pt', values='one', aggfunc='sum', fill_value=0, observed=True)
    ut.columns = [f"u_{b}" for b in ut.columns]; ut = ut.reset_index()
    bcols = [c for c in bt.columns if c.startswith(('rv_', 'one_'))]
    ucols = [c for c in ut.columns if c.startswith('u_')]
    BT = cum_asof(G[['batter', 'd']], bt, ['batter'], bcols)
    UT = cum_asof(G[['sp', 'd']].rename(columns={'sp': 'pitcher'}), ut, ['pitcher'], ucols)
    num = np.zeros(len(G)); den = np.zeros(len(G))
    for t in TYPES:
        if f"u_{t}" not in UT or f"one_{t}" not in BT:
            continue
        u = UT[f"u_{t}"].fillna(0).values; nb = BT[f"one_{t}"].fillna(0).values; rv = BT[f"rv_{t}"].fillna(0).values
        ok = nb >= MIN_TYPE_PITCHES
        num += np.where(ok, u * 100 * rv / np.maximum(nb, 1), 0); den += np.where(ok, u, 0)
    G['c_ars'] = np.where(den > 0, num / np.maximum(den, 1e-9), np.nan)

    # ---------- appearances -> starter length, bullpen quality/availability ----------
    app = R.groupby(['game_pk', 'd', 'fld_team', 'pitcher'], sort=False).agg(
        pitches=('one', 'sum'), bf=('pa_end', 'sum'), hr=('hr', 'sum'), inn=('inning', 'first'),
        lead=('fld_score', 'first'), bs=('bat_score', 'first'), ao=('air', 'sum'), gb=('gb', 'sum'),
        hand=('p_throws', 'first'), first_ab=('at_bat_number', 'min')).reset_index()
    firstab = app.groupby(['game_pk', 'fld_team'])['first_ab'].transform('min')
    app['start'] = (app['first_ab'] == firstab).astype(int)
    app['lev'] = ((app['start'] == 0) & (app['inn'] >= 7) & ((app['lead'] - app['bs']).abs() <= 3)).astype(int)
    app['gp'] = 1
    pdaily = app.groupby(['pitcher', 'd'])[['gp', 'start', 'bf', 'hr', 'ao', 'gb', 'lev']].sum().reset_index()
    # starter expected batters faced
    SPC = cum_asof(G[['sp', 'd']].rename(columns={'sp': 'pitcher'}), pdaily, ['pitcher'], ['gp', 'start', 'bf'])
    gs, gp, bfc = SPC['start'].fillna(0).values, SPC['gp'].fillna(0).values, SPC['bf'].fillna(0).values
    with np.errstate(divide='ignore', invalid='ignore'):
        bfe = np.minimum(27.0, bfc / (gs + RELIEF_SHARE * (gp - gs)))
    G['c_sp_bf'] = np.where(gs >= 3, bfe, np.where(gp > 0, OPENER_BF, SP_BF_DEF))
    pa = PA_SLOT1 - PA_STEP * (G['slot'] - 1)
    G['c_pen_pa'] = pa - np.minimum(pa, np.maximum(0.0, (G['c_sp_bf'] - (G['slot'] - 1)) / 9.0))

    # bullpen per (fielding team, date)
    hand = app.groupby('pitcher')['hand'].agg(lambda s: s.mode().iat[0] if len(s.dropna()) else None)
    pcum = pdaily.sort_values('d').copy()
    pcum[['gp', 'start', 'bf', 'hr', 'ao', 'gb', 'lev']] = pcum.groupby('pitcher')[['gp', 'start', 'bf', 'hr', 'ao', 'gb', 'lev']].cumsum()
    pcum_by = {p: g[['d', 'gp', 'start', 'bf', 'hr', 'ao', 'gb', 'lev']].values for p, g in pcum.groupby('pitcher')}
    pitched = {(p, d): n for p, d, n in app.groupby(['pitcher', 'd'])['pitches'].sum().reset_index().itertuples(index=False)}
    rel_by_team = {t: g for t, g in app[app['start'] == 0][['fld_team', 'd', 'pitcher']].groupby('fld_team')}
    def before(p, day):
        a = pcum_by.get(p)
        if a is None:
            return None
        idx = np.searchsorted(a[:, 0].astype('datetime64[ns]'), np.datetime64(day), side='left') - 1
        return a[idx] if idx >= 0 else None
    pens = {}
    need = G[['fld_team', 'd', 'sp']].drop_duplicates()
    one_day = pd.Timedelta(days=1)
    for team, day, spid in need.itertuples(index=False):
        ra = rel_by_team.get(team)
        if ra is None:
            continue
        recent = ra[(ra['d'] < day) & (ra['d'] >= day - pd.Timedelta(days=PEN_LOOKBACK))]['pitcher'].unique()
        rel = []
        for p in recent:
            if p == spid:
                continue
            c = before(p, day)
            if c is None or c[1] == 0 or c[2] / c[1] >= 0.5:
                continue
            d1 = pitched.get((p, day - one_day)); d2 = pitched.get((p, day - 2 * one_day))
            out = bool((d1 is not None and d2 is not None) or (d1 or 0) >= D1_PITCHES_OUT)
            rel.append(dict(p=p, bf=float(c[3]), hr=float(c[4]), ao=float(c[5]), gb=float(c[6]), lev=float(c[7]),
                            hand=hand.get(p), out=out))
        if not rel:
            continue
        rate = lambda rs: (sum(r['hr'] for r in rs) + SHRINK_BF * LG_HR_BF) / (sum(r['bf'] for r in rs) + SHRINK_BF)
        avail = [r for r in rel if not r['out']] or rel
        top = sorted(rel, key=lambda r: (-r['lev'], -r['bf']))[:TOP_ARMS]
        bf_all = sum(r['bf'] for r in rel) or 1.0
        aL = [r for r in avail if r['hand'] == 'L']; aR = [r for r in avail if r['hand'] == 'R']
        ao = sum(r['ao'] for r in rel); gb = sum(r['gb'] for r in rel)
        pens[(team, day)] = dict(hr=rate(avail), hrL=rate(aL) if aL else None, hrR=rate(aR) if aR else None,
                                 shareL=sum(r['bf'] for r in rel if r['hand'] == 'L') / bf_all,
                                 top_out=sum(1 for r in top if r['out']), air=(ao / (ao + gb)) if (ao + gb) else None)
    pen_cols = {k: [] for k in ('c_pen_hr', 'c_pen_hr_side', 'c_pen_top_out', 'c_pen_air')}
    for team, day, bh in G[['fld_team', 'd', 'side']].itertuples(index=False):
        pn = pens.get((team, day))
        if not pn:
            for k in pen_cols: pen_cols[k].append(np.nan)
            continue
        pen_cols['c_pen_hr'].append(pn['hr']); pen_cols['c_pen_top_out'].append(pn['top_out'])
        pen_cols['c_pen_air'].append(pn['air'] if pn['air'] is not None else np.nan)
        if bh in ('L', 'R'):
            opp = pn['hrR'] if bh == 'L' else pn['hrL']; same = pn['hrL'] if bh == 'L' else pn['hrR']
            share = (1 - pn['shareL']) if bh == 'L' else pn['shareL']
            opp = pn['hr'] if opp is None else opp; same = pn['hr'] if same is None else same
            pen_cols['c_pen_hr_side'].append(share * opp + (1 - share) * same)
        else:
            pen_cols['c_pen_hr_side'].append(pn['hr'])
    for k, v in pen_cols.items():
        G[k] = v
    G['c_pen_x'] = G['c_pen_pa'] * G['c_pen_hr_side'].fillna(G['c_pen_hr'])

    # ---------- environment ----------
    sc = sched.set_index('game_pk')
    G = G.join(sc[['game_utc', 'venue_id', 'roof', 'condition', 'home_abbr']], on='game_pk')
    et = pd.to_datetime(G['game_utc'], utc=True).dt.tz_convert(ZoneInfo('America/New_York'))
    G['wx_key'] = et.dt.strftime('%Y-%m-%dT%H:00')
    if W is not None and len(W):
        W = W.copy(); W['venue_id'] = pd.to_numeric(W['venue_id']).astype('int64')
        G['venue_id'] = pd.to_numeric(G['venue_id']).astype('Int64')
        Wk = W.drop_duplicates(['venue_id', 'time']).set_index(['venue_id', 'time'])
        G = G.merge(Wk, left_on=['venue_id', 'wx_key'], right_index=True, how='left')
    else:
        for c in ('t', 'rh', 'p', 'ws', 'wd'):
            G[c] = np.nan
    dome = G['roof'].eq('Dome').fillna(False) | G['condition'].isin(['Dome', 'Roof Closed']).fillna(False)
    home = G['home_team'].map(lambda h: _talias(h))
    cf = home.map(CF_AZ)
    wind_out = G['ws'] * np.cos(np.radians(((G['wd'] + 180) % 360) - cf))
    G['c_dome'] = dome.astype(int)
    G['c_wind_out'] = np.where(dome, 0.0, wind_out)
    G['c_temp'] = np.where(dome, 72.0, G['t'])
    G['c_rho'] = [air_density(72.0, 50.0, p) if dm else air_density(t, rh, p)
                  for dm, t, rh, p in zip(dome, G['t'], G['rh'], G['p'])]
    G['c_rho'] = pd.to_numeric(G['c_rho'], errors='coerce')
    G['c_park'] = [parkfac.get((S, v, s), np.nan) for v, s in zip(G['venue_id'], G['side'])]

    G['season'] = S
    G = G.rename(columns={'hr_out': 'hr'})
    keep = ['season', 'd', 'game_pk', 'batter', 'bat_team', 'fld_team', 'slot', 'side', 'sp', 'sp_hand', 'hr', 'b_bip',
            'c_dmg', 'c_hh', 'c_la', 'c_fb', 'c_ars', 'c_sp_fb', 'c_sp_swstr', 'c_sp_csw', 'c_sp_bf', 'c_pen_pa',
            'c_pen_hr', 'c_pen_hr_side', 'c_pen_top_out', 'c_pen_air', 'c_pen_x', 'c_wind_out', 'c_temp', 'c_rho',
            'c_dome', 'c_park', 'venue_id']
    return G[keep]


def park_factors(pa_tables, extra_season=None):
    """(season, venue, side) -> shrunk HR/PA ratio vs league over the PRIOR PARK_PRIOR_SEASONS seasons."""
    T = pd.concat(pa_tables, ignore_index=True)       # season, venue_id, side, pa, hr
    out = {}
    for S in sorted(set(T['season'].unique()) | ({extra_season} if extra_season else set())):
        prior = T[(T['season'] < S) & (T['season'] >= S - PARK_PRIOR_SEASONS)]
        if prior.empty:
            continue
        lg = prior.groupby('side')[['pa', 'hr']].sum()
        v = prior.groupby(['venue_id', 'side'])[['pa', 'hr']].sum().reset_index()
        for vid, side, pa, hr in v.itertuples(index=False):
            if side not in lg.index or lg.loc[side, 'pa'] == 0:
                continue
            lr = lg.loc[side, 'hr'] / lg.loc[side, 'pa']
            out[(S, vid, side)] = float((hr + PARK_SHRINK_PA * lr) / (pa + PARK_SHRINK_PA) / lr)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rawdir')
    ap.add_argument('--out', default='kas_train.parquet')
    a = ap.parse_args()
    raws = sorted(glob.glob(os.path.join(a.rawdir, '**', 'raw_*.parquet'), recursive=True))
    if not raws:
        sys.exit('!! no raw_*.parquet under ' + a.rawdir)
    seasons = sorted(int(os.path.basename(f)[4:8]) for f in raws)
    find = lambda stem, S: (glob.glob(os.path.join(a.rawdir, '**', f'{stem}_{S}.parquet'), recursive=True) or [None])[0]
    # pass 1: PA tables for park factors (needs every season before any season's rows)
    pa_tables = []
    for S in seasons:
        R = pd.read_parquet(find('raw', S), columns=['game_pk', 'stand', 'events'])
        sc = pd.read_parquet(find('sched', S), columns=['game_pk', 'venue_id'])
        R = R[R['events'].notna() & R['events'].astype(str).ne('')].merge(sc, on='game_pk')
        R['hr'] = R['events'].astype(str).eq('home_run').astype(int)
        t = R.groupby(['venue_id', 'stand'], observed=True).agg(pa=('hr', 'size'), hr=('hr', 'sum')).reset_index()
        t['season'] = S
        pa_tables.append(t.rename(columns={'stand': 'side'})[['season', 'venue_id', 'side', 'pa', 'hr']])
    pf = park_factors(pa_tables, extra_season=seasons[-1] + 1)
    print(f"park factors: {len(pf)} (season, venue, side) cells", flush=True)
    # KASV1: the NEXT season's factors (prior 3 seasons) are what the live log needs for c_park2.
    nxt = seasons[-1] + 1
    names = {}
    for S in seasons[-PARK_PRIOR_SEASONS:]:
        sc = pd.read_parquet(find('sched', S), columns=['venue_id', 'venue'])
        names.update(dict(zip(sc['venue_id'], sc['venue'])))
    tbl = {}
    for (S, vid, side), f in pf.items():
        if S == nxt:
            tbl.setdefault(str(int(vid)), {'venue': names.get(vid)})[side] = round(f, 4)
    json.dump({'season': int(nxt), 'prior_seasons': PARK_PRIOR_SEASONS, 'shrink_pa': PARK_SHRINK_PA, 'venues': tbl},
              open('park_hand_next.json', 'w'), indent=1, sort_keys=True)
    print("PARKHAND_JSON " + json.dumps({'season': int(nxt), 'venues': tbl}, sort_keys=True, separators=(',', ':')), flush=True)
    out = []
    for S in seasons:
        R = prep(pd.read_parquet(find('raw', S)))
        sched = pd.read_parquet(find('sched', S))
        wf = find('wx', S)
        W = pd.read_parquet(wf) if wf else None
        G = season_rows(R, sched, W, pf)
        cov = {c: round(float(G[c].notna().mean()), 3) for c in G.columns if c.startswith('c_')}
        print(f"{S}: {len(G):,} batter-games | {int(G['hr'].sum()):,} HR ({100 * G['hr'].mean():.2f}%) | "
              f"{G['d'].nunique()} slates | coverage {cov}", flush=True)
        out.append(G)
        del R
    T = pd.concat(out, ignore_index=True)
    T.to_parquet(a.out, index=False)
    print(f"wrote {a.out}: {len(T):,} rows, {int(T['hr'].sum()):,} HR, seasons {seasons}")


if __name__ == '__main__':
    main()
