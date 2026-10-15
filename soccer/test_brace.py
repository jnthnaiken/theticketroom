#!/usr/bin/env python3
"""test_brace.py -- BRACE-2026-10-15. The 👟 Brace: a second 1u ANYTIME unit on the best-value Top Bin leg.

Owner: "if they dont qualify for the board then they shouldnt be eligible for a special" -- so the pick
comes ONLY from tonight's Top Bin legs. Asserts: off-board men never picked however good; benched / out /
kicked-off / longer than +250 skipped; best npxG90 x decimal price wins; sticky; re-picked before kickoff
when benched or dropped off the board, held after kickoff; an Opener cache (no `kind`) is never treated as
a Brace; the leg grades on `hr` (anytime), not `ftd1`.
"""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import soccer_fgs as F
import soccer_grade as G

fail = 0
def chk(label, ok, detail=''):
    global fail
    print(('ok   ' if ok else 'FAIL ') + label + ('' if ok else f'   {detail}'))
    fail += 0 if ok else 1

def pl(odds, x, status='confirmed', **k):
    return dict(odds=odds, npxg90=x, status=status, match='a-v-b', **k)

P = {'Star': pl(-150, 0.90), 'Value': pl(150, 0.65), 'Long': pl(300, 0.90), 'Bench': pl(120, 0.95, 'benched'),
     'Out': pl(110, 0.95, out=True), 'OffBoard': pl(200, 2.00), 'Early': pl(140, 0.80)}
legs = ['Star', 'Value', 'Long', 'Bench', 'Out', 'Early']
never = lambda n: False
r = F.brace_pick(P, legs, never)
chk('best npxG90 x price among eligible Top Bin legs wins (Early 0.80x2.40=1.92 > Value 0.65x2.50=1.63 > Star 0.90x1.67=1.50)', r and r['name'] == 'Early', r)
chk('an off-board man is never picked, however good', all(F.brace_pick(P, legs, never)['name'] != 'OffBoard' for _ in [0]))
chk('longer than +250 is skipped', F.brace_pick({'Long': P['Long']}, ['Long'], never) is None)
chk('benched and out are skipped', F.brace_pick({k: P[k] for k in ('Bench', 'Out')}, ['Bench', 'Out'], never) is None)
chk('a kicked-off match is skipped', F.brace_pick(P, legs, lambda n: n == 'Early')['name'] == 'Value')
chk('the row is tagged kind brace', r['kind'] == 'brace')

d = tempfile.mkdtemp(); cache = os.path.join(d, 'ftd_pick.json')
c1 = F.brace_choose(P, legs, cache, never)
chk('first call writes the cache', os.path.exists(cache) and json.load(open(cache))['name'] == 'Early')
P2 = dict(P, Early=dict(P['Early'], odds=400))
chk('sticky: held even when his price drifts', F.brace_choose(P2, legs, cache, never)['odds'] == 140)
P3 = dict(P, Early=dict(P['Early'], status='benched'))
chk('re-picked before kickoff when benched', F.brace_choose(P3, legs, cache, never)['name'] == 'Value')
json.dump(c1, open(cache, 'w'))
chk('re-picked before kickoff when dropped off the board', F.brace_choose(P, [l for l in legs if l != 'Early'], cache, never)['name'] == 'Value')
json.dump(c1, open(cache, 'w'))
chk('held after kickoff even if benched', F.brace_choose(P3, legs, cache, lambda n: True)['name'] == 'Early')
open(cache, 'w').write(json.dumps({'name': 'Fati', 'match': 'x', 'odds': 550, 'p_first': 0.19}))
chk('an Opener cache (no kind) is not a Brace cache', F.is_brace_cache(cache) is False)
chk('no cache at all is not a Brace cache', F.is_brace_cache(os.path.join(d, 'none.json')) is None)

t = {'kind': 'brace', 'players': [{'name': 'Early', 'odds': 140, 'game': 1}], 'nlegs': 1, 'rr': None, 'payout10': 24.0}
g = G.grade_ticket(t, {'Early': {'hr': True, 'ftd1': False, 'game': 1}}, {1})
chk('grades ANYTIME: scored (not first) wins', g and g['won'] and abs(g['net'] - 1.4) < 1e-9, g)
g = G.grade_ticket(t, {'Early': {'hr': False, 'ftd1': True, 'game': 1}}, {1})
chk('ftd1 alone does not win a Brace', g and not g['won'], g)

print(f"\n{'ALL GREEN' if not fail else str(fail) + ' FAILURE(S)'} -- the Brace")
sys.exit(1 if fail else 0)
