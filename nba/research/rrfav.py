import itertools, collections, json
from rules import days, SEASONS
def picks(R, legs, mode, prob='pb', ev_min=None, max_odds=None, min_odds=None):
    c=[b for b in R if b['dfd'] and b.get(prob) is not None]
    if ev_min is not None: c=[b for b in c if b[prob]*b['dfd']-1>=ev_min]
    if max_odds: c=[b for b in c if b['fd']<=max_odds]
    if min_odds: c=[b for b in c if b['fd']>=min_odds]
    key={'fav':lambda b:-b[prob],'ev':lambda b:-(b[prob]*b['dfd'])}[mode]
    c.sort(key=key); seen,out=set(),[]
    for b in c:
        if b['gid'] in seen: continue
        out.append(b); seen.add(b['gid'])
        if len(out)>=legs: break
    return out
def test(legs,sizes,mode,unit=0.5,**kw):
    res=collections.defaultdict(lambda:[0,0.0,0,0]); hit=[0,0]; odds=[]
    for (S,d),R in days.items():
        if S not in SEASONS: continue
        P=picks(R,legs,mode,**kw)
        if len(P)<legs: continue
        for b in P: hit[0]+=1; hit[1]+=b['y']; odds.append(b['fd'])
        r=res[S]; r[0]+=1; ret=st=0
        for k in sizes:
            for cb in itertools.combinations(P,k):
                st+=unit
                if all(b['y'] for b in cb):
                    m=1
                    for b in cb: m*=b['dfd']
                    ret+=unit*m
        r[1]+=ret-st; r[2]+=st; r[3]+=ret>0
    n=sum(v[0] for v in res.values()); u=sum(v[1] for v in res.values()); st=sum(v[2] for v in res.values()); c=sum(v[3] for v in res.values())
    odds.sort()
    return f'slips={n:4d} leg-hit={hit[1]/max(hit[0],1):5.1%} med-price=+{odds[len(odds)//2] if odds else 0} cashed={c:3d} staked={st:6.0f} units={u:+7.1f} roi={u/max(st,1):+6.1%} | '+' '.join(f'{s%100}:{v[1]:+.0f}' for s,v in sorted(res.items()))
if __name__=='__main__':
    for legs,sizes,lab in ((3,(2,3),'3 legs by 2s & 3'),(4,(2,3),'4 legs by 2s & 3'),(4,(2,3,4),'4 legs by 2s,3s,4'),(3,(2,),'3 legs doubles')):
        print('FAVORITES  ',lab.ljust(20),test(legs,sizes,'fav'))
        print('FAV EV>=0  ',lab.ljust(20),test(legs,sizes,'fav',ev_min=0.0))
        print('FAV <=+600 ',lab.ljust(20),test(legs,sizes,'fav',max_odds=600))
        print('VALUE .2   ',lab.ljust(20),test(legs,sizes,'ev',ev_min=0.2))
        print()
