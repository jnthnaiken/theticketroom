import collections
from rules import days, SEASONS
from bball_draft import rr
def run(sibling_disjoint=True, cap=99):
    res=collections.defaultdict(lambda:[0,0,0.0,0.0]); nights=0; full=0; dup=0
    for (S,d),R in days.items():
        if S not in SEASONS: continue
        el=[b for b in R if b['dfd'] and b.get('pb') is not None]
        if len(el)<8: continue
        key=lambda b:b['pb']*b['dfd']; v=[key(b) for b in el]; m=sum(v)/len(v); sd=(sum((x-m)**2 for x in v)/len(v))**.5 or 1e-9
        pool,per=[],collections.Counter()
        for b in sorted(el,key=lambda b:-key(b)):
            if (key(b)-m)/sd<0.75 or per[b['gid']]>=4: continue
            pool.append(b); per[b['gid']]+=1
        A=pool[:4]; Aid={id(a) for a in A}; partners=[b for b in pool if id(b) not in Aid]
        moons=[[a] for a in A for _ in range(2)]; used=collections.Counter()
        for r in range(3):
            order=range(len(moons)) if r%2==0 else reversed(range(len(moons)))
            for i in order:
                sib=moons[i^1] if sibling_disjoint else []
                g={x['gid'] for x in moons[i]}; sibids={id(x) for x in sib[1:]}
                for b in partners:
                    if used[id(b)]>=cap or b['gid'] in g or id(b) in sibids: continue
                    moons[i].append(b); used[id(b)]+=1; break
        M=[mn for mn in moons if len(mn)==4]
        keys=[tuple(sorted(id(x) for x in mn)) for mn in M]; dup+=len(keys)-len(set(keys))
        nights+=1; full+=len(M)==8
        for mn in M:
            st,ret=rr(mn,0.25); r=res[S]; r[0]+=1; r[1]+=ret>0; r[2]+=st; r[3]+=ret-st
    t=[sum(v[i] for v in res.values()) for i in range(4)]
    print(f'sibling_disjoint={sibling_disjoint} cap={cap}: moons/night={t[0]/nights:.1f} full-8={full/nights:.0%} dup={dup} n={t[0]} cashed={t[1]} staked={t[2]:.0f} u={t[3]:+.0f} roi={t[3]/max(t[2],1):+.1%} | '+' '.join(f'{s%100}:{v[3]:+.0f}' for s,v in sorted(res.items())))
run(False); run(True); run(True,cap=2); run(True,cap=3)
