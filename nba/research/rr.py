import itertools, collections
from rules import days, SEASONS
def picks_for(R, ev_min, cap, prob='pb'):
    c=sorted([(b[prob]*b['dfd']-1,b) for b in R if b['dfd'] and b.get(prob) is not None],key=lambda x:-x[0])
    seen,out=set(),[]
    for e,b in c:
        if e<ev_min or b['gid'] in seen: continue
        out.append(b); seen.add(b['gid'])
        if len(out)>=cap: break
    return out
def test(ev_min, legs, sizes, unit=0.5):
    res=collections.defaultdict(lambda:[0,0.0,0,0])   # season -> slips, units, staked, cashed
    sres=collections.defaultdict(lambda:[0,0.0])
    for (S,d),R in days.items():
        if S not in SEASONS: continue
        P=picks_for(R,ev_min,legs)
        for b in P: sres[S][0]+=1; sres[S][1]+= (b['dfd']-1) if b['y'] else -1
        if len(P)<legs: continue
        r=res[S]; r[0]+=1; ret=0; st=0
        for k in sizes:
            for cb in itertools.combinations(P,k):
                st+=unit
                if all(b['y'] for b in cb):
                    m=1
                    for b in cb: m*=b['dfd']
                    ret+=unit*m
        r[1]+=ret-st; r[2]+=st; r[3]+= 1 if ret>0 else 0
    n=sum(v[0] for v in res.values()); u=sum(v[1] for v in res.values()); st=sum(v[2] for v in res.values()); c=sum(v[3] for v in res.values())
    seas=' '.join(f'{s%100}:{v[1]:+.0f}' for s,v in sorted(res.items()))
    return f'slips={n:4d} cashed={c:3d} staked={st:7.1f} units={u:+8.1f} roi={u/max(st,1):+6.1%} | {seas}'
for ev in (0.0,0.2,0.3):
    for legs,sizes,lab in ((3,(2,3),'3 legs by 2s & 3'),(4,(2,3,4),'4 legs by 2s,3s,4'),(3,(2,),'3 legs doubles only'),(2,(2,),'2-leg parlay'),(4,(2,3),'4 legs by 2s & 3')):
        print(f'EV>={ev:.1f} {lab:22s}', test(ev,legs,sizes))
    print()
