import time, pickle, numpy as np, pandas as pd, sys
sys.path.insert(0,'.')
import scorer_model as S
H='/tmp/claude-0/-home-claude/42321598-3064-5850-adce-cb9ea84c31db/scratchpad/hist/'
t=time.time()
tm=pd.read_csv(H+'team_matches.csv.gz'); tm['date']=pd.to_datetime(tm['date'])
for c in ('xG','xGA','npxG','npxGA'): tm[c]=tm[c].astype(float)
pm=pd.read_pickle(H+'pm_assigned.pkl'); tr=pickle.load(open(H+'tr.pkl','rb'))
tmx=tm.set_index(['team','date'])
act={k:(v.npxG,max(v.xG-v.npxG,0)) for k,v in zip(tmx.index,tmx.itertuples())}
tr2={}
for k,v in tr.items():
    a=act.get(k)
    tr2[k]=(a[0]/v[3],v[1],a[1],v[3])+v[4:] if a else v
pm=S.player_features(pm,tr2); print('feats',time.time()-t,flush=True)
att,dfn,pen,lav,lg=[],[],[],[],[]
for r in pm[['team','opp','date']].itertuples():
    T=tr.get((r.team,r.date)); O=tr.get((r.opp,r.date))
    att.append(T[0] if T else np.nan); pen.append(T[2] if T else np.nan); lav.append(T[3] if T else np.nan)
    lg.append(T[4] if T else None); dfn.append(O[1] if O else np.nan)
pm['att'],pm['dfn'],pm['tpen'],pm['lavg'],pm['league']=att,dfn,pen,lav,lg
pm['lam_team_stats']=pm['lavg']*pm['att']*pm['dfn']*np.where(pm['home']==1,1.10,1/1.10)
pm['lam_team_mkt']=np.nan
pm.to_pickle(H+'pm_feat.pkl')
res,summ,cal,hits,allte=S.evaluate(pm,2017)
print('AUC',summ); print('top8',hits); print(cal.to_string())
allte.to_pickle(H+'allte.pkl')
