#!/usr/bin/env python3
"""nba_espn.py -- FIRSTBASKET-2026-10-17. Read one finished (or live) NBA game off ESPN's site API.

Two consumers, one parser, so the settle and the model can never disagree about what happened:
  * nba_settle.py grades the first-basket picks (who made the game's first FIELD GOAL, who started,
    who did not play) and
  * feeds nba_fb.State.update() the same record shape the 2014-26 replay was built from.

THE RULES (read before changing):
  * FDRULES-2026-10-24 -- WE GRADE BY FANDUEL. FanDuel "First Basket" is "resulted on the first score of the game":
    FREE THROWS COUNT (owner, 10-24, after Jarrett Allen's two free throws beat Peyton Watson's three: "we're going
    by fanduel rules"). `fs` = the first scorer, any points. `fb` (first made FIELD GOAL) is kept for the model's
    features only. FanDuel also refunds a listed player who does not START (settled in nba_settle / nba_live).
  * The jump ball is ESPN's first period-1 "Jumpball" play: participants [jumper, jumper, gainer].
    The tip goes to the gainer's team.
  * A starter is ESPN's box-score `starter` flag. A man who did not play voids his leg.
  * "Early" shots are field-goal attempts in the first five minutes (clock 12:00 down to 7:00).

Reading ESPN from the runner goes through nfl_espn.getj (Node fetch -- urllib is 403'd there).
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, '..', 'nfl')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

ESPN = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/'
# ESPN abbreviation -> NBA tricode (the codes the state and the odds use)
TEAM = {'GS': 'GSW', 'NO': 'NOP', 'NY': 'NYK', 'SA': 'SAS', 'UTAH': 'UTA', 'WSH': 'WAS',
        'BRK': 'BKN', 'PHO': 'PHX', 'NOR': 'NOP', 'UTH': 'UTA', 'GOS': 'GSW'}


def tcode(a):
    a = str(a or '').upper().strip()
    return TEAM.get(a, a)


def getj(url):
    import nfl_espn
    return nfl_espn.getj(url)


def _secs(clock):
    m = re.match(r'(\d+):(\d+(?:\.\d+)?)', str(clock or ''))
    if m: return int(m.group(1)) * 60 + float(m.group(2))
    try: return float(clock)
    except Exception: return None


def _is_fg(p):
    t = str((p.get('type') or {}).get('text') or '')
    return bool(p.get('shootingPlay')) and 'free throw' not in t.lower() and (p.get('scoreValue') in (0, 2, 3) or p.get('scoreValue') is None)


def parse(summary):
    """-> dict with H, V (NBA tricodes), starters {team:[names]}, team_of {name:team}, played set,
    jumpers (home name, away name) or None, tip (team) or None, fb (name) or None, fbT,
    fga/fgm/efga {name:n}, tfirst {team:name}, final (bool), state ('pre'|'in'|'post')."""
    hdr = summary.get('header') or {}
    comp = (hdr.get('competitions') or [{}])[0]
    side, tid = {}, {}
    for c in comp.get('competitors') or []:
        t = c.get('team') or {}
        side[c.get('homeAway')] = tcode(t.get('abbreviation'))
        tid[str(t.get('id'))] = tcode(t.get('abbreviation'))
    st = ((comp.get('status') or {}).get('type') or {})
    H, V = side.get('home'), side.get('away')
    ath, team_of, starters, played = {}, {}, {H: [], V: []}, set()
    for tp in ((summary.get('boxscore') or {}).get('players') or []):
        T = tcode((tp.get('team') or {}).get('abbreviation'))
        tid.setdefault(str((tp.get('team') or {}).get('id')), T)
        for g in tp.get('statistics') or []:
            for a in g.get('athletes') or []:
                at = a.get('athlete') or {}
                nm = at.get('displayName')
                if not nm: continue
                ath[str(at.get('id'))] = nm
                team_of[nm] = T
                if a.get('starter'): starters.setdefault(T, []).append(nm)
                if not a.get('didNotPlay') and (a.get('stats') or []): played.add(nm)
    fga, fgm, efga, tfirst = {}, {}, {}, {}
    jumpers = tip = fb = fbT = fs = fsT = None
    for p in summary.get('plays') or []:
        per = ((p.get('period') or {}).get('number'))
        ty = str((p.get('type') or {}).get('text') or '')
        parts = [str(((x or {}).get('athlete') or {}).get('id')) for x in (p.get('participants') or [])]
        if per == 1 and jumpers is None and ty.lower().startswith('jump'):
            nms = [ath.get(i) for i in parts]
            if len(nms) >= 2 and nms[0] and nms[1]:
                a, b = nms[0], nms[1]
                if team_of.get(a) == V and team_of.get(b) == H: a, b = b, a
                if team_of.get(a) == H and team_of.get(b) == V: jumpers = (a, b)
            if len(nms) >= 3 and nms[2] and team_of.get(nms[2]) in (H, V):
                tip = team_of[nms[2]]
            elif tid.get(str((p.get('team') or {}).get('id'))) in (H, V):
                tip = tid[str((p.get('team') or {}).get('id'))]
            continue
        if fs is None and p.get('scoringPlay') and (p.get('scoreValue') or 0) >= 1 and parts and ath.get(parts[0]):
            fs = ath[parts[0]]; fsT = team_of.get(fs)          # FDRULES: first score of the game, free throws count
        if not _is_fg(p) or not parts: continue
        who = ath.get(parts[0])
        if not who: continue
        T = team_of.get(who)
        fga[who] = fga.get(who, 0) + 1
        made = bool(p.get('scoringPlay'))
        if made: fgm[who] = fgm.get(who, 0) + 1
        if per == 1:
            s = _secs((p.get('clock') or {}).get('displayValue'))
            if s is not None and s >= 420: efga[who] = efga.get(who, 0) + 1
        if T and T not in tfirst: tfirst[T] = who
        if made and fb is None: fb, fbT = who, T
    return dict(H=H, V=V, starters=starters, team_of=team_of, played=played, jumpers=jumpers, tip=tip,
                fb=fb, fbT=fbT, fs=fs, fsT=fsT, fga=fga, fgm=fgm, efga=efga, tfirst=tfirst,
                final=bool(st.get('completed')), state=st.get('state'),
                season_type=((hdr.get('season') or {}).get('type')))


def scoreboard(ymd):
    """-> list of (event id, AWAY, HOME, state, completed, season type, start iso)."""
    sb = getj(ESPN + 'scoreboard?dates=' + ymd.replace('-', ''))
    out = []
    for ev in sb.get('events') or []:
        comp = (ev.get('competitions') or [{}])[0]
        sd = {c.get('homeAway'): tcode((c.get('team') or {}).get('abbreviation')) for c in comp.get('competitors') or []}
        stt = ((comp.get('status') or ev.get('status') or {}).get('type') or {})
        out.append((str(ev.get('id')), sd.get('away'), sd.get('home'), stt.get('state'), bool(stt.get('completed')),
                    ((ev.get('season') or {}).get('type')), ev.get('date')))
    return out


def summary(eid):
    return getj(ESPN + 'summary?event=' + str(eid))
