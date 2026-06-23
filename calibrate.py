#!/usr/bin/env python3
"""
Nightly per-bat outcome logger  ->  calibration.jsonl

Run the morning AFTER a slate finalizes:   python calibrate.py 2026-06-22
Reads D_<date>.json (the scored board) + MLB StatsAPI boxscores and appends one
row per scored bat: every model input + did-he-homer (1/0). This is the dataset
we never had -- after ~2-3 weeks it's enough to FIT the weights (logistic
regression on hr ~ powidx + iso + zone + form + hr9 + parkhr + wf) instead of
guessing at multipliers. Bats are matched to real HRs by normalized name (the
same convention the live grader uses), so run it once the real slate is final.
"""
import json, sys, os, re, unicodedata, urllib.request

SA  = "https://statsapi.mlb.com/api/v1"
OUT = "calibration.jsonl"

def norm(s):
    s = unicodedata.normalize('NFKD', s or '')
    return ''.join(c for c in s if not unicodedata.combining(c)).lower().replace('.', '').replace(' ', '').strip()

def getj(u):
    with urllib.request.urlopen(u, timeout=30) as r:
        return json.load(r)

def homers_and_finals(date):
    """(set of norm(name) who homered in FINAL games, n_final, n_games)."""
    sch   = getj(f"{SA}/schedule?sportId=1&date={date}&hydrate=team")
    dates = sch.get('dates') or []
    games = dates[0].get('games', []) if dates else []
    homered, n_final = set(), 0
    for g in games:
        st = g.get('status') or {}
        ds, ab = st.get('detailedState', ''), st.get('abstractGameState', '')
        if not (re.search('final|completed|over', ds, re.I) or (ab or '').lower() == 'final'):
            continue                                   # not done -> don't grade its bats yet
        n_final += 1
        try:
            bx = getj(f"{SA}/game/{g['gamePk']}/boxscore")
        except Exception:
            continue
        for side in ('home', 'away'):
            tp = ((bx.get('teams') or {}).get(side) or {}).get('players') or {}
            for pl in tp.values():
                b = (pl.get('stats') or {}).get('batting') or {}
                if b.get('homeRuns', 0) and pl.get('person'):
                    homered.add(norm(pl['person']['fullName']))
    return homered, n_final, len(games)

def build_rows(D, homered):
    """Pure (testable): turn a scored board + HR set into per-bat rows."""
    P    = D['players']
    pool = set(D.get('pool', []))
    onkind = {}
    for t in D.get('tickets', []):
        for l in t.get('players', []):
            onkind.setdefault(l['name'], t['kind'])
    rows = []
    for n, p in P.items():
        if p.get('out') or p.get('void'):
            continue                                   # didn't play / postponed -> no outcome
        rows.append({
            "date": D.get('meta', {}).get('date'), "name": n, "code": p.get('code'),
            "hr": 1 if norm(p.get('nm', n)) in homered else 0,
            "pool": n in pool, "kind": onkind.get(n),
            "aT": p.get('aT'), "powidx": p.get('powidx'), "iso": p.get('iso_used'),
            "zone": p.get('zonev'), "form": p.get('form'), "hh": p.get('hh'), "la": p.get('la'),
            "pb": p.get('pb'), "hr9": p.get('hr9'), "phr9": p.get('phr9'), "parkhr": p.get('parkhr'),
            "wf": p.get('wf'), "odds": p.get('odds'), "total": p.get('TOTAL'),
        })
    return rows

def main(date):
    dfile = f"D_{date}.json"
    if not os.path.exists(dfile):
        sys.exit(f"!! no {dfile} to log")
    D = json.load(open(dfile))
    homered, n_final, n_games = homers_and_finals(date)
    if n_final == 0:
        sys.exit(f"{date}: no final games yet -- run again once the slate is complete")
    rows = build_rows(D, homered)
    with open(OUT, 'a') as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    hrs = sum(r['hr'] for r in rows)
    poolhrs = sum(r['hr'] for r in rows if r['pool'])
    print(f"{date}: logged {len(rows)} bats | {hrs} HR overall, {poolhrs} in our 33-pool "
          f"| {n_final}/{n_games} games final -> appended to {OUT}")
    if n_final < n_games:
        print(f"  note: {n_games - n_final} game(s) not final yet -- re-run later to capture them cleanly")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit("usage: python calibrate.py YYYY-MM-DD")
    main(sys.argv[1])
