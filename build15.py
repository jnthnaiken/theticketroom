"""
The Ticket Room - scorer (data-ingesting build).

Replaces the old hardcoded-slate build15. Reads the day's FOUNDATION from four files
(no hardcoded slate), scores every carded hitter with the same model math, and writes
D_0615.json for regen15.py (-> assemble -> inject).

Daily inputs (date = SLATE_DATE env or today ET), each repo-relative:
  cards_<date>.json    Kasper matchup cards   {MATCHUP:{TEAM:[{name,test,zone,form_pct,form_arrow,pb,hh,la},...]}}
  lineups_<date>.json  projected lineups+sched {games:[{gn,matchup,time,away,home,away_sp,home_sp,dome,precip,wind,status,away_bats[],home_bats[]}]}
  odds_<date>.json     consensus HR odds       {name: american}
  iso_<date>.json      ISO sheet               {name: iso}

If a given day's file is missing, falls back to the PRIOR day's file (so a late input
still builds on real data). ISO falls back to the legacy ISO sheet, then to the floor.
season.json is the authoritative ledger (grade_night advances it); we just load it.
"""
import math, statistics as st, json, unicodedata, re, ast, os, datetime
import cardnotes

DATE = os.environ.get('SLATE_DATE') or (datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=4)).strftime('%Y-%m-%d')
def _prior(d): return (datetime.datetime.strptime(d,'%Y-%m-%d')-datetime.timedelta(days=1)).strftime('%Y-%m-%d')

def load_dated(stem, required=True):
    for d in (DATE, _prior(DATE)):
        f = f"{stem}_{d}.json"
        if os.path.exists(f):
            if d != DATE: print(f"  ({stem}_{DATE}.json missing -> using prior day {d})")
            return json.load(open(f))
    if required: raise SystemExit(f"!! missing required input {stem}_{DATE}.json (and prior day)")
    return {}

norm=lambda s:''.join(c for c in unicodedata.normalize('NFKD',s) if not unicodedata.combining(c)).lower().replace('.','').strip()
clamp=lambda x,a,b:max(a,min(b,x))
fF=lambda f:1.0 if f is None else clamp(1+0.006*(f-50),0.85,1.15)
pM=lambda w:1.0 if w is None else 1+(0.25 if w<1 else 0.30)*(w-1)
la_window=lambda la:math.exp(-((la-25.0)/14.0)**2)
FULL={'TOR':'Blue Jays','BOS':'Red Sox','CLE':'Guardians','MIL':'Brewers','MIN':'Twins','TEX':'Rangers','BAL':'Orioles','SEA':'Mariners','NYM':'Mets','PHI':'Phillies','CWS':'White Sox','NYY':'Yankees','SF':'Giants','ATL':'Braves','STL':'Cardinals','KC':'Royals','LAA':'Angels','ATH':'Athletics','COL':'Rockies','CHC':'Cubs','TB':'Rays','LAD':'Dodgers','MIA':'Marlins','PIT':'Pirates','DET':'Tigers','HOU':'Astros','CIN':'Reds','AZ':'Diamondbacks','ARI':'Diamondbacks','WSH':'Nationals','SD':'Padres'}

# ---- ISO: today's sheet primary, legacy build15 sheet as fallback, then floor ----
ISO_OLD={}
try:
    leg=open('build15_legacy.py').read()
    ISO_OLD={norm(k):v for k,v in ast.literal_eval(re.search(r'ISO_RAW\s*=\s*(\{.*?\})\n',leg,re.S).group(1)).items()}
except Exception as e:
    print(f"  (no legacy ISO fallback: {e})")
ISO_TODAY={norm(k):v for k,v in load_dated('iso', required=False).items()}
ISO=dict(ISO_OLD); ISO.update(ISO_TODAY)
ISO_FLOOR=min(ISO_TODAY.values()) if ISO_TODAY else (min(ISO.values()) if ISO else 0.10)

cards=load_dated('cards'); lin=load_dated('lineups')
ODDS={norm(k):v for k,v in load_dated('odds').items()}

def wf_of(g):
    if g.get('dome'): return 1.00
    w=(g.get('wind') or '')
    if 'Out' in w: return 1.05
    if 'In' in w and 'mph' in w: return 0.95
    return 1.00
def gmin(gt):
    m=re.match(r'(\d+):(\d+)\s*(AM|PM)',gt or '')
    return (int(m.group(1))%12+(12 if m.group(3)=='PM' else 0))*60+int(m.group(2)) if m else 0
is_late=lambda gt: gmin(gt)>=21*60

players={}; gamemeta={}
for g in lin['games']:
    gn=g['gn']; gm=g['matchup']; gt=g['time']; wf=wf_of(g); gamemeta[gn]=g
    for side in ('away','home'):
        code=g[side]; opp_sp=g[('home' if side=='away' else 'away')+'_sp']
        posted={norm(x) for x in g[side+'_bats']}
        for c in cards[gm][code]:
            nm=c['name']; n=norm(nm); in_lu=n in posted
            status=('confirmed' if g.get('status')=='confirmed' else 'projected') if in_lu else 'projected'
            form=c['form_pct'] if c.get('form_pct') is not None else 50
            iso=ISO.get(n); iso_used=iso if iso is not None else ISO_FLOOR
            powraw=c['pb']*c['hh']*la_window(c['la'])
            lean='Boost' if wf>1.02 else ('Suppress' if wf<0.98 else 'Neutral')
            players[nm]=dict(nm=nm,code=code,team=FULL[code],aT=c['test'],zonev=c['zone'],form=form,pb=c['pb'],hh=c['hh'],la=c['la'],
                iso=(("."+str(iso).split('.')[1]) if iso is not None else "—"),iso_used=iso_used,powraw=powraw,
                hr9=None,wf=wf,game=gn,gmatch=gm,gtime=gt,late=is_late(gt),rain=False,out=(not in_lu),status=status,
                void=False,opp=[opp_sp[0],opp_sp[1]],oppERA=None,ftrend=c.get('form_arrow','flat'),
                odds=ODDS.get(n),soft=True,why="")

pool=list(players.values()); raws=sorted(r['powraw'] for r in pool); N=len(raws)
def pct(p):
    i=p/100*(N-1); lo=int(i); hi=min(lo+1,N-1); return raws[lo]+(raws[hi]-raws[lo])*(i-lo)
p5,p95=pct(5),pct(95)
for r in pool: r['powidx']=round(clamp(100*(r['powraw']-p5)/(p95-p5),0,100)) if p95>p5 else 50
medP=st.median([r['powidx'] for r in pool]); medI=st.median([r['iso_used'] for r in pool])
zs=[r['zonev'] for r in pool if abs(r['zonev']-0.5)>1e-9]; medZ=st.median(zs) if zs else 0.06
powT=lambda P:clamp(1+0.15*(P-medP)/40,0.85,1.15)
isoT=lambda I:clamp(1+0.08*(I-medI)/0.06,0.92,1.08)
zoneT=lambda z:1.0 if abs(z-0.5)<1e-9 else clamp(1+0.05*(z-medZ)/0.05,0.95,1.05)
for r in pool:
    r['TOTAL']=round(r['aT']*powT(r['powidx'])*isoT(r['iso_used'])*zoneT(r['zonev'])*fF(r['form'])*pM(r['wf']),1)

# descriptive per-player write-ups (same phrase engine as the ticket notes)
for r in pool:
    r['why']=cardnotes.card_why(r)

wx={}
for gn,g in gamemeta.items():
    wf=wf_of(g); lean='Boost' if wf>1.02 else ('Suppress' if wf<0.98 else 'Neutral'); dome=g.get('dome')
    wx[str(gn)]={'emoji':("\U0001f3df" if dome else ("☀️" if g.get('precip',0)<30 else "\U0001f327️")),
        'lean':('Neutral' if dome else lean),'factor':wf,'park':g['matchup'],
        'cond':('Dome' if dome else (g.get('wind','') or 'calm')),'rain':str(g.get('precip',0))+"% rain",'precip':g.get('precip',0)}

try: season=json.load(open(os.environ.get('SEASON_JSON','season.json')))
except Exception: season={'since':DATE,'stake':1,'cats':{},'history':[0.0],'graded_nights':[]}
meta={'wx':wx,'face':{},'maxAT':round(max(r['aT'] for r in pool),1),'season':season,'date':DATE,'gs':{}}
json.dump({'players':players,'meta':meta},open('D_0615.json','w'),indent=1)
print(f"build15: {DATE} | scored {len(players)} carded | in-lineup {sum(1 for r in pool if not r['out'])} | priced {sum(1 for r in pool if r['odds'])} | season {season.get('history',[0])[-1]}u")
