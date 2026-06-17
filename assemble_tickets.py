"""
The Ticket Room — ticket assembler (hardcoded rules + the latest updates).

Drop this into the build step AFTER the field is scored (it consumes the same
`D` the board renders: D['players'][name] = {odds, TOTAL, game, gmatch, gtime,
late, status, void, out, ...}). Call assemble(D) and it returns D['tickets'].

WHAT'S HARDCODED
================
Existing rules (from the model/README + tierOf):
  * Eligible field   = priced bats in the lineup, not voided/scratched.
  * Anchor ranking   = model TOTAL (the full-pool re-rank), one anchor per game.
  * Tier             = premium (rank < 9), strong (rank < 32), else value.
  * Moons            = anchor + 2 longshot partners, snake-drafted so each
                       parlay pairs a stronger bat with a longer shot.
  * Salami           = four longest shots in distinct games, full round robin.
  * Builders         = leftover bats as single-leg bankroll plays.
  * Nightcap         = the late single.

THE THREE UPDATES
=================
  (1) CHALK ROUTING  — chalk = the 8 shortest-odds bats. They are eligible
      ONLY in the lunch special and the nightcap. Moons, builders, and the
      salami are chalk-free.
  (2) MOON STRUCTURE — 5 moons in a 2/2/1 split: A1 x2, A2 x2, A3 x1.
      The 4th-best anchor (A4) LEADS THE SALAMI.
  (3) CARRYOVER      — games still suspended/resuming are rolled to the next
      slate (see carryover()).
"""
import re, datetime

LUNCH_CUT_MIN = 16 * 60          # 4:00 PM ET splits the lunch window from night
CHALK_N       = 8                # the ban8: 8 shortest-odds bats (nightcap/lunch ONLY)
GATE_N        = 33               # parlay/builder pool = the 33 by odds BELOW the ban8
FLOOR         = 75               # TOTAL floor for OUR picks (moon anchors/partners + salami legs).
                                 # Sub-floor bats stay in the pool as builder singles for visitors.
MOON_PLAN     = (0, 0, 1, 1, 2)  # anchor indices per moon -> A1,A1,A2,A2,A3 (2/2/1)

# ---------- ticket-name pools (the brain names tickets here; the HTML only renders) ----------
# Big, curated, theme-tight pools. Assigned without replacement and rotated by day-of-year,
# so a slate never repeats a name and the set shifts day to day. No near-synonyms.
NAME_POOLS = {
    "moon": [  # launch / flight / going deep
        "Escape Velocity", "Past the Event Horizon", "Shot Into Orbit", "Sky High",
        "Defying Gravity", "Through the Stratosphere", "Catching a Vapor Trail",
        "Into the Clouds", "Full Afterburner", "Breaking the Sound Barrier",
        "Reaching for the Stars", "Slipping the Surly Bonds", "Cleared for Launch",
        "Booster Ignition", "Hitting Apogee", "Mach Breaker", "Punching Through the Ceiling",
        "Riding the Jet Stream", "Upper Deck Bound", "Off the Scoreboard", "To the Heavens",
        "Liftoff Sequence", "Second Stage", "Leaving the Atmosphere", "Out of the Solar System",
        "Zero Gravity", "Trajectory Locked", "Sonic Boom", "The Long Bomb", "Moon Landing",
        "Rocket Fuel", "Thrust Vector", "Crossing the Karman Line", "No Doubter",
        "Tape Measure Job", "Onto the Concourse", "Splash Hit", "The Way Back Machine",
        "Goodbye Baseball", "Touch 'Em All", "Climbing the Ladder", "Ballistic Arc",
        "Orbital Insertion", "Star Sailor", "Going Supersonic", "The Slingshot",
        "Heat Shield Off", "Beyond the Bleachers", "Into the Upper Air", "The Apollo",
        "Terminal Climb", "Past Low Earth Orbit",
    ],
    "biggest": [  # the feast / the spread
        "The Charcuterie Board", "The Full Spread", "The Whole Tray", "Meat Sweats",
        "The Grand Buffet", "Family Style", "The Tasting Menu", "Surf and Turf",
        "The Sampler Platter", "All You Can Eat", "The Combo Platter", "Second Helpings",
        "The Smorgasbord", "The Whole Hog", "The Deli Case", "Loaded Plate", "The Feast",
        "The Cold Cuts", "Heaping Plate", "The Potluck", "The Tailgate Spread",
        "The Whole Enchilada", "The Big Platter", "Seconds and Thirds",
    ],
    "late": [  # closing time / after dark
        "The Nightcap", "Last Call", "Closing Time", "After Hours", "One for the Road",
        "Lights Out", "Final Pour", "The Closer", "Last Ring of the Bell", "Midnight Special",
        "Last Train Home", "The Curfew", "Burning the Midnight Oil", "The Late Show",
        "Bar's Last Round", "Nightfall", "The Witching Hour", "Last Orders", "The Final Bell",
        "Under the Lights",
    ],
    "lunch": [  # midday
        "The Power Lunch", "Midday Meal", "High Noon", "The Blue Plate", "Lunch Rush",
        "The Noon Whistle", "Brown Bag Special", "The Midday Mash", "Sunshine Special",
        "Half-Day Hammer", "The Lunch Break", "Noon Special", "The Matinee", "Daylight Special",
        "The Early Bird", "Midday Money", "The Lunch Counter", "First-Pitch Feast",
    ],
    "builder": [  # bankroll / getting paid
        "Cash Is King", "Paid in Full", "Bag Secured", "The Sure Thing", "Easy Money",
        "Stack It High", "Mailbox Money", "Bread Winner", "Walk-Off Wallet", "Petty Cash",
        "Pay the Rent", "Cha-Ching", "Money in the Bank", "The Day Job", "Clock In, Cash Out",
        "Grocery Money", "The Side Hustle", "Beer Money", "Coffee's on Me", "The Tip Jar",
        "Found Money", "Gas Money", "The Piggy Bank", "Padding the Bankroll", "The Lunch Tab",
        "The Down Payment", "Spare Change", "The Nest Egg", "Payday", "House Money",
        "Keep the Change", "Cover Charge", "The Cushion", "Quick Buck", "In the Black",
        "The Float", "Walking-Around Money", "The Cookie Jar", "Pocket Money", "The Allowance",
        "Cashing Out", "The Slow Grind", "Steady Drip", "Singles Add Up", "Chip Stack",
        "The Vig Killer", "Free Roll", "Direct Deposit", "Rainy Day Fund", "The ATM",
        "Milk Money", "Tab Settled",
    ],
}


# ---------- odds / time helpers ----------
def a2d(o):                       # American -> decimal
    return 1 + (o / 100.0 if o > 0 else 100.0 / abs(o))

def d2a(d):                       # decimal -> American
    return round((d - 1) * 100) if d >= 2 else round(-100 / (d - 1))

def gmin(gt):
    m = re.match(r'(\d+):(\d+)\s*(AM|PM)', gt or '')
    if not m:
        return None
    h = int(m[1]) % 12 + (12 if m[3] == 'PM' else 0)
    return h * 60 + int(m[2])


# ---------- selection ----------
def assemble(D):
    P  = D['players']
    gs = D.get('meta', {}).get('gs', {})            # live game-state map
    susp = lambda n: gs.get(str(P[n]['game'])) == 'susp'
    # pending = a bat carried from a still-resuming suspended game -> SINGLES ONLY until that game is final.
    # Set per-bat by carryover() on only the bats we actually had on the suspended board (never a whole game).
    pend = lambda n: bool(P[n].get('pending'))

    elig = [n for n, p in P.items()
            if p.get('odds') and not p.get('out') and not p.get('void')]
    byT  = lambda names: sorted(names, key=lambda n: P[n]['TOTAL'], reverse=True)
    byO  = lambda names: sorted(names, key=lambda n: P[n]['odds'])      # shortest first
    tmin = lambda n: gmin(P[n]['gtime']) or 0

    # update (1): ban8 = 8 shortest odds (nightcap/lunch only). The PARLAY/BUILDER pool is the
    # NEXT GATE_N=33 by odds below the ban8 (+ties); `extra` = #42+ reached only if the 33
    # cannot field a distinct game. Parlays/builders never touch the ban8.
    ranked   = byO(elig)
    chalk    = set(ranked[:CHALK_N])
    rest     = ranked[CHALK_N:]
    if len(rest) > GATE_N:
        cut      = P[rest[GATE_N - 1]]['odds']
        nonchalk = [n for n in rest if P[n]['odds'] <= cut]
    else:
        nonchalk = rest[:]
    _ncset = set(nonchalk)
    extra  = [n for n in rest if n not in _ncset]

    latest      = max((gmin(P[n]['gtime']) or 0) for n in elig)
    lunch_games = {P[n]['game'] for n in elig if (gmin(P[n]['gtime']) or 0) < LUNCH_CUT_MIN}
    night_games = {P[n]['game'] for n in elig if (gmin(P[n]['gtime']) or 0) == latest}

    # anchors: best non-chalk by TOTAL, one per game, never a pending (resuming) bat, never below the floor
    anchors, seen = [], set()
    for n in byT(nonchalk):
        g = P[n]['game']
        if g in seen or pend(n) or P[n]['TOTAL'] < FLOOR:
            continue
        anchors.append(n); seen.add(g)
        if len(anchors) >= 4:
            break

    tickets, used = [], set()

    def leg(n):
        p = P[n]
        return {"name": n, "team": p['team'], "total": p['TOTAL'], "aT": p['aT'],
                "wf": p['wf'], "gmatch": p['gmatch'], "gtime": p['gtime'],
                "game": p['game'], "late": bool(p.get('late')), "odds": p['odds'],
                "status": p['status']}

    # Tightest distinct-game set of `need` partners around the anchor (min time-span), drawn in
    # preference order from the 33, then #42+. No cross-day reach: a wide span just trips the
    # renderer's lineup-timing flag; we never grab a far leg when a tighter one exists.
    def min_span_fill(a, need, pref):
        at = tmin(a); g0 = P[a]['game']
        cands = [n for n in pref if n not in used and n not in anchors
                 and P[n]['game'] != g0 and P[n]['TOTAL'] >= FLOOR and not pend(n)]
        times = sorted(set([at] + [tmin(n) for n in cands]))
        best, bestkey = [], (-1, 1)
        for lo in times:
            if lo > at:
                break
            for hi in times:
                if hi < at or hi < lo:
                    continue
                legs, games = [], {g0}
                for n in cands:
                    tn = tmin(n)
                    if lo <= tn <= hi and P[n]['game'] not in games:
                        legs.append(n); games.add(P[n]['game'])
                        if len(legs) >= need:
                            break
                key = (len(legs), -(hi - lo))
                if key > bestkey:
                    bestkey, best = key, legs
        return best

    def best_partners(a, need, msort):
        legs = min_span_fill(a, need, msort(nonchalk))          # the 33 first
        if len(legs) < need:                                    # widen to #42+ only if forced
            legs = min_span_fill(a, need, msort(nonchalk) + msort(extra))
        for n in legs:
            used.add(n)
        return legs

    def add(name, kind, badge, names, rr=None):
        legs = [leg(n) for n in names]
        t = {"name": name, "kind": kind, "badge": badge, "note": cwnote(kind, names),
             "players": legs, "nlegs": len(legs), "anchor": names[0],
             "lock": min(l['gtime'] for l in legs), "has_late": any(l['late'] for l in legs),
             "final": False, "rr": rr}
        tickets.append(t)

    # ---- ticket naming: date-rotated, no repeats within a slate ----
    try:
        _doy = datetime.date.fromisoformat(D.get('meta', {}).get('date', '')).timetuple().tm_yday
    except Exception:
        _doy = 0
    _name_used, _name_ctr = set(), {}
    def name_for(kind):
        pool = NAME_POOLS.get(kind) or ["Ticket"]
        i = _name_ctr.get(kind, 0); _name_ctr[kind] = i + 1
        L = len(pool)
        for k in range(L):                       # rotate by date, skip any already taken
            cand = pool[(_doy + i + k) % L]
            if cand not in _name_used:
                _name_used.add(cand); return cand
        base, s = pool[(_doy + i) % L], 2         # pool exhausted (shouldn't happen): suffix
        while f"{base} {s}" in _name_used:
            s += 1
        nm = f"{base} {s}"; _name_used.add(nm); return nm

    # ---- ticket notes (ported from the client micro-note generator; the html only renders) ----
    import math
    def _jsround(x):
        return int(math.floor(x + 0.5))
    def _isostr(p):
        s = p.get('iso')
        return s if (isinstance(s, str) and s.startswith('.')) else None
    def _isoval(p):
        s = _isostr(p)
        try:
            return float('0' + s) if s else 0.0
        except Exception:
            return 0.0
    def _lastnm(s):
        sfx = {'jr', 'jr.', 'sr', 'sr.', 'ii', 'iii'}
        t = [w for w in s.split(' ') if w.lower() not in sfx]
        return t[-1] if t else s
    def _micro(p):
        hr9 = p.get('hr9'); hh = p.get('hh') or 0; la = p.get('la') or 0
        wf = 1.0 if p.get('wf') is None else p.get('wf'); iso = _isostr(p); iv = _isoval(p)
        o = []
        if hr9 is not None and hr9 >= 1.6:   o.append((9, 'mtx', 'soft arm'))
        elif hr9 is not None and hr9 >= 1.35: o.append((6, 'mtx', 'beatable arm'))
        if wf >= 1.05:   o.append((8, 'park', 'wind out'))
        elif wf >= 1.02: o.append((4, 'park', 'park boost'))
        if hh >= 52:   o.append((7, 'hh', f"{_jsround(hh)}% hard-hit"))
        elif hh >= 46: o.append((3.5, 'hh', f"{_jsround(hh)}% hard-hit"))
        if 16 <= la <= 23: o.append((5, 'la', f"{_jsround(la)}\u00b0 ideal"))
        if iso and iv >= 0.20: o.append((4.5, 'iso', f"{iso} ISO"))
        if hr9 is not None and hr9 < 1.0 and not o: o.append((1, 'mtx', 'tough arm'))
        if not o: o.append((0.5, 'x', 'live spot'))
        o.sort(key=lambda r: r[0], reverse=True)
        return o
    def _micropick(p, used):
        for w, dim, lab in _micro(p):
            if dim not in used:
                used.add(dim); return lab
        first = _micro(p)[0]; used.add(first[1]); return first[2]
    def cwnote(kind, names):
        if len(names) == 1:
            a = P[names[0]]; r = _micro(a); e = [r[0][2]]
            if len(r) > 1:
                e.append(r[1][2])
            lead = 'Last call' if kind == 'late' else ('Midday' if kind == 'lunch' else 'Single')
            tail = (", " + e[1]) if len(e) > 1 else ""
            return f"{lead}: {a.get('nm', names[0])} \u2014 {e[0]}{tail}."
        used = set()
        bits = " \u00b7 ".join(_lastnm(P[n].get('nm', n)) + " " + _micropick(P[n], used) for n in names)
        return ("Round-robin \u00b7 " + bits) if kind == 'biggest' else bits

    # update (2): A4 leads the salami. DRAFT the salami first so it keeps its own tight window
    # (4 longest shots, distinct games, chalk-free); then the 5 moons (2/2/1) by TOTAL.
    byOdesc = lambda ns: sorted(ns, key=lambda n: P[n]['odds'], reverse=True)
    sal_legs = best_partners(anchors[3], 3, byOdesc) if len(anchors) >= 4 else []
    moon_duos = [(anchors[ai], best_partners(anchors[ai], 2, byT))
                 for ai in MOON_PLAN if ai < len(anchors)]
    for a, d in moon_duos:                                      # emit moons first (display order)
        add(name_for("moon"), "moon", "\U0001f680", [a] + d,
            rr={"struct": "by 2s & 3", "risk": 4.0})
    if len(anchors) >= 4:
        add(name_for("biggest"), "biggest", "\U0001f96a", [anchors[3]] + sal_legs,
            rr={"struct": "by 2s, 3s & 4", "risk": 11.0})

    # update (1): chalk only here — nightcap (late game) + lunch special (day games)
    ncap = byO([n for n in chalk if P[n]['game'] in night_games])
    if ncap:
        add(name_for("late"), "late", "\U0001f303", [ncap[0]])
    lunchc = byO([n for n in chalk if P[n]['game'] in lunch_games])
    if lunchc:
        add(name_for("lunch"), "lunch", "\U0001f371", [lunchc[0]])

    # builders: leftover non-chalk singles
    spent = set(anchors) | used | {t['anchor'] for t in tickets}
    for n in byT([x for x in nonchalk if x not in spent]):       # use the whole 33
        add(name_for("builder"), "builder", "\U0001f4b0", [n])

    # price every ticket (same correlation rule the board uses)
    for i, t in enumerate(tickets, 1):
        t['n'] = i
        pr = [l for l in t['players'] if l['odds']]
        t['priced'] = t['confleg'] = len(pr)
        t['sum']  = round(sum(l['aT'] for l in t['players']), 1)
        t['msum'] = round(sum(l['total'] for l in t['players']), 1)
        if len(pr) == t['nlegs'] and pr:
            if len(pr) == 2 and pr[0]['game'] == pr[1]['game']:
                q1, q2 = 1 / a2d(pr[0]['odds']), 1 / a2d(pr[1]['odds'])
                rho = 0.12 if pr[0]['team'] == pr[1]['team'] else 0.06
                d = 1 / (q1 * q2 + rho * (q1 * (1 - q1) * q2 * (1 - q2)) ** 0.5)
            else:
                d = 1
                for l in pr:
                    d *= a2d(l['odds'])
            t['parlay_am'], t['payout10'] = d2a(d), round(10 * d, 2)
        else:
            t['parlay_am'] = t['payout10'] = None

    D['tickets'] = tickets
    D.setdefault('meta', {})['tickets'] = len(tickets)
    return tickets


# ---------- update (3): suspended-game carryover (per-bat, auto-lifting) ----------
def carryover(D_today, D_prev):
    """Carry only the bats we actually had on a suspended prior board, as SINGLES-ONLY 'pending'.

    Call once, before assemble(D_today). For each prior game left 'susp', take only the
    bats that were on our prior tickets (e.g. the 3 we bet, not the whole roster) and tag
    them pending={gmatch,date} on today's field. We do NOT suspend today's fresh game, so
    everyone else in tonight's matchup stays fully parlay-eligible. The client lifts the
    pending tag automatically once that resumed game posts final in the live feed.
    """
    prev_gs   = D_prev.get('meta', {}).get('gs', {})
    susp_games = {g for g, st in prev_gs.items() if st == 'susp'}
    if not susp_games:
        return D_today
    prev_P    = D_prev.get('players', {})
    prev_date = D_prev.get('meta', {}).get('date')
    bet = {l.get('name') for t in D_prev.get('tickets', []) for l in t.get('players', [])}
    for n in bet:
        p = prev_P.get(n)
        if not p or str(p.get('game')) not in susp_games:
            continue
        info = {'gmatch': p.get('gmatch'), 'date': prev_date}   # the resuming game to watch
        if n in D_today.get('players', {}):
            D_today['players'][n]['pending'] = info             # already in tonight's field -> just tag
        else:
            carried = dict(p); carried['pending'] = info         # not playing tonight -> carry the leg so it grades
            D_today.setdefault('players', {})[n] = carried
    return D_today


if __name__ == "__main__":
    import json
    s = open('/mnt/user-data/outputs/index.html').read()
    D = json.loads(re.search(r'const D=(\{.*?\}),WX=D\.meta\.wx;', s, re.S).group(1))
    ts = assemble(D)
    print(f"{len(ts)} tickets built\n")
    for t in ts:
        legs = " + ".join(f"{l['name']}(+{l['odds']})" for l in t['players'])
        pay  = f"  $10->${t['payout10']}" if t['payout10'] else ""
        print(f"  [{t['kind']:8}] {legs}{pay}")
