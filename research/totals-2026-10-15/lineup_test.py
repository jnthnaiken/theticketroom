import numpy as np, pandas as pd, statsmodels.api as sm
from engine import score_matrix, logloss, logit
m=pd.read_pickle('../data/feats.pkl'); imp=pd.read_pickle('../data/implied.pkl'); m=m.join(imp,how='inner')
w=pd.read_pickle('../data/lineup.pkl').rename(columns={'h_team':'uh','a_team':'ua'})
m=m.merge(w[['date','uh','ua','lu_h','lu_a']],on=['date','uh','ua'],how='left')
print('lineup coverage',m.lu_h.notna().mean().round(3))
# closing implied lambdas
t=m[m.AvgCH.notna()&m.pm_cl.notna()].copy()
ih,idr,ia=1/t.AvgCH,1/t.AvgCD,1/t.AvgCA; s=ih+idr+ia
G=np.linspace(.2,4.2,81); LH,LA=np.meshgrid(G,G,indexing='ij'); lh=LH.ravel(); la=LA.ravel()
M=score_matrix(lh,la,rho=-0.08); k=np.arange(M.shape[1]); PH=(M*(k[:,None]>k[None,:])).sum((1,2)); PA=(M*(k[:,None]<k[None,:])).sum((1,2)); PO=(M*((k[:,None]+k[None,:])>2.5)).sum((1,2))
Q=np.c_[ih/s,ia/s,t.pm_cl].astype(float); b=np.concatenate([(((PH[None]-q[:,0:1])**2+(PA[None]-q[:,1:2])**2+(PO[None]-q[:,2:3])**2)).argmin(1) for q in np.array_split(Q,max(1,len(Q)//2000))])
t['clh'],t['cla']=lh[b],la[b]
def L(x,off_h,off_a): return pd.concat([pd.DataFrame({'y':x.FTHG,'off':np.log(x[off_h]),'own':x.lu_h,'opp':x.lu_a,'season':x.season}),pd.DataFrame({'y':x.FTAG,'off':np.log(x[off_a]),'own':x.lu_a,'opp':x.lu_h,'season':x.season})]).dropna()
for lab,x,oh,oa in (('beyond PRE  2015-22',m[(m.season>=2015)&(m.season<=2022)],'ilh','ila'),('beyond PRE  2023-26',m[m.season>=2023],'ilh','ila'),
                    ('beyond CLOSE 2019-22',t[t.season<=2022],'clh','cla'),('beyond CLOSE 2023-26',t[t.season>=2023],'clh','cla')):
    d=L(x,oh,oa); r=sm.GLM(d.y,sm.add_constant(d[['own','opp']]),family=sm.families.Poisson(),offset=d.off).fit()
    print(f'{lab}: n={len(d)} own {r.params.own:+.3f} (z {r.tvalues.own:+.1f})  opp {r.params.opp:+.3f} (z {r.tvalues.opp:+.1f})')
t.to_pickle('../data/close_lu.pkl')
