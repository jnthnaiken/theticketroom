#!/usr/bin/env python3
"""
fetch_mlb.py  --  Kasper pipeline, step 1: free auto-pulled inputs.

Pulls from MLB's public StatsAPI (no key, no account):
  - the day's games + probable starting pitchers
  - confirmed lineups (if posted yet)
  - each listed hitter's season ISO  (ISO = SLG - AVG)
  - each probable pitcher's season HR/9

Writes everything to  slate_auto_<DATE>.json  and prints a readable summary.

Usage:
    python3 fetch_mlb.py                # today (US/Eastern)
    python3 fetch_mlb.py 2026-06-16     # a specific date

Pure standard library. No dependencies. Runs on a laptop or in a GitHub Action.

NOTE: this is v1, written from the documented API shape but NOT yet run against
the live feed from my side. Run it once and send back the printed summary (or any
error) so we can pin down field names against real responses.
"""

import sys, json, datetime, urllib.request, urllib.error

API = "https://statsapi.mlb.com/api/v1"
TIMEOUT = 20


def get(url):
    """GET JSON with a browser-ish UA; returns dict or None on failure."""
    req = urllib.request.Request(url, headers={"User-Agent": "kasper-pipeline/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.load(r)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as e:
        print(f"  ! fetch failed: {url}\n    {e}", file=sys.stderr)
        return None


def eastern_today():
    # Approximate US/Eastern without external tz libs: UTC-4 (DST) during the season.
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=4)).strftime("%Y-%m-%d")


def to_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def ip_to_decimal(ip):
    """MLB innings-pitched like '45.1' means 45 and 1/3 innings."""
    if ip is None:
        return None
    try:
        whole, _, frac = str(ip).partition(".")
        return int(whole) + {"": 0, "0": 0, "1": 1 / 3, "2": 2 / 3}.get(frac, 0)
    except ValueError:
        return None


def chunk(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def batch_people_stats(ids, group, season):
    """Return {playerId: stat_dict} for a stat group ('hitting'/'pitching')."""
    out = {}
    for ids_chunk in chunk(sorted(set(ids)), 25):
        ids_csv = ",".join(str(i) for i in ids_chunk)
        url = (f"{API}/people?personIds={ids_csv}"
               f"&hydrate=stats(group=[{group}],type=[season],season={season})")
        data = get(url)
        if not data:
            continue
        for person in data.get("people", []):
            pid = person.get("id")
            stat = None
            for s in person.get("stats", []):
                splits = s.get("splits", [])
                if splits:
                    stat = splits[0].get("stat", {})
                    break
            out[pid] = stat or {}
    return out


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else eastern_today()
    season = date[:4]
    print(f"== MLB auto-pull for {date} (season {season}) ==")

    sched = get(f"{API}/schedule?sportId=1&date={date}"
                f"&hydrate=probablePitcher,lineups,team")
    games_raw = []
    if sched and sched.get("dates"):
        games_raw = sched["dates"][0].get("games", [])
    print(f"games found: {len(games_raw)}")

    games = []
    hitter_ids, pitcher_ids = set(), set()

    for g in games_raw:
        teams = g.get("teams", {})
        away_t = teams.get("away", {}).get("team", {})
        home_t = teams.get("home", {}).get("team", {})
        away_pp = teams.get("away", {}).get("probablePitcher", {}) or {}
        home_pp = teams.get("home", {}).get("probablePitcher", {}) or {}
        status = (g.get("status", {}) or {}).get("detailedState", "")

        lineups = g.get("lineups", {}) or {}
        away_lineup = lineups.get("awayPlayers", []) or []
        home_lineup = lineups.get("homePlayers", []) or []
        lineups_posted = bool(away_lineup or home_lineup)

        def names(players):
            out = []
            for p in players:
                pid = p.get("id")
                nm = p.get("fullName") or p.get("name")
                if pid:
                    hitter_ids.add(pid)
                    out.append({"id": pid, "name": nm})
            return out

        for pp in (away_pp, home_pp):
            if pp.get("id"):
                pitcher_ids.add(pp["id"])

        games.append({
            "gamePk": g.get("gamePk"),
            "status": status,
            "gameTime": g.get("gameDate"),
            "away": {"team": away_t.get("name"), "teamId": away_t.get("id"),
                     "sp": {"id": away_pp.get("id"), "name": away_pp.get("fullName")},
                     "lineup": names(away_lineup)},
            "home": {"team": home_t.get("name"), "teamId": home_t.get("id"),
                     "sp": {"id": home_pp.get("id"), "name": home_pp.get("fullName")},
                     "lineup": names(home_lineup)},
            "lineups_posted": lineups_posted,
        })

    print(f"hitters listed: {len(hitter_ids)}  |  probable pitchers: {len(pitcher_ids)}")
    if hitter_ids == set():
        print("  (no lineups posted yet — re-run closer to game time for confirmed bats)")

    # season ISO for hitters
    hit_stats = batch_people_stats(hitter_ids, "hitting", season) if hitter_ids else {}
    iso = {}
    for pid, st in hit_stats.items():
        avg, slg = to_float(st.get("avg")), to_float(st.get("slg"))
        iso[pid] = round(slg - avg, 3) if (avg is not None and slg is not None) else None

    # season HR/9 for pitchers
    pit_stats = batch_people_stats(pitcher_ids, "pitching", season) if pitcher_ids else {}
    hr9 = {}
    for pid, st in pit_stats.items():
        v = to_float(st.get("homeRunsPer9"))
        if v is None:
            hr, ipd = to_float(st.get("homeRuns")), ip_to_decimal(st.get("inningsPitched"))
            v = round(hr / ipd * 9, 2) if (hr is not None and ipd) else None
        hr9[pid] = v

    # stitch ISO / HR9 back onto each game
    for game in games:
        for side in ("away", "home"):
            for bat in game[side]["lineup"]:
                bat["iso"] = iso.get(bat["id"])
            sp = game[side]["sp"]
            if sp.get("id"):
                sp["hr9"] = hr9.get(sp["id"])

    out = {"date": date, "season": season, "pulled_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "games": games}
    fname = f"slate_auto_{date}.json"
    with open(fname, "w") as f:
        json.dump(out, f, indent=2)

    # readable summary
    print(f"\nwrote {fname}\n")
    for game in games:
        a, h = game["away"], game["home"]
        print(f"{a['team']} @ {h['team']}   [{game['status']}]"
              f"{'  lineups posted' if game['lineups_posted'] else '  lineups NOT posted'}")
        print(f"   SP: {a['sp']['name']} (HR/9 {a['sp'].get('hr9')})"
              f"  vs  {h['sp']['name']} (HR/9 {h['sp'].get('hr9')})")
        bats = [f"{b['name']} {b.get('iso')}" for b in (a["lineup"] + h["lineup"])[:6]]
        if bats:
            print("   bats (ISO): " + "; ".join(bats) + (" …" if len(a["lineup"]) + len(h["lineup"]) > 6 else ""))
    print("\nDone. Send me this summary (or any error above) and we wire it into the model next.")


if __name__ == "__main__":
    main()
