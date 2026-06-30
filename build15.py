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
fF=lambda f:1.0 if f is None else clamp(1+0.001*(f-50),0.97,1.03)   # form: near-zero token -- coin-flip AUC (0.499), no real HR signal
pM=lambda w:1.0 if w is None else 1+W_WEATHER*(w-1)
la_window=lambda la:math.exp(-((la-25.0)/14.0)**2)

# ---- weather / park knobs (tunable; symmetric) ----
W_WIND   = 0.0035   # wf per mph of tailwind toward CF
W_TEMP   = 0.0015   # wf per F above 70 (cold subtracts the same)
W_ELEV   = 0.025    # wf per 1000 ft of park elevation (thin-air carry; Coors ~+13%)
W_WEATHER= 0.08     # how hard wf pushes TOTAL via pM (same up and down)
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
W_MKT=0.25; MKT_CLAMP=0.30        # market implied-prob -> TOTAL (independent info; previously used only for drafting)
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
W_PEN=0.08          # bullpen-fatigue: small SEEDED weight, pulled from park/weather (already priced by books)
W_BG=0.15           # bullpen-GAME boost: opener/TBD opposing "starter" -> proven +11% HR rate (full season) + market-underprice hint
def bullpen_games(date):
    """{team_abbrev: True} for teams throwing an opener/bullpen game today (opposing bats get the boost).
    TBD/null probable -> bullpen game; a named probable who is really a reliever (<=3 starts AND <3.5 IP/outing)
    -> opener. Best-effort: {} on any failure -> no boost, build never breaks."""
    out={}
    try:
        _tj=_getj('https://statsapi.mlb.com/api/v1/teams?sportId=1'); _idAb={t['id']:_talias(t.get('abbreviation')) for t in (_tj.get('teams') or [])}
        sch=_getj('https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=%s&hydrate=probablePitcher'%date)
        named={}
        for gd in (sch.get('dates') or []):
            for g in gd.get('games',[]):
                for side in ('away','home'):
                    tm=g['teams'][side]; ab=_idAb.get((tm.get('team') or {}).get('id'))
                    pp=tm.get('probablePitcher')
                    if not pp or not pp.get('id'):
                        if ab: out[ab]=True
                    else:
                        named[pp['id']]=ab
        if named:
            pe=_getj('https://statsapi.mlb.com/api/v1/people?personIds=%s&hydrate=stats(group=[pitching],type=[season],season=%s)'%(','.join(map(str,named)),date[:4]))
            for person in (pe.get('people') or []):
                ab=named.get(person.get('id'))
                try:
                    stt=person['stats'][0]['splits'][0]['stat']
                    gs=int(stt.get('gamesStarted') or 0); gp=int(stt.get('gamesPlayed') or 0); ip=float(stt.get('inningsPitched') or 0)
                    if ab and gp>0 and gs<=3 and ip/gp<3.0:
                        out[ab]=True
                except Exception: pass
    except Exception as e:
        print('  (bullpen games: fallback (%s))'%e); return {}
    return out
_TEAMALIAS={'ARI':'AZ','CHW':'CWS','OAK':'ATH','WSN':'WSH','SDP':'SD','SFG':'SF','TBR':'TB','KCR':'KC'}
def _talias(c):
    c=(c or '').upper(); return _TEAMALIAS.get(c,c)
def bullpen_fatigue(date):
    """Per-team bullpen fatigue from the prior 2 days' relief usage (StatsAPI; BEST-EFFORT).
    {team_abbrev: {'score':float,'pitches':int,'b2b':int}} or {} on ANY failure -> neutral term.
    Rises with total relief pitches over the last 2 days and with relievers used BOTH days
    (back-to-back -> likely down today). Seeded small and LOGGED; weight earned once it proves out."""
    import datetime as _dt
    try: d0=_dt.date.fromisoformat(date)
    except Exception: return {}
    days=[(d0-_dt.timedelta(days=k)).isoformat() for k in (1,2)]
    relief={}; abbr={}
    try:
        for dd in days:
            sch=_getj('https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=%s'%dd)
            for gd in (sch.get('dates') or []):
                for g in gd.get('games',[]):
                    if ((g.get('status') or {}).get('abstractGameState') or '').lower()!='final': continue
                    try: bx=_getj('https://statsapi.mlb.com/api/v1/game/%s/boxscore'%g.get('gamePk'))
                    except Exception: continue
                    for side in ('away','home'):
                        tm=((bx.get('teams') or {}).get(side) or {})
                        tid=((tm.get('team') or {}).get('id'))
                        if tid is None: continue
                        abbr[tid]=_talias((tm.get('team') or {}).get('abbreviation'))
                        rec=relief.setdefault(tid,{'pitches':0,'days':{}})
                        dset=rec['days'].setdefault(dd,set())
                        players=tm.get('players') or {}
                        for pid in (tm.get('pitchers') or [])[1:]:
                            pp=((players.get('ID%s'%pid) or {}).get('stats') or {}).get('pitching') or {}
                            try: rec['pitches']+=int(pp.get('numberOfPitches') or pp.get('pitchesThrown') or 0)
                            except Exception: pass
                            dset.add(pid)
    except Exception as e:
        print('  (bullpen fatigue: fallback (%s))'%e); return {}
    out={}
    for tid,rec in relief.items():
        b2b=len(rec['days'].get(days[0],set()) & rec['days'].get(days[1],set()))
        wl=clamp((rec['pitches']-110)/60.0,-1.0,1.0)
        out[abbr.get(tid) or str(tid)]={'score':round(0.6*wl+0.4*clamp(b2b/3.0,0.0,1.0),3),'pitches':rec['pitches'],'b2b':b2b}
    return out
penTfn=lambda f:1.0 if not f else clamp(1+W_PEN*float(f.get('score') or 0.0),1-W_PEN,1+W_PEN)

WX_LIVE,_wxs=fetch_weather(lin['games'], DATE); HR9_LIVE,_h9s=fetch_hr9(DATE)
BULLPEN=bullpen_fatigue(DATE)   # opposing-bullpen fatigue (LOG-ONLY now)
BG=bullpen_games(DATE)          # opposing opener/bullpen game flag (best-effort; {} offline)
print(f'  (live weather: {_wxs} | live HR/9: {_h9s})')
ODDS={norm(k):v for k,v in load_dated('odds').items()}
def pnorm(x):
    x=''.join(c for c in unicodedata.normalize('NFD',x or '') if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z ]','',x).strip()
HR9={pnorm(k):v for k,v in load_dated('hr9',required=False).items()}
PBRL={pnorm(k):v for k,v in load_dated('pitchers',required=False).items()}   # Kasper Top-Pitchers barrel-against export (partial -> HR/9 fallback)


# ---- Baseball Savant ball-tracking pulls (LOG-ONLY seed; fail-safe -> {} offline, never breaks the build) ----
import csv as _csv, io as _io
def _savant_csv(u, to=25):
    try:
        _rq=urllib.request.Request(u, headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})   # Savant WAF blocks default python-urllib UA
        with urllib.request.urlopen(_rq, timeout=to) as _r: txt=_r.read().decode('utf-8-sig','ignore')
        return list(_csv.DictReader(_io.StringIO(txt)))
    except Exception: return []
def _sv_name(row):                                       # Savant ships "Last, First" -> flip to "First Last"
    raw=(row.get('last_name, first_name') or '').strip()
    if ',' in raw:
        ln,fn=[p.strip() for p in raw.split(',',1)]; return (fn+' '+ln).strip()
    return raw
def _sv_f(row,k):
    try: return float(row.get(k))
    except Exception: return None
_SVYR=DATE[:4]
def fetch_bat_track():                                   # batter pitch-recognition: chase / whiff / in-zone contact
    out={}
    for r in _savant_csv('https://baseballsavant.mlb.com/leaderboard/custom?year=%s&type=batter&min=50&selections=oz_swing_percent,whiff_percent,iz_contact_percent,barrel_batted_rate,xiso,xwoba,xwobacon&csv=true'%_SVYR):
        nm=_sv_name(r)
        if nm: out[norm(nm)]={'chase':_sv_f(r,'oz_swing_percent'),'whiff':_sv_f(r,'whiff_percent'),'zc':_sv_f(r,'iz_contact_percent'),'barrel':_sv_f(r,'barrel_batted_rate'),'xiso':_sv_f(r,'xiso'),'xwoba':_sv_f(r,'xwoba'),'xwcon':_sv_f(r,'xwobacon'),'id':(r.get('player_id') or '').strip()}
    return out
def fetch_bat_spray():                                  # batter pull% (spray-angle) for pull-side HR alignment
    out={}
    for r in _savant_csv('https://baseballsavant.mlb.com/leaderboard/custom?year=%s&type=batter&min=50&selections=pull_percent&csv=true'%_SVYR):
        nm=_sv_name(r)
        if nm: out[norm(nm)]={'pull':_sv_f(r,'pull_percent')}
    return out
def fetch_bat_recent(ids):                              # rolling last-14d xwOBAcon per batter id (recent expected-power form)
    ids=[str(i) for i in ids if i]
    if not ids: return {}
    try:
        import datetime as _d3
        _hi=DATE; _lo=(_d3.datetime.strptime(DATE,'%Y-%m-%d')-_d3.timedelta(days=14)).strftime('%Y-%m-%d')
        u=('https://baseballsavant.mlb.com/statcast_search/csv?all=true&hfGT=R%%7C&hfSea=%s%%7C&player_type=batter&game_date_gt=%s&game_date_lt=%s&min_pitches=0&min_results=0&min_pas=0&group_by=name&sort_col=pitches&sort_order=desc&type=details'%(DATE[:4],_lo,_hi))
        u+=''.join('&batters_lookup%%5B%%5D=%s'%i for i in ids)
        agg={}
        for r in _savant_csv(u, to=55):
            bid=(r.get('batter') or '').strip()
            xw=_sv_f(r,'estimated_woba_using_speedangle')
            if bid and xw is not None: agg.setdefault(bid,[]).append(xw)
        return {bid:(sum(v)/len(v)) for bid,v in agg.items()}
    except Exception: return {}
def fetch_arsenal(kind):                                # pitch-arsenal-stats: per player per pitch type -> usage% + run_value/100
    out={}
    u='https://baseballsavant.mlb.com/leaderboard/pitch-arsenal-stats?type=%s&year=%s&min=10&csv=true'%(kind,_SVYR)
    for r in _savant_csv(u, to=45):
        pid=(r.get('player_id') or '').strip(); pt=(r.get('pitch_type') or '').strip()
        if not pid or not pt: continue
        out.setdefault(pid,{})[pt]={'usage':_sv_f(r,'pitch_usage'),'rv100':_sv_f(r,'run_value_per_100')}
    return out
def fetch_pit_velo():                                    # opposing SP fastball velo + arm angle (extension/perceived-velo added next pass via per-pitch pull)
    out={}
    for r in _savant_csv('https://baseballsavant.mlb.com/leaderboard/custom?year=%s&type=pitcher&min=20&selections=fastball_avg_speed,arm_angle&csv=true'%_SVYR):
        nm=_sv_name(r)
        if nm: out[pnorm(nm)]={'velo':_sv_f(r,'fastball_avg_speed'),'arm':_sv_f(r,'arm_angle'),'id':(r.get('player_id') or '').strip()}
    return out
def fetch_pit_ext(ids):                                  # per-pitch aggregate: perceived velo + release extension for the day's starters
    ids=[str(i) for i in ids if i]
    if not ids: return {}
    try:
        import datetime as _d2
        _hi=DATE; _lo=(_d2.datetime.strptime(DATE,'%Y-%m-%d')-_d2.timedelta(days=28)).strftime('%Y-%m-%d')
        u=('https://baseballsavant.mlb.com/statcast_search/csv?all=true&hfGT=R%%7C&hfSea=%s%%7C&hfPT=FF%%7CSI%%7CFC%%7C&player_type=pitcher&game_date_gt=%s&game_date_lt=%s&min_pitches=0&min_results=0&min_pas=0&group_by=name&sort_col=pitches&player_event_sort=api_p_release_speed&sort_order=desc&type=details'%(DATE[:4],_lo,_hi))
        u+=''.join('&pitchers_lookup%%5B%%5D=%s'%i for i in ids)
        agg={}
        for r in _savant_csv(u):
            pid=(r.get('pitcher') or r.get('player_id') or '').strip()
            if not pid: continue
            a=agg.setdefault(pid,{'es':[],'ex':[],'rs':[]})
            es=_sv_f(r,'effective_speed'); ex=_sv_f(r,'release_extension'); rs=_sv_f(r,'release_speed')
            if es is not None: a['es'].append(es)
            if ex is not None: a['ex'].append(ex)
            if rs is not None: a['rs'].append(rs)
        return {pid:{'pvelo':(sum(a['es'])/len(a['es']) if a['es'] else None),'ext':(sum(a['ex'])/len(a['ex']) if a['ex'] else None),'rvelo':(sum(a['rs'])/len(a['rs']) if a['rs'] else None)} for pid,a in agg.items()}
    except Exception: return {}
SAV_BAT=fetch_bat_track(); SAV_PIT=fetch_pit_velo(); SAV_SPRAY=fetch_bat_spray(); SAV_RECENT=fetch_bat_recent([v['id'] for v in SAV_BAT.values() if v.get('id')]); SAV_ARS_BAT=fetch_arsenal('batter'); SAV_ARS_PIT=fetch_arsenal('pitcher')
print(f'  (savant: {len(SAV_BAT)} batters, {len(SAV_PIT)} pitchers)')
_sp_ids=set()
for _g in lin.get('games',[]):
    for _k in ('away_sp','home_sp'):
        _v=_g.get(_k); _nm=(_v[0] if isinstance(_v,(list,tuple)) and _v else _v)
        _pi=(SAV_PIT.get(pnorm(_nm or '')) or {}).get('id')
        if _pi: _sp_ids.add(_pi)
SAV_EXT=fetch_pit_ext(_sp_ids)
print(f'  (savant ext: {len(SAV_EXT)} starters w/ perceived-velo + extension)')
# Park "trackability" / hitter's-eye -- JUDGMENT, not data (LOG-ONLY). +=easier to pick up the ball, -=harder.
# Most parks neutral; a few flagged from background/lighting reputation. Trivially overruled once real data exists.
PARK_TRK={'TB':0.10,'MIL':0.05,'TOR':0.05,'MIN':0.05,'HOU':0.05,'ARI':0.05,'TEX':0.05,   # roofs/controlled light -> steadier look
          'COL':-0.05,'SF':-0.05,'ATH':-0.05,'OAK':-0.05,'CIN':-0.05}                     # open sky / shadows / tougher-eye notes# Pitcher allowed-contact term: the pitcher EQUIVALENTS of our batter power trio --
# tracking terms fold into the MODEL half at TINY seed weights (signs TENTATIVE -> refined from the log)
W_BTRK=0.08; W_PVEL=0.08
def btrkTfn(r):                                          # better pitch recognition (high in-zone contact, low whiff) -> tiny boost
    zc=r.get('zc'); wh=r.get('whiff')
    if zc is None and wh is None: return 1.0
    s=((zc or 85)-85)/10.0 - ((wh or 25)-25)/15.0
    return clamp(1+W_BTRK*s, 1-W_BTRK, 1+W_BTRK)
def pvTfn(pvelo, velo):                                            # faster opposing fastball (perceived-velo proxy) -> tiny HR suppress
    v=pvelo if pvelo is not None else velo
    return 1.0 if v is None else clamp(1-W_PVEL*((v-93.5)/4.0), 1-W_PVEL, 1+W_PVEL)
def parktrkTfn(pt):                                      # park hitter's-eye judgment -> half-strength multiplier
    return 1+0.5*(pt or 0.0)
W_XPOW=0.08
def xpowTfn(xi):                                         # park-neutral expected power (xISO) -> tiny boost
    return 1.0 if xi is None else clamp(1+W_XPOW*((xi-0.16)/0.06), 1-W_XPOW, 1+W_XPOW)
W_PVDECL=0.08   # opp SP recent fastball velo (28d) vs season avg -> velo drop = losing stuff = batter boost
def pvdTfn(rvelo, svelo):                                 # recent raw fastball velo vs season; 1.5 mph drop = full weight
    if rvelo is None or svelo is None: return 1.0
    return clamp(1+W_PVDECL*((svelo-rvelo)/1.5), 1-W_PVDECL, 1+W_PVDECL)
W_SPRAY=0.08
def sprayTfn(pull, tilt, ptail):                         # pull% x handed park pull-side tilt x wind-to-pull-field
    if pull is None: return 1.0
    lean=(pull-40.0)/10.0                                # >0 = pulls more than ~league-avg 40%
    env=0.0
    if tilt is not None: env+=(tilt-1.0)/0.05            # handed park pull-side friendliness (~+-1)
    if ptail is not None: env+=clamp(ptail/8.0,-1.0,1.0) # wind blowing out to the pull field (~+-1)
    return clamp(1+W_SPRAY*lean*clamp(env,-1.5,1.5), 1-W_SPRAY, 1+W_SPRAY)
W_XPTREND=0.08
def xptrendTfn(recent, season):                          # recent (14d) xwOBAcon vs season xwOBAcon -> hot/cold expected-power form
    if recent is None or season is None: return 1.0
    return clamp(1+W_XPTREND*((recent-season)/0.040), 1-W_XPTREND, 1+W_XPTREND)
W_ARS=0.08
def arsenalTfn(bat, pit):                                # batter run-value-by-pitch-type x opposing pitcher's pitch mix
    if not bat or not pit: return 1.0
    num=0.0; den=0.0
    for pt,pv in pit.items():
        u=pv.get('usage'); bv=bat.get(pt)
        rv=(bv.get('rv100') if bv else None)
        if u is None or rv is None: continue
        num+=u*rv; den+=u
    if den<=0: return 1.0
    return clamp(1+W_ARS*((num/den)/1.5), 1-W_ARS, 1+W_ARS)
# pulled-barrel%, hard-hit%, fly-ball% ALLOWED -- standardized across the slate's starters.
# More allowed contact -> more hittable arm -> boosts the hitter. Bounded +-15% (UNVALIDATED yet;
# the calibration log now carries these per matchup and will confirm/refute as data accrues).
W_PIT=0.10   # equal weight with batter power (+/-30%); per-request parity of pitcher & batter stats
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

def pull_tail_of(home, bh, deg, windstr):                # wind projected onto the batter's PULL field (mph, + = out to pull)
    if deg is None or bh not in ('L','R'): return None
    cf=CF_AZ.get(home)
    if cf is None: return None
    m=re.search(r'(\d+)\s*mph', windstr or ''); spd=int(m.group(1)) if m else 0
    if not spd: return 0.0
    pull_az=(cf+(45 if bh=='L' else -45))%360            # LHB pull->RF (+45 off CF), RHB pull->LF (-45)
    toward=(deg+180)%360
    return spd*math.cos(math.radians(toward-pull_az))

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
                hr9=HR9.get(pnorm(opp_sp[0])),wf=wf,pull_tail=pull_tail_of(g['home'], _bhand.get(n), g.get('wind_deg'), g.get('wind')),game=gn,gmatch=gm,gtime=gt,late=is_late(gt),rain=False,out=(not in_lu),status=status,
                void=False,opp=[opp_sp[0],opp_sp[1]],oppERA=None,opp_code=g[('home' if side=='away' else 'away')],ftrend=c.get('form_arrow','flat'),
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
powT=lambda P:clamp(1+0.10*(P-medP)/40,0.90,1.10)   # power is THE driver -> widened to absorb dropped ISO (data: power AUC ~0.66, ISO ~0.55 & 0.88-redundant w/ power; pb x hh x launch)
# ISO term REMOVED from TOTAL -- weak (AUC ~0.55) and 0.88-redundant with the power index; iso still loaded for display
zoneT=lambda z:1.0 if abs(z-0.5)<1e-9 else clamp(1+0.05*(z-medZ)/0.05,0.95,1.05)
for r in pool:
    _opn=pnorm((r.get('opp') or ['',''])[0])
    if _opn in PBRL: r['phr9']=ppitT(PBRL[_opn]); r['psrc']='brl'   # listed arm -> allowed pulled-barrel%/hard-hit%/fly-ball% (pitcher equivalents of batter power)
    else:                                                              # unlisted arm -> bake the live opp HR/9 here too (was deferred to the browser)
        _gm=r.get('gmatch') or '@'; _oh=(HR9_LIVE.get(_gm) or {}).get('home' if r.get('code')==_gm.split('@')[0] else 'away')
        if _oh is not None: r['hr9']=_oh
        r['phr9']=pHR9(r.get('hr9')); r['psrc']='hr9'
    _hm=(r.get('gmatch') or '@').split('@')[-1]; _ph0=parkHandT(_hm, r.get('bhand')); r['parkhr']=1+0.30*((_ph0 if _ph0 is not None else 1)-1)
    r['mktT']=mktT(r.get('odds')); r['slotT']=slotT(r.get('slot')); r['platT']=platT(r.get('bhand'), (r.get('opp') or [None,None])[1])
    _pf=BULLPEN.get(_talias(r.get('opp_code'))); r['pen_fatigue']=(_pf or {}).get('score'); r['penT']=penTfn(_pf)
    _bg=1 if (r.get('opp_code') and _talias(r.get('opp_code')) in BG) else 0; r['bg']=_bg; r['bgT']=(1+W_BG) if _bg else 1.0
    _bt=SAV_BAT.get(norm(r['nm'])) or {}; _sp=SAV_SPRAY.get(norm(r['nm'])) or {}; r['pull']=_sp.get('pull'); r['xwoba_recent']=SAV_RECENT.get(_bt.get('id')); r['xwcon']=_bt.get('xwcon'); r['chase']=_bt.get('chase'); r['whiff']=_bt.get('whiff'); r['zc']=_bt.get('zc')
    r['barrel']=_bt.get('barrel'); r['xiso']=_bt.get('xiso'); r['xwoba']=_bt.get('xwoba')        # batter ball-tracking (LOG-ONLY)
    _pvv=SAV_PIT.get(pnorm((r.get('opp') or [''])[0])) or {}; r['opp_velo']=_pvv.get('velo'); r['opp_arm']=_pvv.get('arm')
    _ex=SAV_EXT.get(_pvv.get('id') or '') or {}; r['opp_pvelo']=_ex.get('pvelo'); r['opp_ext']=_ex.get('ext'); r['opp_rvelo']=_ex.get('rvelo')        # opp SP velo/arm (LOG-ONLY)
    r['park_trk']=PARK_TRK.get(_hm)                                                                                              # park hitter's-eye (LOG-ONLY)
    r['btrkT']=btrkTfn(r); r['pvT']=pvTfn(r.get('opp_pvelo'), r.get('opp_velo')); r['parktrkT']=parktrkTfn(r.get('park_trk')); r['xpowT']=xpowTfn(r.get('xiso')); r['pvdT']=pvdTfn(r.get('opp_rvelo'), r.get('opp_velo')); r['sprayT']=sprayTfn(r.get('pull'), (PARK_HAND.get(_hm,(1.0,1.0))[0 if r.get('bhand')=='L' else 1]) if r.get('bhand') in ('L','R') else 1.0, r.get('pull_tail')); r['xptrendT']=xptrendTfn(r.get('xwoba_recent'), r.get('xwcon')); r['arsenalT']=arsenalTfn(SAV_ARS_BAT.get(_bt.get('id')), SAV_ARS_PIT.get(_pvv.get('id')))
    r['_mm']=round(r['aT']*r['bgT']*r['btrkT']*r['pvT']*r['parktrkT']*r['xpowT']*r['pvdT']*r['sprayT']*r['xptrendT']*r['arsenalT'],4)   # model half = flat anchor x edge signals: bg, ball-track, perceived-velo, park-eye, xpower, velo-decline, spray-park, xpower-trend, pitch-arsenal

# ---- 50/50 REWEIGHT: scale the market term so its log-spread == our combined model's, then blend (stays a PRODUCT -> client live re-score unaffected) ----
import math as _math
_lm=[_math.log(r['_mm']) for r in pool if r.get('_mm',0)>0]
_lk=[_math.log(r['mktT']) for r in pool if r.get('mktT',0)>0]
_sd_m=(st.pstdev(_lm) if len(_lm)>1 else 0.0) or 1e-9
_sd_k=(st.pstdev(_lk) if len(_lk)>1 else 0.0) or 1e-9
MKT_EXP=clamp(_sd_m/_sd_k, 0.5, 6.0)
print(f'  (reweight: market exp {MKT_EXP:.2f} | model sd {_sd_m:.3f}, mkt sd {_sd_k:.3f})')
for r in pool:
    r['mkt_exp']=round(MKT_EXP,3); r['TOTAL']=round(r['_mm']*(r['mktT']**MKT_EXP),1)

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
meta={'wx':wx,'build':(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=4)).strftime('%-m/%-d %-I:%M%p').lower(),'face':{},'maxAT':round(max(r['aT'] for r in pool),1),'season':season,'date':DATE,'gs':{}}
json.dump({'players':players,'meta':meta},open('D_0615.json','w'),indent=1)
print(f"build15: {DATE} | scored {len(players)} carded | in-lineup {sum(1 for r in pool if not r['out'])} | priced {sum(1 for r in pool if r['odds'])} | season {season.get('history',[0])[-1]}u")
