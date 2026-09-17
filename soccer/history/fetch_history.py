#!/usr/bin/env python3
"""fetch_history.py -- SCORERHIST-2026-09-17. Pull the multi-season history the scorer model is
trained on. Runs in GitHub Actions (soccer-history.yml); the Claude session cannot reach these hosts.

Owner: "there is always order in chaos. you just need to find the correct data set or layer of data
sets. design an algorithm if needed" -> full build.

WHAT IT WRITES (out/, then committed to the `soccer-data` branch, never to main)
  team_matches.csv.gz    one row per team per league match: league, season, date, team, h_a,
                         xG, xGA, npxG, npxGA, scored, missed                     (understat)
  player_matches.csv.gz  one row per player per league match he appeared in: pid, name, league,
                         season, date, match_id, h_team, a_team, h_goals, a_goals, position, time,
                         goals, shots, xG, npg, npxG, xA, key_passes, xGChain, xGBuildup (understat)
  odds/<code>_<ssn>.csv  football-data.co.uk match results + closing 1X2 / over-under 2.5 prices,
                         raw, one file per league-season. This is the "team expected goals" layer.
  manifest.json          counts, failures, timings.

UNDERSTAT ACCESS. /getLeagueData and /getPlayerData answer JSON only to an XHR request
(`X-Requested-With: XMLHttpRequest`) from a session that has loaded a page; a bare GET returns the
HTML shell. Measured from a browser 2026-09-17. So the opener keeps a cookie jar and primes it with a
real page, and any HTML answer re-primes once and retries.

    python3 fetch_history.py --out out [--first 2014] [--last 2026] [--threads 6] [--limit N]
"""
import argparse, csv, gzip, http.cookiejar, io, json, os, sys, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

US = 'https://understat.com'
LEAGUES = ['EPL', 'La_liga', 'Bundesliga', 'Serie_A', 'Ligue_1']
FD = {'EPL': 'E0', 'La_liga': 'SP1', 'Bundesliga': 'D1', 'Serie_A': 'I1', 'Ligue_1': 'F1'}
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36'

_local = threading.local()


def opener():
    if not hasattr(_local, 'op'):
        jar = http.cookiejar.CookieJar()
        _local.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        _local.op.addheaders = [('User-Agent', UA), ('Accept-Language', 'en-US,en;q=0.9')]
        prime()
    return _local.op


def prime(path='/league/EPL'):
    try:
        _local.op.open(US + path, timeout=30).read()
    except Exception as e:
        print(f'  prime {path} failed: {e}', flush=True)


def get_json(path, referer, tries=4):
    op = opener()
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(US + path, headers={
                'X-Requested-With': 'XMLHttpRequest', 'Referer': US + referer,
                'Accept': 'application/json, text/javascript, */*; q=0.01'})
            body = op.open(req, timeout=60).read()
            txt = body.decode('utf-8', 'replace').lstrip()
            if txt.startswith('{') or txt.startswith('['):
                return json.loads(txt)
            last = 'html answer'
            prime(referer)
        except Exception as e:
            last = str(e)
        time.sleep(1.5 * (i + 1))
    raise RuntimeError(f'{path}: {last}')


def get_raw(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            return urllib.request.urlopen(req, timeout=60).read()
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f'{url}: {last}')


TEAM_COLS = ['league', 'season', 'date', 'team', 'h_a', 'xG', 'xGA', 'npxG', 'npxGA', 'scored', 'missed']
PM_COLS = ['pid', 'name', 'league', 'season', 'date', 'match_id', 'h_team', 'a_team', 'h_goals', 'a_goals',
           'position', 'time', 'goals', 'shots', 'xG', 'npg', 'npxG', 'xA', 'key_passes', 'xGChain', 'xGBuildup']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='out')
    ap.add_argument('--first', type=int, default=2014)
    ap.add_argument('--last', type=int, default=2026)
    ap.add_argument('--threads', type=int, default=6)
    ap.add_argument('--limit', type=int, default=0, help='cap players (smoke test)')
    a = ap.parse_args()
    os.makedirs(os.path.join(a.out, 'odds'), exist_ok=True)
    t0 = time.time()
    man = {'started': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'seasons': [a.first, a.last],
           'league_seasons': {}, 'player_fail': [], 'odds': {}}

    # ---- 1. league pages: team histories + the player id universe ------------------------------
    players = {}          # pid -> league where first seen (player matches carry their own league)
    trows = []
    for lg in LEAGUES:
        for s in range(a.first, a.last + 1):
            try:
                j = get_json(f'/getLeagueData/{lg}/{s}', f'/league/{lg}/{s}')
            except Exception as e:
                print(f'!! {lg} {s}: {e}', flush=True)
                man['league_seasons'][f'{lg}/{s}'] = 'FAIL'
                continue
            n = 0
            for t in (j.get('teams') or {}).values():
                for m in t.get('history') or []:
                    trows.append([lg, s, m['date'][:10], t['title'], m['h_a'], m['xG'], m['xGA'],
                                  m['npxG'], m['npxGA'], m['scored'], m['missed']])
                    n += 1
            for p in j.get('players') or []:
                players.setdefault(str(p['id']), lg)
            man['league_seasons'][f'{lg}/{s}'] = {'team_rows': n, 'players': len(j.get('players') or [])}
            print(f'  {lg} {s}: {n} team rows, {len(j.get("players") or [])} players', flush=True)
    with gzip.open(os.path.join(a.out, 'team_matches.csv.gz'), 'wt', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(TEAM_COLS)
        w.writerows(trows)
    print(f'team rows {len(trows)}; unique players {len(players)}  ({time.time() - t0:.0f}s)', flush=True)

    # ---- 2. every player's match log -----------------------------------------------------------
    pids = sorted(players, key=int)
    if a.limit:
        pids = pids[:a.limit]
    lg_of_match = {}
    rows_out = gzip.open(os.path.join(a.out, 'player_matches.csv.gz'), 'wt', newline='', encoding='utf-8')
    w = csv.writer(rows_out)
    w.writerow(PM_COLS)
    lock = threading.Lock()
    done = [0, 0]

    def one(pid):
        j = get_json(f'/getPlayerData/{pid}', f'/player/{pid}')
        name = (j.get('player') or {}).get('name', '')
        out = []
        for m in j.get('matches') or []:
            ssn = int(m.get('season') or 0)
            if ssn < a.first or ssn > a.last:
                continue
            out.append([pid, name, '', ssn, m['date'][:10], m['id'], m['h_team'], m['a_team'], m['h_goals'],
                        m['a_goals'], m['position'], m['time'], m['goals'], m['shots'], m['xG'], m['npg'],
                        m['npxG'], m['xA'], m['key_passes'], m['xGChain'], m['xGBuildup']])
        return out

    with ThreadPoolExecutor(a.threads) as ex:
        futs = {ex.submit(one, p): p for p in pids}
        for fu in as_completed(futs):
            pid = futs[fu]
            try:
                rs = fu.result()
                with lock:
                    w.writerows(rs)
                    done[0] += 1
                    done[1] += len(rs)
            except Exception as e:
                with lock:
                    man['player_fail'].append([pid, str(e)[:120]])
            if (done[0] + len(man['player_fail'])) % 500 == 0:
                print(f'  players {done[0]} ok / {len(man["player_fail"])} failed, rows {done[1]} '
                      f'({time.time() - t0:.0f}s)', flush=True)
    rows_out.close()
    man['players_ok'] = done[0]
    man['player_rows'] = done[1]

    # ---- 3. football-data.co.uk: results + closing market ---------------------------------------
    for lg, code in FD.items():
        for s in range(a.first, a.last + 1):
            ssn = f'{s % 100:02d}{(s + 1) % 100:02d}'
            url = f'https://www.football-data.co.uk/mmz4281/{ssn}/{code}.csv'
            try:
                b = get_raw(url)
                open(os.path.join(a.out, 'odds', f'{code}_{ssn}.csv'), 'wb').write(b)
                man['odds'][f'{code}_{ssn}'] = len(b)
            except Exception as e:
                man['odds'][f'{code}_{ssn}'] = f'FAIL {e}'[:120]
    man['seconds'] = round(time.time() - t0)
    json.dump(man, open(os.path.join(a.out, 'manifest.json'), 'w'), indent=1)
    print(json.dumps({k: v for k, v in man.items() if k not in ('league_seasons', 'odds')})[:2000])
    fails = len(man['player_fail'])
    if done[0] == 0 or fails > 0.05 * max(1, len(pids)):
        print(f'::error::player fetch too lossy: {done[0]} ok, {fails} failed')
        sys.exit(1)


if __name__ == '__main__':
    main()
