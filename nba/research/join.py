"""Join replay rows to BettingPros prices, fit the market blend walk-forward, write the bet table -> bets.json"""
import json, math, sys, collections
import numpy as np
from scipy.optimize import minimize
sys.path.insert(0, '/home/claude/theticketroom/nba')
import nba_fb as F
BP = {'NOR': 'NOP', 'PHO': 'PHX', 'UTH': 'UTA', 'BRK': 'BKN', 'GS': 'GSW', 'NO': 'NOP', 'NY': 'NYK', 'SA': 'SAS'}
code = lambda x: BP.get(x, x)

ev, sel = {}, collections.defaultdict(list)
for line in open('fb_odds.psv', encoding='utf-8'):
    r = line.rstrip('\n').split('|')
    if r[0] == 'E':
        ev[r[2]] = (r[1].replace('-', ''), code(r[4]), code(r[5]))
    elif r[0] == 'S':
        books = {}
        for kv in (r[8] if len(r) > 8 else '').split(','):
            if ':' in kv:
                b, c = kv.split(':')
                try:
                    c = int(c)
                    if c != 49000: books[int(b)] = c
                except ValueError: pass
        sel[r[2]].append({'name': r[4], 'open': r[6], 'books': books})
bykey = {(d, h, a): e for e, (d, h, a) in ev.items()}

rows = json.load(open('rows.json'))
games = collections.defaultdict(list)
for x in rows: games[x['gid']].append(x)

def dec(am): return 1 + (am / 100 if am > 0 else 100 / -am)
joined, miss = [], collections.Counter()
for gid, R in games.items():
    d, H, V = R[0]['date'], R[0]['H'], R[0]['V']
    e = bykey.get((d, H, V))
    if not e:
        # BettingPros dates are ET; shotdetail dates too -- try +/- 1 day for safety
        miss['noevent'] += 1 if R[0]['season'] >= 2020 else 0; continue
    S = sel[e]
    pmap = {}
    for s in S:
        k = F.norm(s['name']); pmap[k] = s
        pmap.setdefault('i:' + F.ikey(s['name']), s)
    ok = True
    for x in R:
        s = pmap.get(F.norm(x['name'])) or pmap.get('i:' + F.ikey(x['name']))
        x['books'] = s['books'] if s else {}
    joined.append(R)
print('priced games', len(joined), dict(miss), file=sys.stderr)

def mkt(R):
    q = {}
    for x in R:
        b = x['books']; c = b.get(0)
        if c is None and b:
            v = sorted(dec(c) for k, c in b.items() if k != 0); c = None; dd = v[len(v) // 2] if v else None
        else:
            dd = dec(c) if c is not None else None
        if dd: q[x['name']] = 1 / dd
    return q

# per team-pair blend is over all 10 starters of the game (as production: market over the game's starters)
def fit_blend(Gs):
    data = []
    for R in Gs:
        q = mkt(R)
        if len(q) < len(R) or not any(x['y'] for x in R): continue
        s = sum(q.values())
        lm = np.array([math.log(q[x['name']] / s) for x in R]); lp = np.array([math.log(x['p']) for x in R])
        data.append((lm, lp, [x['y'] for x in R].index(1)))
    def nll(w):
        t = 0.0
        for lm, lp, i in data:
            u = w[0] * lm + w[1] * lp; m = u.max(); t += m + math.log(np.exp(u - m).sum()) - u[i]
        return t
    return minimize(nll, np.array([0.1, 1.0]), method='Nelder-Mead').x, len(data)

bets = []
for S in range(2020, 2026):
    train = [R for R in joined if R[0]['season'] < S]
    if train:
        w, n = fit_blend(train)
    else:
        w, n = np.array([0.0, 1.0]), 0
    print(S, 'blend', np.round(w, 3), 'on', n, file=sys.stderr)
    for R in joined:
        if R[0]['season'] != S: continue
        q = mkt(R); full = len(q) == len(R)
        if full:
            s = sum(q.values())
            us = {x['name']: w[0] * math.log(q[x['name']] / s * F.BENCH) + w[1] * math.log(x['p']) for x in R}
            m = max(us.values()); den = sum(math.exp(u - m) for u in us.values())
        for x in R:
            pb = (math.exp(us[x['name']] - m) / den * F.BENCH) if full else x['p']
            pm = (q[x['name']] / sum(q.values()) * F.BENCH) if full else None
            fd = x['books'].get(10)
            bets.append({k: x[k] for k in ('gid', 'season', 'date', 'H', 'V', 'team', 'name', 'p', 'pteam', 'share', 'jumper', 'ptip', 'y')}
                        | {'pb': pb, 'pm': pm, 'fd': fd, 'books': x['books']})
json.dump(bets, open('bets.json', 'w'))
print('bets rows', len(bets), 'with FD', sum(1 for b in bets if b['fd']))
