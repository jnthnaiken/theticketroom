"""test_nfl_conflock_inj.py -- CONFLOCK-NFL-2026-10-19: nfl_injuries.py confirms actives off a posted inactives list."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl_injuries as I

fail = 0
def chk(label, ok, d=None):
    global fail
    print(('PASS  ' if ok else 'FAIL  ') + label)
    if not ok:
        fail += 1
        if d is not None: print('      ', d)

inj = lambda nm, st: {'athlete': {'displayName': nm}, 'status': st}
INACT = [inj('A One', 'Out'), inj('B Two', 'Out'), inj('C Three', 'Out'), inj('D Four', 'Injured Reserve')]
REPORT = [inj('A One', 'Out'), inj('B Two', 'Questionable'), inj('C Three', 'Out'), inj('E Five', 'Out')]
chk('a posted list (flat Outs + IR) reads as inactives', I.looks_like_inactives(INACT))
chk('the injury report (a Questionable on it) does not', not I.looks_like_inactives(REPORT))

KO = 1760917200  # 2026-10-19T23:40Z-ish
iso = '2026-10-19T23:40Z'
def getj(url):
    if 'scoreboard' in url: return {'events': [{'id': 1, 'date': iso}]}
    return {'injuries': [{'team': {'abbreviation': 'SF'}, 'injuries': INACT},
                         {'team': {'abbreviation': 'WSH'}, 'injuries': REPORT}]}
ko = I._epoch(iso)
pub = {}; I.out_by_team('2026-10-19', getj=getj, now=ko - 3 * 3600, published=pub)
chk('3h out: nothing published (deadline not reached)', pub == {}, pub)
pub = {}; outs = I.out_by_team('2026-10-19', getj=getj, now=ko - 60 * 60, published=pub)
chk('1h out: SF published, WSH (still a report) not', pub == {'SF': True}, pub)

scored = [{'name': 'George Kittle', 'team': 'SF'}, {'name': 'A One', 'team': 'SF'},
          {'name': 'Jacory Croskey-Merritt', 'team': 'WAS'}]
I.apply(scored, outs)
hits = I.confirm(scored, pub)
chk('Kittle (active on a posted list) -> confirmed', scored[0].get('status') == 'confirmed', scored[0])
chk('a man ON the list -> out, never confirmed', scored[1].get('out') and scored[1].get('status') != 'confirmed', scored[1])
chk('a team with no posted list -> untouched', 'status' not in scored[2], scored[2])

d = tempfile.mkdtemp()
bp = os.path.join(d, 'b.json')
json.dump({'players': {'George Kittle': {'code': 'SF', 'status': 'confirmed'},
                       'Brock Purdy': {'code': 'SF', 'status': 'confirmed', 'out': True}}}, open(bp, 'w'))
again = [{'name': 'George Kittle', 'team': 'SF'}, {'name': 'Brock Purdy', 'team': 'SF'}]
I.carry_prior_outs(again, '2026-10-19', board_paths=[bp], seed_paths=[os.path.join(d, 'none.json')])
chk('sticky: a later build that cannot see the list keeps Kittle confirmed', again[0].get('status') == 'confirmed', again[0])
chk('sticky: an out beats a prior confirmed', again[1].get('out') and again[1].get('status') != 'confirmed', again[1])

print(f'\n{fail} FAILED' if fail else '\nall CONFLOCK-NFL injury checks pass')
sys.exit(1 if fail else 0)
