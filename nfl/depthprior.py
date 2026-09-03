"""
DEPTHPRIOR -- what a week-1 depth-chart slot has historically been worth in touches.

WHY THIS EXISTS. The board prices a player off prior-season usage. On the 2026 week-1 roster that
covers 395 of 905 skill players: every rookie and every player who did not touch the ball last
year is invisible -- on the one weekend of the year when that group matters most. Nicholas
Singleton is Tennessee's listed RB and the board could not see him.

The fallback must not be a guess. Measured here: take the depth chart as it stood before week 1,
and ask what players in each (position, rank) slot actually did.
"""
import pandas as pd, numpy as np, nfl_stats

d=pd.read_csv('dc2025.csv',low_memory=False)
d['dt']=pd.to_datetime(d.dt,errors='coerce')
pre=d[d.dt < '2025-09-11']                      # snapshots before week 1 kicked off
snap=pre.dt.max()
dc=pre[pre.dt==snap]
dc=dc[dc.pos_abb.isin(['RB','WR','TE','QB','FB'])].copy()
# ⚠️ FB IS ITS OWN LADDER. Collapsing it into RB before reading pos_rank made every
# team's fullback an 'RB1' worth 8.3 touches a game -- Riley Nowakowski, Patrick Ricard
# and Brady Russell all priced as lead backs. Keep the ladders separate.
dc['pos']=dc.pos_abb
dc=dc.sort_values('pos_rank').drop_duplicates(['gsis_id'])
print(f'depth snapshot {snap} -- {len(dc)} skill players, {dc.team.nunique()} teams')
print(dc.groupby(['pos','pos_rank']).size().unstack(fill_value=0).to_string())

# what they actually did in 2025
pbp=nfl_stats.load_pbp(2025)
t=nfl_stats.touch_rows(pbp)
t=t[t.week<=6]                                  # the window a week-1 prior has to cover
act=t.groupby('pid').agg(gp=('game_id','nunique'),tch=('td','size'),
                         i10=('i10','sum'),tds=('td','sum')).reset_index()
act['tchpg']=act.tch/act.gp; act['i10pg']=act.i10/act.gp
act['i10_share']=act.i10/act.tch.replace(0,np.nan)
M=dc[['gsis_id','pos','pos_rank','team']].rename(columns={'gsis_id':'pid'}).merge(act,on='pid',how='left')
M[['tchpg','i10pg','tds']]=M[['tchpg','i10pg','tds']].fillna(0)
M['i10_share']=M.i10_share.fillna(0)

print('\nACTUAL weeks 1-6 usage, by week-1 depth slot (2025):')
print(f'{"slot":<10}{"n":>5}{"tch/gm":>9}{"i10/gm":>9}{"i10%":>7}{"any TD":>9}')
rows=[]
for (p,r),g in M.groupby(['pos','pos_rank']):
    if len(g)<4 or r>4: continue
    rows.append(dict(pos=p,pos_rank=int(r),n=len(g),tchpg=g.tchpg.mean(),
                     i10pg=g.i10pg.mean(),i10_share=g.i10_share.mean()))
    print(f'{p+str(int(r)):<10}{len(g):>5}{g.tchpg.mean():>9.1f}{g.i10pg.mean():>9.2f}'
          f'{g.i10_share.mean():>7.0%}{(g.tds>0).mean():>9.0%}')
pd.DataFrame(rows).to_csv('depth_prior.csv',index=False)

# does the slot actually separate? the instrument this project trusts.
sub=M[M.pos_rank<=3]
print('\nseparation check -- mean touches/gm by rank, within position:')
print(sub.pivot_table(index='pos',columns='pos_rank',values='tchpg',aggfunc='mean').round(1).to_string())
print('\nwrote depth_prior.csv')
