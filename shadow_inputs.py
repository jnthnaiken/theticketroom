#!/usr/bin/env python3
"""
shadow_inputs.py -- KASCHAL-2026-09-10. Point-in-time inputs for the Kasper challenger. LOG-ONLY.

WHAT THIS IS
------------
Owner, 2026-09-10: build a model that picks HR hitters WITHOUT the price, graded on top-22 hit rate,
using what Vegas doesn't look at plus the few things it does that Kasper and the owner trust -- then
weather, pitching, and a bullpen predictor. The batter and starter inputs already reach the log
(D_<date>.json + kasper_extras + pitchers sidecars). What does NOT exist anywhere yet is the
BULLPEN and the RAW WEATHER. This module builds them, per slate, and writes one sidecar:

    D_shadow_<date>.json   {v, date, built_at, teams:{ABBR:{pen...}}, sps:{pnorm(name):{...}},
                            games:{gn:{...weather}}, coverage:{...}, errors:[...]}

calibrate.py joins it onto each bat's row as c_* columns.

WHY AT LOG TIME, NOT BUILD TIME
-------------------------------
Every input here is reconstructible AFTER the slate without leaking its outcome, because each one is
cut off BEFORE the slate's games:
  * reliever and starter stats   StatsAPI byDateRange, season start .. D-1  (verified 2026-09-10:
                                 Headrick BF 248 through 08-14 vs 296 through 09-09 -- the range bites)
  * bullpen availability         box scores of D-1 and D-2 -- final before D starts
  * active roster                roster?date=D -- who was on the team that day
  * weather                      Open-Meteo HISTORICAL-FORECAST API: the forecast as issued, not the
                                 observation
So the same code serves tonight and all 78 archived nights, and the board is never touched: no
build15.py, index.html, or workflow change. That is the point -- this cannot move a ticket.

DELIBERATELY NOT USED: StatsAPI statSplits (vs L / vs R). It IGNORES startDate/endDate (verified
2026-09-10: ranged and season calls return identical 104/192 BF), so on any archived night it would
include that night's own home runs. The platoon read is built instead from each reliever's THROWING
HAND and his point-in-time HR/BF.

FAILS SOFT. Every fetch is best-effort; a missing piece is None and recorded in `errors`. Nothing in
here may raise into calibrate.py, because calibrate runs BEFORE build15 on the Action and a raise
there would stop the board.
"""
import json, math, os, re, time, unicodedata, urllib.request
from concurrent.futures import ThreadPoolExecutor

VERSION = 1
SA = "https://statsapi.mlb.com/api/v1"
OM = "https://historical-forecast-api.open-meteo.com/v1/forecast"

# ---- tables copied from build15.py (build15 executes on import, so it cannot be imported) ----
PARK_LL = {'ARI':(33.4455,-112.0667),'AZ':(33.4455,-112.0667),'ATL':(33.8907,-84.4677),'BAL':(39.2839,-76.6217),
 'BOS':(42.3467,-71.0972),'CHC':(41.9484,-87.6553),'CWS':(41.8300,-87.6339),'CIN':(39.0975,-84.5069),
 'CLE':(41.4962,-81.6852),'COL':(39.7559,-104.9942),'DET':(42.3390,-83.0485),'HOU':(29.7572,-95.3556),
 'KC':(39.0517,-94.4803),'LAA':(33.8003,-117.8827),'LAD':(34.0739,-118.2400),'MIA':(25.7780,-80.2197),
 'MIL':(43.0280,-87.9712),'MIN':(44.9817,-93.2776),'NYM':(40.7571,-73.8458),'NYY':(40.8296,-73.9262),
 'ATH':(38.5800,-121.5160),'PHI':(39.9061,-75.1665),'PIT':(40.4469,-80.0057),'SD':(32.7073,-117.1566),
 'SF':(37.7786,-122.3893),'SEA':(47.5914,-122.3325),'STL':(38.6226,-90.1928),'TB':(27.7683,-82.6534),
 'TEX':(32.7473,-97.0833),'TOR':(43.6414,-79.3894),'WSH':(38.8730,-77.0074)}
CF_AZ = {'ARI':0,'AZ':0,'ATL':50,'BAL':30,'BOS':45,'CHC':30,'CWS':38,'CIN':40,'CLE':0,'COL':0,'DET':30,'HOU':20,
 'KC':45,'LAA':40,'LAD':25,'MIA':35,'MIL':30,'MIN':7,'NYM':25,'NYY':15,'ATH':62,'PHI':15,'PIT':70,
 'SD':0,'SF':85,'SEA':60,'STL':30,'TB':50,'TEX':40,'TOR':0,'WSH':30}
_TEAMALIAS = {'ARI':'AZ','CHW':'CWS','OAK':'ATH','SAC':'ATH','WSN':'WSH','WAS':'WSH','SDP':'SD','SFG':'SF','TBR':'TB','KCR':'KC'}

# ---- model constants (documented, not fitted -- these shape RAW inputs, the fit weighs them) ----
LG_HR_BF   = 0.030   # league-ish HR per batter faced; shrink target for thin reliever samples
SHRINK_BF  = 150     # pseudo-BF of league average added to every pen rate (a 40-BF call-up can't swing it)
PA_SLOT1   = 4.65    # expected PA for the leadoff bat; each slot down loses PA_STEP
PA_STEP    = 0.105
SP_BF_DEF  = 22.0    # starter batters-faced when there is no usable history
RELIEF_SHARE = 0.35  # a relief appearance's batters faced as a share of a start's
OPENER_BF  = 9.0     # a "starter" with <3 GS through D-1 is treated as an opener
B2B_OUT    = True    # a reliever who pitched D-1 AND D-2 is unavailable
D1_PITCHES_OUT = 30  # ... or who threw this many pitches on D-1
TOP_ARMS   = 4       # "best arms" = top-N relievers by saves+holds (BF breaks ties)


def _talias(c):
    c = (c or '').upper()
    return _TEAMALIAS.get(c, c)


def pnorm(x):
    x = ''.join(c for c in unicodedata.normalize('NFD', x or '') if not unicodedata.combining(c)).lower()
    x = re.sub(r'[^a-z ]', '', x).strip()
    return re.sub(r'\s+(jr|jnr|junior|sr|snr|senior|ii|iii|iv|v)$', '', x)


def _getj(u, timeout=10):
    rq = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0 ticketroom-shadow'})
    with urllib.request.urlopen(rq, timeout=timeout) as r:
        return json.load(r)


def _day(date, k):
    import datetime as dt
    return (dt.date.fromisoformat(date) - dt.timedelta(days=k)).isoformat()


def _f(x):
    try:
        return float(x)
    except Exception:
        return None


def _i(x):
    try:
        return int(x)
    except Exception:
        return 0


def air_density(temp_f, rh, pres_hpa):
    """kg/m^3 from temperature (F), relative humidity (%), station pressure (hPa). Tetens for e_s.
    Denser air = more drag = shorter fly balls, so LOWER is better for a hitter."""
    if temp_f is None or rh is None or pres_hpa is None:
        return None
    tc = (temp_f - 32.0) * 5.0 / 9.0
    tk = tc + 273.15
    es = 6.1078 * 10 ** (7.5 * tc / (tc + 237.3))          # hPa
    pv = (rh / 100.0) * es * 100.0                          # Pa
    pd = pres_hpa * 100.0 - pv
    return round(pd / (287.058 * tk) + pv / (461.495 * tk), 4)


def _gmin_et(gt):
    m = re.match(r'(\d+):(\d+)\s*(AM|PM)', gt or '')
    return (int(m.group(1)) % 12 + (12 if m.group(3) == 'PM' else 0)) if m else None


def build(date, D, getj=_getj, workers=8):
    """Build the sidecar for slate `date` from its archived board `D` (D_<date>.json). Never raises."""
    errors, cov = [], {}
    out = {'v': VERSION, 'date': date, 'built_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
           'teams': {}, 'sps': {}, 'games': {}, 'coverage': cov, 'errors': errors}
    season0 = f"{date[:4]}-03-01"
    d1, d2 = _day(date, 1), _day(date, 2)
    players = (D or {}).get('players') or {}

    def safe(u):
        try:
            return getj(u)
        except Exception as e:
            errors.append(f"{u.split('/api/v1')[-1][:80]}: {str(e)[:60]}")
            return None

    # ---- 1. who plays today, and which teams (board codes) ----
    board_teams = sorted({_talias(p.get('code')) for p in players.values() if p.get('code')} |
                         {_talias(p.get('opp_code')) for p in players.values() if p.get('opp_code')})
    tj = safe(f"{SA}/teams?sportId=1&season={date[:4]}") or {}
    ab2id = {_talias(t.get('abbreviation')): t.get('id') for t in (tj.get('teams') or [])}
    if not ab2id:                     # StatsAPI unreachable: stop here, don't burn the build's time budget
        cov['down'] = True            # on 70 more calls that will all time out. calibrate treats this as
        return out                    # "no data" -- nothing is written and the night is retried later.

    # ---- 2. probable starters today (name -> id) ----
    sch = safe(f"{SA}/schedule?sportId=1&date={date}&hydrate=probablePitcher") or {}
    prob = {}
    for gd in (sch.get('dates') or []):
        for g in gd.get('games', []):
            for side in ('away', 'home'):
                pp = (g.get('teams') or {}).get(side, {}).get('probablePitcher') or {}
                if pp.get('id') and pp.get('fullName'):
                    prob[pnorm(pp['fullName'])] = pp['id']

    # ---- 3. relief usage on D-1 and D-2 (availability) ----
    usage = {}   # team_id -> pid -> {'d1': pitches or None, 'd2': bool}
    finals = []
    for dd in (d1, d2):
        s = safe(f"{SA}/schedule?sportId=1&date={dd}") or {}
        for gd in (s.get('dates') or []):
            for g in gd.get('games', []):
                if ((g.get('status') or {}).get('abstractGameState') or '').lower() == 'final':
                    finals.append((dd, g.get('gamePk')))
    with ThreadPoolExecutor(workers) as ex:
        boxes = list(ex.map(lambda t: (t[0], safe(f"{SA}/game/{t[1]}/boxscore")), finals))
    for dd, bx in boxes:
        if not bx:
            continue
        for side in ('away', 'home'):
            tm = ((bx.get('teams') or {}).get(side) or {})
            tid = (tm.get('team') or {}).get('id')
            if tid is None:
                continue
            pl = tm.get('players') or {}
            for pid in (tm.get('pitchers') or [])[1:]:          # [0] is the starter
                st = (((pl.get(f'ID{pid}') or {}).get('stats') or {}).get('pitching') or {})
                n = _i(st.get('numberOfPitches') or st.get('pitchesThrown'))
                u = usage.setdefault(tid, {}).setdefault(pid, {'d1': None, 'd2': False})
                if dd == d1:
                    u['d1'] = (u['d1'] or 0) + n
                else:
                    u['d2'] = True
    cov['box_final_games'] = len(finals)
    cov['box_loaded'] = sum(1 for _, b in boxes if b)

    # ---- 4. active rosters on D (pitchers only) ----
    tids = [ab2id[a] for a in board_teams if a in ab2id]
    with ThreadPoolExecutor(workers) as ex:
        rosters = dict(zip(tids, ex.map(lambda t: safe(f"{SA}/teams/{t}/roster?rosterType=active&date={date}"), tids)))
    ros = {}
    for tid, r in rosters.items():
        ros[tid] = [x['person']['id'] for x in ((r or {}).get('roster') or [])
                    if (x.get('position') or {}).get('type') == 'Pitcher' and (x.get('person') or {}).get('id')]
    cov['rosters'] = sum(1 for v in ros.values() if v)

    # ---- 5. point-in-time season stats through D-1 for every rostered pitcher + today's probables ----
    ids = sorted({p for v in ros.values() for p in v} | set(prob.values()))
    chunks = [ids[i:i + 40] for i in range(0, len(ids), 40)]
    def people(ch):
        return safe(f"{SA}/people?personIds={','.join(map(str, ch))}"
                    f"&hydrate=stats(group=[pitching],type=[byDateRange],startDate={season0},endDate={d1})")
    with ThreadPoolExecutor(workers) as ex:
        pres = list(ex.map(people, chunks))
    ps = {}
    for pj in pres:
        for pe in ((pj or {}).get('people') or []):
            stat = {}
            for sx in (pe.get('stats') or []):
                sp = sx.get('splits') or []
                if sp:
                    stat = sp[0].get('stat') or {}
            ps[pe.get('id')] = {
                'name': pe.get('fullName'), 'hand': ((pe.get('pitchHand') or {}).get('code') or '')[:1],
                'gp': _i(stat.get('gamesPlayed')), 'gs': _i(stat.get('gamesStarted')),
                'bf': _i(stat.get('battersFaced')), 'hr': _i(stat.get('homeRuns')),
                'ao': _i(stat.get('airOuts')), 'go': _i(stat.get('groundOuts')),
                'sv': _i(stat.get('saves')), 'hld': _i(stat.get('holds'))}
    cov['pitcher_stats'] = len(ps)

    # ---- 6. starters named on the board -> expected batters faced ----
    for p in players.values():
        nm = (p.get('opp') or [None])[0]
        if not nm:
            continue
        k = pnorm(nm)
        if k in out['sps']:
            continue
        pid = prob.get(k)
        s = ps.get(pid) if pid else None
        if s and s['gs'] >= 3:
            # battersFaced is starts AND relief outings together; a relief outing is ~1/3 of a start,
            # so a swingman's per-start load is recovered as bf / (gs + RELIEF_SHARE * relief games).
            bf_exp, kind = min(27.0, s['bf'] / (s['gs'] + RELIEF_SHARE * (s['gp'] - s['gs']))), 'sp'
        elif s and s['gp'] > 0:
            bf_exp, kind = OPENER_BF, 'opener'
        else:
            bf_exp, kind = SP_BF_DEF, 'unknown'
        out['sps'][k] = {'id': pid, 'bf_exp': round(bf_exp, 2), 'kind': kind,
                         'hr_bf': (round((s['hr'] + SHRINK_BF * LG_HR_BF) / (s['bf'] + SHRINK_BF), 4) if s else None)}
    cov['sps_matched'] = sum(1 for v in out['sps'].values() if v['id'])
    cov['sps_named'] = len(out['sps'])

    # ---- 7. bullpens ----
    sp_ids_today = {v['id'] for v in out['sps'].values() if v['id']}
    for ab in board_teams:
        tid = ab2id.get(ab)
        if tid is None or not ros.get(tid):
            continue
        rel = []
        for pid in ros[tid]:
            s = ps.get(pid)
            if not s or s['gp'] == 0 or pid in sp_ids_today:
                continue
            if s['gs'] / s['gp'] >= 0.5:
                continue
            u = (usage.get(tid) or {}).get(pid) or {}
            out_ = bool((B2B_OUT and u.get('d1') is not None and u.get('d2')) or (u.get('d1') or 0) >= D1_PITCHES_OUT)
            rel.append(dict(s, pid=pid, unavail=out_))
        if not rel:
            continue

        def rate(rs, key='hr'):
            bf = sum(r['bf'] for r in rs); x = sum(r[key] for r in rs)
            return round((x + SHRINK_BF * LG_HR_BF) / (bf + SHRINK_BF), 4)
        bf_all = sum(r['bf'] for r in rel) or 1
        avail = [r for r in rel if not r['unavail']] or rel
        top = sorted(rel, key=lambda r: (-(r['sv'] + r['hld']), -r['bf']))[:TOP_ARMS]
        byh = {h: [r for r in rel if r['hand'] == h] for h in ('L', 'R')}
        byh_av = {h: [r for r in avail if r['hand'] == h] for h in ('L', 'R')}
        ao = sum(r['ao'] for r in rel); go = sum(r['go'] for r in rel)
        out['teams'][ab] = {
            'n_rel': len(rel), 'n_unavail': sum(r['unavail'] for r in rel),
            'top_out': sum(1 for r in top if r['unavail']),
            'hr_bf': rate(rel), 'hr_bf_avail': rate(avail),
            'hr_bf_L': rate(byh['L']) if byh['L'] else None, 'hr_bf_R': rate(byh['R']) if byh['R'] else None,
            'hr_bf_avail_L': rate(byh_av['L']) if byh_av['L'] else None,
            'hr_bf_avail_R': rate(byh_av['R']) if byh_av['R'] else None,
            'share_L': round(sum(r['bf'] for r in byh['L']) / bf_all, 3),
            'air_share': round(ao / (ao + go), 3) if (ao + go) else None,
            'd1_pitches': sum((r_u.get('d1') or 0) for r_u in (usage.get(tid) or {}).values()),
        }
    cov['pens'] = len(out['teams'])

    # ---- 8. weather at first pitch (forecast as issued) ----
    wxmeta = ((D or {}).get('meta') or {}).get('wx') or {}
    games = {}
    for p in players.values():
        gn = p.get('game')
        if gn is None or str(gn) in games:
            continue
        home = _talias(((p.get('gmatch') or '@').split('@')[-1]))
        w = wxmeta.get(str(gn)) or {}
        dome = (w.get('cond') == 'Dome') or ('\U0001f3df' in (w.get('emoji') or ''))
        games[str(gn)] = {'home': home, 'hour': _gmin_et(p.get('gtime')), 'dome': dome}
    homes = sorted({g['home'] for g in games.values() if g['home'] in PARK_LL})
    wx = {}
    if homes:
        u = (f"{OM}?latitude={','.join(str(PARK_LL[h][0]) for h in homes)}"
             f"&longitude={','.join(str(PARK_LL[h][1]) for h in homes)}"
             "&hourly=temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,wind_direction_10m"
             f"&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=America%2FNew_York&start_date={date}&end_date={date}")
        wj = safe(u)
        locs = wj if isinstance(wj, list) else ([wj] if wj else [])
        for h, loc in zip(homes, locs):
            wx[h] = (loc or {}).get('hourly') or {}
    for gn, g in games.items():
        hh = wx.get(g['home']) or {}
        i = None
        if hh.get('time') and g['hour'] is not None:
            key = f"{date}T{g['hour']:02d}:00"
            i = hh['time'].index(key) if key in hh['time'] else None
        pick = (lambda k: (hh.get(k) or [None] * 24)[i] if i is not None and i < len(hh.get(k) or []) else None)
        t, rh, pr, ws, wd = (pick('temperature_2m'), pick('relative_humidity_2m'), pick('surface_pressure'),
                             pick('wind_speed_10m'), pick('wind_direction_10m'))
        if g['dome']:
            g.update(temp=72.0, rh=50.0, pres=pr, wind=0.0, wind_out=0.0, rho=air_density(72.0, 50.0, pr))
        else:
            wo = None
            if ws is not None and wd is not None and g['home'] in CF_AZ:
                wo = round(ws * math.cos(math.radians(((wd + 180) % 360) - CF_AZ[g['home']])), 2)
            g.update(temp=t, rh=rh, pres=pr, wind=ws, wind_out=wo, rho=air_density(t, rh, pr))
    out['games'] = games
    cov['games'] = len(games)
    cov['games_wx'] = sum(1 for g in games.values() if g.get('rho') is not None)
    return out


# =====================================================================================
# Per-bat challenger columns. Pure: board player + sidecars -> dict of c_* values.
# =====================================================================================
MIN_DMG_BIP = 40
MIN_SPLIT_PIT = 300
_PARK2 = None


def park2_table(here=None):
    """KASV1-2026-09-10: empirical park-by-hand HR factors for the current season (venue HR/PA by batter
    side over the prior 3 seasons vs league, shrunk -- exactly what kas_train_build.py computes for the
    Statcast fit), plus each team's home venue. Replaces build15's static table for the challenger only."""
    global _PARK2
    if _PARK2 is None:
        try:
            _PARK2 = json.load(open(os.path.join(here or os.path.dirname(os.path.abspath(__file__)), 'park_hand_2026.json')))
        except Exception:
            _PARK2 = {}
    return _PARK2


C_KEYS = ('c_v', 'c_dmg', 'c_khr', 'c_hh', 'c_la', 'c_fb', 'c_park2',
          'c_ars', 'c_sp_fb', 'c_sp_swstr', 'c_sp_csw',
          'c_sp_bf', 'c_pen_pa', 'c_pen_hr', 'c_pen_hr_side', 'c_pen_top_out', 'c_pen_air',
          'c_pen_x', 'c_wind_out', 'c_temp', 'c_rho', 'c_dome', 'c_park')


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def columns(p, ex, parm, sh):
    """p: board player dict. ex: his kasper_extras row. parm: his opposing starter's pitchers row.
    sh: D_shadow sidecar for the night (or None). Returns {c_*: value}. Never raises on bad data."""
    c = {k: None for k in C_KEYS}
    ex = ex or {}; parm = parm or {}
    # -- batter --
    iso, xwc, bip = ex.get('iso'), ex.get('xwobacon'), ex.get('bip')
    if _num(iso) and 0.02 <= iso <= 0.60 and _num(xwc) and xwc > 0.05 and _num(bip) and bip >= MIN_DMG_BIP:
        c['c_dmg'] = round(iso / xwc, 4)
    c['c_khr'] = ex.get('khr') if _num(ex.get('khr')) else (p.get('khr') if _num(p.get('khr')) else None)
    c['c_hh'] = p.get('hh') if _num(p.get('hh')) else None
    c['c_la'] = round(math.exp(-((p['la'] - 25.0) / 14.0) ** 2), 4) if _num(p.get('la')) else None
    c['c_fb'] = ex.get('fb') if _num(ex.get('fb')) else None
    # -- starter (vs the side this bat hits from; switch hitters take the opposite of the arm) --
    c['c_ars'] = p.get('_zars') if _num(p.get('_zars')) else None
    phand = (((p.get('opp') or ['', ''])[1:] or [''])[0] or '').upper()[:1]
    side = p.get('bhand')
    if side == 'S':
        side = 'L' if phand == 'R' else ('R' if phand == 'L' else None)
    split = parm.get('vR' if side == 'R' else 'vL') if side in ('L', 'R') else None
    use = split if (isinstance(split, dict) and (split.get('pit') or 0) >= MIN_SPLIT_PIT) else parm
    for k, ck in (('fb', 'c_sp_fb'), ('swstr', 'c_sp_swstr'), ('csw', 'c_sp_csw')):
        v = use.get(k) if _num(use.get(k)) else parm.get(k)
        c[ck] = v if _num(v) else None
    c['c_park'] = round(1 + (p['parkhr'] - 1) / 0.30, 4) if _num(p.get('parkhr')) else None
    pt = park2_table()
    if pt and side in ('L', 'R'):
        home = _talias(((p.get('gmatch') or '@').split('@')[-1]))
        v = (pt.get('venues') or {}).get(str((pt.get('teams') or {}).get(home)))
        c['c_park2'] = v.get(side) if isinstance(v, dict) and _num(v.get(side)) else None
    if not sh:
        return c
    c['c_v'] = sh.get('v')
    # -- bullpen --
    spk = pnorm((p.get('opp') or [''])[0] or '')
    sp = (sh.get('sps') or {}).get(spk) or {}
    bf_exp = sp.get('bf_exp') if _num(sp.get('bf_exp')) else SP_BF_DEF
    c['c_sp_bf'] = bf_exp
    slot = p.get('slot')
    if _num(slot) and 1 <= slot <= 9:
        pa = PA_SLOT1 - PA_STEP * (slot - 1)
        vs_sp = min(pa, max(0.0, (bf_exp - (slot - 1)) / 9.0))
        c['c_pen_pa'] = round(pa - vs_sp, 3)
    pen = (sh.get('teams') or {}).get(_talias(p.get('opp_code'))) or {}
    if pen:
        c['c_pen_hr'] = pen.get('hr_bf_avail')
        c['c_pen_top_out'] = pen.get('top_out')
        c['c_pen_air'] = pen.get('air_share')
        # platoon exposure: a LHB gains against RHP relievers and vice versa. Weighted by BF share.
        bh = p.get('bhand')
        hl, hr_ = pen.get('hr_bf_avail_L'), pen.get('hr_bf_avail_R')
        sl = pen.get('share_L')
        if bh in ('L', 'R') and _num(sl):
            opp_rate = hr_ if bh == 'L' else hl
            same_rate = hl if bh == 'L' else hr_
            opp_share = (1 - sl) if bh == 'L' else sl
            base = pen.get('hr_bf_avail')
            opp_rate = opp_rate if _num(opp_rate) else base
            same_rate = same_rate if _num(same_rate) else base
            if _num(opp_rate) and _num(same_rate):
                c['c_pen_hr_side'] = round(opp_share * opp_rate + (1 - opp_share) * same_rate, 4)
        elif bh == 'S':
            c['c_pen_hr_side'] = pen.get('hr_bf_avail')
        rate = c['c_pen_hr_side'] if _num(c['c_pen_hr_side']) else c['c_pen_hr']
        if _num(rate) and _num(c['c_pen_pa']):
            c['c_pen_x'] = round(c['c_pen_pa'] * rate, 4)   # expected HR off the pen, before park/weather
    # -- weather --
    g = (sh.get('games') or {}).get(str(p.get('game'))) or {}
    if g:
        c['c_wind_out'] = g.get('wind_out'); c['c_temp'] = g.get('temp'); c['c_rho'] = g.get('rho')
        c['c_dome'] = 1 if g.get('dome') else 0
    return c


def sidecar_path(date, here=None):
    return os.path.join(here or os.path.dirname(os.path.abspath(__file__)), f"D_shadow_{date}.json")


def load(date, here=None):
    try:
        return json.load(open(sidecar_path(date, here)))
    except Exception:
        return None


if __name__ == '__main__':
    import sys
    d = sys.argv[1]
    D = json.load(open(f"D_{d}.json"))
    sc = build(d, D)
    json.dump(sc, open(sidecar_path(d), 'w'), indent=1)
    print(json.dumps(sc['coverage']), len(sc['errors']), 'errors')
