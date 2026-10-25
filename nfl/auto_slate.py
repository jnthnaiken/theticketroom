#!/usr/bin/env python3
"""AUTONFL-2026-10-24. Pick the next NFL slate that has no committed atd.psv and write its fixtures.json.

    python3 auto_slate.py [--date YYYY-MM-DD]      # prints date=... season=... week=... (GITHUB_OUTPUT lines)

A slate is one (gameday, weekday) of the regular season, exactly what mkfixtures.build() makes for the
browser flow. Only a gameday from today (ET) through tomorrow is taken, so the night-before run builds
tomorrow and a morning run fills anything missed. Prints nothing when there is nothing to do.
"""
import argparse, datetime, json, os, sys
from zoneinfo import ZoneInfo
import nfl_stats, mkfixtures

ap = argparse.ArgumentParser(); ap.add_argument('--date'); a = ap.parse_args()
today = datetime.datetime.now(ZoneInfo('America/New_York')).date()
s = nfl_stats.load_sched()
s = s[(s.game_type == 'REG')]
days = sorted(set(s.gameday))
if a.date:
    want = [a.date]
else:
    want = [d for d in days if today <= datetime.date.fromisoformat(d) <= today + datetime.timedelta(days=1)
            and not os.path.exists(f'slates/{d}/atd.psv')]
if not want:
    print('nothing to fetch', file=sys.stderr); sys.exit(0)
d = want[0]
g = s[s.gameday == d].iloc[0]
fx, _ = mkfixtures.build(int(g.season), int(g.week), weekday=str(g.weekday))
assert fx['date'] == d, (fx['date'], d)
os.makedirs(f'slates/{d}', exist_ok=True)
json.dump(fx, open(f'slates/{d}/fixtures.json', 'w'), indent=1)
print(f'{d} {fx["weekday"]} week {fx["week"]}: {len(fx["matches"])} games', file=sys.stderr)
print(f'date={d}')
