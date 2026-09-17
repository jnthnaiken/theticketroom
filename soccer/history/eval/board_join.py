import numpy as np, pandas as pd, json, sys, re, unicodedata, pickle
sys.path.insert(0,'/tmp/claude-0/-home-claude/42321598-3064-5850-adce-cb9ea84c31db/scratchpad/repo/soccer/history')
sys.path.insert(0,'/tmp/claude-0/-home-claude/42321598-3064-5850-adce-cb9ea84c31db/scratchpad/repo/nfl')
import scorer_model as S
from nfl_ev_fit import implied, dec
H='/tmp/claude-0/-home-claude/42321598-3064-5850-adce-cb9ea84c31db/scratchpad/hist/'
FT='/tmp/claude-0/-home-claude/42321598-3064-5850-adce-cb9ea84c31db/scratchpad/repo/soccer/feature_test/'
pm=pd.read_pickle(H+'pm_feat.pkl')
tr=pickle.load(open(H+'tr.pkl','rb'))
def norm(s):
    s=unicodedata.normalize('NFKD',str(s or '')).encode('ascii','ignore').decode().lower()
    s=re.sub(r"[']","",s); return re.sub(r'[^a-z0-9]+',' ',s).strip()
names=pm.groupby('pid')['name'].first()
byn={}
for pid,n in names.items(): byn.setdefault(norm(n),[]).append(pid)
toks={k:set(k.split()) for k in byn}
def find(n):
    k=norm(n)
    if k in byn and len(byn[k])==1: return byn[k][0]
    t=set(k.split()); 
    if not t: return None
    last=k.split()[-1]
    hits=[kk for kk,tt in toks.items() if (last in tt or k.split()[0] in tt) and (t<=tt or tt<=t) and len(byn[kk])==1]
    return byn[hits[0]][0] if len(hits)==1 else None
rows=json.load(open(FT+'rows_floor200.json'))
# team ratings index by team -> sorted dates
from collections import defaultdict
tdates=defaultdict(list)
for (t,dt) in tr: tdates[t].append(dt)
for t in tdates: tdates[t].sort()
sys.path.insert(0,FT); import build_rows as BR
def team_state(t,date):
    ds=tdates.get(t)
    if not ds: return None
    import bisect
    i=bisect.bisect_left(ds,date)
    if i<len(ds): return tr[(t,ds[i])]      # pre-match state of the next league game (no info from on/after date... next game is after date: its pre-match state includes games before it only)
    return tr[(t,ds[-1])]
pmg={pid:g.sort_values('date') for pid,g in pm.groupby('pid')}
out=[];miss=0
for r in rows:
    d=pd.Timestamp(r['date'])
    pid=find(r['name'])
    if pid is None: miss+=1; continue
    g=pmg[pid]
    same=g[g['date']==d]
    if len(same):
        x=same.iloc[0]; lam_t=x['lam_team_stats']; src='league'
    else:
        prev=g[g['date']<d]
        if not len(prev): miss+=1; continue
        x=prev.iloc[-1]
        tt=BR.resolve(r.get('team') or '') ; T=team_state(tt,d) if tt else None
        # opponent: from board rows we only have team; use league-average defence
        lam_t=(T[0]*T[3]*(1.10 if r['home'] else 1/1.10)) if T else np.nan; src='cup'
    if pd.isna(lam_t) or x['n_prior']<3: miss+=1; continue
    lam=max(lam_t,.05)*x['share']*x['exp_min']/90+(x['tpen'] if not pd.isna(x['tpen']) else .1)*.95*x['pen_share']*x['exp_min']/90
    out.append(dict(r,pid=int(pid),lam=float(lam),p_model=float(1-np.exp(-lam)),fin=float(x['fin']),src=src))
print(len(rows),'rows',len(out),'joined',miss,'missed')
df=pd.DataFrame(out); df.to_pickle(H+'board_joined.pkl')
df['p_mkt']=[implied(o) for o in df['odds']]
print(df.groupby('src').size())
print('AUC price',round(S.auc(df['p_mkt'].values,df['y'].values),4),' model',round(S.auc(df['p_model'].values,df['y'].values),4),' live TOTAL',round(S.auc(df['total'].values,df['y'].values),4))
print('mean p_model',df['p_model'].mean().round(3),'mean p_mkt',df['p_mkt'].mean().round(3),'rate',df['y'].mean().round(3))
