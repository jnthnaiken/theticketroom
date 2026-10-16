import numpy as np, pandas as pd, statsmodels.api as sm
from engine import score_matrix, logloss, logit
from sim import luck_table
from sklearn.metrics import roc_auc_score
t=pd.read_pickle('../data/close_lu.pkl')   # has clh/cla (closing-implied), ilh/ila (pre-implied), lh/la (ratings), lu_h/lu_a
t=t[t.season>=2019].reset_index(drop=True)
L=luck_table(t,4)
for c in L: t[c]=L[c].values
def fitb(tr,off_h,off_a,cols):
    d=pd.concat([pd.DataFrame({'y':tr.FTHG,'off':np.log(tr[off_h]),**{c:tr[c+'_h'] for c in cols}}),pd.DataFrame({'y':tr.FTAG,'off':np.log(tr[off_a]),**{c:tr[c+'_a'] for c in cols}})]).dropna()
    return sm.GLM(d.y,sm.add_constant(d[cols]),family=sm.families.Poisson(),offset=d.off).fit().params
t['own_h'],t['opp_h'],t['own_a'],t['opp_a']=t.own_h,t.opp_h,t.own_a,t.opp_a
t['rat_h']=np.log(t.lh/t.clh); t['rat_a']=np.log(t.la/t.cla)   # ratings vs market, as a feature
def run(seasons,cols):
    out=[]
    for s in seasons:
        tr=t[t.season<s]; te=t[t.season==s].copy()
        if cols:
            p=fitb(tr,'clh','cla',cols)
            te['ah']=te.clh*np.exp(p.const+sum(p[c]*te[c+'_h'].fillna(0) for c in cols)); te['aa']=te.cla*np.exp(p.const+sum(p[c]*te[c+'_a'].fillna(0) for c in cols))
        else: te['ah'],te['aa']=te.clh,te.cla
        out.append(te)
    return pd.concat(out)
LINES=[('G',1.5),('G',2.5),('G',3.5),('H',0.5),('H',1.5),('H',2.5),('A',0.5),('A',1.5),('A',2.5)]
def evals(o):
    M=score_matrix(o.ah.values,o.aa.values,-0.08); k=np.arange(M.shape[1]); res={}
    for typ,ln in LINES:
        if typ=='G': mask=(k[:,None]+k[None,:])>ln; y=(o.FTHG+o.FTAG)>ln
        elif typ=='H': mask=(k[:,None]>ln)&np.ones_like(k[None,:],bool); y=o.FTHG>ln
        else: mask=np.ones_like(k[:,None],bool)&(k[None,:]>ln); y=o.FTAG>ln
        p=(M*mask).sum((1,2)); res[f'{typ}{ln}']=(logloss(y.astype(int).values,p)*1e4, roc_auc_score(y,p))
    return res
for name,cols in [('market only',[]),('market+luck',['own','opp']),('market+luck+ratings',['own','opp','rat']),('market+ratings',['rat']),('market+luck+lineup',['own','opp','lu'])]:
    for per,ss in (('tune 2020-22',range(2020,2023)),('HOLDOUT 2023-26',range(2023,2027))):
        o=run(ss,cols); r=evals(o)
        print(f"{name:22s} {per:16s} "+' '.join(f"{k}:{v[0]:.0f}/{v[1]:.3f}" for k,v in r.items()))
