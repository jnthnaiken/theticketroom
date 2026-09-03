#!/usr/bin/env python3
"""
nfl_fit.py -- fit the four-term model, and PROVE IT IS CALIBRATED before it prices anything.

Fit on 2021-2024. 2025 is never seen by the fit and is the only thing reported as a check.
The output is a PROBABILITY, not a score, because the whole board turns on comparing it to a
price -- and a number you cannot compare to a price is decoration.
"""
import pandas as pd, numpy as np, json
from sklearn.linear_model import LogisticRegression

D=pd.read_pickle('dec.pkl')
ros=[]
for y in [2021,2022,2023,2024,2025]:
    f='rosters2025.csv' if y==2025 else f'ros{y}.csv'
    r=pd.read_csv(f,usecols=['season','gsis_id','position'],low_memory=False)
    ros.append(r.dropna(subset=['gsis_id']).drop_duplicates(['season','gsis_id']))
R=pd.concat(ros,ignore_index=True).rename(columns={'gsis_id':'pid'})
D=D.merge(R,on=['season','pid'],how='left')
D['pos']=D.position.replace({'FB':'RB'})
D['pos']=D.pos.where(D.pos.isin(['RB','WR','TE','QB']),'WR')
D['i10_share']=(D.i10pg/D.tchpg.replace(0,np.nan)).fillna(0)
D=D.dropna(subset=['tchpg','i10pg','imp','rz_pg']).copy()

# transforms: touches is strongly concave (the 20+ band is a different animal), so log1p it.
D['x_tch']=np.log1p(D.tchpg)
D['x_i10']=np.log1p(D.i10pg)
D['x_shr']=D.i10_share
D['x_imp']=D.imp
D['x_rz'] =D.rz_pg
FEAT=['x_tch','x_i10','x_shr','x_imp','x_rz']
X=pd.concat([D[FEAT],pd.get_dummies(D.pos,prefix='p').astype(float)],axis=1)
FEATS=list(X.columns)
mu,sd=X.mean(),X.std().replace(0,1)
Z=((X-mu)/sd).values
y=D.scored.values
tr=(D.season<=2024).values; te=(D.season==2025).values

m=LogisticRegression(max_iter=5000,C=1.0).fit(Z[tr],y[tr])
p=m.predict_proba(Z)[:,1]
D['p']=p
print(f'fit on {tr.sum():,} rows (2021-24), held out {te.sum():,} rows (2025)\n')
print('coefficients (standardised):')
for f,c in sorted(zip(FEATS,m.coef_[0]),key=lambda z:-abs(z[1])):
    print(f'   {f:8}{c:+7.3f}')

print('\nCALIBRATION on held-out 2025 -- predicted vs actual, by model decile')
T=D[te].copy(); T['d']=pd.qcut(T.p,10,labels=False,duplicates='drop')
print(f'   {"decile":<8}{"n":>6}{"predicted":>11}{"actual":>9}{"gap":>8}   fair price')
worst=0
for d,g in T.groupby('d'):
    pr,ac=g.p.mean(),g.scored.mean()
    worst=max(worst,abs(pr-ac))
    fp=int(round((100*(1-ac)/ac)/5)*5) if ac>0 else 9999
    print(f'   {d:<8}{len(g):>6}{pr:>11.1%}{ac:>9.1%}{(ac-pr)*100:>+7.1f}pp   +{fp}')
print(f'   worst decile gap {worst*100:.1f}pp')

# stratified-lift check of the FITTED probability, the instrument this project trusts
def lift(S,f,ctrl='tchpg',nq=4):
    S=S.dropna(subset=[f,ctrl]).copy(); S['q']=pd.qcut(S[ctrl],nq,labels=False,duplicates='drop')
    hs=ls=nh=nl=0
    for _,g in S.groupby('q'):
        if len(g)<120: continue
        a,b=g[f].quantile(1/3),g[f].quantile(2/3)
        L,H=g[g[f]<=a],g[g[f]>=b]
        if len(L)<30 or len(H)<30: continue
        hs+=H.scored.sum();nh+=len(H);ls+=L.scored.sum();nl+=len(L)
    return hs/nh,ls/nl
h,l=lift(T,'p')
print(f'\n   model probability, lift within usage stratum (2025): {h:.1%} vs {l:.1%}  = {(h-l)*100:+.1f}pp')

# ---- de-vig anchor: expected DISTINCT scorers per team, as a function of implied total -----
tm=D.groupby(['season','game_id','team']).agg(sc=('scored','sum'),imp=('imp','first')).reset_index()
tm['b']=pd.cut(tm.imp,[0,16,19,22,25,28,99])
print('\nde-vig anchor -- distinct rush/rec TD scorers per team, by implied total:')
for b,g in tm.groupby('b',observed=True):
    print(f'   {str(b):<12} n={len(g):<5} mean scorers {g.sc.mean():.2f}')
co=np.polyfit(tm.imp,tm.sc,1)
print(f'   linear fit: scorers = {co[0]:.4f} * implied_total + {co[1]:.3f}')

json.dump({'feats':FEATS,'mu':mu.tolist(),'sd':sd.tolist(),
           'coef':m.coef_[0].tolist(),'intercept':float(m.intercept_[0]),
           'devig':[float(co[0]),float(co[1])]},open('nfl_model.json','w'),indent=1)
print('\nwrote nfl_model.json')
