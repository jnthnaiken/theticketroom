#!/usr/bin/env python3
"""soccer_fgs.py -- FGS-2026-09-29. ONE first-goalscorer pick per slate, our best one.

Owner, 2026-09-29: "for soccer lets do like football and get rid of the lunch special and nightcap and
do a first goalscorer, our best pick of the slate each day". The 🍱 Lunch Special / 🌃 Nightcap
singles are no longer drafted (soccer_draft.js DEFAULTS.LUNCH_LATE false); this is the special.

LIKE FOOTBALL (nfl_ftd_stats.py, FTDSTATS-2026-09-29): the choice is made off the FOOTBALL, not off
a price. The first-goalscorer price is only what the slip is written at -- a man must be on the
first-goalscorer board (fgs.psv) to be picked, but his price does not move the pick.

THE CHANCE A MAN SCORES HIS MATCH'S FIRST GOAL
    lambda_i = his non-penalty xG per 90 (soccer_mock's blended, minutes-shrunk npxg90) x START
    START    = 1 if he is confirmed in the XI or the sheet is not out yet; 0.15 if he is BENCHED
               (a sub rarely plays the minutes the first goal usually comes in); 0 if out / void
    LAMBDA   = sum(lambda) / PRICED_SHARE  -- the other side and everyone the book did not price
    P(first) = lambda_i / LAMBDA x (1 - exp(-LAMBDA))
The pick is the highest P(first) on the slate among men with a first-goalscorer price whose match
has not kicked off. It is the same Poisson split the football pick uses, with xG where football has
usage; P is shown on the slip so the reader can see why.

STICKY. Written once to slates/<date>/ftd_pick.json and held on every rebuild, the way prices.json
holds a price, so a placed bet never moves. One exception: if the cached man is now BENCHED, OUT or
VOID and his match has not kicked off, the pick is made again without him -- the sheet came out and
he is not starting, and nobody has a bet on a man the page said to wait for.

The slip rides in D.meta.ftd (kind 'ftd', the leg flagged ftd:true), exactly as football's does, so
the page, soccer_grade.grade_ticket (reads p.ftd1 for an ftd leg) and the tracker need nothing new.
soccer_live.js stamps ftd1 from ESPN keyEvents (first goal that is not an own goal or a shootout kick).
"""
import json, math, os, re, unicodedata

PRICED_SHARE = 0.80      # the other side and the unpriced tail take ~20% of first goals
BENCH_START = 0.15


def norm(s):
    s = unicodedata.normalize('NFKD', str(s))
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r'\s+(jr|jnr|sr|snr|ii|iii|iv|v)\.?\s*$', '', s)
    return re.sub(r'[^a-z]', '', s)


def am(x):
    """'13/8' / '+163' / 'EVS' -> american int"""
    x = str(x).strip().upper()
    if x in ('EVS', 'EVEN'):
        return 100
    if '/' in x:
        a, b = x.split('/')
        d = float(a) / float(b)
        return int(round(d * 100)) if d >= 1 else int(round(-100 / d))
    return int(x.replace('+', ''))


def load_fgs(path):
    out = {}
    if not path or not os.path.exists(path):
        return out
    for ln in open(path, encoding='utf-8'):
        f = ln.rstrip('\n').split('|')
        if len(f) < 3 or not f[2].strip():
            continue
        try:
            out[(f[0], norm(f[1]))] = am(f[2])
        except ValueError:
            pass
    return out


def start_of(p):
    if p.get('out') or p.get('void'):
        return 0.0
    if p.get('status') == 'benched':
        return BENCH_START
    return 1.0


def p_first(players):
    """{name: P(first goal)} over every player dict (payload shape: match via `gmatch`/`match`)."""
    by = {}
    for n, p in players.items():
        x = p.get('npxg90')
        if x is None or x <= 0:
            continue
        m = p.get('match') or p.get('gmatch')
        by.setdefault(m, []).append((n, x * start_of(p)))
    out = {}
    for m, rows in by.items():
        L = sum(l for _, l in rows) / PRICED_SHARE
        if L <= 0:
            continue
        pany = 1 - math.exp(-L)
        for n, l in rows:
            out[n] = l / L * pany
    return out


def pick(players, fgs, started, exclude=()):
    """players: payload players dict; fgs: {(match_key, norm name): american}; started(name)->bool."""
    pf = p_first(players)
    best = None
    for n, p in players.items():
        k = (p.get('match'), norm(n))
        if k not in fgs or n not in pf or n in exclude or start_of(p) < 1.0 or started(n):
            continue
        row = dict(name=n, match=p.get('match'), odds=fgs[k], p_first=round(pf[n], 4),
                   npxg90=round(p.get('npxg90') or 0, 3))
        if best is None or row['p_first'] > best['p_first']:
            best = row
    return best


def choose(players, fgs, cache, started):
    """Sticky pick. Returns the row (or None) and writes the cache when it (re)picks."""
    if cache and os.path.exists(cache):
        c = json.load(open(cache, encoding='utf-8'))
        p = players.get(c.get('name')) or {}
        if start_of(p) < 1.0 and not started(c.get('name')):
            print(f"FGS: cached pick {c.get('name')} is not starting before kickoff -- picking again")
            n = pick(players, fgs, started, exclude=(c.get('name'),))
            if n:
                json.dump(n, open(cache, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
            return n
        print(f"FGS: holding {c['name']} {c['odds']:+d} (cached)")
        return c
    if not fgs:
        print('FGS: no fgs.psv for this slate -- no first-goalscorer pick')
        return None
    c = pick(players, fgs, started)
    if c and cache:
        os.makedirs(os.path.dirname(os.path.abspath(cache)), exist_ok=True)
        json.dump(c, open(cache, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    if c:
        print(f"FGS: {c['name']} ({c['match']}) {c['odds']:+d}  P(first) {c['p_first']:.1%}  npxG90 {c['npxg90']}")
    else:
        print('FGS: nobody priced for the first goal is starting -- no pick')
    return c
