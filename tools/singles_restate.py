#!/usr/bin/env python3
"""SINGLES-2026-10-28 restatement: every graded NBA board since opening night gets the one-per-game singles the rule
(nba_fb.singles) would have posted from that board's own priced starters, at the FanDuel price on the board; the From the
Logo / Full-Court Heaves tickets come off; the season is refolded from the boards (soccer_grade.fold), Downtown and King
of the Court as already graded. Rebuilt from the CURRENT files, never from hard-coded numbers."""
import json, io, os, re, sys, datetime
sys.path.insert(0, 'nba'); sys.path.insert(0, 'soccer')
import nba_fb as F, soccer_grade as G
from nba_payload import NAMES, am_to_dec
SP = 'nba/nba_season.json'
S0 = json.load(open(SP))
nights = list(S0['graded_nights'])
NOTE = ('COVER-2026-10-28 (owner: "3 likeliest, any edge, weighted so any hit covers the game"): Tip-Off = per game, our model\'s '
        '3 most likely starters with any edge, 0.6u a game dutched across them (replaces the one-per-game rule posted earlier the same '
        'day, and From the Logo / Full-Court Heaves). 10-20..10-27 restated from each board\'s priced starters at the FanDuel prices on the board.')
notes = [n for n in (S0.get('notes') or []) if not n.startswith(('SINGLES-2026-10-28', 'COVER-2026-10-28'))] + [NOTE]
fresh = {'since': S0['since'], 'history': [0], 'graded_nights': [], 'cats': {}, 'stake': 1, 'notes': notes, 'restated': True}
json.dump(fresh, open(SP, 'w'), indent=1)
for d in nights:
    bp = f'nba/boards/{d}.json'; D = json.load(open(bp))
    P = D['players']
    cands = [dict(game=p['game'], name=n, ev=p['ev'], odds=int(p['odds']), p=p['p_value'])
             for n, p in P.items() if p.get('ev') is not None and p.get('odds') and not p.get('out')]
    picks = F.singles(cands)
    doy = datetime.date.fromisoformat(d).timetuple().tm_yday
    T = []
    for i, x in enumerate(picks):
        p = P[x['name']]; o = int(x['odds'])
        T.append(dict(name=NAMES[(doy + i) % len(NAMES)], kind='fb', badge='⚡', note=(p.get('why') or ''),
                      players=[dict(name=x['name'], team=p['team'], total=p['TOTAL'], aT=100, wf=1.0, gmatch=p['gmatch'], gtime=p['gtime'],
                                    game=p['game'], late=False, odds=o, status=p['status'], ftd=True)],
                      nlegs=1, anchor=x['name'], lock=re.sub(r'\s*ET\s*$', '', p['gtime'] or ''), has_late=False, final=False, rr=None,
                      wxsum={}, confleg=0, locked=True, priced=True, parlay_am=o, payout10=round(10 * am_to_dec(o), 1), ftd=True,
                      units=x['stake'], ev=round(x['ev'], 3), p=round(x['p'], 4), restated='SINGLES-2026-10-28'))
    D['tickets'] = T
    json.dump(D, io.open(bp, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    G.fold(bp, SP)
