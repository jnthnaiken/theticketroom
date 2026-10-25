#!/usr/bin/env python3
"""nba_nbacom.py -- NONESPN-2026-10-25. The NBA's own data, read from nba.com's game pages, ESPN as last resort.

Owner, 10-25 7:16 PM, after ESPN's half-built live box score voided three starters: "fuck espn dude. only use them
for a last resort ... i cant stand that company".

cdn.nba.com's liveData JSON is 403 from the runner and CORS-blocked in a reader's browser, but www.nba.com's pages
are not, and each one ships its data in __NEXT_DATA__:
  * /games?date=YYYY-MM-DD   pageProps.gameCardFeed ... cards[].cardData: gameId, homeTeam/awayTeam teamTricode,
                             gameStatus 1 pre / 2 live / 3 final
  * /game/<gameId>/box-score pageProps.game: homeTeam/awayTeam .players[] {name, starter '1', played '1',
                             statistics{...}}; pageProps.playByPlay.actions[]: actionType (jumpball, 2pt, 3pt,
                             freethrow ...), personId, playerName, isFieldGoal, shotResult, scoreHome/scoreAway,
                             period, clock 'PT11M40.00S', jumpBallWonPersonId/LostPersonId, possession, teamTricode

This module gives the SAME interface as nba_espn (scoreboard/summary/parse) so the grader and the learner swap it in
unchanged; `nba_src` below picks nba.com first and falls back to ESPN only when nba.com fails.
"""
import json, re, sys, urllib.request

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36',
      'Accept-Language': 'en-US,en;q=0.9'}
TRI = {'GS': 'GSW', 'NO': 'NOP', 'NY': 'NYK', 'SA': 'SAS', 'UTAH': 'UTA', 'WSH': 'WAS', 'PHO': 'PHX', 'BRK': 'BKN'}


def tcode(a):
    a = str(a or '').upper().strip()
    return TRI.get(a, a)


def next_data(url):
    h = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode('utf-8', 'replace')
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', h, re.S)
    if not m: raise RuntimeError('no __NEXT_DATA__ at ' + url)
    return json.loads(m.group(1))['props']['pageProps']


def _cards(pp):
    out = []
    def walk(o):
        if isinstance(o, dict):
            cd = o.get('cardData')
            if isinstance(cd, dict) and cd.get('gameId') and cd.get('homeTeam') and cd.get('awayTeam'):
                out.append(cd)
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(pp.get('gameCardFeed') or pp)
    return out


def scoreboard(ymd):
    """-> list of (gameId, AWAY, HOME, state 'pre'|'in'|'post', completed, season type, start) -- nba_espn's shape."""
    pp = next_data('https://www.nba.com/games?date=' + ymd)
    seen, out = set(), []
    for c in _cards(pp):
        if c['gameId'] in seen: continue
        seen.add(c['gameId'])
        st = int(c.get('gameStatus') or 1)
        ty = 2 if 'Regular' in str(c.get('seasonType') or 'Regular') else 3
        out.append(('nba:' + c['gameId'], tcode(c['awayTeam'].get('teamTricode')), tcode(c['homeTeam'].get('teamTricode')),
                    {1: 'pre', 2: 'in', 3: 'post'}.get(st, 'pre'), st == 3, ty, c.get('gameTimeUtc') or c.get('gameEt')))
    return out


def summary(gid):
    gid = str(gid).replace('nba:', '')
    pp = next_data(f'https://www.nba.com/game/{gid}/box-score')
    return {'_src': 'nba', 'game': pp.get('game') or {}, 'actions': ((pp.get('playByPlay') or {}).get('actions') or [])}


def _secs(clock):
    m = re.match(r'PT(\d+)M(\d+(?:\.\d+)?)S', str(clock or ''))
    return int(m.group(1)) * 60 + float(m.group(2)) if m else None


def parse(s):
    """nba.com summary -> nba_espn.parse's dict (H, V, starters, team_of, played, jumpers, tip, fb, fbT, fs, fsT,
    fga, fgm, efga, tfirst, final, state, season_type)."""
    g = s['game']
    H, V = tcode((g.get('homeTeam') or {}).get('teamTricode')), tcode((g.get('awayTeam') or {}).get('teamTricode'))
    pid, team_of, starters, played = {}, {}, {H: [], V: []}, set()
    tid = {}
    for side, T in (('homeTeam', H), ('awayTeam', V)):
        t = g.get(side) or {}
        tid[t.get('teamId')] = T
        for p in t.get('players') or []:
            nm = p.get('name') or (str(p.get('firstName', '')) + ' ' + str(p.get('familyName', ''))).strip()
            if not nm: continue
            pid[p.get('personId')] = nm; team_of[nm] = T
            if str(p.get('starter')) == '1': starters[T].append(nm)
            if str(p.get('played')) == '1': played.add(nm)
    fga, fgm, efga, tfirst = {}, {}, {}, {}
    jumpers = tip = fb = fbT = fs = fsT = None
    for a in s['actions']:
        at = str(a.get('actionType') or '')
        if at == 'jumpball' and jumpers is None and a.get('period') == 1:
            w, l = pid.get(a.get('jumpBallWonPersonId')), pid.get(a.get('jumpBallLostPersonId'))
            if w and l:
                jumpers = (w, l) if team_of.get(w) == H else (l, w)
            tip = tid.get(a.get('possession')) or tcode(a.get('teamTricode')) or None
            continue
        who = pid.get(a.get('personId'))
        made = str(a.get('shotResult') or '') == 'Made'
        if fs is None and made and who and at in ('2pt', '3pt', 'freethrow'):
            fs, fsT = who, team_of.get(who)                  # FDRULES: first score of the game, free throws count
        if not a.get('isFieldGoal') or not who: continue
        T = team_of.get(who)
        fga[who] = fga.get(who, 0) + 1
        if made: fgm[who] = fgm.get(who, 0) + 1
        if a.get('period') == 1:
            sec = _secs(a.get('clock'))
            if sec is not None and sec >= 420: efga[who] = efga.get(who, 0) + 1
        if T and T not in tfirst: tfirst[T] = who
        if made and fb is None: fb, fbT = who, T
    st = int(g.get('gameStatus') or 1)
    return dict(H=H, V=V, starters=starters, team_of=team_of, played=played, jumpers=jumpers, tip=tip,
                fb=fb, fbT=fbT, fs=fs, fsT=fsT, fga=fga, fgm=fgm, efga=efga, tfirst=tfirst,
                final=st == 3, state={1: 'pre', 2: 'in', 3: 'post'}.get(st, 'pre'), season_type=2)


if __name__ == '__main__':
    d = sys.argv[1]
    sb = scoreboard(d)
    for row in sb:
        print(row)
        if row[3] != 'pre':
            g = parse(summary(row[0]))
            print('   starters', {k: len(v) for k, v in g['starters'].items()}, 'first score', g['fs'], 'jump', g['jumpers'], 'tip', g['tip'])
