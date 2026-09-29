#!/usr/bin/env python3
"""nfl_ftd.py -- FIRSTTD-2026-09-29. ONE first-touchdown pick per slate, our best one.

Owner, 2026-09-29: "think instead of the current specials we should do one first touchdown pick.
our best one. one per slate." It replaces the 🍱 Early Window / 🌃 Sunday Night specials.

THE CHANCE A MAN SCORES HIS GAME'S FIRST TOUCHDOWN
    Each priced man i in a game has an anytime chance p_i -- FTDV2: the MARKET's, off his posted anytime
    price (it was p_value / p_model; see FTDV2 below). Treat touchdowns as independent Poisson streams:
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

FTDV2-2026-09-29 -- owner: "you may need to run some test and not stop until you find a more succesful
way to identify those". What the tests found (claude/ftdv2-2026-09-29.md):
  * 9,872 NFL touchdowns 2019-2026 (nflverse): the first TD goes to men in proportion to their anytime
    chance, with three small, repeatable tilts -- heavy usage (elasticity 0.11 on share of team touches),
    the home side (+8%) and the favourite (+6%). Position does not matter once usage is in.
  * On the 47 archived 2026 games the MARKET's anytime price predicts the first scorer better than our
    own p_value (log-loss 2.66 vs 2.73), so the chance is now anchored on the market price.
  * The first-TD book charges ~12% on the shortest names and ~29% on the longest (PIT@CLE, the one real
    board). Longshots cannot win that fight: 864 games 2023-26 with priced-like odds, +800..+1500 picks
    returned -10% to -22%, +300..+1000 picks on the favourite +6% to +17%.
So v2 takes the favourite's side, +300..+1000, and the best EV there: P(first) from the market's anytime
price x the tilt. It hit 2 of 10 slates (and 8 of 47 games) against the old rule's 1 of 10 (4 of 47).

🪙 TOSS-2026-09-29 -- THE BIGGEST SIGNAL, AND IT IS ONLY KNOWN AT THE COIN TOSS. The team that receives the
opening kickoff scores the game's first touchdown 57% of the time, every season 2019-25 (50-61%), 1,860
games. In the conditional logit it is x1.49 (log se 0.056) -- larger than every other tilt together, and
larger than the book's markup on short names. Nobody knows the receiver before the toss (a team's receive
habit does not carry over: year-to-year corr ~0.1), so owner's call: "Yes, two picks". The slate's pick is
now ONE GAME and TWO MEN -- the best first-TD play IF each side gets the ball first -- and people place it
after the toss. The game is the one whose pair has the best average EV. The page shows both until the live
feed sees the opening drive, then only the one in play; the ledger grades only that one.

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
FTD_MIN, FTD_MAX = 300, 1000        # FTDV2: was 1500 -- the long end is where the vig lives
TEAM_OPP_PG = 58.5                  # team carries+targets a game, 2019-26 -- turns tchpg into a usage share
TILT = dict(usage=0.109, has=0.066, home=0.060, fav=0.093, recv=0.397, mu=-2.123)   # conditional logit, 9,872 TDs, with the receiver in


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


def p_mkt(s):
    """the market's anytime chance, off the posted price (vig left in: the split normalises it away)."""
    o = s.get('odds')
    if o is None:
        return None
    return 100 / (o + 100) if o > 0 else -o / (-o + 100)


def fav_team(scored, match):
    """the side with the bigger implied team total, or None when they are level / unknown."""
    imp = {}
    for s in scored:
        if s['match'] == match and s.get('imp') is not None:
            imp[s.get('team')] = s['imp']
    if len(imp) < 2:
        return None
    (a, x), (b, y) = sorted(imp.items(), key=lambda kv: -kv[1])[:2]
    return a if x > y else None


def tilt(s, fav, recv=None):
    """FTDV2: how much more than his anytime share of the TDs a man takes of the FIRST one.
    TOSS: `recv` is the team taken to receive the opening kickoff (None = not known)."""
    t = s.get('tchpg') or 0
    has = t > 0
    ls = (math.log(min(0.6, max(0.02, t / TEAM_OPP_PG))) - TILT['mu']) if has else 0.0
    home = s.get('team') == s['match'].split('-at-')[-1]
    return math.exp(TILT['usage'] * ls + TILT['has'] * has + TILT['home'] * home + TILT['fav'] * (s.get('team') == fav)
                    + TILT['recv'] * (recv is not None and s.get('team') == recv))


def p_first(scored, recv=None):
    """{(match, norm name): P(first TD)} over every priced man in scored.json -- FTDV2: the market's anytime
    chance split Poisson-wise, tilted, with the unpriced share held at 1 - PRICED_SHARE of the game's TDs."""
    by = {}
    for s in scored:
        p = p_mkt(s)
        if p is None or not (0 < p < 1):
            continue
        by.setdefault(s['match'], []).append(s)
    out = {}
    for m, rows in by.items():
        fav = fav_team(scored, m)
        lam = [(norm(s['name']), -math.log(1 - min(0.95, p_mkt(s))), tilt(s, fav, (recv or {}).get(m))) for s in rows]
        L = sum(l for _, l, _ in lam) / PRICED_SHARE
        W = sum(l * w for _, l, w in lam) / PRICED_SHARE
        if L <= 0:
            continue
        pany = 1 - math.exp(-L)
        for n, l, w in lam:
            out[(m, n)] = l * w / W * pany
    return out


def pick(scored, ftd, exclude=(), fav_only=True):
    pf = p_first(scored)
    favs = {m: fav_team(scored, m) for m in {s['match'] for s in scored}}
    best = None
    for s in scored:
        if fav_only and s.get('team') != favs.get(s['match']):
            continue
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
    if best is None and fav_only:          # no favourite priced inside the band -> best of either side
        return pick(scored, ftd, exclude, fav_only=False)
    return best


def _side_best(scored, ftd, match, team, exclude=()):
    """TOSS: the best first-TD play on `team`'s side of `match`, GIVEN `team` receives the opening kickoff."""
    pf = p_first([s for s in scored if s['match'] == match], recv={match: team})
    best = None
    for s in scored:
        if s['match'] != match or s.get('team') != team or s['name'] in exclude:
            continue
        k = (match, norm(s['name']))
        if k not in ftd or k not in pf:
            continue
        if (s.get('pos') or '').upper() == 'QB' or s.get('out') or s.get('void'):
            continue
        o = ftd[k]
        if not (FTD_MIN <= o <= FTD_MAX):
            continue
        ev = pf[k] * dec(o) - 1
        row = dict(name=s['name'], team=team, recv=team, match=match, pos=s.get('pos'), odds=o,
                   p_first=round(pf[k], 4), ev=round(ev, 4), anytime_odds=s.get('odds'))
        if best is None or row['ev'] > best['ev']:
            best = row
    return best


def pick_toss(scored, ftd, exclude=(), only=None):
    """TOSS: {match, toss:True, picks:{team: row}} for the game whose two if-they-receive plays have the best
    average EV. Both sides must have a man in the band. `only` pins the game (a re-pick after a scratch)."""
    teams = {}
    for s in scored:
        teams.setdefault(s['match'], set()).add(s.get('team'))
    best = None
    for m, ts in sorted(teams.items()):
        if only and m != only:
            continue
        side = {t: _side_best(scored, ftd, m, t, exclude) for t in ts if t}
        if len(side) != 2 or not all(side.values()):
            continue
        avg = sum(r['ev'] for r in side.values()) / 2
        if best is None or avg > best['ev']:
            best = dict(match=m, toss=True, ev=round(avg, 4), picks=side)
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
    if os.path.exists(A.cache) and json.load(open(A.cache, encoding='utf-8')).get('toss'):
        c = json.load(open(A.cache, encoding='utf-8'))
        ko = ((fx.get('matches') or {}).get(c['match']) or {}).get('kickoff')
        if ko is not None and now < ko:
            for t, r in list(c['picks'].items()):
                if (by_name.get(r['name']) or {}).get('out'):
                    print(f"FIRSTTD: {r['name']} ({t} receives) is now OUT before kickoff -- picking that side again")
                    nr = _side_best(scored, ftd, c['match'], t, exclude=(r['name'],))
                    if nr: c['picks'][t] = nr
                    else: del c['picks'][t]
            json.dump(c, open(A.cache, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
        for t, r in c['picks'].items():
            print(f"FIRSTTD: if {t} receives -> {r['name']} {r['odds']:+d}  P(first) {r['p_first']:.1%}  EV {r['ev']:+.3f}")
        return 0
    if os.path.exists(A.cache):                         # a pre-TOSS single pick already placed: hold it
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
        c = pick_toss(scored, ftd)
        if c:
            json.dump(c, open(A.cache, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
            for t, r in c['picks'].items():
                print(f"FIRSTTD: {c['match']} -- if {t} receives -> {r['name']} {r['odds']:+d}  "
                      f"P(first) {r['p_first']:.1%}  EV {r['ev']:+.3f}")
            return 0
    if not c:
        print('FIRSTTD: nothing in the price band -- no pick')
        return 0
    print(f"FIRSTTD: {c['name']} ({c['pos']} {c['team']}) {c['odds']:+d}  "
          f"P(first) {c['p_first']:.1%}  EV {c['ev']:+.3f}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
