import pandas as pd, numpy as np, difflib, sys
D='/home/claude/tot/data/'
tm=pd.read_csv(D+'team_matches.csv.gz')
fd=pd.read_csv(D+'fd_market_2014_2026.csv')
fd['date']=pd.to_datetime(fd['Date'],dayfirst=True,format='mixed').dt.strftime('%Y-%m-%d')
h=tm[tm.h_a=='h'].drop(columns=['season']).rename(columns={'team':'uh','xG':'hxG','xGA':'axG','npxG':'hnpxG','npxGA':'anpxG','scored':'hg','missed':'ag'})
a=tm[tm.h_a=='a'][['league','date','team','scored','missed']].rename(columns={'team':'ua','scored':'ag2','missed':'hg2'})
u=h.merge(a,left_on=['league','date','hg','ag'],right_on=['league','date','hg2','ag2'])
# there can be cross pairings when two games same day same score; resolve after
def sim(x,y): return difflib.SequenceMatcher(None,str(x).lower(),str(y).lower()).ratio()
m=fd.merge(u,left_on=['league','date','FTHG','FTAG'],right_on=['league','date','hg','ag'],how='left')
m['s']=[sim(x,y)+sim(p,q) for x,y,p,q in zip(m.HomeTeam,m.uh,m.AwayTeam,m.ua)]
m=m.sort_values('s',ascending=False).drop_duplicates(['league','date','HomeTeam','AwayTeam'])
# date drift: understat sometimes off by a day; retry unmatched with +-1 day
miss=m[m.uh.isna()][fd.columns]
print('first pass matched',m.uh.notna().sum(),'of',len(fd),'unmatched',len(miss))
rows=[]
for d in (-1,1):
    mm=miss.copy(); mm['date']=(pd.to_datetime(mm.date)+pd.Timedelta(days=d)).dt.strftime('%Y-%m-%d')
    rows.append(mm.merge(u,left_on=['league','date','FTHG','FTAG'],right_on=['league','date','hg','ag']))
r=pd.concat(rows); r['s']=[sim(x,y)+sim(p,q) for x,y,p,q in zip(r.HomeTeam,r.uh,r.AwayTeam,r.ua)]
r=r[r.s>0.9].sort_values('s',ascending=False).drop_duplicates(['league','Date','HomeTeam','AwayTeam'])
m=pd.concat([m[m.uh.notna()],r]); 
print('after drift',len(m), 'low-sim rows', (m.s<0.9).sum())
print(m[m.s<1.0][['HomeTeam','uh','AwayTeam','ua','s']].sort_values('s').head(12).to_string())
m=m[m.s>=0.9]
m=m.sort_values(['date','league']).reset_index(drop=True)
m.to_pickle('/home/claude/tot/data/joined.pkl'); print('saved',len(m)); print(m.groupby('season').size().to_dict())
