"""Owner 10-24: 'only throw a moon out if its an exact duplicate'. Option A drops to 1/anchor because twins are always
exact. Middle ground: the 2nd moon may share partners with its sibling but must differ by at least k legs."""
import collections, itertools
from rules import days, SEASONS
from bball_draft import rr
def run(min_diff):
    res=collections.defaultdict(lambda:[0,0,0.0,0.0]); nights=0
    for (S,d),R in days.items():
        if S not in SEASONS: continue
        el=[b for b in R if b['dfd'] and b.get('pb') is not None]
        if len(el)<8: continue
        key=lambda b:b['pb']*b['dfd']; v=[key(b) for b in el]; m=sum(v)/len(v); sd=(sum((x-m)**2 for x in v)/len(v))**.5 or 1e-9
        pool,per=[],collections.Counter()
        for b in sorted(el,key=lambda b:-key(b)):
            if (key(b)-m)/sd<0.75 or per[b['gid']]>=4: continue
            pool.append(b); per[b['gid']]+=1
        A=pool[:4]; Aid={id(a) for a in A}; P=[b for b in pool if id(b) not in Aid]
        M=[]
        for a in A:
            ok=[b for b in P if b['gid']!=a['gid']]
            # all valid 3-partner sets ranked by value (greedy order = lexicographic over the ranked list)
            sets=[c for c in itertools.combinations(ok,3) if len({a['gid']}|{x['gid'] for x in c})==4]
            if not sets: continue
            first=sets[0]; M.append([a,*first])
            fid={id(x) for x in first}
            for c in sets[1:]:
                if len(fid-{id(x) for x in c})>=min_diff: M.append([a,*c]); break
        nights+=1
        for mn in M:
            st,ret=rr(mn,0.25); r=res[S]; r[0]+=1; r[1]+=ret>0; r[2]+=st; r[3]+=ret-st
    t=[sum(v[i] for v in res.values()) for i in range(4)]
    print(f'2nd moon differs by >= {min_diff} leg(s): moons/night={t[0]/nights:.1f} n={t[0]} cashed={t[1]} staked={t[2]:.0f} u={t[3]:+.0f} roi={t[3]/max(t[2],1):+.1%} | '
          +' '.join(f'{s%100}:{v[3]:+.0f}' for s,v in sorted(res.items())))
for k in (1,2,3): run(k)
