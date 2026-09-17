import numpy as np, pandas as pd, sys, random, math
sys.path.insert(0,'/tmp/claude-0/-home-claude/42321598-3064-5850-adce-cb9ea84c31db/scratchpad/repo/soccer/history')
sys.path.insert(0,'/tmp/claude-0/-home-claude/42321598-3064-5850-adce-cb9ea84c31db/scratchpad/repo/nfl')
import scorer_model as S
from nfl_ev_fit import implied, dec
H='/tmp/claude-0/-home-claude/42321598-3064-5850-adce-cb9ea84c31db/scratchpad/hist/'
df=pd.read_pickle(H+'board_joined.pkl')
df['p_mkt']=[implied(o) for o in df['odds']]; df['dec']=[dec(o) for o in df['odds']]
lg=lambda p: np.log(p/(1-p))
df['blend_avg']=(df['p_mkt']+df['p_model'])/2
df['blend_logit']=1/(1+np.exp(-(lg(df['p_mkt'])+lg(df['p_model']))/2))
nights=sorted(df['date'].unique())
# walk-forward fitted blend
P=pd.Series(np.nan,index=df.index)
for i,d in enumerate(nights):
    if i<6: continue
    tr=df[df['date']<d]; te=df[df['date']==d]
    X=np.column_stack([lg(tr['p_mkt']),np.log(tr['lam'])]); w=S.logit_fit(X,tr['y'].values.astype(float),lam=2.0)
    P[te.index]=S.logit_pred(w,np.column_stack([lg(te['p_mkt']),np.log(te['lam'])]))
df['blend_fit']=P
print('full-sample fit coef (b0, price logit, log model lambda):',np.round(S.logit_fit(np.column_stack([lg(df['p_mkt']),np.log(df['lam'])]),df['y'].values.astype(float),lam=2.0),3))
held=df[df['date']>=nights[6]]
def boot(pk):
    by={d:g for d,g in pk.groupby('date')}; ds=list(by); random.seed(3); o=[]
    for _ in range(3000):
        s=pd.concat([by[x] for x in random.choices(ds,k=len(ds))]); o.append((np.where(s['y']==1,s['dec'],0).sum()-len(s))/len(s))
    o.sort(); return o[150],o[2850]
print(f'\nboard league legs: {len(df)} over {len(nights)} nights; held-out {len(held)} over {len(nights)-6}')
for name,sub in (('ALL 18 nights',df),('held-out 12 nights',held)):
    print(f'\n{name}')
    for k in ['p_mkt','total','p_model','blend_avg','blend_logit']+(['blend_fit'] if name!='ALL 18 nights' else []):
        s=sub.dropna(subset=[k])
        a=S.auc(s[k].values,s['y'].values)
        for n in (4,8):
            pk=s.sort_values(k,ascending=False).groupby('date').head(n)
            roi=(np.where(pk['y']==1,pk['dec'],0).sum()-len(pk))/len(pk)
            lo,hi=boot(pk)
            print(f'  {k:12s} AUC {a:.3f}  top{n}: hit {pk["y"].mean():.0%} of {len(pk):3d}  ROI {roi:+.1%} [{lo:+.0%},{hi:+.0%}]')
df.to_pickle(H+'board_blend.pkl')
