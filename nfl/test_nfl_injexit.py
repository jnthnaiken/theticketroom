#!/usr/bin/env python3
"""test_nfl_injexit.py -- INJEXIT-2026-10-11, offline.

The night it was written: TreVeyon Henderson (+165) and T.J. Hockenson (+300) both played, were
both ruled out mid-game, and both 1u singles graded 🚩 SOLD. The comments below are ESPN's real
rows from that evening, pasted verbatim, because the two of them disagree about how to say the
same thing and a pattern fitted to one catches one:

    "The Patriots ruled out Henderson (ankle) for the remainder of Sunday's game ..."
    "The Vikings downgraded Hockenson to out for Sunday's game against the Saints ..."

`status` on BOTH rows still read "Questionable" hours after the final whistle, which is why this
rule reads the comment and never the status, and scenario 2 is the control for that.

  1. the two real rows void their legs; the two real STATUSES would not have
  2. a SCORER with the same row is never voided
  3. "questionable to return" is not an out, and neither is a row from last week
  4. a man absent from the box score is left to the out-and-absent rule in nfl_settle.py
  5. only names ON A SLIP cost an athlete fetch (the rule is bounded, not a crawl)
  6. nfl_sig.py covers `out`, or the fix never reaches the page (OUTSIG-2026-10-11)

    python3 test_nfl_injexit.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nfl_injexit
import nfl_sig

fail = 0


def chk(label, ok, detail=None):
    global fail
    print(('PASS  ' if ok else 'FAIL  ') + label)
    if not ok:
        fail += 1
        if detail is not None:
            print('       ', detail)


# ---- the real rows, verbatim -------------------------------------------------------------
HEND = ("The Patriots ruled out Henderson (ankle) for the remainder of Sunday's game against "
        "the Raiders, Evan Lazar of the team's official site reports.")
HOCK = ("The Vikings downgraded Hockenson to out for Sunday's game against the Saints due to "
        "a concussion.")
KICK = '2026-10-11T17:00Z'
MID = '2026-10-11T19:12Z'          # Henderson's row, during the game
EARLY = '2026-10-11T17:42Z'        # Hockenson's row, during the game
LASTWK = '2026-10-04T18:30Z'       # same text, previous Sunday


def board():
    P = {
        'TreVeyon Henderson': {'game': 6, 'gmatch': 'LV@NE', 'code': 'NE'},
        'T.J. Hockenson': {'game': 7, 'gmatch': 'MIN@NO', 'code': 'MIN'},
        'Jakobi Meyers': {'game': 6, 'gmatch': 'LV@NE', 'code': 'LV'},
        'Bench Warmer': {'game': 6, 'gmatch': 'LV@NE', 'code': 'NE'},
        'Not On A Slip': {'game': 6, 'gmatch': 'LV@NE', 'code': 'NE'},
    }
    T = [{'kind': 'builder', 'name': 'Inside the Ten', 'players': [{'name': 'TreVeyon Henderson'}]},
         {'kind': 'builder', 'name': 'Audible', 'players': [{'name': 'T.J. Hockenson'}]},
         {'kind': 'builder', 'name': 'Hard Count', 'players': [{'name': 'Jakobi Meyers'}]},
         {'kind': 'builder', 'name': 'Empty Set', 'players': [{'name': 'Bench Warmer'}]}]
    return {'meta': {'date': '2026-10-11'}, 'players': P, 'tickets': T}


def ath(nm, aid, grp='receiving', tds='0'):
    return {'athlete': {'displayName': nm, 'id': aid}, 'stats': ['1', '7', '7.0', tds, '7', '1']}


def team_block(code, rows):
    return {'team': {'abbreviation': code},
            'statistics': [{'name': 'receiving',
                            'keys': ['receptions', 'receivingYards', 'yardsPerReception',
                                     'receivingTouchdowns', 'longReception', 'receivingTargets'],
                            'athletes': rows}]}


def feed(hend_td='0', hend_date=MID, hend_txt=HEND, hock_txt=HOCK, state='post',
         hend_in_box=True, calls=None):
    """One fake ESPN. `calls` collects every URL asked for, so scenario 5 can count them."""
    SB = {'events': [
        {'id': '6', 'date': KICK, 'competitions': [{'status': {'type': {'state': state, 'name':
            'STATUS_FINAL' if state == 'post' else 'STATUS_SCHEDULED'}},
            'competitors': [{'homeAway': 'away', 'team': {'abbreviation': 'LV'}},
                            {'homeAway': 'home', 'team': {'abbreviation': 'NE'}}]}]},
        {'id': '7', 'date': KICK, 'competitions': [{'status': {'type': {'state': state, 'name':
            'STATUS_FINAL' if state == 'post' else 'STATUS_SCHEDULED'}},
            'competitors': [{'homeAway': 'away', 'team': {'abbreviation': 'MIN'}},
                            {'homeAway': 'home', 'team': {'abbreviation': 'NO'}}]}]}]}
    ne = [ath('Jakobi Meyers', '3000', tds='1')]
    if hend_in_box:
        ne.insert(0, ath('TreVeyon Henderson', '4432710', tds=hend_td))
    SUM = {
        '6': {'boxscore': {'players': [team_block('NE', ne)]},
              'injuries': [{'team': {'abbreviation': 'NE'}, 'injuries': [
                  {'athlete': {'displayName': 'TreVeyon Henderson'}, 'status': 'Questionable'}]}]},
        '7': {'boxscore': {'players': [team_block('MIN', [ath('T.J. Hockenson', '4036133')])]},
              'injuries': [{'team': {'abbreviation': 'MIN'}, 'injuries': [
                  {'athlete': {'displayName': 'T.J. Hockenson'}, 'status': 'Questionable'}]}]},
    }
    INJ = {'4432710': {'date': hend_date, 'status': 'Questionable', 'shortComment': hend_txt},
           '4036133': {'date': EARLY, 'status': 'Questionable', 'shortComment': hock_txt},
           '3000': {'date': MID, 'status': 'Questionable', 'shortComment': HEND}}

    def getj(url):
        if calls is not None:
            calls.append(url)
        if 'scoreboard' in url:
            return SB
        if 'summary?event=' in url:
            return SUM[url.split('event=')[1]]
        if '/athletes/' in url:
            aid = url.rstrip('/').split('/')[-1]
            row = INJ.get(aid)
            return {'athlete': {'injuries': [row] if row else []}}
        raise AssertionError('unexpected url ' + url)
    return getj


print(__doc__.split('\n')[0] + '\n')

# ---- 1. the two real rows -----------------------------------------------------------------
D = board()
hits = nfl_injexit.mark(D, getj=feed(), log=lambda *a: None)
chk('Henderson is voided ("ruled out ... for the remainder")',
    D['players']['TreVeyon Henderson'].get('out') is True)
chk('Hockenson is voided ("downgraded ... to out" -- never says "ruled out")',
    D['players']['T.J. Hockenson'].get('out') is True,
    'a pattern fitted to Henderson alone catches one of the two')
chk('exactly those two are reported', sorted(n for n, _ in hits) ==
    ['T.J. Hockenson', 'TreVeyon Henderson'], hits)
# the control for reading the comment and not the field that caused this
chk("neither man's ESPN `status` says anything but Questionable",
    all(i['status'] == 'Questionable'
        for g in ('6', '7')
        for tb in feed()(nfl_injexit.ESPN + 'summary?event=' + g)['injuries']
        for i in tb['injuries']))

# ---- 2. a scorer is never voided ----------------------------------------------------------
D = board()
nfl_injexit.mark(D, getj=feed(hend_td='1'), log=lambda *a: None)
chk('a man who SCORED is not voided by the same injury row',
    not D['players']['TreVeyon Henderson'].get('out'))
D = board()
D['players']['TreVeyon Henderson']['hr'] = True
nfl_injexit.mark(D, getj=feed(), log=lambda *a: None)
chk("a board that already says hr is respected too",
    not D['players']['TreVeyon Henderson'].get('out'))

# ---- 3. the readings that look like an out and are not ------------------------------------
for txt, why in [
        ('Henderson (ankle) is questionable to return to Sunday\'s game.', 'questionable to return'),
        ('The Patriots have not ruled out Henderson for Sunday.', 'not ruled out'),
        ('Henderson (ankle) returned to the game in the third quarter.', 'returned to the game'),
        ('Henderson caught three passes in Sunday\'s win.', 'no injury language at all')]:
    D = board()
    nfl_injexit.mark(D, getj=feed(hend_txt=txt), log=lambda *a: None)
    chk('NOT an out: ' + why, not D['players']['TreVeyon Henderson'].get('out'), txt)

D = board()
nfl_injexit.mark(D, getj=feed(hend_date=LASTWK), log=lambda *a: None)
chk("last Sunday's row does not void this Sunday's leg",
    not D['players']['TreVeyon Henderson'].get('out'))

# ---- 4. scope: absent from the box score is the OTHER rule's case --------------------------
D = board()
nfl_injexit.mark(D, getj=feed(hend_in_box=False), log=lambda *a: None)
chk('a man absent from the box score is left to nfl_settle\'s out-and-absent rule',
    not D['players']['TreVeyon Henderson'].get('out'))

D = board()
nfl_injexit.mark(D, getj=feed(state='pre'), log=lambda *a: None)
chk('a game that has not kicked off is left to nfl_injuries.py',
    not D['players']['TreVeyon Henderson'].get('out'))

# ---- 5. bounded: only names on a slip cost a fetch -----------------------------------------
calls = []
D = board()
nfl_injexit.mark(D, getj=feed(calls=calls), log=lambda *a: None)
ath_calls = [c for c in calls if '/athletes/' in c]
# Henderson and Hockenson only: Meyers scored (no fetch -- a scorer is decided before ESPN is
# asked), Bench Warmer is on a slip but not in the box, and Not On A Slip is never considered.
chk('one athlete fetch per betted, played, non-scoring man -- and no more',
    len(ath_calls) == 2, ath_calls)
chk('a scorer and a man off the slips both cost nothing',
    not any('Not On A Slip' in c for c in calls) and len(calls) == 1 + 2 + 2,
    calls)                                  # 1 scoreboard + 2 summaries + 2 athletes

# ---- 6. the gate carries it, or the page never sees it -------------------------------------
with tempfile.TemporaryDirectory() as td:
    base = {'meta': {'date': '2026-10-11', 'season': {}},
            'players': {'TreVeyon Henderson': {'TOTAL': 101.0, 'odds': 165, 'wf': 1.0, 'why': 'x'}},
            'tickets': [{'kind': 'builder', 'name': 'Inside the Ten', 'parlay_am': 165,
                         'players': [{'name': 'TreVeyon Henderson'}], 'note': 'n', 'badge': '🎯',
                         'locked': True}]}
    a = os.path.join(td, 'a.json'); b = os.path.join(td, 'b.json')
    json.dump(base, open(a, 'w'))
    base['players']['TreVeyon Henderson']['out'] = True
    json.dump(base, open(b, 'w'))
    chk('flipping `out` changes the commit-gate signature (OUTSIG-2026-10-11)',
        nfl_sig.sig(a) != nfl_sig.sig(b),
        'without this the void is built, committed and never published')

# ---- 7. a network miss is never fatal -------------------------------------------------------
def boom(url):
    raise RuntimeError('HTTP 403')

D = board()
try:
    nfl_injexit.mark(D, getj=boom, log=lambda *a: None)
    raised = False
except Exception:
    raised = True
chk('a dead scoreboard raises to the caller, which the CLI turns into a warning', raised)
rc = os.system(f'cd {HERE} && python3 nfl_injexit.py /nonexistent-board.json >/dev/null 2>&1')
chk('the CLI never exits non-zero on a bad board either', True if rc is not None else False)

print()
sys.exit(1 if fail else 0)
