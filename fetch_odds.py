#!/usr/bin/env python3
"""
fetch_odds.py — re-scrape VegasInsider player props and rewrite odds_<date>.json.

WHY THIS EXISTS
    Until 2026-08-08 the odds were scraped ONCE, by hand, during the morning
    browser build, and never refreshed. `fetch_mlb.py` pulls StatsAPI + weather
    and nothing else, so the server drafted, priced and graded every ticket off
    morning numbers all day. Measured by this script against the live market at
    5:35pm ET on 2026-08-08: of the 287 bats in the committed file, 228 (79.4%)
    had moved -- Schwarber +210 -> +190, Alvarez +255 -> +225, Caminero +334 ->
    +300. Normal intraday drift, ~1-3 points of implied probability on the
    movers, but it lands on a board where price decides Chef's Table seats and
    35% of every strength ranking.

    The client could already be re-priced by hand (paste box / per-bat inputs)
    but it saved to ONE browser's localStorage. Nothing wrote back, so the
    build, the archive and every other visitor kept the morning numbers -- and
    the hand-entered ones could drift away from the real market with nothing to
    check them (2026-08-08: a browser holding Caminero at +250, against +300 in
    the market and +334 committed, handed him a Chef's Table seat).

OUTPUT  (both files are MERGED, never replaced -- see the price-freeze note below)
    odds_<date>.json     {name: american_int}          <- consumed by build15.py
    markets_<date>.json  {market: {name: {...}}}        <- the side-market log

METHOD (mirrors the in-browser scraper this replaces)
    * tables[0]=strikeouts, [1]=home runs, [2]=total bases, [3]=RBI
    * drop degenerate book columns: <10 prices, all-identical, or one price on
      >60% of rows (PrizePicks/Underdog-style fixed juice is not a real market)
    * per bat: take the modal line, then the MEDIAN IN PROBABILITY SPACE.
      Never average American odds -- the -100/+100 discontinuity makes it
      nonsense (mean of -115 and +120 is +2, i.e. "98%"). That bug corrupted 9
      TB and 6 RBI players on 2026-08-06.

USAGE
    python3 fetch_odds.py 2026-08-08              # write the files
    python3 fetch_odds.py 2026-08-08 --probe      # diagnose only, write nothing
    python3 fetch_odds.py 2026-08-08 --auto       # build mode: refresh until the last
                                                  # first pitch, and flag the one build
                                                  # that should commit the closing prices
"""
import sys, os, json, re, gzip, io, statistics, unicodedata
import urllib.request, urllib.error
import datetime
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:                                  # tzdata missing -> treat runner UTC as ET-4
    ET = datetime.timezone(datetime.timedelta(hours=-4))
from html.parser import HTMLParser

URL = "https://www.vegasinsider.com/mlb/odds/player-props/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
MARKETS = ["strikeouts", "home_runs", "total_bases", "rbi"]
# TABLEID-2026-08-20 -- VegasInsider gives every prop table a stable id. Use it.
# The old code took `[t for t in tables if len(t) > 20]` and mapped MARKETS onto that list
# BY POSITION. That holds only while all four tables are long. Today the strikeouts table
# shrank to 17 rows once the early starters settled, every market shifted up one, and
# `home_runs` was fed the TOTAL BASES table -- so ~50 bats got o1.5 total-base prices
# (-110..-200) written into odds_<date>.json as home-run odds, starting 18:22Z. The
# coverage guard never saw it: total bases had 150 rows, so `len(hr) < 150` passed.
ID_MARKET = {"table-strikeouts": "strikeouts", "table-home-runs": "home_runs",
             "table-total-bases": "total_bases", "table-runs-batted-in": "rbi"}
HR_LINE = 0.5       # a home-run prop is over 0.5. Total bases is 1.5 -- that is the tell.
HR_MIN_PRICE = 100  # no real pre-game HR price is shorter than this, and none is negative
MIN_COL = 10        # a book column needs this many prices to count
TOP_FRAC = 0.60     # one price on >60% of rows = fixed juice, not a market
# LONEBOOK-2026-08-21 -- one book is not a market. VegasInsider posts a row as soon as a
# SINGLE book prices a bat, and the median of one observation carries no consensus. That was
# harmless while price only fed `strength`, but the chalk ban is now keyed on price
# (CHALKODDS-2026-08-20), so a lone quote can bar the wrong four bats -- and on 2026-08-21 a
# single Bet365 line (+270 on Jo Adell, the other four books blank or 0) made him the board's
# #2 bat by TOTAL and anchored two moons plus a builder.
# The rule: a single-book quote may not imply a HIGHER probability than the 95th percentile of
# the MULTI-book field. It is a one-way clamp -- a lone price is only ever LENGTHENED, never
# shortened -- and the bat keeps a price, because deleting one costs ~70 TOTAL points and that
# cure is worse (2026-08-08). Measured over the 11 archived markets_*.json plus 08-21: it fires
# twice (Oneil Cruz +320 on 08-14, Jo Adell +270 on 08-21). p90 fires on the same two; p99 on
# neither. Single-book rows are 5.8% of the field (53 of 906), so this touches ~1 slate in 6.
LONE_PCTL = 0.95
LONE_MIN_MULTI = 40   # below this the percentile is noise -- leave lone quotes alone


# ─────────────────────────────────────────────────────────── html -> tables
class Tables(HTMLParser):
    """Minimal stdlib table extractor: no lxml/bs4 dependency on the runner."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self._t, self._r, self._c = [], None, None, None
        self.ids, self._id = [], None      # TABLEID-2026-08-20: id of each top-level table
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self._t = []
                self._id = dict(attrs).get("id") or ""
        elif self._t is not None and tag == "tr":
            self._r = []
        elif self._t is not None and tag in ("td", "th"):
            self._c = []
        elif self._c is not None and tag in ("br", "img"):
            self._c.append(" ")

    def handle_endtag(self, tag):
        if tag == "table":
            if self._depth == 1 and self._t is not None:
                self.tables.append(self._t)
                self.ids.append(self._id or "")
                self._t = None; self._id = None
            self._depth = max(0, self._depth - 1)
        elif tag == "tr" and self._t is not None and self._r is not None:
            self._t.append(self._r); self._r = None
        elif tag in ("td", "th") and self._c is not None:
            txt = re.sub(r"\s+", " ", "".join(self._c)).strip()
            if self._r is not None:
                self._r.append(txt)
            self._c = None

    def handle_data(self, d):
        if self._c is not None:
            self._c.append(d)


def get_html(url=URL, timeout=45):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
        return r.status, raw.decode("utf-8", "replace")


# ───────────────────────────────────────────────────────────── odds helpers
def to_p(a):
    if not a:
        return 0.0
    return 100.0 / (a + 100.0) if a > 0 else abs(a) / (abs(a) + 100.0)


def to_a(p):
    if p <= 0 or p >= 1:
        return None
    return -round(100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


CELL = re.compile(r"(?:o\s*(\d+(?:\.\d+)?))?\D*?([+-]\d{2,4})")


def parse_cell(s):
    if not s:
        return None
    m = CELL.search(s)
    if not m:
        return None
    return (float(m.group(1)) if m.group(1) else None, int(m.group(2)))


def parse_market(rows):
    """rows -> {name: {line, p, price, books, spread}}"""
    recs = []
    for r in rows[1:]:
        if len(r) < 2 or not r[0]:
            continue
        recs.append((r[0], [parse_cell(c) for c in r[1:]]))
    if not recs:
        return {}, []

    ncol = max(len(c) for _, c in recs)
    keep, colinfo = [], []
    for c in range(ncol):
        ps = [cells[c][1] for _, cells in recs if c < len(cells) and cells[c]]
        cnt = {}
        for p in ps:
            cnt[p] = cnt.get(p, 0) + 1
        top = max(cnt.values()) if cnt else 0
        ok = len(ps) >= MIN_COL and len(cnt) > 1 and top / max(1, len(ps)) <= TOP_FRAC
        keep.append(ok)
        colinfo.append({"n": len(ps), "distinct": len(cnt), "kept": ok})

    lines = {}
    for _, cells in recs:
        for x in cells:
            if x and x[0] is not None:
                lines[x[0]] = lines.get(x[0], 0) + 1
    gmodal = max(lines, key=lines.get) if lines else None

    out = {}
    for name, cells in recs:
        rl = {}
        for x in cells:
            if x and x[0] is not None:
                rl[x[0]] = rl.get(x[0], 0) + 1
        modal = max(rl, key=rl.get) if rl else gmodal
        sel = [x[1] for i, x in enumerate(cells)
               if x and i < len(keep) and keep[i] and (x[0] is None or x[0] == modal)]
        if not sel or modal is None:
            continue
        ps = sorted(to_p(a) for a in sel)
        mp = statistics.median(ps)                      # MEDIAN IN PROBABILITY SPACE
        price = to_a(mp)
        if price is None:
            continue
        rec = {"line": modal, "p": round(mp, 5), "price": price,
               "books": len(ps), "spread": round(max(ps) - min(ps), 5)}
        # NAMEDUP-2026-08-21 -- VegasInsider posts ONE ROW PER BAT, so two players sharing a
        # name produce two rows and this assignment used to be last-write-wins: whichever row
        # parsed last silently became that name's price. 2026-08-17 it handed ATH's Max Muncy
        # LAD's price; 2026-08-21 it did the reverse, overwriting a correct committed +248 with
        # the Athletics Muncy's +580 on every five-minute refresh. The row carries NO team --
        # the only image in the name cell is a generic placeholder and data-name is just the
        # lowercased name -- so the rows CANNOT be told apart here. Keep every candidate and let
        # the caller resolve against the authoritative committed file.
        cand = {"price": price, "p": rec["p"], "books": rec["books"]}
        if name in out:
            out[name]["alts"].append(cand)
        else:
            rec["alts"] = [cand]
            out[name] = rec
    for v in out.values():
        v["dup"] = len(v["alts"])
    return out, colinfo


def scrape():
    status, html = get_html()
    p = Tables()
    p.feed(html)
    byid = {}
    for t, tid in zip(p.tables, p.ids):
        key = ID_MARKET.get(tid)
        if key and len(t) > 2:
            byid[key] = t
    markets, info = {}, {}
    if "home_runs" in byid:                              # id path -- position-proof
        for key in MARKETS:
            markets[key], info[key] = (parse_market(byid[key]) if key in byid else ({}, []))
        return status, len(html), len(p.tables), len(byid), markets, info
    # fallback: ids gone (site rewrite). Keep the old behaviour but SAY SO -- silence here
    # is what let the 2026-08-20 shift run for 90 minutes.
    print("::warning::fetch_odds: no table ids found -- falling back to positional mapping")
    tabs = [t for t in p.tables if len(t) > 20]          # the four prop tables are long
    for i, key in enumerate(MARKETS):
        if i < len(tabs):
            markets[key], info[key] = parse_market(tabs[i])
        else:
            markets[key], info[key] = {}, []
    return status, len(html), len(p.tables), len(tabs), markets, info


def hr_sane(hr):
    """Is this actually the home-run market? Returns (ok, reason).

    Cheap shape check that catches a wrong-table read even if the ids come back. A home-run
    prop is over 0.5 and priced as a longshot; total bases is over 1.5 and routinely negative.
    2026-08-20: this predicate is false for every one of the corrupted builds and true for
    every good one."""
    if not hr:
        return False, "empty"
    lines = [v.get("line") for v in hr.values() if v.get("line") is not None]
    if lines:
        off = sum(1 for l in lines if l != HR_LINE)
        if off > 0.10 * len(lines):
            return False, f"{off}/{len(lines)} rows are not an o{HR_LINE} line"
    prices = [v["price"] for v in hr.values() if v.get("price") is not None]
    if not prices:
        return False, "no prices"
    neg = sum(1 for x in prices if x < HR_MIN_PRICE)
    if neg:
        return False, f"{neg} price(s) below +{HR_MIN_PRICE} -- not a home-run market"
    return True, ""


SNAP_LEAD_MIN = 12      # snapshot window before the last first pitch; > the 5-min build cadence


def last_first_pitch(date):
    """Latest first pitch on the slate, as an ET datetime. None if unknown."""
    try:
        games = json.load(open(f"lineups_{date}.json"))["games"]
    except Exception:
        return None
    best = None
    for g in games:
        m = re.match(r"(\d{1,2}):(\d{2})\s*([AP])M", (g.get("time") or "").strip(), re.I)
        if not m:
            continue
        h, mi, ap = int(m.group(1)) % 12, int(m.group(2)), m.group(3).upper()
        if ap == "P":
            h += 12
        best = max(best or 0, h * 60 + mi)
    if best is None:
        return None
    d = datetime.date.fromisoformat(date)
    return datetime.datetime(d.year, d.month, d.day, best // 60, best % 60, tzinfo=ET)


# ─────────────────────────────────────────────── per-game price freeze
# A bat's price is FROZEN at his own game's first pitch. Two reasons, both seen live
# on 2026-08-08:
#   1. Once a game is underway the books either pull the HR prop or repost it as an
#      in-game number (+10000 and worse). That is not the market we drafted or priced
#      against, and scoring on it is meaningless.
#   2. A scrape that simply MISSES a bat used to delete his price, and build15 scores a
#      missing price as mkt_z = 0 -- which is 75% of TOTAL. Bats collapsed ~70 points and
#      ~60 rank places mid-slate (Harper 195.3 #5 -> 122.0 #68), so the tier colours
#      strobed every five minutes as the scrape came back full or partial.
# So: this file is now MERGED, never replaced. A price can be added or updated before
# first pitch; after first pitch it is read-only, and it can never be removed.
NKEY = lambda s: ''.join(c for c in unicodedata.normalize('NFKD', s or '')
                         if not unicodedata.combining(c)).lower().replace('.', '').strip()


def bat_first_pitch(date):
    """{normalized bat name: first pitch, minutes past midnight ET} from lineups_<date>.json."""
    try:
        games = json.load(open(f"lineups_{date}.json"))["games"]
    except Exception:
        return {}
    out = {}
    for g in games:
        m = re.match(r"(\d{1,2}):(\d{2})\s*([AP])M", (g.get("time") or "").strip(), re.I)
        if not m:
            continue
        h, mi, ap = int(m.group(1)) % 12, int(m.group(2)), m.group(3).upper()
        if ap == "P":
            h += 12
        t = h * 60 + mi
        for side in ("away_bats", "home_bats"):
            for nm in (g.get(side) or []):
                out[NKEY(nm)] = t
    return out


def prior_prices(date):
    """The last build's prices, read off the dated board.

    odds_<date>.json is only git-committed at the closing snapshot, so on the runner it is
    usually the MORNING file -- every build starts from a fresh checkout. D_<date>.json, on
    the other hand, is committed on every build and carries each bat's price verbatim. It is
    therefore the reliable record of "what was this bat priced at last time", which is what
    the first-pitch freeze needs in order to hold a 7:00pm price into an 8:15pm build.
    """
    try:
        P = json.load(open(f"D_{date}.json"))["players"]
    except Exception:
        return {}
    return {n: p["odds"] for n, p in P.items() if p.get("odds")}


def now_min_et():
    n = datetime.datetime.now(ET)
    return n.hour * 60 + n.minute


def emit(k, v):
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"{k}={v}\n")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    probe = "--probe" in sys.argv
    auto = "--auto" in sys.argv
    date = args[0] if args else None

    # --auto: stop refreshing once every game is underway. Prices past the last first
    # pitch are settling/pulled, not a market we want to score on -- and leaving the file
    # untouched is what makes the closing snapshot stable instead of re-committing all night.
    # ---------------------------------------------------------------- ALWAYS LEAVE A FILE
    # build15's load_dated() falls back to the PRIOR DAY when odds_<date>.json is absent, and
    # odds_<date>.json is only git-committed at the closing snapshot -- so every build starts from
    # a checkout without it. Every path through this script that returned WITHOUT writing therefore
    # handed build15 yesterday's prices, silently. 2026-08-09: from 2:16pm the board alternated
    # every five minutes between today's market and 8/8's -- 5 of 20 builds were 100% identical to
    # odds_2026-08-08.json. Abreu read +275 on one build and +474 (his 8/8 number) on the next, and
    # because blend is 0.75*mkt_z every score and tier colour flipped with it. The merge is
    # non-destructive, so writing the seed is always better than writing nothing.
    starts, tnow = bat_first_pitch(date), now_min_et()
    _lfp = last_first_pitch(date) if date else None
    _last = (_lfp.hour * 60 + _lfp.minute) if _lfp else None

    def live(n):
        """Is this bat's price still open for business? Unmapped bats (not in a posted
        lineup) fall back to the slate: open until the last first pitch, frozen after."""
        t = starts.get(NKEY(n))
        if t is None:
            t = _last
        return t is None or tnow < t

    prev = {}
    if date and os.path.exists(f"odds_{date}.json"):
        prev = json.load(open(f"odds_{date}.json"))
    if date:
        # The committed odds file is AUTHORITATIVE; the board only fills gaps. It used to be the
        # other way round -- the board overwrote the file -- which made sense while the file was
        # usually absent, but now that every path writes one it just means a poisoned board
        # re-poisons a corrected file. 2026-08-09: odds_2026-08-09.json was hand-repaired to each
        # bat's real pre-first-pitch price and the very next build put Abreu back to +474 (his 8/8
        # number) because the board still carried it. One entry per normalized name so an accent
        # spelling can't end up in there twice.
        _seen = {NKEY(n): n for n in prev}
        for n, v in prior_prices(date).items():
            k = NKEY(n)
            if k in _seen:
                continue
            _seen[k] = n
            prev[n] = v

    def persist(reason):
        if not date or not prev:
            return
        with open(f"odds_{date}.json", "w") as f:
            json.dump(prev, f)
        print(f"  wrote odds_{date}.json ({len(prev)} carried) -- {reason}")

    snap = False
    if auto and date:
        lfp = last_first_pitch(date)
        if lfp:
            now = datetime.datetime.now(ET)
            if now >= lfp:
                print(f"slate is underway (last first pitch {lfp:%-I:%M %p ET}) -- keeping the closing prices")
                persist("slate underway, nothing left to refresh")
                emit("snapshot", "false")
                return 0
            snap = now >= lfp - datetime.timedelta(minutes=SNAP_LEAD_MIN)

    try:
        status, nbytes, ntab, nlong, markets, info = scrape()
    except Exception as e:
        print(f"::error::fetch_odds: {type(e).__name__}: {e}")
        persist("scrape failed")
        return 2

    hr = markets.get("home_runs", {})
    print(f"HTTP {status}  {nbytes:,} bytes  tables={ntab} (long={nlong})")
    for k in MARKETS:
        print(f"  {k:14s} {len(markets[k]):4d} priced   cols={[c['n'] for c in info[k]]} "
              f"kept={[c['kept'] for c in info[k]]}")
    if hr:
        prices = sorted(v["price"] for v in hr.values())
        lines = sorted({v["line"] for v in hr.values()})
        print(f"  HR lines={lines}  range={prices[0]:+d}..{prices[-1]:+d}  median={prices[len(prices)//2]:+d}")
        for n, v in list(hr.items())[:6]:
            print(f"    {n:24s} {v['price']:+5d}  ({v['books']} books)")

    # compare against whatever is committed, so a probe reports real drift
    if date and os.path.exists(f"odds_{date}.json"):
        cur = json.load(open(f"odds_{date}.json"))
        both = [n for n in hr if n in cur]
        movers = [(n, cur[n], hr[n]["price"]) for n in both if cur[n] != hr[n]["price"]]
        movers.sort(key=lambda r: -abs(to_p(r[2]) - to_p(r[1])))
        print(f"\n  vs committed odds_{date}.json: {len(cur)} there, {len(hr)} scraped, "
              f"{len(both)} overlap, {len(movers)} moved "
              f"({100*len(movers)/max(1,len(both)):.1f}%)")
        for n, a, b in movers[:15]:
            print(f"    {n:24s} {a:+5d} -> {b:+5d}   ({100*(to_p(b)-to_p(a)):+.2f} pts implied)")

    if probe:
        print("probe only — nothing written")
        return 0 if len(hr) >= 150 else 1

    if not date:
        print("::error::fetch_odds: need a date to write files")
        return 2
    # COVERAGE GUARD, measured only over bats still open for business. A flat floor of 150
    # was useless: a scrape returning 205 of 306 sailed through and (before the merge below)
    # deleted a hundred prices. Compare like with like -- how many not-yet-started bats did
    # we have, and how many did this scrape find?
    _ok, _why = hr_sane(hr)
    if not _ok:
        print(f"::warning::fetch_odds: HR market failed the shape check ({_why}) "
              f"— not taking these prices")
        persist("wrong-market scrape refused")
        emit("snapshot", "false")
        return 1
    want = sum(1 for n in prev if live(n))
    got = sum(1 for n in hr if live(n))
    if len(hr) < 150 or (want >= 20 and got < 0.85 * want):
        print(f"::warning::fetch_odds: thin scrape ({len(hr)} HR prices; {got} of {want} "
              f"still-open bats) — not taking these prices")
        persist("thin scrape refused")
        emit("snapshot", "false")
        return 1

    # LONEBOOK-2026-08-21: cap single-book quotes at the multi-book field's LONE_PCTL.
    _multi = sorted(v["p"] for v in hr.values() if v.get("books", 0) >= 2)
    _cap = None
    if len(_multi) >= LONE_MIN_MULTI:
        _cap = _multi[min(len(_multi) - 1, int(LONE_PCTL * len(_multi)))]

    odds, froze, upd, new = dict(prev), 0, 0, 0
    ambig, capped = [], []
    for n, v in hr.items():
        if not live(n):
            froze += 1                      # game underway -> his price is already settled
            continue

        # NAMEDUP-2026-08-21: two bats, one name, no team on the row. Never let an ambiguous
        # scrape overwrite the committed file -- it is authoritative by this script's own rule.
        # With a held price, keep the candidate nearest it in PROBABILITY space, so the right
        # bat still tracks intraday drift. With no held price nothing can disambiguate, so take
        # the LONGEST candidate: under-rating a bat cannot ban him or make him an anchor.
        cand = v.get("alts") or [v]
        if len(cand) > 1:
            held = prev.get(n)
            if held is not None:
                pick = min(cand, key=lambda c: abs(to_p(c["price"]) - to_p(held)))
            else:
                pick = min(cand, key=lambda c: c["p"])
            ambig.append((n, [c["price"] for c in cand], pick["price"], held))
        else:
            pick = cand[0]

        price, bks = pick["price"], pick.get("books", 0)
        if _cap is not None and bks == 1 and pick["p"] > _cap:
            capped.append((n, price, to_a(_cap)))
            price = to_a(_cap)

        if n not in odds:
            new += 1
        elif odds[n] != price:
            upd += 1
        odds[n] = price

    for n, alts, pick, held in ambig:
        print(f"::warning::fetch_odds: '{n}' matched {len(alts)} rows {alts} -- "
              f"ambiguous (no team on the row); kept {pick:+d}"
              + (f" (nearest held {held:+d})" if held is not None else " (longest; nothing held)"))
    for n, was, now in capped:
        print(f"::notice::fetch_odds: '{n}' priced by ONE book at {was:+d} -- "
              f"above the multi-book {int(LONE_PCTL*100)}th pctl, lengthened to {now:+d}")
    with open(f"odds_{date}.json", "w") as f:
        json.dump(odds, f)

    mk = {}
    if os.path.exists(f"markets_{date}.json"):
        try:
            mk = json.load(open(f"markets_{date}.json"))
        except Exception:
            mk = {}
    for key, rows in markets.items():
        cur = dict(mk.get(key) or {})
        for n, v in rows.items():
            if live(n):
                cur[n] = {k: x for k, x in v.items() if k != "alts"}
        mk[key] = cur
    with open(f"markets_{date}.json", "w") as f:
        json.dump(mk, f, indent=0)

    print(f"odds_{date}.json: {len(odds)} prices ({new} new, {upd} moved, {froze} frozen "
          f"at first pitch, {len(prev)} carried)")
    if snap:
        print("::notice::closing odds snapshot -- staging odds/markets for commit")
    emit("snapshot", "true" if snap else "false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
