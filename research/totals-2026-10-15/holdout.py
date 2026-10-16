import numpy as np, pandas as pd
from parlay import *
seasons=range(2023,2027)
T=legs_table(seasons); T0=legs_table(seasons,use_layer=False)
print('== PRE-REGISTERED: legs=2 edge>0 p>=0.5 rank=edge ==')
report(parlay(T,2,0.0,0.5,'edge'),'HOLDOUT luck'); report(parlay(T0,2,0.0,0.5,'edge'),'HOLDOUT ctrl')
# singles on holdout
L=luck_table(m,4); o=walk(m,L,['own','opp'],first=2019,seasons=seasons); o=o[o.o_maxc.notna()&o.pm_cl.notna()].copy()
M=score_matrix(o.alh.values,o.ala.values,RHO); M0=score_matrix(o.ilh.values,o.ila.values,RHO); k=np.arange(M.shape[1]); ov=(k[:,None]+k[None,:])>2.5
o['pq']=np.clip(o.pm_cl+((M*ov).sum((1,2))-(M0*ov).sum((1,2))),.01,.99)
print('singles LL gain vs closing market 1e-4:',round((logloss(o.over,o.pm_cl)-logloss(o.over,o.pq))*1e4,2), 'n',len(o))
for th in (0.0,0.02):
    b=bets(o,'o_maxc','u_maxc',p='pq',th=th); o['pp']=o.pm_cl; c=bets(o,'o_maxc','u_maxc',p='pp',th=th)
    print(f'singles th{th}: luck n={len(b)} roi={b.pl.mean():+.4f} | ctrl n={len(c)} roi={c.pl.mean():+.4f}')
    print('   luck by season',{int(s):round(g.pl.mean(),3) for s,g in b.groupby('season')})
