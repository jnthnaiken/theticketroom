#!/usr/bin/env python3
"""THREES-2026-10-25 -- player threes made: model, opponent-by-position layer, and the three ticket styles.

    python3 analyze.py threes_odds.psv pbp_dir sd_dir out_dir

Owner: "lets look into adding 3pt made to basketball" -> "lets look at all 3 possibilites. also go deeper into the 3s
given up by opp team by looking at per position too".

DATA
  * play-by-play  shufinskiy/nba_data nbastatsv3_<y>.csv: every action with personId / teamTricode; a 3PA is
    isFieldGoal==1 and shotValue==3, made when shotResult=='Made'. A man "played" if he has any action.
  * dates / full names  shotdetail_<y>.csv: GAME_ID -> GAME_DATE, HTM, VTM; PLAYER_ID -> PLAYER_NAME.
  * prices  BettingPros market 162 (pull_bp162.js): date|event|home|visitor|bp_pid|name|pos|team|book|line|side|cost|main
  * position  BettingPros' player position (G / F / C), the only position source that covers every season here.

MODEL (walk-forward: every number for a game uses only earlier games)
  mu = att * pct * opp      threes made expected
    att  his 3PA per game played, EWMA (half-life 10 games), seeded from his own longer history
    pct  his 3P%, decayed makes/attempts (half-life 40 games) shrunk to the league rate with 150 phantom attempts
    opp  variant 'none' = 1; 'team' = opponent's 3PM allowed per game / league; 'pos' = opponent's 3PM allowed to HIS
         position per game / league for that position (each shrunk toward 1 by games seen); exponent beta fitted
  X ~ negative binomial(mean mu, dispersion r) -- r and beta fitted on the TRAIN season only (2023-24)
TICKETS (FanDuel price, book 10; best-of-books as a check), flat 1u singles / 0.10u round-robin pieces
  A overs   main-line overs, EV = p*dec - 1 >= t, one per game, cap n a night
  B ladders alternate overs at line >= 2.5 (3+ made) priced +150 or longer, best-EV rung per player, EV >= t
  C round robin  the night's top-4 overs from four different games, every 2-, 3- and 4-leg parlay at 0.10u (11 bets);
                 two flavours: top EV (value) and top probability (chalk, like Garrett's Temple)
Rules are CHOSEN on 2023-24 and REPORTED on 2024-25 and 2025-26 separately.
"""
import glob, gzip, itertools, json, math, os, re, sys, unicodedata
from collections import defaultdict
import numpy as np
import pandas as pd
from scipy.special import gammaln

ODDS, PBP, SD, OUT = sys.argv[1:5]
os.makedirs(OUT, exist_ok=True)
SEASON_OF = lambda d: int(d[:4]) if int(d[5:7]) >= 8 else int(d[:4]) - 1   # 2023-24 -> 2023
TRAIN, TESTS = 2023, (2024, 2025)
BPTEAM = {'UTH': 'UTA', 'NOR': 'NOP', 'NO': 'NOP', 'PHO': 'PHX', 'BRK': 'BKN', 'GS': 'GSW', 'NY': 'NYK', 'SA': 'SAS',
          'WSH': 'WAS', 'CHO': 'CHA'}


def norm(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r"[.'’\-]", ' ', s)
    w = [x for x in s.split() if x not in ('jr', 'sr', 'ii', 'iii', 'iv')]
    return ' '.join(w)


def say(*a):
    print(*a, flush=True)


# ------------------------------------------------------------------------------------------------ box: 3PA / 3PM
say('== loading play-by-play')
games, names = {}, {}
for f in sorted(glob.glob(os.path.join(SD, '**', 'shotdetail_*.csv'), recursive=True)):
    d = pd.read_csv(f, usecols=['GAME_ID', 'GAME_DATE', 'HTM', 'VTM', 'PLAYER_ID', 'PLAYER_NAME'], low_memory=False)
    g = d.drop_duplicates('GAME_ID')
    for gid, gd, h, v in zip(g.GAME_ID, g.GAME_DATE, g.HTM, g.VTM):
        s = str(int(gd)); games[int(gid)] = (f'{s[:4]}-{s[4:6]}-{s[6:]}', h, v)
    for pid, nm in d.drop_duplicates('PLAYER_ID')[['PLAYER_ID', 'PLAYER_NAME']].itertuples(index=False):
        names[int(pid)] = nm
def _clk(c):
    m = re.match(r'PT(\d+)M(\d+(?:\.\d+)?)S', str(c or ''))
    return int(m.group(1)) * 60 + float(m.group(2)) if m else None


def minutes_of(d):
    """ROLE-2026-10-26: minutes and starters from the substitution stream. A man is on the floor at a period's start if
    his first action of that period is anything but a sub-in; a sub-in/out opens/closes his stint; the period end
    closes everyone still on."""
    out = {}
    order = 'actionId' if 'actionId' in d else 'actionNumber'
    for (gid, per), g in d.sort_values(['gameId', 'period', order]).groupby(['gameId', 'period'], sort=False):
        plen = 720.0 if per <= 4 else 300.0
        first = {}
        for pid, at, st in zip(g.personId.values, g.actionType.values, g.subType.values):
            if pid > 0 and pid not in first: first[pid] = (str(at).lower() == 'substitution' and str(st).lower() == 'in')
        on = {pid: 0.0 for pid, subin in first.items() if not subin}
        if per == 1:
            for pid in on: out.setdefault((gid, pid), [0.0, True])[1] = True
        for pid, at, st, ck in zip(g.personId.values, g.actionType.values, g.subType.values, g.clock.values):
            if str(at).lower() != 'substitution' or pid <= 0: continue
            t = _clk(ck); el = plen - t if t is not None else None
            if el is None: continue
            if str(st).lower() == 'in': on[pid] = el
            elif str(st).lower() == 'out' and pid in on:
                out.setdefault((gid, pid), [0.0, False])[0] += max(0.0, el - on.pop(pid))
        for pid, t0 in on.items():
            out.setdefault((gid, pid), [0.0, False])[0] += max(0.0, plen - t0)
    return pd.DataFrame([(g, p, v[0] / 60.0, v[1]) for (g, p), v in out.items()], columns=['gameId', 'personId', 'mins', 'started'])


box = []   # gid, pid, team, att, made
for f in sorted(glob.glob(os.path.join(PBP, '**', 'nbastatsv3_*.csv'), recursive=True)):
    cols = pd.read_csv(f, nrows=0).columns
    want = [c for c in ('gameId', 'personId', 'teamTricode', 'isFieldGoal', 'shotValue', 'shotResult', 'description',
                        'period', 'clock', 'actionType', 'subType', 'actionId', 'actionNumber') if c in cols]
    d = pd.read_csv(f, usecols=want, low_memory=False)
    d = d[(d.personId > 0) & d.teamTricode.notna() & (d.teamTricode != '')]
    three = (d.shotValue == 3) if 'shotValue' in d else d.description.astype(str).str.contains('3PT')   # older files: no shotValue
    d['a3'] = ((d.isFieldGoal == 1) & three).astype(int)
    d['m3'] = (d.a3 == 1) & (d.shotResult == 'Made')
    agg = d.groupby(['gameId', 'personId']).agg(team=('teamTricode', 'first'), att=('a3', 'sum'), made=('m3', 'sum')).reset_index()
    if 'actionType' in d:
        sub = d[d.actionType.astype(str).str.lower() == 'substitution']
        say('     substitution rows', len(sub), 'subType', sub.subType.astype(str).value_counts().head(4).to_dict())
    mn = minutes_of(d)
    agg = agg.merge(mn, on=['gameId', 'personId'], how='left')
    agg['mins'] = agg.mins.fillna(0.0); agg['started'] = agg.started.fillna(False).astype(bool)
    say('     minutes: median', round(float(agg.mins.median()), 1), '| starters per game', round(float(agg.started.sum() / agg.gameId.nunique()), 2))
    box.append(agg)
    say('  ', os.path.basename(f), len(agg), 'player-games')
B = pd.concat(box, ignore_index=True)
B = B[B.gameId.isin(games)]
B['date'] = B.gameId.map(lambda g: games[g][0])
B['home'] = B.apply(lambda r: games[r.gameId][1] == r.team, axis=1)
B['opp'] = B.apply(lambda r: games[r.gameId][2] if games[r.gameId][1] == r.team else games[r.gameId][1], axis=1)
B = B.sort_values(['date', 'gameId']).reset_index(drop=True)
say('player-games', len(B), 'games', B.gameId.nunique(), 'dates', B.date.min(), '->', B.date.max())

# ------------------------------------------------------------------------------------------------ prices + positions
say('== loading prices')
op = gzip.open if ODDS.endswith('.gz') else open
O = pd.read_csv(ODDS, sep='|', header=None, quoting=3, low_memory=False,
                names=['date', 'event', 'home', 'visitor', 'bp', 'name', 'pos', 'team', 'book', 'line', 'side', 'cost', 'main'])
O = O[O.cost.abs() < 40000]
O['team'] = O.team.map(lambda t: BPTEAM.get(str(t), str(t)))
say('price rows', len(O), 'dates', O.date.nunique(), 'books', O.book.value_counts().head(8).to_dict())

# BP name -> personId (same date, same full name; else initial+surname unique among that date's players)
pg_by_date = defaultdict(list)
for r in B[['date', 'personId', 'team']].itertuples(index=False):
    pg_by_date[r.date].append((r.personId, r.team))
pos_of, pid_of = {}, {}
miss = 0
for (dt, nm), grp in O.groupby(['date', 'name']):
    cands = pg_by_date.get(dt, [])
    n = norm(nm)
    hit = [p for p, t in cands if norm(names.get(p, '')) == n]
    if not hit:
        sur, ini = n.split()[-1] if n else '', n[:1]
        hit = [p for p, t in cands if norm(names.get(p, '')).split()[-1:] == [sur] and norm(names.get(p, ''))[:1] == ini]
    if len(hit) == 1:
        pid_of[(dt, nm)] = hit[0]
        ps = str(grp.pos.iloc[0] or '').upper()
        if ps: pos_of[hit[0]] = 'C' if ps.startswith('C') else ('G' if (ps.startswith('G') or ps in ('PG', 'SG')) else 'F')
    else:
        miss += 1
O['pid'] = [pid_of.get(k) for k in zip(O.date, O.name)]
say('priced player-nights joined', len(pid_of), 'unjoined', miss, '| positions known for', len(pos_of), 'players')
B['pos'] = B.personId.map(pos_of).fillna('U')
cov = B[B.made > 0].groupby('pos').made.sum()
say('threes made by position bucket (known = BettingPros listed him at some point):', cov.to_dict())

# ------------------------------------------------------------------------------------------------ walk-forward features
say('== features')
HL_ATT, HL_PCT, HL_OPP, K_PCT = 10, 40, 15, 150.0
la, lb, lp = (lambda h: 0.5 ** (1 / h))(HL_ATT), (lambda h: 0.5 ** (1 / h))(HL_PCT), (lambda h: 0.5 ** (1 / h))(HL_OPP)
pl = defaultdict(lambda: {'a': 0.0, 'w': 0.0, 'pm': 0.0, 'pa': 0.0, 'n': 0})
league = {'m': 0.0, 'a': 0.0}
# opponent allowed: per team, decayed per-game 3PM allowed overall and by position
oa = defaultdict(lambda: {'all': 0.0, 'G': 0.0, 'F': 0.0, 'C': 0.0, 'w': 0.0, 'n': 0})
lg = {'all': 0.0, 'G': 0.0, 'F': 0.0, 'C': 0.0, 'w': 0.0}
feats = {}
rl = defaultdict(lambda: {'mS': 0.0, 'wS': 0.0, 'mL': 0.0, 'wL': 0.0, 'am': 0.0, 'mm': 0.0, 'sr': 0.0, 'ws': 0.0, 'team': None, 'tg': -99})
tgames = defaultdict(int)   # team -> games played so far
lS, lL, lM, lR = (lambda h: 0.5 ** (1 / h))(5), (lambda h: 0.5 ** (1 / h))(20), (lambda h: 0.5 ** (1 / h))(15), (lambda h: 0.5 ** (1 / h))(10)
for date, day in B.groupby('date', sort=True):
    # ROLE: who is missing tonight -- team regulars (>= 12 min a game recently, played in one of the team's last 3)
    # who are not in tonight's box, and how much of the team's three-point volume they take with them
    playing = set(zip(day.team, day.personId))
    miss = defaultdict(float); tot = defaultdict(float)
    for pid, q in rl.items():
        if q['team'] is None or q['wS'] == 0: continue
        if q['mS'] / q['wS'] < 12 or tgames[q['team']] - q['tg'] > 3: continue
        a = pl[pid]['a'] / pl[pid]['w'] if pl[pid]['w'] else 0.0
        tot[q['team']] += a
        if (q['team'], pid) not in playing: miss[q['team']] += a
    # 1) features for every player-game today, from state BEFORE today
    lp3 = (league['m'] / league['a']) if league['a'] > 50 else 0.36
    for r in day.itertuples(index=False):
        s = pl[r.personId]
        if s['n'] < 3: continue
        att = s['a'] / s['w']
        pct = (s['pm'] + K_PCT * lp3) / (s['pa'] + K_PCT)
        t = oa[r.opp]
        ft = fp = 1.0
        if t['w'] > 0 and lg['w'] > 0:
            ft = (t['all'] / t['w']) / (lg['all'] / lg['w'])
            ft = 1 + (ft - 1) * t['n'] / (t['n'] + 10)
            if r.pos in 'GFC' and lg[r.pos] > 0:
                fp = (t[r.pos] / t['w']) / (lg[r.pos] / lg['w'])
                fp = 1 + (fp - 1) * t['n'] / (t['n'] + 15)
            else:
                fp = ft
        q = rl[r.personId]
        mS = q['mS'] / q['wS'] if q['wS'] else 0.0
        mL = q['mL'] / q['wL'] if q['wL'] else mS
        srate = q['sr'] / q['ws'] if q['ws'] else 0.0
        msh = miss[r.team] / tot[r.team] if tot[r.team] > 0 else 0.0
        feats[(r.gameId, r.personId)] = (att, pct, ft, fp, s['n'], mS, mL, srate, float(r.started), msh)
    # 2) update state with today's results
    for r in day.itertuples(index=False):
        s = pl[r.personId]
        s['a'] = s['a'] * la + r.att; s['w'] = s['w'] * la + 1
        s['pm'] = s['pm'] * lb + r.made; s['pa'] = s['pa'] * lb + r.att; s['n'] += 1
        league['m'] = league['m'] * 0.9995 + r.made; league['a'] = league['a'] * 0.9995 + r.att
        q = rl[r.personId]
        q['mS'] = q['mS'] * lS + r.mins; q['wS'] = q['wS'] * lS + 1
        q['mL'] = q['mL'] * lL + r.mins; q['wL'] = q['wL'] * lL + 1
        q['sr'] = q['sr'] * lR + float(r.started); q['ws'] = q['ws'] * lR + 1
        q['team'] = r.team; q['tg'] = tgames[r.team] + 1
    for (gid, opp), grp in day.groupby(['gameId', 'opp']):
        t = oa[opp]
        for k in ('all', 'G', 'F', 'C'): t[k] *= lp
        t['w'] = t['w'] * lp + 1; t['n'] += 1
        t['all'] += grp.made.sum()
        for k in ('G', 'F', 'C'): t[k] += grp.made[grp.pos == k].sum()
    for t_ in set(day.team): tgames[t_] += 1
    ng = day.gameId.nunique() * 2
    for k in ('all', 'G', 'F', 'C'): lg[k] = lg[k] * 0.999 + day.made[(day.pos == k) if k != 'all' else slice(None)].sum()
    lg['w'] = lg['w'] * 0.999 + ng
B['f'] = [feats.get(k) for k in zip(B.gameId, B.personId)]
F = B[B.f.notna()].copy()
F[['att', 'pct', 'ft', 'fp', 'ng', 'mS', 'mL', 'srate', 'started', 'msh']] = pd.DataFrame(F.f.tolist(), index=F.index)
say('role features: median recent minutes', round(float(F.mS.median()), 1), '| games with a regular missing',
    round(float((F.msh > 0).mean()), 3), '| start flips', round(float((F.started - F.srate).abs().gt(0.5).mean()), 3))
F['season'] = F.date.map(SEASON_OF)
say('feature rows', len(F))


def nb_logpmf(k, mu, r):
    return gammaln(k + r) - gammaln(r) - gammaln(k + 1) + r * np.log(r / (r + mu)) + k * np.log(mu / (r + mu))


def nb_sf(kmin, mu, r):
    """P(X >= kmin)"""
    ks = np.arange(0, int(kmin))
    if len(ks) == 0: return np.ones_like(mu)
    cdf = sum(np.exp(nb_logpmf(k, mu, r)) for k in ks)
    return np.clip(1 - cdf, 1e-6, 1 - 1e-6)


ROLE = {'beta': 0.75, 'a1': 0.0, 'a2': 0.0, 'a3': 0.0}


def mu_of(df, variant, beta):
    base = df.att.values * df.pct.values
    if variant == 'none': return np.maximum(base, 0.02)
    if variant == 'role':   # ROLE-2026-10-26: minutes trend, start flip, teammates' missing three-point volume
        lm = np.log(np.clip((df.mS.values + 1) / (df.mL.values + 1), 0.2, 5))
        x = ROLE['a1'] * lm + ROLE['a2'] * (df.started.values - df.srate.values) + ROLE['a3'] * df.msh.values
        return np.maximum(base * np.power(np.clip(df.ft.values, 0.3, 3), ROLE['beta']) * np.exp(np.clip(x, -2, 2)), 0.02)
    f = df.ft.values if variant == 'team' else df.fp.values
    return np.maximum(base * np.power(np.clip(f, 0.3, 3), beta), 0.02)


# ------------------------------------------------------------------------------------------------ fit + positional study
say('== fit on', TRAIN, '(players with >= 1.0 3PA a game, the prop-eligible pool)')
pool = F[(F.att >= 1.0)]
tr = pool[pool.season == TRAIN]
fits = {}
for variant in ('none', 'team', 'pos'):
    best = None
    for beta in ([0.0] if variant == 'none' else [0.25, 0.5, 0.75, 1.0, 1.25, 1.5]):
        for r in (4, 6, 8, 12, 20, 40):
            ll = nb_logpmf(tr.made.values, mu_of(tr, variant, beta), r).mean()
            if best is None or ll > best[0]: best = (ll, beta, r)
    fits[variant] = best
    say(f'  {variant:5s} train loglik/game {best[0]:.5f}  beta {best[1]}  r {best[2]}')
from scipy.optimize import minimize
def _nll(x):
    ROLE.update(beta=x[0], a1=x[1], a2=x[2], a3=x[3])
    return -nb_logpmf(tr.made.values, mu_of(tr, 'role', 0), x[4]).mean()
opt = minimize(_nll, [fits['team'][1], 0.3, 0.3, 0.5, fits['team'][2]], method='Nelder-Mead',
               bounds=None, options={'maxiter': 600, 'xatol': 1e-3, 'fatol': 1e-6})
ROLE.update(beta=opt.x[0], a1=opt.x[1], a2=opt.x[2], a3=opt.x[3])
fits['role'] = (-opt.fun, float(opt.x[0]), float(max(opt.x[4], 1.0)))
say(f'  role  train loglik/game {-opt.fun:.5f}  beta {opt.x[0]:.2f}  minutes-trend {opt.x[1]:.2f}  start-flip {opt.x[2]:.2f}'
    f'  missing-teammates {opt.x[3]:.2f}  r {opt.x[4]:.1f}')
rep = {'fit': {k: dict(ll=v[0], beta=v[1], r=v[2]) for k, v in fits.items()}, 'role_coef': dict(ROLE)}
for ss in TESTS:
    te = pool[pool.season == ss]
    rep.setdefault('test_ll', {})[ss] = {v: float(nb_logpmf(te.made.values, mu_of(te, v, fits[v][1]), fits[v][2]).mean()) for v in fits}
    say(f'  test {ss}:', {k: round(x, 5) for k, x in rep['test_ll'][ss].items()})

# how real is "3s given up by position"? split-half stability and spread, per season
say('== opponent threes allowed by position')
pos_rows = []
for ss in sorted(F.season.unique()):
    S = B[(B.date.map(SEASON_OF) == ss) & B.pos.isin(['G', 'F', 'C'])]
    if S.empty: continue
    gm = S.groupby(['opp', 'pos', 'gameId']).made.sum().reset_index()
    gm['half'] = gm.gameId % 2
    piv = gm.groupby(['opp', 'pos', 'half']).made.mean().unstack('half')
    for p in ('G', 'F', 'C'):
        x = piv.xs(p, level='pos')
        if len(x) < 10: continue
        lgm = gm[gm.pos == p].made.mean()
        rel = (x.mean(axis=1) / lgm)
        stab = float(np.corrcoef(x[0], x[1])[0, 1]) if x.notna().all().all() else float('nan')
        pos_rows.append(dict(season=int(ss), pos=p, league_per_game=round(float(lgm), 3), spread_sd=round(float(rel.std()), 3),
                             best=rel.idxmin(), best_x=round(float(rel.min()), 2), worst=rel.idxmax(), worst_x=round(float(rel.max()), 2),
                             split_half_r=round(stab, 2)))
for r in pos_rows: say('  ', r)
rep['positional'] = pos_rows
# within a team: does position add beyond the team number? correlation of (pos rate / team rate) across halves
say('== does the POSITION split carry signal beyond the team total? (split-half r of pos-share-of-team-allowed)')
for ss in sorted(F.season.unique()):
    S = B[(B.date.map(SEASON_OF) == ss) & B.pos.isin(['G', 'F', 'C'])]
    if S.empty: continue
    g2 = S.groupby(['opp', 'pos', 'gameId']).made.sum().reset_index(); g2['half'] = g2.gameId % 2
    tot = g2.groupby(['opp', 'half']).made.sum()
    shr = g2.groupby(['opp', 'pos', 'half']).made.sum().div(tot).unstack('half')
    out = {}
    for p in ('G', 'F', 'C'):
        x = shr.xs(p, level='pos').dropna()
        if len(x) >= 10: out[p] = round(float(np.corrcoef(x[0], x[1])[0, 1]), 2)
    say('  ', ss, out); rep.setdefault('pos_share_r', {})[int(ss)] = out

# ------------------------------------------------------------------------------------------------ priced bets
say('== priced bets')
P = O[O.pid.notna()].copy()
P['pid'] = P.pid.astype(int)
gid_of = {(r.date, r.personId): (r.gameId, r.made) for r in F[['date', 'personId', 'gameId', 'made']].itertuples(index=False)}
P['gm'] = [gid_of.get(k) for k in zip(P.date, P.pid)]
P = P[P.gm.notna()].copy()           # no game row (DNP / no prior) -> the prop would void; dropped
P['gameId'] = P.gm.map(lambda x: x[0]); P['made'] = P.gm.map(lambda x: x[1])
P['season'] = P.date.map(SEASON_OF)
P['dec'] = np.where(P.cost > 0, 1 + P.cost / 100, 1 + 100 / P.cost.abs())
P = P[(P.side == 'O') & (P.book == 10)]   # FanDuel overs: the price we post and grade at
P['kmin'] = np.floor(P.line + 0.5).astype(int)          # over 1.5 -> 2+ made
P['win'] = P.made >= P.kmin
FF = F.set_index(['gameId', 'personId'])
Fx = FF.loc[list(zip(P.gameId, P.pid))]
for v in fits:
    beta, r = fits[v][1], fits[v][2]
    mu = mu_of(Fx, v, beta)
    pv = np.zeros(len(P))
    for k in np.unique(P.kmin.values):
        ix = P.kmin.values == k
        pv[ix] = nb_sf(k, mu[ix], r)
    P['p_' + v] = pv
say('priced over-rows', len(P), '| FanDuel rows', int((P.book == 10).sum()))


def settle(df, stake=1.0):
    return float((np.where(df.win, df.dec - 1, -1) * stake).sum())


def summary(df, label):
    out = {}
    for ss in [TRAIN] + list(TESTS):
        x = df[df.season == ss]
        if len(x) == 0: out[ss] = None; continue
        u = settle(x)
        out[ss] = dict(n=len(x), hit=round(float(x.win.mean()), 3), avg_price=round(float(x.dec.mean()), 2), units=round(u, 1), roi=round(u / len(x), 3))
    return out


def pick(df, pcol, t, cap, one_per_game=True, by='ev'):
    df = df.assign(ev=df[pcol] * df.dec - 1)
    df = df[df.ev >= t]
    df = df.sort_values('ev' if by == 'ev' else pcol, ascending=False)
    if one_per_game: df = df.drop_duplicates(['date', 'gameId'])
    if cap: df = df.groupby('date').head(cap)
    return df


results = {}
FD = P[P.book == 10]
main = FD[FD.main == 1]
# --- A. overs singles
say('== A. overs (main line), FanDuel price')
for v in fits:
    for t in (0.0, 0.05, 0.1, 0.15, 0.2, 0.3):
        for cap in (3, 5, 0):
            s = pick(main, 'p_' + v, t, cap)
            results[f'A|{v}|ev>={t}|cap{cap}'] = summary(s, '')
# --- B. ladders
say('== B. ladders (3+ made or more, +150 or longer), FanDuel price')
lad = FD[(FD.kmin >= 3) & (FD.dec >= 2.5)]
for v in fits:
    for t in (0.0, 0.1, 0.2, 0.3, 0.5):
        for cap in (3, 5, 0):
            s = lad.assign(ev=lad['p_' + v] * lad.dec - 1)
            s = s[s.ev >= t].sort_values('ev', ascending=False).drop_duplicates(['date', 'pid'])
            s = s.drop_duplicates(['date', 'gameId'])
            if cap: s = s.groupby('date').head(cap)
            results[f'B|{v}|ev>={t}|cap{cap}'] = summary(s, '')
# --- C. round robins (4 legs, 4 games, 11 x 0.10u)
say('== C. round robin of shooters (top 4 overs, 4 different games, 2s/3s/4 at 0.10u)')


def rr_units(legs):
    tot = 0.0
    for k in (2, 3, 4):
        for c in itertools.combinations(legs, k):
            tot += 0.1 * ((np.prod([d for d, w in c]) - 1) if all(w for d, w in c) else -1)
    return tot


for v in fits:
    for flavour in ('value', 'chalk'):
        for t in ((0.0, 0.1, 0.2) if flavour == 'value' else (-1.0,)):
            per = {}
            for (ss, dt), day in main.groupby(['season', 'date']):
                d = day.assign(ev=day['p_' + v] * day.dec - 1)
                d = d[d.ev >= t]
                d = d.sort_values('ev' if flavour == 'value' else 'p_' + v, ascending=False).drop_duplicates('gameId').head(4)
                if len(d) < 4: continue
                per.setdefault(ss, []).append(rr_units(list(zip(d.dec, d.win))))
            results[f'C|{v}|{flavour}|ev>={t}'] = {ss: (dict(nights=len(x), staked=round(1.1 * len(x), 1), units=round(sum(x), 1),
                                                         cashed=round(float(np.mean([u > 0 for u in x])), 3)) if x else None)
                                                    for ss, x in ((s_, per.get(s_)) for s_ in [TRAIN] + list(TESTS))}
rep['results'] = results


# choose on TRAIN, report on tests
def train_units(v):
    x = v.get(TRAIN) if isinstance(v, dict) else None
    return (x or {}).get('units', -1e9)


say('\n================ BEST RULES (chosen on 2023-24 units, then shown on 2024-25 and 2025-26) ================')
for style in ('A', 'B', 'C'):
    ks = sorted([k for k in results if k.startswith(style + '|')], key=lambda k: train_units(results[k]), reverse=True)[:6]
    for k in ks: say(f'{k:34s}', json.dumps(results[k]))
say('\n================ VARIANT HEAD-TO-HEAD (same rule, none vs team vs pos) ================')
for rule in ('A|{}|ev>=0.1|cap3', 'A|{}|ev>=0.2|cap5', 'A|{}|ev>=0.1|cap0', 'C|{}|value|ev>=0.1', 'C|{}|chalk|ev>=-1.0'):
    for v in fits:
        k = rule.format(v); say(f'{k:34s}', json.dumps(results.get(k)))
json.dump(rep, open(os.path.join(OUT, 'threes_report.json'), 'w'), indent=1, default=str)
say('\nwrote', os.path.join(OUT, 'threes_report.json'))
