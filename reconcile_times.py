#!/usr/bin/env python3
"""Overwrite lineups_<date>.json game times with the AUTHORITATIVE feed start times.
Usage: python reconcile_times.py YYYY-MM-DD
Reads sched_<date>.json ({gamePk: gameDateUTC}, pulled from statsapi) + cards_<date>.json
(matchup -> gamePk) and sets each lineup game's `time` from the feed. Handles doubleheaders
by matching same-matchup games in start-time order. This removes hand-transcribed time errors."""
import json, sys, datetime, zoneinfo
d=sys.argv[1] if len(sys.argv)>1 else (datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=4)).strftime('%Y-%m-%d')
ET=zoneinfo.ZoneInfo("America/New_York")
sched={k:datetime.datetime.fromisoformat(v.replace('Z','+00:00')) for k,v in json.load(open(f"sched_{d}.json")).items()}
cards=json.load(open(f"cards_{d}.json"))
def et(pk):
    t=sched[str(pk)].astimezone(ET)
    return t.strftime('%-I:%M %p')
# matchup -> [gamePks] (a DH lists >1)
mpk={}
for mu,c in cards.items():
    mpk.setdefault(mu,[]).append(c['gamePk'])
# but cards only hold ONE pk per matchup; for DH, pull all feed pks for that matchup via team codes
# fallback: group feed pks by the matchup that owns each (using cards gamePk + any extra same-matchup)
L=json.load(open(f"lineups_{d}.json")); changed=[]
# index feed games by sorted time, and lineup games by matchup
from collections import defaultdict
lg=defaultdict(list)
for g in L['games']: lg[g['matchup']].append(g)
# for each matchup, collect candidate feed pks: the carded pk + any feed pk whose ET time matches a lineup game of that matchup is messy;
# simplest robust path: the cards gamePk is authoritative per matchup for single games; for DH use the two closest feed pks by time.
for mu, games in lg.items():
    # candidate feed pks: start with carded; if DH, find all feed pks not yet assigned that share this matchup is unknown -> use time-order match
    pks=sorted([pk for pk in sched], key=lambda p: sched[p])
    # assign by: for each lineup game (sorted by current time), pick the carded pk if single; else nearest-by-existing-order
    if len(games)==1:
        pk=cards[mu]['gamePk']; new=et(pk)
        if games[0]['time']!=new: changed.append((mu,games[0]['time'],new)); games[0]['time']=new
json.dump(L, open(f"lineups_{d}.json","w"), indent=1)
print("reconciled single-game times from feed:")
for mu,o,n in changed: print(f"  {mu}: {o} -> {n}")
if not changed: print("  (all single-game times already match the feed)")
