#!/usr/bin/env python3
"""seed_state.py -- DOWNTOWN-2026-10-26. Build nba/threes_state.json: replay 2022-23..2025-26 play-by-play through
nba_threes.State.update_day (the same walk-forward the research ran), then this season's finished games from nba.com.

    python3 seed_state.py pbp_dir sd_dir ../../threes_state.json 2026-10-20
"""
import datetime, glob, json, os, sys
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
import nba_threes as T
import nba_nbacom as N
from boxlib import minutes_of

PBP, SD, OUT, CUR = sys.argv[1:5]
games, names = {}, {}
for f in sorted(glob.glob(os.path.join(SD, '**', 'shotdetail_*.csv'), recursive=True)):
    d = pd.read_csv(f, usecols=['GAME_ID', 'GAME_DATE', 'HTM', 'VTM', 'PLAYER_ID', 'PLAYER_NAME'], low_memory=False)
    for gid, gd, h, v in d.drop_duplicates('GAME_ID')[['GAME_ID', 'GAME_DATE', 'HTM', 'VTM']].itertuples(index=False):
        s = str(int(gd)); games[int(gid)] = (f'{s[:4]}-{s[4:6]}-{s[6:]}', h, v)
    for pid, nm in d.drop_duplicates('PLAYER_ID')[['PLAYER_ID', 'PLAYER_NAME']].itertuples(index=False):
        names[int(pid)] = nm
rows = []
for f in sorted(glob.glob(os.path.join(PBP, '**', 'nbastatsv3_*.csv'), recursive=True)):
    cols = pd.read_csv(f, nrows=0).columns
    want = [c for c in ('gameId', 'personId', 'teamTricode', 'isFieldGoal', 'shotValue', 'shotResult', 'description', 'period',
                        'clock', 'actionType', 'subType', 'actionId', 'actionNumber', 'playerName') if c in cols]
    d = pd.read_csv(f, usecols=want, low_memory=False)
    d = d[(d.personId > 0) & d.teamTricode.notna() & (d.teamTricode != '')]
    three = (d.shotValue == 3) if 'shotValue' in d else d.description.astype(str).str.contains('3PT')
    d['a3'] = ((d.isFieldGoal == 1) & three).astype(int)
    d['m3'] = (d.a3 == 1) & (d.shotResult == 'Made')
    agg = d.groupby(['gameId', 'personId']).agg(team=('teamTricode', 'first'), att=('a3', 'sum'), made=('m3', 'sum')).reset_index()
    agg = agg.merge(minutes_of(d), on=['gameId', 'personId'], how='left')
    rows.append(agg)
    print(os.path.basename(f), len(agg), flush=True)
B = pd.concat(rows, ignore_index=True)
B = B[B.gameId.isin(games)]
B['date'] = B.gameId.map(lambda g: games[g][0])
B['opp'] = [games[g][2] if games[g][1] == t else games[g][1] for g, t in zip(B.gameId, B.team)]
st = T.State()
for date, day in B.sort_values(['date', 'gameId']).groupby('date', sort=True):
    st.update_day([dict(pid=str(r.personId), name=names.get(r.personId), team=r.team, opp=r.opp, gid=str(r.gameId),
                        tpa=int(r.att), tpm=int(r.made), mins=float(r.mins or 0), started=bool(r.started))
                   for r in day.itertuples(index=False)])
    st.meta['through'] = date
print('history through', st.meta['through'], 'players', len(st.pl))
# this season from nba.com
d = datetime.date.fromisoformat(CUR)
today = datetime.date.today()
while d < today:
    ds = d.isoformat()
    try:
        sb = [r for r in N.scoreboard(ds) if r[4]]
    except Exception as e:
        print('  ', ds, 'scoreboard', e); sb = []
    day = []
    for gid, away, home, *_ in sb:
        try:
            g = N.parse(N.summary(gid))
        except Exception as e:
            print('  ', ds, gid, e); continue
        for b in g['box']:
            if not b['played']: continue
            day.append(dict(pid=b['pid'], name=b['name'], team=b['team'], opp=home if b['team'] == away else away,
                            gid=gid, tpa=b['tpa'], tpm=b['tpm'], mins=b['mins'], started=b['started']))
    if day:
        st.update_day(day); st.meta['through'] = ds
        print('  ', ds, len(sb), 'games', len(day), 'player-games', flush=True)
    d += datetime.timedelta(days=1)
json.dump(st.dump(), open(OUT, 'w'), separators=(',', ':'))
print('wrote', OUT, 'through', st.meta['through'], os.path.getsize(OUT), 'bytes')
