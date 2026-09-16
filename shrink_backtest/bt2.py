from bt import *
def auc(scores):
    pos=[s for s,y in scores if y]; neg=[s for s,y in scores if not y]
    if not pos or not neg: return None
    allv=sorted((s,y) for s,y in scores); rsum=0; i=0
    # rank-sum with ties
    ranks={}
    vals=sorted(s for s,_ in scores)
    import bisect
    for s,y in scores: pass
    order=sorted(range(len(scores)),key=lambda j:scores[j][0])
    r=[0]*len(scores); j=0
    while j<len(order):
        k=j
        while k+1<len(order) and scores[order[k+1]][0]==scores[order[j]][0]: k+=1
        for t in range(j,k+1): r[order[t]]=(j+k)/2+1
        j=k+1
    rp=sum(r[j] for j in range(len(scores)) if scores[j][1])
    return (rp-len(pos)*(len(pos)+1)/2)/(len(pos)*len(neg))
def night_auc(floor,k,excl,key):
    a=[];pooled=[]
    for d in NIGHTS:
        rk=rank_night(N[d],floor,k,excl)
        sc=[((t[2] if key=='kas' else t[0]), t[1]['hr']>0) for t in rk]
        # only well-sampled vs all
        v=auc(sc)
        if v is not None: a.append(v)
    return sum(a)/len(a)
def boot_diff(fA,fB,top=30):
    # paired night bootstrap of top-N hit-rate difference
    import random
    hits={}
    for lab,(fl,k,ex) in (('A',fA),('B',fB)):
        hits[lab]={d:[t[1]['hr']>0 for t in rank_night(N[d],fl,k,ex)[:top]] for d in NIGHTS}
    random.seed(3); ds=[]
    for _ in range(2000):
        s=random.choices(NIGHTS,k=len(NIGHTS))
        a=sum(sum(hits['A'][d]) for d in s)/sum(len(hits['A'][d]) for d in s)
        b=sum(sum(hits['B'][d]) for d in s)/sum(len(hits['B'][d]) for d in s)
        ds.append(b-a)
    ds.sort(); return ds[50],ds[1000],ds[1950]
V=[('live: floor80 + exclude',(80,0,80))]+[(f'shrink k={k}',(0,k,0)) for k in (50,100,150,250)]+[(f'shrink k={k} + exclude<40',(0,k,40)) for k in (100,150)]+[(f'shrink k={k} + exclude<80',(0,k,80)) for k in (100,150)]
for lab,(fl,k,ex) in V:
    print(f'{lab:28s} kas AUC {night_auc(fl,k,ex,"kas"):.4f}  EV AUC {night_auc(fl,k,ex,"ev"):.4f}')
print()
for lab,f in V[1:]:
    lo,md,hi=boot_diff(V[0][1],f,30); print(f'{lab:28s} top-30 HR diff vs live {md:+.2%} [{lo:+.2%},{hi:+.2%}]')
