#!/usr/bin/env python3
"""KOTC restatement for a past night: BettingPros PRA lines (kotc.js) -> crown (nba_kotc) -> PRA from nba.com box."""
import json, subprocess, sys, os
sys.path.insert(0, 'nba')
import nba_kotc as K, nba_nbacom as N, nba_payload as NP
d = sys.argv[1]
subprocess.run(['node', 'nba/kotc.js', d, f'/tmp/kotc_raw_{d}.json'], stdout=subprocess.DEVNULL)
R = json.load(open(f'/tmp/kotc_raw_{d}.json'))
B = json.load(open(f'nba/boards/{d}.json')); games = {int(k): v for k, v in B['meta']['games'].items()}
team_game = {}
for gi, gm in games.items():
    a, h = gm.split('@'); team_game[a] = gi; team_game[h] = gi
rows = [dict(r, code=NP.KOTC_BPTEAM.get(r['team'], r['team'])) for r in R['all']]
rows = [dict(r, game=team_game[r['code']]) for r in rows if r['code'] in team_game]
C = K.crown(rows); k = next(r for r in C if r['crown'])
gid = {f'{a}@{h}': g for g, a, h, *_ in N.scoreboard(d)}[games[k['game']]]
box = N.parse(N.summary(gid))['box']
import nba_fb as F
b = next((x for x in box if x['team'] == k['code'] and (F.norm(x['name']) == F.norm(k['name']) or F.ikey(x['name']) == F.ikey(k['name']))), None)
line, odds = (k['fd_line'], k['fd_odds']) if k.get('fd_line') == k['line'] and k.get('fd_odds') else (k['line'], k.get('over_odds'))
pick = dict(name=k['name'], code=k['code'], team=NP.TEAM_NAME.get(k['code'], k['code']), game=k['game'], gmatch=games[k['game']], line=line,
            odds=int(odds), p=k['p'], mean=k['mean'], pop=k['pop'], value=k['value'], tname='The Crown', status='confirmed', final=True,
            pra=b['pra'] if b else None, dnp=not (b and b['played']), restated='KOTC-2026-10-27: restated at BettingPros PRA lines')
pick['res'] = K.grade(pick)
leader = max((x for g_ in gid.values() for x in N.parse(N.summary(g_))['box']), key=lambda x: x['pra'])
out = {'date': d, 'locked': True, 'pick': pick, 'model': R.get('model'), 'leader': [leader['name'], leader['pra']],
       'top': [{x: r[x] for x in ('name', 'code', 'line', 'mean', 'p', 'pop', 'value', 'crown')} for r in C[:6]]}
print(json.dumps(out))
