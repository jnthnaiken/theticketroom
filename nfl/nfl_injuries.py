#!/usr/bin/env python3
"""nfl_injuries.py -- INJOUT-2026-09-11. A player ESPN lists as OUT cannot be drafted.

Owner, 2026-09-11: "why is bowers in a ticket lmao hes out and theres plenty of time to redraft".
Brock Bowers was Out on the Raiders' injury report two days before kickoff and sat on a live moon
("Money Down"), because the server draft never read an injury report at all. nfl_live.js marks
inactives on the PAGE from 90 minutes out (INACTIVES-2026-09-09), but that is display only -- the
football room has no client re-draft -- and the build, which fresh-drafts every pass until the
slate's games start, drafted him every time.

WHAT IT DOES. Runs between nfl_mock.py and nfl_draft_cli.js. For the slate's date it reads ESPN's
scoreboard, then each game's summary `injuries` block, and sets `out: true` on every scored.json
row whose team lists him with a DEFINITE status. soccer_draft.js already refuses `out` men at every
entry point (buildPool / placeable / pinnable / alive[]), so nothing else has to change; the payload
already carries `out` to the page.

⚠️ DEFINITE ONLY -- the same OUT_STATUS nfl_settle.py and nfl_live.js use: Out, Injured Reserve,
Suspended, Inactive, PUP, Non-Football. QUESTIONABLE and DOUBTFUL are NOT out. A Questionable man
plays more often than not, and the inactives list 90 minutes out is what settles it (nfl_live.js).

⚠️ MATCHED BY TEAM, not name alone. nflverse and ESPN abbreviations differ (LA/LAR, WAS/WSH), and a
name-only match would scratch the wrong man whenever two rosters share a surname-free key.

⚠️ NEVER FATAL, NEVER CLEARS. A network miss leaves scored.json exactly as it was (and says so
loudly); a player is only ever ADDED to out here. The draft simply runs on what it has.

    python3 nfl_injuries.py scored.json fixtures.json
"""
import json, re, sys, unicodedata
import nfl_espn

ALIAS = {'LA': 'LAR', 'WAS': 'WSH', 'JAC': 'JAX', 'ARI': 'ARI'}   # nflverse -> ESPN
OUT_STATUS = re.compile(r'^(out|injured reserve|suspension|suspended|inactive|physically unable|non football)', re.I)
_SUF = r'(?:jr|jnr|junior|sr|snr|senior|ii|iii|iv|v)'


def norm(s):
    s = unicodedata.normalize('NFKD', str(s))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r'\s+' + _SUF + r'\.?\s*$', '', s.lower())
    return re.sub(r'[^a-z]', '', s)


def out_by_team(date, getj=nfl_espn.getj):
    """-> {ESPN team abbr: {norm(name): (displayName, status)}} for every game on `date`."""
    sb = getj(nfl_espn.ESPN + 'scoreboard?dates=' + date.replace('-', ''))
    res = {}
    for ev in sb.get('events') or []:
        s = getj(nfl_espn.ESPN + 'summary?event=' + str(ev.get('id')))
        for team in s.get('injuries') or []:
            ab = (team.get('team') or {}).get('abbreviation')
            for inj in team.get('injuries') or []:
                st = str(inj.get('status') or ((inj.get('type') or {}).get('description')) or '')
                nm = (inj.get('athlete') or {}).get('displayName')
                if ab and nm and OUT_STATUS.search(st):
                    res.setdefault(ab, {})[norm(nm)] = (nm, st)
    return res


def apply(scored, outs):
    hits = []
    for p in scored:
        ab = ALIAS.get(p.get('team'), p.get('team'))
        hit = (outs.get(ab) or {}).get(norm(p.get('name')))
        if hit and not p.get('out'):
            p['out'] = True
            p['out_why'] = hit[1]
            hits.append((p['name'], p.get('team'), hit[1], p.get('odds')))
    return hits


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('usage: nfl_injuries.py scored.json fixtures.json'); sys.exit(2)
    sp, fp = sys.argv[1], sys.argv[2]
    scored = json.load(open(sp, encoding='utf-8'))
    date = json.load(open(fp, encoding='utf-8')).get('date')
    try:
        outs = out_by_team(date)
    except Exception as e:
        print(f'::warning::nfl_injuries: ESPN injury report unreachable ({str(e)[:120]}) -- drafting without it')
        sys.exit(0)
    hits = apply(scored, outs)
    json.dump(scored, open(sp, 'w', encoding='utf-8'), indent=1)
    n = sum(len(v) for v in outs.values())
    print(f'nfl_injuries {date}: {n} definite-out listings across {len(outs)} teams; '
          f'{len(hits)} priced player(s) scratched')
    for nm, tm, st, od in hits:
        print(f'  OUT  {nm} ({tm}) {st}  {od:+d}' if isinstance(od, int) else f'  OUT  {nm} ({tm}) {st}')
