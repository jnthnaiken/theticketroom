"""Stage 3: replay every 2025 (and 2024) slate through the LIVE scorer + LIVE draft, per book x rule."""
import os as _os, sys as _sys
_H = _os.path.dirname(_os.path.abspath(__file__))
for _p in (_os.path.join(_H, '..'), _os.path.join(_H, '..', '..', 'soccer')):
    if _p not in _sys.path: _sys.path.insert(0, _p)
_os.chdir(_os.path.join(_H, '..'))   # nfl/: the model files are read relative to it
OUT = lambda n: _os.path.join(_H, n)

import os, sys, json, io, contextlib, subprocess, tempfile, itertools, numpy as np, pandas as pd
import nfl_mock as M, soccer_grade as G

B = pd.read_pickle(OUT('books.pkl'))
SEASONS = [int(x) for x in os.environ.get('BT_SEASONS', '2025').split(',')]
BOOKS = os.environ.get('BT_BOOKS', 'weak,same,rich,sharp').split(',')
VIG = float(os.environ.get('BT_VIG', '1.10'))
PER_TEAM = 8
BIG = 100000
RULES = {                       # name: (MKTSCALE, board model, MKT_W, MAX_ODDS)
    'old_rawEV_nocap': ('0', 'ev_v1', 1.0, BIG),     # live 09-11 .. 09-15 (week 1)
    'mkt50_nocap':     ('0', 'mkt50', 1.0, BIG),     # live before 09-11
    'new_w50_cap500':  ('1', 'ev_v1', 0.5, 500),     # LIVE NOW
    'new_w50_cap400':  ('1', 'ev_v1', 0.5, 400),
    'new_w50_cap300':  ('1', 'ev_v1', 0.5, 300),
    'new_w50_cap800':  ('1', 'ev_v1', 0.5, 800),
    'new_w50_nocap':   ('1', 'ev_v1', 0.5, BIG),
    'new_w100_cap500': ('1', 'ev_v1', 1.0, 500),
    'new_w0_cap500':   ('1', 'ev_v1', 0.0, 500),     # market only: EV is just the vig structure
}
if os.environ.get('BT_RULES'): RULES = {k: RULES[k] for k in os.environ['BT_RULES'].split(',')}

def am(q):
    q = min(max(q, 0.01), 0.95)
    if q >= 0.5:
        return -int(5 * round(100 * q / (1 - q) / 5))
    v = 100 * (1 - q) / q
    step = 5 if v < 300 else 10 if v < 1000 else 50
    return int(step * round(v / step))

def kick(t):
    try: h, m = str(t).split(':'); return int(h) * 60 + int(m)
    except Exception: return 780

def slates():
    for (s, w), wk in B[B.season.isin(SEASONS)].groupby(['season', 'week']):
        for day, g in wk.groupby('gameday'):
            yield s, w, day, g

out = []
tmp = tempfile.mkdtemp()
# The LIVE draft, with only the price ceiling made settable. Generated, never hand-copied.
_cli = open('nfl_draft_cli.js', encoding='utf-8').read()
assert _cli.count('  MAX_ODDS: 500,') == 1, 'nfl_draft_cli.js MAX_ODDS line moved -- update run.py'
_cli = _cli.replace('  MAX_ODDS: 500,', '  MAX_ODDS: Number(process.env.BT_MAX_ODDS || 500),')
_cli = _cli.replace("require('./soccer_draft.js')", "require(%r)" % os.path.abspath(os.path.join('..', 'soccer', 'soccer_draft.js')))
DRAFT = os.path.join(tmp, 'draft_bt.js'); open(DRAFT, 'w', encoding='utf-8').write(_cli)
for s, w, day, g in slates():
    games = g.drop_duplicates('game_id')
    fx = {'date': day, 'season': int(s), 'week': int(w), 'matches': {}}
    for _, r in games.iterrows():
        home = r.team if r.home == 1 else r.opp; away = r.opp if r.home == 1 else r.team
        fx['matches'][f'{away}-{home}'] = dict(home=home, away=away, kickoff=kick(r.gametime), espn='')
    slug = {}
    for k, v in fx['matches'].items(): slug[v['home']] = k; slug[v['away']] = k
    fxp = os.path.join(tmp, 'fixtures.json'); json.dump(fx, open(fxp, 'w'))
    table = g.drop(columns=[c for c in g.columns if c.startswith('p_') or c in ('p_model', 'exp_scorers')], errors='ignore')
    M.nfl_stats.build = lambda season, week, _t=table: _t.copy()
    truth = {r.full_name: dict(hr=bool(r.td_game), out=not r.played, game=slug.get(r.team)) for r in g.itertuples()}
    for book in BOOKS:
        off = g[g.played].sort_values('p_book_' + book, ascending=False).groupby('team').head(PER_TEAM)
        atd = os.path.join(tmp, 'atd.psv')
        with open(atd, 'w') as f:
            for r in off.itertuples():
                a = am(getattr(r, 'p_book_' + book) * VIG)
                f.write(f"{slug[r.team]}|{r.full_name}|{'+' if a > 0 else ''}{a}\n")
        for rule, (scale, model, wgt, mx) in RULES.items():
            os.environ['NFL_MKTSCALE'] = scale; os.environ['NFL_BOARD_MODEL'] = model
            M.CFG['MKT_W'] = wgt; M.CFG['MAX_ODDS'] = mx
            pr = os.path.join(tmp, 'prices.json')
            if os.path.exists(pr): os.remove(pr)
            with contextlib.redirect_stdout(io.StringIO()):
                d, _ = M.score(int(s), int(w), atd, fxp, pr)
                sc = M.to_scored(d, fx)
            scp = os.path.join(tmp, 'scored.json'); json.dump(sc, open(scp, 'w'))
            tk = os.path.join(tmp, 'tickets.json')
            env = dict(os.environ, BT_MAX_ODDS=str(mx))
            r = subprocess.run(['node', DRAFT, scp, fxp, tk], capture_output=True, text=True, env=env)
            if r.returncode != 0:
                print('DRAFT FAIL', s, w, day, book, rule, r.stderr[-300:]); continue
            for t in json.load(open(tk)):
                legs = [dict(name=l['name'], odds=l['odds'], game=l['match']) for l in t['legs']]
                tt = dict(kind=t['kind'], name=t['name'], players=legs,
                          rr=(dict(risk=t['risk']) if len(legs) > 1 else None))
                gr = G.grade_ticket(tt, truth, set(fx['matches']))
                if not gr: continue
                out.append(dict(season=s, week=w, day=day, book=book, rule=rule, kind=t['kind'],
                                stake=gr['stake'], net=gr['net'], won=gr['won'],
                                legs=len(legs), odds=[l['odds'] for l in legs],
                                anchor_odds=legs[0]['odds']))
    print(s, w, day, len(out), flush=True)
pd.DataFrame(out).to_pickle(OUT(os.environ.get('BT_OUT', 'results.pkl')))
