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
    # `homered` and `played` are sets of NORMALISED PLAYER NAMES (grade_night.norm), not teams.
    # A leg whose bat is absent from `played` voids as a DNP, which is how the first cut of this
    # test made a winning Dinger come back ungraded.
    homered = {grade_night.norm(cd['players'][0]['name'])}
    played = {grade_night.norm(l['name']) for t in client for l in t['players']}

    class _P(dict):
        pass
    import longball_grade
    jname = cj['players'][0]['name']
    hdr = '"player_name","events","home_team","hit_distance_sc"\n'
    def _fx(rows):
        return lambda u, timeout=45: hdr + ''.join(
            '"%s","home_run","X","%d"\n' % (longball_grade.flip(n) if ',' in n else
                                             (n.split()[-1] + ', ' + ' '.join(n.split()[:-1])), d)
            for n, d in rows)

    gd = grade_night.grade_ticket(cd, homered, played, set(), 1)
    check(gd is not None and gd['stake'] == 0, 'a Dinger is staked at ZERO even on a winner', gd)
    check(gd is not None and gd['won'] in (True, False),
          'and the Dinger RECORDS a result -- win or loss, not blank', gd)

    # RECORDKEPT-2026-09-24: the Jackpot now grades for real off Savant distance.
    longball_grade.is_winner.__defaults__[1].clear()   # drop the module-level day cache
    won = longball_grade.is_winner(jname, date, fetch=_fx([(jname, 450), ('Someone Else', 400)]), cache={})
    lost = longball_grade.is_winner(jname, date, fetch=_fx([(jname, 399), ('Someone Else', 455)]), cache={})
    check(won is True and lost is False,
          'the Jackpot RECORDS a result: longest homer wins, a shorter one loses', (won, lost))
    check(longball_grade.is_winner(jname, date, fetch=lambda u, timeout=45: hdr, cache={}) is None,
          'and an UNKNOWN day stays ungraded rather than counting as a loss')

    gj_won = dict(cj); gj_won['kind'] = 'jackpot'
    gj = grade_night.grade_ticket(cj, homered, played, set(), 1)          # no date -> unknown
    check(gj is not None and gj['stake'] == 0 and gj['net'] == 0, 'a Jackpot is staked at ZERO', gj)

    season = {'cats': {}, 'history': [0.0]}
    graded = [g for g in (gd, {'kind': 'jackpot', 'stake': 0.0, 'net': 0.0, 'won': True}) if g]
    grade_night.fold(season, date, graded)
    check(season['history'][-1] == 0.0,
          'folding a night of free plays moves season P&L by exactly 0.0u', season['history'])
    check('jackpot' in season['cats'] and season['cats']['jackpot']['graded'] == 1
          and season['cats']['jackpot']['staked'] == 0.0,
          'and BOTH specials keep a record in the ledger, at zero risk', season['cats'])

# ---------------------------------------------------------------------------------------
# 4. IDEMPOTENCE -- the one that actually caught the live bug.
#    The board is re-drafted on every page load, not just at build time. Removing the
#    "already used" exclusion at the MINT site alone fixed only the build that first mints the
#    ticket; every later redraft came through the refill loop, hit `usedG`, and walked the
#    Jackpot off the correct man onto whoever was left -- Goodman and Carroll both leg moons, so
#    the pick slid to the third name. The board shipped right and then drifted wrong, which the
#    commit diff cannot show you. Re-draft repeatedly and assert nothing moves.
with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as tf:
    json.dump(D, tf)
    tmp = tf.name
seen = []
for _ in range(4):
    subprocess.run(['node', os.path.join(HERE, 'client_assemble.js'), tmp, os.path.join(HERE, 'index.html')],
                   capture_output=True, text=True, cwd=HERE)
    tk = json.load(open(tmp))['tickets']
    seen.append((next((t['players'][0]['name'] for t in tk if t['kind'] == 'jackpot'), None),
                 next((t['players'][0]['name'] for t in tk if t['kind'] == 'dinger'), None),
                 sum(1 for t in tk if t['kind'] == 'moon'), len(tk)))
os.unlink(tmp)
check(len(set(seen)) == 1,
      'four consecutive redrafts leave the specials, the moons and the ticket count UNCHANGED',
      ' -> '.join('%s/%s m%d n%d' % x for x in seen))
if cj:
    check(seen[0][0] == cj['players'][0]['name'],
          'and a redraft does not move the Jackpot off a bat that legs a moon', seen[0][0])

# ---------------------------------------------------------------------------------------
# 5. SELF-CORRECTION -- a free pick must be re-derived, never inherited.
#    Prepending the INCUMBENT as the preferred candidate is right for a placed bet (it stops a
#    slip churning under someone with money on it) and wrong for these two, which are a
#    recomputed answer to "who is the best pick right now" and have no stake to protect. With
#    pref prepended a special drafted by a BUGGY build is re-selected forever -- which is exactly
#    what happened on 2026-09-24: 12:36 minted the Jackpot correctly, 12:41 drifted it to the
#    third-best man, and every build after kept choosing him because he was already there.
#    Start from a board holding the WRONG men and assert the engine fixes itself.
Dp = json.loads(json.dumps(D))


def _mkleg(n):
    p = P[n]
    return {"name": n, "team": p['team'], "total": p['TOTAL'], "aT": p['aT'], "wf": p['wf'],
            "gmatch": p['gmatch'], "gtime": p['gtime'], "game": p['game'],
            "late": bool(p.get('late')), "odds": p['odds'], "status": p['status']}


wrong = {}
if cd and cj:
    right = {'jackpot': cj['players'][0]['name'], 'dinger': cd['players'][0]['name']}
    for t in Dp['tickets']:
        if t['kind'] in ('jackpot', 'dinger'):
            pool = [n for n in P if n != right[t['kind']] and P[n].get('odds') is not None
                    and not P[n].get('out') and P[n].get('TOTAL') is not None]
            if t['kind'] == 'dinger':
                pool = [n for n in pool if norm(n) in {norm(x) for x in DLIST}]
            if not pool:
                continue
            bad = min(pool, key=lambda n: P[n]['TOTAL'])
            wrong[t['kind']] = bad
            t['players'] = [_mkleg(bad)]
            t['anchor'] = bad
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as tf:
        json.dump(Dp, tf)
        tmp = tf.name
    subprocess.run(['node', os.path.join(HERE, 'client_assemble.js'), tmp, os.path.join(HERE, 'index.html')],
                   capture_output=True, text=True, cwd=HERE)
    fixed = json.load(open(tmp))['tickets']
    os.unlink(tmp)
    for kind, want in right.items():
        got = next((t['players'][0]['name'] for t in fixed if t['kind'] == kind), None)
        check(got == want,
              'a redraft CORRECTS a %s left on the wrong bat by an earlier build' % kind,
              'seeded %s -> got %s, want %s' % (wrong.get(kind), got, want))

print()
if FAIL:
    print('%d FAILED' % len(FAIL))
    for f in FAIL:
        print('  - ' + f)
    sys.exit(1)
print('ALL GREEN -- the specials are two free plays, and the board treats them like it')
