#!/usr/bin/env python3
"""build_rows.py -- FEATTEST-2026-09-17. One row per bettable soccer leg on every graded night,
with every candidate feature computed from data that existed BEFORE kickoff.

Owner: "what goes into the soccer model exactly? there has to be more than just xG" -> "test all of it".

Population = what the board can bet: confirmed starter, priced +100 or longer, graded night, and a
slate directory on disk (xg.psv is the pre-game player file; nights before 2026-08-27 have none).

Candidate features
  home        1 if his team is at home (neutral cup ties read as the listed home side)
  team_att    log( team non-penalty xG per game / league average )     understat, point-in-time
  opp_def     log( opponent non-penalty xG ALLOWED per game / avg )    understat, point-in-time
  team_xg     team_att + opp_def  (the "how many will his team score" term)
  mins        minutes per appearance / 90, minutes-weighted across his seasons in xg.psv
  pens        penalty goals per 90 across his seasons (goals - npg); >0 means he takes them
  form        this season's npxG/90 minus his multi-season npxG/90, shrunk by this-season minutes
  team_form   team npxG/game over its last 3 league games minus its rating (log scale)
Missing team data (MLS, clubs outside the big five) -> 0 with a `*_miss` flag, never dropped.

Team ratings: last season's per-game rate as a prior worth PRIOR_G games, updated with this
season's matches played strictly BEFORE the slate date. No row sees its own match.
"""
import glob, io, json, math, os, re, sys, unicodedata
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SOC = os.path.dirname(HERE)
PRIOR_G = 8
FORM_K = 450.0


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r"[.'\-/&]", ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


DROP = {'fc', 'afc', 'ac', 'as', 'sc', 'cf', 'sv', 'tsg', '1', 'calcio', '1913', 'de', 'cd', 'rc',
        'ssc', 'us', 'acf', 'ogc', 'rcd', 'ud', 'hove', 'albion', 'hotspur', 'town', 'city', 'aj'}
ALIAS = {
    'atletico madrid': 'Atletico Madrid', 'internazionale': 'Inter', 'paris saint germain': 'Paris Saint Germain',
    'rb leipzig': 'RasenBallsport Leipzig', 'borussia monchengladbach': 'Borussia M.Gladbach',
    'hamburg sv': 'Hamburger SV', 'mainz': 'Mainz 05', 'fc augsburg': 'Augsburg', 'sc freiburg': 'Freiburg',
    'tsg hoffenheim': 'Hoffenheim', '1 fc union berlin': 'Union Berlin', 'sc paderborn 07': 'Paderborn',
    'sv elversberg': 'Elversberg', 'stade rennais': 'Rennes', 'le havre ac': 'Le Havre', 'as monaco': 'Monaco',
    'aj auxerre': 'Auxerre', 'as roma': 'Roma', 'parma': 'Parma Calcio 1913', 'deportivo': 'Deportivo La Coruna',
    'malaga': 'Malaga', 'alaves': 'Alaves', 'afc bournemouth': 'Bournemouth', 'brighton hove albion': 'Brighton',
    'tottenham hotspur': 'Tottenham', 'west ham united': 'West Ham', 'leeds united': 'Leeds', 'hull city': 'Hull',
    'ipswich town': 'Ipswich', 'coventry city': 'Coventry', 'wolverhampton wanderers': 'Wolverhampton Wanderers',
    'fc cologne': 'FC Cologne', 'manchester city': 'Manchester City', 'manchester united': 'Manchester United',
    'newcastle united': 'Newcastle United',
}


def load_teams(path):
    prior, games = {}, defaultdict(list)
    lg_of = {}
    for line in io.open(path, encoding='utf-8'):
        c = line.rstrip('\n').split('|')
        if c[0] == 'A':
            _, lg, _s, t, n, xg, xga, _g, _ga = c
            prior[t] = (float(xg) / int(n), float(xga) / int(n))
            lg_of[t] = lg
        elif c[0] == 'M':
            _, lg, _s, t, d, ha, xg, xga, _g, _ga = c
            games[t].append((d, ha, float(xg), float(xga)))
            lg_of[t] = lg
    for t in games:
        games[t].sort()
    return prior, games, lg_of


PRIOR, GAMES, LG_OF = load_teams(os.path.join(HERE, 'teams_understat.psv'))
BYNORM = {norm(t): t for t in LG_OF}


def resolve(name):
    n = norm(name)
    if n in ALIAS:
        return ALIAS[n]
    if n in BYNORM:
        return BYNORM[n]
    core = ' '.join(w for w in n.split() if w not in DROP)
    hits = [t for k, t in BYNORM.items() if ' '.join(w for w in k.split() if w not in DROP) == core]
    return hits[0] if len(hits) == 1 else None


def league_avg(lg, date):
    teams = [t for t, l in LG_OF.items() if l == lg]
    r = [rating(t, date, raw=True) for t in teams]
    r = [x for x in r if x]
    return (sum(a for a, _ in r) / len(r), sum(b for _, b in r) / len(r))


def rating(t, date, raw=False):
    """(npxG per game, npxGA per game) using only matches before `date`."""
    past = [g for g in GAMES.get(t, []) if g[0] < date]
    lg = LG_OF[t]
    if t in PRIOR:
        pa, pd = PRIOR[t]
    else:   # promoted: prior = bottom-third of last season's league, a promoted club's usual level
        ps = sorted(PRIOR[x] for x in PRIOR if LG_OF[x] == lg)
        k = max(1, len(ps) // 3)
        pa = sum(a for a, _ in sorted(ps)[:k]) / k
        pd = sum(b for _, b in sorted(ps, key=lambda v: -v[1])[:k]) / k
    n = len(past)
    a = (pa * PRIOR_G + sum(g[2] for g in past)) / (PRIOR_G + n)
    d = (pd * PRIOR_G + sum(g[3] for g in past)) / (PRIOR_G + n)
    return (a, d)


_AVG = {}


def rel(t, date):
    key = (LG_OF[t], date)
    if key not in _AVG:
        _AVG[key] = league_avg(*key)
    ma, md = _AVG[key]
    a, d = rating(t, date)
    past = [g for g in GAMES.get(t, []) if g[0] < date][-3:]
    tf = math.log(max(.2, sum(g[2] for g in past) / len(past)) / a) if len(past) == 3 else 0.0
    return math.log(a / ma), math.log(d / md), tf


def load_xg(path):
    recs = defaultdict(list)
    for line in io.open(path, encoding='utf-8'):
        c = line.rstrip('\n').split('|')
        if len(c) < 18:
            continue
        recs[norm(c[2])].append(dict(season=int(c[1]), games=int(c[5]), minutes=int(c[6]), goals=int(c[7]),
                                     npg=int(c[8]), npxg=float(c[9])))
    return recs


def find(recs, name):
    n = norm(name)
    if n in recs:
        return recs[n]
    toks = n.split()
    if not toks:
        return None
    hits = [k for k in recs if toks[-1] in k.split() and (set(toks) <= set(k.split()) or set(k.split()) <= set(toks))]
    return recs[hits[0]] if len(hits) == 1 else None


def player_feats(rs):
    mins = sum(r['minutes'] for r in rs)
    games = sum(r['games'] for r in rs)
    if not mins or not games:
        return None
    npx90 = sum(r['npxg'] for r in rs) * 90 / mins
    cur = max(r['season'] for r in rs)
    cr = [r for r in rs if r['season'] == cur]
    cm = sum(r['minutes'] for r in cr)
    form = 0.0
    if cm and len({r['season'] for r in rs}) > 1:
        cur90 = sum(r['npxg'] for r in cr) * 90 / cm
        form = (cur90 - npx90) * cm / (cm + FORM_K)
    pens = sum(r['goals'] - r['npg'] for r in rs) * 90 / mins
    return dict(mins=min(mins / games, 90) / 90, pens=pens, form=form)


def main():
    season = json.load(io.open(os.path.join(SOC, 'soccer_season.json'), encoding='utf-8'))
    rows, miss = [], defaultdict(int)
    for d in sorted(season['graded_nights']):
        xgp = os.path.join(SOC, 'slates', d, 'xg.psv')
        bp = os.path.join(SOC, 'boards', d + '.json')
        if not (os.path.exists(xgp) and os.path.exists(bp)):
            continue
        recs = load_xg(xgp)
        D = json.load(io.open(bp, encoding='utf-8'))
        P = D['players']
        night = []
        for n, p in P.items():
            o = p.get('odds')
            if o is None or p.get('out') or p.get('void') or p.get('status') != 'confirmed':
                continue
            if not isinstance(p.get('edge_z'), (int, float)):
                continue
            gm = p.get('gmatch') or ''
            sides = gm.split(' v ') if ' v ' in gm else [None, None]
            team = p.get('team')
            opp = (p.get('opp') or [None])[0]
            if ' v ' in str(opp or ''):
                opp = None
            if sides[0] and team:
                if norm(team) == norm(sides[0]):
                    opp = sides[1]
                elif norm(team) == norm(sides[1]):
                    opp = sides[0]
            home = 1.0 if '(H)' in str((p.get('opp') or [None, None])[1:]) else 0.0
            r = dict(date=d, name=n, odds=int(o), ez=float(p['edge_z']), total=float(p.get('TOTAL') or 0),
                     y=1 if p.get('hr') else 0, league=p.get('league'), home=home)
            tt, oo = resolve(team) if team else None, resolve(opp) if opp else None
            if tt:
                r['team_att'], _, r['team_form'] = rel(tt, d)
                r['team_miss'] = 0.0
            else:
                r['team_att'] = r['team_form'] = 0.0
                r['team_miss'] = 1.0
                miss['team:' + str(team)] += 1
            if oo:
                r['opp_def'] = rel(oo, d)[1]
                r['opp_miss'] = 0.0
            else:
                r['opp_def'] = 0.0
                r['opp_miss'] = 1.0
                miss['opp:' + str(opp)] += 1
            r['team_xg'] = r['team_att'] + r['opp_def']
            pf = player_feats(find(recs, n) or [])
            if pf:
                r.update(pf)
                r['pl_miss'] = 0.0
            else:
                r.update(mins=0.0, pens=0.0, form=0.0, pl_miss=1.0)
            night.append(r)
        if len(night) < 2:
            continue
        m = sum(x['ez'] for x in night) / len(night)
        sd = (sum((x['ez'] - m) ** 2 for x in night) / len(night)) ** .5 or 1.0
        for x in night:
            x['z'] = (x['ez'] - m) / sd
        rows += [x for x in night if x['odds'] >= 100]
    json.dump(rows, io.open(os.path.join(HERE, 'rows.json'), 'w', encoding='utf-8'), indent=0)
    print(f'{len(rows)} rows, {sum(r["y"] for r in rows)} scored, {len({r["date"] for r in rows})} nights')
    for k in ('team_miss', 'opp_miss', 'pl_miss'):
        print(f'  {k}: {sum(r[k] for r in rows):.0f}')
    top = sorted(((v, k) for k, v in miss.items()), reverse=True)[:25]
    print('  unresolved:', ', '.join(f'{k} x{v}' for v, k in top))


if __name__ == '__main__':
    main()
