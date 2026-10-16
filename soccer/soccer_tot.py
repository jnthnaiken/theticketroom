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
MIN_LEG = 1.40
N_LEGS = 2
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
    """mkt: TG (game) | TH (home team) | TA (away team); side: O | U."""
    p = 0.0
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
    for mkt, lines in (('TG', GAME_LINES), ('TH', TEAM_LINES), ('TA', TEAM_LINES)):
        for line in lines:
            for side in ('O', 'U'):
                price = pr.get((mkt, side, line))
                legs.append({'match': mkey, 'mkt': mkt, 'side': side, 'line': line, 'price': price,
                             'p': leg_prob(M, mkt, side, line), 'pm': leg_prob(M0, mkt, side, line),
                             'label': leg_label(mkt, side, line, fx['home'], fx['away'])})
    return {'match': mkey, 'mlh': mlh, 'mla': mla, 'lh': lh, 'la': la, 'legs': legs,
            'luck': {'home': [th, own_h, conc_h], 'away': [ta, own_a, conc_a]}}


def pick(views, started=lambda m: False):
    """The rule: top N_LEGS legs by model P, one per match, priced >= MIN_LEG, match not started."""
    cand = [l for v in views for l in v['legs']
            if l['price'] and l['price'] >= MIN_LEG and not started(l['match'])]
    cand.sort(key=lambda l: -l['p'])
    out, used = [], set()
    for l in cand:
        if l['match'] in used:
            continue
        out.append(l); used.add(l['match'])
        if len(out) == N_LEGS:
            break
    return out if len(out) == N_LEGS else None


def build(fixtures, prices_path, tm_path, date, cache_path=None, started=lambda m: False, gnum=None, gtime=None):
    """Returns (ticket or None, views). Sticky: a cache with legs is returned as-is."""
    if cache_path and os.path.exists(cache_path):
        try:
            c = json.load(open(cache_path, encoding='utf-8'))
            if c.get('legs'):
                return ticket(c['legs'], fixtures, gnum, gtime, date, c.get('picked_at')), None
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
    return ticket(legs, fixtures, gnum, gtime, date, stamp), views


GOALLINE_NAMES = ['The Net Count', 'Final Tally', 'Scoreline Special', 'The Ninety',
                  'Full-Time Whistle', 'Back of the Net', 'The Goal Rush', 'Shut the Gate', 'The Score Sheet',
                  'Ninety Minutes', 'The Totals Board']


def _h(s):
    h = 2166136261
    for ch in s:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def ticket(legs, fixtures, gnum, gtime, date, stamp):
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
                    'pm': round(l['pm'], 4)})
    name = GOALLINE_NAMES[_h('goalline' + date) % len(GOALLINE_NAMES)]
    return {'name': name, 'kind': 'goalline', 'badge': '🧤', 'units': 1, 'tlegs': out, 'players': [],
            'nlegs': len(out), 'pj': round(pj, 4), 'parlay_am': american(dj), 'payout10': round(10 * dj, 1),
            'lock': min((o['gtime'] for o in out if o['gtime']), default=''), 'picked_at': stamp,
            'final': False, 'rr': None, 'priced': len(out)}


# ---------------------------------------------------------------------------------------------
# grading (used by soccer_grade.py and mirrored in the page)
# ---------------------------------------------------------------------------------------------
def leg_won(leg, score):
    hg, ag = score
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
