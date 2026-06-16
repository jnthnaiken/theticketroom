import json, re, time
SHELL="/home/claude/slate0615/shell_0614.html"
OUT="/mnt/user-data/outputs/ticket_room.html"
src=open(SHELL).read()
D=json.load(open('/home/claude/slate0615/D_0615.json'))
def rep(old,new,n=1):
    global src
    assert src.count(old)==n, f"count {src.count(old)} (want {n}) for: {old[:55]!r}"
    src=src.replace(old,new)

# 1) data swap (first match only; 2nd is the in-page download fn template)
dj='const D='+json.dumps(D,ensure_ascii=True)+',WX=D.meta.wx;'
src,n=re.subn(r'const D=[\s\S]*?,WX=D\.meta\.wx;',(lambda m:dj),src,count=1); assert n==1,"D block"
# 2) date roll
src=src.replace("June 14, 2026","June 15, 2026")
# 3) salami renders horizontal (lunchwide); full pool tab stays unfiltered (people build their own)
rep("${t.kind==='lunch'?' lunchwide':''}","${t.kind==='lunch'?' lunchwide':''}${t.kind==='biggest'?' lunchwide bigtop':''}")
# 4) colored leg bars measure TOTAL (the model score) against the field max, not aT
rep("const maxAT=D.meta.maxAT;","const maxAT=D.meta.maxAT,maxT=(Math.max.apply(null,Object.values(D.players).map(function(p){return p.TOTAL||0;}))||1);")
rep("w=Math.max(5,p.aT/maxAT*100)","w=Math.max(5,(p.total||0)/maxT*100)")
# 5) moonshots show the round-robin badge in the top-right, like the salami
rep("const od=(t.kind==='biggest'&&t.rr)?","const od=(t.rr)?")
rep("pay=(t.kind==='biggest'&&t.rr)?","pay=(t.rr)?")
# 6) only the dome badge was jammed against its count; space it (boost/suppress were fine)
rep("'&#127967;'+ws.dome","'&#127967; '+ws.dome")
# write with retry (transient Errno5 on this volume)
for attempt in range(5):
    try:
        open(OUT,'w').write(src); break
    except OSError:
        if attempt==4: raise
        time.sleep(0.4)
print(f"injected OK -> {len(src)} bytes; tickets {len(D['tickets'])}; players {len(D['players'])}")
