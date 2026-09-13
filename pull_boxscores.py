#!/usr/bin/env python3
"""
pull_boxscores.py — a batter-game table for FIFTEEN seasons, 2010-2024.

WHY: the Statcast table the lab/walk/sim runs use begins in 2015, because Statcast
begins in 2015. Owner asked for fifteen seasons and that is a real gap, not a quibble --
five of the fifteen simply have no launch angle or exit velocity in existence.

MLB StatsAPI boxscores go back decades and are free. They do not carry batted-ball
physics, but they carry the things that turn out to matter most: who batted, where in
the order, against which starter, in which park, and whether he went deep. The single
strongest feature in every experiment so far -- a hitter's season-to-date HR rate --
needs nothing but outcomes, so it is available for all fifteen.

So: this pulls 2010-2024 uniformly from boxscores, and daily15.py left-joins the richer
Statcast columns on top for 2015+. The model simply gets better inputs partway through
its own history, which is exactly what happened to us in real life.

    batter_id, batter, game_date, game_pk, season, team, opp, home, slot, pa, hr, sp_id

NEEDS NETWORK. Run on the Action, not the sandbox (statsapi is unreachable there).

    python3 pull_boxscores.py 2010 2024 --out boxscores_2010_2024.parquet
    python3 pull_boxscores.py 2024 2024 --workers 4      # quick sanity pass first
"""
import sys, os, json, time, argparse, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

SA = 'https://statsapi.mlb.com/api/v1'


def getj(url, tries=4):
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'theticketroom/1.0'})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if a == tries - 1:
                return None
            time.sleep(1.5 * (a + 1))
    return None


def season_games(year):
    """Every regular-season gamePk for one year. Schedule takes a date range, so this is
    a handful of calls rather than one per day."""
    out = []
    sch = getj(f'{SA}/schedule?sportId=1&gameType=R&startDate={year}-03-01&endDate={year}-12-01')
    if not sch:
        return out
    for d in sch.get('dates', []):
        for g in d.get('games', []):
            st = (g.get('status') or {}).get('abstractGameState', '')
            if st != 'Final':
                continue
            out.append((g['gamePk'], d['date']))
    return out


def one_box(pk, date):
    """One boxscore -> a row per batter who took a plate appearance.

    A batter with 0 PA is dropped: he did not have a chance to homer, and on the live
    board he would have been a VOID leg rather than a loss.
    """
    bx = getj(f'{SA}/game/{pk}/boxscore')
    if not bx:
        return []
    teams = bx.get('teams') or {}
    rows = []
    for side in ('away', 'home'):
        t = teams.get(side) or {}
        o = teams.get('home' if side == 'away' else 'away') or {}
        code = ((t.get('team') or {}).get('abbreviation') or '?')
        ocode = ((o.get('team') or {}).get('abbreviation') or '?')
        # the OPPOSING starter is the first pitcher listed for the other side
        opitch = (o.get('pitchers') or [])
        sp = opitch[0] if opitch else None
        order = {}
        for pid, pl in (t.get('players') or {}).items():
            bo = pl.get('battingOrder')
            if bo:
                try: order[pid] = int(bo) // 100
                except Exception: pass
        for pid, pl in (t.get('players') or {}).items():
            b = (pl.get('stats') or {}).get('batting') or {}
            pa = b.get('plateAppearances', 0) or 0
            if not pa:
                continue
            per = pl.get('person') or {}
            rows.append(dict(
                batter_id=per.get('id'), batter=per.get('fullName'),
                game_date=date, game_pk=pk, season=int(date[:4]),
                team=code, opp=ocode, home=1 if side == 'home' else 0,
                slot=order.get(pid, 0), pa=int(pa), hr=int(b.get('homeRuns', 0) or 0),
                sp_id=sp))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('start', type=int)
    ap.add_argument('end', type=int)
    ap.add_argument('--out', default='boxscores.parquet')
    ap.add_argument('--workers', type=int, default=12)
    a = ap.parse_args()

    import pandas as pd

    games = []
    for y in range(a.start, a.end + 1):
        g = season_games(y)
        print(f'{y}: {len(g)} final regular-season games', flush=True)
        games += g
    print(f'\ntotal {len(games)} games -> pulling boxscores with {a.workers} workers', flush=True)

    rows, done, failed = [], 0, 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(one_box, pk, d): pk for pk, d in games}
        for f in as_completed(futs):
            r = f.result()
            if not r:
                failed += 1
            rows += r
            done += 1
            if done % 2000 == 0:
                el = time.time() - t0
                print(f'  {done}/{len(games)} games, {len(rows):,} rows, '
                      f'{el:.0f}s elapsed, ~{el/done*(len(games)-done):.0f}s left', flush=True)

    df = pd.DataFrame(rows)
    df = df[df['batter_id'].notna()].copy()
    df['batter_id'] = df['batter_id'].astype('int64')
    df['sp_id'] = df['sp_id'].fillna(-1).astype('int64')
    df = df.sort_values(['game_date', 'game_pk', 'batter_id']).reset_index(drop=True)
    df.to_parquet(a.out, index=False)
    print(f'\nwrote {a.out}: {len(df):,} batter-games | '
          f'{df["hr"].sum():,} HR ({df["hr"].mean()*100:.2f}%) | '
          f'{df["game_date"].nunique():,} slates | {df["season"].min()}..{df["season"].max()}')
    if failed:
        print(f'!! {failed} boxscores failed after retries')
    for y, g in df.groupby('season'):
        print(f'  {y}: {len(g):>7,} batter-games  {g["game_date"].nunique():>4} slates  '
              f'{g["hr"].mean()*100:5.2f}% HR')


if __name__ == '__main__':
    main()
