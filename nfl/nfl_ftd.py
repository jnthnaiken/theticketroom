#!/usr/bin/env python3
"""nfl_ftd.py -- FIRSTTD-2026-09-29. ONE first-touchdown pick per slate, our best one.

Owner, 2026-09-29: "think instead of the current specials we should do one first touchdown pick.
our best one. one per slate." It replaces the 🍱 Early Window / 🌃 Sunday Night specials.

THE CHANCE A MAN SCORES HIS GAME'S FIRST TOUCHDOWN
    Each priced man i in a game has the board's anytime chance p_i -- p_value (the value model's
    blend) where nfl_value.py ran, else p_model. Treat touchdowns as independent Poisson streams:
        lambda_i = -ln(1 - p_i)                        his expected touchdowns
        LAMBDA   = sum(lambda_i) / PRICED_SHARE        the game's, grossed up for the scorers the
                                                       anytime market does not price (D/ST, returns,
                                                       fringe men past the 25 listed)
        P(first) = lambda_i / LAMBDA * (1 - exp(-LAMBDA))
    The last factor is P(at least one TD in the game): a scoreless-in-the-end-zone game loses every
    first-TD ticket, which the books settle the same way.

WHICH MAN
    EV = P(first) x decimal(FTD price) - 1, over men the board would bet anyway: not a QB, not ruled
    out, a first-TD price between FTD_MIN and FTD_MAX. The best EV on the whole slate is the pick,
    positive or not -- the owner asked for one a slate, and the best one. The price band keeps the
    Poisson split away from the tails it is worst at: the anytime replay showed the model's longest
    shots are where it is most wrong (claude/football-valuereplay-2026-09-29.md).

STICKY
    The pick is written to --cache (slates/<date>/ftd_pick.json, committed by the build) the first
    time and REUSED on every rebuild, the way prices.json holds a price, so a placed bet never moves.
    The one exception: if the cached man is now ruled OUT and his game has not kicked off, the pick
    is made again without him -- a scratch before kickoff is not a bet anyone has placed yet.

    python3 nfl_ftd.py scored.json fixtures.json ftd.psv --date D --cache ../slates/D/ftd_pick.json
Never fatal: exits 0 with no pick written when there is no ftd.psv or nothing to pick.
"""
import argparse, datetime, json, math, os, re, sys, unicodedata

PRICED_SHARE = 0.93      # ~7% of NFL touchdowns go to men the anytime market does not list (D/ST etc.)
FTD_MIN, FTD_MAX = 300, 1500


def norm(s):
    s = unicodedata.normalize('NFKD', str(s))
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r'\s+(jr|jnr|sr|snr|ii|iii|iv|v)\.?\s*$', '', s)
    return re.sub(r'[^a-z]', '', s)


def am(x):
    """'+650' / '13/2' / '-110' -> american int"""
    x = str(x).strip()
    if '/' in x:
        a, b = x.split('/')
        d = float(a) / float(b)
        return int(round(d * 100)) if d >= 1 else int(round(-100 / d))
    return int(x.replace('+', ''))


def dec(o):
    return 1 + o / 100 if o > 0 else 1 + 100 / -o


def load_ftd(path):
    out = {}
    for ln in open(path, encoding='utf-8'):
        f = ln.rstrip('\n').split('|')
        if len(f) < 3 or not f[2].strip():
            continue
        try:
            out[(f[0], norm(f[1]))] = am(f[2])
        except ValueError:
            pass
    return out


def p_first(scored):
    """{(match, norm name): P(first TD)} over every priced man in scored.json."""
    by = {}
    for s in scored:
        p = s.get('p_value') if s.get('p_value') is not None else s.get('p_model')
        if p is None or not (0 < p < 1):
            continue
        by.setdefault(s['match'], []).append((norm(s['name']), -math.log(1 - p)))
    out = {}
    for m, rows in by.items():
        lam = sum(l for _, l in rows) / PRICED_SHARE
        if lam <= 0:
            continue
        pany = 1 - math.exp(-lam)
        for n, l in rows:
            out[(m, n)] = l / lam * pany
    return out


def pick(scored, ftd, exclude=()):
    pf = p_first(scored)
    best = None
    for s in scored:
        k = (s['match'], norm(s['name']))
        if k not in ftd or k not in pf or s['name'] in exclude:
            continue
        if (s.get('pos') or '').upper() == 'QB' or s.get('out') or s.get('void'):
            continue
        o = ftd[k]
        if not (FTD_MIN <= o <= FTD_MAX):
            continue
        ev = pf[k] * dec(o) - 1
        row = dict(name=s['name'], team=s.get('team'), match=s['match'], pos=s.get('pos'),
                   odds=o, p_first=round(pf[k], 4), ev=round(ev, 4),
                   p_any=s.get('p_value') if s.get('p_value') is not None else s.get('p_model'),
                   anytime_odds=s.get('odds'))
        if best is None or row['ev'] > best['ev']:
            best = row
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('scored'); ap.add_argument('fixtures'); ap.add_argument('ftd')
    ap.add_argument('--date', required=True); ap.add_argument('--cache', required=True)
    ap.add_argument('--now-et-min', type=int, default=None)
    A = ap.parse_args()
    if not os.path.exists(A.ftd):
        print(f'FIRSTTD: no {A.ftd} for {A.date} -- no first-TD pick this slate')
        return 0
    scored = json.load(open(A.scored, encoding='utf-8'))
    fx = json.load(open(A.fixtures, encoding='utf-8'))
    ftd = load_ftd(A.ftd)
    by_name = {s['name']: s for s in scored}
    now = A.now_et_min
    if now is None:
        et = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=4)
        now = (et.hour * 60 + et.minute) if et.strftime('%Y-%m-%d') == A.date else (-1 if et.strftime('%Y-%m-%d') < A.date else 10 ** 6)
    if os.path.exists(A.cache):
        c = json.load(open(A.cache, encoding='utf-8'))
        s = by_name.get(c.get('name')) or {}
        ko = ((fx.get('matches') or {}).get(c.get('match')) or {}).get('kickoff')
        if s.get('out') and ko is not None and now < ko:
            print(f"FIRSTTD: cached pick {c['name']} is now OUT before kickoff -- picking again")
            c = pick(scored, ftd, exclude=(c['name'],))
            if c:
                json.dump(c, open(A.cache, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
        else:
            print(f"FIRSTTD: holding {c['name']} {c['odds']:+d} (cached)")
    else:
        c = pick(scored, ftd)
        if c:
            json.dump(c, open(A.cache, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    if not c:
        print('FIRSTTD: nothing in the price band -- no pick')
        return 0
    print(f"FIRSTTD: {c['name']} ({c['pos']} {c['team']}) {c['odds']:+d}  "
          f"P(first) {c['p_first']:.1%}  EV {c['ev']:+.3f}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
