#!/usr/bin/env python3
"""FIRSTBASKET-2026-10-17 -- the basketball room end to end without the network.

    python3 nba/test_nba_fb.py
"""
import io, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'soccer'))
import nba_fb as F
import nba_espn as E
import nba_payload as PL
import nba_settle as SE

FX = os.path.join(HERE, 'test_fixtures', 'espn_MEM_at_PHI_2026-03-10.json')
fails = []


def check(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond: fails.append(msg)


# ---- ESPN parse: first FIELD GOAL, not a free throw; the tip; starters ----
g = E.parse(json.load(open(FX)))
check(g['H'] == 'PHI' and g['V'] == 'MEM', 'teams folded to NBA tricodes')
check(g['fb'] == 'Kelly Oubre Jr.' and g['fbT'] == 'PHI', 'first basket = first made field goal (Oubre three)')
check(g['jumpers'] == ('Adem Bona', 'Olivier-Maxence Prosper'), 'jumpers ordered home, away')
check(g['tip'] == 'PHI', 'tip goes to the gainer\'s team')
check(all(len(v) == 5 for v in g['starters'].values()), 'five starters a side from the box score')
check(g['tfirst'] == {'PHI': 'Kelly Oubre Jr.', 'MEM': 'Cedric Coward'}, 'each team\'s first shot')
check(E.tcode('UTAH') == 'UTA' and E.tcode('GS') == 'GSW' and E.tcode('NY') == 'NYK', 'ESPN abbreviations fold')

# ---- the free throw rule ----
ft = {'type': {'text': 'Free Throw - 1 of 2'}, 'shootingPlay': True, 'scoringPlay': True, 'scoreValue': 1}
check(not E._is_fg(ft), 'a made free throw is not a basket')
check(E._is_fg({'type': {'text': 'Driving Layup Shot'}, 'shootingPlay': True, 'scoringPlay': True, 'scoreValue': 2}), 'a layup is')

# ---- picks rule ----
c = [dict(game=1, name='a', ev=.5), dict(game=1, name='b', ev=.45), dict(game=2, name='c', ev=.31),
     dict(game=3, name='d', ev=.29), dict(game=4, name='e', ev=.9), dict(game=5, name='f', ev=.35)]
p = F.pick(c)
check([x['name'] for x in p] == ['e', 'a', 'f'], 'EV >= +30%, one per game, best first, cap three')
check([x['name'] for x in F.pick([dict(game=1, name='x', ev=.1), dict(game=2, name='y', ev=.2)])] == ['y'],
      'nothing clears +30% -> the single best edge')
check(F.pick([dict(game=1, name='x', ev=-.1)]) == [], 'no positive edge -> no pick')

# ---- EW is bias-corrected (adjust=True) ----
d = {}
for x in (1.0, 0.0, 0.0): F.ew(d, 'v', x, F.A_SHOT)
check(abs(d['v'] - 1 / 3) < 0.02, 'three starts average like three starts, not the first one decayed')

# ---- state: model probabilities sum to the bench-adjusted one ----
st = F.State(json.load(open(os.path.join(HERE, 'nba_state.json'))))
pr = F.game_probs(st, g['H'], g['V'], g['starters'], st.params)
check(abs(sum(v['p'] for v in pr.values()) - F.BENCH) < 1e-9, 'ten starters carry 99.5% of the first basket')
check(sum(1 for v in pr.values() if v['jumper']) == 2, 'one predicted jumper a side')
check(st.key('Bub Carrington') == 'carltoncarrington', 'nickname table')

# ---- payload from a tiny slate, sticky cache ----
tmp = tempfile.mkdtemp()
slate = os.path.join(tmp, 'fb.psv')
rows = ['E|2026-03-10|1|2026-03-10 23:00:00|PHI|MEM|scheduled|confirmed|confirmed']
odds = {}
for i, (T, side) in enumerate(((g['H'], 'h'), (g['V'], 'a'))):
    for n in g['starters'][T]:
        rows.append(f'L|2026-03-10|1|{side}|started|0|{n}||{T}')
        o = 900 if n != 'Adem Bona' else 2000
        rows.append(f'S|2026-03-10|1|0|{n}|||{o}|10|0:{o},10:{o}')
open(slate, 'w').write('\n'.join(rows) + '\n')
cache = os.path.join(tmp, 'picks.json')
D = PL.build(slate, os.path.join(HERE, 'nba_state.json'), '2026-03-10', cache, None, 'T1')
check(len(D['players']) == 10 and D['meta']['games'] == {'1': 'MEM@PHI'}, 'payload: ten starters, one game')
check(len(D['tickets']) == 1 and D['tickets'][0]['anchor'] == 'Adem Bona', 'the long-priced jumper is the pick')
t = D['tickets'][0]
check(t['kind'] == 'fb' and t['players'][0]['ftd'] is True and t['lock'] == '7:00 PM', 'slip shape: kind fb, ftd leg, ET lock')
check(not any(ch.isdigit() for ch in t['note'].split('.', 1)[1]), 'write-up after the first sentence has no digits')
open(slate, 'a').write('S|2026-03-10|1|0|Kelly Oubre Jr.|||5000|10|0:5000,10:5000\n')
D2 = PL.build(slate, os.path.join(HERE, 'nba_state.json'), '2026-03-10', cache, None, 'T2')
check(D2['tickets'][0]['anchor'] == 'Adem Bona', 'sticky: a rebuild keeps the posted pick')

# ---- PICKSTICKY: a pick who leaves the five before tip is replaced; after tip he stands ----
import datetime as _dt
rows2 = [r.replace('L|2026-03-10|1|h|started|0|Adem Bona||PHI', 'L|2026-03-10|1|h|bench|0|Adem Bona||PHI') for r in rows]
rows2.append('L|2026-03-10|1|h|started|0|Andre Drummond||PHI')
rows2.append('S|2026-03-10|1|0|Andre Drummond|||1500|10|0:1500,10:1500')
slate2 = os.path.join(tmp, 'fb2.psv'); open(slate2, 'w').write('\n'.join(rows2) + '\n')
c2 = os.path.join(tmp, 'p2.json'); shutil.copy(cache, c2)
before = _dt.datetime(2026, 3, 10, 20, 0, tzinfo=_dt.timezone.utc)
after = _dt.datetime(2026, 3, 11, 0, 30, tzinfo=_dt.timezone.utc)
D3 = PL.build(slate2, os.path.join(HERE, 'nba_state.json'), '2026-03-10', c2, None, 'T3', now=before)
check('Adem Bona' not in [t['anchor'] for t in D3['tickets']], 'before tip: a pick benched out of the five is replaced')
shutil.copy(cache, c2)
D4 = PL.build(slate2, os.path.join(HERE, 'nba_state.json'), '2026-03-10', c2, None, 'T4', now=after)
check([t['anchor'] for t in D4['tickets']] == ['Adem Bona'] and 'Adem Bona' in D4['players'], 'after tip: the posted pick stands and still renders')

# ---- settle: grade the board off the fixture ----
board = os.path.join(tmp, 'board.json'); season = os.path.join(tmp, 'season.json')
D['tickets'].append(dict(t, name='x', anchor='Kelly Oubre Jr.', players=[dict(t['players'][0], name='Kelly Oubre Jr.', odds=900)], payout10=100.0, parlay_am=900))
json.dump(D, open(board, 'w'))
r = SE.grade_board(board, season, getsum=lambda e: json.load(open(FX)),
                   getsb=lambda d: [('1', 'MEM', 'PHI', 'post', True, 2, '')])
S = json.load(open(season))
check(r == 'graded' and S['cats']['fb'] == {'graded': 2, 'won': 1, 'units': 8.0, 'staked': 2.0}, 'ledger: Bona -1u, Oubre at +900 +9u -> +8u on 2u')

# ---- fork ----
out = os.path.join(tmp, 'nba.html')
pj = os.path.join(tmp, 'D.json'); json.dump(D2, open(pj, 'w'))
rc = subprocess.run([sys.executable, os.path.join(HERE, 'nba_fork.py'), os.path.join(HERE, '..', 'index.html'), pj, out],
                    capture_output=True, text=True)
check(rc.returncode == 0, 'nba_fork.py applies every seam to the live index.html ' + rc.stderr[-300:])
if rc.returncode == 0:
    h = open(out, encoding='utf-8').read()
    check('nbaLive()' in h and 'liveUpdate(); setInterval' not in h, 'basketball live loop wired, MLB loop dead')
    check("ODDS_KEY='nba_ticket_odds'" in h and "SLIP_KEY='nba_slip'" in h, 'own localStorage keys')
    check('<title>The Basketball Room</title>' in h, 'title')

# ---- live module ----
rc = subprocess.run(['node', '-e', '''
const L=require(process.argv[1]); const fs=require('fs'); const s=JSON.parse(fs.readFileSync(process.argv[2]));
const D={meta:{date:'2026-03-10',games:{'1':'MEM@PHI'}},players:{'Kelly Oubre Jr.':{game:1,code:'PHI'},'Adem Bona':{game:1,code:'PHI'}},tickets:[]};
const lv=L.makeLive({D,fetchJSON:()=>Promise.reject()}); lv.applyGame(1,{competitions:[{status:{type:{name:'STATUS_IN_PROGRESS',state:'in'}}}]},s);
process.stdout.write(JSON.stringify([D.players['Kelly Oubre Jr.'].ftd1,D.players['Adem Bona'].ftd1,D.players['Adem Bona'].status]));''',
                     os.path.join(HERE, 'nba_live.js'), FX], capture_output=True, text=True)
check(rc.stdout.strip() == '[true,false,"confirmed"]', 'live: first basket stamped while the game is in progress ' + rc.stdout + rc.stderr[-200:])

# ---- BBDRAFT-2026-10-23: baseball-style board (anchors + moons) ----
_c = []
for g in range(1, 13):
    for k in range(10):
        _c.append(dict(game=g, name=f'P{g}_{k}', p=0.05 + 0.01 * ((g * 7 + k * 3) % 11), odds=600 + 100 * ((g + k) % 12),
                       ev=0.0, ko=1140 + 30 * (g % 3)))
_b = F.draft_board(_c)
check(len(_b['anchors']) == 4, 'bbdraft: four anchors')
_val = sorted(_c, key=lambda c: -F.value(c))
_ag = []
for c in F.draft_pool(_c):
    if c['game'] not in {x['game'] for x in _ag}: _ag.append(c)
check([a['name'] for a in _b['anchors']] == [c['name'] for c in _ag[:4]], 'bbdraft: anchors are the best value from four different games')
check(len({a['game'] for a in _b['anchors']}) == len(_b['anchors']), 'bbdraft: one anchor per game (ANCHOR1G)')
check(all(len(m) == 4 and len({x['game'] for x in m}) == 4 for m in _b['moons']), 'bbdraft: moons are 4 legs from 4 games')
check(len(_b['moons']) == 8, 'bbdraft: two moons per anchor on a deep slate')
check(all(_b['moons'][i][0] is _b['moons'][i + 1][0] and len({x['name'] for x in _b['moons'][i][1:]} - {x['name'] for x in _b['moons'][i + 1][1:]}) >= F.MOON_DIFF
          for i in range(0, len(_b['moons']) - 1, 2)), "bbdraft: an anchor's two moons differ by >= 2 partners")
check(len({tuple(sorted(x['name'] for x in m)) for m in _b['moons']}) == len(_b['moons']), 'bbdraft: no duplicate moons')
check(F.rr_combos(4) == 11 and abs(F.RR_UNIT * F.rr_combos(4) - 1.10) < 1e-9, 'bbdraft: 11 bets x 0.10u')
check(F.draft_board(_c[:5])['anchors'] == [], 'bbdraft: thin slate drafts nothing')
# ---- FAVANCHOR-2026-10-24: favourites lead the moons, value partners ----
_f = F.draft_board(_c, fav=True)
_fav = []
for c in sorted(_c, key=lambda c: -c['p']):
    if c['game'] not in {x['game'] for x in _fav}: _fav.append(c)
check([a['name'] for a in _f['anchors']] == [c['name'] for c in _fav[:4]], 'favanchor: anchors are the most likely from four different games')
_vp = {c['name'] for c in F.draft_pool(_c)}
check(all(x['name'] in _vp for m in _f['moons'] for x in m[1:]), 'favanchor: moon partners come from the value pool')
check(all(m[0] is _f['anchors'][i // 2] for i, m in enumerate(_f['moons'])) and len(_f['moons']) == 8, 'favanchor: two moons per favourite anchor')
check(F.draft_board(_c[:5], fav=True)['anchors'] == [], 'favanchor: thin slate drafts nothing')

# ---- FDRULES-2026-10-24: FanDuel grades the first SCORE -- free throws count ----
_fx = json.load(open(FX)); _pl = _fx.get('plays') or []
_i = next(i for i, p in enumerate(_pl) if p.get('scoringPlay') and (p.get('scoreValue') or 0) >= 2)
_ft = dict(_pl[_i]); _ft.update(scoreValue=1, type={'text': 'Free Throw - 1 of 2'}, text='free throw 1 of 2', shootingPlay=True)
_g0 = E.parse(_fx); _fx2 = dict(_fx); _fx2['plays'] = _pl[:_i] + [_ft] + _pl[_i:]
_g2 = E.parse(_fx2)
check(_g0['fs'] == _g0['fb'], 'fdrules: no free throw first -> first score is the first field goal')
_ath = {str(a_['athlete']['id']): a_['athlete']['displayName'] for tb in _fx['boxscore']['players'] for sg in tb['statistics'] for a_ in sg['athletes'] if a_.get('athlete')}
_ftp = dict(_pl[_i]); _ftp.update(scoreValue=1, type={'text': 'Free Throw - 1 of 2'})
_other = next(p for p in _pl if p.get('participants') and _ath.get(str(p['participants'][0]['athlete']['id'])) not in (None, _g0['fb']))
_ftp['participants'] = [_other['participants'][0]]
_fx3 = dict(_fx); _fx3['plays'] = _pl[:_i] + [_ftp] + _pl[_i:]
_g3 = E.parse(_fx3); _ftname = _ath[str(_other['participants'][0]['athlete']['id'])]
check(_g3['fs'] == _ftname and _g3['fs'] != _g3['fb'], f'fdrules: a free throw before the first field goal wins first basket ({_ftname})')
check(_g3['fb'] == _g0['fb'], 'fdrules: the free throw does not change the first field goal')

shutil.rmtree(tmp, ignore_errors=True)
print(f'\n{len(fails)} failure(s)')
sys.exit(1 if fails else 0)
