#!/usr/bin/env python3
"""nba_livebake.py -- NONESPN-2026-10-25. Bake nba.com's live state into the board on every build, so the page does
not need ESPN. Owner: "fuck espn dude. only use them for a last resort".

    python3 nba_livebake.py .nba_D.json

For each board game nba.com has started: game state (D.meta.gs / finals / live), the starting fives (a starter is
confirmed; once BOTH fives are listed a non-starter is void -- FanDuel refunds him, FDRULES), the game's first score
(free throws count) -> D.meta.fb[gi] and each man's ftd1/hr. D.meta.nbacom = {games: [gi...]} tells nba_live.js which
games are covered; it only goes to ESPN for a game nba.com did not cover. Never fatal: on any failure the board is
left exactly as the payload wrote it.
"""
import json, sys
import nba_nbacom as N
import nba_fb as F


def _match(name, cands):
    n = F.norm(name)
    for c in cands:
        if F.norm(c) == n: return c
    ik = F.ikey(name)
    hits = [c for c in cands if F.ikey(c) == ik]
    return hits[0] if len(hits) == 1 else None


def bake(D, sb=None, getsum=N.summary):
    date = D['meta'].get('date')
    games = {int(k): v for k, v in (D['meta'].get('games') or {}).items()}
    sb = sb if sb is not None else N.scoreboard(date)
    byp = {f'{a}@{h}': (gid, st) for gid, a, h, st, *_ in sb}
    M = D['meta']
    M['gs'] = M.get('gs') or {}; M['fb'] = M.get('fb') or {}
    M['finals'] = [int(x) for x in (M.get('finals') or [])]; M['live'] = [int(x) for x in (M.get('live') or [])]
    covered = []
    for gi, pair in sorted(games.items()):
        hit = byp.get(pair)
        if not hit: continue
        gid, st = hit
        covered.append(gi)
        M['gs'][str(gi)] = {'pre': 'pre', 'in': 'live', 'post': 'final'}[st]
        if st == 'pre': continue
        if st == 'post' and gi not in M['finals']: M['finals'].append(gi)
        if st == 'in' and gi not in M['live']: M['live'].append(gi)
        try:
            g = N.parse(getsum(gid))
        except Exception as e:
            print(f'  ::warning::livebake {pair}: {str(e)[:120]}'); covered.remove(gi); continue
        full = sum(len(v) for v in g['starters'].values()) >= 10
        starters = set(sum(g['starters'].values(), []))
        fs = g['fs']
        if fs: M['fb'][str(gi)] = fs
        for n, p in D['players'].items():
            if p.get('game') != gi: continue
            who = _match(n, [c for c, t in g['team_of'].items() if t == p.get('code')])
            if who and who in starters:
                p['status'] = 'confirmed'; p['out'] = False
            p['void'] = bool(full and who not in starters)
            p['ftd1'] = bool(fs) and who == fs and not p['void']
            p['hr'] = p['ftd1']
    M['nbacom'] = {'games': covered}
    for t in D.get('tickets') or []:
        t['confleg'] = sum(1 for l in t.get('players') or []
                           if (D['players'].get(l['name']) or {}).get('status') == 'confirmed'
                           and not (D['players'].get(l['name']) or {}).get('void'))
    return covered


if __name__ == '__main__':
    path = sys.argv[1]
    try:
        D = json.load(open(path, encoding='utf-8'))
        cov = bake(D)
        json.dump(D, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
        print(f'livebake: nba.com covered games {cov}; first scores {D["meta"].get("fb")}')
    except Exception as e:
        print(f'::warning::livebake skipped: {str(e)[:200]}')
