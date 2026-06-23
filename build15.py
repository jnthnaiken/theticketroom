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
fF=lambda f:1.0 if f is None else clamp(1+0.003*(f-50),0.92,1.08)   # form trimmed: HRs track power/matchup, not recent hot/cold
pM=lambda w:1.0 if w is None else 1+W_WEATHER*(w-1)
la_window=lambda la:math.exp(-((la-25.0)/14.0)**2)

# ---- weather / park knobs (tunable; symmetric) ----
W_WIND   = 0.0035   # wf per mph of tailwind toward CF
W_TEMP   = 0.0015   # wf per F above 70 (cold subtracts the same)
W_ELEV   = 0.025    # wf per 1000 ft of park elevation (thin-air carry; Coors ~+13%)
W_WEATHER= 0.30     # how hard wf pushes TOTAL via pM (same up and down)
W_HR9    = 0.16     # opposing-pitcher HR/9: TOTAL multiplier per HR/9 vs baseline (symmetric)
HR9_BASE = 1.15     # league-ish HR/9 (neutral matchup); above -> boost, below -> penalty
HR9_CLAMP= 0.15     # cap the pitcher-matchup swing at +-15%
W_BRL     = 0.018   # opposing-pitcher barrel-against -> TOTAL mult per pt of (Brl/BIP% + 0.5*PulledBrl%) deviation
BRL_BASE  = 7.5     # league-ish Brl/BIP% allowed (neutral)
PBRL_BASE = 5.0     # league-ish PulledBrl% allowed
BRL_SHRINK= 0.6     # regress toward mean -- export has no batted-ball counts, so guard small samples (e.g. a rookie at 0.000)
BRL_CLAMP = 0.15
PARK_HR  = {'NYY':1.10,'CIN':1.10,'PHI':1.06,'BAL':1.05,'MIL':1.04,'HOU':1.04,'TOR':1.03,'BOS':1.02,'CHC':1.00,
            'NYM':1.00,'WSH':1.00,'ATL':1.00,'TEX':1.00,'LAD':1.00,'MIN':1.00,'COL':1.00,'ARI':1.00,'CWS':1.00,'CHW':1.00,
            'CLE':0.98,'STL':0.97,'LAA':0.97,'SD':0.96,'TB':0.96,'ATH':0.95,'KC':0.94,'PIT':0.93,'DET':0.93,'SEA':0.92,'SF':0.91,'MIA':0.90}
pHR9 = lambda h: 1.0 if h is None else clamp(1+W_HR9*(h-HR9_BASE), 1-HR9_CLAMP, 1+HR9_CLAMP)   # pitcher HR-vulnerability (notes-only before; now scored)
parkT= lambda code: clamp(PARK_HR.get(code,1.0), 0.90, 1.12)                                   # static park HR factor (dimensions/short-porch; elevation stays in weather)
pbrl_mult= lambda d: clamp(1 + W_BRL*BRL_SHRINK*(((d.get('brl') if d.get('brl') is not None else BRL_BASE)-BRL_BASE)+0.5*((d.get('pbrl') if d.get('pbrl') is not None else PBRL_BASE)-PBRL_BASE)), 1-BRL_CLAMP, 1+BRL_CLAMP)   # listed pitchers: barrel-against -> hitter HR mult
WX_CLAMP = 0.10     # symmetric cap on the wind+temp part (+/-10%)
PARK_ELEV= {'COL':5200,'ATH':2000,'ATL':1050,'MIN':815,'KC':750,'PIT':730,'CLE':660,'CHC':600,'DET':600,
            'CIN':490,'STL':465,'LAD':522,'LAA':160,'SD':62,'SF':13,'NYY':55,'NYM':36,'PHI':39,'BOS':20,
            'BAL':36,'WSH':30,'ARI':1100,'SEA':134,'HOU':80,'MIA':10,'TB':44,'TOR':250,'TEX':545,'MIL':635}
CF_AZ    = {'ARI':0,'ATL':50,'BAL':30,'BOS':45,'CHC':30,'CWS':38,'CIN':40,'CLE':0,'COL':0,'DET':30,'HOU':20,
            'KC':45,'LAA':40,'LAD':25,'MIA':35,'MIL':30,'MIN':7,'NYM':25,'NYY':15,'ATH':62,'PHI':15,'PIT':70,
            'SD':0,'SF':85,'SEA':60,'STL':30,'TB':50,'TEX':40,'TOR':0,'WSH':30}   # plate->CF bearing (deg); ATH=Vegas placeholder
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
def pnorm(x):
    x=''.join(c for c in unicodedata.normalize('NFD',x or '') if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z ]','',x).strip()
HR9={pnorm(k):v for k,v in load_dated('hr9',required=False).items()}
PBRL={pnorm(k):v for k,v in load_dated('pitchers',required=False).items()}   # Kasper Top-Pitchers barrel-against export (partial -> HR/9 fallback)
SLATE={(_g.get('matchup')):_g for _g in (load_dated('slate_auto',required=False).get('games') or [])}

def wf_of(g):
    # park factor = symmetric weather (tailwind + temp, capped +/-WX_CLAMP) * elevation. Domes -> 1.0.
    # Tailwind is the wind vector PROJECTED onto the plate->CF axis (handles crosswinds / any angle):
    #   tail = speed * cos(wind_toward - CF_azimuth).  Needs wind direction in DEGREES (Open-Meteo).
    # RotoWire only gives Out/In/L-R, so without degrees we fall back to a coarse +1/-1/0 bucket.
    if g.get('dome'): return 1.00
    w=(g.get('wind') or ''); m=re.search(r'(\d+)\s*mph',w); spd=int(m.group(1)) if m else 0
    deg=g.get('wind_deg')
    if deg is not None:                                   # real bearing -> continuous projection
        toward=(deg+180)%360
        tail=spd*math.cos(math.radians(toward-CF_AZ.get(g.get('home'),0)))
    else:                                                 # bucket fallback (lossy; can't resolve angle)
        sign=1 if 'Out' in w else (-1 if re.search(r'\bIn\b',w) else 0); tail=spd*sign
    temp=(g.get('temp') or 70)
    wx_w=clamp(1.0+W_WIND*tail+W_TEMP*(temp-70), 1-WX_CLAMP, 1+WX_CLAMP)
    wx_e=1.0+W_ELEV*(PARK_ELEV.get(g.get('home'),0)/1000.0)
    return round(wx_w*wx_e, 3)
def gmin(gt):
    m=re.match(r'(\d+):(\d+)\s*(AM|PM)',gt or '')
    return (int(m.group(1))%12+(12 if m.group(3)=='PM' else 0))*60+int(m.group(2)) if m else 0
is_late=lambda gt: gmin(gt)>=21*60

players={}; gamemeta={}
for g in lin['games']:
    gn=g['gn']; gm=g['matchup']; gt=g['time']
    _sa=SLATE.get(gm)                                   # auto-pull (Open-Meteo) weather -> real wind bearing
    if _sa:
        _wx=_sa.get('weather') or {}
        if _wx.get('wind_dir') is not None: g['wind_deg']=_wx['wind_dir']        # degrees -> cos-projection
        if _wx.get('wind_mph') is not None: g['wind']=str(round(_wx['wind_mph']))+' mph'
        if _wx.get('temp') is not None: g['temp']=_wx['temp']
        if 'dome' in _wx: g['dome']=_wx['dome']
        if _wx.get('precip') is not None: g['precip']=_wx['precip']
    wf=wf_of(g); gamemeta[gn]=g
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
                hr9=HR9.get(pnorm(opp_sp[0])),wf=wf,game=gn,gmatch=gm,gtime=gt,late=is_late(gt),rain=False,out=(not in_lu),status=status,
                void=False,opp=[opp_sp[0],opp_sp[1]],oppERA=None,ftrend=c.get('form_arrow','flat'),
                odds=ODDS.get(n),soft=True,why="")

pool=list(players.values()); raws=sorted(r['powraw'] for r in pool); N=len(raws)
def pct(p):
    i=p/100*(N-1); lo=int(i); hi=min(lo+1,N-1); return raws[lo]+(raws[hi]-raws[lo])*(i-lo)
p5,p95=pct(5),pct(95)
for r in pool: r['powidx']=round(clamp(100*(r['powraw']-p5)/(p95-p5),0,100)) if p95>p5 else 50
medP=st.median([r['powidx'] for r in pool]); medI=st.median([r['iso_used'] for r in pool])
zs=[r['zonev'] for r in pool if abs(r['zonev']-0.5)>1e-9]; medZ=st.median(zs) if zs else 0.06
powT=lambda P:clamp(1+0.18*(P-medP)/40,0.82,1.18)   # power widened (true HR driver)
isoT=lambda I:clamp(1+0.12*(I-medI)/0.06,0.88,1.12)   # ISO widened (cleanest power stat)
zoneT=lambda z:1.0 if abs(z-0.5)<1e-9 else clamp(1+0.05*(z-medZ)/0.05,0.95,1.05)
for r in pool:
    _opn=pnorm((r.get('opp') or ['',''])[0])
    if _opn in PBRL: r['phr9']=pbrl_mult(PBRL[_opn]); r['psrc']='brl'   # listed top arm -> barrel-against (better signal)
    else:            r['phr9']=1.0; r['psrc']='hr9'                     # unlisted -> neutral here; live engine applies HR/9
    _hm=(r.get('gmatch') or '@').split('@')[-1]; r['parkhr']=parkT(_hm)
    r['TOTAL']=round(r['aT']*powT(r['powidx'])*isoT(r['iso_used'])*zoneT(r['zonev'])*fF(r['form'])*r['phr9']*r['parkhr']*pM(r['wf']),1)

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
meta={'wx':wx,'build':__import__('time').strftime('%-m/%-d %-I:%M%p').lower(),'face':{},'maxAT':round(max(r['aT'] for r in pool),1),'season':season,'date':DATE,'gs':{}}
json.dump({'players':players,'meta':meta},open('D_0615.json','w'),indent=1)
print(f"build15: {DATE} | scored {len(players)} carded | in-lineup {sum(1 for r in pool if not r['out'])} | priced {sum(1 for r in pool if r['odds'])} | season {season.get('history',[0])[-1]}u")
