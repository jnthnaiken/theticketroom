#!/usr/bin/env python3
"""nfl_longtd.py -- KINGEZ-2026-10-05. 👑 King of the End Zone: who scores the LONGEST touchdown of the game.

Owner, 2026-10-05: "draftkings does a thing called king of the end zone, the longest td of the game. everyone
that picks right splits 2mil in bonus bets" -> "lets add this section to the board. underneath first td".

A FREE PLAY, NOT A BET. Nothing here is staked, graded or folded into the ledger. It is information on the page,
exactly like baseball's Long Ball Jackpot drop-down whose slot it reuses (nfl_fork.py seam `sec-nightcap`).

THE CHANCE A MAN SCORES THE GAME'S LONGEST TOUCHDOWN, by simulation:
  * How OFTEN he scores: Poisson with lambda = -ln(1 - p), p = his anytime price de-vigged (DEVIG). The market,
    not our model -- this is a ranking of who scores and how far, and the price is the best single read of the
    first half of that.
  * How FAR each touchdown goes: 2023-2026 regular-season touchdowns (nflverse pbp, `yards_gained` on the
    scoring play). Half the draws come from the man's OWN touchdowns when he has >= OWN_MIN of them and his
    initial+surname key is unambiguous on this card (two "B. Robinson"s on ATL@NO share a key -> neither uses
    it); the rest from the league pool for his kind of score -- rushing for a RB (RB_RUSH of the time) or QB,
    receiving for everyone else. Measured 2023-26: the longest TD of a game is a catch 74% of the time, median
    ~29 yards; receiving TDs average 17 yards, rushing 9.
  * Ties split the credit, as the contest splits the pot.
Not modelled: D/ST and return touchdowns (~5% of TDs, unpriced), and the contest's own tie rules.
    python3 nfl_longtd.py scored.json [--pbp-dir .cache] [--out longtd.json]
Never fatal: writes nothing and exits 0 when it cannot run.
"""
import argparse, glob, json, math, os, re, sys, unicodedata
import numpy as np

N_SIMS = 40000
SEED = 20261005          # fixed, so every rebuild of a slate shows the same numbers
DEVIG = 1.08
OWN_MIN = 8
RB_RUSH, QB_RUSH, OTHER_RUSH = 0.80, 0.95, 0.03
TOP_N = 5
PBP_COLS = ['season_type', 'td_player_name', 'yards_gained', 'pass_touchdown', 'rush_touchdown']


def nm(s):
    return re.sub(r'[^a-z]', '', unicodedata.normalize('NFKD', str(s)).lower())


def pkey(name):
    t = [x for x in str(name).split() if x.rstrip('.') not in ('Jr', 'Sr', 'II', 'III', 'IV')]
    return nm(t[0][0] + t[-1]) if t else ''


def am2p(a):
    a = int(a)
    return 100 / (a + 100) if a > 0 else -a / (-a + 100)


def load_tds(pbp_dir):
    import pandas as pd
    fs = sorted(glob.glob(os.path.join(pbp_dir, 'pbp20*.csv.gz')))[-4:]
    if not fs:
        return None
    parts = []
    for f in fs:
        try:
            parts.append(pd.read_csv(f, usecols=lambda c: c in PBP_COLS, low_memory=False))
        except Exception as e:
            print(f'KINGEZ: skipped {f}: {e}')
    if not parts:
        return None
    P = pd.concat(parts)
    P = P[(P.season_type == 'REG') & ((P.pass_touchdown == 1) | (P.rush_touchdown == 1))]
    P = P[P.yards_gained.notna()]
    P['kind'] = np.where(P.rush_touchdown == 1, 'rush', 'rec')
    P['key'] = P.td_player_name.fillna('').map(lambda s: nm(s))
    return P


def simulate(rows, P, n=N_SIMS, seed=SEED):
    rng = np.random.default_rng(seed)
    pool = {k: P[P.kind == k].yards_gained.to_numpy(float) for k in ('rush', 'rec')}
    keys = [pkey(r['name']) for r in rows]
    win = np.zeros(len(rows))
    best = np.full(n, -1e9)
    draws = []
    for i, r in enumerate(rows):
        lam = -math.log(1 - min(am2p(r['odds']) / DEVIG, 0.95))
        k = rng.poisson(lam, n)
        tot = int(k.sum())
        rs = {'RB': RB_RUSH, 'QB': QB_RUSH}.get(r.get('pos'), OTHER_RUSH)
        y = np.where(rng.random(tot) < rs, rng.choice(pool['rush'], tot), rng.choice(pool['rec'], tot))
        own = P.yards_gained[P.key == keys[i]].to_numpy(float) if keys.count(keys[i]) == 1 else np.array([])
        if len(own) >= OWN_MIN:
            m = rng.random(tot) < 0.5
            y[m] = rng.choice(own, int(m.sum()))
        idx = np.repeat(np.arange(n), k)
        mx = np.full(n, -1e9)
        np.maximum.at(mx, idx, y)
        draws.append(mx)
        best = np.maximum(best, mx)
    D = np.vstack(draws)                          # players x sims: each man's longest TD (-1e9 = none)
    hit = (D == best) & (best > -1e8)
    share = hit / np.maximum(hit.sum(0), 1)
    win = share.sum(1) / n
    return win, float(np.median(best[best > -1e8])) if (best > -1e8).any() else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('scored'); ap.add_argument('--pbp-dir', default='.cache'); ap.add_argument('--out', default='longtd.json')
    A = ap.parse_args(argv)
    try:
        scored = json.load(open(A.scored, encoding='utf-8'))
        P = load_tds(A.pbp_dir)
        if P is None or len(P) < 500:
            print(f'KINGEZ: not enough touchdown history in {A.pbp_dir} -- no King of the End Zone this pass')
            return 0
        rows = [s for s in scored if s.get('odds') is not None and not s.get('out') and not s.get('void')]
        out = {}
        for m in sorted({r['match'] for r in rows}):
            rr = [r for r in rows if r['match'] == m]
            w, med = simulate(rr, P)
            top = sorted(zip(w, rr), key=lambda t: -t[0])[:TOP_N]
            picks = [dict(name=r['name'], team=r.get('team'), pos=r.get('pos'), odds=int(r['odds']),
                          p=round(float(x), 4), pop=round(am2p(r['odds']) / DEVIG, 4)) for x, r in top]
            # KINGEZ2-2026-10-05 -- owner: "if your pick was olave then it should be olave. take into account how many
            # people pick them". Winners SPLIT the pot, so what a pick is worth is P(longest) / how many others hold it.
            # Nobody publishes pick counts; the public picks the names it expects to score, so popularity is proxied by
            # the anytime chance (`pop`). The crown goes to the best P(longest)/pop among the TOP_N by P(longest) -- the
            # shortlist keeps a +3000 tight end with a 1% chance from winning on a tiny denominator.
            for pk in picks:
                pk['value'] = round(pk['p'] / pk['pop'], 4) if pk['pop'] else 0.0
            crown = max(picks, key=lambda pk: pk['value']) if picks else None
            for pk in picks:
                pk['crown'] = pk is crown
            picks.sort(key=lambda pk: (not pk['crown'], -pk['p']))
            out[m] = dict(match=m, median_yards=med, n_tds=int(len(P)), picks=picks)
            print(f"KINGEZ {m}: " + ', '.join(f"{'*' if p['crown'] else ''}{p['name']} {p['p']:.1%} (value {p['value']:.2f})" for p in out[m]['picks']))
        json.dump(out, open(A.out, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    except Exception as e:
        print(f'::warning::nfl_longtd.py failed ({e.__class__.__name__}: {e}) -- no King of the End Zone this pass')
    return 0


main_args = main


if __name__ == '__main__':
    sys.exit(main())
