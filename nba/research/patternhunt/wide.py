"""PATTERN-HUNT wide table: one row per priced starter (FanDuel price), 2020-21 .. 2025-26 seasons labelled 2020..2025.
Families: FBL (tips / methods / positional / first-3-min), old model features, market structure, schedule context."""
import json, math, sys, collections, datetime
import numpy as np
sys.path.insert(0, '/home/claude/theticketroom/nba'); import nba_fb as F
BP = {'NOR': 'NOP', 'PHO': 'PHX', 'UTH': 'UTA', 'BRK': 'BKN', 'GS': 'GSW', 'NO': 'NOP', 'NY': 'NYK', 'SA': 'SAS'}
code = lambda x: BP.get(x, x)
def dec(am): return 1 + (am / 100 if am > 0 else 100 / -am)
B = json.load(open('/home/claude/fbr/bets.json'))
X0 = np.load('/home/claude/fbr/X.npy'); M0 = json.load(open('/home/claude/fbr/meta.json'))
X3 = np.load('/home/claude/fbl/X3.npy'); M3 = json.load(open('/home/claude/fbl/meta3.json'))
FN = ['o_' + n for n in M0['names']] + M3['names']
idx = {(str(g['gid']), n): (gi, j) for gi, g in enumerate(M3['games']) for j, n in enumerate(g['names'])}
G = json.load(open('/home/claude/fbr/games2.json'))
# --- BettingPros: position + opening price
ev, sel = {}, collections.defaultdict(dict)
for line in open('/home/claude/fbr/fb_odds.psv', encoding='utf-8'):
    r = line.rstrip('\n').split('|')
    if r[0] == 'E': ev[(r[1].replace('-', ''), code(r[4]), code(r[5]))] = r[2]
    elif r[0] == 'S':
        try: op = int(r[6])
        except ValueError: op = None
        sel[r[2]][F.norm(r[4])] = (r[5], op); sel[r[2]]['i:' + F.ikey(r[4])] = (r[5], op)
# --- schedule context from games2: rest days, game number
last, gnum, ctx = {}, collections.Counter(), {}
for g in G:
    d = datetime.date(int(g['date'][:4]), int(g['date'][4:6]), int(g['date'][6:]))
    c = {}
    for T in (g['H'], g['V']):
        s = g['season']; key = (s, T)
        rest = (d - last[key]).days if key in last else 9
        gnum[key] += 1; c[T] = (min(rest, 5), gnum[key]); last[key] = d
    ctx[str(g['gid'])] = c
# --- per game assemble
games = collections.defaultdict(list)
for b in B:
    if b['fd']: games[b['gid']].append(b)
cols = None; rows = []; meta = []
posallow = collections.defaultdict(lambda: [0.0, 0.0])      # (season, opp, pos) -> [first team baskets by pos, games]
order = sorted(games, key=lambda g: (games[g][0]['date'], g))
pending = []
for gid in order:
    R = games[gid]; b0 = R[0]; S = b0['season']; H, V = b0['H'], b0['V']
    e = ev.get((b0['date'], H, V)); SS = sel.get(e, {})
    def med_cons(x):
        v = sorted(dec(c) for k, c in x['books'].items() if k not in ('10', '0'))
        return v[len(v) // 2] if v else None
    imp = {x['name']: 1 / dec(x['fd']) for x in R}
    tot = {T: sum(imp[x['name']] for x in R if x['team'] == T) for T in (H, V)}
    rk_team = {}; rk_game = {x['name']: i for i, x in enumerate(sorted(R, key=lambda x: -imp[x['name']]))}
    for T in (H, V):
        for i, x in enumerate(sorted([x for x in R if x['team'] == T], key=lambda x: -imp[x['name']])): rk_team[x['name']] = i
    c = ctx.get(str(gid), {})
    for x in R:
        T = x['team']; O = V if T == H else H
        pos, op = SS.get(F.norm(x['name'])) or SS.get('i:' + F.ikey(x['name'])) or ('?', None)
        pos = (pos or '?')[:1]
        df = dec(x['fd']); mc = med_cons(x)
        pa = posallow[(S, O, pos)]; pl = posallow[(S, 'LG', pos)]
        k = idx.get((str(gid), x['name']))
        fv = list(X0[k[0], k[1]]) + list(X3[k[0], k[1]]) if k else [np.nan] * len(FN)
        rest_t, gn = c.get(T, (2, 40)); rest_o = c.get(O, (2, 40))[0]
        r = {'am': x['fd'], 'imp_fd': 1 / df, 'fd_vs_cons': (df / mc) if mc else 1.0, 'nbooks': len(x['books']),
             'open_move': (math.log(dec(op)) - math.log(df)) if op else 0.0,
             'rk_team': rk_team[x['name']], 'rk_game': rk_game[x['name']], 'team_imp': tot[T], 'team_imp_diff': tot[T] - tot[O],
             'pos_C': 1.0 if pos == 'C' else 0.0, 'pos_G': 1.0 if pos == 'G' else 0.0, 'pos_F': 1.0 if pos == 'F' else 0.0,
             'opp_pos_allow': ((pa[0] + 2) / (pa[1] + 10)) - ((pl[0] + 2) / (pl[1] + 10)),
             'p_model': x['p'], 'pb': x['pb'], 'edge': x['pb'] * df - 1, 'pteam': x['pteam'], 'share': x['share'],
             'jumper': 1.0 if x['jumper'] else 0.0, 'ptip': x['ptip'] if T == H else 1 - x['ptip'],
             'home': 1.0 if T == H else 0.0, 'rest': rest_t, 'rest_diff': rest_t - rest_o, 'b2b': 1.0 if rest_t == 1 else 0.0,
             'gnum': gn}
        for n, v in zip(FN, fv): r[n] = float(v)
        if cols is None: cols = list(r)
        rows.append([r[k_] for k_ in cols]); meta.append((gid, S, x['date'], x['name'], T, x['y'], df))
    # update positional allowance AFTER the game: position of each team's first basket scorer (first FG by team)
    g2 = None
    for x in R:
        pass
    fbT = [x for x in R if x['y']]
    if fbT:
        x = fbT[0]; T = x['team']; O = V if T == H else H
        pos = ((SS.get(F.norm(x['name'])) or ('?', None))[0] or '?')[:1]
        for p_ in 'CFG':
            posallow[(S, O, p_)][0] += 1.0 if pos == p_ else 0.0; posallow[(S, O, p_)][1] += 1
            posallow[(S, 'LG', p_)][0] += 1.0 if pos == p_ else 0.0; posallow[(S, 'LG', p_)][1] += 1
A = np.array(rows, dtype=np.float64)
np.save('W.npy', A); json.dump({'cols': cols, 'meta': meta}, open('Wmeta.json', 'w'))
print(A.shape, 'nan share', np.isnan(A).mean(), collections.Counter(m[1] for m in meta))
