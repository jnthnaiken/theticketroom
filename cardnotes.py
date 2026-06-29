# cardnotes.py - per-player prose write-up, ported from assemble_tickets' ticket-note engine.
# Same phrase banks the tickets use, single-player mode -> rich card descriptions.
import math, re

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

def card_why(p):
    # fresh de-dup per card so each write-up is internally varied; seeded by name for determinism
    global _gseen
    _gseen = {}
    seed = sum(ord(c) for c in _lastnm(p.get('nm','')))
    parts = _edges_fill(p, seed)
    return (p.get('nm','') + ' ' + _join(parts) + '.') if parts else (p.get('nm','')+' takes his cuts.')
