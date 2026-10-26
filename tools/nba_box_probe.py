import sys, json; sys.path.insert(0,'nba')
import nba_nbacom as N, nba_src as SRC
d=sys.argv[1]
for gid,a,h,st,*_ in N.scoreboard(d):
    s=N.summary(gid); g=N.parse(s)
    print('NBA',a,h,'starters',{k:len(v) for k,v in g['starters'].items()},'played',len(g['played']),'fs',g['fs'],'acts',len(s['actions']))
    g2=SRC.parse(SRC.summary(gid)); print('   SRC fs',g2['fs'],'starters',{k:len(v) for k,v in g2['starters'].items()})
s=N.summary(N.scoreboard(d)[0][0]); A=s['actions']
print('ACT0', json.dumps(A[:3])[:1500]); print('MADE', [a for a in A if a.get('shotResult')][:1])
print('STATS', json.dumps(s['game']['homeTeam']['players'][0].get('statistics'))[:600])
