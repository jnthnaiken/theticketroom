#!/usr/bin/env python3
"""backtest_true, stage 2 -- TRUE outcome sets per night from StatsAPI boxscores.

For each night in bt_nights.json: schedule -> every game's boxscore -> the set of bats
who took a PLATE APPEARANCE (this is what makes a DNP leg a refund instead of a loss)
plus the HR set, postponed-team codes, and a non-final count. Nights with any non-final,
non-postponed game are dropped (a backtest must not grade a night mid-play).

Needs network (StatsAPI) -- run on the Action or any online box, NOT the offline sandbox.
Names are normalized with grade_night.norm so grading joins identically to the ledger.
Writes bt_outcomes.json.
"""
import json, re, sys, urllib.request
from grade_night import norm

SA = "https://statsapi.mlb.com/api/v1"

def getj(u):
    with urllib.request.urlopen(u, timeout=30) as r:
        return json.load(r)

nights = json.load(open('bt_nights.json'))
out, dropped = {}, []
for dt in nights:
    try:
        sch = getj(f"{SA}/schedule?sportId=1&date={dt}&hydrate=team")
    except Exception as e:
        dropped.append((dt, f'schedule: {e}')); continue
    dates = sch.get('dates') or []
    games = dates[0].get('games', []) if dates else []
    played, hr, ppd, nf = set(), set(), set(), 0
    for g in games:
        st = g.get('status') or {}
        ds, ab = st.get('detailedState', ''), (st.get('abstractGameState') or '').lower()
        fin = bool(re.search('final|completed|over', ds, re.I)) or ab == 'final'
        if re.search('postpon', ds, re.I):
            for sd in ('away', 'home'):
                try: ppd.add(g['teams'][sd]['team']['abbreviation'])
                except Exception: pass
            continue
        if not fin:
            nf += 1; continue
        try:
            bx = getj(f"{SA}/game/{g['gamePk']}/boxscore")
        except Exception:
            nf += 1; continue
        for sd in ('away', 'home'):
            tp = ((bx.get('teams') or {}).get(sd) or {}).get('players') or {}
            for pl in tp.values():
                b = (pl.get('stats') or {}).get('batting') or {}
                if b.get('plateAppearances', 0) and pl.get('person'):
                    nn = norm(pl['person']['fullName'])
                    played.add(nn)
                    if b.get('homeRuns', 0): hr.add(nn)
    if nf:
        dropped.append((dt, f'{nf} game(s) not final')); continue
    out[dt] = {'p': sorted(played), 'h': sorted(hr), 'ppd': sorted(ppd), 'ng': len(games)}
    print(f'{dt}: {len(games)} games, {len(played)} PA bats, {len(hr)} HR'
          + (f', ppd {",".join(sorted(ppd))}' if ppd else ''), flush=True)

json.dump(out, open('bt_outcomes.json', 'w'))
print(f'\nwrote bt_outcomes.json: {len(out)} nights' + (f' | dropped {dropped}' if dropped else ''))
if not out: sys.exit('!! no gradable nights')
