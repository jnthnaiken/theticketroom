#!/usr/bin/env python3
"""shadow.py -- SCORERSHADOW-2026-09-17. Runs the layered scorer model (scorer_model.py) BESIDE the
live soccer board, logs its number for every priced player, and grades it against the live ranking
once a night settles. It changes nothing on the board.

Owner, after the first results (RESULTS-2026-09-17.md): "go ahead and commit it" -- shadow mode.

WHAT IT WRITES (soccer/shadow/)
  <date>.json    one entry per priced player on that slate: model lambda, P(score), and the layers
                 (team goals expected, share, expected minutes, penalty share) + how he was matched.
                 Written ONCE per slate, from data that existed before the slate's date.
  ledger.json    per graded night: legs, scorers, top-4 / top-8 hit rate and flat-1u ROI for the
                 model, the live TOTAL, and the price; plus running totals and pooled AUCs.
                 Population = the board's betting population: confirmed starter, not out/void,
                 priced, odds >= the soccer floor (-200).

HOW A PRE-MATCH NUMBER IS MADE FOR A FUTURE MATCH. scorer_model computes every feature as the value
BEFORE a row's match. So for a slate date with no understat row yet (tonight, or any cup / UEFA
tie), a synthetic appearance is appended for the player and for his team, and the same code is run;
the synthetic row's pre-match values are the answer. If a real league row already exists on that
date (a backfill), the real row's pre-match values are used. Either way nothing on or after the
slate date is seen.

    python3 shadow.py --history <dir with player_matches.csv.gz, team_matches.csv.gz>
                      --soccer <repo>/soccer [--dates 2026-09-17 ...] [--backfill] [--grade]
"""
import argparse, glob, io, json, math, os, re, sys, unicodedata
from collections import defaultdict

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scorer_model as S   # noqa: E402

FLOOR = -200          # FLOOR200-2026-09-17, soccer_draft.js DEFAULTS.MIN_ODDS
HOME_ADV = 1.10
MODEL = 'layered_v0'


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r"[']", '', s)
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def implied(o):
    o = float(o)
    return 100 / (o + 100) if o > 0 else -o / (-o + 100)


def dec(o):
    o = float(o)
    return 1 + (o / 100 if o > 0 else 100 / -o)


def frac_to_am(f):
    a, b = str(f).split('/')
    x = float(a) / float(b)
    return round(x * 100) if x >= 1 else round(-100 / x)


# ------------------------------------------------------------------------------ name resolution
TEAM_DROP = {'fc', 'afc', 'ac', 'as', 'sc', 'cf', 'sv', 'tsg', '1', 'calcio', '1913', 'de', 'cd', 'rc', 'ssc',
             'us', 'acf', 'ogc', 'rcd', 'ud', 'hove', 'albion', 'hotspur', 'town', 'city', 'aj', 'cfc'}
TEAM_ALIAS = {
    'atletico madrid': 'Atletico Madrid', 'internazionale': 'Inter', 'paris saint germain': 'Paris Saint Germain',
    'rb leipzig': 'RasenBallsport Leipzig', 'borussia monchengladbach': 'Borussia M.Gladbach',
    'hamburg sv': 'Hamburger SV', 'mainz': 'Mainz 05', 'fc augsburg': 'Augsburg', 'sc freiburg': 'Freiburg',
    'tsg hoffenheim': 'Hoffenheim', '1 fc union berlin': 'Union Berlin', 'sc paderborn 07': 'Paderborn',
    'sv elversberg': 'Elversberg', 'stade rennais': 'Rennes', 'le havre ac': 'Le Havre', 'as monaco': 'Monaco',
    'aj auxerre': 'Auxerre', 'as roma': 'Roma', 'parma': 'Parma Calcio 1913', 'deportivo': 'Deportivo La Coruna',
    'malaga': 'Malaga', 'alaves': 'Alaves', 'afc bournemouth': 'Bournemouth', 'brighton hove albion': 'Brighton',
    'brighton and hove albion': 'Brighton', 'tottenham hotspur': 'Tottenham', 'west ham united': 'West Ham',
    'leeds united': 'Leeds', 'hull city': 'Hull', 'ipswich town': 'Ipswich', 'coventry city': 'Coventry',
    'wolverhampton wanderers': 'Wolverhampton Wanderers', 'fc cologne': 'FC Cologne', '1 fc koln': 'FC Cologne',
    'manchester city': 'Manchester City', 'manchester united': 'Manchester United',
    'newcastle united': 'Newcastle United', 'nottingham forest': 'Nottingham Forest',
    'olympique lyonnais': 'Lyon', 'olympique de marseille': 'Marseille', 'real betis balompie': 'Real Betis',
}


class Teams:
    def __init__(self, names):
        self.by = {norm(t): t for t in names}
        self.core = defaultdict(list)
        for k, t in self.by.items():
            self.core[' '.join(w for w in k.split() if w not in TEAM_DROP)].append(t)

    def __call__(self, name):
        n = norm(name)
        if not n:
            return None
        if n in TEAM_ALIAS:
            return TEAM_ALIAS[n]
        if n in self.by:
            return self.by[n]
        c = ' '.join(w for w in n.split() if w not in TEAM_DROP)
        hits = self.core.get(c, [])
        return hits[0] if len(set(hits)) == 1 else None


class Players:
    """Understat pid lookup. Surname-anchored and unique-or-nothing, the same rule the board uses."""
    def __init__(self, pm):
        last = pm.sort_values('date').groupby('pid').tail(1).set_index('pid')
        self.team = last['team'].to_dict()
        self.last_date = last['date'].to_dict()
        self.by = defaultdict(list)
        for pid, n in pm.groupby('pid')['name'].first().items():
            self.by[norm(n)].append(pid)
        self.tok = {k: set(k.split()) for k in self.by}

    def __call__(self, name, team_hint=None):
        k = norm(name)
        cands = list(self.by.get(k, []))
        how = 'exact'
        if not cands:
            t = set(k.split())
            if not t:
                return None, None
            hits = [kk for kk, tt in self.tok.items()
                    if (k.split()[-1] in tt or k.split()[0] in tt) and (t <= tt or tt <= t)]
            cands = [p for kk in hits for p in self.by[kk]]
            how = 'token'
        if len(cands) > 1 and team_hint:
            cands = [p for p in cands if self.team.get(p) == team_hint] or cands
        if len(set(cands)) != 1:
            return None, None
        return cands[0], how


# ------------------------------------------------------------------------------ model state
def load_history(hdir):
    tm = pd.read_csv(os.path.join(hdir, 'team_matches.csv.gz'))
    pm = pd.read_csv(os.path.join(hdir, 'player_matches.csv.gz'))
    for c in ('xG', 'xGA', 'npxG', 'npxGA'):
        tm[c] = tm[c].astype(float)
    tm['date'] = pd.to_datetime(tm['date'])
    pm['date'] = pd.to_datetime(pm['date'])
    tm = tm.drop_duplicates(['team', 'date'], keep='last')
    pm = pm.drop_duplicates(['pid', 'match_id'], keep='last')
    return tm, pm


def slate_legs(sdir):
    """(match_key, player, american odds) from ags.psv, and the fixture table."""
    fx = json.load(io.open(os.path.join(sdir, 'fixtures.json'), encoding='utf-8'))
    legs = []
    for line in io.open(os.path.join(sdir, 'ags.psv'), encoding='utf-8'):
        c = line.rstrip('\n').split('|')
        if len(c) < 3 or not c[0]:
            continue
        try:
            am = frac_to_am(c[2])
        except Exception:
            continue
        legs.append((c[0], c[1], am))
    return legs, fx


def compute(tm, pm, jobs):
    """jobs: list of dicts {date, match, name, home_name, away_name, league}.
    Returns the same dicts with the model fields filled in."""
    TR = Teams(set(tm['team']))
    PL = Players(pm)        # pm already carries `team` (assign_team runs once, in main)

    # ---- resolve every job ----
    syn_t, syn_p = [], []
    for j in jobs:
        d = pd.Timestamp(j['date'])
        h, a = TR(j['home_name']), TR(j['away_name'])
        j['home_t'], j['away_t'] = h, a
        pid, how = PL(j['name'])
        j['pid'], j['how'] = (int(pid) if pid is not None else None), how
        if pid is None:
            continue
        team = PL.team.get(pid)
        # the player's club tonight must be one of the two fixture sides. If it is not, he has moved
        # to a club understat does not cover (Vlahovic -> Besiktas) or the name matched the wrong
        # man; either way his old club's team layer would be a lie, so he is not modelled.
        if not team or team not in (h, a):
            j['status_hint'] = f'club {team} not in fixture'
            j['team'] = None
            continue
        j['team'] = team
        j['home'] = 1 if j['team'] and j['team'] == h else 0
        j['opp'] = a if j['home'] else h
        if j['team'] and not ((tm['team'] == j['team']) & (tm['date'] == d)).any():
            syn_t.append((j['team'], d))
        if j['opp'] and not ((tm['team'] == j['opp']) & (tm['date'] == d)).any():
            syn_t.append((j['opp'], d))
        if not ((pm['pid'] == pid) & (pm['date'] == d)).any():
            syn_p.append(dict(pid=pid, name=j['name'], date=d, team=j['team'],
                              h_team=j['team'] if j['home'] else (j['opp'] or '?'),
                              a_team=(j['opp'] or '?') if j['home'] else j['team']))

    # ---- synthetic team rows (values only feed the state AFTER the row, so zeros are harmless) ----
    lg_of = tm.sort_values('date').groupby('team')['league'].last().to_dict()
    ss_of = tm.sort_values('date').groupby('team')['season'].last().to_dict()
    rows = []
    for t, d in set(syn_t):
        if t in lg_of:
            rows.append(dict(league=lg_of[t], season=ss_of[t], date=d, team=t, h_a='h',
                             xG=0.0, xGA=0.0, npxG=0.0, npxGA=0.0, scored=0, missed=0, _syn=1))
    tm2 = pd.concat([tm.assign(_syn=0), pd.DataFrame(rows)], ignore_index=True) if rows else tm.assign(_syn=0)
    tr = S.team_ratings(tm2)
    tmx = tm2[tm2['_syn'] == 0].set_index(['team', 'date'])
    act = {k: (v.npxG, max(v.xG - v.npxG, 0)) for k, v in zip(tmx.index, tmx.itertuples())}
    tr2 = {}
    for k, v in tr.items():
        a_ = act.get(k)
        tr2[k] = (a_[0] / v[3], v[1], a_[1], v[3]) + v[4:] if a_ else v

    # ---- synthetic player rows ----
    prow = []
    for r in syn_p:
        prow.append(dict(pid=r['pid'], name=r['name'], league='', season=0, date=r['date'], match_id=-1,
                         h_team=r['h_team'], a_team=r['a_team'], h_goals=0, a_goals=0, position='FW', time=0,
                         goals=0, shots=0, xG=0.0, npg=0, npxG=0.0, xA=0.0, key_passes=0, xGChain=0.0,
                         xGBuildup=0.0, team=r['team'], _syn=1))
    pm2 = pd.concat([pm.assign(_syn=0), pd.DataFrame(prow)], ignore_index=True) if prow else pm.assign(_syn=0)
    if prow:
        pm2['home'] = (pm2['team'] == pm2['h_team']).astype(int)
        pm2['opp'] = np.where(pm2['home'] == 1, pm2['a_team'], pm2['h_team'])
    # stable order: a synthetic row sorts AFTER any real row on the same date (it never feeds them)
    pm2 = pm2.sort_values(['pid', 'date', '_syn']).reset_index(drop=True)
    pm2 = S.player_features(pm2, tr2)
    key = pm2.set_index(['pid', 'date'])

    # ---- assemble ----
    for j in jobs:
        if j.get('pid') is None:
            j['status'] = 'no understat match'
            continue
        if not j.get('team'):
            j['status'] = j.get('status_hint') or 'no club'
            continue
        d = pd.Timestamp(j['date'])
        try:
            x = key.loc[(j['pid'], d)]
        except KeyError:
            j['status'] = 'no state'
            continue
        if isinstance(x, pd.DataFrame):
            x = x.iloc[0]
        T = tr.get((j['team'], d)) if j.get('team') else None
        O = tr.get((j['opp'], d)) if j.get('opp') else None
        if T is None:
            j['status'] = 'team not in understat'
            continue
        att, lavg, tpen = T[0], T[3], T[2]
        dfn = O[1] if O else 1.0
        lam_team = lavg * att * dfn * (HOME_ADV if j['home'] else 1 / HOME_ADV)
        em = float(x['exp_min'])
        lam = max(lam_team, .05) * float(x['share']) * em / 90 + (tpen if tpen == tpen else .1) * .95 * float(x['pen_share']) * em / 90
        j.update(status='ok', lam=round(float(lam), 5), p_model=round(float(1 - math.exp(-lam)), 5),
                 team_goals=round(float(lam_team), 4), share=round(float(x['share']), 4),
                 exp_min=round(em, 1), pen_share=round(float(x['pen_share']), 4), n_prior=int(x['n_prior']),
                 opp_rated=O is not None)
    return jobs


def shadow_slate(tm, pm, soccer, date):
    sdir = os.path.join(soccer, 'slates', date)
    legs, fx = slate_legs(sdir)
    jobs = []
    for mk, name, am in legs:
        f = fx['matches'].get(mk)
        if not f:
            continue
        jobs.append(dict(date=date, match=mk, name=name, odds=am, league=f.get('league'),
                         home_name=f['home'], away_name=f['away']))
    # only history strictly before the slate date may inform it
    d = pd.Timestamp(date)
    jobs = compute(tm[tm['date'] < d], pm[pm['date'] < d], jobs)
    out = {'model': MODEL, 'date': date, 'players': {}}
    for j in jobs:
        rec = {k: j.get(k) for k in ('match', 'odds', 'league', 'status', 'lam', 'p_model', 'team_goals', 'share',
                                     'exp_min', 'pen_share', 'n_prior', 'pid', 'how', 'team', 'opp', 'home',
                                     'opp_rated')}
        out['players'][j['name']] = rec
    ok = sum(1 for v in out['players'].values() if v['status'] == 'ok')
    out['coverage'] = {'priced': len(out['players']), 'modelled': ok}
    return out


# ------------------------------------------------------------------------------ grading
def auc(p, y):
    p, y = np.asarray(p, float), np.asarray(y, int)
    if y.sum() in (0, len(y)):
        return None
    return float(S.auc(p, y))


def grade(soccer):
    sdir = os.path.join(soccer, 'shadow')
    season = json.load(io.open(os.path.join(soccer, 'soccer_season.json'), encoding='utf-8'))
    graded = set(season.get('graded_nights') or [])
    ledger_p = os.path.join(sdir, 'ledger.json')
    led = json.load(io.open(ledger_p, encoding='utf-8')) if os.path.exists(ledger_p) else \
        {'model': MODEL, 'population': f'confirmed starters, not out/void, odds >= {FLOOR}', 'nights': {}}
    for f in sorted(glob.glob(os.path.join(sdir, '2*.json'))):
        date = os.path.basename(f)[:-5]
        if date not in graded or date in led['nights']:
            continue
        bp = os.path.join(soccer, 'boards', date + '.json')
        if not os.path.exists(bp):
            continue
        sh = json.load(io.open(f, encoding='utf-8'))['players']
        P = json.load(io.open(bp, encoding='utf-8'))['players']
        rows = []
        for n, p in P.items():
            o = p.get('odds')
            if o is None or p.get('out') or p.get('void') or p.get('status') != 'confirmed' or o < FLOOR:
                continue
            s = sh.get(n) or {}
            rows.append(dict(name=n, odds=o, total=p.get('TOTAL') or 0, y=1 if p.get('hr') else 0,
                             p_model=s.get('p_model')))
        both = [r for r in rows if r['p_model'] is not None]
        night = {'legs': len(rows), 'modelled': len(both), 'scored': sum(r['y'] for r in rows), 'rows': both}
        for n_ in (4, 8):
            for k, key in (('model', 'p_model'), ('total', 'total'), ('price', None)):
                srt = sorted(both, key=lambda r: -(r[key] if key else implied(r['odds'])))[:n_]
                night[f'top{n_}_{k}'] = {'hit': sum(r['y'] for r in srt), 'n': len(srt),
                                         'units': round(sum((dec(r['odds']) if r['y'] else 0) - 1 for r in srt), 3)}
        led['nights'][date] = night
    # running totals
    allr = [r for v in led['nights'].values() for r in v['rows']]
    tot = {'nights': len(led['nights']), 'legs': len(allr)}
    if allr:
        y = [r['y'] for r in allr]
        tot['auc'] = {'model': auc([r['p_model'] for r in allr], y), 'total': auc([r['total'] for r in allr], y),
                      'price': auc([implied(r['odds']) for r in allr], y)}
        for n_ in (4, 8):
            for k in ('model', 'total', 'price'):
                h = sum(v[f'top{n_}_{k}']['hit'] for v in led['nights'].values())
                c = sum(v[f'top{n_}_{k}']['n'] for v in led['nights'].values())
                u = sum(v[f'top{n_}_{k}']['units'] for v in led['nights'].values())
                tot[f'top{n_}_{k}'] = {'hit': h, 'n': c, 'units': round(u, 2), 'roi': round(u / c, 4) if c else None}
    led['totals'] = tot
    json.dump(led, io.open(ledger_p, 'w', encoding='utf-8'), indent=1)
    return tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--history', required=True)
    ap.add_argument('--soccer', required=True)
    ap.add_argument('--dates', nargs='*', default=[])
    ap.add_argument('--backfill', action='store_true', help='every slate directory without a shadow file')
    ap.add_argument('--latest', action='store_true', help='the newest slate directory, if not yet shadowed')
    ap.add_argument('--grade', action='store_true')
    a = ap.parse_args()
    shd = os.path.join(a.soccer, 'shadow')
    os.makedirs(shd, exist_ok=True)
    slates = sorted(os.path.basename(p) for p in glob.glob(os.path.join(a.soccer, 'slates', '2*'))
                    if os.path.exists(os.path.join(p, 'ags.psv')) and os.path.exists(os.path.join(p, 'fixtures.json')))
    todo = list(a.dates)
    if a.backfill:
        todo += [d for d in slates if not os.path.exists(os.path.join(shd, d + '.json'))]
    if a.latest and slates and not os.path.exists(os.path.join(shd, slates[-1] + '.json')):
        todo.append(slates[-1])
    todo = sorted(set(todo))
    if todo:
        tm, pm = load_history(a.history)
        pm = S.assign_team(pm)
        print(f'history: {len(pm)} player rows, {len(tm)} team rows, last {pm["date"].max().date()}', flush=True)
        for d in todo:
            out = shadow_slate(tm, pm, a.soccer, d)
            json.dump(out, io.open(os.path.join(shd, d + '.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
            top = sorted(((v['p_model'], k, v['odds']) for k, v in out['players'].items() if v['p_model']), reverse=True)[:5]
            print(f'  {d}: {out["coverage"]}  top: ' + ', '.join(f'{k} {p:.2f} ({o:+d})' for p, k, o in top), flush=True)
    if a.grade:
        print('ledger:', json.dumps(grade(a.soccer))[:1500])


if __name__ == '__main__':
    main()
