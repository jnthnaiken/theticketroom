#!/usr/bin/env python3
"""
fetch_mlb.py  --  Kasper pipeline, step 1: free auto-pulled inputs.

Pulls, with NO API key and NO account, and writes slate_auto_<DATE>.json:
  - MLB StatsAPI : the day's games + probable starters (name + throwing hand),
                   posted lineups, each hitter's season ISO, each starter's HR/9
  - Open-Meteo   : per-ballpark wind / temp / precip at first pitch -> park factor wf
                   (open-meteo.com, free, keyless). Domes -> neutral wf=1.0.

The GitHub Action runs this on a schedule, so HR/9, lineups and weather all
auto-update through the day; re-running just overwrites slate_auto_<DATE>.json.

Usage:
    python3 fetch_mlb.py                # today (US/Eastern)
    python3 fetch_mlb.py 2026-06-17     # a specific date

Pure standard library. Runs on a laptop or in a GitHub Action.
"""

import sys, json, math, datetime, urllib.request, urllib.parse, urllib.error

API      = "https://statsapi.mlb.com/api/v1"
OPENMETEO = "https://api.open-meteo.com/v1/forecast"
TIMEOUT  = 20

# ---- park table: home-team code -> (lat, lon, CF azimuth deg from home plate, dome?) ----
# CF azimuth = compass bearing home-plate->center-field; used to resolve wind as
# blowing OUT (toward CF, carry) vs IN (toward plate, knockdown). Bearings are
# public stadium orientations, approximate to a few degrees and easy to tune.
# Retractable-roof parks are marked dome=True (treated neutral); flip to False on
# confirmed open-roof days.
PARKS = {
 'ARI':(33.4455,-112.0667, 0,  True),  'ATL':(33.8907,-84.4677, 50,  False),
 'BAL':(39.2839,-76.6217, 30,  False), 'BOS':(42.3467,-71.0972, 45,  False),
 'CHC':(41.9484,-87.6553, 30,  False), 'CWS':(41.8300,-87.6339, 38,  False),
 'CIN':(39.0975,-84.5069, 40,  False), 'CLE':(41.4962,-81.6852, 0,   False),
 'COL':(39.7559,-104.9942,0,   False), 'DET':(42.3390,-83.0485, 30,  False),
 'HOU':(29.7572,-95.3556, 20,  True),  'KC':(39.0517,-94.4803, 45,  False),
 'LAA':(33.8003,-117.8827,40,  False), 'LAD':(34.0739,-118.2400,25,  False),
 'MIA':(25.7780,-80.2197, 35,  True),  'MIL':(43.0280,-87.9712, 30,  True),
 'MIN':(44.9817,-93.2776, 7,   False), 'NYM':(40.7571,-73.8458, 25,  False),
 'NYY':(40.8296,-73.9262, 15,  False), 'ATH':(38.5800,-121.5160,60,  False),  # Sacramento (Sutter Health Pk)
 'PHI':(39.9061,-75.1665, 15,  False), 'PIT':(40.4469,-80.0057, 70,  False),
 'SD':(32.7073,-117.1566, 0,   False), 'SF':(37.7786,-122.3893,85,  False),
 'SEA':(47.5914,-122.3325,60,  True),  'STL':(38.6226,-90.1928, 30,  False),
 'TB':(27.7683,-82.6534,  50,  True),  'TEX':(32.7473,-97.0833, 40,  True),
 'TOR':(43.6414,-79.3894, 0,   True),  'WSH':(38.8730,-77.0074, 30,  False),
}
# StatsAPI abbreviation -> our park code (handles the few that differ)
ALIAS = {'CHW':'CWS','AZ':'ARI','OAK':'ATH','SAC':'ATH','WAS':'WSH','SD':'SD','SDP':'SD',
         'TBR':'TB','KCR':'KC','SFG':'SF'}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "kasper-pipeline/2.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.load(r)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as e:
        print(f"  ! fetch failed: {url}\n    {e}", file=sys.stderr)
        return None


def appeared_ids(game_pk):
    """Player IDs who actually appeared in a STARTED game (have a batting order or a recorded at-bat).
    Used to drop scratches from that game's posted lineup at build time -- the build-time twin of the
    client's boxscore scratch backstop. Returns None when the box isn't trustworthy yet (< 8 hitters),
    so a not-yet-started or empty box leaves the posted lineup untouched."""
    bx = get(f"{API}/game/{game_pk}/boxscore")
    if not bx:
        return None
    ids = set()
    for side in ("away", "home"):
        players = (((bx.get("teams") or {}).get(side) or {}).get("players")) or {}
        for _, p in players.items():
            pid = (p.get("person") or {}).get("id")
            bo  = p.get("battingOrder")
            ab  = (((p.get("stats") or {}).get("batting")) or {}).get("atBats")
            if pid and (bo or ab is not None):
                ids.add(pid)
    return ids if len(ids) >= 8 else None


def eastern_today():
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=4)).strftime("%Y-%m-%d")

def to_float(x):
    try: return float(x)
    except (TypeError, ValueError): return None

def ip_to_decimal(ip):
    if ip is None: return None
    try:
        whole, _, frac = str(ip).partition(".")
        return int(whole) + {"":0,"0":0,"1":1/3,"2":2/3}.get(frac, 0)
    except ValueError:
        return None

def chunk(lst, n):
    for i in range(0, len(lst), n): yield lst[i:i+n]


def batch_people(ids, group, season):
    """{playerId: stat_dict} for a stat group, plus pitchHand on the person."""
    out, hand = {}, {}
    for ids_chunk in chunk(sorted(set(ids)), 25):
        ids_csv = ",".join(str(i) for i in ids_chunk)
        url = (f"{API}/people?personIds={ids_csv}"
               f"&hydrate=stats(group=[{group}],type=[season],season={season})")
        data = get(url)
        if not data: continue
        for person in data.get("people", []):
            pid = person.get("id")
            hand[pid] = (person.get("pitchHand", {}) or {}).get("code")
            stat = {}
            for s in person.get("stats", []):
                sp = s.get("splits", [])
                if sp: stat = sp[0].get("stat", {}); break
            out[pid] = stat
    return out, hand


# ---- Open-Meteo weather -> park factor ----
def weather_for(code, when_iso):
    """Return (weather_dict, wf) for a ballpark at first pitch. Dome -> neutral."""
    p = PARKS.get(code)
    if not p:
        return {"dome": False, "note": "no park coords"}, 1.0
    lat, lon, cf_bearing, dome = p
    if dome:
        return {"dome": True, "emoji": "\U0001f3df", "cond": "Dome", "lean": "Neutral",
                "temp": None, "wind_mph": None, "wind_dir": None, "precip": None}, 1.0
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "hourly": "temperature_2m,precipitation_probability,wind_speed_10m,wind_direction_10m",
        "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
        "timezone": "America/New_York", "forecast_days": 2})
    data = get(f"{OPENMETEO}?{q}")
    if not data or "hourly" not in data:
        return {"dome": False, "note": "weather fetch failed"}, 1.0
    H = data["hourly"]; times = H.get("time", [])
    hour = when_iso[:13]                       # match 'YYYY-MM-DDTHH'
    i = next((k for k, t in enumerate(times) if t[:13] == hour), None)
    if i is None: i = 0
    temp  = H["temperature_2m"][i]
    wind  = H["wind_speed_10m"][i]
    wdir  = H["wind_direction_10m"][i]         # deg the wind blows FROM
    precip= H.get("precipitation_probability", [None]*len(times))[i]
    # wind blows TOWARD (wdir+180); component along plate->CF axis (+ = out to CF)
    toward = (wdir + 180) % 360
    tail   = wind * math.cos(math.radians(toward - cf_bearing))   # mph out to CF
    # park factor: carry from tailwind + mild temperature term, bounded
    wf = 1.0 + 0.0035 * tail + 0.0015 * ((temp or 70) - 70)
    wf = max(0.94, min(1.08, round(wf, 3)))
    lean = "Boost" if wf > 1.02 else ("Suppress" if wf < 0.98 else "Neutral")
    if precip and precip >= 50: emoji = "\U0001f327\ufe0f"      # 🌧
    elif tail >= 6:             emoji = "\u2600\ufe0f"          # ☀ (wind out)
    else:                       emoji = "\u26c5"                # ⛅
    cond = (f"{'wind out' if tail>=3 else 'wind in' if tail<=-3 else 'calm'} "
            f"{abs(round(tail))}mph, {round(temp)}\u00b0")
    return {"dome": False, "emoji": emoji, "cond": cond, "lean": lean, "temp": temp,
            "wind_mph": round(wind, 1), "wind_dir": wdir, "tail_mph": round(tail, 1),
            "precip": precip}, wf


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else eastern_today()
    season = date[:4]
    print(f"== MLB auto-pull for {date} (season {season}) ==")

    sched = get(f"{API}/schedule?sportId=1&date={date}&hydrate=probablePitcher,lineups,team")
    games_raw = sched["dates"][0].get("games", []) if (sched and sched.get("dates")) else []
    print(f"games found: {len(games_raw)}")

    games, hitter_ids, pitcher_ids = [], set(), set()
    for g in games_raw:
        teams = g.get("teams", {})
        at = teams.get("away", {}).get("team", {}); ht = teams.get("home", {}).get("team", {})
        app = teams.get("away", {}).get("probablePitcher", {}) or {}
        hpp = teams.get("home", {}).get("probablePitcher", {}) or {}
        status = (g.get("status", {}) or {}).get("detailedState", "")
        lu = g.get("lineups", {}) or {}
        al = lu.get("awayPlayers", []) or []; hl = lu.get("homePlayers", []) or []

        # Build-time scratch backstop: once a game has started, the posted-lineup hydrate can be stale or
        # empty, so a confirmed bat who was actually scratched would slip into the slate (and the 33).
        # Trim each side's lineup to who truly appeared in the box, so scratches never reach assembly.
        started = any(w in status.lower() for w in
                      ("progress", "final", "completed", "live", "game over", "suspended"))
        if started and g.get("gamePk"):
            seen = appeared_ids(g.get("gamePk"))
            if seen is not None:                                    # box is populated -> trust it
                al = [p for p in al if p.get("id") in seen]
                hl = [p for p in hl if p.get("id") in seen]

        def names(players):
            o = []
            for p in players:
                pid = p.get("id"); nm = p.get("fullName") or p.get("name")
                if pid: hitter_ids.add(pid); o.append({"id": pid, "name": nm})
            return o
        for pp in (app, hpp):
            if pp.get("id"): pitcher_ids.add(pp["id"])

        a_ab = (at.get("abbreviation") or "").upper(); h_ab = (ht.get("abbreviation") or "").upper()
        a_code = ALIAS.get(a_ab, a_ab); h_code = ALIAS.get(h_ab, h_ab)
        games.append({
            "gamePk": g.get("gamePk"), "status": status, "gameTime": g.get("gameDate"),
            "matchup": f"{a_code}@{h_code}",
            "away": {"abbrev": a_code, "sp": {"id": app.get("id"), "name": app.get("fullName")},
                     "lineup": names(al), "confirmed": bool(al)},
            "home": {"abbrev": h_code, "sp": {"id": hpp.get("id"), "name": hpp.get("fullName")},
                     "lineup": names(hl), "confirmed": bool(hl)},
            "lineups_posted": bool(al or hl)})

    print(f"hitters listed: {len(hitter_ids)} | probable pitchers: {len(pitcher_ids)}")

    # season ISO (hitters) + HR/9 & throwing hand (pitchers)
    hit_stats, _      = batch_people(hitter_ids, "hitting", season) if hitter_ids else ({}, {})
    pit_stats, pithand = batch_people(pitcher_ids, "pitching", season) if pitcher_ids else ({}, {})
    iso = {}
    for pid, st in hit_stats.items():
        a, s = to_float(st.get("avg")), to_float(st.get("slg"))
        iso[pid] = round(s - a, 3) if (a is not None and s is not None) else None
    hr9 = {}
    for pid, st in pit_stats.items():
        v = to_float(st.get("homeRunsPer9"))
        if v is None:
            hr, ipd = to_float(st.get("homeRuns")), ip_to_decimal(st.get("inningsPitched"))
            v = round(hr / ipd * 9, 2) if (hr is not None and ipd) else None
        hr9[pid] = v

    # stitch ISO / HR9 / hand onto each game, then attach weather + wf
    for game in games:
        for side in ("away", "home"):
            for bat in game[side]["lineup"]:
                bat["iso"] = iso.get(bat["id"])
            sp = game[side]["sp"]
            if sp.get("id"):
                sp["hr9"]  = hr9.get(sp["id"])
                sp["hand"] = {"L": "LHP", "R": "RHP"}.get(pithand.get(sp["id"]), None)
        wx, wf = weather_for(game["home"]["abbrev"], game["gameTime"])
        game["weather"], game["wf"] = wx, wf

    out = {"date": date, "season": season,
           "pulled_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "games": games}
    fname = f"slate_auto_{date}.json"
    with open(fname, "w") as f:
        json.dump(out, f, indent=2)

    print(f"\nwrote {fname}\n")
    for game in games:
        a, h = game["away"], game["home"]; w = game["weather"]
        print(f"{game['matchup']:9} [{game['status']}] wf={game['wf']}  {w.get('cond','?')}")
        print(f"   SP {a['sp'].get('name')} ({a['sp'].get('hand')}, HR/9 {a['sp'].get('hr9')})"
              f"  vs  {h['sp'].get('name')} ({h['sp'].get('hand')}, HR/9 {h['sp'].get('hr9')})")
    print("\nDone. The scorer reads slate_auto_<date>.json for wf + HR/9 at score time.")


if __name__ == "__main__":
    main()
