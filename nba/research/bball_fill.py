import collections
from rules import days, SEASONS
from bball_draft import rr
WINX=120
def run(mode, zg=0.75):
    res=collections.defaultdict(lambda:[0,0,0.0,0.0]); nights=0; full=0
    for (S,d),R in days.items():
        if S not in SEASONS: continue
        el=[b for b in R if b['dfd'] and b.get('pb') is not None]
        if len(el)<8: continue
        key=lambda b:b['pb']*b['dfd']; v=[key(b) for b in el]; m=sum(v)/len(v); sd=(sum((x-m)**2 for x in v)/len(v))**.5 or 1e-9
        allv=sorted(el,key=lambda b:-key(b))
        pool,per=[],collections.Counter()
        for b in allv:
            if (key(b)-m)/sd<zg or per[b['gid']]>=4: continue
            pool.append(b); per[b['gid']]+=1
        A=pool[:4]; Aid={id(a) for a in A}
        if mode in ('reuse','twice'):   partners=[b for b in pool if id(b) not in Aid]
        elif mode=='wide':  partners=[b for b in allv if id(b) not in Aid and key(b)>1.0]   # any +EV starter
        else:               partners=[b for b in pool if id(b) not in Aid]
        moons=[[a] for a in A for _ in range(2)]; used=collections.Counter()
        cap = {'reuse':99,'twice':2}.get(mode,1)
        for r in range(3):
            order=range(len(moons)) if r%2==0 else reversed(range(len(moons)))
            for i in order:
                g={x['gid'] for x in moons[i]}; kos=[x['ko'] for x in moons[i]]; names={id(x) for x in moons[i]}
                for b in partners:
                    if used[id(b)]>=cap or b['gid'] in g or id(b) in names: continue
                    if WINX and max(kos+[b["ko"]])-min(kos+[b["ko"]])>WINX: continue
                    # no two identical moons
                    moons[i].append(b); used[id(b)]+=1; break
        M=[mn for mn in moons if len(mn)==4]
        nights+=1; full+= len(M)==8
        for mn in M:
            st,ret=rr(mn,0.25); r=res[S]; r[0]+=1; r[1]+=ret>0; r[2]+=st; r[3]+=ret-st
    t=[sum(v[i] for v in res.values()) for i in range(4)]
    print(f'{mode:8s} z>={zg}: moons/night={t[0]/nights:.1f} full-8 nights={full/nights:.0%} n={t[0]} cashed={t[1]} staked={t[2]:.0f} u={t[3]:+.0f} roi={t[3]/max(t[2],1):+.1%} | '+' '.join(f'{s%100}:{v[3]:+.0f}' for s,v in sorted(res.items())))


for w in (120,180,None):
    WINX=w; print('WIN',w)
    for mode in ('once','reuse'): run(mode)
