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

Each row also carries the full Kasper stat set (k_* columns) when a
kasper_extras_<date>.json sidecar is present, so fly-ball%, sample size,
xwOBAcon, etc. are captured for fitting WITHOUT touching the live scorer.
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

def load_extras(date):
    """Load the kasper_extras_<date>.json sidecar (full Kasper stat set), or {} if absent.
    Looks in cwd first, then alongside this script (so grade_night on the Action finds it too)."""
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (f"kasper_extras_{date}.json", os.path.join(here, f"kasper_extras_{date}.json")):
        try:
            return json.load(open(p))
        except Exception:
            continue
    return {}

def load_pitchers(date):
    """Load pitchers_<date>.json (the opposing-SP allowed-contact sidecar), keyed by norm(name).
    Holds the pitcher EQUIVALENTS of our batter power stats -- pulled-barrel% (pbrl) and barrel%
    (brl) allowed today; hard-hit% (hh) and fly-ball% (fb) and xwOBA allowed added going forward.
    We join these onto each batter via their opposing starter so we can later test the matchup
    crossovers (batter pull-barrel x pitcher pull-barrel-allowed, etc.)."""
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (f"pitchers_{date}.json", os.path.join(here, f"pitchers_{date}.json")):
        try:
            raw = json.load(open(p))
            return {norm(k): v for k, v in raw.items()}
        except Exception:
            continue
    return {}

def build_rows(D, homered, extras=None, pstats=None):
    """Pure (testable): turn a scored board + HR set into per-bat rows.

    `extras` (optional) is the kasper_extras_<date>.json sidecar -- the full Kasper
    stat set per hitter (fly-ball%, sample size, xwOBAcon, etc.), keyed by norm(name).
    Its fields are merged onto each row under `k_*` columns so we can fit them in
    later WITHOUT touching the live scorer (build15). Missing/unmatched bats just
    leave those columns null -- the row is still logged.
    """
    P    = D['players']
    pool = set(D.get('pool', []))
    extras = extras or {}
    pstats = pstats or {}
    KX = ("fb", "sweet", "xwobacon", "xwoba", "brl_bip", "swstr",
          "kstrk", "bip", "pitch", "ceiling", "khr", "likely")   # Kasper-extra columns
    onkind = {}
    for t in D.get('tickets', []):
        for l in t.get('players', []):
            onkind.setdefault(l['name'], t['kind'])
    rows = []
    for n, p in P.items():
        if p.get('out') or p.get('void'):
            continue                                   # didn't play / postponed -> no outcome
        row = {
            "date": D.get('meta', {}).get('date'), "name": n, "code": p.get('code'),
            "hr": 1 if norm(p.get('nm', n)) in homered else 0,
            "pool": n in pool, "kind": onkind.get(n),
            "aT": p.get('aT'), "powidx": p.get('powidx'), "iso": p.get('iso_used'),
            "zone": p.get('zonev'), "form": p.get('form'), "hh": p.get('hh'), "la": p.get('la'),
            "pb": p.get('pb'), "hr9": p.get('hr9'), "phr9": p.get('phr9'), "parkhr": p.get('parkhr'),
            "wf": p.get('wf'), "odds": p.get('odds'), "total": p.get('TOTAL'),
        }
        ex = extras.get(norm(p.get('nm', n))) or {}
        for k in KX:
            row["k_" + k] = ex.get(k)
        # opposing-pitcher allowed-contact (matchup crossover features); pitcher = p['opp'][0]
        ps = pstats.get(norm((p.get('opp') or [None])[0] or '')) or {}
        for pk in ("pbrl", "hh", "fb"):   # pitcher equivalents of our batter trio: pulled-barrel%, hard-hit%, fly-ball% ALLOWED
            row["p_" + pk] = ps.get(pk)
        rows.append(row)
    return rows

def logged_dates(path=OUT):
    """Set of slate dates already present in calibration.jsonl (for idempotent backfill)."""
    s = set()
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    s.add(json.loads(line).get("date"))
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    return s

def backfill():
    """Idempotent, self-healing calibration logger. Logs every FULLY-FINAL dated board
    (D_<date>.json) that isn't already in calibration.jsonl. Safe to run on EVERY build:
    it skips dates already logged, skips today/future, and skips not-yet-final nights
    (they get picked up automatically on a later run). This is the single source of truth
    for the calibration dataset -- no run can silently drop a night, and a missed run
    self-heals on the next one."""
    import datetime, glob
    here = os.path.dirname(os.path.abspath(__file__))
    today = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=4)).date()  # US/Eastern
    done = logged_dates()
    files = sorted(set(glob.glob(os.path.join(here, "D_*.json")) + glob.glob("D_*.json")))
    seen, added, nights = set(), 0, 0
    for fp in files:
        m = re.search(r"D_(\d{4}-\d{2}-\d{2})\.json$", os.path.basename(fp))
        if not m:
            continue
        d = m.group(1)
        if d in done or d in seen:
            continue
        seen.add(d)
        if datetime.date.fromisoformat(d) >= today:        # today/future -> not final yet
            continue
        try:
            homered, n_final, n_games = homers_and_finals(d)
        except Exception as e:
            print(f"  calib {d}: results fetch failed ({e}) -> retry next run")
            continue
        if n_games == 0 or n_final < n_games:              # only log a CLEAN, fully-final night
            print(f"  calib {d}: {n_final}/{n_games} final -> skip, retry next run")
            continue
        try:
            D = json.load(open(fp))
        except Exception as e:
            print(f"  calib {d}: cannot read board ({e})")
            continue
        rows = build_rows(D, homered, load_extras(d), load_pitchers(d))
        with open(OUT, "a") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        added += len(rows); nights += 1
        print(f"  calib {d}: +{len(rows)} rows ({sum(r['hr'] for r in rows)} HR, "
              f"{sum(1 for r in rows if r.get('k_fb') is not None)} w/extras)")
    cov = sorted(x for x in logged_dates() if x)
    total = sum(1 for _ in open(OUT)) if os.path.exists(OUT) else 0
    print(f"calibration: +{added} rows / {nights} night(s); now {total} rows "
          f"covering {len(cov)} nights ({cov[0] if cov else '-'}..{cov[-1] if cov else '-'})")
    return added

def main(date):
    dfile = f"D_{date}.json"
    if not os.path.exists(dfile):
        sys.exit(f"!! no {dfile} to log")
    D = json.load(open(dfile))
    homered, n_final, n_games = homers_and_finals(date)
    if n_final == 0:
        sys.exit(f"{date}: no final games yet -- run again once the slate is complete")
    extras = load_extras(date)
    rows = build_rows(D, homered, extras, load_pitchers(date))
    with open(OUT, 'a') as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    hrs = sum(r['hr'] for r in rows)
    poolhrs = sum(r['hr'] for r in rows if r['pool'])
    kmatched = sum(1 for r in rows if r.get('k_fb') is not None)
    print(f"{date}: logged {len(rows)} bats | {hrs} HR overall, {poolhrs} in our 33-pool "
          f"| {kmatched} with Kasper extras | {n_final}/{n_games} games final -> appended to {OUT}")
    if n_final < n_games:
        print(f"  note: {n_games - n_final} game(s) not final yet -- re-run later to capture them cleanly")

if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else '--backfill'
    if arg in ('--backfill', '-b', 'backfill', ''):
        backfill()                       # idempotent, self-healing: the Action runs this every build
    else:
        main(arg)                        # one-off single date: python calibrate.py YYYY-MM-DD
