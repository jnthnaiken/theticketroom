import numpy as np, pandas as pd, statsmodels.api as sm
from engine import score_matrix, logloss
p=pd.read_csv('../data/player_matches.csv.gz')
p=p.sort_values(['date','match_id'])
# infer team: per (pid,season) count appearances of each candidate team
c=pd.concat([p[['pid','season','h_team']].rename(columns={'h_team':'t'}),p[['pid','season','a_team']].rename(columns={'a_team':'t'})])
cnt=c.groupby(['pid','season','t']).size()
ch=cnt.reindex(pd.MultiIndex.from_arrays([p.pid,p.season,p.h_team])).values
ca=cnt.reindex(pd.MultiIndex.from_arrays([p.pid,p.season,p.a_team])).values
p['team']=np.where(ch>=ca,p.h_team,p.a_team); p['home']=(p.team==p.h_team).astype(int)
p['start']=(p.position!='Sub').astype(int)
# player prior rate (strictly before this match): cumulative npxG and minutes, shrunk
g=p.groupby('pid')
p['cx']=g.npxG.cumsum()-p.npxG; p['cm']=g.time.cumsum()-p.time
# recency: also last-10-appearance rolling
p['rx']=g.npxG.transform(lambda s:s.shift(1).rolling(15,min_periods=1).sum()).fillna(0)
p['rm']=g.time.transform(lambda s:s.shift(1).rolling(15,min_periods=1).sum()).fillna(0)
k=3.0; prior=0.10
p['rate']=(p.rx+prior*k)/(p.rm/90+k)
st=p[p.start==1].groupby(['match_id','date','h_team','a_team','home']).agg(att=('rate','sum'),n=('rate','size')).reset_index()
st=st.sort_values('date')
st['team']=np.where(st.home==1,st.h_team,st.a_team)
gg=st.groupby('team')
st['base']=gg.att.transform(lambda s:s.shift(1).rolling(6,min_periods=3).mean())
st['lu']=np.log(st.att/st.base)
w=st.pivot_table(index=['match_id','date','h_team','a_team'],columns='home',values='lu').reset_index().rename(columns={1:'lu_h',0:'lu_a'})
w.to_pickle('../data/lineup.pkl'); print(w.describe().round(3))
