#!/usr/bin/env python3
"""
grade_night.py  --  the nightly fold that makes the season ledger self-advance.

For every archived board D_<YYYY-MM-DD>.json whose games are FINAL and which has
not been graded yet, this:
  1. pulls that date's StatsAPI boxscores and marks who homered,
  2. grades every ticket with the SAME math the live board uses (gradeTicket),
  3. folds the night into season.json (cats + history), and records the date in
     season['graded_nights'] so it can never be double-counted.

build15.py reads season.json as the authoritative base, so the next morning's
board carries the advanced ledger automatically. Idempotent: safe to run on every
Action tick. Never corrupts season.json -- a date is only folded once its games
are all final and its results fetch succeeds; any failure skips that date.

Usage:
  python3 grade_night.py                 # auto: grade every finished, ungraded prior date
  python3 grade_night.py 2026-06-18      # grade a specific date (must be final)
"""
import sys, os, re, json, glob, time, datetime, unicodedata, urllib.request

SA = "https://statsapi.mlb.com/api/v1"
SEASON_JSON = os.environ.get("SEASON_JSON", "season.json")
ALIAS = {'CHW':'CWS','AZ':'ARI','OAK':'ATH','SAC':'ATH','WAS':'WSH','SD':'SD',
         'SDP':'SD','TBR':'TB','KCR':'KC','SFG':'SF'}
AMBIG = {'maxmuncy'}                      # same normalized name, two players -> needs team check

def eastern_today():
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=4)).strftime("%Y-%m-%d")

def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if i == tries - 1:
                print(f"  ! fetch failed {url}: {e}")
                return None
            time.sleep(2)

# --- name normalizer: identical to the client's norm() (strips accents, punctuation, Jr/Sr/II/III/IV) ---
def norm(s):
    s = (s or "").lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z ]", "", s)
    s = re.sub(r" (jr|sr|ii|iii|iv)$", "", s)
    return s.strip()

def alias(ab):
    ab = (ab or "").upper()
    return ALIAS.get(ab, ab)

# --- decimal odds + the live board's exact grading (port of gradeTicket; all legs final here) ---
def _dec(a):
    return 1 + a/100.0 if a > 0 else 1 + 100.0/abs(a)

def grade_ticket(t, hrflag, stake_base=1):
    legs = t.get("players", [])
    L = len(legs)
    if not L:
        return None
    hr = [bool(hrflag.get(l["name"])) for l in legs]
    cashed = all(hr)
    rr = t.get("rr")
    if rr:
        dec = [_dec(l["odds"]) for l in legs]
        risk = rr["risk"]
        def rrnet(m):
            s = -risk
            for a in range(L):
                for b in range(a+1, L):
                    if m[a] and m[b]:
                        s += dec[a]*dec[b]
            for a in range(L):
                for b in range(a+1, L):
                    for c in range(b+1, L):
                        if m[a] and m[b] and m[c]:
                            s += dec[a]*dec[b]*dec[c]
            if L >= 4:
                for a in range(L):
                    for b in range(a+1, L):
                        for c in range(b+1, L):
                            for d in range(c+1, L):
                                if m[a] and m[b] and m[c] and m[d]:
                                    s += dec[a]*dec[b]*dec[c]*dec[d]
            return s
        net = rrnet(hr)
        if net <= 0:                                   # no profitable sub-parlay -> whole risk lost
            return {"kind": t["kind"], "stake": float(risk), "net": float(-risk), "won": False}
        return {"kind": t["kind"], "stake": float(risk), "net": float(net), "won": net > 0}
    # straight (single / flat parlay)
    sb = stake_base
    p10 = t.get("payout10")
    if not p10:
        p10 = 10.0
        for l in legs:
            p10 *= _dec(l["odds"])
    if cashed:
        return {"kind": t["kind"], "stake": float(sb), "net": float(sb*(p10/10.0 - 1)), "won": True}
    return {"kind": t["kind"], "stake": float(sb), "net": float(-sb), "won": False}

# --- pull a date's results: returns (all_final, hr_list[(normname, teamname_lower)]) restricted to slate games ---
def fetch_results(date, board_codes):
    sch = get(f"{SA}/schedule?sportId=1&date={date}&hydrate=team")
    if not sch or not sch.get("dates"):
        return None
    games = sch["dates"][0].get("games", []) if sch["dates"] else []
    if not games:
        return None
    slate_pks, all_final = [], True
    for g in games:
        try:
            a = g["teams"]["away"]["team"]["abbreviation"]; h = g["teams"]["home"]["team"]["abbreviation"]
        except Exception:
            continue
        gd = g.get("gameDate")
        if gd:
            try:
                et = (datetime.datetime.fromisoformat(gd.replace("Z", "+00:00")) - datetime.timedelta(hours=4)).strftime("%Y-%m-%d")
                if et != date:
                    continue   # feed game from another date (resumed/DH sharing this matchup) -> not this slate's game
            except Exception:
                pass
        acand = {a.upper(), alias(a)}; hcand = {h.upper(), alias(h)}
        if (acand & board_codes) and (hcand & board_codes):       # game is part of our slate
            st = (g.get("status", {}) or {})
            state = (st.get("abstractGameState") or st.get("detailedState") or "")
            if not re.search(r"final|completed|over", state, re.I):
                all_final = False
            slate_pks.append(g.get("gamePk"))
    if not slate_pks:
        return None
    hr_list = []
    for pk in slate_pks:
        bx = get(f"{SA}/game/{pk}/boxscore")
        if not bx:
            all_final = False
            continue
        for side in ("away", "home"):
            tm = (bx.get("teams", {}) or {}).get(side, {}) or {}
            tn = ((tm.get("team", {}) or {}).get("name", "") or "").lower()
            for p in (tm.get("players", {}) or {}).values():
                bat = (((p.get("stats", {}) or {}).get("batting", {}) or {}).get("homeRuns"))
                fn = (p.get("person", {}) or {}).get("fullName")
                if bat and bat > 0 and fn:
                    hr_list.append((norm(fn), tn))
    return {"all_final": all_final, "hr": hr_list}

def mark_hr(players, hr_list):
    idx = {norm(k): k for k in players}
    flag = {k: False for k in players}
    for hn, tn in hr_list:
        key = idx.get(hn)
        if not key:
            continue
        if hn in AMBIG and tn and (players[key].get("team", "").lower() not in tn):
            continue
        flag[key] = True
    return flag

def fold(season, date, night_grades):
    cats = {k: dict(v) for k, v in season.get("cats", {}).items()}
    for g in night_grades:
        c = cats.setdefault(g["kind"], {"graded": 0, "won": 0, "units": 0.0, "staked": 0.0})
        c["graded"] += 1
        c["won"]    += 1 if g["won"] else 0
        c["units"]  = round(c["units"]  + g["net"],   2)
        c["staked"] = round(c["staked"] + g["stake"], 2)
    hist = list(season.get("history", [0.0])) or [0.0]
    run = hist[-1]
    for g in night_grades:
        run = round(run + g["net"], 2)
        hist.append(run)
    season["cats"] = cats
    season["history"] = hist
    gn = set(season.get("graded_nights", []))
    gn.add(date)
    season["graded_nights"] = sorted(gn)
    return season

def load_season():
    try:
        s = json.load(open(SEASON_JSON))
    except Exception:
        s = {"since": eastern_today(), "stake": 1, "cats": {}, "history": [0.0]}
    s.setdefault("cats", {}); s.setdefault("history", [0.0]); s.setdefault("graded_nights", [])
    s.setdefault("stake", 1)
    return s

def save_season(s):
    tmp = SEASON_JSON + ".tmp"
    json.dump(s, open(tmp, "w"), indent=1)
    os.replace(tmp, SEASON_JSON)

def board_for(date):
    f = f"D_{date}.json"
    if not os.path.exists(f):
        return None
    try:
        return json.load(open(f))
    except Exception:
        return None

def main():
    today = eastern_today()
    season = load_season()
    graded = set(season.get("graded_nights", []))
    if len(sys.argv) > 1:
        targets = [d for d in sys.argv[1:]]
    else:
        targets = []
        for f in glob.glob("D_*.json"):
            m = re.match(r"D_(\d{4}-\d{2}-\d{2})\.json$", os.path.basename(f))
            if m and m.group(1) < today and m.group(1) not in graded:
                targets.append(m.group(1))
        targets.sort()
    if not targets:
        print("grade_night: nothing to grade."); return
    changed = False
    for date in targets:
        if date in graded:
            print(f"grade_night: {date} already folded -- skip."); continue
        D = board_for(date)
        if not D:
            print(f"grade_night: no archived board D_{date}.json -- skip."); continue
        players = D.get("players", {}); tickets = D.get("tickets", [])
        if not tickets:
            print(f"grade_night: {date} board has no tickets -- skip."); continue
        board_codes = {p.get("code") for p in players.values() if p.get("code")}
        res = fetch_results(date, board_codes)
        if not res:
            print(f"grade_night: {date} results unavailable -- skip (will retry)."); continue
        if not res["all_final"]:
            print(f"grade_night: {date} not all games final -- skip (will retry)."); continue
        stake_base = (D.get("meta", {}).get("season", {}) or {}).get("stake", season.get("stake", 1)) or 1
        flag = mark_hr(players, res["hr"])
        grades = [g for g in (grade_ticket(t, flag, stake_base) for t in tickets) if g]
        season = fold(season, date, grades)
        graded.add(date)
        changed = True
        tot = round(sum(c["units"] for c in season["cats"].values()), 2)
        w = sum(c["won"] for c in season["cats"].values()); g = sum(c["graded"] for c in season["cats"].values())
        nl = sum(1 for x in flag.values() if x)
        print(f"grade_night: folded {date} -- {len(grades)} tickets graded, {nl} HR bats "
              f"-> season {tot:+.1f}u, overall {w}-{g-w}")
    if changed:
        save_season(season)
        print(f"grade_night: wrote {SEASON_JSON} (graded_nights={season['graded_nights']})")
    else:
        print("grade_night: no changes.")

if __name__ == "__main__":
    main()
