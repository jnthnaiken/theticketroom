#!/usr/bin/env python3
"""FGS-2026-09-29 -- the one first-goalscorer pick, end to end without the network.
  * the pick is the highest P(first goal) among men with a first-goalscorer price who are starting
  * the price does not move the pick; a benched / out man is never picked
  * the pick is sticky, and re-made only when its man is not starting before kickoff
  * soccer_grade.fold() grades meta.ftd once, on ftd1 (first goal), not hr (any goal)
  * soccer_live.js stamps ftd1 from keyEvents, skipping own goals (run under node)
"""
import json, os, subprocess, sys, tempfile
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import soccer_fgs as F, soccer_grade as G
FAIL = []
def chk(ok, msg):
    print(('PASS  ' if ok else 'FAIL  ') + msg)
    if not ok: FAIL.append(msg)

M = 'a-v-b'
P = {'Big Nine': dict(match=M, npxg90=0.70, status='projected'),
     'Winger':   dict(match=M, npxg90=0.40, status='projected'),
     'Sub Star': dict(match=M, npxg90=0.90, status='benched'),
     'Hurt Guy': dict(match=M, npxg90=0.80, status='projected', out=True)}
fgs = {(M, 'bignine'): 400, (M, 'winger'): 700, (M, 'substar'): 500, (M, 'hurtguy'): 450}
never = lambda n: False
pk = F.pick(P, fgs, never)
chk(pk and pk['name'] == 'Big Nine', 'pick = best starting xG with a first-goalscorer price')
chk(F.pick(P, {(M, 'bignine'): 100000, (M, 'winger'): 200}, never)['name'] == 'Big Nine', 'the price does not move the pick')
pf = F.p_first(P)
chk(pf['Sub Star'] < pf['Big Nine'] and 'Hurt Guy' in pf and pf['Hurt Guy'] == 0, 'bench is discounted, out is zero')
chk(F.pick(P, {(M, 'winger'): 700}, never)['name'] == 'Winger', 'only men on the first-goalscorer board can be picked')
chk(F.am('13/8') in (162, 163) and F.am('4/1') == 400 and F.am('EVS') == 100, 'fractional prices convert')

d = tempfile.mkdtemp(); cache = os.path.join(d, 'ftd_pick.json')
c1 = F.choose(P, fgs, cache, never)
P['Winger']['npxg90'] = 2.0
chk(F.choose(P, fgs, cache, never)['name'] == c1['name'], 'sticky: a rebuild holds the pick when the numbers move')
P['Big Nine']['status'] = 'benched'
chk(F.choose(P, fgs, cache, lambda n: True)['name'] == 'Big Nine', 'benched AFTER kickoff: held (a placed bet)')
chk(F.choose(P, fgs, cache, never)['name'] == 'Winger', 'benched BEFORE kickoff: picked again')

# grading: meta.ftd joins the tickets once, and grades on ftd1
leg = lambda n, o: {'name': n, 'odds': o, 'game': 1, 'ftd': True}
D = {'meta': {'date': '2026-09-30', 'finals': [1],
              'ftd': {'name': 'The Opener', 'kind': 'ftd', 'players': [leg('Winger', 700)], 'nlegs': 1}},
     'players': {'Winger': {'game': 1, 'hr': True, 'ftd1': True}, 'Big Nine': {'game': 1, 'hr': True, 'ftd1': False}},
     'tickets': [{'name': 'Top', 'kind': 'builder', 'players': [{'name': 'Big Nine', 'odds': 150, 'game': 1}], 'nlegs': 1}]}
bp, sp = os.path.join(d, 'b.json'), os.path.join(d, 's.json')
json.dump(D, open(bp, 'w'))
json.dump({'since': '2026-09-30', 'history': [0], 'graded_nights': [], 'cats': {}, 'stake': 1}, open(sp, 'w'))
S = G.fold(bp, sp)
chk(S['cats'].get('ftd', {}).get('graded') == 1 and abs(S['cats']['ftd']['units'] - 7.0) < 1e-9, 'the Opener grades once, at the first-goalscorer price')
chk(sum(1 for t in json.load(open(bp))['tickets'] if t['kind'] == 'ftd') == 1, 'meta.ftd joined the archived tickets exactly once')

js = r"""
const L=require(process.argv[1]);
const D={meta:{date:'2026-09-30',espn:{'1':{lg:'fifa.friendly',ev:'1'}}},players:{'Lionel Messi':{game:1,gmatch:'Argentina v Bolivia'},'Lautaro Martinez':{game:1,gmatch:'Argentina v Bolivia'}},tickets:[]};
const sum={keyEvents:[
 {type:{text:'Own Goal'},clock:{displayValue:"3'"},participants:[{athlete:{displayName:'Bolivia Defender'}}]},
 {type:{text:'Goal'},clock:{displayValue:"12'"},participants:[{athlete:{displayName:'Lautaro Martinez'}}]},
 {type:{text:'Penalty - Scored'},clock:{displayValue:"40'"},participants:[{athlete:{displayName:'Lionel Messi'}}]}]};
const lv=L.makeLive({D,fetchJSON:()=>Promise.reject(),stamp:()=>{},render:()=>{}});
const f = lv.applyMatch || lv.applyGame; f(1,{competitions:[{status:{type:{state:'in',completed:false,name:'STATUS_SECOND_HALF'}}}]},sum);
console.log(JSON.stringify([D.players['Lautaro Martinez'].ftd1,D.players['Lionel Messi'].ftd1]));
"""
o = subprocess.run(['node', '-e', js, os.path.join(H, 'soccer_live.js')], capture_output=True, text=True)
chk(o.stdout.strip() == '[true,false]', f'soccer_live.js stamps ftd1 on the first real goal, skipping an own goal ({o.stdout.strip() or o.stderr[-200:]})')

print('ALL GREEN -- first-goalscorer pick, settle and grade' if not FAIL else f'{len(FAIL)} FAILURE(S)')
sys.exit(1 if FAIL else 0)
