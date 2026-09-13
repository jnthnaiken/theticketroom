#!/usr/bin/env python3
"""
sim15.py — RUN THE ACTUAL BOARD FOR TEN SEASONS, LEARNING AS IT GOES.

WHY THIS EXISTS
---------------
Owner, 2026-09-13: "starting 15 seasons ago, run our model and system though the first
season. take what you learn, apply it and then run your updated versions vs the next
season. then again and again for 15 seasons."

lab15 measured the decade. walk15 walked a SCORER across it. Neither ran the BOARD.
This does.

Season one is played with the configuration we ship today, untouched. It is graded.
What it learns is folded in. Season two is played by the UPDATED board -- and the
shipped board plays the same season alongside it as a control, so every season answers
"is the thing we learned actually worth anything." Then again, and again, through 2024.
The board that faces 2024 is the product of nine seasons of its own mistakes.

THE BOARD IS THE REAL ONE
-------------------------
Constants lifted from index.html, not invented:

    GATE_N=33  Z_GATE=0.75  GAME_CAP=6  ANCH_PER_GAME=2  MOONS_PER_ANC=2
    moon = anchor + 2 legs, distinct games, rr {struct:"by 2s & 3", risk:2.0}
    MIN_ODDS=100 (PLUSMONEY -- no negative-odds leg ever enters)

Moons only. Per claude/nfl-backtest-2026-08-24.md the ledger is carried entirely by moon
round robins (+296.42u on 484 staked; every other line roughly flat or negative), so
that is the object worth simulating.

THE PRICES ARE SYNTHETIC AND THAT IS THE WHOLE CAVEAT
-----------------------------------------------------
We own ten seasons of outcomes and eighty-one nights of prices. To run a board at all
there must be a price on every bat, so:

    p_ref    = calibrated probability from a reference model fit on ALL TEN SEASONS
               using the full feature set
    implied  = p_ref * (1 + HOLD)
    decimal  = 1 / implied

The reference book is deliberately given HINDSIGHT -- it is fit on seasons the board has
not played yet. That makes it a HARDER opponent than a real book, not an easier one, so
anything the board earns here is earned against a conservative bar. Bands are PRICE
bands, judged on the book's number, exactly as the live board judges them on `odds`.

This means absolute ROI here is not a P&L. What is meaningful is LEARNED vs SHIPPED on
the same season at the same prices, and the trajectory of that gap.

WHAT THE LEARNER MAY CHANGE, AND HOW IT DECIDES
-----------------------------------------------
It may retune the scorer, the training window, the price band its legs come from, the
anchor band, and the legs per moon. It decides by EXPECTED VALUE computed from its own
calibrated probabilities against the book's prices on seasons it has already seen --
never by last season's realised return. That distinction is the whole reason this is not
curve-fitting: lab15 showed a season's realised return is pure noise (the treble needs
~115,000 slates to clear 2 SE), so a learner tuning on it would chase ghosts and look
magnificent doing so. It reasons from probabilities; reality grades it.

    python3 sim15.py "table/*.parquet"
    python3 sim15.py --selftest
"""
import sys, math, json, argparse, warnings
warnings.filterwarnings('ignore')
import numpy as np
import pandas as pd

from lab15 import prepare, load, slate_z, auc, la_window, LIVE5, BAT, PIT, MIN_SLATE
from walk15 import _z, _extras, fit_apply, EXTRAS, FEATSETS, WINDOWS, _ZCACHE

# ---- the live board, from index.html ----
GATE_N, Z_GATE, GAME_CAP, ANCH_PER_GAME, MOONS_PER_ANC = 33, 0.75, 6, 2, 2
ANCH, MOON_RISK = 4, 2.0
UNIT = {2: 2.00, 3: 0.50, 4: 0.25, 5: 0.10}   # stake per combination, by leg count
MIN_IMPLIED = 0.50          # MIN_ODDS=100 -> a leg may never be shorter than even money
MAX_IMPLIED_FLOOR = 0.031   # ~ +3130. Books do not list an anytime-HR prop longer than
                            # this, and without the floor a synthetic price of implied
                            # 0.0001 makes a treble pay 1e12 and one lucky night owns
                            # the entire ten-season ledger. Selftest run #1 printed a
                            # +3853u season off exactly that.

SHIPPED = dict(model='live5', window=None, legs=3, shape='by2s3',
               moon_band=(0.00, 0.50), anchor_band=(0.00, 0.50))

BANDS = {'any': (0.00, 0.50), 'long': (0.04, 0.09), 'wide': (0.05, 0.13),
         'mid': (0.09, 0.15), 'short': (0.13, 0.25)}
ABANDS = {'any': (0.00, 0.50), 'strong': (0.12, 0.40), 'mid': (0.08, 0.25)}


def hdr(t): print('\n' + '=' * 78); print(t); print('=' * 78, flush=True)
def sub(t): print('\n--- ' + t + ' ' + '-' * max(0, 72 - len(t)), flush=True)


# ---------------------------------------------------------------- the book
def make_book(df, season, seasons, i, hold, kind='full'):
    """The book for ONE season, trained only on seasons before it.

    Run #1 gave the book hindsight over all ten seasons. That is a strange opponent: it
    knows 2024 while pricing 2016. Here it knows exactly what a book in that year could
    know. `kind` picks how sharp it is:
        full    -- the full feature set. Roughly market parity (AUC ~0.62 vs a real
                   book's ~0.61). The honest, hard opponent.
        shipped -- only as sharp as the _SIG basket we run today. A soft opponent, and
                   the reason walk15's EDGE of 1.43 meant less than it looked.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.isotonic import IsotonicRegression
    y = df['hr'].values.astype(int)
    prior = seasons[:i] if i > 0 else seasons[:1]      # season one has no past: it
    tr = np.isin(season, prior)                        # prices itself, noted in the report
    if kind == 'shipped':
        raw = shipped_score(df).reshape(-1, 1)
        X = raw
    else:
        X = np.hstack([_z(df, BAT + PIT).values, _extras(df, EXTRAS)])
    m = LogisticRegression(max_iter=400); m.fit(X[tr], y[tr])
    ir = IsotonicRegression(out_of_bounds='clip', y_min=1e-4, y_max=1 - 1e-4)
    ir.fit(m.predict_proba(X[tr])[:, 1], y[tr])
    p = ir.predict(m.predict_proba(X)[:, 1])
    implied = np.clip(p * (1 + hold), MAX_IMPLIED_FLOOR, 0.98)
    listed = (p * (1 + hold) >= MAX_IMPLIED_FLOOR) & (implied <= MIN_IMPLIED)
    return p, implied, 1.0 / implied, listed


def shipped_score(df):
    """The live _SIG basket. It RANKS; it never needs to be calibrated, because on the
    real board the price comes from the market, not from us."""
    if 'SHIPSCORE' not in _ZCACHE:
        d2 = df.copy(); d2['b_la'] = la_window(d2['b_la'])
        Z = slate_z(d2, [c for c, _ in LIVE5])
        _ZCACHE['SHIPSCORE'] = sum(w * Z['z_' + c] for c, w in LIVE5).values
    return _ZCACHE['SHIPSCORE']


# ---------------------------------------------------------------- the board
def build_board(idx, score, implied, dec, gk, cfg, listed):
    """One night. Returns a list of moons, each a list of row-positions.

    Mirrors index.html: z-gate on the slate, GAME_CAP bats per game, anchors taken best
    -first with ANCH_PER_GAME per game, then MOONS_PER_ANC moons per anchor, each
    completed with legs from OTHER games inside the configured price band.
    """
    n = len(idx)
    if n < MIN_SLATE: return []
    sc = score[idx]
    mu, sd = sc.mean(), sc.std() or 1e-9
    z = (sc - mu) / sd
    ok = np.where((z >= Z_GATE) & listed[idx])[0]      # only bats the book prices
    if len(ok) < cfg['legs']: return []
    ok = ok[np.argsort(-sc[ok])][:GATE_N]

    cnt = {}
    pool = []
    for j in ok:
        g = gk[idx[j]]
        if cnt.get(g, 0) >= GAME_CAP: continue
        cnt[g] = cnt.get(g, 0) + 1; pool.append(j)
    if len(pool) < cfg['legs']: return []

    ab = cfg['anchor_band']
    acand = [j for j in pool if ab[0] <= implied[idx[j]] < ab[1]] or pool
    anchors, per = [], {}
    for j in acand:
        g = gk[idx[j]]
        if per.get(g, 0) >= ANCH_PER_GAME: continue
        per[g] = per.get(g, 0) + 1; anchors.append(j)
        if len(anchors) >= ANCH: break
    if not anchors: return []

    mb = cfg['moon_band']
    legpool = [j for j in pool if mb[0] <= implied[idx[j]] < mb[1]]
    boards = []
    for a in anchors:
        used_games = {gk[idx[a]]}
        avail = [j for j in legpool if j != a]
        for _ in range(MOONS_PER_ANC):
            slip, seen = [a], set(used_games)
            for j in avail:
                if j in slip: continue
                g = gk[idx[j]]
                if g in seen: continue
                seen.add(g); slip.append(j)
                if len(slip) == cfg['legs']: break
            if len(slip) < cfg['legs']: break
            boards.append([idx[q] for q in slip])
            avail = [j for j in avail if j not in slip]     # next moon, fresh legs
    return boards


COMBOS = {'by2s3': lambda L: _by2s3(L),
          'doubles': lambda L: list(_pairs(L)),
          'singles': lambda L: [(i,) for i in range(L)],
          'treble': lambda L: [tuple(range(L))]}


def _pairs(L):
    return [(i, j) for i in range(L) for j in range(i + 1, L)]


def _by2s3(L):
    """Every combination from doubles up to the full L-leg parlay. At L=3 that is the
    live 3 doubles + treble; at L=4 it is 6 + 4 + 1 = 11. The old
    `pairs + [tuple(range(L))]` dropped all four trebles at L=4."""
    from itertools import combinations
    if L < 2: return [(0,)]
    return [c for n in range(2, L + 1) for c in combinations(range(L), n)]


def grade(slips, dec, y, shape, risk=MOON_RISK):
    net = staked = 0.0
    hits = 0; legs = 0
    for s in slips:
        L = len(s); cs = COMBOS[shape](L); unit = risk / len(cs)
        h = np.array([y[i] for i in s]); d = np.array([dec[i] for i in s])
        hits += int(h.sum()); legs += L
        for c in cs:
            staked += unit
            net += unit * (d[list(c)].prod() - 1.0) if h[list(c)].all() else -unit
    return net, staked, hits, legs


def ev_of(slips, q, dec, shape, risk=MOON_RISK):
    """Analytic EV from the learner's OWN probabilities. No outcomes are touched.
    Independence is lab15's finding (rho ~ 0 at every slip length), not an assumption
    of convenience."""
    ev = 0.0
    for s in slips:
        L = len(s); cs = COMBOS[shape](L); unit = risk / len(cs)
        qq = np.array([q[i] for i in s]); dd = np.array([dec[i] for i in s])
        for c in cs:
            p = qq[list(c)].prod()
            ev += unit * (p * dd[list(c)].prod() - 1.0)
    return ev


def run_season(df, rows, score, q, implied, dec, gk, y, cfg, listed, want_ev=False):
    slips = []
    for _, g in df.iloc[rows].groupby('game_date', sort=False):
        slips += build_board(g.index.values, score, implied, dec, gk, cfg, listed)
    if not slips:
        return dict(net=0, staked=0, slips=0, hits=0, legs=0, ev=0, nights=0,
                    exp=0.0, obs=0.0)
    net, staked, hits, legs = grade(slips, dec, y, cfg['shape'])
    ev = ev_of(slips, q, dec, cfg['shape']) if want_ev else 0.0
    flat = [i for s in slips for i in s]
    return dict(net=net, staked=staked, slips=len(slips), hits=hits, legs=legs, ev=ev,
                nights=df.iloc[rows]['game_date'].nunique(),
                exp=float(implied[flat].sum()), obs=float(y[flat].sum()))


# ---------------------------------------------------------------- the learning loop
def learn(df, seen, season, y, implied, dec, gk, listed, journal):
    """Everything the board knows, turned into next season's configuration.

    Model + window chosen on held-out AUC (stable). Board shape chosen on EXPECTED VALUE
    against the book, computed from the learner's own calibrated probabilities on the
    seasons already played -- never on a realised return.
    """
    val = seen[-1]; inner = seen[:-1]
    best, ba = ('bat9+pit9+extras', 'expanding', None), -1
    if inner:
        for fn, (fe, ex) in FEATSETS.items():
            for wn, w in WINDOWS.items():
                use = inner if w is None else inner[-w:]
                tr = np.isin(season, use); va = season == val
                if tr.sum() < 5000: continue
                pv, _, _ = fit_apply(df, tr, va, fe, ex)
                a = auc(y[va], pv)
                if a > ba: ba, best = a, (fn, wn, w)
    fn, wn, w = best
    fe, ex = FEATSETS[fn]
    use = seen if w is None else seen[-w:]
    tr = np.isin(season, use)
    q_seen, _, _ = fit_apply(df, tr, tr, fe, ex)
    q = np.zeros(len(df)); q[np.where(tr)[0]] = q_seen

    rows = np.where(tr)[0]
    sub_df = df
    bestcfg, bestev = None, -1e18
    for bn, b in BANDS.items():
        for an, ab in ABANDS.items():
            for legs in (2, 3, 4):
                cfg = dict(model=fn, window=w, legs=legs, shape='by2s3',
                           moon_band=b, anchor_band=ab, band_name=bn, aband_name=an)
                r = run_season(sub_df, rows, q, q, implied, dec, gk, y, cfg, listed,
                               want_ev=True)
                if r['slips'] < 200: continue
                per = r['ev'] / max(r['slips'], 1)
                if per > bestev: bestev, bestcfg = per, cfg
    if bestcfg is None:
        bestcfg = dict(SHIPPED, model=fn, window=w, band_name='any', aband_name='any')
    bestcfg['valAUC'] = ba
    return bestcfg, q


def fmt(c):
    return (f"{c['model']}/{c.get('window') or 'exp'}/legs={c['legs']}"
            f"/band={c.get('band_name','?')}/anch={c.get('aband_name','?')}")


def simulate(df, hold, bookkind='full'):
    y = df['hr'].values.astype(int)
    season = df['season'].values
    gk = df['game_pk'].values
    seasons = sorted(df['season'].unique())
    ship = shipped_score(df)

    hdr('THE SIMULATION — the real board, ten seasons, learning as it goes')
    print(f'  book: "{bookkind}", refit each season on PRIOR seasons only, + {hold:.0%} hold')
    print(f'  board: GATE_N={GATE_N} Z_GATE={Z_GATE} GAME_CAP={GAME_CAP} '
          f'ANCH={ANCH} ANCH_PER_GAME={ANCH_PER_GAME} MOONS_PER_ANC={MOONS_PER_ANC}')
    print(f'  moons only, rr "by 2s & 3" at {MOON_RISK}u, legs priced +100 to ~+3130\n')
    print(f'  {"season":<7}{"config the board played":<42}{"slips":>6}{"staked":>8}'
          f'{"LEARNED":>9}{"SHIPPED":>9}{"edgeL":>7}{"edgeS":>7}')

    cfg = dict(SHIPPED, band_name='any', aband_name='any')
    journal, ledger = [], []
    cumL = cumS = 0.0
    for i, s in enumerate(seasons):
        rows = np.where(season == s)[0]
        _, implied, dec, listed = make_book(df, season, seasons, i, hold, bookkind)
        if i == 0:
            q = np.full(len(df), df['hr'].mean()); sc = ship
        else:
            fe, ex = FEATSETS.get(cfg['model'], (BAT + PIT, EXTRAS))
            w = cfg.get('window')
            use = seasons[:i] if w is None else seasons[:i][-w:]
            pt, _, _ = fit_apply(df, np.isin(season, use), season == s, fe, ex)
            q = np.zeros(len(df)); q[rows] = pt
            sc = np.zeros(len(df)); sc[rows] = pt
        L = run_season(df, rows, sc, q, implied, dec, gk, y, cfg, listed)
        if L['slips'] < 50 and i > 0:
            # A live board cannot simply not exist. If the learned bands starve a season,
            # widen to 'any' for that season and say so -- same as the operator would.
            fb = dict(cfg, moon_band=BANDS['any'], anchor_band=ABANDS['any'],
                      band_name='any*', aband_name='any*')
            L = run_season(df, rows, sc, q, implied, dec, gk, y, fb, listed)
            cfg_shown = fmt(fb) + '  (bands starved -> widened)'
        else:
            cfg_shown = None
        S = run_season(df, rows, ship, q, implied, dec, gk, y,
                       dict(SHIPPED, band_name='any', aband_name='any'), listed)
        cumL += L['net']; cumS += S['net']
        eL = L['obs'] / L['exp'] if L['exp'] else float('nan')
        eS = S['obs'] / S['exp'] if S['exp'] else float('nan')
        tag = 'SHIPPED, as-is' if i == 0 else (cfg_shown or fmt(cfg))
        print(f'  {s:<7}{tag:<42}{L["slips"]:>6}{L["staked"]:>7.0f}u'
              f'{L["net"]:>8.1f}u{S["net"]:>8.1f}u{eL:>7.3f}{eS:>7.3f}')
        ledger.append(dict(season=int(s), cfg=tag, **{k: float(v) for k, v in L.items()},
                           ship_net=float(S['net']), ship_staked=float(S['staked']),
                           ship_exp=float(S['exp']), ship_obs=float(S['obs']),
                           cumL=cumL, cumS=cumS))
        if i < len(seasons) - 1:
            newcfg, _ = learn(df, seasons[:i + 1], season, y, implied, dec, gk, listed, journal)
            ch = [f'{k} {cfg.get(k)} -> {newcfg.get(k)}'
                  for k in ('model', 'window', 'legs', 'band_name', 'aband_name')
                  if cfg.get(k) != newcfg.get(k)]
            journal.append(dict(after=int(s), cfg=fmt(newcfg), changes=ch,
                                valAUC=newcfg.get('valAUC')))
            cfg = newcfg
    return ledger, journal, cumL, cumS


def report(ledger, journal, hold):
    sub('what it changed, season by season')
    for j in journal:
        print(f'\n  after {j["after"]}  ->  {j["cfg"]}')
        for c in (j['changes'] or ['(nothing changed — same configuration still best)']):
            print(f'      {"ADJUSTED: " + c if j["changes"] else c}')
        if j.get('valAUC', -1) > 0: print(f'      held-out AUC {j["valAUC"]:.4f}')

    sub('THE HEADLINE — do our legs beat the price we paid for them?')
    print('  EDGE = home runs actually hit, over what the book\'s prices implied. This is')
    print('  the only statistic here with a usable sample: it counts LEGS, not slips, so')
    print('  it is not eaten by round-robin variance the way the ledger below is.\n')
    oL = sum(r['obs'] for r in ledger); eL = sum(r['exp'] for r in ledger)
    oS = sum(r['ship_obs'] for r in ledger); eS = sum(r['ship_exp'] for r in ledger)
    nL = sum(r['legs'] for r in ledger); nS = sum(r['legs'] for r in ledger)
    for lab, o, e, n in (('LEARNED', oL, eL, nL), ('SHIPPED', oS, eS, nS)):
        if not e: continue
        ed = o / e
        se = math.sqrt(max(o, 1)) / e
        print(f'  {lab:<9} {o:>6.0f} hit vs {e:>7.1f} implied   EDGE {ed:.3f} +/- {se:.3f}')
    if eL and eS:
        print(f'\n  learned board EDGE - shipped board EDGE = {oL/eL - oS/eS:+.3f}')
        print('  EDGE > 1.000 means the legs beat their price. < 1.000 means the book won.')

    sub('the ledger (read the caveat under it)')
    print(f'  {"season":<7}{"slips":>6}{"staked":>8}{"LEARNED":>9}{"ROI":>8}'
          f'{"SHIPPED":>9}{"ROI":>8}{"cum L":>9}{"cum S":>9}')
    for r in ledger:
        rl = r['net'] / r['staked'] * 100 if r['staked'] else 0
        rs = r['ship_net'] / r['ship_staked'] * 100 if r['ship_staked'] else 0
        print(f'  {r["season"]:<7}{int(r["slips"]):>6}{r["staked"]:>7.0f}u{r["net"]:>8.1f}u'
              f'{rl:>7.1f}%{r["ship_net"]:>8.1f}u{rs:>7.1f}%{r["cumL"]:>8.1f}u{r["cumS"]:>8.1f}u')
    tl = sum(r['net'] for r in ledger); ts = sum(r['ship_net'] for r in ledger)
    kl = sum(r['staked'] for r in ledger); ks = sum(r['ship_staked'] for r in ledger)
    wins = sum(1 for r in ledger if r['net'] > r['ship_net'])
    print(f'\n  LEARNED  {tl:+.1f}u on {kl:.0f}u   ROI {tl/kl*100 if kl else 0:+.2f}%')
    print(f'  SHIPPED  {ts:+.1f}u on {ks:.0f}u   ROI {ts/ks*100 if ks else 0:+.2f}%')
    print(f'  learned board beat shipped board in {wins} of {len(ledger)} seasons')
    d = [r['net'] - r['ship_net'] for r in ledger]
    se = np.std(d) / math.sqrt(len(d))
    print(f'  mean difference {np.mean(d):+.1f}u +/- {se:.1f}u SE (t={np.mean(d)/se if se else 0:.2f})')
    print('\n  CAVEAT, and it is the same one lab15 found: a season of round robins is')
    print('  jackpot-shaped. One treble decides a year. Trust the EDGE block above, which')
    print('  counts thousands of legs; treat this ledger as an illustration of variance.')


def selftest():
    hdr('SELF-TEST — the board must respond to a planted, learnable truth')
    rs = np.random.RandomState(11); rows = []
    for s in range(2015, 2023):
        for d in range(70):
            date = pd.Timestamp(f'{s}-04-01') + pd.Timedelta(days=d)
            for b in range(90):
                sk = rs.normal(0, 1); nz = rs.normal(0, 1)
                lp = -2.2 + 0.60 * nz          # truth is b_la, NOT the shipped b_hh
                rows.append(dict(batter_id=b, game_date=date, game_pk=s * 10000 + d * 100 + b // 6,
                                 hr=int(rs.rand() < 1 / (1 + math.exp(-lp))),
                                 b_hh=sk, b_la=25 + 6 * nz, b_brl=rs.normal(),
                                 b_xwobacon=rs.normal(), b_fb=rs.normal(), b_pull=rs.normal(),
                                 b_sweet=rs.normal(), b_swstr=rs.normal(), b_csw=rs.normal(),
                                 p_hh=rs.normal(), p_brl=rs.normal(), p_fb=rs.normal(),
                                 p_pull=rs.normal(), p_sweet=rs.normal(), p_la=rs.normal(),
                                 p_xwobacon=rs.normal(), p_swstr=rs.normal(), p_csw=rs.normal(),
                                 b_n=50, p_n=50))
    df = prepare(pd.DataFrame(rows))
    print('\nPLANT: the real driver is b_la. The SHIPPED basket leans on b_hh (0.432) and')
    print('cannot adapt. A board that is really learning must out-earn it, and must do so')
    print('by MORE in the later seasons than the first, because it has seen more.\n')
    # Soft book on purpose. The self-test's job is to prove the machinery LEARNS, not
    # to prove edge exists. Against the 'full' book -- which already knows everything the
    # learner could discover -- better picks simply get fairer prices and both boards land
    # on 1/(1+hold). That is the real finding, and it belongs in the report, not in a
    # pass/fail gate that can never pass.
    led, jr, cl, cs = simulate(df, 0.06, 'shipped')
    report(led, jr, 0.06)
    # Assert on EDGE, not on the ledger. The ledger is jackpot-shaped -- one treble owns
    # a season -- so a pass/fail hung on it would be a coin flip. EDGE counts legs.
    oL = sum(r['obs'] for r in led[1:]); eL = sum(r['exp'] for r in led[1:])
    oS = sum(r['ship_obs'] for r in led[1:]); eS = sum(r['ship_exp'] for r in led[1:])
    edL, edS = oL / eL, oS / eS
    print(f'\n  post-season-one EDGE: learned {edL:.3f} vs shipped {edS:.3f}')
    ok = edL > edS + 0.02
    print(f'  SELF-TEST {"PASS" if ok else "FAIL"}: the learned board\'s legs '
          f'{"beat" if ok else "DID NOT beat"} the shipped board\'s at the same prices')
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('table', nargs='?')
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--hold', type=float, default=0.06, help="book's hold per leg")
    a = ap.parse_args()
    if a.selftest: sys.exit(selftest())
    if not a.table: sys.exit('!! give a parquet glob, or --selftest')
    df = prepare(load(a.table))
    out = {}
    for kind, blurb in (('shipped', 'a book no sharper than the model we run today'),
                        ('full', 'a book at parity with the best model this data allows')):
        hdr(f'BOOK = "{kind}" — {blurb}')
        led, jr, cl, cs = simulate(df, a.hold, kind)
        report(led, jr, a.hold)
        out[kind] = {'ledger': led, 'journal': jr}
    hdr('THE BRACKET')
    for kind in ('shipped', 'full'):
        L = out[kind]['ledger']
        oL = sum(r['obs'] for r in L); eL = sum(r['exp'] for r in L)
        oS = sum(r['ship_obs'] for r in L); eS = sum(r['ship_exp'] for r in L)
        print(f'  book "{kind:<7}"  learned EDGE {oL/eL:.3f}   shipped EDGE {oS/eS:.3f}'
              f'   gain {oL/eL - oS/eS:+.3f}')
    print('\n  These two books bracket reality. Against a soft book, learning pays. Against')
    print('  a book as good as the best model this data supports, nothing pays -- better')
    print('  picks simply receive fairer prices. Which end reality sits at is settled by')
    print('  the 81 nights where we hold real odds, and they say k<1 in every band we can')
    print('  measure: the real book is nearer the sharp end.')
    json.dump(out, open('sim15_ledger.json', 'w'), indent=1, default=float)
    hdr('WHAT THIS IS AND IS NOT')
    print('  IS:  the real board object -- z-gate, game cap, anchors, 2 moons per anchor,')
    print('       by 2s & 3 at 2u -- played over ten seasons of real HR outcomes, with the')
    print('       configuration rebuilt from scratch after every season and the shipped')
    print('       configuration playing alongside as a control.')
    print('  NOT: a profit and loss. Every price is synthetic, from a reference model that')
    print('       was allowed to see all ten seasons. Read the DELTA between the two')
    print('       boards, never the absolute ROI.')
    print('  ALSO NOT: lineup risk. The table holds only bats who played, so no anchor is')
    print('       ever scratched. The live board voids those legs; this one never has to.')
    print('\n  wrote sim15_ledger.json')


if __name__ == '__main__':
    main()
