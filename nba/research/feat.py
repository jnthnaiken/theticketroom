"""Feature replay for the first-basket prediction search. Pre-game features for every starter of every game
(EWMA over his previous starts / appearances), then saved as a matrix for walk-forward model fitting."""
import json, math, sys
import numpy as np
sys.path.insert(0, '/home/claude/theticketroom/nba')
import nba_fb as F

G = json.load(open('games2.json'))
HL = 25.0; A = 1 - 0.5 ** (1 / HL); A60 = 1 - 0.5 ** (1 / 60.0); AT = 1 - 0.5 ** (1 / 40.0); A10 = 1 - 0.5 ** (1 / 8.0)
P, T = {}, {}           # player -> stats, team -> stats

def ew(d, k, x, a):
    if x is None: return
    s = d.get(k + '_s', 0.0) * (1 - a) + x; w = d.get(k + '_w', 0.0) * (1 - a) + 1
    d[k + '_s'], d[k + '_w'] = s, w; d[k] = s / w
def gv(d, k, dflt): v = d.get(k); return dflt if v is None else v
def lg(x): return math.log(max(x, .02))

NAMES = ['x_ef', 'x_tf', 'x_fs', 'x_fbc', 'x_fg', 'x_j', 'x_new',          # production share set
         'x_tfw', 'x_tfl', 'x_fbt', 'x_efg', 'x_rim', 'x_three', 'x_fsmk', 'x_ast', 'x_ef10', 'x_tf10', 'x_efa',
         't_tip', 't_first', 't_home', 't_fmk', 't_opp_allow', 't_conv']
rows, games = [], []
for gi, g in enumerate(G):
    H, V = g['H'], g['V']
    st = {Tm: g['starters'][Tm] for Tm in (H, V)}
    # predicted jumper = highest jump rate among starters
    jr = lambda n: gv(P.get(n, {}), 'jr', -1)
    J = {Tm: max(st[Tm], key=jr) for Tm in (H, V)}
    elo = lambda n: gv(P.get(n, {}), 'elo', 0.0)
    ptip = 1 / (1 + 10 ** (-(elo(J[H]) - elo(J[V]) + 8) / 400))
    X = []
    for Tm in (H, V):
        O = V if Tm == H else H
        tp = ptip if Tm == H else 1 - ptip
        tt, to = T.get(Tm, {}), T.get(O, {})
        for n in st[Tm]:
            p = P.get(n, {})
            fgp = (p['fgm'] / p['fga']) if p.get('fga') else .46
            efa, efm = gv(p, 'efa', 0), gv(p, 'efm', 0)
            X.append([lg(gv(p, 'ef', .2)), lg(gv(p, 'tf', .2)), lg(gv(p, 'fs', .2)), lg(gv(p, 'fbc', .2)),
                      min(max(fgp, .3), .7) - .46, 1.0 if n == J[Tm] else 0.0, 1.0 if gv(p, 'nst', 0) < 10 else 0.0,
                      lg(gv(p, 'tfw', .2)), lg(gv(p, 'tfl', .2)), lg(gv(p, 'fbt', .2)),
                      ((efm + 2.3) / (efa + 5)) - .46, lg(gv(p, 'rim', .2)), lg(gv(p, 'three', .2)),
                      ((gv(p, 'fsm', 0) + 1) / (gv(p, 'fsn', 0) + 2.5)) - .4, lg(gv(p, 'ast', .2)),
                      lg(gv(p, 'ef10', .2)), lg(gv(p, 'tf10', .2)), math.log(1 + gv(p, 'efan', 1.5)),
                      math.log(tp / (1 - tp)), gv(tt, 'first', .5) - gv(to, 'first', .5), 1.0 if Tm == H else 0.0,
                      gv(tt, 'fmk', .45) - .45, gv(to, 'allow', .5) - .5, gv(tt, 'conv', .5) - gv(to, 'conv', .5)])
    names10 = st[H] + st[V]
    y = names10.index(g['fb']) if g['fb'] in names10 else -1
    games.append({'gid': g['gid'], 'season': g['season'], 'date': g['date'], 'names': names10, 'y': y,
                  'teams': [H] * 5 + [V] * 5, 'ptip': ptip})
    rows.append(X)
    # ---------------- update ----------------
    team_of = g['team_of']; tip = g.get('tip'); jm = g.get('jumpers')
    if jm and jm[0] and jm[1] and tip in (H, V):
        a, b = P.setdefault(jm[0], {}), P.setdefault(jm[1], {})
        ra, rb = a.get('elo', 0.0), b.get('elo', 0.0)
        pe = 1 / (1 + 10 ** (-(ra - rb + 8) / 400)); yy = 1.0 if tip == H else 0.0
        ka = 16 * max(1, 3 - a.get('nj', 0) / 10); kb = 16 * max(1, 3 - b.get('nj', 0) / 10)
        a['elo'] = ra + ka * (yy - pe); b['elo'] = rb - kb * (yy - pe); a['nj'] = a.get('nj', 0) + 1; b['nj'] = b.get('nj', 0) + 1
    shots = g['shots']
    early = [s for s in shots if s[0] <= 300]
    for Tm in (H, V):
        O = V if Tm == H else H
        te = [s for s in early if s[1] == Tm]; tall = [s for s in shots if s[1] == Tm]
        tf_name = tall[0][2] if tall else None
        tfmade = tall[0][4] if tall else None
        firstT = 1.0 if g.get('fbT') == Tm else 0.0
        tmd = [s for s in tall if s[4]]; fbt_name = tmd[0][2] if tmd else None
        ew(T.setdefault(Tm, {}), 'first', firstT, AT)
        ew(T[Tm], 'fmk', tfmade, AT)
        ew(T.setdefault(O, {}), 'allow', firstT, AT)          # O allowed Tm to score first
        # conversion: scored on its first FGA (team-level), from the team's perspective
        ew(T[Tm], 'conv', tfmade, AT)
        n_e = len(te); n_rim = sum(1 for s in te if s[3] <= 4); n_3 = sum(1 for s in te if s[5] == 3)
        n_ast = sum(1 for s in te if s[6])
        ten = [s for s in shots if s[1] == Tm and s[0] <= 180]
        won = (tip == Tm)
        for n in st[Tm]:
            p = P.setdefault(n, {})
            mine = [s for s in te if s[2] == n]
            ew(p, 'ef', len(mine) / n_e if n_e else None, A)
            ew(p, 'tf', 1.0 if tf_name == n else 0.0, A)
            if tip in (H, V):
                ew(p, 'tfw' if won else 'tfl', 1.0 if tf_name == n else 0.0, A)
            if firstT: ew(p, 'fbc', 1.0 if g.get('fb') == n else 0.0, A)
            ew(p, 'fbt', 1.0 if fbt_name == n else 0.0, A)
            ew(p, 'rim', (sum(1 for s in mine if s[3] <= 4) / n_rim) if n_rim else None, A)
            ew(p, 'three', (sum(1 for s in mine if s[5] == 3) / n_3) if n_3 else None, A)
            ew(p, 'ast', (sum(1 for s in te if s[6] == n) / n_ast) if n_ast else None, A)
            ew(p, 'ef10', len(mine) / n_e if n_e else None, A10)
            ew(p, 'tf10', 1.0 if tf_name == n else 0.0, A10)
            ew(p, 'efan', float(len([s for s in ten if s[2] == n])), A)
            ew(p, 'jr', 1.0 if (jm and n in jm) else 0.0, A)
            p['efa'] = gv(p, 'efa', 0) * (1 - A60) + len(mine); p['efm'] = gv(p, 'efm', 0) * (1 - A60) + sum(s[4] for s in mine)
            if tf_name == n:
                p['fsn'] = gv(p, 'fsn', 0) * (1 - A60) + 1; p['fsm'] = gv(p, 'fsm', 0) * (1 - A60) + (tfmade or 0)
            p['nst'] = gv(p, 'nst', 0) + 1
    for n, Tm in team_of.items():
        p = P.setdefault(n, {})
        ew(p, 'fga', float(g['fga'].get(n, 0)), A60); ew(p, 'fgm', float(g['fgm'].get(n, 0)), A60)
    # fs = whole-game FGA share among the team (starters only updated, like production)
    for Tm in (H, V):
        tot = sum(v for n, v in g['fga'].items() if team_of.get(n) == Tm)
        for n in st[Tm]:
            ew(P[n], 'fs', g['fga'].get(n, 0) / tot if tot else None, A)
np.save('X.npy', np.array(rows, dtype=np.float32))
json.dump({'games': games, 'names': NAMES}, open('meta.json', 'w'))
print('X', np.array(rows).shape)
