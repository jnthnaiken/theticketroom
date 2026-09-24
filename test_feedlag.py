#!/usr/bin/env python3
"""FEEDLAG-2026-09-24 -- replayed against the real pull history, not a fixture.

A detector for "MLB is slow publishing this club" is only worth having if it fires on the nights
it was written for, so this replays the committed slate_auto revisions out of git and asserts
against what actually happened:

  * 2026-09-23 HOU@SEA -- the pull that cost a slip. Seattle posted, Houston empty, and the board
    left Daulton Varsho `projected` on a 7:40 slip until Houston sat him.
  * 2026-09-22 NYM -- the owner's first report ("some teams arent confirming at all now"),
    unposted in 12 of 44 pre-game pulls, down to 77 minutes before first pitch.

And the property that keeps it from being noise: a pull where NEITHER half is up is an early
pull, not a lag, and must never be flagged. Without that, every board in the morning is an alarm.

Run: python3 test_feedlag.py
"""
import json
import subprocess
import sys

import feedlag

FAIL = []


def check(ok, msg, got=''):
    print(('PASS  ' if ok else 'FAIL  ') + msg + (('   ' + str(got)) if got and not ok else ''))
    if not ok:
        FAIL.append(msg)


def revisions(path, every=3, limit=60):
    shas = [s for s in subprocess.run(
        ['git', 'log', '--format=%H', 'origin/main', '--', path],
        capture_output=True, text=True).stdout.strip().split('\n') if s]
    for sha in shas[::every][:limit]:
        raw = subprocess.run(['git', 'show', '%s:%s' % (sha, path)],
                             capture_output=True, text=True).stdout
        try:
            yield sha, json.loads(raw)
        except Exception:
            continue


# ---------------------------------------------------------------------------------------
# 1. the unit rule, stated directly.
G_BOTH = {'status': 'Pre-Game', 'matchup': 'HOU@SEA',
          'away': {'abbrev': 'HOU', 'confirmed': True, 'lineup': ['x'] * 9},
          'home': {'abbrev': 'SEA', 'confirmed': True, 'lineup': ['x'] * 9}}
G_NEITHER = {'status': 'Pre-Game', 'matchup': 'HOU@SEA',
             'away': {'abbrev': 'HOU', 'confirmed': False, 'lineup': []},
             'home': {'abbrev': 'SEA', 'confirmed': False, 'lineup': []}}
G_HALF = {'status': 'Pre-Game', 'matchup': 'HOU@SEA',
          'away': {'abbrev': 'HOU', 'confirmed': False, 'lineup': []},
          'home': {'abbrev': 'SEA', 'confirmed': True, 'lineup': ['x'] * 9}}
G_SHORT = {'status': 'Pre-Game', 'matchup': 'HOU@SEA',
           'away': {'abbrev': 'HOU', 'confirmed': True, 'lineup': ['x'] * 6},
           'home': {'abbrev': 'SEA', 'confirmed': True, 'lineup': ['x'] * 9}}

check(not feedlag.lagging(G_BOTH, 'away'), 'both halves posted is not a lag')
check(not feedlag.lagging(G_NEITHER, 'away'),
      'NEITHER half posted is an early pull, not a lag -- the property that stops this being noise')
check(feedlag.lagging(G_HALF, 'away'), 'one half posted and the other empty IS a lag')
check(not feedlag.lagging(G_HALF, 'home'), 'the posted half is never itself flagged')
check(feedlag.lagging(G_SHORT, 'away'),
      'a half confirmed with SIX bats is still mid-flight, not a posted card')
check(not feedlag.lagging({}, 'away') and not feedlag.lagging(G_HALF, 'sideways'),
      'a junk record or a bad side returns False rather than raising')

# a live or final game is out of scope -- the box score settles it.
for st in ('In Progress', 'Final', 'Game Over'):
    g = dict(G_HALF, status=st)
    check(feedlag.scan({'games': [g]}) == [], 'scan skips a %s game' % st)

# ---------------------------------------------------------------------------------------
# 2. the nights it was written for.
hou = [sha for sha, s in revisions('slate_auto_2026-09-23.json')
       if any(a == 'HOU' for _m, _s, a in feedlag.scan(s))]
check(bool(hou), '2026-09-23: HOU is caught in the real pulls (the night it cost a slip)',
      'no revision flagged HOU')

# NYM's lag ran through the AFTERNOON pulls, which sit deep in the log (git orders newest
# first), so the default 60-revision window walked straight past them and the first cut of this
# test went red against a detector that was working. Widen the window rather than weaken the
# assertion -- a check that only looks at the last hour of a slate would have missed the
# original report too.
nym = [sha for sha, s in revisions('slate_auto_2026-09-22.json', every=4, limit=200)
       if any(a == 'NYM' for _m, _s, a in feedlag.scan(s))]
check(bool(nym), '2026-09-22: NYM is caught in the real pulls (the first report)',
      'no revision flagged NYM')

# ---------------------------------------------------------------------------------------
# 3. and it is not flagging the whole slate. If it fired on most sides of most games the signal
#    would be worthless, so hold it to a ceiling measured off the same history.
worst = 0
for _sha, s in revisions('slate_auto_2026-09-23.json'):
    pre = [g for g in s.get('games', [])
           if str(g.get('status') or '') in ('Scheduled', 'Pre-Game', 'Warmup')]
    if not pre:
        continue
    worst = max(worst, len(feedlag.scan(s)) / float(len(pre) * 2))
check(worst <= 0.5,
      'never flags more than half the sides in a pull (worst seen %.0f%%)' % (worst * 100), worst)

print()
if FAIL:
    print('%d FAILED' % len(FAIL))
    for f in FAIL:
        print('  - ' + f)
    sys.exit(1)
print('ALL GREEN -- a lagging club is now distinguishable from a lineup that is not out yet')
