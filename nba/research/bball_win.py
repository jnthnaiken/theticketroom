import collections,sys
from rules import days, SEASONS
from bball_draft import rr
def draft(R,win):
    el=[b for b in R if b['dfd'] and b.get('pb') is not None]
    if len(el)<8: return [],[]
    key=lambda b:b['pb']*b['dfd']; v=[key(b) for b in el]; m=sum(v)/len(v); sd=(sum((x-m)**2 for x in v)/len(v))**.5 or 1e-9
    pool,per=[],collections.Counter()
    for b in sorted(el,key=lambda b:-key(b)):
        if (key(b)-m)/sd<0.75 or per[b['gid']]>=4: continue
        pool.append(b); per[b['gid']]+=1
    A=pool[:4]; rest=pool[4:]; moons=[[a] for a in A for _ in range(2)]; used=set()
    for r in range(3):
        order=range(len(moons)) if r%2==0 else reversed(range(len(moons)))
        for i in order:
            g={x['gid'] for x in moons[i]}; kos=[x['ko'] for x in moons[i] if x.get('ko') is not None]
            for b in rest:
                if id(b) in used or b['gid'] in g: continue
                if win and b.get('ko') is not None and kos and (max(kos+[b['ko']])-min(kos+[b['ko']]))>win: continue
                moons[i].append(b); used.add(id(b)); break
    return A,[mn for mn in moons if len(mn)==4]
for win in (None,120,90):
    res=collections.defaultdict(lambda:[0,0,0.0,0.0])
    for (S,d),R in days.items():
        if S not in SEASONS: continue
        A,M=draft(R,win)
        for mn in M:
            st,ret=rr(mn,0.25); r=res[S]; r[0]+=1; r[1]+=ret>0; r[2]+=st; r[3]+=ret-st
    t=[sum(v[i] for v in res.values()) for i in range(4)]
    print(f'WIN={win}: moons n={t[0]} cashed={t[1]} staked={t[2]:.0f} u={t[3]:+.0f} roi={t[3]/max(t[2],1):+.1%} | '+' '.join(f'{s%100}:{v[3]:+.0f}' for s,v in sorted(res.items())))
