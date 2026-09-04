#!/usr/bin/env python3
"""
nfl_mock.py -- THE SCORER. atd.psv + nflverse -> scored.json, then shells out to the draft.

Sibling of soccer_mock.py and deliberately the same shape: it scores, it does NOT draft. The
draft is soccer_draft.js, reused as-is rather than forked -- see nfl_draft_cli.js for why.

INPUTS   atd.psv        match|player|fractional-odds        (oddschecker, via nfl/atd_scrape.js)
         fixtures.json  {date, matches:{slug:{home,away,kickoff,espn}}}
         nflverse       via nfl_stats.build(season, week)

THE MODEL is four terms, measured as percentage-point lift within a usage stratum on held-out
2025 -- never by AUC, which is the instrument that produced the retraction in
nfl/EDGE-2026-09-02.md. See nfl/MODEL-2026-09-02.md:

    usage          touches per game                    +28.2pp
    role           inside-10 touches per game           +6.6pp  (usage AND price held)
    concentration  inside-10 share of own touches       +5.0pp  (usage AND price held)
    environment    implied team total                   +8.6pp  (usage held)
    position       tilt vs same-usage average       TE +2.9 / RB -1.4

⚠️ NO DEFENSIVE MATCHUP TERM. Opponent TD rate allowed inside the 10 measured -0.2pp and opponent
red-zone trips allowed +0.8pp. The genre is dead on both instruments. Do not add one.

⚠️ PRICEONCE (claude/priceonce-doctrine.md). A price is WRITTEN ONCE per slate. This scorer never
changes a price it has already seen: `atd.psv` is merged into the committed `prices.json`, holding
every existing entry and only appending new names. The scrape may therefore run as often as we
like -- the MERGE enforces the rule, not the scrape. A TOTAL may still move, but only for live
reasons: here that is weather (the wind trim is measured, -1.6pp above 11mph within usage strata)
and inactives.

⚠️ ADDING IS ALLOWED AND MUST STAY SO. A player with no price is not "unpriced", he is scored as
AVERAGE -- the market half of blend goes to 0.0 -- so freezing ADDs as well as CHANGEs would hand
every name a flaky scrape missed a permanent penalty.
"""
import argparse, json, math, os, re, sys, unicodedata
import subprocess as _sp
import numpy as np, pandas as pd
import nfl_stats

CFG = dict(
    WIN=None,            # set per-slate: NFL kickoff waves, see fixtures.json
    Z_GATE=0.55,
    GAME_CAP=5,
    ANCH=4, MOON_LEGS=3, MOONS_PER_ANC=2, ANCH_PER_GAME=2,
    MOON_RISK=2.0, SINGLE_STAKE=1.0,
)

# ---------------------------------------------------------------------------------------------
def norm(s):
    s = unicodedata.normalize('NFKD', str(s))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r'\b(jr|sr|ii|iii|iv|v)\b\.?', '', s.lower())
    return re.sub(r'[^a-z]', '', s)

def surname(s):
    parts = [p for p in re.sub(r'\b(Jr|Sr|II|III|IV|V)\b\.?', '', str(s)).split() if p]
    return norm(parts[-1]) if parts else ''

def frac_to_am(f):
    """Fractional -> American. 20/27 is odds-ON and must go negative, which is common on an
    anytime-TD card (a lead back at 4/5) and never happens on the soccer one."""
    n, d = f.split('/')
    n, d = float(n), float(d)
    if n >= d:
        return int(round(100 * n / d))
    return -int(round(100 * d / n))

def am_to_prob(a):
    return (100.0 / (a + 100.0)) if a > 0 else (abs(a) / (abs(a) + 100.0))

# ---------------------------------------------------------------------------------------------
def load_prices(atd_path, prices_path):
    """PRICEONCE merge. Existing entries are HELD; new names are appended. Returns
    (prices dict, n_new, n_held, n_would_move)."""
    prev = {}
    if prices_path and os.path.exists(prices_path):
        prev = json.load(open(prices_path, encoding='utf-8'))
    prices = dict(prev)
    new = held = would = 0
    for line in open(atd_path, encoding='utf-8'):
        line = line.rstrip('\n')
        if not line.strip():
            continue
        match, name, frac = line.split('|')
        am = frac_to_am(frac)
        key = f'{match}|{name}'
        if key not in prices:
            prices[key] = am
            new += 1
        else:
            if prices[key] != am:
                would += 1          # counted, NOT applied
            held += 1
    # PRICELEDGER-2026-09-04: the merge was computed and then THROWN AWAY. score() read
    # prices.json and never wrote it, which broke PRICEONCE at both ends. Loudly: the Publish
    # step's `cp .work/prices.json slates/<date>/prices.json` failed on the first build of every
    # slate, and runs 3 and 5 died there with a clean scorer, a clean draft and a clean fork
    # behind them. Quietly, and far worse: with nothing ever committed there is no prior ledger
    # to hold, so every build would have re-read atd.psv as gospel, `n_held` would have stayed 0
    # forever, and the doctrine the header of this file states -- "never CHANGED once set" --
    # would have been decoration. The dict IS the ledger; write it back where it was read from.
    if prices_path:
        json.dump(prices, open(prices_path, 'w', encoding='utf-8'), indent=1, sort_keys=True)
    return prices, new, held, would

def model_prob(df, model='nfl_model.json'):
    M = json.load(open(model))
    d = df.copy()
    d['x_tch'] = np.log1p(d.tchpg); d['x_i10'] = np.log1p(d.i10pg)
    d['x_shr'] = d.i10_share; d['x_imp'] = d.imp
    d['x_rz'] = d.rz_pg.fillna(d.rz_pg.median() if d.rz_pg.notna().any() else 4.0)
    for p in ['QB', 'RB', 'TE', 'WR']:
        d['p_' + p] = (d.pos == p).astype(float)
    X = d[M['feats']].astype(float)
    Z = (X - np.array(M['mu'])) / np.array(M['sd'])
    lin = Z.values @ np.array(M['coef']) + M['intercept']
    d['p_raw'] = 1 / (1 + np.exp(-lin))
    a, b = M['devig']
    d['exp_scorers'] = (a * d.imp + b).clip(lower=0.6)
    s = d.groupby('team').p_raw.transform('sum')
    d['p_model'] = (d.p_raw * d.exp_scorers / s.replace(0, np.nan)).clip(0.005, 0.90)
    return d

def wx_mult(row):
    """Measured WITHIN usage quartiles, outdoor only, 2021-2025:
       0-3mph -0.2pp | 3-7 +1.4 | 7-11 -0.0 | 11-15 -1.5 | 15+ -1.6 | indoor +1.4
       ⚠️ An earlier note claimed the windiest decile scored 18.0% vs 24.0%. That was NOT
       usage-controlled and overstated the effect ~4x. Wind is a trim, not a headline."""
    if row.indoor:
        return 1.014
    w = row.wind
    if w <= 3:  return 0.998
    if w <= 7:  return 1.014
    if w <= 11: return 1.000
    if w <= 15: return 0.985
    return 0.984

def score(season, week, atd_path, fixtures_path, prices_path):
    fx = json.load(open(fixtures_path, encoding='utf-8'))
    slugs = fx['matches']
    prices, n_new, n_held, n_would = load_prices(atd_path, prices_path)
    print(f'prices: {n_new} new, {n_held} held by PRICEONCE [{n_would} would have moved]')

    raw = nfl_stats.build(season, week)
    d = model_prob(raw)
    d['wf'] = d.apply(wx_mult, axis=1)
    d['p_model'] = (d.p_model * d.wf).clip(0.005, 0.90)

    # ---- join prices. Surname-anchored, same rule as soccer_teamnews.match_one -------------
    by_exact, by_sur = {}, {}
    for key, am in prices.items():
        m, nm = key.split('|', 1)
        by_exact.setdefault((m, norm(nm)), (nm, am))
        by_sur.setdefault((m, surname(nm)), []).append((nm, am))

    # a team plays in exactly one fixture on a Sunday slate
    team_slug = {}
    for slug, mm in slugs.items():
        team_slug[mm['home']] = slug
        team_slug[mm['away']] = slug
    d['match'] = d.team.map(team_slug)
    d = d[d.match.notna()].copy()

    odds, book = [], []
    for _, r in d.iterrows():
        k = (r.match, norm(r.full_name))
        hit = by_exact.get(k)
        if hit is None:
            cand = by_sur.get((r.match, surname(r.full_name)), [])
            hit = cand[0] if len(cand) == 1 else None
        odds.append(hit[1] if hit else None)
        book.append(hit[0] if hit else None)
    d['odds'] = odds
    d['book_name'] = book
    print(f'price join: {d.odds.notna().sum()}/{len(d)} rostered players priced')

    # ---- blend: half market, half edge -----------------------------------------------------
    d['p_mkt'] = d.odds.apply(lambda a: am_to_prob(a) if a is not None else np.nan)
    # de-vig the market the same way the model is normalised, so the two halves are comparable
    tot = d.groupby('team').p_mkt.transform('sum')
    d['p_mkt_dv'] = np.where(tot > 0, d.p_mkt * d.exp_scorers / tot, np.nan)

    def z(x):
        x = pd.to_numeric(x, errors='coerce')
        sd = x.std(ddof=0)
        return (x - x.mean()) / sd if sd and sd > 0 else x * 0.0

    priced = d[d.odds.notna()].copy()
    priced['mkt_z'] = z(priced.p_mkt_dv)
    # ⚠️ EDGE IS THE MODEL, NOT MODEL-MINUS-MARKET. The first cut used z(p_model - p_mkt_dv) and
    # the blend collapsed: TOTAL spanned 73.4-121.7 against ~120-200 on the baseball board,
    # because `edge` defined that way is mechanically ANTI-correlated with `mkt` -- a short price
    # raises mkt_z and lowers edge_z by construction, so the two halves of the blend cancel and
    # every player lands near 100. MLB's _SIG composite is the MODEL's own signals
    # (_zars/_zhh/_zla/_zdmg/_zpsw), scored independently of the price, and the blend then puts
    # equal weight on two views that disagree freely. Same here: the model's probability.
    priced['edge_z'] = z(priced.p_model)
    d = d.merge(priced[['full_name', 'match', 'mkt_z', 'edge_z']], on=['full_name', 'match'], how='left')
    # ⚠️ mkt_z 0.0 for an unpriced man is a VALUE, not "unknown" -- he scores as average.
    d['mkt_z'] = d.mkt_z.fillna(0.0)
    d['edge_z'] = d.edge_z.fillna(0.0)
    d['blend'] = 0.5 * d.mkt_z + 0.5 * d.edge_z
    d['TOTAL'] = ((100 + 30 * d.blend) * d.wf).round(1)
    d['gate_z'] = z(d.TOTAL)
    return d, fx

# ---------------------------------------------------------------------------------------------
def to_scored(d, fx):
    out = []
    for _, r in d.iterrows():
        if r.odds is None or (isinstance(r.odds, float) and math.isnan(r.odds)):
            continue                       # the board drafts from the priced field
        out.append(dict(
            name=r.full_name, match=r['match'], team=r.team, opp=r.opp, pos=r.pos,
            odds=int(r.odds), TOTAL=float(r.TOTAL), blend=float(r.blend),
            gate_z=float(r.gate_z), p_model=round(float(r.p_model), 4),
            p_mkt=round(float(r.p_mkt), 4) if pd.notna(r.p_mkt) else None,
            tchpg=round(float(r.tchpg), 2), i10pg=round(float(r.i10pg), 2),
            i10_share=round(float(r.i10_share), 3), imp=float(r.imp),
            rz_pg=round(float(r.rz_pg), 2) if pd.notna(r.rz_pg) else None,
            wf=round(float(r.wf), 3), wind=float(r.wind), indoor=int(r.indoor),
            basis=r.basis, basis_games=int(r.basis_games),
            out=False, void=False))
    out.sort(key=lambda x: -x['TOTAL'])
    return out

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('season', type=int); ap.add_argument('week', type=int)
    ap.add_argument('--atd', default='atd.psv')
    ap.add_argument('--fixtures', default='fixtures.json')
    ap.add_argument('--prices', default='prices.json')
    ap.add_argument('--out', default='scored.json')
    ap.add_argument('--no-draft', action='store_true')
    A = ap.parse_args()

    d, fx = score(A.season, A.week, A.atd, A.fixtures, A.prices)
    scored = to_scored(d, fx)
    json.dump(scored, open(A.out, 'w'), indent=1)
    print(f'scored.json: {len(scored)} priced players over {len({s["match"] for s in scored})} games')
    print(f'  TOTAL {min(s["TOTAL"] for s in scored):.1f} .. {max(s["TOTAL"] for s in scored):.1f}')
    for s in scored[:12]:
        print(f'   {s["name"][:22]:24}{s["pos"]:4}{s["team"]:4}{s["odds"]:+5d}  T={s["TOTAL"]:6.1f}  '
              f'model={s["p_model"]:.1%} mkt={(s["p_mkt"] or 0):.1%}  {s["basis"]}')
