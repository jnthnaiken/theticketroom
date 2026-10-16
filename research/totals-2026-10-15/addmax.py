import pandas as pd, glob, os, numpy as np
FD={'E0':'EPL','SP1':'La_liga','D1':'Bundesliga','I1':'Serie_A','F1':'Ligue_1','E1':'Championship','N1':'Eredivisie','P1':'Primeira','B1':'Jupiler','SC0':'Scot_Prem'}
rows=[]
for f in glob.glob('/home/claude/tot/data/fd_raw/*.csv'):
    code,s=os.path.basename(f)[:-4].split('_')
    try: d=pd.read_csv(f,encoding='latin1',on_bad_lines='skip')
    except Exception as e: print('bad',f,e); continue
    d=d.dropna(subset=['HomeTeam','FTHG'])
    d['league']=FD[code]; d['season']=2000+int(s[:2])
    rows.append(d)
raw=pd.concat(rows,ignore_index=True)
raw['date']=pd.to_datetime(raw.Date,dayfirst=True,format='mixed').dt.strftime('%Y-%m-%d')
for a,b in (('Max>2.5','BbMx>2.5'),('Max<2.5','BbMx<2.5')):
    raw[a]=raw[a].fillna(raw[b]) if b in raw else raw[a]
raw.to_pickle('/home/claude/tot/data/fd_all.pkl')
print(raw.groupby('league').size().to_dict())
print(raw.groupby('season')[['Max>2.5','MaxC>2.5','HS','HST']].apply(lambda x:x.notna().mean().round(2)).to_string())
m=pd.read_pickle('/home/claude/tot/data/feats.pkl')
k=raw[['league','date','HomeTeam','AwayTeam','Max>2.5','Max<2.5','MaxC>2.5','MaxC<2.5']].rename(columns={'Max>2.5':'o_max','Max<2.5':'u_max','MaxC>2.5':'o_maxc','MaxC<2.5':'u_maxc'})
m2=m.merge(k,on=['league','date','HomeTeam','AwayTeam'],how='left')
print('max coverage in feats',m2.o_max.notna().mean().round(3), len(m2),len(m))
m2.index=m.index; m2.to_pickle('/home/claude/tot/data/feats.pkl')
