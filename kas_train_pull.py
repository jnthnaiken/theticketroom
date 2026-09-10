#!/usr/bin/env python3
"""
kas_train_pull.py SEASON -- KASV1-2026-09-10, stage 1 of the Statcast training build for the Kasper
challenger. Research only: nothing here touches the board.

Pulls ONE regular season and writes three files under --out:
  raw_<S>.parquet    every regular-season pitch, slimmed to the columns the challenger needs
  sched_<S>.parquet  one row per game: first pitch (UTC), venue id/coords/elevation/roof, the
                     stadium weather condition (to catch "Roof Closed"), home team abbreviation
  wx_<S>.parquet     hourly Open-Meteo ARCHIVE weather per venue (temp F, RH, surface pressure hPa,
                     wind mph + direction), local clock = America/New_York, same as the live feed

Runs on the Action (the sandbox has no route to Savant/StatsAPI/Open-Meteo). One season per matrix job
so no job gets near the 6-hour limit; days are cached under --cache so a re-run only fetches what is
missing.
"""
import argparse, datetime as dt, json, os, sys, time, urllib.request

import numpy as np
import pandas as pd

KEEP = ['game_date', 'game_pk', 'game_type', 'batter', 'pitcher', 'events', 'description', 'stand', 'p_throws',
        'home_team', 'away_team', 'bb_type', 'inning', 'inning_topbot', 'launch_speed', 'launch_angle',
        'estimated_woba_using_speedangle', 'at_bat_number', 'pitch_number', 'bat_score', 'fld_score',
        'delta_run_exp', 'pitch_type', 'launch_speed_angle']
WX_VARS = 'temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,wind_direction_10m'


def getj(u, tries=4, timeout=60):
    for k in range(tries):
        try:
            rq = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0 ticketroom-kastrain'})
            with urllib.request.urlopen(rq, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            if k == tries - 1:
                raise
            time.sleep(5 * (k + 1))


def pull_day(day, cache):
    fp = os.path.join(cache, f"{day}.parquet")
    if os.path.exists(fp):
        try:
            return pd.read_parquet(fp)
        except Exception:
            os.remove(fp)
    import pybaseball as pyb
    df = None
    for k in range(3):
        try:
            df = pyb.statcast(start_dt=day, end_dt=day, verbose=False)
            break
        except Exception as e:
            print(f"  ! {day}: attempt {k + 1} failed ({str(e)[:80]})", flush=True)
            time.sleep(10 * (k + 1))
    if df is None:
        return pd.DataFrame(columns=KEEP)          # not cached -> a re-run retries it
    df = pd.DataFrame(columns=KEEP) if df.empty else df[[c for c in KEEP if c in df.columns]].copy()
    os.makedirs(cache, exist_ok=True)
    df.to_parquet(fp, index=False)
    return df


def slim(df):
    df = df[df['game_type'].astype(str).eq('R')] if 'game_type' in df.columns else df
    for c in ('batter', 'pitcher', 'game_pk', 'at_bat_number', 'pitch_number', 'inning', 'bat_score', 'fld_score'):
        df[c] = pd.to_numeric(df[c], errors='coerce').astype('Int32')
    for c in ('launch_speed', 'launch_angle', 'estimated_woba_using_speedangle', 'delta_run_exp', 'launch_speed_angle'):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').astype('float32')
    for c in ('events', 'description', 'stand', 'p_throws', 'home_team', 'away_team', 'bb_type', 'inning_topbot',
              'pitch_type'):
        df[c] = df[c].astype('string').astype('category')
    df['game_date'] = pd.to_datetime(df['game_date']).dt.date.astype('string')
    return df.drop(columns=[c for c in ('game_type',) if c in df.columns])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('season', type=int)
    ap.add_argument('--cache', default='kas_cache')
    ap.add_argument('--out', default='kasraw')
    a = ap.parse_args()
    S = a.season
    os.makedirs(a.out, exist_ok=True)
    cache = os.path.join(a.cache, str(S))

    # ---- schedule: which days, which venues ----
    sj = getj(f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&gameType=R&season={S}"
              f"&hydrate=weather,team,venue(location,fieldInfo)")
    rows = []
    for d in sj.get('dates') or []:
        for g in d.get('games') or []:
            v = g.get('venue') or {}
            loc = (v.get('location') or {})
            co = loc.get('defaultCoordinates') or {}
            st = (g.get('status') or {})
            rows.append({'game_pk': g.get('gamePk'), 'official_date': g.get('officialDate') or d.get('date'),
                         'game_utc': g.get('gameDate'), 'state': st.get('abstractGameState'),
                         'venue_id': v.get('id'), 'venue': v.get('name'), 'lat': co.get('latitude'),
                         'lon': co.get('longitude'), 'elev': loc.get('elevation'),
                         'roof': (v.get('fieldInfo') or {}).get('roofType'),
                         'condition': (g.get('weather') or {}).get('condition'),
                         'home_abbr': ((g.get('teams') or {}).get('home', {}).get('team') or {}).get('abbreviation')})
    sched = pd.DataFrame(rows)
    sched = sched[sched['state'].eq('Final')].drop_duplicates('game_pk')
    sched.to_parquet(os.path.join(a.out, f"sched_{S}.parquet"), index=False)
    days = sorted(sched['official_date'].unique())
    print(f"{S}: {len(sched)} final games over {len(days)} days, {sched['venue_id'].nunique()} venues", flush=True)

    # ---- weather: one archive call per chunk of venues, whole season ----
    V = sched.dropna(subset=['lat', 'lon']).drop_duplicates('venue_id')[['venue_id', 'lat', 'lon']].values.tolist()
    start, end = days[0], days[-1]
    wx = []
    for i in range(0, len(V), 8):
        ch = V[i:i + 8]
        u = ("https://archive-api.open-meteo.com/v1/archive?latitude=" + ','.join(str(x[1]) for x in ch) +
             "&longitude=" + ','.join(str(x[2]) for x in ch) + f"&hourly={WX_VARS}&temperature_unit=fahrenheit"
             f"&wind_speed_unit=mph&timezone=America%2FNew_York&start_date={start}&end_date={end}")
        try:
            j = getj(u, timeout=120)
        except Exception as e:
            print(f"  ! weather chunk {i}: {str(e)[:100]}", flush=True)
            continue
        locs = j if isinstance(j, list) else [j]
        for (vid, _, _), loc in zip(ch, locs):
            h = loc.get('hourly') or {}
            if not h.get('time'):
                continue
            wx.append(pd.DataFrame({'venue_id': vid, 'time': h['time'], 't': h.get('temperature_2m'),
                                    'rh': h.get('relative_humidity_2m'), 'p': h.get('surface_pressure'),
                                    'ws': h.get('wind_speed_10m'), 'wd': h.get('wind_direction_10m')}))
        time.sleep(1)
    if wx:
        W = pd.concat(wx, ignore_index=True)
        for c in ('t', 'rh', 'p', 'ws', 'wd'):
            W[c] = pd.to_numeric(W[c], errors='coerce').astype('float32')
        W.to_parquet(os.path.join(a.out, f"wx_{S}.parquet"), index=False)
        print(f"  weather: {W['venue_id'].nunique()} venues, {len(W):,} hourly rows", flush=True)

    # ---- pitches ----
    parts, n = [], 0
    t0 = time.time()
    for i, day in enumerate(days, 1):
        df = pull_day(day, cache)
        if not df.empty:
            parts.append(slim(df.copy()))
            n += len(df)
        if i % 20 == 0 or i == len(days):
            print(f"  {i}/{len(days)} days | {n:,} pitches | {time.time() - t0:.0f}s", flush=True)
    if not parts:
        sys.exit("no pitches pulled")
    R = pd.concat(parts, ignore_index=True)
    for c in ('events', 'description', 'stand', 'p_throws', 'home_team', 'away_team', 'bb_type', 'inning_topbot',
              'pitch_type'):
        R[c] = R[c].astype('string').astype('category')
    R.to_parquet(os.path.join(a.out, f"raw_{S}.parquet"), index=False)
    miss = sorted(set(days) - set(R['game_date'].unique()))
    print(f"{S}: wrote {len(R):,} pitches | {R['game_pk'].nunique()} games | days with no pitches: {len(miss)}"
          f"{' e.g. ' + ', '.join(miss[:5]) if miss else ''}", flush=True)


if __name__ == '__main__':
    main()
