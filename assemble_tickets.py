"""
The Ticket Room — ticket assembler (hardcoded rules + the latest updates).

Drop this into the build step AFTER the field is scored (it consumes the same
`D` the board renders: D['players'][name] = {odds, TOTAL, game, gmatch, gtime,
late, status, void, out, ...}). Call assemble(D) and it returns D['tickets'].

RULES (match the code below):
================================
  * Eligible field = priced bats in the lineup, not voided/scratched.
  * Pool gate      = z-THRESHOLD on the blended model score (Z_GATE SDs above the slate mean) --
                     scale/slate-independent, no fixed size.
  * Anchors        = strongest by model; MULTIPLE anchors per game allowed (two bats from one
                     game can each lead their own tickets).
  * Per-ticket     = one bat per distinct game; GAME_CAP (=3) bats per game overall.
  * Chalk          = the CHALK_N shortest-odds bats -> lunch + nightcap ONLY; moons/salami/builders chalk-free.
  * Moons          = ~2 per non-salami anchor; anchor + 2 longshots, snake-drafted, legs inside a WIN(=120)-min window.
  * Salami         = led by the BEST fittable anchor; 4 longest shots in distinct games, full round robin.
  * Builders       = leftover / sub-gate bats as single-leg bankroll plays.
  * Nightcap       = the late single. Lunch cut = LUNCH_CUT_MIN (4:00 PM ET).
  * Ticket names   = rotated by day-of-year, no repeats.
"""
import re, datetime

LUNCH_CUT_MIN = 16 * 60          # 4:00 PM ET splits the lunch window from night
NIGHT_WIN     = 60              # nightcap window = games starting within 60 min of the last first pitch (chalk only)
CHALK_N       = 4                # ban-4: only the 4 shortest-odds bats are chalk (nightcap/lunch ONLY); #5-8 favorites now buildable
GATE_N        = 33               # DEPRECATED (no longer gates the pool); FLOOR is the pool gate now
FLOOR         = 130               # the pool gate: a bat must clear this model TOTAL to make the board at all
Z_GATE        = 0.75             # pool gate: keep bats whose blended z-score is >= this many SDs above the slate mean (scale/slate-independent; replaces the fixed top-40). Lowered 1.0->0.75 to deepen the pool (more legs -> more moons on fragmented slates).
                                 # Sub-floor bats stay in the pool as builder singles for visitors.
MOONS_PER_ANC = 2                # moons carried by each non-salami anchor; the salami anchor is chosen by fittable-pool strength
WIN           = 120              # max minutes between a parlay's earliest & latest leg; below the 155 warning line so we never ship a flagged (afternoon->night) parlay

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
    # pending / carryover = a bat carried from a still-resuming suspended game (or named in the carryover
    # strip). It stays in the pool and CAN be a single (builder), but is barred from every parlay leg --
    # anchor, moon partner, or salami -- until its suspended game finalizes and the tag lifts.
    # Set per-bat by carryover() on only the bats we actually had on the suspended board (never a whole game).
    _co = D.get('meta', {}).get('carryover') or {}
    carry_names = {b.get('name') for b in _co.get('bats', []) if b.get('name')}   # carryover trio -> singles only
    _wx = D.get('meta', {}).get('wx', {})
    _precip = lambda n: ((_wx.get(str(P[n]['game']), {}) or {}).get('precip', 0)) or 0   # rain%% at first pitch
    pend = lambda n: bool(P[n].get('pending')) or n in carry_names or (50 <= _precip(n) < 70)   # 50-69%% rain -> singles(builder) only, never a parlay leg
    elig = [n for n, p in P.items()
            if p.get('odds') and not p.get('out') and not p.get('void') and _precip(n) < 70]   # >=70%% rain -> game out of the pool entirely
    byT  = lambda names: sorted(names, key=lambda n: (P[n]['TOTAL'], P[n]['aT']), reverse=True)   # TOTAL desc; ties broken by aT (base) so the hard 33-cut is deterministic
    byO  = lambda names: sorted(names, key=lambda n: P[n]['odds'])      # shortest first
    tmin = lambda n: gmin(P[n]['gtime']) or 0

    # POOL (one draft, top-3-per-GAME): the pool is EVERY eligible bat whose model TOTAL clears FLOOR.
    # Re-sort that pool by odds and pull the CHALK_N shortest (chalk -> lunch/nightcap ONLY); from the rest
    # keep at most TOP-3 per GAME (best-by-model, both teams combined). No fixed size and no backfill -- the floor is the only
    # gate, so moons, salami and builders all draft from this single pool and a thin slate yields fewer bats.
    GAME_CAP = 3   # at most 3 bats per GAME (both lineups combined); per-team would allow 6/game (3 each side) -> implies 6 different HRs in one game, unrealistic
    fullrank = byT(elig)                              # everyone ranked by model -> replacement order
    _bl = [P[n]['blend'] for n in fullrank if P[n].get('blend') is not None]
    if len(_bl) >= 8:                                  # z-THRESHOLD gate (scale/slate-independent): keep bats whose blended z clears Z_GATE SDs above the slate mean
        _bm = sum(_bl)/len(_bl); _bsd = (sum((x-_bm)**2 for x in _bl)/len(_bl))**0.5 or 1e-9
        cand = [n for n in fullrank if P[n].get('blend') is not None and (P[n]['blend']-_bm)/_bsd >= Z_GATE]
    else:                                              # fallback (board scored by old model, no 'blend'): strongest ~40 by TOTAL
        _ft = sorted([P[n]['TOTAL'] for n in fullrank if P[n].get('TOTAL') is not None], reverse=True)
        _floor = _ft[min(len(_ft)-1, 39)] if _ft else FLOOR
        cand = [n for n in fullrank if P[n]['TOTAL'] >= _floor]
    ranked   = byO(cand)                              # re-sort those 41 by odds
    chalk    = set()                                 # chalk ban removed -- the top-4 favorites now draft into moons/salami/builders like every other bat
    nonchalk, _tc = [], {}
    for n in byT([x for x in cand if x not in chalk]):   # the pool, model order, trimmed to <=3 per GAME (both teams combined)
        g = P[n]['game']
        if _tc.get(g, 0) >= GAME_CAP: continue
        nonchalk.append(n); _tc[g] = _tc.get(g, 0) + 1
    _have = set(nonchalk)
    extra = []                                           # FLOOR is the only gate -> no fixed pool size, no backfill, no sub-floor tier
    D['pool'] = list(nonchalk)   # Players tab = exactly this 33 (lunch/nightcap chalk are NOT in it)
    D.setdefault('meta', {})['pool'] = len(P)   # counters denominator = the whole scored field (all bats, e.g. 243 live); Players/Tickets still use the gated 33 in D['pool']

    # STRENGTH = normalized TOTAL, nothing else. TOTAL already carries the market -- the ~50% odds /
    # 50% edge blend is baked into TOTAL (via mktT) -- so ranking by TOTAL alone avoids double-counting the
    # odds. This one key decides every role board-wide: anchors, salami, moon legs, and builder order.
    _Ts   = [P[n]['TOTAL'] for n in nonchalk] or [0]
    _tmn, _tmx = min(_Ts), max(_Ts)
    def strength(n):
        return (P[n]['TOTAL'] - _tmn) / (_tmx - _tmn) if _tmx > _tmn else 0.5   # TOTAL alone
    byS = lambda names: sorted(names, key=strength, reverse=True)   # board-wide role/order key

    cand_t      = [(gmin(P[n]['gtime']) or 0) for n in cand]
    latest      = max(cand_t) if cand_t else 0
    lunch_games = {P[n]['game'] for n in cand if (gmin(P[n]['gtime']) or 0) < LUNCH_CUT_MIN}
    night_games = {P[n]['game'] for n in cand if (gmin(P[n]['gtime']) or 0) >= latest - NIGHT_WIN}

    # anchor CANDIDATES: strongest nonchalk by STRENGTH, one per game, never pending/below-floor.
    # The final 4 anchors are chosen from these for the best fittable schedule (see the draft below), so
    # every moon fills three legs -- we never ship a 2-leg moon.
    cand_anchors, seen = [], set()
    for n in byS(nonchalk):
        g = P[n]['game']
        if g in seen or pend(n) or _precip(n) >= 40:   # one anchor per game; 40%+ rain never anchors
            continue
        cand_anchors.append(n); seen.add(g)

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
        wf = 1.0 if p.get('wf') is None else p.get('wf')
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
        ft = p.get('ftrend')
        if ft == 'up':
            o.append((3, 'form_up', ["the bat's heating up", "the swing's trending up", "he's locked in at the plate lately", "riding a hot stretch", "the timing has come around", "recent form points up", "he's squaring more up lately", "on a clear upswing", "the bat speed looks back", "the momentum's with him"]))
        elif ft == 'down':
            o.append((2, 'form_down', ["due for a get-right night", "positive regression overdue", "a bounce-back feels close", "ready to break a quiet stretch", "the underlying contact still grades out", "due to run into one", "the process ahead of the results lately", "a slump-buster could be near"]))
        else:
            o.append((2, 'form_flat', ["steady form behind it", "holding his level", "in a steady groove", "the bat ticking along", "keeping an even keel", "on stable footing lately", "no real cold streak to speak of", "running at his usual clip"]))
        pw = p.get('powidx')
        if pw is not None:
            if pw >= 90:   o.append((3.2, 'pow', [f"packs elite raw power, a {pw}/100 grade", f"swings one of the biggest sticks on the board ({pw}/100 power)", f"carries top-shelf pop ({pw}/100 power grade)", f"brings light-tower raw power ({pw}/100)", f"grades near the top of the slate for power ({pw}/100)", f"has the raw juice to clear any wall ({pw}/100 power)", f"sits in the elite power tier ({pw}/100)"]))
            elif pw >= 70: o.append((3.2, 'pow', [f"brings well-above-average pop ({pw}/100 power)", f"carries serious thump ({pw}/100 grade)", f"swings a heavy stick ({pw}/100 power)", f"has plenty of raw power ({pw}/100)", f"grades out strong for power ({pw}/100)", f"packs a big-league power grade ({pw}/100)", f"has the pop to go deep ({pw}/100 power)"]))
            elif pw >= 50: o.append((3.2, 'pow', [f"carries a solid power grade ({pw}/100)", f"has enough pop to clear it ({pw}/100 power)", f"brings average-plus thump ({pw}/100)", f"packs respectable power ({pw}/100 grade)", f"has real over-the-fence pop ({pw}/100)", f"swings with usable power ({pw}/100)"]))
            elif pw >= 30: o.append((3.2, 'pow', [f"gets there more on timing than thump ({pw}/100 power)", f"leans on contact with sneaky pop ({pw}/100)", f"needs to square one up to leave ({pw}/100 power)", f"plays a touch under the power tier ({pw}/100)", f"brings fringe-average pop ({pw}/100)"]))
            else:          o.append((3.2, 'pow', [f"is a contact-first bat hunting one good swing ({pw}/100 power)", f"wins with bat-to-ball over raw pop ({pw}/100)", f"needs everything to click for one to leave ({pw}/100 power)", f"is more table-setter than slugger ({pw}/100)", f"banks on a mistake pitch to clear it ({pw}/100 power)"]))
        T = p.get('TOTAL')
        if T is not None:
            Ti = _jsround(T)
            o.append((2.6, 'model', [f"the model still lands him at {Ti}", f"our number on him is {Ti} tonight", f"the projection backs him at {Ti}", f"grades to {Ti} on our board", f"the model bumps him to {Ti}", f"lands at {Ti} in our model", f"the model has him at {Ti} for the night", f"our projection sits at {Ti}"]))
        od = p.get('odds')
        if od:
            o.append((1.4, 'price', [f"at a fair +{od}", f"priced at +{od}", f"you're getting +{od} on it", f"the +{od} tag plays", f"+{od} is a number worth taking", f"+{od} carries value", f"a tidy +{od} price"]))
        o.append((1.2, 'spot', [f"facing {opp}", f"drawing {opp}", f"matched up with {opp}", f"up against {opp}", f"taking on {opp}", f"staring down {opp}", f"in against {opp}", f"set against {opp}", f"opposite {opp}", f"with {opp} on the bump", f"across from {opp}", f"tested by {opp}"]))
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
    def _edges_fill(p, seed, target=120, lo=3, hi=5):   # add clauses until the note actually fills ~2 lines
        out, seen = [], set()
        for w, dim, phs in _phrases(p):
            if dim in seen: continue
            seen.add(dim); out.append(_choose(dim, phs, seed))
            if len(out) >= hi: break
            if len(out) >= lo and len(_join(out)) >= target: break
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
    def _shortc(p, used, seed):
        SK={'price','spot','x','form_up','form_down','form_flat'}
        rows=[r for r in _phrases(p) if r[1] not in SK] or _phrases(p)
        if not rows: return 'takes his cuts'
        avail=[r for r in rows if r[1] not in used] or rows
        best=min(avail, key=lambda r: min(len(v) for v in r[2]))
        used[best[1]]=1
        return min(best[2], key=len)
    def _clmp(s, B=116):
        if not s or len(s)<=B: return s
        t=s[:B]; i=max(t.rfind(", "), t.rfind(" and "))
        if i<50: i=t.rfind(" ")
        return s[:i].rstrip(" ,").rstrip(".")+"."
    def _edgesU(p, k, used, seed):
        out = []
        for w, dim, phs in _phrases(p):
            if dim in used: continue
            used[dim] = used.get(dim, 0) + 1
            out.append(_choose(dim, phs, seed))
            if len(out) >= k: break
        if not out:
            r = _phrases(p); out = [_choose(r[0][1], r[0][2], seed)]
        return out
    def cwnote(kind, names):
        # Substance only: why each bat can leave the yard. Full-width cards (salami/nightcap/lunch) carry
        # richer two-line notes since they have the room; grid cards (moons/builders) fill two normal lines.
        seed = sum(sum(ord(c) for c in _lastnm(P[n].get('nm', n))) for n in names)
        WIDE = kind in ('biggest', 'late', 'lunch')
        B = 168 if WIDE else 150
        if len(names) == 1:
            a = P[names[0]]
            cl = _edges_fill(a, seed, target=(150 if WIDE else 140), lo=3, hi=(6 if WIDE else 7))
            return _clmp(a.get('nm', names[0]) + " " + _join(cl) + ".", B)
        per = 2 if WIDE else 1
        used = {}
        parts = [_lastnm(P[n].get('nm', n)) + " " + _join(_edgesU(P[n], per, used, seed)) for n in names]
        full = _join(parts) + "."
        if len(full) <= B: return full
        used = {}
        parts = [_lastnm(P[n].get('nm', n)) + " " + _shortc(P[n], used, seed) for n in names]
        full = _join(parts) + "."
        if len(full) <= B: return full
        anc = _lastnm(P[names[0]].get('nm', names[0])) + " " + _shortc(P[names[0]], {}, seed)
        rest = [_lastnm(P[n].get('nm', n)) for n in names[1:]]
        return _clmp(anc + ", with " + _join(rest) + ".", B)

    # ---- ANCHOR SELECTION + SNAKE DRAFT (restored: exhaustive best-fillable set) ----
    # Pick the 4 anchors (from cand_anchors, one per game) whose draft fills the most clean 2-per-anchor
    # moons, then ships the salami, then maximizes combined strength. TOTAL-first: strongest fillable
    # anchors lead the board; a time-isolated anchor that can't fill is simply not chosen.
    def _draft(anchor_list):
        al = sorted(anchor_list, key=lambda n: -strength(n))            # A0..A3 by STRENGTH (weakest = highest index)
        _sal_anchor = al[-1] if len(al) >= 4 else None                  # weakest = the salami anchor
        pool_av = [n for n in byS(nonchalk) if (n not in al or n == _sal_anchor) and not pend(n)]  # keep the salami anchor AS a leg candidate too (moons get first pick; the salami builds from true leftovers, and only if its anchor wasn't drafted into a moon)
        def _fitpool(a):                                                # STRENGTH of the 3 legs this anchor can fill a 4-leg salami with (span-aware)
            reach, seen, legs, times = byS([n for n in pool_av if P[n]['game'] != P[a]['game'] and abs(tmin(n) - tmin(a)) <= WIN]), set(), [], [tmin(a)]
            for n in reach:
                if P[n]['game'] in seen:
                    continue
                t2 = times + [tmin(n)]
                if max(t2) - min(t2) > WIN:
                    continue
                seen.add(P[n]['game']); legs.append(n); times.append(tmin(n))
                if len(legs) == 3:
                    break
            return sum(strength(n) for n in legs) if len(legs) == 3 else -1e9
        sidx = len(al) - 1 if len(al) >= 4 else None                            # README: salami rides the WEAKEST (4th) anchor -> demote loop drops it first
        mids = [i for i in range(len(al)) if i != sidx]
        pls = []
        for i in mids:                                                  # two moons per non-salami anchor
            for _ in range(MOONS_PER_ANC):
                pls.append({'rank': i, 'kind': 'moon', 'badge': "\U0001f680",
                            'rr': {"struct": "by 2s & 3", "risk": 2.0},
                            'legs': [al[i]], 'need': 2, 'games': {P[al[i]]['game']}})
        # (the salami is assembled AFTER the moons below, from the legs they leave behind -- moons get first pick)
        def fits(t, n):
            if P[n]['game'] in t['games']:
                return False
            ts = [tmin(x) for x in t['legs']] + [tmin(n)]
            return (max(ts) - min(ts)) <= WIN
        def needy(t):
            return (len(t['legs']) - 1) < t['need']
        # (no salami pre-fill: moons fill first, then the salami takes leftovers -- see after the demote loop)
        # (no re-task: a salami that cannot fill is dropped by the demote loop below; its legs free up for the moons -- per README)
        def _fill_round():                                             # round-robin: weakest anchor picks first, fills BOTH its tickets before the next
            rnd = 0
            while any(needy(t) for t in pls):
                ranks = sorted({t['rank'] for t in pls}, reverse=True)
                order = ranks if (rnd % 2 == 0) else list(reversed(ranks))
                progressed = False
                for r in order:
                    for t in sorted([x for x in pls if x['rank'] == r], key=lambda x: len(x['legs'])):
                        if not needy(t):
                            continue
                        pick = next((n for n in pool_av if fits(t, n)), None)
                        if pick is None:
                            continue
                        t['legs'].append(pick); t['games'].add(P[pick]['game']); pool_av.remove(pick); progressed = True
                rnd += 1
                if not progressed:
                    break
        _fill_round()
        _full = lambda t: (len(t['legs']) - 1) >= t['need']            # clean N-per-anchor: an anchor ships ALL its parlays or none
        while pls and not all(_full(t) for t in pls):
            drop = max(t['rank'] for t in pls)                          # weakest anchor by strength-index
            for t in [x for x in pls if x['rank'] == drop]:
                for n in t['legs'][1:]:
                    if n not in pool_av: pool_av.append(n)
            if al[drop] not in pool_av and not pend(al[drop]): pool_av.append(al[drop])   # the demoted anchor itself re-enters as a draftable leg (not just its legs)
            pls[:] = [t for t in pls if t['rank'] != drop]
            for t in pls:                                               # FULL REDRAFT: return every SURVIVING ticket's legs too and rebuild from scratch -- a demoted anchor's freed longshots re-enter the pool for the strongest anchors, instead of being handed to whoever was still needy while already-placed anchors keep weak leftovers
                for n in t['legs'][1:]:
                    if n not in pool_av: pool_av.append(n)
                t['legs'] = [t['legs'][0]]; t['games'] = {P[t['legs'][0]]['game']}
            pool_av[:] = byS(pool_av)
            _fill_round()
        # MOONS WIN, SALAMI IS LEFTOVER: with every kept moon full, build the salami on the weakest
        # anchor (al[sidx]) from the legs the moons left behind. If it can't reach 4 legs, it doesn't ship.
        if sidx is not None and al[sidx] in pool_av:                   # salami ships only if its anchor wasn't already drafted into a moon (moons win)
            pool_av.remove(al[sidx])
            sal = {'rank': sidx, 'kind': 'biggest', 'badge': "\U0001f96a",
                   'rr': {"struct": "by 2s, 3s & 4", "risk": 5.5},
                   'legs': [al[sidx]], 'need': 3, 'games': {P[al[sidx]]['game']}}
            while needy(sal):
                pick = next((n for n in pool_av if fits(sal, n)), None)
                if pick is None:
                    break
                sal['legs'].append(pick); sal['games'].add(P[pick]['game']); pool_av.remove(pick)
            if (len(sal['legs']) - 1) >= sal['need']:
                pls.append(sal)
        miss = 0
        return al, pls, miss

    best = None                                                        # exhaustive best-fillable-set search over one-per-game candidates
    N = len(cand_anchors)
    for ia in range(N):
        for ib in range(ia + 1, N):
            for ic in range(ib + 1, N):
                for idd in range(ic + 1, N):
                    al, pls, miss = _draft([cand_anchors[ia], cand_anchors[ib], cand_anchors[ic], cand_anchors[idd]])
                    sal_ok = any(t['kind'] == 'biggest' and (len(t['legs']) - 1) >= t['need'] for t in pls)
                    n_moons = sum(1 for t in pls if t['kind'] == 'moon')
                    score = (n_moons, 1 if sal_ok else 0, round(sum(strength(a) for a in al), 4))   # most clean moons first, salami as tiebreak, then strength
                    if best is None or score > best[0]:
                        best = (score, al, pls)
    if best is None:                                                   # fewer than 4 candidates (degenerate slate)
        anchors, parlays, _ = _draft(cand_anchors)
    else:
        _, anchors, parlays = best

    parlays = [t for t in parlays if (len(t['legs']) - 1) >= t['need']]   # ship only fully-filled parlays; dropped bats fall to builders

    # CANONICAL NAMING: a moon's name is tied to its LEG SET, not its output position.
    # Without this, two moons sharing an anchor can swap names on a rebuild (the partner pairs
    # come out in the opposite order) even though the legs are intact -> looks like legs "moved".
    # We assign names in a deterministic leg-set order, then emit in display order, so the same
    # three legs always carry the same slip name across rebuilds.
    _moons = [t for t in parlays if t['kind'] == 'moon']
    _nm = {}
    for t in sorted(_moons, key=lambda t: tuple(sorted(t['legs']))):
        _nm[id(t)] = name_for("moon")
    for t in _moons:                                        # emit moons first (display order), canonical name
        add(_nm[id(t)], "moon", t['badge'], t['legs'], rr=t['rr'])
    for t in parlays:                                       # then the salami
        if t['kind'] == 'biggest':
            add(name_for("biggest"), "biggest", t['badge'], t['legs'], rr=t['rr'])

    # lunch special + nightcap = the highest-ranked (by model) bat NOT already on a parlay, in each window
    _pused  = {l for t in parlays for l in t.get('legs', [])}   # parlay legs are name strings at this stage, not dicts
    _lnpick = []
    _nc = [n for n in byS(nonchalk) if P[n]['game'] in night_games and n not in _pused
           and P[n].get('odds') is not None and P[n]['odds'] <= 600]
    if _nc:
        add(name_for("late"), "late", "\U0001f303", [_nc[0]]); _lnpick.append(_nc[0])
    _lc = [n for n in byS(nonchalk) if P[n]['game'] in lunch_games and n not in _pused and n not in _lnpick
           and P[n].get('odds') is not None and P[n]['odds'] <= 600]
    if _lc:
        add(name_for("lunch"), "lunch", "\U0001f371", [_lc[0]]); _lnpick.append(_lc[0])

    # builders: every remaining NONCHALK bat as a single. Chalk is never a builder; the 33 buildable
    # bats land on tickets, and the chalk sit in lunch/nightcap (or nowhere, if their window is empty).
    BUILDER_MAX_ODDS = 600
    # Builders = the actual anchors as singles, PLUS the conviction "snubs": strong bats that landed on
    # NO parlay at all (neither an anchor nor a drafted leg) -- typically bats stuck in time-isolated late
    # games that no moon window could reach (e.g. Marte / Canzone). A bat already on a moon/salami leg is
    # on the board, so it is NOT re-listed; bats below leg strength aren't conviction plays, so they drop.
    # Concretely: the anchors, plus any UNUSED pool bat at least as strong as the weakest bat we actually
    # used on a leg, at <= +600. Self-adjusts per slate to catch whoever falls through the cracks.
    _parlays = [t for t in tickets if t.get('kind') in ('moon', 'biggest')]
    _usedN   = {l['name'] for t in _parlays for l in t['players']}
    _legfloor = min([strength(l['name']) for t in _parlays for l in t['players']] or [-1])
    _bnames = []
    for t in _parlays:                                  # every actual anchor ships as a single too
        a = t.get('anchor')
        if a and a not in _bnames and P[a].get('odds') is not None and P[a]['odds'] <= BUILDER_MAX_ODDS:
            _bnames.append(a)
    for n in byS(nonchalk):                             # + conviction snubs left off every parlay
        if n in _usedN or n in _bnames or n in _lnpick:   # _lnpick (lunch/nightcap) featured once, not duplicated as a builder
            continue
        if strength(n) >= _legfloor - 1e-9 and P[n].get('odds') is not None and P[n]['odds'] <= BUILDER_MAX_ODDS:
            _bnames.append(n)
    for n in _bnames:
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
            D_today['players'][n]['pending'] = info             # already in
