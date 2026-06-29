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

def _latest_slate():
    import glob
    base=os.path.dirname(os.path.abspath(__file__))
    ds=sorted(re.findall(r'cards_(\d{4}-\d{2}-\d{2})\.json','\n'.join(glob.glob(os.path.join(base,'cards_*.json')))))
    return ds[-1] if ds else (datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=4)).strftime('%Y-%m-%d')
# date = pinned SLATE_DATE, else the most recent slate that actually has input files (never roll forward to an empty calendar day)
DATE = os.environ.get('SLATE_DATE') or _latest_slate()
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
fF=lambda f:1.0 if f is None else clamp(1+0.002*(f-50),0.94,1.06)   # form trimmed: HRs track power/matchup, not recent hot/cold
pM=lambda w:1.0 if w is None else 1+W_WEATHER*(w-1)
la_window=lambda la:math.exp(-((la-25.0)/14.0)**2)

# ---- weather / park knobs (tunable; symmetric) ----
W_WIND   = 0.0035   # wf per mph of tailwind toward CF
W_TEMP   = 0.0015   # wf per F above 70 (cold subtracts the same)
W_ELEV   = 0.025    # wf per 1000 ft of park elevation (thin-air carry; Coors ~+13%)
W_WEATHER= 0.18     # how hard wf pushes TOTAL via pM (same up and down)
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
# ---- new HR-signal knobs (1 market, 2 lineup slot, 3 platoon, 4 handed park) ----
W_MKT=0.18; MKT_CLAMP=0.22        # market implied-prob -> TOTAL (independent info; previously used only for drafting)
W_SLOT=0.08                       # lineup slot / PA volume: top of order up, bottom down (centered at #5)
W_PLAT=0.08                       # platoon: same-hand suppress, opposite-hand boost, switch slight boost
PARK_HAND={'NYY':(1.05,0.97),'BOS':(0.97,1.05),'SF':(0.95,1.02),'CIN':(1.03,1.00),'PHI':(1.02,1.00),
           'BAL':(0.99,1.03),'HOU':(0.99,1.03),'DET':(0.98,1.00),'KC':(0.99,1.00),'TEX':(1.00,1.01)}  # (LHB_mult,RHB_mult) pull-side tilt on top of PARK_HR
slotT=lambda srank: 1.0 if not srank else clamp(1+W_SLOT*(5-srank)/4.0, 1-W_SLOT, 1+W_SLOT)
def platT(bh, sph):
    if not bh or not sph: return 1.0
    ph='L' if 'L' in sph else 'R'
    if bh=='S': return 1+W_PLAT*0.3
    return (1-W_PLAT) if bh==ph else (1+W_PLAT*0.7)
def parkHandT(code, bh):
    fac=PARK_HR.get(code,1.0)
    if bh in ('L','R') and code in PARK_HAND: fac*=PARK_HAND[code][0 if bh=='L' else 1]
    return clamp(fac, 0.88, 1.16)
pbrl_mult= lambda d: clamp(1 + W_BRL*BRL_SHRINK*(((d.get('brl') if d.get('brl') is not None else BRL_BASE)-BRL_BASE)+0.5*((d.get('pbrl') if d.get('pbrl') is not None else PBRL_BASE)-PBRL_BASE)), 1-BRL_CLAMP, 1+BRL_CLAMP)   # listed pitchers: barrel-against -> hitter HR mult
WX_CLAMP = 0.10     # symmetric cap on the wind+temp part (+/-10%)
PARK_ELEV= {'COL':5200,'ATH':2000,'ATL':1050,'MIN':815,'KC':750,'PIT':730,'CLE':660,'CHC':600,'DET':600,
            'CIN':490,'STL':465,'LAD':522,'LAA':160,'SD':62,'SF':13,'NYY':55,'NYM':36,'PHI':39,'BOS':20,
            'BAL':36,'WSH':30,'ARI':1100,'SEA':134,'HOU':80,'MIA':10,'TB':44,'TOR':250,'TEX':545,'MIL':635}
CF_AZ    = {'ARI':0,'ATL':50,'BAL':30,'BOS':45,'CHC':30,'CWS':38,'CIN':40,'CLE':0,'COL':0,'DET':30,'HOU':20,
            'KC':45,'LAA':40,'LAD':25,'MIA':35,'MIL':30,'MIN':7,'NYM':25,'NYY':15,'ATH':62,'PHI':15,'PIT':70,
            'SD':0,'SF':85,'SEA':60,'STL':30,'TB':50,'TEX':40,'TOR':0,'WSH':30}   # plate->CF bearing (deg); ATH=Vegas placeholder
FULL={'TOR':'Blue Jays','BOS':'Red Sox','CLE':'Guardians','MIL':'Brewers','MIN':'Twins','TEX':'Rangers','BAL':'Orioles','SEA':'Mariners','NYM':'Mets','PHI':'Phillies','CWS':'White Sox','NYY':'Yankees','SF':'Giants','ATL':'Braves','STL':'Cardinals','KC':'Royals','LAA':'Angels','ATH':'Athletics','COL':'Rockies','CHC':'Cubs','TB':'Rays','LAD':'Dodgers','MIA':'Marlins','PIT':'Pirates','DET':'Tigers','HOU':'Astros','CIN':'Reds','AZ':'Diamondbacks','ARI':'Diamondbacks','WSH':'Nationals','SD':'Padres'}

# ---- LIVE data at build time (Open-Meteo weather + StatsAPI HR/9) so the shipped seed == the browser re-draft ----
import urllib.request
PARK_LL={'ARI':(33.4455,-112.0667),'AZ':(33.4455,-112.0667),'ATL':(33.8907,-84.4677),'BAL':(39.2839,-76.6217),
'BOS':(42.3467,-71.0972),'CHC':(41.9484,-87.6553),'CWS':(41.8300,-87.6339),'CIN':(39.0975,-84.5069),
'CLE':(41.4962,-81.6852),'COL':(39.7559,-104.9942),'DET':(42.3390,-83.0485),'HOU':(29.7572,-95.3556),
'KC':(39.0517,-94.4803),'LAA':(33.8003,-117.8827),'LAD':(34.0739,-118.2400),'MIA':(25.7780,-80.2197),
'MIL':(43.0280,-87.9712),'MIN':(44.9817,-93.2776),'NYM':(40.7571,-73.8458),'NYY':(40.8296,-73.9262),
'ATH':(38.5800,-121.5160),'PHI':(39.9061,-75.1665),'PIT':(40.4469,-80.0057),'SD':(32.7073,-117.1566),
'SF':(37.7786,-122.3893),'SEA':(47.5914,-122.3325),'STL':(38.6226,-90.1928),'TB':(27.7683,-82.6534),
'TEX':(32.7473,-97.0833),'TOR':(43.6414,-79.3894),'WSH':(38.8730,-77.0074)}
def _getj(u):
    with urllib.request.urlopen(u, timeout=20) as _r: return json.load(_r)
def fetch_weather(games, date):
    homes=[]
    for g in games:
        h=g.get('home')
        if not g.get('dome') and h in PARK_LL and h not in homes: homes.append(h)
    if not homes: return {}, 'no open parks'
    la=','.join(str(PARK_LL[c][0]) for c in homes); lo=','.join(str(PARK_LL[c][1]) for c in homes)
    try:
        u=('https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s'
           '&hourly=temperature_2m,wind_speed_10m,wind_direction_10m'
           '&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=America%%2FNew_York'
           '&start_date=%s&end_date=%s')%(la,lo,date,date)
        d=_getj(u)
    except Exception as e:
        return {}, 'fallback (%s)'%str(e)[:40]
    locs=d if isinstance(d,list) else [d]; out={}
    for c,loc in zip(homes,locs):
        hh=loc.get('hourly') or {}
        out[c]={'time':hh.get('time') or [],'t':hh.get('temperature_2m') or [],'ws':hh.get('wind_speed_10m') or [],'wd':hh.get('wind_direction_10m') or []}
    return out, 'OK (%d parks)'%len(out)
def apply_weather(g, wx, date):
    w=wx.get(g.get('home'))
    if not w or not w.get('time'): return False
    m=re.match(r'(\d+):(\d+)\s*(AM|PM)', g.get('time') or '')
    if not m: return False
    hr=(int(m.group(1))%12)+(12 if m.group(3)=='PM' else 0); key='%sT%02d:00'%(date,hr)
    try: i=w['time'].index(key)
    except ValueError: i=min(18,len(w['time'])-1)
    if i<0: return False
    if i<len(w['t']) and w['t'][i] is not None: g['temp']=round(w['t'][i])
    if i<len(w['ws']) and w['ws'][i] is not None: g['wind']=str(round(w['ws'][i]))+' mph'
    if i<len(w['wd']) and w['wd'][i] is not None: g['wind_deg']=w['wd'][i]
    return True
def fetch_hr9(date):
    try:
        sch=_getj('https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=%s&hydrate=probablePitcher'%date)
    except Exception as e:
        return {}, 'fallback (%s)'%str(e)[:40]
    dates=sch.get('dates') or []; games=dates[0].get('games',[]) if dates else []
    A={'ARI':'AZ','CHW':'CWS'}; cc=lambda a:A.get((a or '').upper(),(a or '').upper())
    mm={}; ids=[]
    for g in games:
        try:
            a=cc(g['teams']['away']['team']['abbreviation']); h=cc(g['teams']['home']['team']['abbreviation'])
            ap=g['teams']['away'].get('probablePitcher') or {}; hp=g['teams']['home'].get('probablePitcher') or {}
            mm[a+'@'+h]={'away':ap.get('id'),'home':hp.get('id')}
            for pid in (ap.get('id'),hp.get('id')):
                if pid and pid not in ids: ids.append(pid)
        except Exception: pass
    id2={}
    if ids:
        try:
            pe=_getj('https://statsapi.mlb.com/api/v1/people?personIds=%s&hydrate=stats(group=[pitching],type=[season],season=%s)'%(','.join(map(str,ids)),date[:4]))
            for pr in pe.get('people',[]):
                v=None
                for st_ in pr.get('stats',[]):
                    sps=st_.get('splits') or []; x=(sps[0].get('stat') if sps else {}) or {}
                    if x.get('homeRunsPer9') is not None:
                        try: v=float(x['homeRunsPer9'])
                        except Exception: pass
                    elif x.get('homeRuns') is not None and x.get('inningsPitched'):
                        try: v=round(float(x['homeRuns'])/float(x['inningsPitched'])*9,2)
                        except Exception: pass
                id2[pr.get('id')]=v
        except Exception as e:
            return {}, 'people fallback (%s)'%str(e)[:40]
    out={gm:{'away':id2.get(v['away']),'home':id2.get(v['home'])} for gm,v in mm.items()}
    n=sum(1 for v in out.values() for x in v.values() if x is not None)
    return out, 'OK (%d arms)'%n

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
KEXTRA={norm(v['name']):v for v in load_dated('kasper_extras',required=False).values() if v.get('name')}
WX_LIVE,_wxs=fetch_weather(lin['games'], DATE); HR9_LIVE,_h9s=fetch_hr9(DATE)
print(f'  (live weather: {_wxs} | live HR/9: {_h9s})')
ODDS={norm(k):v for k,v in load_dated('odds').items()}
def pnorm(x):
    x=''.join(c for c in unicodedata.normalize('NFD',x or '') if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z ]','',x).strip()
HR9={pnorm(k):v for k,v in load_dated('hr9',required=False).items()}
PBRL={pnorm(k):v for k,v in load_dated('pitchers',required=False).items()}   # Kasper Top-Pitchers barrel-against export (partial -> HR/9 fallback)
# Pitcher allowed-contact term: the pitcher EQUIVALENTS of our batter power trio --
# pulled-barrel%, hard-hit%, fly-ball% ALLOWED -- standardized across the slate's starters.
# More allowed contact -> more hittable arm -> boosts the hitter. Bounded +-15% (UNVALIDATED yet;
# the calibration log now carries these per matchup and will confirm/refute as data accrues).
W_PIT=0.25   # equal weight with batter power (+/-30%); per-request parity of pitcher & batter stats
_PKS=('pbrl','hh','fb')
def _pmed(k):
    vs=[d[k] for d in PBRL.values() if isinstance(d,dict) and d.get(k) is not None]
    return (st.median(vs), (st.pstdev(vs) or 1)) if len(vs)>=3 else (None,1)
_PMED={k:_pmed(k) for k in _PKS}
def ppitT(d):
    zs=[(d[k]-_PMED[k][0])/_PMED[k][1] for k in _PKS if d.get(k) is not None and _PMED[k][0] is not None]
    return clamp(1+W_PIT*(sum(zs)/len(zs)),1-W_PIT,1+W_PIT) if zs else 1.0
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
    apply_weather(g, WX_LIVE, DATE)                     # live Open-Meteo overrides lineup wind/temp/dir
    wf=wf_of(g); gamemeta[gn]=g
    for side in ('away','home'):
        code=g[side]; opp_sp=g[('home' if side=='away' else 'away')+'_sp']
        posted={norm(x) for x in g[side+'_bats']}
        _bhand={norm(b):(g.get(side+'_hands') or [])[i] if i<len(g.get(side+'_hands') or []) else None for i,b in enumerate(g[side+'_bats'])}
        _slot={norm(b):i+1 for i,b in enumerate(g[side+'_bats'])}
        for c in cards[gm][code]:
            nm=c['name']; n=norm(nm); in_lu=n in posted
            status=('confirmed' if g.get('status')=='confirmed' else 'projected') if in_lu else 'projected'
            form=c['form_pct'] if c.get('form_pct') is not None else 50
            iso=ISO.get(n); iso_used=iso if iso is not None else ISO_FLOOR
            powraw=c['pb']*c['hh']*la_window(c['la'])
            lean='Boost' if wf>1.02 else ('Suppress' if wf<0.98 else 'Neutral')
            players[nm]=dict(nm=nm,code=code,team=FULL[code],aT=100.0,khr=(KEXTRA.get(n) or {}).get('khr'),zonev=c['zone'],form=form,pb=c['pb'],hh=c['hh'],la=c['la'],
                iso=(("."+str(iso).split('.')[1]) if iso is not None else "—"),iso_used=iso_used,powraw=powraw,slot=_slot.get(n),bhand=_bhand.get(n),
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
_imps=[100.0/(r['odds']+100) for r in pool if r.get('odds')]; medImp=st.median(_imps) if _imps else 0.13
mktT=lambda o: 1.0 if not o else clamp(1+W_MKT*((100.0/(o+100))-medImp)/0.06, 1-MKT_CLAMP, 1+MKT_CLAMP)
powT=lambda P:clamp(1+0.25*(P-medP)/40,0.75,1.25)   # power is THE driver -> widened to absorb dropped ISO (data: power AUC ~0.66, ISO ~0.55 & 0.88-redundant w/ power; pb x hh x launch)
# ISO term REMOVED from TOTAL -- weak (AUC ~0.55) and 0.88-redundant with the power index; iso still loaded for display
zoneT=lambda z:1.0 if abs(z-0.5)<1e-9 else clamp(1+0.05*(z-medZ)/0.05,0.95,1.05)
for r in pool:
    _opn=pnorm((r.get('opp') or ['',''])[0])
    if _opn in PBRL: r['phr9']=ppitT(PBRL[_opn]); r['psrc']='brl'   # listed arm -> allowed pulled-barrel%/hard-hit%/fly-ball% (pitcher equivalents of batter power)
    else:                                                              # unlisted arm -> bake the live opp HR/9 here too (was deferred to the browser)
        _gm=r.get('gmatch') or '@'; _oh=(HR9_LIVE.get(_gm) or {}).get('home' if r.get('code')==_gm.split('@')[0] else 'away')
        if _oh is not None: r['hr9']=_oh
        r['phr9']=pHR9(r.get('hr9')); r['psrc']='hr9'
    _hm=(r.get('gmatch') or '@').split('@')[-1]; _ph0=parkHandT(_hm, r.get('bhand')); r['parkhr']=1+0.6*((_ph0 if _ph0 is not None else 1)-1)
    r['mktT']=mktT(r.get('odds')); r['slotT']=slotT(r.get('slot')); r['platT']=platT(r.get('bhand'), (r.get('opp') or [None,None])[1])
    r['TOTAL']=round(r['aT']*powT(r['powidx'])*zoneT(r['zonev'])*fF(r['form'])*r['phr9']*r['parkhr']*pM(r['wf'])*r['mktT']*r['slotT']*r['platT'],1)   # ISO dropped; park/weather/zone kept

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
