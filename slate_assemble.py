#!/usr/bin/env python3
"""
slate_assemble.py — CANONICAL assembler: scraped intermediates -> the 5 dated
input files build15.py consumes. Keep this in the repo so it is NEVER rebuilt
from memory again (that is how 2026-07-21 shipped three format bugs).

Reads five raw intermediates produced by the daily browser scrape+transfer
(names are the session convention; adjust --dir if you stage them elsewhere):
    cards.json    {MATCHUP:{TEAM:[{name,form_pct,form_arrow,pb,hh,la,zone,test}]}}   (Kasper)
    extras.json   {name:{khr,...}}                                                    (Kasper)
    pitch.json    {name:{brl,pbrl,hh,fb, csw,swstr,cs,ball,xwoba,la,bip,pit,
                         vR:{...},vL:{...}}}                                          (Kasper)
                  ^ csw/swstr + the vR/vL platoon splits added 2026-08-23 by
                    kasper_pitch_scrape.js. STRICTLY ADDITIVE: brl/pbrl/hh/fb keep their names
                    and meaning, this file passes the dict through verbatim, and slate_validate
                    only checks that starters resolve. build15 scores the flat fields only; the
                    splits are collected so the platoon matchup becomes measurable later
                    without a re-scrape.
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

# ---- PERMANENT ROSTER EXCLUSIONS (owner's call) ----------------------------------
# `cards`, `kasper_extras` and `odds` are all keyed by NAME ALONE, so two bats sharing a
# name cannot both be represented: build15 does `players[name]=...` and the later matchup in
# gn order silently wins (documented 2026-08-12, and it bit again on 2026-08-17 when
# VegasInsider posted a single "Max Muncy" row at LAD's price that ATH's Muncy inherited).
# Until players are keyed by (name, team) this is the deliberate fix for the one collision
# we actually have: drop the bat we will never draft, so the survivor is unambiguous and the
# outcome no longer depends on scrape/iteration order.
#   (TEAM, NAME) -> dropped from EVERY name-keyed surface before anything downstream sees it.
DROP_BATS = {('ATH', 'Max Muncy')}      # 2026-08-17: keep LAD's Max Muncy, never the Athletics'
DROP_CARDS = DROP_BATS                  # back-compat alias; the exclusion is no longer cards-only

def drop_excluded(cards, extras=None, roto=None):
    """Remove permanently-excluded bats from every surface build15 reads.

    ⚠️ DROPSCOPE-2026-09-05 — the 2026-08-17 implementation pruned `cards` ONLY, and the owner's
    instruction was that the bat is out of the pool, full stop. Pruning cards alone left two
    silent leaks, both of which score the wrong player with no warning anywhere:

      * `kasper_extras` is keyed by NAME ALONE, so whichever matchup page the daily scrape
        visited LAST owned the entry. On 2026-09-05 ATH@SEA is game 15 and WSH@LAD is game 14,
        so the Athletics' Muncy overwrote the Dodgers': khr 45 vs 54, bip 226 vs 1382,
        iso .171 vs .244, xwobacon .329 vs .424 — every column materially wrong, feeding
        `_ziso`, `_zxwcon` and `_zdmg` for a bat the board actually drafts.
      * `lineups` still listed him whenever the Athletics started him, so an ATH lineup slot
        would be scored off the SURVIVING team's card and extras entirely.

    Extras entries may now carry an optional "team" (stripped before write). An untagged entry
    for an excluded name is resolved when only one of the colliding teams is on the slate, and
    is a HARD ERROR when both are — it must never be guessed again.

    Returns (cards, extras, roto, [dropped], [errors]).
    """
    dropped, errs = [], []
    extras = {} if extras is None else extras
    roto = [] if roto is None else roto

    drop_by_name = {}
    for tm, nm in DROP_BATS:
        drop_by_name.setdefault(nm, set()).add(tc(tm))

    slate_teams = set()
    for g in roto:
        slate_teams.add(tc(g.get('away'))); slate_teams.add(tc(g.get('home')))

    # 1) cards
    for mk, teams in cards.items():
        for tm, bats in list(teams.items()):
            keep = [b for b in bats if (tc(tm), b.get('name')) not in DROP_BATS]
            if len(keep) != len(bats):
                dropped += [f"cards {tc(tm)} {b['name']} ({mk})" for b in bats if b not in keep]
                teams[tm] = keep

    # which teams still card each name, AFTER the prune above
    survivors = {}
    for mk, teams in cards.items():
        for tm, bats in teams.items():
            for b in bats:
                survivors.setdefault(b.get('name'), set()).add(tc(tm))

    # 2) lineups — an excluded bat must never occupy a lineup slot
    for g in roto:
        for side, bk in (('away', 'away_bats'), ('home', 'home_bats')):
            tm, arr = tc(g.get(side)), (g.get(bk) or [])
            keep = [b for b in arr if (tm, b.get('name')) not in DROP_BATS]
            if len(keep) != len(arr):
                dropped += [f"lineup {tm} {b['name']}" for b in arr if b not in keep]
                g[bk] = keep

    # 3) extras — name-keyed, so resolve through the optional team tag
    for nm, bad_teams in drop_by_name.items():
        e = extras.get(nm)
        if e is None:
            continue
        tag = tc(e.get('team')) if isinstance(e, dict) and e.get('team') else None
        if tag:
            if tag in bad_teams:
                extras.pop(nm)
                dropped.append(f"extras {tag} {nm}")
            continue
        others = survivors.get(nm, set()) - bad_teams
        if not others:
            extras.pop(nm)            # nobody we keep carries this name
            dropped.append(f"extras {nm} (no surviving card)")
        elif bad_teams & slate_teams:
            errs.append(
                f"kasper_extras[{nm!r}] is UNTAGGED and AMBIGUOUS: excluded "
                f"{'/'.join(sorted(bad_teams))} is on this slate alongside kept "
                f"{'/'.join(sorted(others))}, so the entry may be either bat's. The daily scrape "
                f"must emit \"team\" on extras entries (see HANDOFF) — refusing to guess.")

    for e in extras.values():         # strip the transport-only tag
        if isinstance(e, dict):
            e.pop('team', None)

    return cards, extras, roto, dropped, errs

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print("usage: slate_assemble.py <YYYY-MM-DD> [--dir DIR]"); return 2
    date = args[0]
    base = sys.argv[sys.argv.index('--dir')+1] if '--dir' in sys.argv else '.'
    J = lambda n: json.load(open(os.path.join(base, n)))
    cards, extras, pitch, roto, odds = (J('cards.json'), J('extras.json'),
                                        J('pitch.json'), J('roto.json'), J('odds.json'))

    cards, extras, roto, _dropped, _derrs = drop_excluded(cards, extras, roto)
    for _d in _dropped:
        print(f"  excluded (permanent): {_d}")

    pitch_norm = {norm(k): k for k in pitch}
    surname = {}
    for k in pitch: surname.setdefault(norm(k).split()[-1] if norm(k) else '', []).append(k)
    def resolve_sp(name):
        """RotoWire abbreviates a starter ("G. Rodriguez"); Kasper spells him out. Match on
        surname to recover the full name -- but ONLY when the first names are compatible.

        SPFIRST-2026-08-22: the surname fallback used to accept ANY lone surname match, so a
        starter Kasper never listed was silently renamed to a DIFFERENT pitcher who happened to
        share his last name. Today SEA's Kade Anderson became DET's Drew Anderson: CHC's nine
        bats would have been scored against the wrong arm's barrel profile, and slate_validate's
        "no pitcher stats" warning was suppressed because the wrong name resolved cleanly.
        Surnames like Anderson / Perez / Rodriguez / Sanchez make this a recurring hazard.

        A match now requires the roto first token to be either an INITIAL of the candidate's
        first name ("g" or "g." vs "grayson") or the same first name. Anything else keeps the
        roto name, which is the correct outcome: an arm Kasper does not cover falls back to
        live HR/9, and the validator says so."""
        if not name: return None
        n = norm(name)
        if n in pitch_norm: return pitch_norm[n]
        parts = n.split()
        if len(parts) < 2: return name
        cand = surname.get(parts[-1], [])
        if len(cand) != 1: return name
        want, got = parts[0].rstrip('.'), norm(cand[0]).split()[0]
        if want == got or (len(want) == 1 and got.startswith(want)):
            return cand[0]
        return name                       # different person, same surname -> keep roto name

    games, errors, gn = [], list(_derrs), 0
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
