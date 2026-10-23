"""Walk-forward replay: pre-game features for every game (state from nba_fb.State), seasonal refits of the
team + share models on earlier seasons only, then per-starter model probabilities. -> rows.json"""
import json, math, sys
import numpy as np
from scipy.optimize import minimize
sys.path.insert(0, '/home/claude/theticketroom/nba')
import nba_fb as F

G = json.load(open('games.json'))
SH = ['x_fbc', 'x_tf', 'x_ef', 'x_fs', 'x_fg', 'x_j', 'x_new']
st = F.State()
recs = []
for g in G:
    H, V = g['H'], g['V']
    keys = {T: [(n, st.key(n, team=T)) for n in g['starters'][T]] for T in (H, V)}
    jh = st.jumper([k for _, k in keys[H]]); ja = st.jumper([k for _, k in keys[V]])
    ptip = st.p_tip_home(jh, ja) if (jh and ja) else 0.5
    lt = math.log(ptip / (1 - ptip))
    fd = (st.T.get(H, {}).get('first') or .5) - (st.T.get(V, {}).get('first') or .5)
    X = {}
    for T in (H, V):
        J = jh if T == H else ja
        rows = []
        for n, k in keys[T]:
            f = st.feats(k) if k else F.State().feats(None)
            f['x_j'] = 1.0 if (k and k == J) else 0.0
            rows.append([n] + [f[c] for c in SH])
        X[T] = rows
    recs.append({'gid': g['gid'], 'season': g['season'], 'date': g['date'], 'H': H, 'V': V, 'lt': lt, 'fd': fd,
                 'ptip': ptip, 'X': X, 'fb': g['fb'], 'fbT': g['fbT'], 'jumpers': g['jumpers'], 'tip': g['tip']})
    st.update(g)
print('replayed', len(recs), file=sys.stderr)

def fit_team(R):
    R = [r for r in R if r['fbT'] in (r['H'], r['V'])]
    Xm = np.array([[1, r['lt'], r['fd']] for r in R]); y = np.array([1.0 if r['fbT'] == r['H'] else 0.0 for r in R])
    def nll(b):
        z = Xm @ b; return np.sum(np.logaddexp(0, z) - y * z)
    return minimize(nll, np.zeros(3), method='BFGS').x

def fit_share(R):
    blocks = []
    for r in R:
        T = r['fbT']
        if T not in (r['H'], r['V']): continue
        rows = r['X'][T]; names = [x[0] for x in rows]
        if r['fb'] not in names: continue
        blocks.append((np.array([x[1:] for x in rows]), names.index(r['fb'])))
    A = np.stack([b[0] for b in blocks]); idx = np.array([b[1] for b in blocks])
    def nll(w):
        u = A @ w; m = u.max(1, keepdims=True); lse = (m[:, 0] + np.log(np.exp(u - m).sum(1)))
        return np.sum(lse - u[np.arange(len(idx)), idx])
    return minimize(nll, np.zeros(len(SH)), method='BFGS').x

rows = []
for S in range(2016, 2026):
    train = [r for r in recs if r['season'] < S]
    bt = fit_team(train); ws = fit_share(train)
    print(S, 'team', np.round(bt, 3), 'share', np.round(ws, 3), file=sys.stderr)
    for r in recs:
        if r['season'] != S: continue
        z = bt[0] + bt[1] * r['lt'] + bt[2] * r['fd']; ph = 1 / (1 + math.exp(-z))
        for T, pt in ((r['H'], ph), (r['V'], 1 - ph)):
            xs = np.array([x[1:] for x in r['X'][T]]); u = xs @ ws; e = np.exp(u - u.max()); sh = e / e.sum()
            for i, x in enumerate(r['X'][T]):
                rows.append({'gid': r['gid'], 'season': S, 'date': r['date'], 'H': r['H'], 'V': r['V'], 'team': T,
                             'name': x[0], 'p': float(pt * sh[i] * F.BENCH), 'pteam': pt, 'share': float(sh[i]),
                             'jumper': bool(x[SH.index('x_j') + 1]), 'ptip': r['ptip'] if T == r['H'] else 1 - r['ptip'],
                             'y': 1 if r['fb'] == x[0] else 0, 'fbT': r['fbT']})
json.dump(rows, open('rows.json', 'w'))
print('rows', len(rows))
