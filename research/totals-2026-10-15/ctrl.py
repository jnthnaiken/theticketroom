import numpy as np, pandas as pd
from sim import *
m=pd.read_pickle('../data/feats.pkl'); imp=pd.read_pickle('../data/implied.pkl'); m=m.join(imp,how='inner')
o=m[(m.season>=2019)&(m.season<=2022)&m.o_max.notna()].copy()
for name,p in (('fair=Avg devig','pm_pre'),('fair=closing devig (cheat ref)','pm_cl')):
    o['pp']=o[p]
    print(name,end=': ')
    for th in (0.0,0.01,0.02,0.03,0.05):
        b=bets(o,'o_max','u_max',p='pp',th=th); print(f'th{th}: n={len(b)} roi={b.pl.mean():+.3f}',end='  ')
    print()
