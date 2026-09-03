#!/usr/bin/env python3
"""
nfl_payload.py -- build the `D` object the room renders from.

Sibling of soccer_payload.py. The football room is a SEAM TRANSFORM of index.html, exactly as the
soccer room is (owner, 2026-08-24: "it should be built the exact same way as mlb in terms of the
user interface and aesthetics"), so this file's job is NOT to invent a shape -- it is to fill the
shape index.html already renders, with football values. Field names below are baseball names on
purpose: `khr`, `hh`, `la`, `zonev`, `powidx`. They are the renderer's slots, and renaming them
would mean forking the renderer, which is the thing we are refusing to do.

WHAT GOES IN WHICH SLOT, and why -- the four measured terms (nfl/MODEL-2026-09-02.md):

    slot      baseball meaning        football value            measured lift
    hh        hard-hit %             touches / game             +28.2pp
    la        launch angle           inside-10 touches / game    +6.6pp  (usage AND price held)
    zonev     zone value             inside-10 share of touches  +5.0pp  (usage AND price held)
    powidx    power index            implied team total          +8.6pp  (usage held)
    khr       Kasper base score      model P(TD) x100            -- the model's own output
    wf        park/weather factor    weather factor              wind trim, -1.6pp above 11mph

⚠️ `phr9` / `hr9` STAY NULL. That slot is the opposing pitcher's HR/9 -- the matchup term. Its
football analogue measured +0.8pp (opponent red-zone trips allowed) and -0.2pp (opponent TD rate
allowed inside the 10) with usage and price held. The whole opponent-adjustment genre is dead on
both instruments. Leaving the slot null is the honest render; inventing a number to fill a chip
would be decoration, and the chip itself is re-labelled by the fork.

⚠️ `GCAL` IS MLB-FITTED AND THE FORK NULLS IT. The Hit-rate and House chips derive from a
calibration fitted on baseball TOTALs (mu 98.4, sd 32.2). Football TOTALs are on the same
100+30*blend scale but the mapping to a hit rate is not the same curve, and there are no graded
football nights to fit one on yet. Same call the soccer room made.
"""
import argparse, json, math, re, sys
from collections import defaultdict

TEAM_NAME = {
 'ARI':'Cardinals','ATL':'Falcons','BAL':'Ravens','BUF':'Bills','CAR':'Panthers','CHI':'Bears',
 'CIN':'Bengals','CLE':'Browns','DAL':'Cowboys','DEN':'Broncos','DET':'Lions','GB':'Packers',
 'HOU':'Texans','IND':'Colts','JAX':'Jaguars','KC':'Chiefs','LA':'Rams','LAC':'Chargers',
 'LV':'Raiders','MIA':'Dolphins','MIN':'Vikings','NE':'Patriots','NO':'Saints','NYG':'Giants',
 'NYJ':'Jets','PHI':'Eagles','PIT':'Steelers','SEA':'Seahawks','SF':'49ers','TB':'Buccaneers',
 'TEN':'Titans','WAS':'Commanders'}

def hhmm(m):
    h = m // 60; ap = 'PM' if h >= 12 else 'AM'; h12 = h - 12 if h > 12 else (12 if h == 0 else h)
    return f'{h12}:{m % 60:02d} {ap} ET'

def am_to_dec(o):  return 1 + o / 100.0 if o > 0 else 1 + 100.0 / abs(o)
def dec_to_am(d):
    if d <= 1: return 0
    return int(round((d - 1) * 100)) if d >= 2 else -int(round(100 / (d - 1)))

def rr_maxprofit(legs, risk):
    """Round robin by 2s & 3: every pair and the treble, each staked `risk`. Max profit is the
    all-win case. Mirrors soccer_payload.rr_maxprofit so the two rooms quote the same number."""
    dec = [am_to_dec(l['odds']) for l in legs if l.get('odds')]
    L = len(dec)
    if L < 2: return 0.0
    tot, n = 0.0, 0
    for a in range(L):
        for b in range(a + 1, L):
            tot += dec[a] * dec[b]; n += 1
    if L >= 3:
        for a in range(L):
            for b in range(a + 1, L):
                for c in range(b + 1, L):
                    tot += dec[a] * dec[b] * dec[c]; n += 1
    return round((risk / n) * tot - risk, 1) if n else 0.0

def wx_of(mm, wx_src):
    """meta.wx entry. The football room KEEPS the baseball weather lane rather than replacing it
    (soccer had to substitute a rotation lane); only the label changes, in the fork."""
    w = (wx_src or {}).get(mm['slug'], {})
    indoor = str(mm.get('roof') or '').lower() in ('dome', 'closed')
    wind = float(w.get('wind', 0) or 0)
    precip = int(w.get('precip', 0) or 0)
    if indoor:
        return dict(emoji='🏟', lean='Neutral', factor=1.014, park=mm['label'],
                    cond='indoors', rain='—', precip=0)
    if precip >= 40:  emoji, lean = '🌧️', 'Suppress'
    elif wind >= 15:  emoji, lean = '💨', 'Suppress'
    elif wind >= 11:  emoji, lean = '💨', 'Slight'
    else:             emoji, lean = '☀️', 'Boost' if wind <= 7 else 'Neutral'
    f = 1.014 if wind <= 7 else (1.000 if wind <= 11 else (0.985 if wind <= 15 else 0.984))
    if wind <= 3: f = 0.998
    return dict(emoji=emoji, lean=lean, factor=round(f, 3), park=mm['label'],
                cond=f'{int(wind)} mph', rain=f'{precip}% rain', precip=precip)

def note_for(kind, legs, P):
    """Prose from the four terms that actually measured. No matchup claims -- there is no
    defensive term on this board and the note must not imply one."""
    bits = []
    for l in legs[:3]:
        p = P[l['name']]
        if p['la'] and p['la'] >= 1.5:
            bits.append(f"{p['nm'].split()[-1]} is getting {p['la']:.1f} looks a game inside the ten")
        elif p['zonev'] and p['zonev'] >= 0.12:
            bits.append(f"{int(p['zonev']*100)}% of {p['nm'].split()[-1]}'s work comes inside the ten")
        elif p['powidx'] and p['powidx'] >= 25:
            bits.append(f"{p['nm'].split()[-1]}'s side is implied for {p['powidx']:.1f}")
        else:
            bits.append(f"{p['nm'].split()[-1]} is on {p['hh']:.1f} touches a game")
    if not bits: return ''
    s = ', '.join(bits[:-1]) + (', and ' if len(bits) > 1 else '') + bits[-1]
    return s[0].upper() + s[1:] + '.'

def build(scored, tickets, fx, wx_src, season_path=None, build_stamp='', wk=None):
    matches = fx['matches']
    order = sorted(matches.keys(), key=lambda k: (matches[k]['kickoff'], k))
    gidx = {k: i + 1 for i, k in enumerate(order)}
    last_wave = max(matches[k]['kickoff'] for k in matches)

    meta_wx = {}
    for k in order:
        mm = matches[k]
        meta_wx[str(gidx[k])] = wx_of(dict(slug=k, roof=mm.get('roof'),
                                           label=f"{mm['away']}@{mm['home']}"), wx_src)

    P = {}
    for s in scored:
        k = s['match']; mm = matches[k]
        P[s['name']] = dict(
            nm=s['name'], code=s['team'], team=TEAM_NAME.get(s['team'], s['team']),
            aT=100, khr=round(s['p_model'] * 100, 1),
            zonev=s['i10_share'],                 # inside-10 share of own touches
            form=None, pb=round(s['tchpg'], 1), hh=round(s['tchpg'], 1),
            la=round(s['i10pg'], 2), iso='—', iso_used=None,
            powraw=None, powidx=round(s['imp'], 1),      # implied team total
            slot=None, bhand=s['pos'],
            hr9=None, phr9=None,                  # ⚠️ no matchup term -- measured dead
            wf=s['wf'], pull_tail=None,
            game=gidx[k], gmatch=f"{mm['away']}@{mm['home']}", gtime=hhmm(mm['kickoff']),
            late=mm['kickoff'] == last_wave, rain=meta_wx[str(gidx[k])]['precip'] >= 40,
            out=bool(s.get('out')), status='projected', void=bool(s.get('void')),
            opp=[TEAM_NAME.get(s['opp'], s['opp']), ''], oppERA=None, opp_code=s['opp'],
            ftrend=None, odds=s['odds'], soft=False, why=None,
            basis=s.get('basis'), basis_games=s.get('basis_games'),
            mkt_z=None, edge_z=None, blend=s['blend'],
            baseTotal=s['TOTAL'], TOTAL=s['TOTAL'])

    T = []
    for t in tickets:
        legs = []
        for l in t['legs']:
            p = P[l['name']]
            legs.append(dict(name=l['name'], team=p['team'], total=p['TOTAL'], aT=100,
                             wf=p['wf'], gmatch=p['gmatch'], gtime=p['gtime'], game=p['game'],
                             late=p['late'], odds=p['odds'], status=p['status']))
        dec = 1.0
        for l in legs: dec *= am_to_dec(l['odds'])
        lock = min(legs, key=lambda l: matches[[k for k in order if gidx[k] == l['game']][0]]['kickoff'])
        wxs = defaultdict(int)
        for l in legs:
            wxs[meta_wx[str(l['game'])]['lean'].lower()] += 1
        T.append(dict(
            name=t['name'], kind=t['kind'], badge=t['badge'],
            note=note_for(t['kind'], t['legs'], P),
            players=legs, nlegs=len(legs), anchor=t['anchor'],
            lock=lock['gtime'], has_late=any(l['late'] for l in legs), final=False,
            rr=(dict(struct='by 2s & 3', risk=t['risk'],
                     maxprofit=rr_maxprofit(t['legs'], t['risk']), bytwos=False)
                if len(legs) > 1 else None),
            wxsum=dict(wxs), confleg=0, locked=False, priced=True,
            parlay_am=dec_to_am(dec) if len(legs) > 1 else legs[0]['odds'],
            payout10=round(10 * dec, 1)))

    season = {}
    if season_path:
        try: season = json.load(open(season_path, encoding='utf-8'))
        except Exception: season = {}

    return dict(
        players=P,
        pool=[s['name'] for s in scored],
        tickets=T,
        meta=dict(wx=meta_wx, build=build_stamp, face={}, maxAT=100, season=season,
                  date=fx['date'], gs={}, chalkever={}, chalkstate={}, chalk=[],
                  pool=len(scored), gate=len({l['name'] for t in T for l in t['players']}),
                  tickets=len(T), week=fx.get('week'), sport='nfl',
                  ko={str(gidx[k]): matches[k]['kickoff'] for k in order}))

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('scored'); ap.add_argument('tickets'); ap.add_argument('fixtures')
    ap.add_argument('out')
    ap.add_argument('--wx', default=None); ap.add_argument('--season', default=None)
    ap.add_argument('--build', default='')
    A = ap.parse_args()
    wx = json.load(open(A.wx, encoding='utf-8')) if A.wx else {}
    D = build(json.load(open(A.scored, encoding='utf-8')),
              json.load(open(A.tickets, encoding='utf-8')),
              json.load(open(A.fixtures, encoding='utf-8')),
              wx, A.season, A.build)
    json.dump(D, open(A.out, 'w'), ensure_ascii=False, separators=(', ', ': '))
    print(f'{A.out}: {len(D["players"])} players, {len(D["tickets"])} tickets, '
          f'{len(D["meta"]["wx"])} games')
    print('  wx:', ' '.join(f'{k}:{v["emoji"]}{v["factor"]}' for k, v in list(D['meta']['wx'].items())[:6]))
