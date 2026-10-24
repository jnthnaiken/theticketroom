"""Owner 10-24: 'what if we just threw out the duplicates?' -- option A (no sibling exclusion) with exact-duplicate
moons dropped, vs the shipped MOONFILL (sibling-disjoint)."""
import collections
from rules import days, SEASONS
from bball_draft import rr
def run(sibling_disjoint, dedup):
    res=collections.defaultdict(lambda:[0,0,0.0,0.0]); nights=0; cnt=collections.Counter()
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
        moons=[[a] for a in A for _ in range(2)]
        for r in range(3):
            order=range(len(moons)) if r%2==0 else reversed(range(len(moons)))
            for i in order:
                sibids={id(x) for x in moons[i^1][1:]} if sibling_disjoint else set()
                g={x['gid'] for x in moons[i]}
                for b in partners:
                    if b['gid'] in g or id(b) in sibids: continue
                    moons[i].append(b); break
        M=[mn for mn in moons if len(mn)==4]
        if dedup:
            seen=set(); U=[]
            for mn in M:
                k=tuple(sorted(id(x) for x in mn))
                if k not in seen: seen.add(k); U.append(mn)
            M=U
        nights+=1; cnt[len(M)]+=1
        for mn in M:
            st,ret=rr(mn,0.25); r=res[S]; r[0]+=1; r[1]+=ret>0; r[2]+=st; r[3]+=ret-st
    t=[sum(v[i] for v in res.values()) for i in range(4)]
    print(f'disjoint={sibling_disjoint} dedup={dedup}: moons/night={t[0]/nights:.1f} n={t[0]} cashed={t[1]} ({t[1]/max(t[0],1):.1%}) staked={t[2]:.0f} u={t[3]:+.0f} roi={t[3]/max(t[2],1):+.1%} per-moon={t[3]/max(t[0],1):+.2f} | '
          +' '.join(f'{s%100}:{v[3]:+.0f}' for s,v in sorted(res.items())), dict(sorted(cnt.items())))
run(False,False); run(False,True); run(True,False)
