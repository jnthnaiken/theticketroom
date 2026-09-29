#!/usr/bin/env python3
"""FIRSTTD-2026-09-29 -- the one first-touchdown pick, end to end without the network.

  * P(first) splits a game's expected touchdowns between its men and sums to <= P(any TD)
  * the pick is the best EV inside the price band; never a QB, never a man ruled out
  * the pick is sticky across rebuilds, and re-made only if its man is scratched before kickoff
  * nfl_settle.first_td() reads the scorer off ESPN's scoringPlays text
  * soccer_grade.grade_ticket() grades an ftd leg on `ftd1` (first TD), not `hr` (any TD)
  * nfl_live.js stamps ftd1 from scoringPlays (run under node)
Run: python3 test_nfl_ftd.py
"""
import json, math, os, subprocess, sys, tempfile
H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, H); sys.path.insert(0, os.path.join(H, '..', 'soccer'))
import nfl_ftd, nfl_settle, soccer_grade

FAIL = []
def chk(ok, msg):
    print(('PASS  ' if ok else 'FAIL  ') + msg)
    if not ok: FAIL.append(msg)

M = 'A-at-B'
scored = [dict(name='Lead Back', team='B', pos='RB', match=M, odds=-120, p_value=0.52),
          dict(name='Slot Guy', team='A', pos='WR', match=M, odds=200, p_value=0.36),
          dict(name='Tight End', team='A', pos='TE', match=M, odds=300, p_value=0.28),
          dict(name='Deep Man', team='B', pos='WR', match=M, odds=900, p_value=0.12),
          dict(name='The QB', team='B', pos='QB', match=M, odds=300, p_value=0.30),
          dict(name='Hurt Guy', team='A', pos='WR', match=M, odds=250, p_value=0.33, out=True)]
pf = nfl_ftd.p_first(scored)
tot = sum(pf.values())
lam = sum(-math.log(1 - s['p_value']) for s in scored) / nfl_ftd.PRICED_SHARE
chk(abs(tot - nfl_ftd.PRICED_SHARE * (1 - math.exp(-lam))) < 1e-9, 'P(first) over the priced men = priced share of P(any TD)')
chk(pf[(M, 'leadback')] > pf[(M, 'slotguy')] > pf[(M, 'deepman')], 'P(first) orders with the anytime chance')

ftd = {(M, 'leadback'): 450, (M, 'slotguy'): 900, (M, 'tightend'): 1100, (M, 'deepman'): 3000,
       (M, 'theqb'): 700, (M, 'hurtguy'): 400}
best = nfl_ftd.pick(scored, ftd)
evs = {n: pf[(M, k)] * nfl_ftd.dec(ftd[(M, k)]) - 1 for n, k in
       [('Lead Back', 'leadback'), ('Slot Guy', 'slotguy'), ('Tight End', 'tightend')]}
chk(best['name'] == max(evs, key=evs.get), f"pick = best EV in the band ({best['name']})")
chk(best['name'] not in ('The QB', 'Hurt Guy', 'Deep Man'), 'never a QB, a man ruled out, or a price outside the band')

d = tempfile.mkdtemp()
sp, fp, pp, cp = (os.path.join(d, x) for x in ('s.json', 'fx.json', 'ftd.psv', 'pick.json'))
json.dump(scored, open(sp, 'w'))
json.dump({'date': '2026-10-01', 'matches': {M: {'kickoff': 1215}}}, open(fp, 'w'))
open(pp, 'w').write('\n'.join(f'{M}|{n}|+{ftd[(M, nfl_ftd.norm(n))]}' for n in
                              ['Lead Back', 'Slot Guy', 'Tight End', 'Deep Man', 'The QB', 'Hurt Guy']) + '\n')
run = lambda now: subprocess.run([sys.executable, os.path.join(H, 'nfl_ftd.py'), sp, fp, pp, '--date', '2026-10-01',
                                  '--cache', cp, '--now-et-min', str(now)], capture_output=True, text=True)
r = run(600); first = json.load(open(cp))
chk(r.returncode == 0 and first['name'] == best['name'], 'CLI writes the pick to the cache')
for s in scored:
    if s['name'] == 'Slot Guy': s['p_value'] = 0.60           # the board moves...
json.dump(scored, open(sp, 'w'))
run(700)
chk(json.load(open(cp))['name'] == first['name'], 'a rebuild holds the cached pick even when the model moves')
for s in scored:
    if s['name'] == first['name']: s['out'] = True
json.dump(scored, open(sp, 'w'))
run(1300)
chk(json.load(open(cp))['name'] == first['name'], 'scratched AFTER kickoff: held (it voids)')
run(800)
chk(json.load(open(cp))['name'] != first['name'], 'scratched BEFORE kickoff: re-picked without him')

summ = {'scoringPlays': [
    {'type': {'abbreviation': 'FG'}, 'text': 'Cairo Santos 29 Yd Field Goal'},
    {'type': {'abbreviation': 'TD'}, 'text': 'Luther Burden III 8 Yd pass from Case Keenum (Cairo Santos Kick)'},
    {'type': {'abbreviation': 'TD'}, 'text': 'Jalen Hurts 1 Yd Rush (Jake Elliott Kick)'}]}
chk(nfl_settle.first_td(summ) == 'Luther Burden III', 'settle reads the first TD scorer, skipping the field goal')
chk(nfl_settle.first_td({'scoringPlays': []}) is None, 'no touchdown -> no first scorer')

players = {'Luther Burden': {'hr': True, 'ftd1': True}, 'Jalen Hurts': {'hr': True, 'ftd1': False}}
leg = lambda n: {'name': n, 'odds': 700, 'game': 1, 'ftd': True}
g1 = soccer_grade.grade_ticket({'kind': 'ftd', 'players': [leg('Luther Burden')]}, players, {1})
g2 = soccer_grade.grade_ticket({'kind': 'ftd', 'players': [leg('Jalen Hurts')]}, players, {1})
g3 = soccer_grade.grade_ticket({'kind': 'builder', 'players': [{'name': 'Jalen Hurts', 'odds': 150, 'game': 1}]}, players, {1})
chk(g1 and g1['won'] and abs(g1['net'] - 7.0) < 1e-9, 'first-TD leg on the first scorer wins at the first-TD price')
chk(g2 and not g2['won'], 'first-TD leg on a LATER scorer loses')
chk(g3 and g3['won'], 'an anytime leg on the same later scorer still wins')

js = r"""
const L=require(process.argv[1]);
const D={meta:{date:'2026-09-28'},players:{'Luther Burden III':{game:1,code:'CHI',gmatch:'PHI@CHI'},'Jalen Hurts':{game:1,code:'PHI',gmatch:'PHI@CHI'}},tickets:[]};
const ev={id:'9',date:'2026-09-29T00:15Z',competitions:[{status:{type:{name:'STATUS_IN_PROGRESS',state:'in'}}}]};
const sum={boxscore:{players:[]},scoringPlays:[{type:{abbreviation:'TD'},team:{abbreviation:'CHI'},text:'Luther Burden III 8 Yd pass from Case Keenum (Cairo Santos Kick)'}]};
const lv=L.makeLive({D,fetchJSON:()=>Promise.reject()}); lv.applyGame(1,ev,sum);
console.log(JSON.stringify([D.players['Luther Burden III'].ftd1,D.players['Jalen Hurts'].ftd1]));
"""
o = subprocess.run(['node', '-e', js, os.path.join(H, 'nfl_live.js')], capture_output=True, text=True)
chk(o.stdout.strip() == '[true,false]', f'nfl_live.js stamps ftd1 from scoringPlays ({o.stdout.strip() or o.stderr[-120:]})')

print('ALL GREEN -- first-TD pick, settle and grade' if not FAIL else f'{len(FAIL)} FAILURE(S)')
sys.exit(1 if FAIL else 0)
