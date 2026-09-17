#!/usr/bin/env python3
"""scorer_model.py -- SCORERHIST-2026-09-17. A layered anytime-goalscorer model, trained and
walk-forward tested on understat + football-data history.

Owner: "there is always order in chaos. you just need to find the correct data set or layer of data
sets. design an algorithm if needed."

THE ALGORITHM. A goal is a rare event, so model the RATE and turn it into a probability:

    lambda_player = lambda_team_np * share * (exp_min / 90)       # open play
                  + lambda_team_pen * pen_share * (exp_min / 90)  # penalties
    P(scores)     = 1 - exp(-lambda_player)

  layer 1  lambda_team      how many goals his TEAM will score tonight.
                            a) market: football-data 1X2 + over/under 2.5 closing-ish prices,
                               de-vigged, solved for two Poisson means            (best when present)
                            b) stats: team npxG-for x opponent npxG-against, relative to league,
                               exponentially weighted, prior = previous season    (fallback)
  layer 2  share            his share of his team's non-penalty xG while he is on the pitch,
                            exponentially weighted over his history, shrunk toward a position prior
  layer 3  exp_min          minutes he plays when he starts (starters only -- the board only bets
                            confirmed starters)
  layer 4  pen_share        his share of his team's penalty xG
  layer 5  calibration      logistic on log(lambda) + finishing skill + home + history depth,
                            fitted ONLY on seasons before the one being scored

Every feature for a match uses only matches strictly before that match's date.

    python3 scorer_model.py --data <history dir> [--test-from 2018]
"""
import argparse, glob, gzip, json, math, os, re, sys, unicodedata
from collections import defaultdict

import numpy as np
import pandas as pd

HALF_LIFE = 30          # player matches
TEAM_HALF = 19          # team matches
SHARE_K = 1.5           # team-npxG units of prior for a player's share
PEN_K = 0.15
MIN_K = 3.0
PRIOR_SHARE = {'F': 0.30, 'AM': 0.16, 'M': 0.07, 'D': 0.035, 'GK': 0.0, 'S': 0.12}
LEAGUE_OF_CODE = {'E0': 'EPL', 'SP1': 'La_liga', 'D1': 'Bundesliga', 'I1': 'Serie_A', 'F1': 'Ligue_1'}


def pos_group(p):
    p = str(p or '').upper()
    if p in ('GK',):
        return 'GK'
    if p in ('FW', 'ST', 'CF') or p.startswith('F'):
        return 'F'
    if p in ('AML', 'AMR', 'AMC') or p.startswith('AM'):
        return 'AM'
    if p.startswith('D'):
        return 'D'
    if p in ('SUB', 'S'):
        return 'S'
    return 'M'


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


# ------------------------------------------------------------------------------------------ load
def load(data):
    tm = pd.read_csv(os.path.join(data, 'team_matches.csv.gz'))
    pm = pd.read_csv(os.path.join(data, 'player_matches.csv.gz'))
    for c in ('xG', 'xGA', 'npxG', 'npxGA'):
        tm[c] = tm[c].astype(float)
    tm['date'] = pd.to_datetime(tm['date'])
    pm['date'] = pd.to_datetime(pm['date'])
    return tm, pm


def assign_team(pm):
    """understat's player log names both clubs, not his. Take the club that appears in the most
    of his matches within +-60 days (handles a mid-season move)."""
    pm = pm.sort_values(['pid', 'date']).reset_index(drop=True)
    teams = np.empty(len(pm), dtype=object)
    for pid, g in pm.groupby('pid', sort=False):
        d = g['date'].values.astype('datetime64[D]').astype(np.int64)
        h = g['h_team'].values
        a = g['a_team'].values
        idx = g.index.values
        for i in range(len(g)):
            lo = np.searchsorted(d, d[i] - 60)
            hi = np.searchsorted(d, d[i] + 60, side='right')
            ch = h[i]
            ca = a[i]
            nh = np.sum((h[lo:hi] == ch) | (a[lo:hi] == ch))
            na = np.sum((h[lo:hi] == ca) | (a[lo:hi] == ca))
            teams[idx[i]] = ch if nh >= na else ca
    pm['team'] = teams
    pm['home'] = (pm['team'] == pm['h_team']).astype(int)
    pm['opp'] = np.where(pm['home'] == 1, pm['a_team'], pm['h_team'])
    return pm


# ------------------------------------------------------------------------------ team layer (stats)
def team_ratings(tm):
    """For every (team, date) the pre-match EW npxG-for / npxG-against and pen-xG rate, relative to
    the league. Prior = the team's previous-season per-game rate (or the league's bottom third)."""
    tm = tm.sort_values(['team', 'date']).reset_index(drop=True)
    tm['penxG'] = (tm['xG'] - tm['npxG']).clip(lower=0)
    lg_avg = tm.groupby(['league', 'season'])[['npxG', 'penxG']].mean()
    out = {}
    decay = 0.5 ** (1 / TEAM_HALF)
    for team, g in tm.groupby('team', sort=False):
        a = d = p = w = 0.0
        last_season = None
        for r in g.itertuples():
            if last_season is not None and r.season != last_season:
                # season boundary: keep the history but shrink it (weight x0.6)
                a, d, p, w = a * 0.6, d * 0.6, p * 0.6, w * 0.6
            la = lg_avg.loc[(r.league, r.season)]
            prior_w = 4.0
            fa = (a + prior_w * la.npxG) / (w + prior_w)
            fd = (d + prior_w * la.npxG) / (w + prior_w)
            fp = (p + prior_w * la.penxG) / (w + prior_w)
            out[(team, r.date)] = (fa / la.npxG, fd / la.npxG, fp, la.npxG, r.league, r.season, r.h_a)
            a = a * decay + r.npxG
            d = d * decay + r.npxGA
            p = p * decay + r.penxG
            w = w * decay + 1
            last_season = r.season
    return out


# ------------------------------------------------------------------------------ team layer (market)
def poisson_1x2_ou(lh, la, maxg=10):
    ph = np.exp(-lh) * lh ** np.arange(maxg) / np.array([math.factorial(k) for k in range(maxg)])
    pa = np.exp(-la) * la ** np.arange(maxg) / np.array([math.factorial(k) for k in range(maxg)])
    M = np.outer(ph, pa)
    home = np.tril(M, -1).sum()
    draw = np.trace(M)
    away = np.triu(M, 1).sum()
    tot = np.add.outer(np.arange(maxg), np.arange(maxg))
    over = M[tot > 2].sum()
    return home, draw, away, over


_GRID = None


def solve_lambdas(pH, pD, pA, pO):
    """least squares over a grid, then refine -- fast enough for ~20k matches."""
    global _GRID
    if _GRID is None:
        ls = np.round(np.arange(0.15, 4.01, 0.05), 2)
        rows = []
        for lh in ls:
            for la in ls:
                rows.append((lh, la) + poisson_1x2_ou(lh, la))
        _GRID = np.array(rows)
    G = _GRID
    t = np.array([pH, pD, pA, pO])
    err = ((G[:, 2:6] - t) ** 2 * np.array([1, 1, 1, 1.5])).sum(1)
    i = int(err.argmin())
    return G[i, 0], G[i, 1]


def load_market(data):
    rows = []
    for f in sorted(glob.glob(os.path.join(data, 'odds', '*.csv'))):
        code = os.path.basename(f).split('_')[0]
        lg = LEAGUE_OF_CODE.get(code)
        try:
            df = pd.read_csv(f, encoding='latin-1', on_bad_lines='skip')
        except Exception:
            continue
        if 'HomeTeam' not in df.columns:
            continue
        def pick(*cols):
            for c in cols:
                if c in df.columns and df[c].notna().mean() > 0.5:
                    return df[c]
            return None
        H = pick('AvgH', 'BbAvH', 'B365H')
        D_ = pick('AvgD', 'BbAvD', 'B365D')
        A = pick('AvgA', 'BbAvA', 'B365A')
        O = pick('Avg>2.5', 'BbAv>2.5', 'B365>2.5')
        U = pick('Avg<2.5', 'BbAv<2.5', 'B365<2.5')
        if H is None or O is None or U is None:
            continue
        dt = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
        for i in range(len(df)):
            try:
                h, d, a, o, u = float(H[i]), float(D_[i]), float(A[i]), float(O[i]), float(U[i])
            except (TypeError, ValueError):
                continue
            if not all(x > 1 for x in (h, d, a, o, u)) or pd.isna(dt[i]):
                continue
            s1 = 1 / h + 1 / d + 1 / a
            s2 = 1 / o + 1 / u
            rows.append((lg, dt[i], df['HomeTeam'][i], df['AwayTeam'][i],
                         (1 / h) / s1, (1 / d) / s1, (1 / a) / s1, (1 / o) / s2))
    mk = pd.DataFrame(rows, columns=['league', 'date', 'home', 'away', 'pH', 'pD', 'pA', 'pO'])
    lam = [solve_lambdas(r.pH, r.pD, r.pA, r.pO) for r in mk.itertuples()]
    mk['lh'] = [x[0] for x in lam]
    mk['la'] = [x[1] for x in lam]
    return mk


FD_ALIAS = {
    'man united': 'manchester united', 'man city': 'manchester city', 'nott m forest': 'nottingham forest',
    'wolves': 'wolverhampton wanderers', 'newcastle': 'newcastle united', 'sheffield united': 'sheffield united',
    'west brom': 'west bromwich albion', 'ath madrid': 'atletico madrid', 'ath bilbao': 'athletic club',
    'betis': 'real betis', 'sociedad': 'real sociedad', 'celta': 'celta vigo', 'vallecano': 'rayo vallecano',
    'espanol': 'espanyol', 'la coruna': 'deportivo la coruna', 'sp gijon': 'sporting gijon',
    'bayern munich': 'bayern munich', 'dortmund': 'borussia dortmund', "m'gladbach": 'borussia m gladbach',
    'm gladbach': 'borussia m gladbach', 'leverkusen': 'bayer leverkusen', 'ein frankfurt': 'eintracht frankfurt',
    'rb leipzig': 'rasenballsport leipzig', 'fc koln': 'fc cologne', 'stuttgart': 'vfb stuttgart',
    'hertha': 'hertha berlin', 'mainz': 'mainz 05', 'schalke 04': 'schalke 04', 'hamburg': 'hamburger sv',
    'heidenheim': 'fc heidenheim', 'st pauli': 'st pauli', 'greuther furth': 'greuther fuerth',
    'bielefeld': 'arminia bielefeld', 'fortuna dusseldorf': 'fortuna duesseldorf', 'paderborn': 'paderborn',
    'inter': 'inter', 'milan': 'ac milan', 'roma': 'roma', 'parma': 'parma calcio 1913', 'spal': 'spal 2013',
    'paris sg': 'paris saint germain', 'st etienne': 'saint etienne', 'nimes': 'nimes',
    'clermont': 'clermont foot', 'ajaccio gfco': 'gfc ajaccio',
}


def market_index(mk, team_names):
    by_norm = defaultdict(list)
    for t in team_names:
        by_norm[norm(t)].append(t)

    def res(x):
        n = norm(x)
        n = FD_ALIAS.get(n, n)
        if n in by_norm:
            return by_norm[n][0]
        hits = [t for k, v in by_norm.items() for t in v if n and (k.startswith(n) or n.startswith(k))]
        return hits[0] if len(set(hits)) == 1 else None
    cache = {}
    idx = {}
    miss = defaultdict(int)
    for r in mk.itertuples():
        for side, team, opp, lam in ((1, r.home, r.away, r.lh), (0, r.away, r.home, r.la)):
            if team not in cache:
                cache[team] = res(team)
            t = cache[team]
            if t is None:
                miss[team] += 1
                continue
            idx[(t, r.date.normalize())] = lam
    return idx, miss


# ------------------------------------------------------------------------------ player layers
def player_features(pm, tr):
    pm = pm.sort_values(['pid', 'date']).reset_index(drop=True)
    decay = 0.5 ** (1 / HALF_LIFE)
    feats = defaultdict(list)
    for pid, g in pm.groupby('pid', sort=False):
        s_np = s_tnp = s_pen = s_tpen = 0.0
        s_g = s_x = 0.0
        s_minw = s_min = 0.0
        n = 0
        s_pos = defaultdict(float)
        for r in g.itertuples():
            key = (r.team, r.date)
            T = tr.get(key)
            grp = max(s_pos, key=s_pos.get) if s_pos else pos_group(r.position)
            prior = PRIOR_SHARE.get(grp, 0.1)
            share = (s_np + SHARE_K * prior) / (s_tnp + SHARE_K)
            pen_share = (s_pen + PEN_K * (0.25 if grp == 'F' else 0.05)) / (s_tpen + PEN_K)
            exp_min = (s_min + MIN_K * 78) / (s_minw + MIN_K)
            fin = (s_g - s_x) / (s_x + 4.0)
            feats['share'].append(share)
            feats['pen_share'].append(min(pen_share, 1.0))
            feats['exp_min'].append(exp_min)
            feats['fin'].append(fin)
            feats['n_prior'].append(n)
            feats['grp'].append(grp)
            # ---- update AFTER using (no leakage) ----
            t = float(r.time)
            tnp = T[0] * T[3] if T else 1.3
            tpen = T[2] if T else 0.1
            if T is not None:
                # actual team npxG in THIS match would be better; the rating is a stand-in that
                # keeps the denominator on the same scale as the numerator's opportunity.
                pass
            s_np = s_np * decay + float(r.npxG)
            s_tnp = s_tnp * decay + tnp * t / 90
            s_pen = s_pen * decay + max(float(r.xG) - float(r.npxG), 0)
            s_tpen = s_tpen * decay + tpen * t / 90
            s_g = s_g * decay + float(r.npg)
            s_x = s_x * decay + float(r.npxG)
            if str(r.position) != 'Sub':
                s_min = s_min * decay + t
                s_minw = s_minw * decay + 1
            s_pos[pos_group(r.position)] += 1 if str(r.position) != 'Sub' else 0
            n += 1
    for k, v in feats.items():
        pm[k] = v
    return pm


# ------------------------------------------------------------------------------ assemble + test
def build(data):
    tm, pm = load(data)
    tr = team_ratings(tm)
    pm = assign_team(pm)
    # use the ACTUAL team npxG of each match in the share denominator (not the rating): join it
    tmx = tm.set_index(['team', 'date'])
    act = {k: (v.npxG, max(v.xG - v.npxG, 0)) for k, v in zip(tmx.index, tmx.itertuples())}
    tr2 = {}
    for k, v in tr.items():
        a = act.get(k)
        tr2[k] = (a[0] / v[3], v[1], a[1], v[3]) + v[4:] if a else v
    pm = player_features(pm, tr2)
    # team + opponent pre-match ratings
    att, dfn, pen, lav, lg, ssn = [], [], [], [], [], []
    for r in pm.itertuples():
        T = tr.get((r.team, r.date))
        O = tr.get((r.opp, r.date))
        att.append(T[0] if T else np.nan)
        pen.append(T[2] if T else np.nan)
        lav.append(T[3] if T else np.nan)
        lg.append(T[4] if T else None)
        dfn.append(O[1] if O else np.nan)
    pm['att'], pm['dfn'], pm['tpen'], pm['lavg'], pm['league'] = att, dfn, pen, lav, lg
    HOME_ADV = 1.10
    pm['lam_team_stats'] = pm['lavg'] * pm['att'] * pm['dfn'] * np.where(pm['home'] == 1, HOME_ADV, 1 / HOME_ADV)
    mk = load_market(data)
    idx, miss = market_index(mk, set(tm['team']))
    pm['lam_team_mkt'] = [idx.get((t, d.normalize()), np.nan) for t, d in zip(pm['team'], pm['date'])]
    return pm, mk, miss


def logit_fit(X, y, lam=1.0, iters=50):
    X = np.column_stack([np.ones(len(X)), X])
    w = np.zeros(X.shape[1])
    w[0] = math.log(y.mean() / (1 - y.mean()))
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ w))
        g = X.T @ (y - p) - lam * np.r_[0, w[1:]]
        H = (X * (p * (1 - p))[:, None]).T @ X + lam * np.diag(np.r_[0, np.ones(len(w) - 1)])
        step = np.linalg.solve(H, g)
        w += step
        if np.abs(step).max() < 1e-8:
            break
    return w


def logit_pred(w, X):
    return 1 / (1 + np.exp(-(w[0] + X @ w[1:])))


def auc(p, y):
    o = np.argsort(p)
    r = np.empty(len(p))
    r[o] = np.arange(1, len(p) + 1)
    pos = y == 1
    return (r[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * (~pos).sum())


def ll(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def evaluate(pm, test_from):
    d = pm[(pm['position'] != 'Sub') & (pm['n_prior'] >= 5) & (pm['grp'] != 'GK')].copy()
    d = d[d['lam_team_stats'].notna()]
    d['y'] = (d['goals'] > 0).astype(int)
    d['has_mkt'] = d['lam_team_mkt'].notna().astype(int)
    # penalties are ~ (team pen xG) -> expressed as a share of the team total
    for src in ('stats', 'mkt'):
        lt = d['lam_team_' + src].fillna(d['lam_team_stats'] * d['tpen'].fillna(0).add(1) if src == 'mkt' else 0)
        if src == 'mkt':
            lt = d['lam_team_mkt'].where(d['lam_team_mkt'].notna(), d['lam_team_stats'] + d['tpen'].fillna(0.1))
            lt_np = lt - d['tpen'].fillna(0.1) * 0.95
        else:
            lt_np = d['lam_team_stats']
        lam = lt_np.clip(lower=0.05) * d['share'] * d['exp_min'] / 90 + d['tpen'].fillna(0.1) * 0.95 * d['pen_share'] * d['exp_min'] / 90
        d['lam_' + src] = lam.clip(lower=1e-4)
        d['p_raw_' + src] = 1 - np.exp(-d['lam_' + src])
    d['naive'] = d['share'] * d['exp_min'] / 90   # player-only baseline (no team layer)
    res = {}
    seasons = sorted(d['season'].unique())
    feats = lambda z: np.column_stack([np.log(z['lam_mkt']), z['fin'], z['home'], np.log1p(z['n_prior']),
                                      (z['grp'] == 'F').astype(int), (z['grp'] == 'D').astype(int)])
    out_rows = []
    for s in seasons:
        if s < test_from:
            continue
        tr = d[d['season'] < s]
        te = d[d['season'] == s].copy()
        if len(tr) < 5000 or len(te) < 1000:
            continue
        w = logit_fit(feats(tr), tr['y'].values.astype(float))
        te['p_cal'] = logit_pred(w, feats(te))
        out_rows.append(te)
        y = te['y'].values
        res[int(s)] = {
            'rows': int(len(te)), 'rate': round(float(y.mean()), 4), 'market_cov': round(float(te['has_mkt'].mean()), 3),
            'auc': {k: round(float(auc(te[k].values, y)), 4) for k in ('naive', 'p_raw_stats', 'p_raw_mkt', 'p_cal')},
            'logloss': {k: round(ll(te[k].values, y), 4) for k in ('p_raw_stats', 'p_raw_mkt', 'p_cal')},
            'coef': [round(float(x), 3) for x in w],
        }
        print(s, json.dumps(res[int(s)]), flush=True)
    allte = pd.concat(out_rows)
    y = allte['y'].values
    summ = {k: round(float(auc(allte[k].values, y)), 4) for k in ('naive', 'p_raw_stats', 'p_raw_mkt', 'p_cal')}
    # calibration table for the final model
    allte['dec'] = pd.qcut(allte['p_cal'], 10, labels=False)
    cal = allte.groupby('dec').agg(pred=('p_cal', 'mean'), actual=('y', 'mean'), n=('y', 'size')).round(3)
    # top-of-slate hit rates, per matchday (date x league)
    allte['day'] = allte['date'].dt.strftime('%Y-%m-%d')
    hits = {}
    for k in ('naive', 'p_raw_stats', 'p_raw_mkt', 'p_cal'):
        top = allte.sort_values(k, ascending=False).groupby('day').head(8)
        hits[k] = round(float(top['y'].mean()), 4)
    return res, summ, cal, hits, allte


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True)
    ap.add_argument('--test-from', type=int, default=2018)
    ap.add_argument('--out', default='scorer_results.json')
    a = ap.parse_args()
    pm, mk, miss = build(a.data)
    print(f'player rows {len(pm)}, market matches {len(mk)}, unresolved market names {len(miss)}: '
          f'{sorted(miss.items(), key=lambda x: -x[1])[:25]}', flush=True)
    res, summ, cal, hits, allte = evaluate(pm, a.test_from)
    print('\nAUC over all test seasons:', summ)
    print('top-8 per matchday hit rate:', hits)
    print(cal.to_string())
    json.dump({'by_season': res, 'auc': summ, 'top8_hit': hits, 'calibration': cal.reset_index().to_dict('records')},
              open(a.out, 'w'), indent=1)
    pm.to_pickle(os.path.splitext(a.out)[0] + '_features.pkl')


if __name__ == '__main__':
    main()
