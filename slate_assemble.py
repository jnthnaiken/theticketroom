#!/usr/bin/env python3
"""
slate_assemble.py — CANONICAL assembler: scraped intermediates -> the 5 dated
input files build15.py consumes. Keep this in the repo so it is NEVER rebuilt
from memory again (that is how 2026-07-21 shipped three format bugs).

Reads five raw intermediates produced by the daily browser scrape+transfer
(names are the session convention; adjust --dir if you stage them elsewhere):
    cards.json    {MATCHUP:{TEAM:[{name,form_pct,form_arrow,pb,hh,la,zone,test}]}}   (Kasper)
    extras.json   {name:{khr,...}}                                                    (Kasper)
    pitch.json    {name:{brl,pbrl,hh,fb}}                                             (Kasper)
    roto.json     [{away,home,time,status,away_sp:{name,hand},home_sp,weather,
                    away_bats:[{name,pos,bats}],home_bats:[...]}]                      (RotoWire)
    odds.json     {name: american_int}                                               (VegasInsider, median)

Writes cards_<date>.json, kasper_extras_<date>.json, odds_<date>.json,
pitchers_<date>.json, lineups_<date>.json — then runs slate_validate.py and
REFUSES to leave broken output (exits 1 on any hard error).

Usage:
    python3 slate_assemble.py 2026-07-21 --dir /tmp/ttbuild21

Lineups contract (build15.py header + gamemeta/wx):
    {"date": <date>, "games": [ {
        gn:int (UNIQUE per game — keys the weather map, must be 1..N distinct),
        matchup, away, home, time, status,
        away_sp:[name,hand], home_sp:[name,hand],
        dome:bool, precip:int, temp:int, wind:str ("Dome" for dome games),
        away_bats:[names], away_hands:[hands], home_bats, home_hands } ] }
"""
import json, re, os, sys, unicodedata, subprocess

# Team-code normalization: RotoWire/VegasInsider -> the codes Kasper uses in cards keys.
TEAMMAP = {'ARI':'AZ','OAK':'ATH','SAC':'ATH','CHW':'CWS','WAS':'WSH',
           'SD':'SD','SDP':'SD','SFG':'SF','TBR':'TB','KCR':'KC',
           'AZ':'AZ','ATH':'ATH','CWS':'CWS','WSH':'WSH','SF':'SF','TB':'TB','KC':'KC'}
DOME = {'ARI','AZ','HOU','MIA','MIL','SEA','TB','TEX','TOR'}

def tc(c): c=(c or '').upper(); return TEAMMAP.get(c, c)
def norm(s):
    return ''.join(ch for ch in unicodedata.normalize('NFKD', s or '')
                   if not unicodedata.combining(ch)).lower().replace('.', '').strip()

def parse_weather(w, home):
    """RotoWire weather text -> (dome, precip:int, temp:int, wind:str). Types matter:
    build15 does `precip < 30`, so precip/temp MUST be ints, wind MUST be a string."""
    w = (w or '').strip()
    if re.search(r'dome', w, re.I) or home in DOME:
        return True, 0, 72, 'Dome'
    precip = int(re.search(r'(\d+)%', w).group(1)) if re.search(r'(\d+)%', w) else 0
    temp   = int(re.search(r'(\d+)\s*°', w).group(1)) if re.search(r'(\d+)\s*°', w) else 72
    m = re.search(r'Wind\s+(.+)$', w)
    return False, precip, temp, (m.group(1).strip() if m else '')

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print("usage: slate_assemble.py <YYYY-MM-DD> [--dir DIR]"); return 2
    date = args[0]
    base = sys.argv[sys.argv.index('--dir')+1] if '--dir' in sys.argv else '.'
    J = lambda n: json.load(open(os.path.join(base, n)))
    cards, extras, pitch, roto, odds = (J('cards.json'), J('extras.json'),
                                        J('pitch.json'), J('roto.json'), J('odds.json'))

    pitch_norm = {norm(k): k for k in pitch}
    surname = {}
    for k in pitch: surname.setdefault(norm(k).split()[-1] if norm(k) else '', []).append(k)
    def resolve_sp(name):
        if not name: return None
        n = norm(name)
        if n in pitch_norm: return pitch_norm[n]
        cand = surname.get(n.split()[-1] if n else '', [])
        return cand[0] if len(cand) == 1 else name  # else keep roto name (validator warns)

    games, errors, gn = [], [], 0
    seen = set()
    for g in roto:
        away, home = tc(g['away']), tc(g['home'])
        mk = f"{away}@{home}"
        if mk not in cards:
            errors.append(f"matchup {mk} (roto {g['away']}@{g['home']}) not in cards"); continue
        if mk in seen:  # doubleheader -> keep game 1 only
            continue
        seen.add(mk); gn += 1
        asp, hsp = (g.get('away_sp') or {}), (g.get('home_sp') or {})
        dome, precip, temp, wind = parse_weather(g.get('weather'), home)
        games.append({
            'matchup': mk, 'away': away, 'home': home,
            'time': g.get('time', ''),
            'status': 'confirmed' if re.search(r'confirm', g.get('status',''), re.I) else 'projected',
            'away_sp': [resolve_sp(asp.get('name')), asp.get('hand', '')],
            'home_sp': [resolve_sp(hsp.get('name')), hsp.get('hand', '')],
            'dome': dome, 'precip': precip, 'temp': temp, 'wind': wind,
            'away_bats':  [b['name'] for b in g.get('away_bats', [])],
            'away_hands': [b.get('bats','') for b in g.get('away_bats', [])],
            'home_bats':  [b['name'] for b in g.get('home_bats', [])],
            'home_hands': [b.get('bats','') for b in g.get('home_bats', [])],
            'gn': gn,   # UNIQUE per kept game
        })

    out = lambda n, o: json.dump(o, open(os.path.join(base, n), 'w'), indent=0)
    out(f"cards_{date}.json", cards)
    out(f"kasper_extras_{date}.json", extras)
    out(f"odds_{date}.json", odds)
    out(f"pitchers_{date}.json", pitch)
    out(f"lineups_{date}.json", {"date": date, "games": games})

    print(f"assembled {date}: {len(games)} games, {len(cards)} matchups, "
          f"{len(extras)} extras, {len(pitch)} pitchers, {len(odds)} odds")
    for e in errors: print("  ERR", e)

    # never leave broken output: gate on the validator
    vpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'slate_validate.py')
    if os.path.exists(vpath):
        rc = subprocess.call([sys.executable, vpath, date, '--dir', base])
        return 1 if (rc or errors) else 0
    print("WARNING: slate_validate.py not found next to assembler — validate manually!")
    return 1 if errors else 0

if __name__ == '__main__':
    sys.exit(main())
