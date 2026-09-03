#!/usr/bin/env python3
"""
nfl_stats.py -- the signal extractor. nflverse -> one row per player for a given (season, week).

THE FOUR TERMS, and why these four: MODEL-2026-09-02.md. Each is measured as percentage-point
lift within a usage stratum on held-out 2025, NOT by AUC -- the AUC instrument is what produced
the retraction in EDGE-2026-09-02.md and it must not be used to judge a signal on this board.

    usage        touches per game                     +28.2pp   (Q5 vs Q1)
    role         inside-10 touches per game            +6.6pp   (usage AND price held fixed)
    concentration inside-10 share of own touches       +5.0pp   (usage AND price held fixed)
    environment  implied team total from the line      +8.6pp   (usage held fixed)
    position     tilt vs the same-usage average     TE +2.9pp / RB -1.4pp

⚠️ DO NOT ADD A DEFENSIVE MATCHUP TERM. Opponent TD rate allowed inside the 10 measured -0.2pp and
opponent red-zone trips allowed +0.8pp, on top of a genre that already died twice on the other
instrument. Coach 4th-down aggression inside the 10: +0.4pp. Team finishing rate: +0.0pp. Those
four are settled; re-testing them is re-walking a dead end.

⚠️ WEEK 1 IS A COLD START AND IT IS FLAGGED, NOT HIDDEN. In week 1 there are no snaps this season,
so every usage figure is last season's attached to this season's depth chart, and roughly a fifth
of the league's touch distribution turns over each September. Rows carry `basis` = 'season' or
'prior' and `basis_games`; the payload shows it. This is the same rule the soccer room adopted for
a player with no top-five xG history -- score him, and say so on the card.
"""
import argparse, os, sys, io, gzip, urllib.request
import pandas as pd, numpy as np

NFLVERSE = 'https://github.com/nflverse/nflverse-data/releases/download'
SCHED    = 'https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv'
MIN_GAMES = 3          # below this many in-season games, fall back to the prior season

PBP_COLS=['game_id','season','season_type','week','posteam','defteam','yardline_100',
          'play_type','rush_attempt','pass_attempt','touchdown','rush_touchdown',
          'pass_touchdown','fixed_drive','rusher_player_id','receiver_player_id']

def _get(url, dest, cache='.cache'):
    os.makedirs(cache, exist_ok=True)
    p = os.path.join(cache, dest)
    if not os.path.exists(p) or os.path.getsize(p) < 1000:
        urllib.request.urlretrieve(url, p)
    return p

def load_pbp(season, required=True):
    """A season that has not kicked off yet has NO pbp asset -- nflverse 404s rather than
    publishing an empty file. That is the normal state every September and it must not be an
    error: week 1 is built entirely from the prior season by design (see the cold-start note
    above). Returns an empty frame with the right columns so every caller downstream is
    unchanged."""
    try:
        p=_get(f'{NFLVERSE}/pbp/play_by_play_{season}.csv.gz', f'pbp{season}.csv.gz')
    except Exception as e:
        if required: raise
        return pd.DataFrame(columns=PBP_COLS)
    d=pd.read_csv(p, usecols=PBP_COLS, low_memory=False)
    d=d[d.season_type=='REG'].copy()
    for c in ['rush_attempt','pass_attempt','rush_touchdown','pass_touchdown','touchdown']:
        d[c]=d[c].fillna(0)
    return d

def load_roster(season):
    p=_get(f'{NFLVERSE}/weekly_rosters/roster_weekly_{season}.csv', f'ros{season}.csv')
    r=pd.read_csv(p, usecols=['season','week','team','position','full_name','gsis_id'], low_memory=False)
    return r.dropna(subset=['gsis_id'])

def load_depth(season, before=None):
    """The ESPN-derived depth chart. Schema changed in 2025 (dt/team/pos_abb/pos_rank); 2024 and
    earlier use season/club_code/week/depth_team and are NOT read here -- the prior table was
    measured on the new schema and mixing them would silently mis-rank."""
    p=_get(f'{NFLVERSE}/depth_charts/depth_charts_{season}.csv', f'dc{season}.csv')
    d=pd.read_csv(p, low_memory=False)
    if 'pos_abb' not in d.columns:
        return pd.DataFrame(columns=['pid','pos','pos_rank'])
    d['dt']=pd.to_datetime(d.dt,errors='coerce')
    if before is not None: d=d[d.dt<before]
    if not len(d): return pd.DataFrame(columns=['pid','pos','pos_rank'])
    d=d[d.dt==d.dt.max()]
    d=d[d.pos_abb.isin(['RB','WR','TE','QB','FB'])].copy()
    # DEPTHFB-2026-09-02: FB IS ITS OWN LADDER and must not be folded into RB before the rank is
    # read. It was, and every team's fullback came out as an "RB1" worth 17 touches a game --
    # Riley Nowakowski, Patrick Ricard and Brady Russell all priced as lead backs on the first
    # build. Measured separately, FB1 is 0.7 touches a game.
    d['pos']=d.pos_abb
    d=d.dropna(subset=['gsis_id']).sort_values('pos_rank').drop_duplicates('gsis_id')
    return d.rename(columns={'gsis_id':'pid'})[['pid','pos','pos_rank']]


def apply_depth(out, season, model='depth_model.json'):
    """DEPTHPRIOR-2026-09-02 -- the rookie hole, closed.

    The board scored a player off last season's usage, so on the 2026 week-1 roster it could see
    395 of 905 skill players: every rookie and every man who did not touch the ball last year was
    invisible, on the one weekend that group matters most. Tennessee's listed back did not exist
    to it.

    Measured on 2025 (week-1 depth chart -> that season's weeks 1-6):
      * a player WITH a prior-season figure does best on a BLEND -- R2 0.770, against 0.738 for
        prior usage alone and 0.544 for the slot alone. The depth chart is what catches the
        veteran who lost his job over the summer.
      * a player with NO history gets 0.60x the slot average, not the slot average. A rookie
        listed RB1 in September is not a workhorse: rookies at depth rank 1-2 averaged 3.9
        touches a game and 40% scored in weeks 1-6, against 12.4 and 73% for the slot at large.
        Handing him the veteran number would have been worse than omitting him.

    ⚠️ ONLY applied when the usage basis is `prior` (i.e. week 1). Once there are in-season snaps
    the observed figure is the real thing and the depth chart is not an improvement on it -- the
    blend was fitted prior-season-to-next-season and that is the only case it is licensed for.
    """
    import json as _json, os as _os
    if not _os.path.exists(model): return out
    M=_json.load(open(model))
    dp=pd.DataFrame(M['depth_prior'])[['pos','pos_rank','tchpg','i10pg']].rename(
        columns={'tchpg':'d_tch','i10pg':'d_i10'})
    dc=load_depth(season).merge(dp,on=['pos','pos_rank'],how='left')
    o=out.merge(dc[['pid','pos_rank','d_tch','d_i10']],on='pid',how='left')
    has=o.d_tch.notna()
    vt,vi=M['vet_tch'],M['vet_i10']; nt,ni=M['new_tch'],M['new_i10']
    prior=(o.basis=='prior')&has
    o.loc[prior,'tchpg']=(vt['coef'][0]*o.loc[prior,'tchpg']+vt['coef'][1]*o.loc[prior,'d_tch']
                          +vt['intercept']).clip(lower=0)
    o.loc[prior,'i10pg']=(vi['coef'][0]*o.loc[prior,'i10pg']+vi['coef'][1]*o.loc[prior,'d_i10']
                          +vi['intercept']).clip(lower=0)
    o.loc[prior,'basis']='prior+depth'
    new=(o.basis=='none')&has
    o.loc[new,'tchpg']=(nt['coef'][0]*o.loc[new,'d_tch']+nt['intercept']).clip(lower=0)
    o.loc[new,'i10pg']=(ni['coef'][0]*o.loc[new,'d_i10']+ni['intercept']).clip(lower=0)
    o.loc[new,'basis']='depth'
    o['i10_share']=np.where(o.tchpg>0,(o.i10pg/o.tchpg).clip(0,1),0.0)
    return o


def load_sched():
    p=_get(SCHED,'games.csv')
    return pd.read_csv(p, low_memory=False)

def touch_rows(pbp):
    """One row per touch (carry or target). A target counts even if incomplete: the market is
    anytime TD, and being thrown at inside the 10 is opportunity whether or not it is caught."""
    ru=pbp[(pbp.rush_attempt==1)&pbp.rusher_player_id.notna()][
        ['game_id','season','week','posteam','defteam','yardline_100','rusher_player_id','rush_touchdown']]
    ru.columns=['game_id','season','week','team','opp','yl','pid','td']
    rc=pbp[(pbp.pass_attempt==1)&pbp.receiver_player_id.notna()][
        ['game_id','season','week','posteam','defteam','yardline_100','receiver_player_id','pass_touchdown']]
    rc.columns=['game_id','season','week','team','opp','yl','pid','td']
    t=pd.concat([ru,rc],ignore_index=True)
    t['td']=t.td.fillna(0); t['i10']=(t.yl<=10).astype(int)
    return t

def usage_from(t, label):
    g=t.groupby('pid').agg(gp=('game_id','nunique'),tch=('td','size'),
                           i10=('i10','sum'),tds=('td','sum')).reset_index()
    g['tchpg']=g.tch/g.gp
    g['i10pg']=g.i10/g.gp
    g['i10_share']=g.i10/g.tch.replace(0,np.nan)
    g['tdpg']=g.tds/g.gp
    g['basis']=label; g['basis_games']=g.gp
    return g[['pid','tchpg','i10pg','i10_share','tdpg','basis','basis_games']]

def rz_trips(pbp):
    rz=pbp[pbp.yardline_100<=20].groupby(['posteam','game_id']).fixed_drive.nunique().reset_index()
    a=rz.groupby('posteam').agg(t=('fixed_drive','sum'),g=('game_id','nunique')).reset_index()
    a['rz_pg']=a.t/a.g
    return a.rename(columns={'posteam':'team'})[['team','rz_pg']]

def build(season, week, min_games=MIN_GAMES):
    pbp=load_pbp(season, required=False)
    cur=pbp[pbp.week<week] if len(pbp) else pbp
    t_cur=touch_rows(cur) if len(cur) else None
    u_cur=usage_from(t_cur,'season') if t_cur is not None and len(t_cur) else pd.DataFrame()
    if len(u_cur): u_cur=u_cur[u_cur.basis_games>=min_games]

    # prior season, for week 1 and for anybody short of min_games
    prev=load_pbp(season-1)
    u_prev=usage_from(touch_rows(prev),'prior')
    u_prev=u_prev[u_prev.basis_games>=4]

    have=set(u_cur.pid) if len(u_cur) else set()
    u=pd.concat([u_cur, u_prev[~u_prev.pid.isin(have)]],ignore_index=True) if len(u_cur) else u_prev

    # team red-zone trips: in-season if there is any, else prior season
    rz = rz_trips(cur) if len(cur) else pd.DataFrame()
    if not len(rz): rz = rz_trips(prev)

    # this week's games, from the schedule: opponent, kickoff, line -> implied team total
    s=load_sched()
    s=s[(s.season==season)&(s.game_type=='REG')&(s.week==week)]
    if not len(s):
        sys.exit(f'no schedule rows for {season} week {week}')
    h=s.rename(columns={'home_team':'team','away_team':'opp'}).copy(); h['home']=1
    h['imp']=h.total_line/2+h.spread_line/2
    a=s.rename(columns={'away_team':'team','home_team':'opp'}).copy(); a['home']=0
    a['imp']=a.total_line/2-a.spread_line/2
    keep=['game_id','team','opp','home','imp','total_line','spread_line','gameday','gametime',
          'weekday','roof','surface','temp','wind']
    gm=pd.concat([h[keep],a[keep]],ignore_index=True)

    # who is on which roster this week
    r=load_roster(season)
    rw=r[r.week==week] if (r.week==week).any() else r[r.week==r.week.max()]
    rw=rw.drop_duplicates('gsis_id')[['gsis_id','team','position','full_name']].rename(columns={'gsis_id':'pid'})
    rw=rw[rw.position.isin(['RB','WR','TE','QB','FB'])]

    out=(rw.merge(u,on='pid',how='left')
           .merge(gm,on='team',how='inner')
           .merge(rz,on='team',how='left'))
    out['pos']=out.position.replace({'FB':'RB'})
    for c in ['tchpg','i10pg','tdpg']: out[c]=out[c].fillna(0.0)
    out['i10_share']=out.i10_share.fillna(0.0)
    out['basis']=out.basis.fillna('none'); out['basis_games']=out.basis_games.fillna(0)
    out['indoor']=out.roof.isin(['dome','closed']).astype(int)
    out['wind']=np.where(out.indoor==1,0,out.wind.fillna(0))
    out=apply_depth(out, season)
    return out.sort_values('tchpg',ascending=False).reset_index(drop=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('season',type=int); ap.add_argument('week',type=int)
    ap.add_argument('-o','--out',default=None)
    ap.add_argument('--min-games',type=int,default=MIN_GAMES)
    A=ap.parse_args()
    df=build(A.season,A.week,A.min_games)
    if A.out:
        df.to_csv(A.out,index=False); print(f'{len(df)} players -> {A.out}')
    n_prior=(df.basis=='prior').sum(); n_none=(df.basis=='none').sum()
    print(f'{A.season} wk{A.week}: {len(df)} rostered skill players across {df.game_id.nunique()} games')
    print(f'  basis: season={(df.basis=="season").sum()}  prior={n_prior}  none={n_none}')
    print(f'  with any touches: {(df.tchpg>0).sum()}   implied totals {df.imp.min():.1f}-{df.imp.max():.1f}')
