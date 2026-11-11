#!/usr/bin/env python3
"""fetch_history_fotmob.py -- XGFOTMOB-2026-11-11. The current season's match history from FotMob, in fetch_history.py's
exact layout, for the scorer shadow while understat is gone.

Owner: "might as well" (move off understat -- understat.com has not loaded for anyone since 2026-11-02).

    python3 fetch_history_fotmob.py --base <dir: base team_matches/player_matches> --out fresh --season 2026 --cache fmcache

Source: www.fotmob.com/api/data/leagues (fixtures) and /api/data/matchDetails (per match: header score, every player's
"Minutes played / Goals / Expected goals (xG) / xG Non-penalty / Expected assists (xA) / Total shots / Chances created",
and the shot map with each shot's xG and situation). Measured 11-11 from a runner: all five leagues answer.

Kept continuous with the understat years in the base files, because shadow.py follows a player by `pid` and a club by
its name across seasons:
  * team names -> understat spelling, by majority vote over the players both sources share (base season - 1 rows);
    a club with no shared players keeps FotMob's name (a promoted side with no understat history, for example).
  * pid -> the understat pid of the same name (unique, preferring the same mapped club); otherwise 10,000,000 + FotMob id.
  * position: starters GK / DC / MC / FW from FotMob's usual position (0..3); bench appearances 'Sub' (the model only
    uses the group and the Sub flag). xGChain / xGBuildup have no FotMob equivalent and are written as 0.
Each finished match is parsed once and cached (--cache), so a daily run fetches only the new results.
"""
import argparse, gzip, json, os, re, sys, time, unicodedata, urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

LEAGUES = {47: 'EPL', 87: 'La_liga', 55: 'Serie_A', 54: 'Bundesliga', 53: 'Ligue_1'}
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
TEAM_COLS = ['league', 'season', 'date', 'team', 'h_a', 'xG', 'xGA', 'npxG', 'npxGA', 'scored', 'missed']
PM_COLS = ['pid', 'name', 'league', 'season', 'date', 'match_id', 'h_team', 'a_team', 'h_goals', 'a_goals',
           'position', 'time', 'goals', 'shots', 'xG', 'npg', 'npxG', 'xA', 'key_passes', 'xGChain', 'xGBuildup']
POS = {0: 'GK', 1: 'DC', 2: 'MC', 3: 'FW'}


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    return ' '.join(re.sub(r'[^a-z ]', ' ', s.replace('ø', 'o')).split())


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'user-agent': UA, 'accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:
            err = e; time.sleep(3 * (i + 1))
    raise err


def parse_match(mid):
    D = get(f'https://www.fotmob.com/api/data/matchDetails?matchId={mid}')
    H, A = (D.get('header') or {}).get('teams') or [{}, {}]
    C = D.get('content') or {}
    lu = C.get('lineup') or {}
    started, usual = set(), {}
    for side in ('homeTeam', 'awayTeam'):
        for p in (lu.get(side) or {}).get('starters') or []:
            started.add(p.get('id')); usual[p.get('id')] = p.get('usualPlayingPositionId')
        for p in (lu.get(side) or {}).get('subs') or []:
            usual[p.get('id')] = p.get('usualPlayingPositionId')
    shots = (C.get('shotmap') or {}).get('shots') or []
    pen_goals = Counter(s.get('playerId') for s in shots if s.get('situation') == 'Penalty' and s.get('eventType') == 'Goal' and not s.get('isOwnGoal'))
    txg = defaultdict(float); tnp = defaultdict(float)
    for s in shots:
        if s.get('isOwnGoal'): continue
        x = float(s.get('expectedGoals') or 0); txg[s.get('teamId')] += x
        if s.get('situation') != 'Penalty': tnp[s.get('teamId')] += x
    players = []
    for pid, p in (C.get('playerStats') or {}).items():
        st = {}
        for g in p.get('stats') or []:
            for k, v in (g.get('stats') or {}).items():
                st[k] = ((v or {}).get('stat') or {}).get('value')
        mins = int(st.get('Minutes played') or 0)
        if mins <= 0: continue
        fid = int(p.get('id') or pid); g = int(st.get('Goals') or 0); pg = pen_goals.get(fid, 0)
        players.append(dict(fid=fid, name=p.get('name'), team_id=p.get('teamId'), time=mins,
                            started=fid in started, usual=usual.get(fid), goals=g, npg=g - pg,
                            shots=int(st.get('Total shots') or 0), xG=float(st.get('Expected goals (xG)') or 0),
                            npxG=float(st.get('xG Non-penalty') if st.get('xG Non-penalty') is not None else (st.get('Expected goals (xG)') or 0)),
                            xA=float(st.get('Expected assists (xA)') or 0), kp=int(st.get('Chances created') or 0)))
    return dict(mid=int(mid), h=dict(id=H.get('id'), name=H.get('name'), score=H.get('score')),
                a=dict(id=A.get('id'), name=A.get('name'), score=A.get('score')),
                xg={str(k): v for k, v in txg.items()}, npxg={str(k): v for k, v in tnp.items()}, players=players)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--season', type=int, required=True); ap.add_argument('--cache', default='fmcache')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True); os.makedirs(a.cache, exist_ok=True)
    bp = pd.read_csv(os.path.join(a.base, 'player_matches.csv.gz'))
    prev = bp[bp.season >= a.season - 1]
    by_name = defaultdict(set)
    for pid, n in bp.groupby('pid')['name'].first().items():
        by_name[norm(n)].add(int(pid))
    # base club of a pid in the newest base season: the side he appears for most in that season's rows
    side = {}
    for r in prev.itertuples():
        side.setdefault(r.pid, Counter())
    for r in prev.itertuples():
        side[r.pid][r.h_team] += 1; side[r.pid][r.a_team] += 1
    club_of = {pid: c.most_common(1)[0][0] for pid, c in side.items() if c}

    fixtures, fail = [], 0
    for lid, lg in LEAGUES.items():
        L = get(f'https://www.fotmob.com/api/data/leagues?id={lid}&ccode3=USA')
        want = f'{a.season}/{a.season + 1}'
        cur = (L.get('allAvailableSeasons') or [None])[0]
        if cur != want:
            L = get(f'https://www.fotmob.com/api/data/leagues?id={lid}&ccode3=USA&season={urllib.parse.quote(want)}')
        for m in ((L.get('fixtures') or {}).get('allMatches') or []):
            s = m.get('status') or {}
            if s.get('finished') and not s.get('cancelled') and not s.get('awarded'):
                fixtures.append((lg, m['id'], (s.get('utcTime') or '')[:10]))
    print(f'FotMob {a.season}: {len(fixtures)} finished league matches', flush=True)

    def load(f):
        lg, mid, d = f; p = os.path.join(a.cache, f'{mid}.json')
        if os.path.exists(p):
            return f, json.load(open(p))
        try:
            M = parse_match(mid); json.dump(M, open(p, 'w')); return f, M
        except Exception as e:
            return f, e
    got = []
    with ThreadPoolExecutor(8) as ex:
        for f, M in ex.map(load, fixtures):
            if isinstance(M, Exception):
                fail += 1; print(f'  ::warning::FotMob match {f[1]}: {str(M)[:100]}'); continue
            got.append((f, M))
    if fail > max(5, 0.05 * len(fixtures)):
        sys.exit(f'FotMob history too lossy: {fail} of {len(fixtures)} matches failed')

    # club names -> understat spelling, by majority vote of shared players
    votes = defaultdict(Counter)
    for (lg, mid, d), M in got:
        names = {M['h']['id']: M['h']['name'], M['a']['id']: M['a']['name']}
        for p in M['players']:
            pids = by_name.get(norm(p['name'])) or set()
            if len(pids) == 1:
                c = club_of.get(next(iter(pids)))
                if c: votes[names.get(p['team_id'])][c] += 1
    alias = {fm: c.most_common(1)[0][0] for fm, c in votes.items() if fm and c and c.most_common(1)[0][1] >= 3}
    print('  clubs mapped to understat spelling:', len(alias), '| kept FotMob spelling:',
          sorted({M[s]['name'] for _, M in got for s in ('h', 'a')} - set(alias)), flush=True)
    tn = lambda n: alias.get(n, n)

    T, P, synth = [], [], 0
    for (lg, mid, d), M in got:
        h, aw = M['h'], M['a']; hn, an = tn(h['name']), tn(aw['name'])
        hx, ax = M['xg'].get(str(h['id']), 0.0), M['xg'].get(str(aw['id']), 0.0)
        hnp, anp = M['npxg'].get(str(h['id']), 0.0), M['npxg'].get(str(aw['id']), 0.0)
        T.append([lg, a.season, d, hn, 'h', hx, ax, hnp, anp, h['score'], aw['score']])
        T.append([lg, a.season, d, an, 'a', ax, hx, anp, hnp, aw['score'], h['score']])
        for p in M['players']:
            club = hn if p['team_id'] == h['id'] else an
            c = by_name.get(norm(p['name'])) or set()
            same = [x for x in c if club_of.get(x) == club]
            pid = same[0] if len(same) == 1 else (next(iter(c)) if len(c) == 1 else None)
            if pid is None: pid = 10_000_000 + p['fid']; synth += 1
            pos = POS.get(p['usual'], 'MC') if p['started'] else 'Sub'
            P.append([pid, p['name'], lg, a.season, d, mid, hn, an, h['score'], aw['score'], pos, p['time'], p['goals'],
                      p['shots'], round(p['xG'], 4), p['npg'], round(p['npxG'], 4), round(p['xA'], 4), p['kp'], 0.0, 0.0])
    pd.DataFrame(T, columns=TEAM_COLS).to_csv(os.path.join(a.out, 'team_matches.csv.gz'), index=False)
    pd.DataFrame(P, columns=PM_COLS).to_csv(os.path.join(a.out, 'player_matches.csv.gz'), index=False)
    print(f'  wrote {len(T)} team rows, {len(P)} player rows ({synth} player-matches with no understat pid), '
          f'{len(got)} matches, latest {max(f[2] for f, _ in got) if got else None}')


if __name__ == '__main__':
    import urllib.parse
    main()
