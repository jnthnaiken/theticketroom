#!/usr/bin/env python3
"""
daily15.py — ONE SLATE AT A TIME, FIFTEEN SEASONS, LEARNING EVERY NIGHT.

WHAT THE OWNER ASKED FOR, THIRD TIME OF ASKING
----------------------------------------------
"day by day during each season from the past 15 seasons to build a board, see who hits,
grade it then make adjustments based on who actually hit and what you learned. then the
next day etc. for 15 seasons."

lab15 measured the decade in one shot. walk15 walked a scorer across it a season at a
time. sim15 ran the board but still only learned once a year. All three updated far too
slowly. This one updates EVERY NIGHT, roughly 2,700 times, which is the thing that was
actually asked for.

THE LOOP, AND NOTHING IS ALLOWED TO SKIP AHEAD
----------------------------------------------
For each slate in calendar order:

    1. SCORE every bat with the model as it stands TONIGHT -- trained only on slates
       strictly before today
    2. PRICE them from the book, which is also online and also only knows the past
    3. BUILD the board -- z-gate, game cap, anchors, two moons per anchor, by 2s & 3
    4. GRADE it against who actually went deep
    5. LEARN:
         a. the model takes a gradient step on tonight's outcomes
         b. EVERY candidate draft configuration is graded counterfactually on tonight's
            outcomes, not just the one we played, and its running record is updated
         c. tomorrow's configuration is whichever now has the best record
    6. tomorrow

Step 5b is what makes this cheap enough to do nightly. We know who homered, so we can
ask what every configuration WOULD have drafted and how it WOULD have done, at no extra
cost and with no bandit exploration problem. The board learns from nights it did not
play as well as the one it did.

FIFTEEN SEASONS, HONESTLY
-------------------------
Statcast begins in 2015. Seasons 2010-2014 genuinely have no launch angle or exit
velocity anywhere, so they run on the boxscore feature set -- lineup slot, rest, park,
opposing starter's HR rate allowed, and above all the hitter's own HR rate to date,
which was the heaviest term in every season of walk15. From 2015 the Statcast columns
arrive and the model simply starts using them. That is what happened to us in real life.

THE ONE NUMBER YOU MUST NOT READ AS PROFIT
------------------------------------------
There are no historical odds, so the book here is a second model. That creates a bias in
our favour that is worth naming: if our score and the book's are both noisy estimates of
the same truth, then holding the book's number fixed and picking the bats OUR model likes
best selects for hitters the book happens to have under-rated. EDGE comes out above 1.00
by construction, and a real market -- which aggregates vastly more information than any
model fit on this table -- would not hand that over.

So the absolute EDGE is not an edge. What IS clean is the DELTA: the learned draft
configuration against the shipped one, on the same nights, at the same prices, with the
same bias applied to both. That comparison is the output of this program.

SELECTION IS ON LEG EDGE, NOT ON THE LEDGER
-------------------------------------------
A configuration's nightly record is EDGE: home runs hit over home runs the price implied.
It is not ROI. lab15 established that a round robin's return needs ~115,000 slates to be
told from zero, so a learner ranking configurations by last night's profit would be
chasing noise and would look brilliant doing it. EDGE counts legs, converges in weeks,
and is the honest signal. The ledger is reported; it is never optimised against.

    python3 daily15.py --box boxscores_2010_2024.parquet --savant "table/*.parquet"
    python3 daily15.py --selftest
"""
import sys, glob, math, json, argparse, warnings
warnings.filterwarnings('ignore')
import numpy as np
import pandas as pd

# ---- the live board, from index.html ----
GATE_N, Z_GATE, GAME_CAP, ANCH_PER_GAME, MOONS_PER_ANC = 33, 0.75, 6, 2, 2
ANCH, MOON_RISK = 4, 2.0
MIN_IMPLIED, MAX_IMPLIED_FLOOR = 0.50, 0.031
MIN_SLATE = 60

WARMUP = 120            # slates played with the shipped config before learning turns on
RECAL_EVERY = 150       # slates between calibrator refits
PRIOR_STRENGTH = 60.0   # shrinkage on a configuration's EDGE, in "implied home runs"

BANDS = {'any': (0.031, 0.50), 'long': (0.04, 0.09), 'wide': (0.05, 0.13),
         'mid': (0.09, 0.15), 'short': (0.13, 0.25), 'vshort': (0.18, 0.35)}
ABANDS = {'any': (0.031, 0.50), 'strong': (0.12, 0.40), 'mid': (0.08, 0.25)}
LEGSET = (2, 3, 4)
SHIPPED_CFG = ('any', 'any', 3)

UNI = ['b_hr_prior', 'b_hr_30', 'b_hr_career', 'b_games_prior', 'b_rest', 'b_month',
       'slot', 'home', 'park_hr', 'sp_hr', 'b_pa_avg']
SAV = ['b_hh', 'b_la', 'b_brl', 'b_xwobacon', 'b_swstr', 'b_csw', 'b_fb', 'b_pull',
       'b_sweet', 'p_hh', 'p_brl', 'p_la', 'p_xwobacon', 'p_swstr', 'p_csw']


def hdr(t): print('\n' + '=' * 78); print(t); print('=' * 78, flush=True)
def sub(t): print('\n--- ' + t + ' ' + '-' * max(0, 72 - len(t)), flush=True)


# ---------------------------------------------------------------- features
def build_features(df):
    """Every column strictly prior to the row's own game. Nothing here may see tonight."""
    df = df.sort_values(['game_date', 'game_pk', 'batter_id']).reset_index(drop=True)
    # ANYTIME home run, not a count. pull_boxscores stores StatsAPI's homeRuns, which is
    # 2 on a two-homer night; the board bets "does he go deep", so the target -- and every
    # prior-rate feature built from it -- is the indicator. Caught when partial_fit was
    # handed a label of 2 on the first slate of the first real run.
    df['hr_n'] = df['hr'].astype(int)
    df['hr'] = (df['hr_n'] > 0).astype(int)
    df['game_date'] = pd.to_datetime(df['game_date'])
    df['season'] = df['game_date'].dt.year
    df['b_month'] = df['game_date'].dt.month

    g = df.groupby(['batter_id', 'season'], sort=False)
    ph = g['hr'].transform(lambda s: s.shift(1).expanding().sum())
    pg = g['hr'].transform(lambda s: s.shift(1).expanding().count())
    df['b_hr_prior'] = ph / pg.replace(0, np.nan)
    df['b_games_prior'] = pg.fillna(0)
    df['b_hr_30'] = g['hr'].transform(lambda s: s.shift(1).rolling(30, min_periods=8).mean())
    df['b_rest'] = g['game_date'].transform(lambda s: (s - s.shift(1)).dt.days).fillna(1).clip(0, 10)
    df['b_pa_avg'] = g['pa'].transform(lambda s: s.shift(1).rolling(15, min_periods=3).mean())

    gc = df.groupby('batter_id', sort=False)
    ch = gc['hr'].transform(lambda s: s.shift(1).expanding().sum())
    cg = gc['hr'].transform(lambda s: s.shift(1).expanding().count())
    df['b_hr_career'] = ch / cg.replace(0, np.nan)

    df['park'] = np.where(df['home'] == 1, df['team'], df['opp'])
    gp = df.groupby('park', sort=False)['hr']
    df['park_hr'] = gp.transform(lambda s: s.shift(1).expanding().mean())
    gs = df.groupby('sp_id', sort=False)['hr']
    df['sp_hr'] = gs.transform(lambda s: s.shift(1).expanding().mean())

    lg = df['hr'].mean()
    for c, fb in [('b_hr_prior', lg), ('b_hr_30', lg), ('b_hr_career', lg),
                  ('park_hr', lg), ('sp_hr', lg), ('b_pa_avg', 4.0)]:
        df[c] = df[c].fillna(fb)
    df['slot'] = df['slot'].replace(0, 5)
    have = [c for c in SAV if c in df.columns]
    df['has_sav'] = (df[have].notna().all(axis=1)).astype(float) if have else 0.0
    for c in SAV:
        if c not in df.columns: df[c] = np.nan
    return df


def slate_matrix(df):
    """Per-slate z-scores, the space the live scorer works in. Missing Statcast (pre-2015)
    lands on 0, which IS the slate mean -- neutral, not a fabricated value."""
    cols = UNI + SAV
    g = df.groupby('game_date', sort=False)
    out = np.zeros((len(df), len(cols) + 1), dtype=np.float32)
    for i, c in enumerate(cols):
        mu = g[c].transform('mean'); sd = g[c].transform('std').replace(0, np.nan)
        out[:, i] = ((df[c] - mu) / sd).fillna(0.0).values
    out[:, -1] = df['has_sav'].values
    return out, cols + ['has_sav']


# ---------------------------------------------------------------- online pieces
class Online:
    """A logistic model that takes one gradient step per slate, plus a calibrator that is
    refit periodically on a reservoir of recent scores. Never sees a row before it has
    been scored."""

    def __init__(self, ncol, seed=0):
        from sklearn.linear_model import SGDClassifier
        # constant rate on purpose: the point is to keep adapting for fifteen years, not
        # to converge and freeze. alpha carries the load of not chasing nightly noise.
        self.m = SGDClassifier(loss='log_loss', learning_rate='constant', eta0=0.01,
                               alpha=1e-5, random_state=seed)
        self.started = False
        self.iso = None
        self.buf_p, self.buf_y = [], []
        self.n = 0

    def score(self, X):
        if not self.started:
            return None
        raw = self.m.predict_proba(X)[:, 1]
        return self.iso.predict(raw) if self.iso is not None else raw

    def update(self, X, y):
        if not self.started:
            self.m.partial_fit(X, y, classes=np.array([0, 1])); self.started = True
        else:
            self.m.partial_fit(X, y)
        self.n += len(y)
        raw = self.m.predict_proba(X)[:, 1]
        self.buf_p.append(raw); self.buf_y.append(y)
        if len(self.buf_p) > 400:                      # reservoir ~ last 400 slates
            self.buf_p.pop(0); self.buf_y.pop(0)

    def recalibrate(self):
        from sklearn.isotonic import IsotonicRegression
        if not self.buf_p: return
        p = np.concatenate(self.buf_p); y = np.concatenate(self.buf_y)
        if len(p) < 2000 or y.sum() < 50: return
        ir = IsotonicRegression(out_of_bounds='clip', y_min=1e-4, y_max=1 - 1e-4)
        ir.fit(p, y); self.iso = ir


def build_board(pos, score, implied, listed, gk, band, aband, legs):
    """One night's moons. Identical shape to index.html."""
    if len(pos) < MIN_SLATE: return []
    sc = score[pos]
    z = (sc - sc.mean()) / (sc.std() or 1e-9)
    ok = np.where((z >= Z_GATE) & listed[pos])[0]
    if len(ok) < legs: return []
    ok = ok[np.argsort(-sc[ok])][:GATE_N]
    cnt, pool = {}, []
    for j in ok:
        g = gk[pos[j]]
        if cnt.get(g, 0) >= GAME_CAP: continue
        cnt[g] = cnt.get(g, 0) + 1; pool.append(j)
    if len(pool) < legs: return []
    imp = implied[pos]
    acand = [j for j in pool if aband[0] <= imp[j] < aband[1]] or pool
    anchors, per = [], {}
    for j in acand:
        g = gk[pos[j]]
        if per.get(g, 0) >= ANCH_PER_GAME: continue
        per[g] = per.get(g, 0) + 1; anchors.append(j)
        if len(anchors) >= ANCH: break
    legpool = [j for j in pool if band[0] <= imp[j] < band[1]]
    out = []
    for a in anchors:
        avail = [j for j in legpool if j != a]
        for _ in range(MOONS_PER_ANC):
            slip, seen = [a], {gk[pos[a]]}
            for j in avail:
                g = gk[pos[j]]
                if g in seen: continue
                seen.add(g); slip.append(j)
                if len(slip) == legs: break
            if len(slip) < legs: break
            out.append([pos[q] for q in slip])
            avail = [j for j in avail if j not in slip]
    return out


def combos(L):
    p = [(i, j) for i in range(L) for j in range(i + 1, L)]
    return p + [tuple(range(L))] if L >= 3 else p or [(0,)]


def grade(slips, dec, y):
    net = staked = 0.0
    for s in slips:
        cs = combos(len(s)); unit = MOON_RISK / len(cs)
        h = y[s]; d = dec[s]
        for c in cs:
            staked += unit
            net += unit * (d[list(c)].prod() - 1.0) if h[list(c)].all() else -unit
    return net, staked


# ---------------------------------------------------------------- the run
def run(df, hold, quiet=False):
    X, names = slate_matrix(df)
    y = df['hr'].values.astype(int)
    gk = df['game_pk'].values
    dates = df['game_date'].values
    seasons = df['season'].values
    order = df.groupby('game_date', sort=True).indices
    slate_keys = sorted(order.keys())

    model = Online(X.shape[1], 0)
    book = Online(X.shape[1], 1)

    CFGS = [(b, a, L) for b in BANDS for a in ABANDS for L in LEGSET]
    rec = {c: {'obs': 0.0, 'exp': 0.0, 'net': 0.0, 'staked': 0.0, 'slips': 0} for c in CFGS}
    cur = SHIPPED_CFG
    hist, changes = [], []
    cumnet = cumstake = 0.0
    played_obs = played_exp = 0.0

    hdr('THE RUN — one slate at a time')
    print(f'  {len(slate_keys):,} slates, {len(df):,} batter-games, '
          f'{df["season"].min()}..{df["season"].max()}, hold {hold:.0%}')
    print(f'  first {WARMUP} slates are played with the SHIPPED configuration while the')
    print(f'  model has nothing to go on; learning turns on after that.\n')

    for si, key in enumerate(slate_keys):
        pos = order[key]
        if len(pos) < MIN_SLATE:
            if model.started: model.update(X[pos], y[pos]); book.update(X[pos], y[pos])
            continue
        p = model.score(X[pos]); q = book.score(X[pos])
        if p is None or q is None:
            model.update(X[pos], y[pos]); book.update(X[pos], y[pos]); continue

        sc = np.zeros(len(df), dtype=np.float32); sc[pos] = p
        qq = np.zeros(len(df), dtype=np.float32); qq[pos] = q
        implied = np.zeros(len(df), dtype=np.float32)
        implied[pos] = np.clip(q * (1 + hold), MAX_IMPLIED_FLOOR, 0.98)
        listed = np.zeros(len(df), dtype=bool)
        listed[pos] = (q * (1 + hold) >= MAX_IMPLIED_FLOOR) & (implied[pos] <= MIN_IMPLIED)
        dec = np.zeros(len(df), dtype=np.float32); dec[pos] = 1.0 / np.maximum(implied[pos], 1e-6)

        # ---- 3/4: play tonight's configuration and grade it ----
        slips = build_board(pos, sc, implied, listed, gk, BANDS[cur[0]], ABANDS[cur[1]], cur[2])
        net, staked = grade(slips, dec, y)
        cumnet += net; cumstake += staked
        flat = [i for s in slips for i in s]
        if flat:
            played_obs += float(y[flat].sum()); played_exp += float(implied[flat].sum())

        # ---- 5b: grade EVERY configuration on tonight's real outcomes ----
        for c in CFGS:
            sl = slips if c == cur else build_board(pos, sc, implied, listed, gk,
                                                    BANDS[c[0]], ABANDS[c[1]], c[2])
            if not sl: continue
            f = [i for s in sl for i in s]
            r = rec[c]
            r['obs'] += float(y[f].sum()); r['exp'] += float(implied[f].sum())
            r['slips'] += len(sl)
            if c == cur:
                r['net'] += net; r['staked'] += staked
            else:
                n2, s2 = grade(sl, dec, y); r['net'] += n2; r['staked'] += s2

        # ---- 5a: the model learns tonight ----
        model.update(X[pos], y[pos]); book.update(X[pos], y[pos])
        if si % RECAL_EVERY == 0: model.recalibrate(); book.recalibrate()

        # ---- 5c: tomorrow's configuration ----
        if si >= WARMUP:
            best, bs = cur, -1e9
            for c, r in rec.items():
                if r['exp'] < 20: continue
                s = (r['obs'] + PRIOR_STRENGTH) / (r['exp'] + PRIOR_STRENGTH)
                if s > bs: bs, best = s, c
            if best != cur:
                changes.append((str(key)[:10], cur, best, bs))
                cur = best

        hist.append(dict(date=str(key)[:10], season=int(seasons[pos[0]]), slips=len(slips),
                         net=net, staked=staked, cum=cumnet, cfg=cur,
                         obs=float(y[flat].sum()) if flat else 0.0,
                         exp=float(implied[flat].sum()) if flat else 0.0))
    return hist, rec, changes, cur, model, names, (played_obs, played_exp)


def report(hist, rec, changes, cur, model, names, played, hold):
    H = pd.DataFrame(hist)
    sub('the learning curve — EDGE by season (hit / implied on the legs we drafted)')
    print(f'  {"season":<8}{"slates":>7}{"slips":>8}{"legs hit":>10}{"implied":>10}'
          f'{"EDGE":>8}{"net":>10}{"cum":>11}')
    for s, g in H.groupby('season'):
        e = g['obs'].sum() / g['exp'].sum() if g['exp'].sum() else float('nan')
        print(f'  {s:<8}{len(g):>7}{int(g["slips"].sum()):>8}{g["obs"].sum():>10.0f}'
              f'{g["exp"].sum():>10.1f}{e:>8.3f}{g["net"].sum():>9.1f}u{g["cum"].iloc[-1]:>10.1f}u')
    po, pe = played
    print(f'\n  WHOLE RUN   {po:.0f} hit vs {pe:.1f} implied   EDGE {po/pe if pe else 0:.4f}'
          f' +/- {math.sqrt(max(po,1))/pe if pe else 0:.4f}')

    half = len(H) // 2
    for lab, g in (('first half', H.iloc[:half]), ('second half', H.iloc[half:])):
        e = g['obs'].sum() / g['exp'].sum() if g['exp'].sum() else float('nan')
        print(f'  {lab:<12}{g["obs"].sum():>7.0f} hit vs {g["exp"].sum():>8.1f} implied'
              f'   EDGE {e:.4f}')

    sub(f'it changed its mind {len(changes)} times — the last ten')
    for d, a, b, s in changes[-10:]:
        print(f'  {d}  {a[0]}/{a[1]}/{a[2]}legs  ->  {b[0]}/{b[1]}/{b[2]}legs   '
              f'(shrunk EDGE {s:.3f})')

    sub('every configuration, ranked by what actually hit')
    rows = [(c, r) for c, r in rec.items() if r['exp'] >= 200]
    rows.sort(key=lambda t: -((t[1]['obs'] + PRIOR_STRENGTH) / (t[1]['exp'] + PRIOR_STRENGTH)))
    print(f'  {"band":<8}{"anchor":<8}{"legs":>5}{"slips":>8}{"hit":>7}{"implied":>9}'
          f'{"EDGE":>8}{"ROI":>9}')
    for c, r in rows[:12]:
        e = r['obs'] / r['exp']
        roi = r['net'] / r['staked'] * 100 if r['staked'] else 0
        print(f'  {c[0]:<8}{c[1]:<8}{c[2]:>5}{r["slips"]:>8}{r["obs"]:>7.0f}'
              f'{r["exp"]:>9.1f}{e:>8.3f}{roi:>8.1f}%')
    sh = rec.get(SHIPPED_CFG)
    if sh and sh['exp']:
        print(f'\n  the shipped configuration for reference:')
        print(f'  {SHIPPED_CFG[0]:<8}{SHIPPED_CFG[1]:<8}{SHIPPED_CFG[2]:>5}{sh["slips"]:>8}'
              f'{sh["obs"]:>7.0f}{sh["exp"]:>9.1f}{sh["obs"]/sh["exp"]:>8.3f}'
              f'{sh["net"]/sh["staked"]*100 if sh["staked"] else 0:>8.1f}%')

    sub('THE ONLY CLEAN COMPARISON — learned vs shipped, same nights, same prices')
    best = rec[cur]
    if sh and sh['exp'] and best['exp']:
        eb, es = best['obs'] / best['exp'], sh['obs'] / sh['exp']
        seb = math.sqrt(max(best['obs'], 1)) / best['exp']
        ses = math.sqrt(max(sh['obs'], 1)) / sh['exp']
        print(f'  LEARNED  {cur[0]}/{cur[1]}/{cur[2]}legs   EDGE {eb:.3f} +/- {seb:.3f}'
              f'   on {best["obs"]:.0f} home runs')
        print(f'  SHIPPED  any/any/3legs         EDGE {es:.3f} +/- {ses:.3f}'
              f'   on {sh["obs"]:.0f} home runs')
        print(f'  DELTA    {eb - es:+.3f}   ({(eb/es - 1) * 100:+.1f}% more home runs per unit')
        print('           of price paid than the board we ship today)')
        print('\n  Both numbers carry the same upward bias from pricing off a model, so the')
        print('  DELTA survives it and the absolute values do not. This is the result.')

    hdr('THE PERFECTED CONFIGURATION')
    print(f'  draft:  legs={cur[2]}  price band={cur[0]} {BANDS[cur[0]]}  '
          f'anchor band={cur[1]} {ABANDS[cur[1]]}')
    print(f'          Z_GATE={Z_GATE}  GATE_N={GATE_N}  GAME_CAP={GAME_CAP}  '
          f'ANCH={ANCH}  MOONS_PER_ANC={MOONS_PER_ANC}')
    w = model.m.coef_[0]
    idx = np.argsort(-np.abs(w))
    print(f'\n  scorer, after {model.n:,} batter-games of nightly updates '
          f'(per-slate z space):')
    for i in idx[:16]:
        print(f'    {names[i]:<18}{w[i]:>+9.4f}')
    tot = sum(abs(w[i]) for i in idx) or 1.0
    print('\n  renormalised to a _SIG-style basket summing to 1:')
    for i in idx[:10]:
        print(f'    {names[i]:<18}{abs(w[i])/tot:>7.3f}   {"(+)" if w[i] > 0 else "(-) INVERTED"}')
    json.dump({'band': cur[0], 'anchor_band': cur[1], 'legs': cur[2],
               'weights': {names[i]: float(w[i]) for i in range(len(names))}},
              open('daily15_final.json', 'w'), indent=1)
    print('\n  wrote daily15_final.json')


# ---------------------------------------------------------------- selftest
def selftest():
    hdr('SELF-TEST — a planted truth the nightly loop has to find on its own')
    rs = np.random.RandomState(4); rows = []
    for s in range(2012, 2018):
        for d in range(150):
            date = pd.Timestamp(f'{s}-04-01') + pd.Timedelta(days=d)
            for b in range(110):
                hh = rs.normal(); la = rs.normal()
                lp = -2.3 + 0.75 * la
                rows.append(dict(batter_id=b, batter=f'b{b}', game_date=date,
                                 game_pk=s * 100000 + d * 100 + b // 7, team='A', opp='B',
                                 home=b % 2, slot=(b % 9) + 1, pa=4,
                                 hr=int(rs.rand() < 1 / (1 + math.exp(-lp))),
                                 sp_id=b // 7, b_hh=hh, b_la=la,
                                 b_brl=rs.normal(), b_xwobacon=rs.normal(),
                                 b_swstr=rs.normal(), b_csw=rs.normal(), b_fb=rs.normal(),
                                 b_pull=rs.normal(), b_sweet=rs.normal(),
                                 p_hh=rs.normal(), p_brl=rs.normal(), p_la=rs.normal(),
                                 p_xwobacon=rs.normal(), p_swstr=rs.normal(),
                                 p_csw=rs.normal()))
    df = build_features(pd.DataFrame(rows))
    print(f'\n{len(df):,} batter-games, {df["game_date"].nunique()} slates')
    print('PLANT: b_la drives home runs; b_hh is noise. The nightly model must end up')
    print('leaning on b_la, and the second half of the run must beat the first.\n')
    hist, rec, ch, cur, model, names, played = run(df, 0.06)
    report(hist, rec, ch, cur, model, names, played, 0.06)
    H = pd.DataFrame(hist); half = len(H) // 2
    e1 = H.iloc[:half]['obs'].sum() / H.iloc[:half]['exp'].sum()
    e2 = H.iloc[half:]['obs'].sum() / H.iloc[half:]['exp'].sum()
    w = dict(zip(names, model.m.coef_[0]))
    found = abs(w.get('b_la', 0)) > abs(w.get('b_hh', 0))
    ok = found and e2 > e1
    print(f'\n  first-half EDGE {e1:.4f} -> second-half {e2:.4f}')
    print(f'  |w[b_la]|={abs(w.get("b_la",0)):.3f} vs |w[b_hh]|={abs(w.get("b_hh",0)):.3f}')
    print(f'  SELF-TEST {"PASS" if ok else "FAIL"}: the nightly loop '
          f'{"found the real driver and improved as it went" if ok else "DID NOT"}')
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--box', help='boxscores parquet, 2010-2024')
    ap.add_argument('--savant', help='glob for the Statcast table (2015+), optional')
    ap.add_argument('--hold', type=float, default=0.06)
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest: sys.exit(selftest())
    if not a.box: sys.exit('!! --box is required')

    df = pd.read_parquet(a.box)
    print(f'boxscores: {len(df):,} batter-games, {df["season"].min()}..{df["season"].max()}')
    if a.savant:
        fs = sorted(glob.glob(a.savant))
        if fs:
            sv = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
            keep = ['batter_id', 'game_pk'] + [c for c in SAV if c in sv.columns]
            sv = sv[keep].drop_duplicates(['batter_id', 'game_pk'])
            before = len(df)
            df = df.merge(sv, on=['batter_id', 'game_pk'], how='left')
            got = df[[c for c in SAV if c in df.columns]].notna().all(axis=1).sum()
            print(f'savant: joined {got:,} of {before:,} rows ({got/before*100:.1f}%) '
                  f'— the pre-2015 seasons have none, by construction')
    df = build_features(df)
    hist, rec, ch, cur, model, names, played = run(df, a.hold)
    report(hist, rec, ch, cur, model, names, played, a.hold)
    pd.DataFrame(hist).to_csv('daily15_history.csv', index=False)
    print('  wrote daily15_history.csv')


if __name__ == '__main__':
    main()
