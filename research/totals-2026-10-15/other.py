import numpy as np, pandas as pd, statsmodels.api as sm
from engine import logloss, logit, score_matrix
from feats import team_long
raw=pd.read_pickle('../data/fd_all.pkl')
LG=['Championship','Eredivisie','Primeira','Jupiler','Scot_Prem','EPL','La_liga','Serie_A','Bundesliga','Ligue_1']
r=raw[raw.league.isin(LG)].copy()
r['d']=pd.to_datetime(r.date); r=r.sort_values(['date','league']).reset_index(drop=True)
o_pre=r['Avg>2.5'].fillna(r.get('BbAv>2.5')); u_pre=r['Avg<2.5'].fillna(r.get('BbAv<2.5'))
r['pm_cl']=(1/r['AvgC>2.5'])/((1/r['AvgC>2.5'])+(1/r['AvgC<2.5']))
xH=r.AvgCH; xD=r.AvgCD; xA=r.AvgCA
ih,idr,ia=1/xH,1/xD,1/xA; s=ih+idr+ia; r['qh'],r['qa']=ih/s,ia/s
r=r[r.pm_cl.notna()&r.qh.notna()&r.HST.notna()&r['MaxC>2.5'].notna()].copy()
G=np.linspace(.2,4.2,81); LH,LA=np.meshgrid(G,G,indexing='ij'); lh=LH.ravel(); la=LA.ravel()
M=score_matrix(lh,la,rho=-0.08); k=np.arange(M.shape[1]); PH=(M*(k[:,None]>k[None,:])).sum((1,2)); PA=(M*(k[:,None]<k[None,:])).sum((1,2)); PO=(M*((k[:,None]+k[None,:])>2.5)).sum((1,2))
Q=np.c_[r.qh,r.qa,r.pm_cl].astype(float); b=np.concatenate([(((PH[None]-q[:,0:1])**2+(PA[None]-q[:,1:2])**2+(PO[None]-q[:,2:3])**2)).argmin(1) for q in np.array_split(Q,max(1,len(Q)//2000))])
r['ilh'],r['ila']=lh[b],la[b]; r=r.reset_index(drop=True)
r['hnpxG']=np.nan; r['anpxG']=np.nan
t=team_long(r.assign(hnpxG=0.0,anpxG=0.0)); g=t.groupby(['league','team'],sort=False)
t['lf']=t.gf-.30*t.sf; t['lA']=t.ga-.30*t.sa
for c in ('lf','lA'): t[c+'e']=g[c].transform(lambda s_: s_.shift(1).ewm(halflife=4,min_periods=3).mean())
hs=t[t.home==1].set_index('idx'); as_=t[t.home==0].set_index('idx')
r['own_h'],r['opp_h'],r['own_a'],r['opp_a']=hs.lfe.reindex(r.index).values,as_.lAe.reindex(r.index).values,as_.lfe.reindex(r.index).values,hs.lAe.reindex(r.index).values
r['tier']=np.where(r.league.isin(LG[:5]),'second','top5')
def long(x): return pd.concat([pd.DataFrame({'y':x.FTHG,'off':np.log(x.ilh),'own':x.own_h,'opp':x.opp_h}),pd.DataFrame({'y':x.FTAG,'off':np.log(x.ila),'own':x.own_a,'opp':x.opp_a})]).dropna()
for tier in ('second','top5'):
  R=r[r.tier==tier]; outs=[]
  for s_ in range(2021,2027):
    lr=long(R[(R.season>=2019)&(R.season<s_)]); fit=sm.GLM(lr.y,sm.add_constant(lr[['own','opp']]),family=sm.families.Poisson(),offset=lr.off).fit()
    te=R[R.season==s_].copy(); p=fit.params
    te['alh']=te.ilh*np.exp(p.const+p.own*te.own_h.fillna(0)+p.opp*te.opp_h.fillna(0)); te['ala']=te.ila*np.exp(p.const+p.own*te.own_a.fillna(0)+p.opp*te.opp_a.fillna(0))
    outs.append(te)
  o=pd.concat(outs)
  M1=score_matrix(o.alh.values,o.ala.values,-0.08); M0=score_matrix(o.ilh.values,o.ila.values,-0.08); ov=(k[:,None]+k[None,:])>2.5
  o['pq']=np.clip(o.pm_cl+((M1*ov).sum((1,2))-(M0*ov).sum((1,2))),.01,.99)
  y=(o.FTHG+o.FTAG>2.5).astype(int)
  print(tier,'n',len(o),'shots-luck LL gain vs close 1e-4',round((logloss(y,o.pm_cl)-logloss(y,o.pq))*1e4,2),'last fit',fit.params.round(4).to_dict(),'z',fit.tvalues.round(1).to_dict())
  for lab,pp in (('luck',o.pq),('ctrl',o.pm_cl)):
    eo=pp*o['MaxC>2.5']-1; eu=(1-pp)*o['MaxC<2.5']-1
    for th in (0.0,0.02):
      bo=eo>th; bu=(eu>th)&~bo
      pl=np.r_[np.where(y[bo]==1,o['MaxC>2.5'][bo]-1,-1),np.where(y[bu]==0,o['MaxC<2.5'][bu]-1,-1)]
      print(f'   {lab} th{th} n={len(pl)} roi={pl.mean():+.4f}')
