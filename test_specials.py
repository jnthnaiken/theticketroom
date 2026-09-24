#!/usr/bin/env python3
"""SPECIALS-2026-09-24 -- the Daily Dinger and the Long Ball Jackpot, tested through BOTH drafters.

The Lunch Special and the Nightcap are retired. Their replacements are FREE plays on other books
(a FanDuel profit-boost token, a share of a Fanatics pot), and that single fact drives every rule
below -- each one is the OPPOSITE of what the old specials did, so none of them is safe to assume:

  * a free pick does NOT block a parlay and is NOT blocked by one. The old specials drew from the
    pool the board bets, so a shared bat was double real exposure and the engine both reserved the
    bat and DELETED any other slip carrying him. Keep that behaviour and the normal case -- the
    best bat on the slate is on a moon AND is the best free pick -- silently eats a moon.
  * no <=600 price cap. It protected a 1u single that no longer exists.
  * ZERO stake. At 1u these two would add ~180 fictional units of risk a season.
  * the Dinger picks from FANDUEL'S LIST, not from the top of our board. Owner, 2026-09-23:
    "its not just our top scored bat. its our highest scored bat thats on their list that day."
  * the Jackpot ranks z(park tail) + z(TOTAL). NOT `parkhr`, which is negatively related to the
    longest homer, and NOT a hard filter to the best park -- both measured in longball/backtest.py.

And the one that actually bit during the build: a RETIRED kind must be dropped from `prior`, or the
old ticket object survives the redraft, falls through to the generic single path, and comes back
re-filled under its dead kind -- while the mint guard, which is satisfied by kind, never fires.

Run: python3 test_specials.py        (from the repo root)
"""
import json
import os
import re
import subprocess
import sys
import tempfile

import assemble_tickets
import grade_night

HERE = os.path.dirname(os.path.abspath(__file__))
FAIL = []


def check(ok, msg, got=''):
    print(('PASS  ' if ok else 'FAIL  ') + msg + (('   ' + str(got)) if got and not ok else ''))
    if not ok:
        FAIL.append(msg)


def latest_board():
    ds = sorted(f for f in os.listdir(HERE) if re.match(r'^D_\d{4}-\d\d-\d\d\.json$', f))
    if not ds:
        sys.exit('!! no archived board to test against')
    return ds[-1], json.load(open(os.path.join(HERE, ds[-1])))


def park_tail():
    pt = {}
    with open(os.path.join(HERE, 'longball', 'park_tail_h1.tsv')) as fh:
        for ln in fh:
            f = ln.split()
            if len(f) >= 4:
                try:
                    pt[f[0]] = float(f[3])
                except ValueError:
                    pass
    return pt


fn, D = latest_board()
date = fn[2:-5]
PT = park_tail()
dpath = os.path.join(HERE, 'dinger_%s.txt' % date)
DLIST = ([l.strip() for l in open(dpath, encoding='utf-8') if l.strip()]
         if os.path.exists(dpath) else [])
if not DLIST:
    sys.exit('!! no dinger_%s.txt -- cannot test the Daily Dinger against a real list' % date)
D['meta']['dinger'] = DLIST
D['meta']['park_tail'] = PT
P = D['players']
print('board %s -- %d players, %d on the FanDuel list, %d parks with tail\n' % (fn, len(P), len(DLIST), len(PT)))


def norm(s):
    import unicodedata
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r'\b(jr|sr|ii|iii|iv)\b', '', s)
    return re.sub(r'[^a-z ]', '', s).strip()


# ---------------------------------------------------------------------------------------
# 1. the CLIENT engine -- index.html, which is what a person actually sees.
with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as tf:
    json.dump(D, tf)
    tmp = tf.name
r = subprocess.run(['node', os.path.join(HERE, 'client_assemble.js'), tmp, os.path.join(HERE, 'index.html')],
                   capture_output=True, text=True, cwd=HERE)
client = json.load(open(tmp))['tickets']
os.unlink(tmp)
ck = {t['kind'] for t in client}

check('dinger' in ck, 'client engine ships a Daily Dinger', sorted(ck))
check('jackpot' in ck, 'client engine ships a Long Ball Jackpot', sorted(ck))
check('lunch' not in ck and 'late' not in ck,
      'the retired lunch/late kinds do NOT survive a redraft off a board that still carries them',
      sorted(ck))
check(sum(1 for t in client if t['kind'] == 'dinger') == 1
      and sum(1 for t in client if t['kind'] == 'jackpot') == 1,
      'exactly one of each -- the mint guard still holds')

cd = next((t for t in client if t['kind'] == 'dinger'), None)
cj = next((t for t in client if t['kind'] == 'jackpot'), None)
if cd and cj:
    dn = cd['players'][0]['name']
    check(norm(dn) in {norm(x) for x in DLIST},
          "the Dinger pick is ON FanDuel's list (suffix-insensitively)", dn)
    onlist = [n for n in P if norm(n) in {norm(x) for x in DLIST}
              and P[n].get('TOTAL') is not None and not P[n].get('out') and not P[n].get('void')]
    best = max(onlist, key=lambda n: P[n]['TOTAL'])
    check(dn == best, 'the Dinger is the HIGHEST TOTAL on that list, not the best bat on the board',
          '%s vs %s' % (dn, best))
    top = max((n for n in P if P[n].get('TOTAL') is not None and not P[n].get('out')),
              key=lambda n: P[n]['TOTAL'])
    if norm(top) not in {norm(x) for x in DLIST}:
        check(dn != top, "and it is NOT simply the board's top bat when he is off the list",
              'board top %s' % top)

    jn = cj['players'][0]['name']
    check(cj['players'][0].get('odds') is not None, 'the Jackpot pick carries a price', jn)
    # the blend, recomputed here from scratch rather than trusted
    import statistics as st
    elig = [n for n in P if P[n].get('odds') is not None and not P[n].get('out') and not P[n].get('void')
            and P[n].get('TOTAL') is not None and '@' in (P[n].get('gmatch') or '')
            and PT.get((P[n]['gmatch'].split('@')[1])) is not None]
    tl = [PT[P[n]['gmatch'].split('@')[1]] for n in elig]
    to = [P[n]['TOTAL'] for n in elig]
    mt, sdt = st.mean(tl), (st.pstdev(tl) or 1.0)
    mo, sdo = st.mean(to), (st.pstdev(to) or 1.0)
    z = lambda n: (PT[P[n]['gmatch'].split('@')[1]] - mt) / sdt + (P[n]['TOTAL'] - mo) / sdo
    want = max(elig, key=z)
    check(jn == want, 'the Jackpot is the top of z(park tail) + z(TOTAL)', '%s vs %s' % (jn, want))

    # NOT the naive alternatives -- these are the two the backtest rejected.
    byparkhr = max((n for n in elig if P[n].get('parkhr') is not None),
                   key=lambda n: (P[n]['parkhr'], P[n]['TOTAL']), default=None)
    besttail = max(PT[P[n]['gmatch'].split('@')[1]] for n in elig)
    hardfilt = [n for n in elig if PT[P[n]['gmatch'].split('@')[1]] == besttail]
    hardpick = max(hardfilt, key=lambda n: P[n]['TOTAL']) if hardfilt else None
    if byparkhr and byparkhr != want:
        check(jn != byparkhr, 'and NOT the `parkhr` ranking, which is negatively related to distance',
              byparkhr)
    if hardpick and hardpick != want:
        check(jn != hardpick, 'and NOT a hard filter to the single best tail park (1 hit in 78)',
              hardpick)

    # the exposure rule, stated directly
    parl = [t for t in client if t['kind'] in ('moon', 'biggest')]
    pnames = {l['name'] for t in parl for l in t['players']}
    shared = pnames & {dn, jn}
    check(len(parl) >= 1, 'the board still carries its parlays after the specials drafted',
          '%d parlays' % len(parl))
    if shared:
        check(True, 'a free pick MAY sit on a bat the board is already betting (no reservation)',
              ', '.join(sorted(shared)))
    for t in parl:
        check(len(t['players']) == t['nlegs'],
              'no parlay lost a leg to a special: %s intact' % t['name'])

# ---------------------------------------------------------------------------------------
# 2. the FALLBACK drafter -- assemble_tickets.py must agree, or a night it runs ships a
#    different board than the one the page would have shown.
D2 = json.loads(json.dumps(D))
assemble_tickets.assemble(D2)
srv = D2['tickets']
sd = next((t for t in srv if t['kind'] == 'dinger'), None)
sj = next((t for t in srv if t['kind'] == 'jackpot'), None)
check(sd is not None and sj is not None, 'the fallback drafter ships both specials too',
      sorted({t['kind'] for t in srv}))
if sd and cd:
    check(sd['players'][0]['name'] == cd['players'][0]['name'],
          'both drafters pick the SAME Dinger',
          '%s vs %s' % (sd['players'][0]['name'], cd['players'][0]['name']))
if sj and cj:
    check(sj['players'][0]['name'] == cj['players'][0]['name'],
          'both drafters pick the SAME Jackpot',
          '%s vs %s' % (sj['players'][0]['name'], cj['players'][0]['name']))

# ---------------------------------------------------------------------------------------
# 3. grading -- free means free.
if cd and cj:
    homered = {norm(cd['players'][0]['name'])}
    played = {(l.get('team') or '') for t in client for l in t['players']}

    class _P(dict):
        pass
    gd = grade_night.grade_ticket(cd, homered, played, set(), 1)
    gj = grade_night.grade_ticket(cj, homered, played, set(), 1)
    check(gd is None or gd['stake'] == 0, 'a Dinger is staked at ZERO even on a winner', gd)
    check(gj is None or (gj['stake'] == 0 and gj['net'] == 0), 'a Jackpot is staked at ZERO', gj)
    check(gj is None or gj['won'] is None,
          'a Jackpot is left UNGRADED -- "longest homer in baseball" needs hit_distance_sc, and '
          'scoring it as a HR prop would inflate its hit rate ~10x', gj)
    season = {'cats': {}, 'history': [0.0]}
    grade_night.fold(season, date, [g for g in (gd, gj) if g])
    check(season['history'][-1] == 0.0,
          'folding a night of free plays moves season P&L by exactly 0.0u', season['history'])
    check('jackpot' not in season['cats'],
          'and an ungraded Jackpot never enters the ledger at all', sorted(season['cats']))

print()
if FAIL:
    print('%d FAILED' % len(FAIL))
    for f in FAIL:
        print('  - ' + f)
    sys.exit(1)
print('ALL GREEN -- the specials are two free plays, and the board treats them like it')
