import numpy as np, pandas as pd, statsmodels.api as sm
from scipy.optimize import minimize
from engine import logloss, logit, score_matrix, pois_pmf
m=pd.read_pickle('../data/feats.pkl'); m=m[m.pm_pre.notna()&m.xH.notna()].copy()
# implied 1X2 (devig)
ih,idr,ia=1/m.xH,1/m.xD,1/m.xA; s=ih+idr+ia; m['qh'],m['qd'],m['qa']=ih/s,idr/s,ia/s
# grid solve (lh,la) minimising squared error to qh,qa,pm_pre under DC rho=-0.08
G=np.linspace(.2,4.2,81); LH,LA=np.meshgrid(G,G,indexing='ij'); lh=LH.ravel(); la=LA.ravel()
M=score_matrix(lh,la,rho=-0.08); k=np.arange(M.shape[1]); hw=(k[:,None]>k[None,:]); aw=(k[:,None]<k[None,:]); ov=(k[:,None]+k[None,:])>2.5
PH=(M*hw).sum((1,2)); PA=(M*aw).sum((1,2)); PO=(M*ov).sum((1,2))
Q=np.c_[m.qh,m.qa,m.pm_pre].astype(float)
best=[]
for i in range(0,len(Q),2000):
    q=Q[i:i+2000]; e=(PH[None]-q[:,0:1])**2+(PA[None]-q[:,1:2])**2+(PO[None]-q[:,2:3])**2
    best.append(e.argmin(1))
b=np.concatenate(best); m['ilh'],m['ila']=lh[b],la[b]
# refine is skipped; grid step 0.05
print('implied mean lh,la',m.ilh.mean().round(3),m.ila.mean().round(3),'actual',m.FTHG.mean().round(3),m.FTAG.mean().round(3))
def pov(l,line): P=pois_pmf(np.asarray(l)); kk=np.arange(P.shape[1]); return (P*(kk>line)).sum(1)
rows=[]
for side,L,ML,G_ ,luck_for,luck_opp in [('home','ilh','lh','FTHG','h_','a_'),('away','ila','la','FTAG','a_','h_')]:
    for line in (0.5,1.5,2.5):
        y=(m[G_]>line).astype(int).values
        pm=pov(m[L],line); pmod=pov(m[ML],line)
        # team-specific luck: own finishing luck (gf6-xf6) and opponent's conceding luck (ga6-xa6)
        own=(m[luck_for+'gf6']-m[luck_for+'xf6']).values; opp=(m[luck_opp+'ga6']-m[luck_opp+'xa6']).values
        df=pd.DataFrame(dict(y=y,mk=logit(pm),md=logit(pmod),own=own,opp=opp,season=m.season.values)).dropna()
        tr=df[(df.season>=2015)&(df.season<=2022)]
        for name,X in [('mkt+model',['mk','md']),('mkt+luck',['mk','own','opp'])]:
            r=sm.Logit(tr.y,sm.add_constant(tr[X])).fit(disp=0)
            rows.append((side,line,name,' '.join(f"{c}:{r.tvalues[c]:+.1f}" for c in X)))
        rows.append((side,line,'LL mkt vs model',f"{logloss(tr.y,1/(1+np.exp(-tr.mk))):.4f} vs {logloss(tr.y,1/(1+np.exp(-tr.md))):.4f}"))
for r in rows: print(r)
m[['ilh','ila']].to_pickle('../data/implied.pkl')
