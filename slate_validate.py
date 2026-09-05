#!/usr/bin/env python3
"""
slate_validate.py — pre-commit gate for a Ticket Room slate.

Checks the five dated input files against the contract that build15.py actually
consumes (see build15.py header + gamemeta/wx construction). Run this BEFORE
committing/pushing a slate. Exit code 0 = safe to build, 1 = do NOT commit.

Usage:
    python3 slate_validate.py 2026-07-21            # explicit date
    python3 slate_validate.py                        # newest cards_*.json
    python3 slate_validate.py 2026-07-21 --dir /tmp/ttbuild21

This exists because on 2026-07-21 a mid-build container reclaim forced the
assembler to be rebuilt from memory, and three format regressions slipped
through that this validator is designed to catch:
  1. lineups written as a bare list instead of {"games":[...]}  -> build15 crash
  2. precip/temp emitted as strings instead of ints            -> wx/skew bugs
  3. gn hardcoded to 1 for every game (must be unique per game) -> wx key
     collision, ticket renderer crash "Cannot read properties of undefined
     (reading 'emoji')", header/date + tiles fall back to defaults.
"""
import json, os, sys, glob, unicodedata

def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s or '')
                   if not unicodedata.combining(c)).lower().replace('.', '').strip()

# DROPSCOPE-2026-09-05: a permanently-excluded bat must not survive anywhere in a slate.
# The assembler prunes him; this is the independent check that it actually ran, so a
# hand-rolled or half-reassembled slate can never quietly put him back in the pool.
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from slate_assemble import DROP_BATS, tc
except Exception:                       # validator must still run standalone
    DROP_BATS, tc = set(), (lambda c: (c or '').upper())

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    base = '.'
    if '--dir' in sys.argv:
        base = sys.argv[sys.argv.index('--dir') + 1]
    date = args[0] if args else None
    if not date:
        ds = sorted(re.findall(r'cards_(\d{4}-\d{2}-\d{2})\.json', '\n'.join(
            glob.glob(os.path.join(base, 'cards_*.json'))))) if False else \
            sorted(os.path.basename(p)[6:16] for p in glob.glob(os.path.join(base, 'cards_*.json')))
        if not ds:
            print("FATAL: no cards_*.json found in", base); return 1
        date = ds[-1]

    errors, warnings = [], []
    def E(m): errors.append(m)
    def W(m): warnings.append(m)

    def load(kind):
        p = os.path.join(base, f"{kind}_{date}.json")
        if not os.path.exists(p):
            E(f"missing file: {kind}_{date}.json"); return None
        try:
            return json.load(open(p))
        except Exception as ex:
            E(f"{kind}_{date}.json is not valid JSON: {ex}"); return None

    cards   = load('cards')
    lineups = load('lineups')
    odds    = load('odds')
    pitch   = load('pitchers')
    extras  = load('kasper_extras')
    if errors:  # can't proceed without files
        report(date, errors, warnings); return 1

    # ---- cards: {MATCHUP:{TEAM:[{name,...}]}} ----
    if not isinstance(cards, dict) or not cards:
        E("cards must be a non-empty object {MATCHUP:{TEAM:[...]}}")
    carded = {}  # matchup -> set(norm names)
    if isinstance(cards, dict):
        for mk, teams in cards.items():
            if '@' not in mk: E(f"cards key not a matchup: {mk!r}")
            if not isinstance(teams, dict): E(f"cards[{mk}] must be a team->list object"); continue
            names = set()
            for tk, arr in teams.items():
                if not isinstance(arr, list): E(f"cards[{mk}][{tk}] must be a list"); continue
                for c in arr:
                    if not isinstance(c, dict) or 'name' not in c:
                        E(f"cards[{mk}][{tk}] has a card with no name"); continue
                    names.add(norm(c['name']))
            carded[mk] = names

    # ---- odds: {name: american int} ----
    if not isinstance(odds, dict) or not odds:
        E("odds must be a non-empty object {name: american}")
    else:
        for k, v in list(odds.items())[:99999]:
            if not isinstance(v, (int, float)):
                E(f"odds[{k!r}] must be a number, got {type(v).__name__}"); break

    # ---- pitchers: {name:{brl,pbrl,hh,fb}} ----
    if not isinstance(pitch, dict):
        E("pitchers must be an object {name:{brl,pbrl,hh,fb}}")
    pitch_norm = {norm(k) for k in (pitch or {})}

    # ---- kasper_extras: {name:{...}} ----
    if not isinstance(extras, dict):
        E("kasper_extras must be an object {name:{...}}")

    # ---- lineups: {games:[...]}  (THE big one) ----
    if not isinstance(lineups, dict):
        E(f"lineups must be an OBJECT with a 'games' key, got {type(lineups).__name__}. "
          f"A bare list [...] crashes build15 at lin['games'].")
    else:
        if 'date' in lineups and lineups['date'] != date:
            W(f"lineups.date={lineups['date']!r} but filename date is {date}")
        games = lineups.get('games')
        if not isinstance(games, list) or not games:
            E("lineups.games must be a non-empty list")
        else:
            gns = []
            REQ = ['gn','matchup','away','home','time','status','away_sp','home_sp',
                   'dome','precip','temp','wind','away_bats','away_hands','home_bats','home_hands']
            for i, g in enumerate(games):
                tag = f"lineups.games[{i}]"
                if not isinstance(g, dict):
                    E(f"{tag} must be an object"); continue
                for k in REQ:
                    if k not in g: E(f"{tag} ({g.get('matchup','?')}) missing key '{k}'")
                mk = g.get('matchup', '')
                tag = f"{mk}"
                # types that, if wrong, break build15/frontend
                if not isinstance(g.get('gn'), int):
                    E(f"{tag}: gn must be an int (got {g.get('gn')!r}); it keys the weather map")
                else:
                    gns.append(g['gn'])
                if not isinstance(g.get('precip'), (int, float)) or isinstance(g.get('precip'), bool):
                    E(f"{tag}: precip must be a number (build15 does precip<30), got {g.get('precip')!r}")
                if not isinstance(g.get('temp'), (int, float)) or isinstance(g.get('temp'), bool):
                    E(f"{tag}: temp must be a number, got {g.get('temp')!r}")
                if not isinstance(g.get('wind'), str):
                    E(f"{tag}: wind must be a string (e.g. '13 mph L-R' or 'Dome'), got {g.get('wind')!r}")
                if not isinstance(g.get('dome'), bool):
                    W(f"{tag}: dome should be a bool")
                for spk in ('away_sp', 'home_sp'):
                    sp = g.get(spk)
                    if not (isinstance(sp, list) and len(sp) == 2 and isinstance(sp[0], str)):
                        E(f"{tag}: {spk} must be [name, hand]; got {sp!r}")
                for bk, hk in (('away_bats','away_hands'), ('home_bats','home_hands')):
                    b, h = g.get(bk), g.get(hk)
                    if not isinstance(b, list) or not isinstance(h, list):
                        E(f"{tag}: {bk}/{hk} must be lists")
                    elif len(b) != len(h):
                        E(f"{tag}: {bk} ({len(b)}) and {hk} ({len(h)}) length mismatch")
                # matchup must be a real carded game
                if mk and mk not in carded:
                    E(f"{tag}: lineup matchup not present in cards_{date}.json")
                else:
                    for team in (g.get('away'), g.get('home')):
                        if isinstance(cards, dict) and team not in cards.get(mk, {}):
                            W(f"{tag}: team {team} has no card block in cards[{mk}]")
                # SP / bat coverage (soft)
                for who, sp in (('away', (g.get('away_sp') or [None])[0]),
                                ('home', (g.get('home_sp') or [None])[0])):
                    if sp and norm(sp) not in pitch_norm:
                        W(f"{tag}: {who} SP {sp!r} has no pitcher stats (fallback used)")
                cn = carded.get(mk, set())
                for nm in (g.get('away_bats') or []) + (g.get('home_bats') or []):
                    if norm(nm) not in cn:
                        W(f"{tag}: uncarded lineup bat {nm} (dropped by scorer)")
            # THE gn-collision check (today's core bug)
            if len(gns) != len(set(gns)):
                dup = sorted(x for x in set(gns) if gns.count(x) > 1)
                E(f"gn values are NOT unique (duplicates {dup}). build15 keys gamemeta/wx by "
                  f"str(gn); collisions drop games and crash the ticket renderer on wx.emoji.")

    # ---- permanent exclusions must not survive anywhere (DROPSCOPE-2026-09-05) ----
    if DROP_BATS:
        for bad_tm, bad_nm in sorted(DROP_BATS):
            bad_tm = tc(bad_tm)
            if isinstance(cards, dict):
                for mk, teams in cards.items():
                    for tk, arr in (teams or {}).items():
                        if tc(tk) != bad_tm or not isinstance(arr, list):
                            continue
                        if any(isinstance(c, dict) and c.get('name') == bad_nm for c in arr):
                            E(f"permanently-excluded bat {bad_tm} {bad_nm} is still in "
                              f"cards[{mk}][{tk}] — slate_assemble.drop_excluded did not run")
            if isinstance(lineups, dict):
                for g in (lineups.get('games') or []):
                    if not isinstance(g, dict):
                        continue
                    for side, bk in (('away', 'away_bats'), ('home', 'home_bats')):
                        if tc(g.get(side)) == bad_tm and bad_nm in (g.get(bk) or []):
                            E(f"permanently-excluded bat {bad_tm} {bad_nm} is still in "
                              f"{g.get('matchup','?')}.{bk} — he would take a lineup slot and be "
                              f"scored off the surviving team's card")
            # extras/odds are name-keyed: flag only when NO kept bat carries the name, which
            # means whatever is there can only be the excluded player's numbers.
            kept = any(isinstance(c, dict) and c.get('name') == bad_nm
                       for mk, teams in (cards or {}).items()
                       for tk, arr in (teams or {}).items() if isinstance(arr, list)
                       for c in arr)
            if not kept:
                if isinstance(extras, dict) and bad_nm in extras:
                    E(f"kasper_extras[{bad_nm!r}] survives with no kept card — those are the "
                      f"excluded {bad_tm} bat's numbers")
                if isinstance(odds, dict) and bad_nm in odds:
                    W(f"odds[{bad_nm!r}] survives with no kept card (inert, but the scrape "
                      f"should not have kept the excluded {bad_tm} row)")

    report(date, errors, warnings)
    return 1 if errors else 0

def report(date, errors, warnings):
    print(f"=== slate_validate {date} ===")
    if warnings:
        print(f"\n{len(warnings)} warning(s) (non-blocking):")
        for w in warnings[:60]: print("  ⚠", w)
        if len(warnings) > 60: print(f"  … +{len(warnings)-60} more")
    if errors:
        print(f"\n{len(errors)} ERROR(s) — DO NOT COMMIT until fixed:")
        for e in errors: print("  ✗", e)
        print("\nRESULT: FAIL")
    else:
        print("\nRESULT: PASS — safe to commit + build")

import re  # used lazily above
if __name__ == '__main__':
    sys.exit(main())
