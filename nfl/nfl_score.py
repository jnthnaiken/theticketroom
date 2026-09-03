#!/usr/bin/env python3
"""
nfl_score.py -- turn signal rows into a priced board.

OUTPUT IS A PROBABILITY. The four-term model (MODEL-2026-09-02.md) is fitted on 2021-2024 and
calibrated on held-out 2025 to a worst-decile gap of 3.8pp, so `p` can be compared to a price
directly. That is the point: an anytime-TD board lives or dies on model-probability vs
market-probability, and a score that is not a probability cannot make that comparison.

PER-TEAM NORMALISATION (the de-vig anchor). Raw logistic probabilities do not have to sum to
anything, but the number of distinct rush/rec TD scorers a team produces is a known function of
its implied total -- measured over 2021-2025, `scorers = 0.0977 * implied_total - 0.300` (16-19
implied -> 1.45 scorers; 25-28 -> 2.40). Each team's player probabilities are scaled to that sum.
This is what makes `p` comparable to a book's price after ITS vig is removed the same way, and it
is also what stops a stacked offence from having eleven men at 30%.

wxMult -- measured WITHIN usage quartiles, outdoor games only, 2021-2025:
    0-3 mph -0.2pp | 3-7 +1.4pp | 7-11 -0.0pp | 11-15 -1.5pp | 15+ -1.6pp | indoor +1.4pp
⚠️ An earlier note in this project claimed the windiest decile scored 18.0% against 24.0% for the
calmest. That was NOT usage-controlled and it overstated the effect roughly four-fold. Wind is a
small trim, not a headline.
"""
import argparse, json, numpy as np, pandas as pd
import nfl_stats

def wx_mult(row):
    if row.indoor: return 1.014
    w=row.wind
    if w<=3:  return 0.998
    if w<=7:  return 1.014
    if w<=11: return 1.000
    if w<=15: return 0.985
    return 0.984

def score(df, model='nfl_model.json'):
    M=json.load(open(model))
    d=df.copy()
    d['x_tch']=np.log1p(d.tchpg); d['x_i10']=np.log1p(d.i10pg)
    d['x_shr']=d.i10_share; d['x_imp']=d.imp; d['x_rz']=d.rz_pg.fillna(d.rz_pg.median())
    for p in ['QB','RB','TE','WR']: d['p_'+p]=(d.pos==p).astype(float)
    X=d[M['feats']].astype(float)
    Z=(X-np.array(M['mu']))/np.array(M['sd'])
    lin=Z.values@np.array(M['coef'])+M['intercept']
    d['p_raw']=1/(1+np.exp(-lin))

    # per-team scaling to the de-vig anchor
    a,b=M['devig']
    d['exp_scorers']=(a*d.imp+b).clip(lower=0.6)
    s=d.groupby('team').p_raw.transform('sum')
    d['p']=(d.p_raw*d.exp_scorers/s.replace(0,np.nan)).clip(0.005,0.90)

    d['wf']=d.apply(wx_mult,axis=1)
    d['p']=(d.p*d.wf).clip(0.005,0.90)
    d['fair']=np.where(d.p>0,(100*(1-d.p)/d.p),9999)
    d['fair_am']=d.fair.apply(lambda x:'+%d'%int(round(x/5)*5))
    return d.sort_values('p',ascending=False).reset_index(drop=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('season',type=int); ap.add_argument('week',type=int)
    ap.add_argument('-o','--out',default=None); ap.add_argument('-n',type=int,default=25)
    A=ap.parse_args()
    raw=nfl_stats.build(A.season,A.week)
    d=score(raw)
    d=d[d.tchpg>0]
    print(f'\n{A.season} week {A.week} -- {len(d)} priced players, {d.game_id.nunique()} games\n')
    print(f'{"player":22}{"pos":4}{"tm":4}{"opp":5}{"tch/g":>6}{"i10/g":>6}{"i10%":>6}{"imp":>6}{"rz":>5}{"P(TD)":>8}{"fair":>7}  basis')
    print('-'*100)
    for _,r in d.head(A.n).iterrows():
        print(f'{r.full_name[:21]:22}{r.pos:4}{r.team:4}{r.opp:5}{r.tchpg:>6.1f}{r.i10pg:>6.2f}'
              f'{r.i10_share:>6.0%}{r.imp:>6.1f}{(r.rz_pg if pd.notna(r.rz_pg) else 0):>5.1f}'
              f'{r.p:>8.1%}{r.fair_am:>7}  {r.basis}')
    if A.out:
        d.to_csv(A.out,index=False); print(f'\n-> {A.out}')
