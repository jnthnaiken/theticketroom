#!/usr/bin/env python3
"""nfl_settle.py -- SETTLENFL-2026-09-10. Grade finished football boards into nfl_season.json.

Owner, 2026-09-10: "well it was graded until you published the new board". The football room had
no settle step at all. nfl_live.js grades the tickets IN THE BROWSER and saves nothing, so a night
stayed "graded" only as long as its board was the one on the page, and the moment the next
slate's board published (Thursday replacing Wednesday's opener) the result was gone, and
nfl_season.json never heard about it. Soccer solved the same problem with boards/<date>.json +
soccer_grade.fold(); this is that, for football:

    nfl-build.yml Publish     archives every published board as  nfl/boards/<date>.json
    this file, every build    for each archived board NOT in nfl_season.json graded_nights whose
                              games are all FINAL on ESPN: mark scorers (hr) and scratches (out),
                              stamp meta.finals, and fold it with soccer_grade.fold() -- the same
                              grader, stake rules and ledger shape the soccer room uses.

THE SETTLE RULES ARE nfl_live.js's, not new ones (read its header before changing either):
  * a TD is any box-score column ending in `touchdowns` EXCEPT the passing group. A QB throwing
    one does not settle his anytime-TD leg; running one in does.
  * absence from an NFL box score is NOT absence from the game (a WR can play 60 snaps and never
    appear). A leg is voided only when ESPN's injury/inactive block says Out/Inactive/IR/... AND
    the man is not in the box score. A scorer is never voided.

    python3 nfl_settle.py [--season nfl_season.json] [--boards boards] [--slates slates]
Exit 0 always unless the arguments are wrong; a network miss leaves the night for the next build.
"""
import datetime, glob, io, json, os, re, sys, unicodedata, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, '..', 'soccer')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import soccer_grade                                    # ONE GRADER: fold() / grade_ticket()

ESPN = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/'
ALIAS = {'LA': 'LAR', 'WAS': 'WSH'}                    # nflverse -> ESPN abbreviations
OUT_STATUS = re.compile(r'^(out|injured reserve|suspension|suspended|inactive|physically unable|non football)', re.I)
_SUF = r'(?:jr|jnr|junior|sr|snr|senior|ii|iii|iv|v)'  # same vocabulary as nfl_mock.norm
GRACE_MIN = 200                                        # don't ask ESPN before last kickoff + 200 min


def norm(s):
    s = unicodedata.normalize('NFKD', str(s))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r'\s+' + _SUF + r'\.?\s*$', '', s.lower())
    return re.sub(r'[^a-z]', '', s)


def _getj(url):
    rq = urllib.request.Request(url, headers={'User-Agent': 'ticketroom-nfl-settle'})
    with urllib.request.urlopen(rq, timeout=30) as r:
        return json.load(r)


def box(summary):
    """-> (scored {norm: n}, appeared set(norm), out set(norm)) from one ESPN summary."""
    scored, seen, out = {}, set(), set()
    for tp in ((summary.get('boxscore') or {}).get('players') or []):
        for g in tp.get('statistics') or []:
            keys = g.get('keys') or []
            cols = [i for i, k in enumerate(keys) if re.search(r'[Tt]ouchdowns$', k)]
            for a in g.get('athletes') or []:
                nm = ((a.get('athlete') or {}).get('displayName'))
                if not nm:
                    continue
                n = norm(nm)
                seen.add(n)
                if g.get('name') == 'passing':
                    continue                           # THROWN, NEVER SCORED
                tds = 0
                for i in cols:
                    try:
                        tds += max(0, int((a.get('stats') or [])[i]))
                    except (ValueError, IndexError, TypeError):
                        pass
                if tds:
                    scored[n] = scored.get(n, 0) + tds
    for team in summary.get('injuries') or []:
        for inj in team.get('injuries') or []:
            st = str(inj.get('status') or ((inj.get('type') or {}).get('description')) or '')
            nm = (inj.get('athlete') or {}).get('displayName')
            if nm and OUT_STATUS.search(st):
                out.add(norm(nm))
    return scored, seen, out


def settle(board_path, season_path, slates_dir, getj=_getj, now_et=None):
    D = json.load(io.open(board_path, encoding='utf-8'))
    date = (D.get('meta') or {}).get('date')
    season = json.load(io.open(season_path, encoding='utf-8')) if os.path.exists(season_path) else {}
    if not date or date in (season.get('graded_nights') or []):
        return 'already'
    fxp = os.path.join(slates_dir, date, 'fixtures.json')
    fx = json.load(io.open(fxp, encoding='utf-8')) if os.path.exists(fxp) else {'matches': {}}
    kos = [m.get('kickoff') for m in (fx.get('matches') or {}).values() if isinstance(m.get('kickoff'), int)]
    now_et = now_et or (datetime.datetime.utcnow() - datetime.timedelta(hours=4))
    if kos:
        ready = datetime.datetime.strptime(date, '%Y-%m-%d') + datetime.timedelta(minutes=max(kos) + GRACE_MIN)
        if now_et < ready:
            return 'too early'
    # which games does the board actually carry? (game index -> "AWAY@HOME")
    games = {}
    for p in D['players'].values():
        if p.get('game') is not None and p.get('gmatch'):
            games[p['game']] = p['gmatch']
    try:
        sb = getj(ESPN + 'scoreboard?dates=' + date.replace('-', ''))
    except Exception as e:
        print(f'  {date}: scoreboard unreachable ({str(e)[:80]}) -- left for the next build')
        return 'network'
    events = {}
    for ev in sb.get('events') or []:
        comp = (ev.get('competitions') or [{}])[0]
        side = {c.get('homeAway'): (c.get('team') or {}).get('abbreviation') for c in comp.get('competitors') or []}
        done = bool((((comp.get('status') or ev.get('status') or {}).get('type')) or {}).get('completed'))
        events[(side.get('away'), side.get('home'))] = (ev.get('id'), done)
    scored, seen, out, finals, missing = {}, set(), set(), [], []
    for gi, gm in sorted(games.items()):
        away, home = gm.split('@')
        hit = events.get((ALIAS.get(away, away), ALIAS.get(home, home)))
        if not hit:
            missing.append(gm); continue
        eid, done = hit
        if not done:
            print(f'  {date}: {gm} not final yet -- not settling'); return 'not final'
        try:
            s, a, o = box(getj(ESPN + 'summary?event=' + str(eid)))
        except Exception as e:
            print(f'  {date}: summary {eid} unreachable ({str(e)[:80]})'); return 'network'
        for k, v in s.items():
            scored[k] = scored.get(k, 0) + v
        seen |= a; out |= o
        finals.append(gi)
    if missing:
        print(f'  ::warning::{date}: no ESPN event for {missing} -- not settling'); return 'unmatched'
    nscore = nvoid = 0
    for nm, p in D['players'].items():
        n = norm(nm)
        if n in scored:
            p['hr'] = True; p['out'] = False; nscore += 1
        else:
            p['hr'] = False
            if n in out and n not in seen:
                p['out'] = True; nvoid += 1
    D['meta']['finals'] = finals
    json.dump(D, io.open(board_path, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print(f'  {date}: {len(finals)} final game(s), {nscore} priced scorer(s), {nvoid} void(s)')
    soccer_grade.fold(board_path, season_path)
    return 'graded'


if __name__ == '__main__':
    a = sys.argv
    opt = lambda k, d: a[a.index(k) + 1] if k in a else d
    sp = opt('--season', os.path.join(HERE, 'nfl_season.json'))
    bd = opt('--boards', os.path.join(HERE, 'boards'))
    sl = opt('--slates', os.path.join(HERE, 'slates'))
    for b in sorted(glob.glob(os.path.join(bd, '*.json'))):
        try:
            print(f'{os.path.basename(b)}: {settle(b, sp, sl)}')
        except Exception as e:                          # never take the board build down
            print(f'::warning::settle {os.path.basename(b)} failed: {str(e)[:160]}')
