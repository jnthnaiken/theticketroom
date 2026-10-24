"""FBL-REBUILD: walk-forward per-starter probabilities 2020-25 for each candidate model -> probs.json {model: {gid|name: p}}"""
import json, numpy as np, lightgbm as lgb
from search import X, NM, y, season, ok, fit, M3
PROD = ['o_x_ef', 'o_x_tf', 'o_x_fs', 'o_x_fbc', 'o_x_fg', 'o_x_j', 'o_x_new', 'o_t_tip', 'o_t_first']
SELF = json.load(open('selected3.json'))['final']
MODELS = {'prod_logit': PROD, 'fwd_select': SELF, 'fbl_only': M3['names'], 'everything': NM}
G = M3['games']; out = {}
def store(name, S, te, p):
    d = out.setdefault(name, {})
    for gi, row in zip(te, p):
        for nm, v in zip(G[gi]['names'], row): d[f"{G[gi]['gid']}|{nm}"] = float(v)
for S in range(2020, 2026):
    tr = ok & (season < S); te = np.where(season == S)[0]
    for name, feats in MODELS.items():
        idx = [NM.index(f) for f in feats]; w = fit(idx, X[tr], y[tr])
        u = X[te][:, :, idx] @ w; u -= u.max(1, keepdims=True); p = np.exp(u); p /= p.sum(1, keepdims=True)
        store(name, S, te, p)
    tri = np.where(tr)[0]; lab = np.zeros((len(tri), 10)); lab[np.arange(len(tri)), y[tri]] = 1
    m = lgb.LGBMClassifier(objective='binary', verbose=-1, n_estimators=400, learning_rate=0.02, num_leaves=7, min_child_samples=500,
                           subsample=0.8, subsample_freq=1, colsample_bytree=0.7).fit(X[tri].reshape(-1, X.shape[2]), lab.ravel())
    s = m.predict_proba(X[te].reshape(-1, X.shape[2]))[:, 1].reshape(-1, 10); p = s / s.sum(1, keepdims=True)
    store('gbm', S, te, p)
    print(S, flush=True)
out['ensemble'] = {k: 0.5 * out['fwd_select'][k] + 0.5 * out['gbm'][k] for k in out['gbm']}
json.dump(out, open('probs.json', 'w'))
