#!/usr/bin/env python3
"""soccer_tot.py -- GOALLINE-2026-10-15. The daily goals parlay: game totals + team totals.

Owner: "design another algorithm that figures out the correct layer of data points ... the most
successful way to predict game totals and team totals for goals in a game. im thinking one parlay a
day." Then: "remember we are not trying to beat the books. it is one of the layers we are using."

THE MODEL (TOTALS v1, research: soccer-data research/totals-2026-10-15, project doc
claude/totals-research-2026-10-15.md). Two layers, one score matrix, every line read off it:

    market layer : each side's expected goals backed out of tonight's 1X2 + Over/Under 2.5 prices
                   (devigged best prices; Dixon-Coles rho -0.08; 0.05-goal grid)
    luck layer   : exponentially weighted (half-life 4 matches) recent  goals - npxG  for the side's
                   own attack, and  conceded - npxGA  for the OPPONENT'S defence (understat).
                   Recent goals regress toward the chances that made them; the market prices the goals.
    lambda_side  = market lambda x exp(C + B_OWN*own + B_OPP*opp)        (Poisson GLM, 2019-2026)

  Accuracy on unseen 2023-26 seasons: equal or better than the market alone on all nine lines tested.
  A side with no understat history (cup minnows, MLS, national teams) gets luck 0 = pure market.

THE PARLAY (pre-registered on 2020-22, run once on 2023-26):
    each day, the TWO highest-probability legs from DIFFERENT matches, among 18 leg types
    (game over/under 1.5/2.5/3.5, home and away over/under 0.5/1.5/2.5), each leg priced >= 1.40.
    Holdout 2023-26, market + luck: 519 days, 45.9% hit (predicted 43.7%) at about +107.
    The same rule on the market layer alone hit 43.2%.

STICKY. Picked once, before the earliest candidate kickoff, cached in slates/<d>/tot_pick.json and
held: the prices it was posted at are the prices it is graded at.
"""
import json, math, os, re, unicodedata
from datetime import datetime, timezone

C, B_OWN, B_OPP = 0.00528, -0.03318, -0.03971     # frozen fit, all 2019-2026 top-five seasons
HALF_LIFE, MIN_PERIODS = 4.0, 3
RHO = -0.08
MIN_LEG = 1.40          # on the market-fair price less MARGIN, as tested (STALEPRICE-2026-10-16)
MARGIN = 1.06
def n_legs(n_matches):
    """GLSIZE-2026-10-16 (owner: "it doesnt have to be just 2 picks. it can change based on the size of the slate").
    Pre-registered on 2020-22, run once on 2023-26 (with BTTS legs): 1 match -> 1 leg (63.6% hit, pred 63.9%),
    2-5 -> 2 (42.1%, pred 42.4%), 6-11 -> 3 (31.7%, pred 29.1%), 12+ -> 4 (19.8%, pred 20.0%)."""
    return 1 if n_matches <= 1 else (2 if n_matches <= 5 else (3 if n_matches <= 11 else 4))
KMAX = 11

GAME_LINES = (1.5, 2.5, 3.5)
TEAM_LINES = (0.5, 1.5, 2.5)


# ---------------------------------------------------------------------------------------------
# odds + score matrix
# ---------------------------------------------------------------------------------------------
def dec(odds):
    """'5/6' | '+120' | '-150' | 'EVS' | 1.83 -> decimal."""
    if odds is None:
        return None
    if isinstance(odds, (int, float)):
        return float(odds)
    s = str(odds).strip().upper()
    if s in ('EVS', 'EVEN', 'EVENS'):
        return 2.0
    m = re.fullmatch(r'(\d+)/(\d+)', s)
    if m:
        return 1 + int(m.group(1)) / int(m.group(2))
    m = re.fullmatch(r'([+-])(\d+)', s)
    if m:
        v = int(m.group(2))
        return 1 + v / 100 if m.group(1) == '+' else 1 + 100 / v
    try:
        return float(s)
    except ValueError:
        return None


def american(d):
    return int(round((d - 1) * 100)) if d >= 2 else -int(round(100 / (d - 1)))


def _pois(l):
    return [math.exp(-l) * l ** k / math.factorial(k) for k in range(KMAX)]


def matrix(lh, la, rho=RHO):
    ph, pa = _pois(lh), _pois(la)
    M = [[ph[i] * pa[j] for j in range(KMAX)] for i in range(KMAX)]
    M[0][0] *= 1 - lh * la * rho
    M[0][1] *= 1 + lh * rho
    M[1][0] *= 1 + la * rho
    M[1][1] *= 1 - rho
    s = sum(max(x, 0) for r in M for x in r)
    return [[max(x, 0) / s for x in r] for r in M]


def leg_prob(M, mkt, side, line):
    """mkt: TG (game) | TH (home team) | TA (away team) | BT (both teams to score, side Y/N); side: O | U."""
    p = 0.0
    if mkt == 'BT':   # GLBTTS-2026-10-16
        yes = sum(M[i][j] for i in range(1, KMAX) for j in range(1, KMAX))
        return yes if side == 'Y' else 1 - yes
    for i in range(KMAX):
        for j in range(KMAX):
            v = i + j if mkt == 'TG' else (i if mkt == 'TH' else j)
            if (v > line) if side == 'O' else (v < line):
                p += M[i][j]
    return p


_GRID = None


def implied(ph, pd_, pa, pover):
    """Market lambdas: the (lh, la) on a 0.05 grid whose DC matrix best reproduces the devigged
    home/away win and over-2.5 probabilities (exactly the research's market layer)."""
    global _GRID
    if _GRID is None:
        g = [0.2 + 0.05 * i for i in range(81)]
        _GRID = []
        for lh in g:
            for la in g:
                M = matrix(lh, la)
                hw = sum(M[i][j] for i in range(KMAX) for j in range(KMAX) if i > j)
                aw = sum(M[i][j] for i in range(KMAX) for j in range(KMAX) if i < j)
                ov = leg_prob(M, 'TG', 'O', 2.5)
                _GRID.append((lh, la, hw, aw, ov))
    best = min(_GRID, key=lambda r: (r[2] - ph) ** 2 + (r[3] - pa) ** 2 + (r[4] - pover) ** 2)
    return best[0], best[1]


# ---------------------------------------------------------------------------------------------
# luck layer
# ---------------------------------------------------------------------------------------------
_STRIP = re.compile(r'\b(fc|afc|cf|sc|ac|ss|as|ssc|us|rc|cd|ud|sd|rcd|vfb|vfl|tsg|bv|fk|sk|nk|1\.|calcio|club|de|la)\b')
ALIAS = {   # ESPN / oddschecker spelling -> understat spelling, where normalising is not enough
    'rb leipzig': 'rasenballsport leipzig', 'leipzig': 'rasenballsport leipzig',
    'paris saint-germain': 'paris saint germain', 'psg': 'paris saint germain', 'paris sg': 'paris saint germain',
    'internazionale': 'inter', 'inter milan': 'inter', 'milan': 'ac milan',
    'manchester united': 'manchester united', 'man utd': 'manchester united', 'man united': 'manchester united',
    'manchester city': 'manchester city', 'man city': 'manchester city',
    'wolves': 'wolverhampton wanderers', 'wolverhampton': 'wolverhampton wanderers',
    'tottenham hotspur': 'tottenham', 'spurs': 'tottenham', 'newcastle united': 'newcastle united',
    'brighton & hove albion': 'brighton', 'brighton and hove albion': 'brighton',
    'west ham united': 'west ham', 'nottingham forest': 'nottingham forest', "nott'm forest": 'nottingham forest',
    'borussia monchengladbach': 'borussia m.gladbach', "borussia m'gladbach": 'borussia m.gladbach', 'gladbach': 'borussia m.gladbach',
    'bayern munich': 'bayern munich', 'bayern munchen': 'bayern munich',
    'cologne': 'fc cologne', 'koln': 'fc cologne', '1. fc koln': 'fc cologne',
    'mainz': 'mainz 05', 'mainz 05': 'mainz 05', 'hoffenheim': 'hoffenheim', 'st. pauli': 'st. pauli',
    'atletico madrid': 'atletico madrid', 'atlético madrid': 'atletico madrid', 'athletic club': 'athletic club',
    'athletic bilbao': 'athletic club', 'real betis': 'real betis', 'betis': 'real betis', 'celta vigo': 'celta vigo',
    'deportivo alaves': 'alaves', 'alavés': 'alaves', 'rayo vallecano': 'rayo vallecano',
    'olympique lyonnais': 'lyon', 'olympique marseille': 'marseille', 'olympique de marseille': 'marseille',
    'stade rennais': 'rennes', 'saint-etienne': 'saint-etienne', 'as monaco': 'monaco', 'ogc nice': 'nice',
    'hellas verona': 'verona', 'as roma': 'roma',
}


def norm(name):
    s = unicodedata.normalize('NFKD', str(name)).encode('ascii', 'ignore').decode().lower().strip()
    return s


def key(name):
    s = norm(name)
    s = ALIAS.get(s, s)
    s = _STRIP.sub(' ', s)
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def load_tm(path):
    """tm.psv: league|team|date|h_a|xG|xGA|npxG|npxGA|scored|missed  (understat teamsData history)."""
    rows = {}
    if not path or not os.path.exists(path):
        return rows
    for ln in open(path, encoding='utf-8'):
        p = ln.rstrip('\n').split('|')
        if len(p) < 10 or p[0] == 'league':
            continue
        rows.setdefault(p[1], []).append((p[2], float(p[6]), float(p[7]), int(p[8]), int(p[9])))
    for t in rows:
        rows[t] = sorted(set(rows[t]))
    return rows


def _ewm(vals):
    """pandas ewm(halflife=HL).mean() over the series (adjust=True), None under MIN_PERIODS."""
    if len(vals) < MIN_PERIODS:
        return None
    a = 1 - 0.5 ** (1 / HALF_LIFE)
    num = den = 0.0
    for v in vals:
        num = num * (1 - a) + v
        den = den * (1 - a) + 1
    return num / den


class Luck:
    def __init__(self, tm_rows, before_date):
        self.by_key = {}
        for team, rows in tm_rows.items():
            past = [r for r in rows if r[0] < before_date]
            self.by_key[key(team)] = (team, past)

    def find(self, name):
        k = key(name)
        if k in self.by_key:
            return self.by_key[k]
        # token containment fallback ("Bayer Leverkusen" ~ "Bayer Leverkusen", "Brighton" ~ "Brighton")
        cands = [v for kk, v in self.by_key.items() if kk and (kk in k or k in kk)]
        return cands[0] if len(cands) == 1 else (None, [])

    def xga(self, name, n=10):
        """DEFXGA-2026-10-16: the side's non-penalty xG conceded per match over its last `n` league games
        before the slate (None with no understat history). Fills the research table's long-empty Def column."""
        team, past = self.find(name)
        if not past:
            return None
        last = past[-n:]
        return round(sum(r[2] for r in last) / len(last), 2)

    def own_opp(self, name):
        team, past = self.find(name)
        if not past:
            return None, None, None
        own = _ewm([s - x for (_, x, xa, s, c) in past])          # goals - npxG
        conc = _ewm([c - xa for (_, x, xa, s, c) in past])        # conceded - npxGA
        return team, own, conc


# ---------------------------------------------------------------------------------------------
# prices
# ---------------------------------------------------------------------------------------------
def load_prices(path):
    """tot.psv: match|market|side|line|odds   market WIN (side H/D/A, line -), TG/TH/TA (side O/U)."""
    P = {}
    if not path or not os.path.exists(path):
        return P
    for ln in open(path, encoding='utf-8'):
        p = ln.rstrip('\n').split('|')
        if len(p) != 5 or p[0] == 'match':
            continue
        m, mkt, side, line, odds = p
        d = dec(odds)
        if not d or d <= 1:
            continue
        P.setdefault(m, {})[(mkt, side, None if line in ('', '-') else float(line))] = d
    return P


LEG_NAMES = {'TG': 'Match', 'TH': '{home}', 'TA': '{away}'}


def leg_label(mkt, side, line, home, away):
    if mkt == 'BT':
        return 'Both teams to score' if side == 'Y' else 'Both teams to score: No'
    who = 'Match' if mkt == 'TG' else (home if mkt == 'TH' else away)
    goals = 'goals' if mkt == 'TG' else ('goal' if line == 0.5 and side == 'O' else 'goals')
    if mkt != 'TG' and line == 0.5:
        return f"{who} to score" if side == 'O' else f"{who} not to score"
    return f"{who} {'over' if side == 'O' else 'under'} {line:g} {goals}"


def match_view(mkey, fx, prices, luck):
    """Every priced leg on one match with its model and market probability."""
    pr = prices.get(mkey) or {}
    h, d_, a = pr.get(('WIN', 'H', None)), pr.get(('WIN', 'D', None)), pr.get(('WIN', 'A', None))
    o25, u25 = pr.get(('TG', 'O', 2.5)), pr.get(('TG', 'U', 2.5))
    if not all((h, d_, a, o25, u25)):
        return None
    s = 1 / h + 1 / d_ + 1 / a
    pover = (1 / o25) / (1 / o25 + 1 / u25)
    mlh, mla = implied(1 / h / s, 1 / d_ / s, 1 / a / s, pover)
    th, own_h, conc_h = luck.own_opp(fx['home'])
    ta, own_a, conc_a = luck.own_opp(fx['away'])
    eh = C + B_OWN * (own_h or 0) + B_OPP * (conc_a or 0)
    ea = C + B_OWN * (own_a or 0) + B_OPP * (conc_h or 0)
    lh, la = mlh * math.exp(eh), mla * math.exp(ea)
    M, M0 = matrix(lh, la), matrix(mlh, mla)
    legs = []
    # GLBTTS-2026-10-16 (owner: "can we scrap btts too. throw that in the parlay too"): BTTS Yes/No join the menu.
    _menu = [(m, ln, sd) for m, lines in (('TG', GAME_LINES), ('TH', TEAM_LINES), ('TA', TEAM_LINES))
             for ln in lines for sd in ('O', 'U')] + [('BT', None, 'Y'), ('BT', None, 'N')]
    for mkt, line, side in _menu:
        best = pr.get((mkt, side, line))
        pm = leg_prob(M0, mkt, side, line)
        # STALEPRICE-2026-10-16. The research rule judged a leg at the MARKET-FAIR price less a normal
        # margin (1/(pm*MARGIN)), never at the best quote, and the audit showed best quotes carry stale
        # outliers (10-16: Deportivo to score at 10/11 as 116/100 home favourites; Le Mans o1.5 longer
        # than o2.5). So: qualify on `est`, and post the scraped best price CAPPED at fair (1/pm).
        fair = 1 / pm if pm > 0 else None
        price = min(best, fair) if (best and fair) else None
        legs.append({'match': mkey, 'mkt': mkt, 'side': side, 'line': line, 'price': price, 'best': best,
                     'est': (1 / (pm * MARGIN)) if pm > 0 else None,
                     'p': leg_prob(M, mkt, side, line), 'pm': pm,
                     'label': leg_label(mkt, side, line, fx['home'], fx['away'])})
    return {'match': mkey, 'mlh': mlh, 'mla': mla, 'lh': lh, 'la': la, 'legs': legs,
            'luck': {'home': [th, own_h, conc_h], 'away': [ta, own_a, conc_a]}}


def pick(views, started=lambda m: False):
    """The rule: top n_legs(slate size) legs by model P, one per match, qualifying at >= MIN_LEG on the market-fair
    price, match not started. Slate size = priced board matches."""
    N_LEGS = n_legs(len(views))
    cand = [l for v in views for l in v['legs']
            if l['price'] and l['est'] and l['est'] >= MIN_LEG and not started(l['match'])]
    cand.sort(key=lambda l: -l['p'])
    out, used = [], set()
    for l in cand:
        if l['match'] in used:
            continue
        out.append(l); used.add(l['match'])
        if len(out) == N_LEGS:
            break
    return out if len(out) == N_LEGS else None


def build(fixtures, prices_path, tm_path, date, cache_path=None, started=lambda m: False, gnum=None, gtime=None,
          recent=None):
    """Returns (ticket or None, views). Sticky: a cache with legs is returned as-is."""
    if cache_path and os.path.exists(cache_path):
        try:
            c = json.load(open(cache_path, encoding='utf-8'))
            if c.get('legs'):
                return ticket(c['legs'], fixtures, gnum, gtime, date, c.get('picked_at'), c.get('views'), recent=recent), None
        except Exception:
            pass
    prices = load_prices(prices_path)
    luck = Luck(load_tm(tm_path), date)
    views = [v for v in (match_view(k, fx, prices, luck) for k, fx in fixtures.items()) if v]
    legs = pick(views, started)
    if not legs:
        return None, views
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')
    if cache_path:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        json.dump({'kind': 'goalline', 'date': date, 'picked_at': stamp, 'legs': legs,
                   'views': [{k: v[k] for k in ('match', 'mlh', 'mla', 'lh', 'la', 'luck')} for v in views]},
                  open(cache_path, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    vv = [{k: v[k] for k in ('match', 'mlh', 'mla', 'lh', 'la', 'luck')} for v in views]
    return ticket(legs, fixtures, gnum, gtime, date, stamp, vv, recent=recent), views


GOALLINE_NAMES = ['The Net Count', 'Final Tally', 'Scoreline Special', 'The Ninety',
                  'Full-Time Whistle', 'Back of the Net', 'The Goal Rush', 'Shut the Gate', 'The Score Sheet',
                  'Ninety Minutes', 'The Totals Board']


def _h(s):
    h = 2166136261
    for ch in s:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def _clock(t):
    """GLLOCK-2026-10-17: '9:30 AM' -> 570. The lock is the EARLIEST kickoff, and a string min() put
    '7:30 PM' ahead of '9:30 AM' (10-17: the slip read Lock 7:30 PM with a 9:30 AM leg on it)."""
    m = re.match(r'\s*(\d{1,2}):(\d{2})\s*([AP]M)', str(t or ''), re.I)
    if not m:
        return 99999
    h, mi, ap = int(m.group(1)) % 12, int(m.group(2)), m.group(3).upper()
    return (h + (12 if ap == 'PM' else 0)) * 60 + mi


def ticket(legs, fixtures, gnum, gtime, date, stamp, views=None, recent=None):
    gnum = gnum or {}
    gtime = gtime or {}
    pj = 1.0; dj = 1.0
    out = []
    for l in legs:
        fx = fixtures.get(l['match'], {})
        pj *= l['p']; dj *= l['price']
        out.append({'match': l['match'], 'gmatch': f"{fx.get('home', '?')} v {fx.get('away', '?')}",
                    'game': gnum.get(l['match'], 0), 'gtime': gtime.get(l['match'], ''),
                    'mkt': l['mkt'], 'side': l['side'], 'line': l['line'], 'label': l['label'],
                    'price': round(l['price'], 3), 'odds': american(l['price']), 'p': round(l['p'], 4),
                    'best': l.get('best'),
                    'pm': round(l['pm'], 4)})
    name = GOALLINE_NAMES[_h('goalline' + date) % len(GOALLINE_NAMES)]
    vmap = {v['match']: v for v in (views or [])}
    # VOICEMEM-2026-10-19: dated, nothing twice on the slip, nothing from the last few boards (`recent`).
    _mem = None
    if recent is not None:
        from soccer_voicemem import Mem
        _mem = Mem(day=date, recent=recent)
    for o_, l in zip(out, legs):
        o_['why'] = writeup(l, vmap.get(l['match']), fixtures.get(l['match'], {}), date, mem=_mem)
        if _mem:
            _mem.commit(o_['why'])
    return {'name': name, 'kind': 'goalline', 'badge': '🧤', 'units': 1, 'tlegs': out, 'players': [],
            'nlegs': len(out), 'pj': round(pj, 4), 'parlay_am': american(dj), 'payout10': round(10 * dj, 1),
            'lock': min((o['gtime'] for o in out if o['gtime']), key=_clock, default=''), 'picked_at': stamp,   # GLLOCK-2026-10-17
            'final': False, 'rr': None, 'priced': len(out)}


# ---------------------------------------------------------------------------------------------
# research (GLRESEARCH-2026-10-16, owner: "add any of the new data for total goals to the research tab")
# One row per priced board match, from the CURRENT prices (independent of the sticky pick): both
# sides' expected goals (market and model), the luck reads, and the model probability + best price
# (capped at fair, as the Goal Line posts it) for the lines a reader actually bets.
# ---------------------------------------------------------------------------------------------
RS_LINES = [('o15', 'TG', 'O', 1.5), ('o25', 'TG', 'O', 2.5), ('u25', 'TG', 'U', 2.5), ('o35', 'TG', 'O', 3.5),
            ('hs', 'TH', 'O', 0.5), ('as', 'TA', 'O', 0.5), ('h15', 'TH', 'O', 1.5), ('a15', 'TA', 'O', 1.5),
            ('btts', 'BT', 'Y', None), ('bttsn', 'BT', 'N', None)]


def research(fixtures, prices_path, tm_path, date, gnum=None, gtime=None, picked=None):
    gnum, gtime = gnum or {}, gtime or {}
    prices = load_prices(prices_path)
    luck = Luck(load_tm(tm_path), date)
    pk = {(l['match'], l['mkt'], l['side'], l['line']) for l in (picked or [])}
    rows = []
    for k, fx in fixtures.items():
        v = match_view(k, fx, prices, luck)
        if not v:
            continue
        M = matrix(v['lh'], v['la'])
        by = {(l['mkt'], l['side'], l['line']): l for l in v['legs']}
        r = {'match': k, 'home': fx['home'], 'away': fx['away'], 'game': gnum.get(k, 0), 'gtime': gtime.get(k, ''),
             'mlh': round(v['mlh'], 2), 'mla': round(v['mla'], 2), 'lh': round(v['lh'], 2), 'la': round(v['la'], 2),
             'hfin': None if v['luck']['home'][1] is None else round(v['luck']['home'][1], 2),
             'hconc': None if v['luck']['home'][2] is None else round(v['luck']['home'][2], 2),
             'afin': None if v['luck']['away'][1] is None else round(v['luck']['away'][1], 2),
             'aconc': None if v['luck']['away'][2] is None else round(v['luck']['away'][2], 2)}
        for key_, mkt, side, line in RS_LINES:
            l = by.get((mkt, side, line))
            r[key_] = round(l['p'], 4) if l else None
            r[key_ + '_o'] = american(l['price']) if (l and l['price']) else None
            if (k, mkt, side, line) in pk:
                r[key_ + '_gl'] = 1
        rows.append(r)
    rows.sort(key=lambda r: (r['game'] or 99, r['match']))
    return rows


# ---------------------------------------------------------------------------------------------
# write-up (GLWRITE-2026-10-16, owner: "need more of a write up too")
# One sentence per leg, from what the model actually saw: how many goals the market expects (the
# lambdas) and whose finishing has been running hot or cold (the luck layer). House voice, NO DIGITS
# (the card already prints price and probability), no promise. Deterministic: same inputs, same words.
# ---------------------------------------------------------------------------------------------
def _pk(opts, key):
    return opts[_h(key) % len(opts)]


def writeup(l, v, fx, date, mem=None):
    """VOICEMEM-2026-10-19: every sentence is drawn through `mem` when one is given -- dated, and not a
    phrase already on this slip or on the last few boards. Without `mem` it is the old dated hash."""
    home, away = fx.get('home', 'the hosts'), fx.get('away', 'the visitors')
    key = l['match'] + l['mkt'] + l['side'] + str(l['line']) + date
    if not v:
        return ''
    P = (lambda opts, k: mem.pick(opts, k, names=(home, away))) if mem else (lambda opts, k: _pk(opts, k))
    lh, la = v['lh'], v['la']
    lk = v.get('luck') or {}
    h_own, h_conc = (lk.get('home') or [None, None, None])[1:]
    a_own, a_conc = (lk.get('away') or [None, None, None])[1:]
    HOT, COLD = 0.15, -0.15
    if l['mkt'] == 'TG':
        if l['side'] == 'O':
            base = P([f'{home} and {away} is priced as an open game, and both back lines have been giving up proper chances.',
                      f'Plenty of traffic expected at both ends of {home} v {away}.',
                      f'{home} v {away} has goals written all over it, two sides happier attacking than defending.',
                      f'{home} v {away} looks like end-to-end stuff, with the defending optional.',
                      f'Neither {home} nor {away} is built to sit back, and the market agrees.',
                      f'Leave the tin hat at home for {home} v {away}; this one is set up for goals.'], key)
            extra = ''
            if (h_own or 0) < COLD or (a_own or 0) < COLD:
                who = home if (h_own or 0) < (a_own or 0) else away
                extra = ' ' + P([f'{who} have been finishing below their chances lately, and that usually turns.',
                                 f'{who} have been leaving goals out there lately, and the chances have not dried up.',
                                 f'{who} are due a kinder night in front of goal; the chances have been there.'], key + 'x')
            return base + extra
        base = P([f'{home} v {away} shapes up as a cagey one, and the model sees a long way to a goal-fest.',
                  f'Not much between {home} and {away}, and tight games rarely run away from anyone.',
                  f'Expect {home} v {away} to be more chess than fireworks.',
                  f'{home} v {away} has the look of a long, careful evening.',
                  f'Two sides at {home} v {away} who like the ball more than the risk.',
                  f'This one at {home} v {away} reads tight, tense and low on traffic.'], key)
        extra = ''
        if max(h_own or 0, a_own or 0) > HOT:
            who = home if (h_own or 0) >= (a_own or 0) else away
            extra = ' ' + P([f'{who} have been scoring above their chances, and that tends to cool off.',
                             f'{who} have been finishing above their chances, and hot streaks cool.',
                             f'{who} have been running above their chances in front of goal, and that rarely holds.'], key + 'x')
        return base + extra
    if l['mkt'] == 'BT':
        if l['side'] == 'Y':
            base = P([f'Both {home} and {away} carry enough threat to get on the board.',
                      f'Neither back line at {home} v {away} looks like keeping a clean sheet.',
                      f'Goals at both ends of {home} v {away}; each side should find a way through.',
                      f'{home} and {away} both have the tools to make the other side pay.',
                      f'There is a goal in both of these sides at {home} v {away}.',
                      f'Clean sheets look a long shot at both ends of {home} v {away}.'], key)
            extra = ''
            if min(h_conc or 0, a_conc or 0) < COLD:
                extra = ' ' + P(['One of these defences has been getting away with it lately, and that rarely lasts.',
                                 'One of these back lines has been living on luck, and luck runs out.',
                                 'One defence here has conceded less than its chances deserve, and that evens out.'], key + 'x')
            return base + extra
        base = P([f'One of {home} or {away} should struggle to find the net.',
                  f'We expect a clean sheet somewhere in {home} v {away}.',
                  f'{home} v {away} looks like one side doing the scoring.',
                  f'One of {home} or {away} looks set for a frustrating night up front.',
                  f'{home} v {away} has a shutout written in somewhere.'], key)
        extra = ''
        if max(h_own or 0, a_own or 0) > HOT:
            extra = ' ' + P(['There is a finishing streak in this fixture that the chances do not back up.',
                             'Somebody here has been finishing above the chances, and that tends to settle.'], key + 'x')
        return base + extra
    side_home = l['mkt'] == 'TH'
    team, opp = (home, away) if side_home else (away, home)
    lam = lh if side_home else la
    own = h_own if side_home else a_own
    opp_conc = a_conc if side_home else h_conc
    if l['side'] == 'O':
        base = (P([f'{team} carry the bigger threat in this one and should find the net.',
                   f'{team} get chances in bunches, and {opp} have been letting them come.',
                   f'Back {team} to get on the scoresheet; the attack has been creating enough to deserve it.',
                   f'{team} have the firepower to find a way past {opp}.',
                   f'{team} bring plenty of attacking menace to this one.',
                   f'Expect {team} to make {opp} work for every minute.'], key)
                if lam >= 1.2 else
                P([f'{team} only need one, and they have been creating enough to get it.',
                   f'{team} are not the favourites here, but one goal from them is the likeliest thing on the card.',
                   f'One goal is all this asks of {team}, and they carry enough of a threat to find it.',
                   f'{team} do not need a classic here, just the one, and they have the attackers for it.',
                   f'A single {team} goal cashes this leg, and that is a modest ask.',
                   f'{team} only have to get on the board once, and they have been knocking on the door.'], key))
        extra = ''
        if (own or 0) < COLD:
            extra = ' ' + P([f'Their finishing has been running behind their chances, which is exactly when the goals come.',
                             f'Their chances have been better than their finishing lately, and that gap tends to close.',
                             f'They have been unlucky in front of goal lately, and that kind of luck turns.'], key + 'x')
        elif (opp_conc or 0) < COLD:
            extra = ' ' + P([f'{opp} have been getting away with more than their chances allow, and that rarely lasts.',
                             f'{opp} have conceded less than their chances deserve lately, and that evens out.',
                             f'{opp} have been living a charmed life at the back, and charms wear off.'], key + 'x')
        return base + extra
    base = P([f'{team} have a hard afternoon ahead against {opp}, and a quiet one in front of goal suits this line.',
              f'{opp} should keep {team} to scraps.',
              f'We do not see {team} running riot here.',
              f'{opp} have the structure to keep {team} quiet.',
              f'{team} look set for a lean night in front of goal against {opp}.',
              f'{opp} should keep a lid on {team} in this one.'], key)
    extra = ''
    if (own or 0) > HOT:
        extra = ' ' + P([f'{team} have been scoring above their chances lately, and that tends to come back to earth.',
                         f'{team} have been finishing above their chances, and hot streaks cool.',
                         f'{team} have been running above their chances in front of goal, and that rarely holds.'], key + 'x')
    elif (opp_conc or 0) > HOT:
        extra = ' ' + P([f'{opp} have been conceding more than the chances they allow, and that kind of run corrects itself.',
                         f'{opp} have been unlucky at the back lately, and the chances they allow are fewer than the goals.',
                         f'{opp} have shipped more than their chances deserve, and that tends to even out.'], key + 'x')
    return base + extra


# ---------------------------------------------------------------------------------------------
# grading (used by soccer_grade.py and mirrored in the page)
# ---------------------------------------------------------------------------------------------
def leg_won(leg, score):
    hg, ag = score
    if leg['mkt'] == 'BT':
        both = hg > 0 and ag > 0
        return both if leg['side'] == 'Y' else not both
    v = hg + ag if leg['mkt'] == 'TG' else (hg if leg['mkt'] == 'TH' else ag)
    return v > leg['line'] if leg['side'] == 'O' else v < leg['line']


def grade(t, results, finals):
    """None while undecided. A losing leg decides the ticket at once; a win needs every leg final."""
    legs = t.get('tlegs') or []
    if not legs:
        return None
    st = []
    for l in legs:
        g = l.get('game')
        sc = (results or {}).get(str(g)) or (results or {}).get(g)
        if g in finals and sc:
            st.append(leg_won(l, sc))
        else:
            st.append(None)
    stake = float(t.get('units') or 1)
    if any(s is False for s in st):
        return {'kind': t['kind'], 'stake': stake, 'net': -stake, 'won': False}
    if all(s is True for s in st):
        return {'kind': t['kind'], 'stake': stake, 'net': stake * (t['payout10'] / 10 - 1), 'won': True}
    return None


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('fixtures'); ap.add_argument('tot_psv'); ap.add_argument('tm_psv'); ap.add_argument('date')
    a = ap.parse_args()
    fx = json.load(open(a.fixtures))['matches']
    t, views = build(fx, a.tot_psv, a.tm_psv, a.date)
    for v in views or []:
        print(f"{v['match']:45s} mkt {v['mlh']:.2f}-{v['mla']:.2f} -> {v['lh']:.2f}-{v['la']:.2f}  luck {v['luck']}")
    print(json.dumps(t, indent=1, ensure_ascii=False))
