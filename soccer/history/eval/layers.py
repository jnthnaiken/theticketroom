import numpy as np, pandas as pd, time, json, sys
sys.path.insert(0,'/tmp/claude-0/-home-claude/42321598-3064-5850-adce-cb9ea84c31db/scratchpad/repo/soccer/history')
import scorer_model as S
from sklearn.ensemble import HistGradientBoostingClassifier
H='/tmp/claude-0/-home-claude/42321598-3064-5850-adce-cb9ea84c31db/scratchpad/hist/'
t0=time.time()
pm=pd.read_pickle(H+'pm_feat.pkl').sort_values(['pid','date']).reset_index(drop=True)
for c in ['time','goals','shots','xG','npg','npxG','xA','key_passes','xGChain','xGBuildup']: pm[c]=pm[c].astype(float)
g=pm.groupby('pid',sort=False)
def ew(col,hl):  # pre-match EW mean, shifted
    return g[col].transform(lambda s: s.shift().ewm(halflife=hl,min_periods=1).mean())
pm['m90']=pm['time']/90
for hl,tag in ((5,'s'),(30,'l')):
    pm['min_'+tag]=ew('time',hl)
    for c in ['npxG','shots','xA','key_passes','xGChain','npg']:
        pm[c+'_'+tag]=ew(c,hl)
pm['npxg90_s']=pm['npxG_s']/(pm['min_s']/90+.05); pm['npxg90_l']=pm['npxG_l']/(pm['min_l']/90+.05)
pm['sh90_l']=pm['shots_l']/(pm['min_l']/90+.05); pm['xgpsh_l']=pm['npxG_l']/(pm['shots_l']+.05)
pm['chain90_l']=pm['xGChain_l']/(pm['min_l']/90+.05); pm['kp90_l']=pm['key_passes_l']/(pm['min_l']/90+.05)
pm['form_ratio']=np.log((pm['npxg90_s']+.05)/(pm['npxg90_l']+.05))
pm['hot']=pm['npg_s']-pm['npxG_s']            # recent over-finishing
pm['prev_date']=g['date'].shift(); pm['rest']=(pm['date']-pm['prev_date']).dt.days.clip(upper=30)
pm['last_min']=g['time'].shift()
pm['started_last']=(g['position'].shift()!='Sub').astype(float)
pm['month']=pm['date'].dt.month
pm['early']=pm['month'].isin([8,9]).astype(int)
# team recent form: team npxG last 5 vs rating (from team_matches)
tm=pd.read_csv(H+'team_matches.csv.gz'); tm['date']=pd.to_datetime(tm['date']); tm=tm.sort_values(['team','date'])
tm['npxG']=tm['npxG'].astype(float); tm['npxGA']=tm['npxGA'].astype(float)
tg=tm.groupby('team')
tm['t_att5']=tg['npxG'].transform(lambda s:s.shift().rolling(5,min_periods=1).mean())
tm['t_def5']=tg['npxGA'].transform(lambda s:s.shift().rolling(5,min_periods=1).mean())
pm=pm.merge(tm[['team','date','t_att5']],on=['team','date'],how='left')
pm=pm.merge(tm[['team','date','t_def5']].rename(columns={'team':'opp','t_def5':'o_def5'}),on=['opp','date'],how='left')
pm['team_form']=np.log((pm['t_att5']+.1)/(pm['att']*pm['lavg']+.1))
pm['opp_form']=np.log((pm['o_def5']+.1)/(pm['dfn']*pm['lavg']+.1))
print('features',time.time()-t0,flush=True)

d=pm[(pm['position']!='Sub')&(pm['n_prior']>=5)&(pm['grp']!='GK')&pm['lam_team_stats'].notna()].copy()
d['y']=(d['goals']>0).astype(int)
lt=d['lam_team_stats'].clip(lower=.05)
d['lam']=(lt*d['share']*d['exp_min']/90+d['tpen'].fillna(.1)*.95*d['pen_share']*d['exp_min']/90).clip(lower=1e-4)
d['lam_noteam']=(d['lavg']*d['share']*d['exp_min']/90+d['tpen'].fillna(.1)*.95*d['pen_share']*d['exp_min']/90).clip(lower=1e-4)
d['lam_nopen']=(lt*d['share']*d['exp_min']/90).clip(lower=1e-4)
d['lam_nomin']=(lt*d['share']*80/90+d['tpen'].fillna(.1)*.95*d['pen_share']*80/90).clip(lower=1e-4)
d['L']=np.log(d['lam']); 
for c in ['lam_noteam','lam_nopen','lam_nomin']: d['L_'+c]=np.log(d[c])
d['isF']=(d['grp']=='F').astype(int); d['isD']=(d['grp']=='D').astype(int)
d['lg']=d['league'].astype('category').cat.codes
d=d.fillna({'rest':7,'last_min':70,'form_ratio':0,'hot':0,'team_form':0,'opp_form':0})
d['day']=d['date'].dt.strftime('%Y-%m-%d')+d['league'].astype(str)
d.to_pickle(H+'d_eval.pkl')

base=['fin','home','n_prior_log','isF','isD']
d['n_prior_log']=np.log1p(d['n_prior'])
ABL={
 'L1 team-only (share x minutes, no team layer)':['L_lam_noteam']+base,
 'no penalty layer':['L_lam_nopen']+base,
 'no minutes layer':['L_lam_nomin']+base,
 'FULL layered (team x share x minutes x pens)':['L']+base,
 '+ form (short vs long xG rate)':['L']+base+['form_ratio'],
 '+ hot hand (recent goals minus xG)':['L']+base+['hot'],
 '+ shot volume & quality':['L']+base+['sh90_l','xgpsh_l'],
 '+ involvement (xGChain, key passes)':['L']+base+['chain90_l','kp90_l'],
 '+ team form / opp form':['L']+base+['team_form','opp_form'],
 '+ rest days / last minutes / started last':['L']+base+['rest','last_min','started_last'],
 '+ early season':['L']+base+['early'],
}
ALL=['L']+base+['form_ratio','hot','sh90_l','xgpsh_l','chain90_l','kp90_l','team_form','opp_form','rest','last_min','started_last','early','lg','npxg90_s','npxg90_l','share','exp_min','pen_share','lam_team_stats','att','dfn']

def zs(tr,te,cols):
    mu=tr[cols].mean(); sd=tr[cols].std().replace(0,1)
    return ((tr[cols]-mu)/sd).values, ((te[cols]-mu)/sd).values
seasons=[s for s in sorted(d['season'].unique()) if s>=2017]
out={}
def run(name,cols,model='lr'):
    P=[];Y=[];D=[];PR=[]
    for s in seasons:
        tr=d[d['season']<s]; te=d[d['season']==s]
        if model=='lr':
            Xtr,Xte=zs(tr,te,cols); w=S.logit_fit(Xtr,tr['y'].values.astype(float)); p=S.logit_pred(w,Xte)
        else:
            m=HistGradientBoostingClassifier(max_iter=300,learning_rate=.05,max_leaf_nodes=31,min_samples_leaf=200,l2_regularization=1.0,random_state=0)
            m.fit(tr[cols].values,tr['y'].values); p=m.predict_proba(te[cols].values)[:,1]
        P.append(p);Y.append(te['y'].values);D.append(te['day'].values)
    p=np.concatenate(P);y=np.concatenate(Y);dd=np.concatenate(D)
    df=pd.DataFrame({'p':p,'y':y,'day':dd})
    top=df.sort_values('p',ascending=False).groupby('day').head(3)
    # "priced-like" subset: top 40% by p within each day
    df['rk']=df.groupby('day')['p'].rank(pct=True,ascending=False)
    sub=df[df['rk']<=.4]
    r=dict(auc=round(S.auc(p,y),4),ll=round(S.ll(p,y),4),auc_top40=round(S.auc(sub['p'].values,sub['y'].values),4),top3_hit=round(top['y'].mean(),4))
    out[name]=r; print(f'{name:48s} {r}',flush=True)
    return df
for k,v in ABL.items(): run(k,v)
run('ALL features, logistic',ALL)
df=run('ALL features, gradient boosting',ALL,'gb')
json.dump(out,open(H+'layers.json','w'),indent=1)
print('done',time.time()-t0)
