import numpy as np, pandas as pd, statsmodels.api as sm, itertools
from engine import logloss, logit, score_matrix
from feats import team_long
m=pd.read_pickle('../data/feats.pkl'); imp=pd.read_pickle('../data/implied.pkl'); m=m.join(imp,how='inner')
# exponentially weighted luck per team, several half-lives, computed strictly pre-match
t=team_long(m.drop(columns=[c for c in m.columns if c.startswith(('h_','a_'))]))
g=t.groupby(['league','team'],sort=False)
t['lf']=t.gf-t.xf; t['la_']=t.ga-t.xa
t['sotf']=t.gf-0.30*t.sf; t['sota']=t.ga-0.30*t.sa
for hl in (2,4,8):
    for c in ('lf','la_','sotf','sota'):
        t[f'{c}_e{hl}']=g[c].transform(lambda s: s.shift(1).ewm(halflife=hl,min_periods=3).mean())
hs=t[t.home==1].set_index('idx'); as_=t[t.home==0].set_index('idx')
def tbl(hl,kind='x'):
    a,b=('lf','la_') if kind=='x' else ('sotf','sota')
    return pd.DataFrame({'own_h':hs[f'{a}_e{hl}'],'opp_h':as_[f'{b}_e{hl}'],'own_a':as_[f'{a}_e{hl}'],'opp_a':hs[f'{b}_e{hl}']}).reindex(m.index)
res={}
for kind,hl in itertools.product(('x','s'),(2,4,8)):
    L=tbl(hl,kind)
    # stacked long table: one row per side
    long=pd.concat([pd.DataFrame({'y':m.FTHG,'off':np.log(m.ilh),'own':L.own_h,'opp':L.opp_h,'season':m.season,'home':1}),
                    pd.DataFrame({'y':m.FTAG,'off':np.log(m.ila),'own':L.own_a,'opp':L.opp_a,'season':m.season,'home':0})]).dropna()
    tr=long[(long.season>=2015)&(long.season<=2022)]
    r=sm.GLM(tr.y,sm.add_constant(tr[['own','opp']]),family=sm.families.Poisson(),offset=tr.off).fit()
    res[(kind,hl)]=r
    print(kind,hl,'coef',r.params.round(4).to_dict(),'z',r.tvalues.round(1).to_dict(), 'dev gain',round(sm.GLM(tr.y,np.ones((len(tr),1)),family=sm.families.Poisson(),offset=tr.off).fit().deviance-r.deviance,1))
