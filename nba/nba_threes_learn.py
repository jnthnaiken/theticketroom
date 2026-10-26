#!/usr/bin/env python3
"""nba_threes_learn.py -- DOWNTOWN-2026-10-26. Roll the threes model state forward one finished day at a time from
nba.com box scores (threes, minutes, starters), exactly like seed_state.py's tail. A day is learned only once every
game on it is final; never half a day.   python3 nba_threes_learn.py threes_state.json"""
import datetime, json, sys
import nba_threes as T
import nba_nbacom as N

path = sys.argv[1]
try:
    st = T.State(json.load(open(path, encoding='utf-8')))
except Exception as e:
    print(f'threes learn: no state ({e})'); sys.exit(0)
through = st.meta.get('through')
if not through:
    sys.exit(0)
yday = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=10)).date()
d = datetime.date.fromisoformat(through) + datetime.timedelta(days=1)
n = 0
while d <= yday and n < 10:
    ds = d.isoformat()
    try:
        sb = N.scoreboard(ds)
    except Exception as e:
        print(f'threes learn {ds}: scoreboard unreachable ({str(e)[:80]})'); break
    if any(not r[4] for r in sb):
        print(f'threes learn {ds}: not every game final yet'); break
    day = []
    try:
        for gid, away, home, *_ in sb:
            for b in N.parse(N.summary(gid))['box']:
                if b['played']:
                    day.append(dict(pid=b['pid'], name=b['name'], team=b['team'], opp=home if b['team'] == away else away,
                                    gid=gid, tpa=b['tpa'], tpm=b['tpm'], mins=b['mins'], started=b['started']))
    except Exception as e:
        print(f'threes learn {ds}: box unreachable ({str(e)[:80]})'); break
    if day: st.update_day(day)
    st.meta['through'] = ds; n += 1
    print(f'threes learn {ds}: {len(sb)} games, {len(day)} player-games')
    d += datetime.timedelta(days=1)
if n:
    json.dump(st.dump(), open(path, 'w'), separators=(',', ':'))
