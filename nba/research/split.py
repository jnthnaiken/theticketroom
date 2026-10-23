from rules import run, fmt
import itertools
TR=[2021,2022,2023]; TE=[2024,2025]
cands=[]
for t,cap,fb,lo,hi,prob in itertools.product((0.0,0.1,0.2,0.3,0.4,0.5),(1,2,3,5,None),(True,False),(None,500,700,1000),(None,999,1499),('pb','p')):
    if lo and hi and lo>=hi: continue
    kw=dict(ev_min=t,per_day=cap,fallback=fb,lo=lo,hi=hi,prob=prob)
    (n,h,u),per=run(seasons=TR,**kw)
    if n<150: continue
    cands.append((u/n, u, n, min(v[2] for v in per.values()), kw))
print(len(cands),'rules tried on 2021-23')
for key,lab in ((lambda c:-c[1],'by units'),(lambda c:-c[0],'by ROI')):
    print('\n== top 8 on TRAIN',lab,'-> then TEST 2024-25 ==')
    for roi,u,n,w,kw in sorted([c for c in cands if c[3]>0],key=key)[:8]:
        (tn,th,tu),tp=run(seasons=TE,**kw)
        print(f'train n={n:4d} roi={roi:+.1%} u={u:+6.0f} | TEST n={tn:4d} roi={tu/max(tn,1):+.1%} u={tu:+6.0f} | {kw}')
print('\nreference on TEST:')
for lab,kw in (('CHOSEN',dict()),('EV>=0 cap3',dict(ev_min=0.0)),('mid 500-999 EV>=.3 cap1',dict(lo=500,hi=999,per_day=1,fallback=False))):
    (tn,th,tu),tp=run(seasons=TE,**kw); print(f'{lab:28s} TEST n={tn} roi={tu/max(tn,1):+.1%} u={tu:+.0f}')
