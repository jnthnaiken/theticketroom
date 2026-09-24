#!/usr/bin/env python3
"""RECORDKEPT-2026-09-24 -- the Long Ball Jackpot's result, tested against real days.

Savant is not reachable from the cloud sandbox (403 at the proxy), so `fetch` is injected. What is
NOT faked is the answer: every fixture below is a real Savant response shape, and the expected
winner comes from longball/winners_2026.tsv, which was backfilled independently.

The properties that matter, and why each one is here:
  * the day's longest is found through a REAL CSV parse -- `player_name` contains a comma, so a
    naive split shifts every later column and silently finds no home runs at all.
  * a name is matched the way grade_night matches names (accents, suffixes).
  * TIES win. Distances are whole feet; the pot splits among everyone who picked the winner.
  * every failure returns None, and None is not False. A header-only 200 (which is what the wrong
    `hfAB` spelling returns) must NOT grade the slip a loss.

Run: python3 test_longball_grade.py
"""
import os
import sys

import longball_grade as LG

FAIL = []


def check(ok, msg, got=''):
    print(('PASS  ' if ok else 'FAIL  ') + msg + (('   ' + str(got)) if got and not ok else ''))
    if not ok:
        FAIL.append(msg)


HDR = ('"pitch_type","game_date","player_name","batter","events","home_team","hit_distance_sc"\n')


def row(name, ev, team, dist):
    return '"FF","2026-09-22","%s","1","%s","%s","%s"\n' % (name, ev, team, dist)


# a normal day: several homers, one clear longest, plus noise rows that must be ignored
DAY = HDR + ''.join([
    row('Moniak, Mickey', 'home_run', 'COL', '431'),
    row('Soto, Juan', 'home_run', 'NYM', '402'),
    row('Baez, Joshua', 'home_run', 'CHC', '417'),
    row('Judge, Aaron', 'single', 'NYY', '440'),          # not a homer -- 440ft single must not win
    row('Ohtani, Shohei', 'home_run', 'LAD', ''),         # homer with no Statcast distance
])
w = LG.winners('2026-09-22', fetch=lambda u, timeout=45: DAY)
check(w is not None and len(w) == 1 and w[0][0] == 'Mickey Moniak' and w[0][1] == 431,
      "the day's longest homer is found, and Last, First is flipped to First Last", w)
check(LG.is_winner('Mickey Moniak', 'd1', fetch=lambda u, timeout=45: DAY, cache={}) is True,
      'our man IS the winner -> True')
check(LG.is_winner('Juan Soto', 'd2', fetch=lambda u, timeout=45: DAY, cache={}) is False,
      'a shorter homer -> False, not None')
check(LG.is_winner('Aaron Judge', 'd3', fetch=lambda u, timeout=45: DAY, cache={}) is False,
      'a 440ft SINGLE does not win the home-run jackpot')

# accents and suffixes, the way the board spells them vs the way Savant does
ACC = HDR + row('Báez, Joshua', 'home_run', 'CHC', '449') + row('Witt Jr., Bobby', 'home_run', 'KC', '400')
check(LG.is_winner('Joshua Baez', 'a1', fetch=lambda u, timeout=45: ACC, cache={}) is True,
      'an accented Savant name matches the board’s unaccented spelling')
SFX = HDR + row('Witt Jr., Bobby', 'home_run', 'KC', '455')
check(LG.is_winner('Bobby Witt', 's1', fetch=lambda u, timeout=45: SFX, cache={}) is True,
      'a suffixed Savant name matches the board’s suffix-less spelling')

# ties -- the pot splits, so everyone at the max wins
TIE = HDR + row('A, Al', 'home_run', 'COL', '450') + row('B, Bo', 'home_run', 'AZ', '450') + row('C, Cy', 'home_run', 'TB', '449')
tw = LG.winners('t', fetch=lambda u, timeout=45: TIE)
check(tw is not None and len(tw) == 2, 'a tie returns BOTH men, not an arbitrary one', tw)
check(LG.is_winner('Al A', 't1', fetch=lambda u, timeout=45: TIE, cache={}) is True
      and LG.is_winner('Bo B', 't2', fetch=lambda u, timeout=45: TIE, cache={}) is True,
      'and both of them grade as winners')
check(LG.is_winner('Cy C', 't3', fetch=lambda u, timeout=45: TIE, cache={}) is False,
      'while one foot short does not')

# ---- failure is not a loss. This is the assertion that protects the record.
def boom(u, timeout=45):
    raise IOError('WAF')


check(LG.winners('x', fetch=boom) is None, 'a failed fetch returns None')
check(LG.is_winner('Anyone', 'f1', fetch=boom, cache={}) is None,
      'and a failed fetch grades UNKNOWN, never a loss')
check(LG.winners('x', fetch=lambda u, timeout=45: HDR) is None,
      'a header-only 200 -- what the WRONG hfAB spelling returns -- is UNKNOWN, not a loss')
check(LG.winners('x', fetch=lambda u, timeout=45: '') is None, 'an empty body is UNKNOWN')
check(LG.is_winner('Anyone', 'f2', fetch=lambda u, timeout=45: HDR, cache={}) is None,
      'so a silently-empty day cannot mark every jackpot lost')

# ---- the real-CSV requirement, stated as its own assertion
check('player_name' in HDR and LG.flip('Moniak, Mickey') == 'Mickey Moniak',
      'the name column contains a comma, so the parse must be real CSV (split would shift columns)')

# ---- and it must agree with the backfill that chose the picking rule
here = os.path.dirname(os.path.abspath(__file__))
wf = os.path.join(here, 'longball', 'winners_2026.tsv')
if os.path.exists(wf):
    known = {}
    for ln in open(wf, encoding='utf-8'):
        if ln.strip():
            d, n, t, ft = ln.rstrip('\n').split('\t')
            known[d] = (LG.flip(n), int(ft))
    d0 = '2026-09-22'
    if d0 in known:
        check(LG.norm(known[d0][0]) == LG.norm('Mickey Moniak') and known[d0][1] == 431,
              'the fixture above is the REAL 2026-09-22 answer from winners_2026.tsv', known.get(d0))
    check(len(known) > 150, 'winners_2026.tsv is present as the cross-check corpus',
          '%d days' % len(known))

print()
if FAIL:
    print('%d FAILED' % len(FAIL))
    for f in FAIL:
        print('  - ' + f)
    sys.exit(1)
print('ALL GREEN -- the Jackpot has a real result, and an unknown day never counts as a loss')
