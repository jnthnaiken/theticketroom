import numpy as np, pandas as pd, itertools, sys
from engine import score_matrix
exec(open('acc.py').read().split('LINES=')[0])   # reuse data + run()
MARG=1.06   # assumed book overround on a two-way totals/team-total line
def legs(o):
    M=score_matrix(o.ah.values,o.aa.values,-0.08); M0=score_matrix(o.clh.values,o.cla.values,-0.08); k=np.arange(M.shape[1]); rows=[]
    defs=[]
    for ln in (1.5,2.5,3.5): defs+= [(f'Over {ln}',(k[:,None]+k[None,:])>ln,(o.FTHG+o.FTAG)>ln),(f'Under {ln}',(k[:,None]+k[None,:])<ln,(o.FTHG+o.FTAG)<ln)]
    for ln in (0.5,1.5,2.5):
        defs+=[(f'Home o{ln}',(k[:,None]>ln)&np.ones((1,len(k)),bool),o.FTHG>ln),(f'Home u{ln}',(k[:,None]<ln)&np.ones((1,len(k)),bool),o.FTHG<ln),
               (f'Away o{ln}',np.ones((len(k),1),bool)&(k[None,:]>ln),o.FTAG>ln),(f'Away u{ln}',np.ones((len(k),1),bool)&(k[None,:]<ln),o.FTAG<ln)]
    for nm,mask,y in defs:
        p=(M*mask).sum((1,2)); pm=(M0*mask).sum((1,2))
        rows.append(pd.DataFrame({'date':o.date.values,'mid':o.index.values,'season':o.season.values,'leg':nm,'p':p,'pm':pm,'hit':y.values,'price':1/(pm*MARG)}))
    return pd.concat(rows)
def daily(Lg,n=2,minleg=1.40,rank='p',agree=False):
    q=Lg[Lg.price>=minleg]
    if agree: q=q[q.p>=q.pm]
    out=[]
    for d,g in q.groupby('date'):
        g=g.sort_values(rank,ascending=False).drop_duplicates('mid')
        if len(g)<n: continue
        s=g.head(n); out.append((d,s.season.iloc[0],s.p.prod(),s.hit.all(),s.price.prod()))
    r=pd.DataFrame(out,columns=['date','season','pj','win','price']); r['pl']=np.where(r.win,r.price-1,-1.); return r
def rep(r,lab): print(f"{lab:44s} days={len(r):4d} hit={r.win.mean():.3f} predicted={r.pj.mean():.3f} avg_price={r.price.mean():.2f} (+{(r.price.mean()-1)*100:.0f}) est_units={r.pl.sum():+.1f} roi={r.pl.mean():+.3f}")
per=sys.argv[1] if len(sys.argv)>1 else 'tune'
ss=range(2020,2023) if per=='tune' else range(2023,2027)
o=run(ss,['own','opp','rat']); Lg=legs(o)
if per=='tune':
  for n in (2,3):
    for ml in (1.30,1.40,1.50,1.60):
      for ag in (False,True):
        rep(daily(Lg,n,ml,'p',ag),f'n={n} minleg={ml} agree={ag}')
else:
  rep(daily(Lg,2,float(sys.argv[2]),'p',sys.argv[3]=='1'),'HOLDOUT pre-registered')
  r=daily(Lg,2,float(sys.argv[2]),'p',sys.argv[3]=='1'); print(r.groupby('season').agg(days=('win','size'),hit=('win','mean'),pred=('pj','mean'),units=('pl','sum')).round(3))
