"""FBL-REBUILD: can a nonlinear learner (gradient-boosted trees, finds interactions on its own) pull more out of the
same 51 features? Walk-forward by season, per-game softmax over the 10 starters. Same select/hold split."""
import json, math, numpy as np, lightgbm as lgb
from search import X, NM, y, season, ok, SEL, HOLD
n10 = X.shape[1]
def run(seasons, obj, params):
    tot, n, per = 0.0, 0, {}
    for S in seasons:
        tr = np.where(ok & (season < S))[0]; te = np.where(ok & (season == S))[0]
        Xtr = X[tr].reshape(-1, X.shape[2]); lab = np.zeros((len(tr), n10)); lab[np.arange(len(tr)), y[tr]] = 1
        if obj == 'binary':
            m = lgb.LGBMClassifier(objective='binary', verbose=-1, **params).fit(Xtr, lab.ravel())
            s = m.predict_proba(X[te].reshape(-1, X.shape[2]))[:, 1].reshape(-1, n10); p = s / s.sum(1, keepdims=True)
        else:
            m = lgb.LGBMRanker(objective='rank_xendcg', verbose=-1, **params).fit(Xtr, lab.ravel().astype(int), group=[n10] * len(tr))
            str_ = m.predict(Xtr).reshape(-1, n10); ste = m.predict(X[te].reshape(-1, X.shape[2])).reshape(-1, n10)
            best = None
            for T in np.linspace(0.1, 3, 30):        # temperature fitted on TRAIN only
                u = str_ * T; u -= u.max(1, keepdims=True); pp = np.exp(u); pp /= pp.sum(1, keepdims=True)
                l = -np.log(pp[np.arange(len(tr)), y[tr]]).mean()
                if best is None or l < best[0]: best = (l, T)
            u = ste * best[1]; u -= u.max(1, keepdims=True); p = np.exp(u); p /= p.sum(1, keepdims=True)
        ll = -np.log(p[np.arange(len(te)), y[te]]); per[S] = round(ll.mean(), 4); tot += ll.sum(); n += len(te)
    return tot / n, per
for obj in ('binary', 'rank'):
    for params in ({'n_estimators': 200, 'learning_rate': 0.03, 'num_leaves': 15, 'min_child_samples': 200},
                   {'n_estimators': 400, 'learning_rate': 0.02, 'num_leaves': 7, 'min_child_samples': 500, 'subsample': 0.8, 'subsample_freq': 1, 'colsample_bytree': 0.7}):
        s, _ = run(SEL, obj, params); h, hp = run(HOLD, obj, params)
        print(obj, params['num_leaves'], f'select {s:.4f} hold {h:.4f}', hp, flush=True)
