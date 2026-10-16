#!/usr/bin/env python3
"""test_goalline.py -- GOALLINE-2026-10-15. The daily goals parlay (soccer_tot.py).

Asserts: odds parsing; the market layer reproduces devigged prices; the luck layer moves lambdas in the
fitted direction and falls back to the market for a side with no understat history; understat names join
(FC Cologne, RasenBallsport Leipzig, Borussia M.Gladbach); the parlay takes the top two legs by model P from
DIFFERENT matches, never a leg under 1.40 and never a started match; it is sticky; grading follows the
final scores (an over lands early, a loser decides at once, a win waits for every leg).
"""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import soccer_tot as T

fail = 0
def chk(label, ok, detail=''):
    global fail
    print(('ok   ' if ok else 'FAIL ') + label + ('' if ok else f'   {detail}'))
    fail += 0 if ok else 1

chk('fractional odds', abs(T.dec('5/6') - 1.8333) < 1e-3 and T.dec('EVS') == 2.0 and abs(T.dec('+120') - 2.2) < 1e-9 and abs(T.dec('-150') - 1.6667) < 1e-3)
chk('american', T.american(2.1) == 110 and T.american(1.4) == -250)

M = T.matrix(1.5, 1.2)
chk('score matrix sums to 1', abs(sum(map(sum, M)) - 1) < 1e-9)
chk('over + under 2.5 = 1', abs(T.leg_prob(M, 'TG', 'O', 2.5) + T.leg_prob(M, 'TG', 'U', 2.5) - 1) < 1e-9)
lh, la = T.implied(0.45, 0.27, 0.28, 0.52)
M2 = T.matrix(lh, la)
hw = sum(M2[i][j] for i in range(T.KMAX) for j in range(T.KMAX) if i > j)
chk('implied lambdas reproduce the market', abs(hw - 0.45) < 0.03 and abs(T.leg_prob(M2, 'TG', 'O', 2.5) - 0.52) < 0.03, (lh, la, hw))

d = tempfile.mkdtemp()
tm = os.path.join(d, 'tm.psv')
rows = ['league|team|date|h_a|xG|xGA|npxG|npxGA|scored|missed']
for i in range(8):   # Lucky FC: scores far above its chances; Leaky FC: concedes far above its chances
    rows.append(f'Bundesliga|FC Cologne|2026-09-{10+i:02d}|h|1.0|1.0|1.0|1.0|3|1')
    rows.append(f'Bundesliga|RasenBallsport Leipzig|2026-09-{10+i:02d}|a|1.0|1.0|1.0|1.0|1|3')
    rows.append(f'Bundesliga|Borussia M.Gladbach|2026-09-{10+i:02d}|h|1.0|1.0|1.0|1.0|1|1')
rows.append('Bundesliga|FC Cologne|2026-10-20|h|1.0|1.0|1.0|1.0|9|0')   # AFTER the slate: must be ignored
open(tm, 'w').write('\n'.join(rows) + '\n')
L = T.Luck(T.load_tm(tm), '2026-10-16')
chk('understat join: Cologne', L.own_opp('Cologne')[0] == 'FC Cologne')
chk('understat join: RB Leipzig', L.own_opp('RB Leipzig')[0] == 'RasenBallsport Leipzig')
chk("understat join: Borussia M'gladbach", L.own_opp("Borussia Monchengladbach")[0] == 'Borussia M.Gladbach')
chk('rows after the slate date are ignored', abs(L.own_opp('Cologne')[1] - 2.0) < 1e-9, L.own_opp('Cologne'))
chk('no history -> no luck (pure market)', L.own_opp('Sturm Graz') == (None, None, None))

tp = os.path.join(d, 'tot.psv')
lines = []
for m in ('cologne-v-rb-leipzig', 'a-v-b', 'c-v-d'):
    lines += [f'{m}|WIN|H|-|6/4', f'{m}|WIN|D|-|12/5', f'{m}|WIN|A|-|15/8', f'{m}|TG|O|2.5|10/11', f'{m}|TG|U|2.5|10/11',
              f'{m}|TG|O|1.5|1/3', f'{m}|TG|U|3.5|1/3', f'{m}|TH|O|0.5|4/9', f'{m}|TA|O|0.5|4/7']
lines.append('c-v-d|TG|O|1.5|1/4')    # c-v-d's shortest leg drops under 1.40 and must be skipped
open(tp, 'w').write('\n'.join(lines) + '\n')
FX = {'cologne-v-rb-leipzig': {'home': 'Cologne', 'away': 'RB Leipzig'}, 'a-v-b': {'home': 'Alpha', 'away': 'Beta'},
      'c-v-d': {'home': 'Gamma', 'away': 'Delta'}}
P = T.load_prices(tp)
views = [T.match_view(k, v, P, L) for k, v in FX.items()]
v0 = views[0]
chk('luck: lucky attack facing a defence leaky by luck -> lower home lambda', v0['lh'] < 0.9 * v0['mlh'], (v0['mlh'], v0['lh']))
chk('luck: neutral sides -> away lambda within 1% of the market', abs(v0['la'] / v0['mla'] - 1) < 0.01, (v0['mla'], v0['la']))
chk('luck: no history -> lambdas equal the market', abs(views[1]['lh'] - views[1]['mlh']) < 0.01)
pk = T.pick(views)
chk('two legs from two different matches', pk and len({l['match'] for l in pk}) == 2, pk)
chk('every leg qualifies at 1.40+ on the market-fair price less margin', all(l['est'] >= 1.40 for l in pk))
chk('posted price never better than fair', all(l['price'] <= 1 / l['pm'] + 1e-9 for v in views for l in v['legs'] if l['price']))
chk('top legs by model probability', pk[0]['p'] >= pk[1]['p'])
pk2 = T.pick(views, started=lambda m: m == pk[0]['match'])
chk('a started match is never picked', pk2 and all(l['match'] != pk[0]['match'] for l in pk2))
cache = os.path.join(d, 'tot_pick.json')
t1, _ = T.build(FX, tp, tm, '2026-10-16', cache_path=cache, gnum={k: i + 1 for i, k in enumerate(FX)})
open(tp, 'w').write('')   # prices vanish -- the cached pick must hold
t2, _ = T.build(FX, tp, tm, '2026-10-16', cache_path=cache, gnum={k: i + 1 for i, k in enumerate(FX)})
chk('sticky: the cached pick is returned unchanged', t1 and t2 and [l['label'] for l in t1['tlegs']] == [l['label'] for l in t2['tlegs']])
chk('ticket title is not the section name', t1['name'] != 'The Goal Line' and t1['kind'] == 'goalline')

t = {'kind': 'goalline', 'units': 1, 'payout10': 21.0, 'tlegs': [
    {'game': 1, 'mkt': 'TG', 'side': 'O', 'line': 1.5}, {'game': 2, 'mkt': 'TA', 'side': 'U', 'line': 1.5}]}
chk('undecided while a leg is open', T.grade(t, {'1': [2, 0], '2': [0, 0]}, {1}) is None)
g = T.grade(t, {'1': [2, 0], '2': [0, 1]}, {1, 2}); chk('both land -> +1.1u', g and g['won'] and abs(g['net'] - 1.1) < 1e-9, g)
g = T.grade(t, {'1': [0, 1], '2': [0, 0]}, {1}); chk('a final losing leg decides it at once', g and not g['won'] and g['net'] == -1, g)
g = T.grade(t, {'1': [1, 1], '2': [0, 2]}, {1, 2}); chk('team under busted -> lost', g and not g['won'])
chk('home/away legs read the right side', T.leg_won({'mkt': 'TH', 'side': 'O', 'line': 0.5}, (1, 0)) and not T.leg_won({'mkt': 'TA', 'side': 'O', 'line': 0.5}, (1, 0)))

import re as _re
_whys = [l.get('why') for l in t1['tlegs']]
chk('every leg carries a write-up', all(_whys), _whys)
chk('write-ups recite no digits', not any(_re.search(r'\d', w or '') for w in _whys), _whys)
_v = {'match': 'x', 'lh': 1.5, 'la': 1.1, 'luck': {'home': ['H', 0.4, 0.0], 'away': ['A', 0.0, 0.4]}}
_w = T.writeup({'match': 'x', 'mkt': 'TH', 'side': 'U', 'line': 1.5}, _v, {'home': 'Hosts', 'away': 'Guests'}, 'd')
chk('team under cites the hot finishing that should cool', 'above their chances' in _w, _w)
# GLRESEARCH-2026-10-16: the research rows
open(tp, 'w').write('\n'.join(lines) + '\n')
_rows = T.research(FX, tp, tm, '2026-10-16', gnum={k: i + 1 for i, k in enumerate(FX)}, picked=t1['tlegs'])
chk('research: one row per priced match', len(_rows) == 3, len(_rows))
chk('research: probabilities for every bettable line', all(r[k] is not None for r in _rows for k in ('o15', 'o25', 'u25', 'hs', 'as')))
chk('research: o2.5 + u2.5 = 1', all(abs(r['o25'] + r['u25'] - 1) < 1e-3 for r in _rows))
chk('research: the Goal Line legs are marked', sum(1 for r in _rows for k in r if k.endswith('_gl')) >= 1)
print(f"\n{'ALL GREEN' if not fail else str(fail) + ' FAILURE(S)'} -- the Goal Line")
sys.exit(1 if fail else 0)
