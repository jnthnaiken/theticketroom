import sys, json; sys.path.insert(0,'nba')
import nba_nbacom as N, nba_espn as ES
d=sys.argv[1]
for gid,a,h,st,*_ in N.scoreboard(d):
    s=N.summary(gid); g=N.parse(s)
    print('NBA', a,h,st,'starters',{k:len(v) for k,v in g['starters'].items()},'pbp',g['pbp_complete'],'players',{t:len([x for x in g['box'] if x['team']==t]) for t in (a,h)})
for row in ES.scoreboard(d):
    try:
        g=ES.parse(ES.summary(row[0])); print('ESPN',row[1],row[2],row[3],'starters',{k:len(v) for k,v in g['starters'].items()},'fs',g.get('fs'))
    except Exception as e: print('ESPN',row[1],row[2],'ERR',str(e)[:150])
s=N.summary(N.scoreboard(d)[0][0]); t=s['game']['homeTeam']['players']
print('KEYS', sorted(t[0].keys())); print([(x.get('name'),x.get('starter'),x.get('position')) for x in t[:8]])
import nba_src as SRC; g=SRC.parse(SRC.summary(N.scoreboard(d)[0][0])); print('SRC starters',{k:len(v) for k,v in g['starters'].items()}, g['fs'])
