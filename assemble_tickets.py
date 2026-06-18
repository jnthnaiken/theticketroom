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
CHALK_N       = 8                # the ban8: 8 shortest-odds bats among the featured pool (nightcap/lunch ONLY)
GATE_N        = 33               # buildable pool = 33; we take top (33+8) by TOTAL so the ban8 leaves 33
FLOOR         = 75               # TOTAL floor for OUR picks (moon anchors/partners + salami legs).
                                 # Sub-floor bats stay in the pool as builder singles for visitors.
MOON_PLAN     = (0, 0, 1, 1, 2)  # anchor indices per moon -> A1,A1,A2,A2,A3 (2/2/1)
WIN           = 165              # max minutes between a parlay's earliest & latest leg (lineup-timing cap; mirrors client)

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
        "Zero Gravity", "Trajectory Locked", "Sonic Boom", "The Long Bomb", "Rocket Fuel", "Thrust Vector", "Crossing the Karman Line", "No Doubter",
        "Tape Measure Job", "Onto the Concourse", "Splash Hit", "The Way Back Machine",
        "Goodbye Baseball", "Touch 'Em All", "Climbing the Ladder", "Ballistic Arc",
        "Orbital Insertion", "Star Sailor", "Going Supersonic", "The Slingshot",
        "Heat Shield Off", "Beyond the Bleachers", "Into the Upper Air", "The Apollo",
        "Terminal Climb", "Past Low Earth Orbit",
    ],
    "biggest": [  # the feast / the spread
        "The Charcuterie Board", "The Full Spread", "The Whole Tray", "Meat Sweats",
        "Family Style", "The Tasting Menu", "Surf and Turf",
        "All You Can Eat", "The Combo Platter", "Second Helpings",
        "The Smorgasbord", "The Whole Hog", "The Deli Case", "Loaded Plate", "The Feast",
        "The Cold Cuts", "Heaping Plate", "The Potluck", "The Tailgate Spread",
        "The Whole Enchilada", "The Big Platter", "Seconds and Thirds",
    ],
    "late": [  # closing time / after dark
        "Last Call", "Closing Time", "After Hours", "One for the Road",
        "Lights Out", "Final Pour", "The Closer", "Last Ring of the Bell", "Midnight Special",
        "Last Train Home", "The Curfew", "Burning the Midnight Oil", "Bar's Last Round", "Nightfall", "The Witching Hour", "Last Orders", "The Final Bell",
        "Under the Lights",
    ],
    "lunch": [  # midday  (no 'Lunch'/'Special' — those are the section-header words)
        "Midday Meal", "High Noon", "The Blue Plate", "The Noon Whistle", "The Midday Mash",
        "Half-Day Hammer", "The Matinee", "The Early Bird", "Midday Money", "First-Pitch Feast",
    ],
    "builder": [  # bankroll / getting paid
        "Cash Is King", "Paid in Full", "Bag Secured", "The Sure Thing", "Easy Money",
        "Stack It High", "Mailbox Money", "Bread Winner", "Walk-Off Wallet", "Petty Cash",
        "Pay the Rent", "Cha-Ching", "The Day Job", "Clock In, Cash Out",
        "Grocery Money", "The Side Hustle", "Beer Money", "Coffee's on Me", "The Tip Jar",
        "Found Money", "Gas Money", "The Down Payment", "Spare Change", "The Nest Egg", "Payday", "House Money",
        "Keep the Change", "Cover Charge", "The Cushion", "Quick Buck", "In the Black",
        "The Float", "Walking-Around Money", "The Cookie Jar", "Pocket Money", "The Allowance",
        "Cashing Out", "The Slow Grind", "Steady Drip", "Singles Add Up", "Chip Stack",
        "The Vig Killer", "Direct Deposit", "Rainy Day Fund", "The ATM",
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

    # POOL: take the model's top (33 + 8) by TOTAL, then re-sort by odds. The 8 shortest-odds bats are
    # the chalk -> lunch/nightcap ONLY (never builders). The remaining 33 are the parlay/builder pool.
    # Taking 41 up front IS the backfill: pulling the 8 chalk never shrinks the buildable 33 (same idea
    # as replacing a scratched bat with the next one).
    cand     = byT(elig)[:GATE_N + CHALK_N]
    ranked   = byO(cand)
    chalk    = set(ranked[:CHALK_N])
    nonchalk = ranked[CHALK_N:]
    extra    = byT(elig)[GATE_N + CHALK_N:]
    D['pool'] = list(nonchalk)   # Players tab = exactly this 33 (lunch/nightcap chalk are NOT in it)

    cand_t      = [(gmin(P[n]['gtime']) or 0) for n in cand]
    latest      = max(cand_t) if cand_t else 0
    lunch_games = {P[n]['game'] for n in cand if (gmin(P[n]['gtime']) or 0) < LUNCH_CUT_MIN}
    night_games = {P[n]['game'] for n in cand if (gmin(P[n]['gtime']) or 0) == latest}

    # anchors: best nonchalk by TOTAL, one per game, never pending/below-floor
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


    def add(name, kind, badge, names, rr=None):
        legs = [leg(n) for n in names]
        t = {"name": name, "kind": kind, "badge": badge, "note": "",
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
    def _opp(p):
        o = p.get('opp'); return (o[0] if (o and o[0]) else 'the arm')
    def _phrases(p):
        opp = _opp(p); hr9 = p.get('hr9'); hh = p.get('hh') or 0; la = p.get('la') or 0
        wf = 1.0 if p.get('wf') is None else p.get('wf'); iso = _isostr(p); iv = _isoval(p)
        H = _jsround(hh); L = _jsround(la)
        o = []
        if hr9 is not None and hr9 >= 1.6:
            o.append((9, 'mtx', [f"draws {opp}, one of the most homer-prone arms on the slate ({hr9:.2f}/9)", f"gets to feast on {opp} \u2014 batting-practice stuff at {hr9:.2f} HR/9", f"faces {opp}, who's been serving up souvenirs all year ({hr9:.2f}/9)", f"catches {opp} on a night the ball flies ({hr9:.2f} HR/9)", f"squares off with {opp}, a meatball machine at {hr9:.2f}/9", f"draws {opp} and his {hr9:.2f} HR/9 mistakes", f"gets {opp}, who can't keep it in the yard ({hr9:.2f} HR/9)"]))
        elif hr9 is not None and hr9 >= 1.35:
            o.append((6, 'mtx', [f"draws a beatable {opp} ({hr9:.2f} HR/9)", f"gets {opp}, who leaves a few up in the zone ({hr9:.2f}/9)", f"has a hittable {opp} on the mound ({hr9:.2f} HR/9)", f"faces a homer-prone {opp} ({hr9:.2f}/9)", f"draws {opp}, good for a mistake or two ({hr9:.2f} HR/9)"]))
        elif hr9 is not None and hr9 < 1.0:
            o.append((1, 'mtx', [f"has to solve a stingy {opp} ({hr9:.2f}/9)", f"runs into a tough {opp} ({hr9:.2f}/9)", f"faces {opp}, who limits the long ball ({hr9:.2f}/9)"]))
        if wf >= 1.05:   o.append((8, 'park', ["has the wind howling out behind him", "gets a yard playing like a launchpad tonight", "has the jet stream pushing toward the seats", "swings with the wind at his back", "gets a park that's launching everything tonight", "has gusts carrying balls over the wall", "plays in a wind tunnel pointed at the seats"]))
        elif wf >= 1.02: o.append((4, 'park', ["catches a small park boost", "has the yard tilting his way", "gets a sliver of help from the park", "plays in a slightly friendly yard", "gets a touch of carry tonight"]))
        elif wf <= 0.95: o.append((1.5, 'park', ["fights a ball-killing yard", "battles heavy, homer-suppressing air", "plays in a park that swallows fly balls"]))
        if hh >= 52:   o.append((7, 'hh', [f"is scorching the ball ({H}% hard-hit)", f"is barreling everything in sight ({H}% hard-hit)", f"is denting outfield walls ({H}% hard-hit)", f"is hitting absolute lasers ({H}% hard-hit)", f"is squaring up everything ({H}% hard-hit)", f"is crushing the baseball ({H}% hard-hit)", f"is leaving scorch marks ({H}% hard-hit)", f"is teeing off ({H}% hard-hit)", f"is rocketing line drives ({H}% hard-hit)", f"is punishing the baseball ({H}% hard-hit)", f"is making elite contact ({H}% hard-hit)", f"is stinging it on a rope ({H}% hard-hit)", f"is tattooing the baseball ({H}% hard-hit)", f"is hammering the ball ({H}% hard-hit)", f"is lighting up the radar gun ({H}% hard-hit)", f"is blistering line drives ({H}% hard-hit)", f"is putting a charge into everything ({H}% hard-hit)", f"is crushing it to all fields ({H}% hard-hit)", f"is squaring up rockets ({H}% hard-hit)", f"is impacting the ball at an elite clip ({H}% hard-hit)", f"is mashing the ball ({H}% hard-hit)", f"is hitting frozen ropes ({H}% hard-hit)", f"is generating elite exit velo ({H}% hard-hit)", f"is hitting bullets ({H}% hard-hit)", f"is making thunderous contact ({H}% hard-hit)", f"is squaring up premium contact ({H}% hard-hit)", f"is barreling balls at will ({H}% hard-hit)", f"is hitting it on the screws ({H}% hard-hit)", f"is crushing contact at an elite rate ({H}% hard-hit)", f"is launching rockets ({H}% hard-hit)", f"is consistently barreling up ({H}% hard-hit)", f"is striking it clean and hard ({H}% hard-hit)"]))
        elif hh >= 46: o.append((3.5, 'hh', [f"is squaring it up ({H}% hard-hit)", f"is making loud contact ({H}% hard-hit)", f"is stinging the ball ({H}% hard-hit)", f"is finding the barrel ({H}% hard-hit)", f"is driving the ball ({H}% hard-hit)", f"is putting good wood on it ({H}% hard-hit)", f"is centering the ball ({H}% hard-hit)", f"is connecting solidly ({H}% hard-hit)", f"is hitting it hard enough ({H}% hard-hit)", f"is barreling a fair share ({H}% hard-hit)", f"is making consistent contact ({H}% hard-hit)", f"is catching it flush ({H}% hard-hit)", f"is hitting line drives ({H}% hard-hit)", f"is squaring up a good chunk ({H}% hard-hit)", f"is driving it with authority ({H}% hard-hit)", f"is putting a charge into it ({H}% hard-hit)", f"is making solid contact ({H}% hard-hit)", f"is making quality contact ({H}% hard-hit)", f"is driving balls into the gaps ({H}% hard-hit)", f"is barreling up enough ({H}% hard-hit)", f"is putting the bat on it well ({H}% hard-hit)", f"is squaring up its share ({H}% hard-hit)"]))
        if 16 <= la <= 23: o.append((5, 'la', [f"lives in the launch window ({L}\u00b0)", f"has the swing plane dialed for liftoff ({L}\u00b0)", f"is lifting everything ({L}\u00b0)", f"puts the ball in the air on a homer plane ({L}\u00b0)", f"sits in the ideal launch angle ({L}\u00b0)", f"gets under it just right ({L}\u00b0)", f"swings on a clean uppercut ({L}\u00b0)", f"elevates with ease ({L}\u00b0)", f"has a swing built for the seats ({L}\u00b0)", f"stays in the sweet-spot angle ({L}\u00b0)", f"sends it skyward ({L}\u00b0)", f"has loft to spare ({L}\u00b0)", f"hits it on the perfect plane ({L}\u00b0)", f"launches it at the right angle ({L}\u00b0)", f"keeps the ball in the air ({L}\u00b0)", f"swings with natural lift ({L}\u00b0)", f"finds the home-run trajectory ({L}\u00b0)", f"gets ideal loft ({L}\u00b0)", f"drives the ball into the air ({L}\u00b0)", f"tilts the bat for distance ({L}\u00b0)", f"swings with home-run loft ({L}\u00b0)", f"stays in the launch zone ({L}\u00b0)", f"puts air under the ball ({L}\u00b0)", f"has textbook lift ({L}\u00b0)"]))
        if iso and iv >= 0.24:   o.append((6.5, 'iso', [f"packs {iso} of isolated thump", f"carries tape-measure power ({iso} ISO)", f"brings elite raw pop ({iso} ISO)", f"has light-tower power ({iso} ISO)", f"swings a {iso}-ISO sledgehammer", f"brings prodigious pop ({iso} ISO)", f"carries game-changing power ({iso} ISO)", f"has rare thump ({iso} ISO)", f"brings middle-of-the-order slug ({iso} ISO)", f"hits for serious power ({iso} ISO)", f"brings 30-homer pop ({iso} ISO)", f"carries elite slug ({iso} ISO)", f"has monster raw power ({iso} ISO)", f"brings the loudest pop on the ticket ({iso} ISO)", f"swings a thunderstick ({iso} ISO)", f"brings cleanup-spot power ({iso} ISO)", f"carries premium thump ({iso} ISO)", f"has elite extra-base juice ({iso} ISO)"]))
        elif iso and iv >= 0.20: o.append((4.5, 'iso', [f"brings {iso} ISO juice", f"has legit pop behind it ({iso} ISO)", f"carries {iso} of real ISO", f"packs above-average pop ({iso} ISO)", f"has honest thump ({iso} ISO)", f"swings with pop ({iso} ISO)", f"brings useful power ({iso} ISO)", f"carries solid slug ({iso} ISO)", f"has real extra-base pop ({iso} ISO)", f"brings dependable power ({iso} ISO)"]))
        if not o: o.append((0.5, 'x', [f"takes on {opp}", f"steps in against {opp}", f"gets his cuts at {opp}"]))
        o.sort(key=lambda r: r[0], reverse=True)
        return o
    # Global phrase de-dup across the WHOLE board: _choose picks the least-used variant in a bank
    # (tie -> the one nearest the note's seed), so a phrase never repeats until its bank is exhausted.
    # Notes are generated in one final pass below (in ticket order) so _gseen accumulates deterministically;
    # the client mirrors this exactly.
    _gseen = {}
    def _choose(dim, phs, seed):
        n = len(phs); best, bk = 0, None
        for i in range(n):
            key = (_gseen.get(dim + '#' + str(i), 0), (i - seed) % n)
            if bk is None or key < bk:
                bk = key; best = i
        _gseen[dim + '#' + str(best)] = _gseen.get(dim + '#' + str(best), 0) + 1
        return phs[best]
    def _edges(p, n, seed):
        out, seen = [], set()
        for w, dim, phs in _phrases(p):
            if dim in seen: continue
            seen.add(dim); out.append(_choose(dim, phs, seed))
            if len(out) >= n: break
        return out
    def _pick(p, used, seed):
        r = _phrases(p); ch = None
        for row in r:
            if row[1] not in used: ch = row; break
        if ch is None: ch = r[0]
        dim, phs = ch[1], ch[2]; used[dim] = used.get(dim, 0) + 1
        return _choose(dim, phs, seed)
    def _join(parts):
        if len(parts) <= 1: return parts[0] if parts else ""
        if len(parts) == 2: return parts[0] + " and " + parts[1]
        return ", ".join(parts[:-1]) + ", and " + parts[-1]
    def cwnote(kind, names):
        # Substance only: why each bat can leave the yard. A char-code seed varies each note's starting
        # phrase; _choose then guarantees board-wide variety. No structural preamble, no filler.
        seed = sum(sum(ord(c) for c in _lastnm(P[n].get('nm', n))) for n in names)
        if len(names) == 1:
            a = P[names[0]]
            return a.get('nm', names[0]) + " " + _join(_edges(a, 2, seed)) + "."
        used = {}
        parts = [_lastnm(P[n].get('nm', n)) + " " + _pick(P[n], used, seed) for n in names]
        return _join(parts) + "."

    # ---- SNAKE DRAFT of parlay partners, by TOTAL (update 3) ----
    # A0>A1>A2>A3 are the anchors by TOTAL: A0 & A1 each carry two moons, A2 one moon, A3 the salami.
    # Partners are drafted from the remaining nonchalk (then #42+ only if forced) HIGHEST TOTAL FIRST, in
    # a snake whose WEAKEST anchor picks first -> salami, A2, A1, A0 / A0, A1, A2, A3 / salami, A2, ...
    # So the strongest leftover bats always land in a parlay: no builder single can outscore a parlay leg.
    # The reverse-snake start also tilts help toward the shakier anchors. Each pick takes the best TOTAL
    # that keeps the ticket inside one distinct-game lineup window (span <= WIN).
    parlays = []
    for ai in MOON_PLAN:
        if ai < len(anchors):
            parlays.append({'rank': ai, 'kind': 'moon', 'badge': "\U0001f680",
                            'rr': {"struct": "by 2s & 3", "risk": 4.0},
                            'legs': [anchors[ai]], 'need': 2, 'games': {P[anchors[ai]]['game']}})
    if len(anchors) >= 4:
        parlays.append({'rank': 3, 'kind': 'biggest', 'badge': "\U0001f96a",
                        'rr': {"struct": "by 2s, 3s & 4", "risk": 11.0},
                        'legs': [anchors[3]], 'need': 3, 'games': {P[anchors[3]]['game']}})

    by_rank = {}
    for t in parlays:
        by_rank.setdefault(t['rank'], []).append(t)

    pool_av = [n for n in byT(nonchalk) if n not in anchors and n not in used
               and P[n]['TOTAL'] >= FLOOR and not pend(n)]
    pool_av += [n for n in byT(extra) if n not in anchors and n not in used
                and P[n]['TOTAL'] >= FLOOR and not pend(n)]

    def fits(t, n):
        if P[n]['game'] in t['games']:
            return False
        ts = [tmin(x) for x in t['legs']] + [tmin(n)]
        return (max(ts) - min(ts)) <= WIN

    def needy(t):
        return (len(t['legs']) - 1) < t['need']

    ranks_fwd = sorted(by_rank.keys(), reverse=True)        # weakest (3) -> strongest (0)
    rnd = 0
    while any(needy(t) for t in parlays):
        order = ranks_fwd if (rnd % 2 == 0) else list(reversed(ranks_fwd))
        progressed = False
        for r in order:
            cands = [t for t in by_rank[r] if needy(t)]
            if not cands:
                continue
            t = min(cands, key=lambda x: len(x['legs']))    # spread an anchor's picks across its moons
            pick = next((n for n in pool_av if fits(t, n)), None)
            if pick is None:
                continue
            t['legs'].append(pick); t['games'].add(P[pick]['game'])
            used.add(pick); pool_av.remove(pick); progressed = True
        rnd += 1
        if not progressed:
            break

    for t in parlays:                                       # emit moons first (display order)
        if t['kind'] == 'moon':
            add(name_for("moon"), "moon", t['badge'], t['legs'], rr=t['rr'])
    for t in parlays:                                       # then the salami
        if t['kind'] == 'biggest':
            add(name_for("biggest"), "biggest", t['badge'], t['legs'], rr=t['rr'])

    # lunch special + nightcap come from the 8-ban chalk (the favorites), always
    ncap = byO([n for n in chalk if P[n]['game'] in night_games])
    if ncap:
        add(name_for("late"), "late", "\U0001f303", [ncap[0]])
    lunchc = byO([n for n in chalk if P[n]['game'] in lunch_games])
    if lunchc:
        add(name_for("lunch"), "lunch", "\U0001f371", [lunchc[0]])

    # builders: every remaining NONCHALK bat as a single. Chalk is never a builder; the 33 buildable
    # bats land on tickets, and the chalk sit in lunch/nightcap (or nowhere, if their window is empty).
    spent = set(anchors) | used | {t['anchor'] for t in tickets}
    for n in byT([x for x in nonchalk if x not in spent and P[x]['TOTAL'] >= FLOOR]):
        add(name_for("builder"), "builder", "\U0001f4b0", [n])

    # price every ticket (same correlation rule the board uses)
    wx = D.get('meta', {}).get('wx', {})
    def _rrmax(legs, risk):                              # round-robin max profit, mirrors client rrmax()
        dec = [a2d(l['odds']) for l in legs]; L = len(dec); s = -risk
        for a in range(L):
            for b in range(a + 1, L):
                s += dec[a] * dec[b]
        for a in range(L):
            for b in range(a + 1, L):
                for c in range(b + 1, L):
                    s += dec[a] * dec[b] * dec[c]
        if L >= 4:
            for a in range(L):
                for b in range(a + 1, L):
                    for c in range(b + 1, L):
                        for e in range(c + 1, L):
                            s += dec[a] * dec[b] * dec[c] * dec[e]
        return _jsround(s * 10) / 10
    for i, t in enumerate(tickets, 1):
        t['n'] = i
        pr = [l for l in t['players'] if l['odds']]
        t['priced']  = len(pr)
        t['confleg'] = sum(1 for l in t['players'] if l.get('status') == 'confirmed')   # confirmed legs (matches client)
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
        # ---- mirror the client post-process so the baked board renders without a redraft ----
        ws = {'boost': 0, 'supp': 0, 'dome': 0, 'neu': 0}
        for l in t['players']:
            w = wx.get(str(l['game'])) or {}
            if   w.get('cond') == 'Dome':     ws['dome']  += 1
            elif w.get('lean') == 'Boost':    ws['boost'] += 1
            elif w.get('lean') == 'Suppress': ws['supp']  += 1
            else:                             ws['neu']   += 1
        t['wxsum'] = ws
        if t['rr']:
            t['rr']['maxprofit'] = _rrmax(pr, t['rr']['risk'])
            t['rr']['bytwos'] = False

    # final note pass: generate all notes in ticket order so the board-wide phrase de-dup is deterministic
    _gseen.clear()
    for t in tickets:
        t['note'] = cwnote(t['kind'], [l['name'] for l in t['players']])

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
    bet_ticket = {}
    for t in D_prev.get('tickets', []):
        for l in t.get('players', []):
            bet_ticket.setdefault(l.get('name'), t.get('name'))
    carry_meta = []
    for n in set(bet_ticket):
        p = prev_P.get(n)
        if not p or str(p.get('game')) not in susp_games:
            continue
        info = {'gmatch': p.get('gmatch'), 'date': prev_date}   # the resuming game to watch
        carry_meta.append({'name': n, 'ticket': bet_ticket.get(n), 'gmatch': p.get('gmatch')})
        if n in D_today.get('players', {}):
            D_today['players'][n]['pending'] = info             # already in tonight's field -> just tag
        else:
            carried = dict(p); carried['pending'] = info         # not playing tonight -> carry the leg so it grades
            D_today.setdefault('players', {})[n] = carried
    if carry_meta:                                               # subtle settled-carryover strip data
        D_today.setdefault('meta', {})['carryover'] = {'date': prev_date,
            'gmatch': carry_meta[0]['gmatch'], 'bats': carry_meta}
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
