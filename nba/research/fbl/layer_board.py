"""In-sample check of the two 5/5 layers on the shipped board: drop pool members that are tip favourites (top third
of t_tipd) and/or cold on recent early shots (bottom third of x_ef10). IN-SAMPLE -- the layers were found on these
same seasons."""
import collections, numpy as np, json
import bt
from search import X, NM, M3
idx = {(str(g['gid']), n): (gi, j) for gi, g in enumerate(M3['games']) for j, n in enumerate(g['names'])}
iT, iE = NM.index('t_tipd'), NM.index('o_x_ef10')
allv = np.array([X[gi, j] for gi, j in idx.values()])
qT = np.quantile(allv[:, iT], 2/3); qE = np.quantile(allv[:, iE], 1/3)
def run(label, drop):
    days = collections.defaultdict(list)
    for b in bt.B:
        if b['season'] < 2021: continue
        k = idx.get((str(b['gid']), b['name']))
        if k is None: continue
        f = X[k[0], k[1]]
        fd = b['fd']
        days[(b['season'], b['date'])].append({'gid': b['gid'], 'y': b['y'], 'pb': b['pb'], 'dfd': bt.dec(fd) if fd else None,
                                               'drop': drop(f)})
    res = collections.defaultdict(lambda: [0, 0, 0.0, 0.0, 0.0])
    for (S, d), R in days.items():
        # gate on the full slate (z-score uses everyone), then drop flagged players from the pool
        el = [b for b in R if b['dfd']]
        if len(el) < 8: continue
        key = lambda b: b['pb'] * b['dfd']; v = [key(b) for b in el]; m = sum(v) / len(v); sd = (sum((x - m) ** 2 for x in v) / len(v)) ** .5 or 1e-9
        keep = [b for b in el if not ((key(b) - m) / sd >= 0.75 and b['drop'])]
        for b in keep: b['_z'] = (key(b) - m) / sd
        A, Mn = bt.board([dict(b, dfd=b['dfd']) for b in el if not b['drop']] if True else el)
        r = res[S]
        for b in A: r[0] += 1; r[1] += b['y']; r[2] += (b['dfd'] - 1) if b['y'] else -1
        for mn in Mn: st, ret = bt.rr(mn, 0.10); r[3] += st; r[4] += ret - st
    tA = sum(v[2] for v in res.values()); nA = sum(v[0] for v in res.values()); tM = sum(v[4] for v in res.values()); sM = sum(v[3] for v in res.values())
    print(f'{label:34s} anchors {nA} hit {sum(v[1] for v in res.values())/max(nA,1):.1%} {tA:+.0f}u ({tA/max(nA,1):+.1%}) | moons {tM:+.0f}u | board {tA+tM:+.0f}u ({(tA+tM)/max(nA+sM,1):+.1%}) | anchors by season '
          + ' '.join(f'{s%100}:{v[2]:+.0f}' for s, v in sorted(res.items())) + ' | board ' + ' '.join(f'{s%100}:{v[2]+v[4]:+.0f}' for s, v in sorted(res.items())))
run('shipped (no layer)', lambda f: False)
run('drop tip favourites', lambda f: f[iT] >= qT)
run('drop cold early-shot share', lambda f: f[iE] <= qE)
run('drop both', lambda f: f[iT] >= qT or f[iE] <= qE)
