#!/usr/bin/env python3
"""nba_fb.py -- FIRSTBASKET-2026-10-17. The first-basket model: state, features, probabilities, picks.

Owner, 2026-10-16: "find the correct layer of data points to organize the chaos. remember we are not
trying to beat the books, they are one of the layers. do not stop until you find the most successful
way to predict first basket and the most profitable way to build the tickets."
Research: claude/firstbasket-research-2026-10-17.md (14,439 games of play-by-play 2014-26, 7,230 games of
BettingPros first-basket prices 2020-26).

THE CHANCE A STARTER SCORES HIS GAME'S FIRST FIELD GOAL
    P(i) = P(his team scores first) x P(him | his team scores first)
  * TEAM. The team that wins the opening tip scores first 63.5% of the time (every season 62-65%).
    The tip is called before the game from a jump-ball Elo on each team's usual jumper (the starter who
    has jumped most often -- right 96% of the time), 64.6% accurate. Plus the team's own recent
    scored-first rate. Logit: TEAM_C + TEAM_TIP*logit(P(home wins tip)) + TEAM_FIRST*(home first-rate - away).
  * SHARE. Conditional logit over the team's five starters on: his share of the team's shots in the
    first five minutes, how often he takes the team's first shot, his share of all team shots, how often
    he scored his team's first basket, his FG%, whether he is the team's jumper, and a new-starter flag.
  * MARKET. The books are a layer: u = BLEND_M*log(market devig) + BLEND_P*log(model). On 4,400 games the
    model alone beat the market (log-loss 2.263 vs 2.279) and the blend gives the market ~7%. The books
    overprice stars and underprice the jumper.

THE TICKET (pick())
    EV = P x decimal(FanDuel price) - 1. Every starter at EV >= +30%, one per game, at most three a slate,
    flat 1u. If nothing clears +30%, the single best EV (> 0). Backtest 2021-26 at FanDuel prices,
    walk-forward: 1,007 picks, 12.0% hit at ~+1240, +52% ROI, every season positive.

STATE (nba_state.json) is replayed from history through the SAME update() the nightly settle uses, so the
features the model was fitted on and the features it is served are one computation.
"""
import json, math, re, unicodedata

HL_SHOT = 25.0          # games, exponentially weighted, starts only
HL_FG = 60.0            # games, all appearances
HL_TEAM = 40.0          # games
ELO_K, ELO_HA = 16.0, 8.0
A_SHOT = 1 - 0.5 ** (1 / HL_SHOT)
A_FG = 1 - 0.5 ** (1 / HL_FG)
A_TEAM = 1 - 0.5 ** (1 / HL_TEAM)
BENCH = 0.995           # starters take 99.5% of first baskets
EV_MIN, MAX_PICKS = 0.30, 3

def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r'\b(jr|sr|ii|iii|iv)\b\.?', '', s)
    return re.sub(r'[^a-z]', '', s)

def ikey(name):
    """'Chet Holmgren' / 'C. Holmgren' -> 'i:cholmgren' (secondary index)."""
    parts = re.sub(r'\b(Jr|Sr|II|III|IV)\b\.?', '', str(name or '')).replace('.', ' ').split()
    if len(parts) < 2: return 'i:' + norm(name)
    return 'i:' + norm(parts[0][0] + ' ' + ' '.join(parts[1:]))

def dec(am):
    am = float(am); return 1 + (am / 100 if am > 0 else 100 / -am)

def american(d):
    return int(round((d - 1) * 100)) if d >= 2 else int(round(-100 / (d - 1)))

def ew(d, k, x, a):
    """Bias-corrected exponential mean (pandas ewm adjust=True): keeps a weighted sum and a weight sum,
    so a man with three starts is the average of three starts, not his first start decayed by 3%."""
    if x is None or (isinstance(x, float) and math.isnan(x)): return
    s, w = d.get(k + '_s', 0.0) * (1 - a) + x, d.get(k + '_w', 0.0) * (1 - a) + 1
    d[k + '_s'], d[k + '_w'] = s, w
    d[k] = s / w


class State:
    def __init__(self, d=None):
        d = d or {}
        self.P = d.get('players', {})     # key -> dict
        self.T = d.get('teams', {})       # code -> {'first': ew}
        self.alias = d.get('alias', {})   # ikey -> key
        self.params = d.get('params', {})
        self.meta = d.get('meta', {})

    def dump(self):
        return {'meta': self.meta, 'params': self.params, 'teams': self.T, 'alias': self.alias, 'players': self.P}

    NICK = {'bubcarrington': 'carltoncarrington', 'nicclaxton': 'nicolasclaxton', 'herbjones': 'herbertjones',
            'camreddish': 'cameronreddish', 'camjohnson': 'cameronjohnson', 'gg jackson': 'gregoryjackson',
            'ggjackson': 'gregoryjackson', 'kj martin': 'kenyonmartin', 'kjmartin': 'kenyonmartin'}

    def key(self, name, create=False, team=None):
        """Exact normalized full name first. The initial+surname alias is only a LOOKUP fallback (ESPN's
        'C. Holmgren' style), and only when it is unambiguous -- two J. Williamses map to None."""
        k = norm(name)
        if k in self.P: return k
        if create:
            self.P[k] = {'nm': name}
            ik = ikey(name)
            self.alias[ik] = k if ik not in self.alias else None
            return k
        if self.NICK.get(k) in self.P: return self.NICK[k]
        a = self.alias.get(ikey(name))
        if a in self.P: return a
        if team:   # last resort: the one man on that team with this surname
            sur = norm(str(name).split()[-1]) if str(name).split() else ''
            if sur in ('jr', 'sr', 'ii', 'iii', 'iv') and len(str(name).split()) > 1: sur = norm(str(name).split()[-2])
            hits = [kk for kk, p in self.P.items() if p.get('team') == team and kk.endswith(sur)]
            if len(hits) == 1: return hits[0]
        return None

    # ---- features for one starter, BEFORE the game ----
    def feats(self, key):
        p = self.P.get(key) or {}
        g = lambda k, d: p.get(k) if p.get(k) is not None else d
        fgp = (p['fgm'] / p['fga']) if p.get('fga') else 0.46
        return {
            'x_fbc': math.log(max(g('fbc', .2), .02)), 'x_tf': math.log(max(g('tf', .2), .02)),
            'x_ef': math.log(max(g('ef', .2), .02)), 'x_fs': math.log(max(g('fs', .13), .02)),
            'x_fg': min(max(fgp, .3), .7) - .46, 'x_new': 1.0 if g('nst', 0) < 10 else 0.0,
            'jr': g('jr', -1.0), 'elo': g('elo', 0.0),
        }

    def jumper(self, keys):
        """The team's usual jumper among tonight's starters: the highest rolling jump rate."""
        keys = [k for k in keys if k]
        if not keys: return None
        jr = lambda k: (self.P.get(k) or {}).get('jr')
        return max(keys, key=lambda k: jr(k) if jr(k) is not None else -1)

    def p_tip_home(self, hk, ak):
        rh = (self.P.get(hk) or {}).get('elo', 0.0); ra = (self.P.get(ak) or {}).get('elo', 0.0)
        return 1 / (1 + 10 ** (-(rh - ra + ELO_HA) / 400))

    # ---- one finished game ----
    def update(self, g):
        """g: {'H','V','starters':{team:[names]}, 'jumpers':(home name, away name) or None, 'tip': team or None,
        'fb': name or None, 'fbT': team, 'fga':{name:n}, 'fgm':{name:n}, 'efga':{name:n}, 'tfirst':{team:name},
        'team_of':{name:team}}"""
        H, V = g['H'], g['V']
        team_of = g['team_of']
        # Learning resolves names by EXACT normalized name or the NICK table only -- never by the alias or
        # same-team-surname fallbacks, which are fine for reading a slate but would fold a rookie into a
        # veteran with the same initial and surname for good.
        def _k(n):
            k = norm(n)
            if k in self.P: return k
            if self.NICK.get(k) in self.P: return self.NICK[k]
            return self.key(n, create=True)
        K = {n: _k(n) for n in team_of}
        for n, k in K.items():
            self.P[k]['team'] = team_of[n]
        # jump-ball Elo (actual jumpers)
        j = g.get('jumpers')
        if j and j[0] and j[1] and g.get('tip') in (H, V):
            a, b = K.get(j[0]) or _k(j[0]), K.get(j[1]) or _k(j[1])
            pa, pb = self.P[a], self.P[b]
            ra, rb = pa.get('elo', 0.0), pb.get('elo', 0.0)
            p = 1 / (1 + 10 ** (-(ra - rb + ELO_HA) / 400)); y = 1.0 if g['tip'] == H else 0.0
            ka = ELO_K * max(1, 3 - pa.get('nj', 0) / 10); kb = ELO_K * max(1, 3 - pb.get('nj', 0) / 10)
            pa['elo'] = ra + ka * (y - p); pb['elo'] = rb - kb * (y - p)
            pa['nj'] = pa.get('nj', 0) + 1; pb['nj'] = pb.get('nj', 0) + 1
        jset = set(j or [])
        tfga = {T: sum(v for n, v in g['fga'].items() if team_of.get(n) == T) for T in (H, V)}
        tefga = {T: sum(v for n, v in g['efga'].items() if team_of.get(n) == T) for T in (H, V)}
        for T in (H, V):
            first = 1.0 if g.get('fbT') == T else 0.0
            ew(self.T.setdefault(T, {}), 'first', first, A_TEAM)
            if len(g['starters'].get(T, [])) == 5: self.T[T]['last5'] = list(g['starters'][T])
            for n in g['starters'].get(T, []):
                p = self.P[K.get(n) or _k(n)]
                ew(p, 'ef', (g['efga'].get(n, 0) / tefga[T]) if tefga[T] else None, A_SHOT)
                ew(p, 'fs', (g['fga'].get(n, 0) / tfga[T]) if tfga[T] else None, A_SHOT)
                ew(p, 'tf', 1.0 if g['tfirst'].get(T) == n else 0.0, A_SHOT)
                if first: ew(p, 'fbc', 1.0 if g.get('fb') == n else 0.0, A_SHOT)
                ew(p, 'jr', 1.0 if n in jset else 0.0, A_SHOT)
                p['nst'] = p.get('nst', 0) + 1
        for n in team_of:
            p = self.P[K[n]]
            ew(p, 'fga', float(g['fga'].get(n, 0)), A_FG)
            ew(p, 'fgm', float(g['fgm'].get(n, 0)), A_FG)


def game_probs(st, H, V, starters, params):
    """starters: {team:[names]} (5 each). Returns {name: {'p','pteam','share','jumper','team'}}."""
    pr = params
    keys = {T: [(n, st.key(n, team=T)) for n in starters[T]] for T in (H, V)}
    jh = st.jumper([k for _, k in keys[H]]); ja = st.jumper([k for _, k in keys[V]])
    ptip = st.p_tip_home(jh, ja) if (jh and ja) else 0.5
    lt = math.log(ptip / (1 - ptip))
    fd = (st.T.get(H, {}).get('first') or .5) - (st.T.get(V, {}).get('first') or .5)
    z = pr['team_c'] + pr['team_tip'] * lt + pr['team_first'] * fd
    ph = 1 / (1 + math.exp(-z))
    out = {}
    for T, pt in ((H, ph), (V, 1 - ph)):
        J = jh if T == H else ja
        us = []
        for n, k in keys[T]:
            f = st.feats(k) if k else State().feats(None)
            f['x_j'] = 1.0 if (k and k == J) else 0.0
            u = sum(pr['share'][c] * f[c] for c in pr['share'])
            us.append((n, u, f['x_j']))
        m = max(u for _, u, _ in us); den = sum(math.exp(u - m) for _, u, _ in us)
        for n, u, xj in us:
            sh = math.exp(u - m) / den
            out[n] = {'team': T, 'pteam': pt, 'share': sh, 'p': pt * sh * BENCH, 'jumper': bool(xj), 'ptip': ptip if T == H else 1 - ptip}
    return out


def blend(probs, market, params):
    """probs: {name: {...'p'}}; market: {name: decimal consensus/fair price} for the same game's starters.
    Market devig over the starters it prices; anyone it does not price keeps the model chance."""
    bm, bp = params.get('blend_m', 0.0), params.get('blend_p', 1.0)
    q = {n: 1 / d for n, d in market.items() if n in probs and d and d > 1}
    if len(q) < len(probs):
        for n in probs: probs[n]['pb'] = probs[n]['p']
        return probs
    s = sum(q.values())
    us = {n: bm * math.log(q[n] / s * BENCH) + bp * math.log(probs[n]['p']) for n in probs}
    m = max(us.values()); den = sum(math.exp(u - m) for u in us.values())
    for n in probs:
        probs[n]['pb'] = math.exp(us[n] - m) / den * BENCH
        probs[n]['pm'] = q[n] / s * BENCH
    return probs


def pick(cands, ev_min=EV_MIN, cap=MAX_PICKS):
    """cands: list of dicts with 'game','name','ev'. One per game, EV >= ev_min, best first, at most cap.
    If none qualifies, the single best EV > 0. Returns the chosen list."""
    c = sorted([x for x in cands if x.get('ev') is not None], key=lambda x: -x['ev'])
    seen, out = set(), []
    for x in c:
        if x['ev'] < ev_min or x['game'] in seen: continue
        out.append(x); seen.add(x['game'])
        if len(out) >= cap: break
    if not out and c and c[0]['ev'] > 0:
        out = [c[0]]
    return out


# ======================================================================================================
# BBDRAFT-2026-10-23. Owner: "build the ticket draft process the exact same as baseball with the anchors and
# shit and test it" -> "yes". Baseball's board, ported, with STRENGTH = VALUE (chance x FanDuel decimal):
#   * pool    = priced starters whose value z-score is >= Z_GATE above the slate mean, at most GAME_CAP a game
#   * anchors = the N_ANCHORS strongest -- each a 1u single
#   * moons   = MOONS_PER per anchor: the anchor + (MOON_LEGS-1) partners, every leg a different game, partners
#               snake-drafted from the rest of the pool by strength, each starter used once; full round robin
#               (6 doubles + 4 trebles + 1 four-fold = 11 bets x RR_UNIT = 2.75u)
# Backtest 2021-26 at FanDuel (claude/nba-baseballdraft-2026-10-23.md, nba/research/bball_draft.py): anchors
# 2,964 / 11.1% / +1,055u (+35.6%, every season up); moons 461 / 20 cashed / +140u; board +1,194u (+28.2%).
# The same draft with strength = likelihood (baseball's literal rule) lost -528u: the books price first-basket
# favourites ~5% short and a round robin multiplies it.
Z_GATE, GAME_CAP, N_ANCHORS, MOONS_PER, MOON_LEGS, RR_UNIT = 0.75, 4, 4, 2, 4, 0.10
MOON_DIFF = 2
WIN = None  # baseball's 120-min leg window does NOT apply: owner 10-23 "basketball lineups dont get confirmed until 15 min
            # before tip" -- no window makes a later leg confirmable at bet time anyway
# MOONFILL-2026-10-23: owner "should be 2 per anchor". Only ~15 of ~70 priced starters carry positive value a night
# (baseball: ~44 of ~260), so partners may sit in moons of DIFFERENT anchors; an anchor's two moons never share a
# partner (no duplicate slips). Backtest 2021-26: 6.0 moons/night, all 8 on 66% of nights, 4,511 moons, +2,425u
# (+19.5%), seasons +2543/+227/-53/-529/+237. (nba/research/bball_fill2.py)


def value(c):
    return c['p'] * dec(c['odds'])


def draft_pool(cands):
    """cands: [{'game','name','p','odds',...}] -> the gated pool, strongest first."""
    el = [c for c in cands if c.get('odds') and c.get('p') is not None]
    if len(el) < 8:
        return []
    v = [value(c) for c in el]; m = sum(v) / len(v); sd = (sum((x - m) ** 2 for x in v) / len(v)) ** .5 or 1e-9
    out, per = [], {}
    for c in sorted(el, key=lambda c: -value(c)):
        if (value(c) - m) / sd < Z_GATE: continue
        if per.get(c['game'], 0) >= GAME_CAP: continue
        out.append(c); per[c['game']] = per.get(c['game'], 0) + 1
    return out


# MOONDIFF-2026-10-24. Owner: "only throw a moon out if its an exact duplicate" -> "yea this works for me" (at .10u).
# Per anchor, the partner sets are walked in strength order (combinations over the ranked pool, every leg a
# different game): moon 1 = the first valid set; moon 2 = the next valid set that differs from moon 1 by at least
# MOON_DIFF partners. Partners may repeat across anchors and once inside an anchor. RR_UNIT 0.25 -> 0.10 (11 x 0.10
# = 1.10u a moon). Backtest 2021-26 (nba/research/bball_fill4.py): 6.4 moons/night, 4,843 moons, +7,016u at 0.25u
# = +2,806u at 0.10u (+52.7%), seasons +2507/+548/+3340/+933/-313 at 0.25u; board with 1u anchors +3,861u on
# 8,291u (+46.6%). Supersedes MOONFILL's sibling-disjoint snake (+2,425u, +19.5%).
def draft_board(cands):
    """-> {'anchors': [cand...], 'moons': [[cand x MOON_LEGS]...]} (only fully filled moons ship)."""
    import itertools
    pool = draft_pool(cands)
    # ANCHOR1G-2026-10-24. Owner, on P.J. Washington Jr. and Naji Marshall (both DAL, SAS@DAL) anchoring together:
    # "two anchors from not only the same game, but the same team ... we really think thats smart? cause i dont".
    # Only one man can score a game's first basket, so two anchors from one game can never both win. Anchors are now
    # the best value from each of N_ANCHORS different games. Backtest 2021-26: anchors +1,055u either way (36.9% ROI vs
    # 35.6%, 2,862 bets vs 2,964); board +3,549u vs +3,861u, the gap all moon noise in 2023 (better in the other 4).
    anchors, ag = [], set()
    for c in pool:
        if c['game'] in ag: continue
        anchors.append(c); ag.add(c['game'])
        if len(anchors) == N_ANCHORS: break
    rest = [c for c in pool if c not in anchors]
    moons = []
    for a in anchors:
        ok = [c for c in rest if c['game'] != a['game']]
        got = []
        for cb in itertools.combinations(ok, MOON_LEGS - 1):
            if len({a['game']} | {x['game'] for x in cb}) != MOON_LEGS: continue
            if got and len({x['name'] for x in got[0]} - {x['name'] for x in cb}) < MOON_DIFF: continue
            got.append(cb)
            if len(got) == MOONS_PER: break
        moons += [[a, *cb] for cb in got]
    return {'anchors': anchors, 'moons': moons}


def rr_combos(k):
    return sum(math.comb(k, z) for z in range(2, k + 1))


def rr_maxprofit(odds_list, unit=RR_UNIT):
    import itertools
    d = [dec(o) for o in odds_list]; tot = 0.0
    for z in range(2, len(d) + 1):
        for cb in itertools.combinations(d, z):
            m = 1.0
            for x in cb: m *= x
            tot += unit * m
    return tot - unit * rr_combos(len(d))
