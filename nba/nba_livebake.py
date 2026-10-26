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


def bake(D, sb=None, getsum=N.summary, firsts=None):
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
        # FIRSTLOCK-2026-10-25 (owner: "why did all of the basketball tickets just go red? we had like 4 of them cash
        # already"). nba.com's box-score page for a FINISHED game carries only the late play-by-play, so the opening
        # basket vanished and every leg on games 1-2 read as a loss. A first score never changes: keep it once seen
        # (firsts cache, committed per slate), and with no first score known, leave ftd1 pending -- never red.
        fs = g['fs']
        if firsts is not None:
            if fs and str(gi) not in firsts: firsts[str(gi)] = fs
            fs = firsts.get(str(gi)) or fs
        if fs: M['fb'][str(gi)] = fs
        for n, p in D['players'].items():
            if p.get('game') != gi: continue
            who = _match(n, [c for c, t in g['team_of'].items() if t == p.get('code')])
            if who and who in starters:
                p['status'] = 'confirmed'; p['out'] = False
            p['void'] = bool(full and who not in starters)
            p['ftd1'] = (who == fs and not p['void']) if fs else None
            p['hr'] = p['ftd1']
    M['nbacom'] = {'games': covered}
    for t in D.get('tickets') or []:
        t['confleg'] = sum(1 for l in t.get('players') or []
                           if (D['players'].get(l['name']) or {}).get('status') == 'confirmed'
                           and not (D['players'].get(l['name']) or {}).get('void'))
    return covered


if __name__ == '__main__':
    path = sys.argv[1]
    fpath = sys.argv[2] if len(sys.argv) > 2 else None
    try:
        D = json.load(open(path, encoding='utf-8'))
        firsts = {}
        if fpath:
            try: firsts = json.load(open(fpath, encoding='utf-8'))
            except Exception: firsts = {}
        cov = bake(D, firsts=firsts)
        if fpath and firsts: json.dump(firsts, open(fpath, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        json.dump(D, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
        print(f'livebake: nba.com covered games {cov}; first scores {D["meta"].get("fb")}')
    except Exception as e:
        print(f'::warning::livebake skipped: {str(e)[:200]}')
