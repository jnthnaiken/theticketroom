"""FBL-REBUILD betting backtest. For each candidate model: market blend fitted walk-forward exactly as fbr/join.py,
then (a) out-of-sample log loss on fully priced games vs the market alone, (b) the shipped board (4 value anchors at
1u + 2 moons per anchor differing by >= 2 legs, 11 x 0.10u) at FanDuel prices, per season."""
import json, math, sys, collections, itertools
import numpy as np
from scipy.optimize import minimize
sys.path.insert(0, '/home/claude/theticketroom/nba'); import nba_fb as F
PR = json.load(open('probs.json')); B = json.load(open('/home/claude/fbr/bets.json'))
def dec(am): return 1 + (am / 100 if am > 0 else 100 / -am)
games = collections.defaultdict(list)
for b in B: games[b['gid']].append(b)
def mq(R):
    q = {}
    for x in R:
        bk = x['books']; c = bk.get('0') if '0' in bk else bk.get(0)
        if c is None and bk:
            v = sorted(dec(c) for k, c in bk.items() if str(k) != '0'); dd = v[len(v) // 2] if v else None
        else: dd = dec(c) if c is not None else None
        if dd: q[x['name']] = 1 / dd
    return q

def blended(model):
    """-> {(gid,name): pb} walk-forward blend of market + model (model=None -> production p as in bets.json)"""
    pm = (lambda x: x['p']) if model is None else (lambda x: PR[model].get(f"{x['gid']}|{x['name']}", 0.1) * F.BENCH)
    full = {}
    for gid, R in games.items():
        q = mq(R)
        if len(q) == len(R) and any(x['y'] for x in R):
            s = sum(q.values()); full[gid] = (np.array([math.log(q[x['name']] / s) for x in R]),
                                               np.array([math.log(max(pm(x), 1e-6)) for x in R]))
    out = {}
    for S in range(2020, 2026):
        tr = [(gid, v) for gid, v in full.items() if games[gid][0]['season'] < S]
        if tr:
            data = [(lm, lp, [x['y'] for x in games[g]].index(1)) for g, (lm, lp) in tr]
            def nll(w):
                t = 0.0
                for lm, lp, i in data:
                    u = w[0] * lm + w[1] * lp; m = u.max(); t += m + math.log(np.exp(u - m).sum()) - u[i]
                return t
            w = minimize(nll, np.array([0.1, 1.0]), method='Nelder-Mead').x
        else: w = np.array([0.0, 1.0])
        for gid, R in games.items():
            if R[0]['season'] != S: continue
            if gid in full:
                lm, lp = full[gid]; u = w[0] * (lm + math.log(F.BENCH)) + w[1] * lp; u = np.exp(u - u.max()); u = u / u.sum() * F.BENCH
                for x, v in zip(R, u): out[(gid, x['name'])] = float(v)
            else:
                for x in R: out[(gid, x['name'])] = pm(x)
    return out

def rr(legs, unit):
    st = ret = 0.0
    for k in range(2, len(legs) + 1):
        for cb in itertools.combinations(legs, k):
            st += unit
            if all(b['y'] for b in cb): ret += unit * math.prod(b['dfd'] for b in cb)
    return st, ret

def board(R):
    el = [b for b in R if b['dfd'] and b.get('pb') is not None]
    if len(el) < 8: return [], []
    key = lambda b: b['pb'] * b['dfd']; v = [key(b) for b in el]; m = sum(v) / len(v); sd = (sum((x - m) ** 2 for x in v) / len(v)) ** .5 or 1e-9
    pool, per = [], collections.Counter()
    for b in sorted(el, key=lambda b: -key(b)):
        if (key(b) - m) / sd < 0.75 or per[b['gid']] >= 4: continue
        pool.append(b); per[b['gid']] += 1
    A = pool[:4]; P = pool[4:]; M = []
    for a in A:
        ok = [b for b in P if b['gid'] != a['gid']]; got = []
        for cb in itertools.combinations(ok, 3):
            if len({a['gid']} | {x['gid'] for x in cb}) != 4: continue
            if got and len({id(x) for x in got[0]} - {id(x) for x in cb}) < 2: continue
            got.append(cb)
            if len(got) == 2: break
        M += [[a, *cb] for cb in got]
    return A, M

def evaluate(label, pbmap):
    # log loss on fully priced games
    llm = llb = 0.0; n = 0
    days = collections.defaultdict(list)
    for gid, R in games.items():
        q = mq(R); S = R[0]['season']
        if S >= 2021 and len(q) == len(R) and any(x['y'] for x in R):
            i = [x['y'] for x in R].index(1); s = sum(q.values())
            llm += -math.log(q[R[i]['name']] / s); pp = [pbmap[(gid, x['name'])] for x in R]
            llb += -math.log(pp[i] / sum(pp)); n += 1
        for x in R:
            fd = x['books'].get('10') if '10' in x['books'] else x['books'].get(10)
            if S >= 2021: days[(S, x['date'])].append({'gid': gid, 'y': x['y'], 'pb': pbmap[(gid, x['name'])], 'dfd': dec(fd) if fd else None})
    res = collections.defaultdict(lambda: [0, 0, 0.0, 0.0, 0.0])
    for (S, d), R in days.items():
        A, Mn = board(R); r = res[S]
        for b in A: r[0] += 1; r[1] += b['y']; r[2] += (b['dfd'] - 1) if b['y'] else -1
        for mn in Mn:
            st, ret = rr(mn, 0.10); r[3] += st; r[4] += ret - st
    tA = sum(v[2] for v in res.values()); nA = sum(v[0] for v in res.values()); tM = sum(v[4] for v in res.values()); sM = sum(v[3] for v in res.values())
    print(f'{label:12s} ll market {llm/n:.4f} blend {llb/n:.4f} (n={n}) | anchors {nA} hit {sum(v[1] for v in res.values())/max(nA,1):.1%} {tA:+.0f}u ({tA/max(nA,1):+.1%})'
          f' | moons {tM:+.0f}u ({tM/max(sM,1):+.1%}) | board {tA+tM:+.0f}u ({(tA+tM)/max(nA+sM,1):+.1%}) | '
          + ' '.join(f'{s%100}:{v[2]+v[4]:+.0f}' for s, v in sorted(res.items())), flush=True)

if __name__ == '__main__':
    evaluate('production', {(b['gid'], b['name']): b['pb'] for b in B})
    for m in ('prod_logit', 'fwd_select', 'fbl_only', 'everything', 'gbm', 'ensemble'):
        evaluate(m, blended(m))
