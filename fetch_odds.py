#!/usr/bin/env python3
"""
fetch_odds.py — re-scrape VegasInsider player props and rewrite odds_<date>.json.

WHY THIS EXISTS
    Until 2026-08-08 the odds were scraped ONCE, by hand, during the morning
    browser build, and never refreshed. `fetch_mlb.py` pulls StatsAPI + weather
    and nothing else, so the server drafted, priced and graded every ticket off
    morning numbers all day. Measured on 2026-08-08 at 4:45pm ET against the
    prices actually showing on the board: of the 255 bats in both, 220 (86.3%)
    had moved, 180 by 40+ cents -- Harper +259 -> +418, Crow-Armstrong +292 ->
    +440, Baldwin +310 -> +522. Those three carried two moons, the salami, three
    builders and the whole Lunch Special.

    The client could already be re-priced by hand (paste box / per-bat inputs)
    but it saved to ONE browser's localStorage, so the build, the archive and
    every other visitor never saw it.

OUTPUT
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
"""
import sys, os, json, re, gzip, io, statistics
import urllib.request, urllib.error
from html.parser import HTMLParser

URL = "https://www.vegasinsider.com/mlb/odds/player-props/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
MARKETS = ["strikeouts", "home_runs", "total_bases", "rbi"]
MIN_COL = 10        # a book column needs this many prices to count
TOP_FRAC = 0.60     # one price on >60% of rows = fixed juice, not a market


# ─────────────────────────────────────────────────────────── html -> tables
class Tables(HTMLParser):
    """Minimal stdlib table extractor: no lxml/bs4 dependency on the runner."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self._t, self._r, self._c = [], None, None, None
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self._t = []
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
                self._t = None
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
        out[name] = {"line": modal, "p": round(mp, 5), "price": price,
                     "books": len(ps), "spread": round(max(ps) - min(ps), 5)}
    return out, colinfo


def scrape():
    status, html = get_html()
    p = Tables()
    p.feed(html)
    tabs = [t for t in p.tables if len(t) > 20]          # the four prop tables are long
    markets, info = {}, {}
    for i, key in enumerate(MARKETS):
        if i < len(tabs):
            markets[key], info[key] = parse_market(tabs[i])
        else:
            markets[key], info[key] = {}, []
    return status, len(html), len(p.tables), len(tabs), markets, info


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    probe = "--probe" in sys.argv
    date = args[0] if args else None

    try:
        status, nbytes, ntab, nlong, markets, info = scrape()
    except Exception as e:
        print(f"::error::fetch_odds: {type(e).__name__}: {e}")
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
    if len(hr) < 150:
        print(f"::warning::fetch_odds: only {len(hr)} HR prices — refusing to overwrite odds_{date}.json")
        return 1

    odds = {n: v["price"] for n, v in hr.items()}
    with open(f"odds_{date}.json", "w") as f:
        json.dump(odds, f)
    with open(f"markets_{date}.json", "w") as f:
        json.dump(markets, f, indent=0)
    print(f"wrote odds_{date}.json ({len(odds)}) + markets_{date}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
