#!/usr/bin/env python3
"""REFINED-2026-11-12 restatement. Owner: "10% it is" -> "what is the ledger backtested now?". Every graded NBA board
since opening night gets the Tip-Off tickets the REFINED rule (nba_fb: rank + gate on cover_p = 0.8 ours + 0.2 market,
EV >= .10, top 3 per game, 0.6u dutched in tenths) would have posted from that board's own priced starters at the
FanDuel price on the board; the season is refolded from the boards (soccer_grade.fold). The Brickyard and King of the
Court stay as graded. Rebuilt from the CURRENT files."""
import json, io, re, sys, datetime
sys.path.insert(0, 'nba'); sys.path.insert(0, 'soccer')
import nba_fb as F, soccer_grade as G
from nba_payload import NAMES, am_to_dec
SP = 'nba/nba_season.json'
S0 = json.load(open(SP))
nights = list(S0['graded_nights'])
NOTE = ('REFINED-2026-11-12 (owner: "actually i think we still want to go with the refined method" -> "10% it is"): Tip-Off ranks '
        'and gates on 0.8 x our chance + 0.2 x the market\'s, edge >= 10%, our 3 most likely per game, 0.6u a game split so any hit '
        'covers it. Every night since 10-20 restated from each board\'s priced starters at the FanDuel prices on the board.')
notes = [n for n in (S0.get('notes') or []) if not n.startswith('REFINED-2026-11-12')] + [NOTE]
json.dump({'since': S0['since'], 'history': [0], 'graded_nights': [], 'cats': {}, 'stake': S0.get('stake', 1), 'notes': notes,
           'restated': True}, open(SP, 'w'), indent=1)
for d in nights:
    bp = f'nba/boards/{d}.json'; D = json.load(open(bp)); P = D['players']
    cands = []
    for n, p in P.items():
        if p.get('p_value') is None or not p.get('odds') or p.get('out'): continue
        q = F.cover_p(p['p_value'], p.get('p_mkt'))
        cands.append(dict(game=p['game'], name=n, ev=q * am_to_dec(p['odds']) - 1, odds=int(p['odds']), p=q))
    picks = F.singles(cands)
    doy = datetime.date.fromisoformat(d).timetuple().tm_yday
    old = {t['players'][0]['game']: t.get('note') for t in D['tickets'] if t.get('kind') == 'fb'}
    T = [t for t in D['tickets'] if t.get('kind') != 'fb']
    for i, x in enumerate(picks):
        p = P[x['name']]; o = int(x['odds'])
        T.append(dict(name=NAMES[(doy + i) % len(NAMES)], kind='fb', badge='⚡', note=old.get(p['game']) or (p.get('why') or ''),
                      players=[dict(name=x['name'], team=p['team'], total=p['TOTAL'], aT=100, wf=1.0, gmatch=p['gmatch'], gtime=p['gtime'],
                                    game=p['game'], late=False, odds=o, status=p['status'], ftd=True)],
                      nlegs=1, anchor=x['name'], lock=re.sub(r'\s*ET\s*$', '', p['gtime'] or ''), has_late=False, final=False, rr=None,
                      wxsum={}, confleg=0, locked=True, priced=True, parlay_am=o, payout10=round(10 * am_to_dec(o), 1), ftd=True,
                      units=x['stake'], ev=round(x['ev'], 3), p=round(x['p'], 4), restated='REFINED-2026-11-12'))
    D['tickets'] = T
    json.dump(D, io.open(bp, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    G.fold(bp, SP)
S1 = json.load(open(SP))
print('nights', len(S1['graded_nights']), 'season', round(S1['history'][-1], 2))
for k, v in S1['cats'].items(): print(' ', k, v)
