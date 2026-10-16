import numpy as np, pandas as pd
from parlay import *
seasons=range(2023,2027)
L=luck_table(m,4); o=walk(m,L,['own','opp'],first=2019,seasons=seasons); o=o[o.o_maxc.notna()&o.pm_cl.notna()].copy()
M=score_matrix(o.alh.values,o.ala.values,RHO); M0=score_matrix(o.ilh.values,o.ila.values,RHO); k=np.arange(M.shape[1]); ov=(k[:,None]+k[None,:])>2.5
o['pq']=np.clip(o.pm_cl+((M*ov).sum((1,2))-(M0*ov).sum((1,2))),.01,.99)
y=o.over.values; d=-(y*np.log(o.pm_cl)+(1-y)*np.log(1-o.pm_cl))+(y*np.log(o.pq)+(1-y)*np.log(1-o.pq))
o['d']=d.values; g=o.groupby('date').d.sum(); n=len(o)
rng=np.random.default_rng(1); bs=[rng.choice(g.values,len(g)).sum()/n for _ in range(4000)]
print('LL gain',round(d.mean()*1e4,2),'95% CI',np.percentile(bs,[2.5,97.5]).round(6)*1e4,'P(gain<=0)',np.mean(np.array(bs)<=0))
T=legs_table(seasons); r=parlay(T,2,0.0,0.5,'edge'); bp=[rng.choice(r.pl.values,len(r)).mean() for _ in range(4000)]
print('parlay roi',round(r.pl.mean(),3),'95% CI',np.percentile(bp,[2.5,97.5]).round(3),'P(roi<=0)',np.mean(np.array(bp)<=0))
