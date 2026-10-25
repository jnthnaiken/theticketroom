#!/usr/bin/env python3
"""nba_payload.py -- FIRSTBASKET-2026-10-17. One slate of first-basket prices -> the basketball board (nba_D.json).

    python3 nba_payload.py slates/<date>/fb.psv nba_state.json nba_D.json --date D \
        --cache slates/<date>/picks.json [--season nba_season.json] [--build STAMP]

INPUT fb.psv is written in the browser by fb_scrape.js (BettingPros, "Player to Score the First Basket"):
    E|date|event|sched_utc|HOME|AWAY|status|home_lineup_type|away_lineup_type
    L|date|event|h/a|status|bp_id|name|pos|team
    S|date|event|bp_id|name|pos|team|open_cost|open_book|book:cost,book:cost,...   (book 10 = FanDuel, 0 = consensus)

STARTERS. BettingPros' lineup for the side (projected, then confirmed) when it lists five; otherwise the five
shortest first-basket prices on that team (flagged soft ⚠ on the board); otherwise the game is left off.

THE PICKS (nba_fb.pick). EV = blended chance x FanDuel decimal - 1. Every starter at EV >= +30%, one per
game, at most three; if none, the single best EV above zero. FanDuel is the price the rule was tested on --
a man FanDuel does not price is never picked.

STICKY (like soccer's tot_pick.json): the first build writes the picks to --cache and every rebuild reuses
them, so a placed bet never moves. One exception: a cached man whose game has not started and who is no
longer in his team's five is dropped and the slate is re-picked without him.
"""
import argparse, datetime, json, math, os, re, sys
import nba_voice as V
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nba_fb as F

ET = ZoneInfo('America/New_York')
TEAM_NAME = {
    'ATL': 'Hawks', 'BKN': 'Nets', 'BOS': 'Celtics', 'CHA': 'Hornets', 'CHI': 'Bulls', 'CLE': 'Cavaliers',
    'DAL': 'Mavericks', 'DEN': 'Nuggets', 'DET': 'Pistons', 'GSW': 'Warriors', 'HOU': 'Rockets', 'IND': 'Pacers',
    'LAC': 'Clippers', 'LAL': 'Lakers', 'MEM': 'Grizzlies', 'MIA': 'Heat', 'MIL': 'Bucks', 'MIN': 'Timberwolves',
    'NOP': 'Pelicans', 'NYK': 'Knicks', 'OKC': 'Thunder', 'ORL': 'Magic', 'PHI': '76ers', 'PHX': 'Suns',
    'POR': 'Trail Blazers', 'SAC': 'Kings', 'SAS': 'Spurs', 'TOR': 'Raptors', 'UTA': 'Jazz', 'WAS': 'Wizards'}
BP = {'NOR': 'NOP', 'PHO': 'PHX', 'UTH': 'UTA', 'BRK': 'BKN', 'GS': 'GSW', 'NO': 'NOP', 'NY': 'NYK', 'SA': 'SAS',
      'CHO': 'CHA', 'WSH': 'WAS', 'UTAH': 'UTA'}
FD, CONS = 10, 0
NAMES = ['Jump Ball', 'Center Circle', 'First Bucket', 'Win the Tip', 'Opening Tip', 'Bucket One', 'The Opener',
         'Tip Drill', 'First Points', 'Break the Seal', 'Open Floor', 'Tip-Off Call', 'Get on the Board',
         'First Look', 'Set Play', 'Out of the Huddle', 'Top of the Key', 'Off the Tip', 'Early Offense',
         'Ice Breaker', 'Lead the Break', 'First Touch', 'Two Points', 'The Starter', 'Opening Set']


def code(x): x = str(x or '').upper(); return BP.get(x, x)
def am_to_dec(o): return F.dec(o)
def dec_to_am(d): return F.american(d)


def et(sched_utc):
    t = datetime.datetime.strptime(sched_utc, '%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc)
    return t.astimezone(ET)


def hhmm(t):
    return t.strftime('%-I:%M %p') + ' ET'


def parse_books(s):
    d = {}
    for x in str(s or '').split(','):
        if ':' in x:
            k, c = x.split(':', 1)
            try:
                c = float(c); dd = am_to_dec(c)
                if 1.5 <= dd <= 41: d[int(k)] = c          # BettingPros parks suspended lines at +49000
            except Exception:
                pass
    return d


RWALIAS = {'NY': 'NYK', 'SA': 'SAS', 'GS': 'GSW', 'NO': 'NOP', 'PHO': 'PHX', 'UTAH': 'UTA', 'WSH': 'WAS', 'BKN': 'BKN'}
RW = {}
INJ = {}          # RWINJ-2026-10-24: (team, name key) -> RotoWire tag; Ques / Doubt / Out / GTD never anchor or leg
BLOCK_TAGS = ('ques', 'doubt', 'out', 'gtd', 'susp')


def _nk(n):
    import unicodedata
    n = ''.join(c for c in unicodedata.normalize('NFKD', str(n)) if not unicodedata.combining(c)).lower()
    n = re.sub(r'\b(jr|sr|ii|iii|iv)\b\.?', '', n)
    return re.sub(r'[^a-z ]', '', n).split()


def blocked(T, n):
    """RWINJ: RotoWire tags him questionable / doubtful / out / game-time -- he never anchors or legs a slip."""
    tag = INJ.get((T, ' '.join(_nk(n))))
    if tag is None:   # RotoWire abbreviates the MAY NOT PLAY list ("A. Diallo"): initial + surname, unique
        t = _nk(n)
        c = [v for (tt, kk), v in INJ.items() if tt == T and t and kk.split() and kk.split()[-1] == t[-1] and kk[0] == t[0][0]]
        tag = c[0] if len(c) == 1 else None
    return bool(tag) and str(tag).strip().lower().startswith(BLOCK_TAGS)


def rw_confirm(T, priced_names, want=('confirmed',)):
    """RWLINEUP: RotoWire's five for team T (CONFIRMED by default; RWEXPECTED-2026-10-24 also takes 'expected'),
    joined to that team's priced names; None unless all five join."""
    r = RW.get(T)
    if not r or r['status'] not in want or len(r['five']) != 5:
        return None
    keyed = {' '.join(_nk(n)): n for n in priced_names}
    out = []
    for n in r['five']:
        k = ' '.join(_nk(n))
        hit = keyed.get(k)
        if not hit:   # initial + surname, unique
            t = _nk(n)
            c = [v for kk, v in keyed.items() if t and kk.split() and kk.split()[-1] == t[-1] and kk[0] == t[0][0]]
            hit = c[0] if len(c) == 1 else None
        if not hit:
            print(f'  ::warning::RWLINEUP {T}: confirmed starter "{n}" has no first-basket price -- not confirming {T}')
            return None
        out.append(hit)
    return out


def read_slate(path, date):
    E, L, S = {}, {}, {}
    RW.clear(); INJ.clear()
    for line in open(path, encoding='utf-8'):
        r = line.rstrip('\n').split('|')
        if r and r[0] == 'R' and len(r) > 5 and r[1] == date:   # RWLINEUP-2026-10-20 (fb_fetch.js rotowire())
            T_ = code(RWALIAS.get(r[2], r[2]))
            RW.setdefault(T_, {'status': r[4], 'five': []})['five'].append(r[5])
            if len(r) > 6 and r[6]: INJ[(T_, ' '.join(_nk(r[5])))] = r[6]
            continue
        if r and r[0] == 'I' and len(r) > 4 and r[1] == date:      # RWINJ-2026-10-24: MAY NOT PLAY list
            INJ[(code(RWALIAS.get(r[2], r[2])), ' '.join(_nk(r[3])))] = r[4]
            continue
        if not r or r[0] not in ('E', 'L', 'S') or (len(r) > 1 and r[1] != date):
            continue
        if r[0] == 'E':
            E[r[2]] = dict(eid=r[2], sched=r[3], H=code(r[4]), V=code(r[5]), status=r[6],
                           lt=(r[7] if len(r) > 7 else ''), at=(r[8] if len(r) > 8 else ''))
        elif r[0] == 'L':
            L.setdefault(r[2], []).append(dict(side=r[3], status=r[4], bpid=r[5], name=r[6], pos=r[7] if len(r) > 7 else '',
                                               team=code(r[8]) if len(r) > 8 else ''))
        else:
            S.setdefault(r[2], {})[r[4]] = dict(bpid=r[3], name=r[4], pos=r[5], team=code(r[6]),
                                                open=r[7], books=parse_books(r[9] if len(r) > 9 else ''))
    return E, L, S


def starters_for(ev, lineup, st, sel=None):
    """The five a side: BettingPros' lineup when it lists five; else the five shortest first-basket prices
    on that team (the books list the starters and price them shortest); else nobody -- an old lineup from
    last week is a guess about tonight, and the board does not post guesses."""
    out, src = {}, {}
    for side, T in (('h', ev['H']), ('a', ev['V'])):
        # BettingPros statuses: 'started' / 'bench' / 'did_not_play' after the game; pre-game words vary, so
        # anything that reads like a starter counts and anything that reads like bench / out does not.
        five = [x['name'] for x in lineup if x['side'] == side and re.search(r'start|confirm|project|expect', x['status'], re.I)
                and not re.search(r'bench|did_not|dnp|out|inactive|injur|question|doubt', x['status'], re.I)]
        if len(five) == 5:
            out[T] = five; src[T] = ev['lt'] if side == 'h' else ev['at']
            continue
        priced = []
        for n, r in (sel or {}).items():
            if r.get('team') != T or not r.get('books'): continue
            b = r['books']; c = b.get(FD, b.get(CONS))
            if c is None: c = sorted(b.values())[len(b) // 2]
            priced.append((am_to_dec(c), n))
        if len(priced) >= 5:
            out[T] = [n for _, n in sorted(priced)[:5]]; src[T] = 'priced'
        else:
            out[T] = []; src[T] = 'none'
    return out, src


def pct(x, d=0): return None if x is None else round(100 * x, d)


# COLLINS-2026-10-19. Owner: "for the basketball write ups, use the voice of eric collins for the charlotte
# hornets". The register, not the man: relentless joy, stretched-out vowels, sing-song rhymes and made-up
# words, homespun comparisons, and drama dialled to eleven. ORIGINAL lines only -- none of his own trademark
# calls are quoted, same rule as the Madden and soccer booths. What does NOT change: every line still fires
# only when the model's number earns it (jumper, tip record, early-shot share, finishing, value), no digits
# after the opening sentence, and nothing promises the bucket.
def _fnv(key):
    h = 2166136261
    for ch in key:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def _pk(opts, key):
    return opts[_fnv(key) % len(opts)]


_MEM = {'card': V.Mem(), 'note': V.Mem()}   # COLLINS2-2026-10-25: reset per build() with the date and the recent boards


def _angle(jumper, ptip, p):
    fgp = (p['fgm'] / p['fga']) if p.get('fga') else None
    if jumper: return 'tipw' if ptip >= .56 else 'tip'
    if (p.get('ef') or 0) >= .24 or (p.get('tf') or 0) >= .26: return 'early'
    if fgp and fgp >= .54: return 'fin'
    return 'z'


def why(n, r, st, gm, salt=''):
    """One sentence for his card (COLLINS2: nba_voice.card, board memory). No percentages in the prose."""
    k = st.key(n, team=r['team']); p = st.P.get(k) or {}
    return V.card(n, _angle(r['jumper'], r['ptip'], p), n + '|' + str(salt), _MEM['card'])


BOARD_FROM = '2026-10-24'
FAV_FROM = '2026-10-24'
TEMPLE_FROM = '2026-10-24'   # TEMPLE-2026-10-24: Garrett's Temple, the four anchors round-robined      # FAVANCHOR-2026-10-24: favourite anchors lead the moons, no anchor singles   # BBDRAFT-2026-10-23: first slate drafted as anchors + moons
# TEMPLENAMES-2026-10-25. Owner: "garretts temple tickets should have their own names. garrett temple inspired".
# The section stays Garrett's Temple; the slip wears a date-rotated name, the way moons rotate.
# Owner, 10-25: "no the retire player garrett temple" -> "just make them about the journeyman aspect. consistent
# reliable role player. like how the picks are the safest reliable ones". The Temple is the chalk: the names say steady.
# "those ticket names arent clever enough either" / "no 10 day contract. should be positive": two jokes, both his -- the journeyman's suitcase, and the role
# player you can bank on (the Temple is the chalk, so the safe-money puns land).
# Owner: "reliable category is what im lookimg for" -- the role player you can count on, every name.
TEMPLE_NAMES = ['Set Your Watch By It', 'Old Faithful', 'Sure as Sunrise', 'Rain or Shine', 'Like Clockwork',
                'Tried and True', 'Built to Last', 'Duct Tape and WD-40', 'Swiss Army Knife', 'Bread and Butter',
                'Rock Solid', 'Iron Man', 'Mr. Dependable', 'Steady as She Goes', 'You Can Bank On It',
                'Never Misses a Shift', 'Always On Time', 'Every Single Night', 'Count On Me', 'Max Effort']
MOON_NAMES = ['Alley-Oop', 'Full Court', 'Fast Break', 'Coast to Coast', 'Pick and Roll', 'Backdoor Cut',
              'Splash Zone', 'Tomahawk', 'Euro Step', 'Skyhook', 'Lob City', 'Transition', 'Run and Gun',
              'Heat Check', 'Buzzer Beater', 'Showtime']


def _sur(n):
    """Surname for the write-ups, skipping a suffix: 'P.J. Washington Jr.' -> 'Washington' (was 'Jr.')."""
    w = [x for x in str(n).split() if x.rstrip('.').lower() not in ('jr', 'sr', 'ii', 'iii', 'iv')]
    return w[-1] if w else str(n)


def moon_note(names, salt, info=None, openers=None, temple=False):
    """COLLINS2-2026-10-25: an opener, one called play per leg from the angle the model earned (tip, early shots,
    finishing, sleeper), then a closing call -- every phrasing drawn through the board memory (nba_voice.Mem), so
    nothing repeats on the board or from the last few nights. `openers` is ignored (kept for old callers)."""
    mem = _MEM['note']
    surs = [_sur(n) for n in names]
    lines = []
    for n, sur in zip(names, surs):
        team, jumper, ptip, pp = info(n) if info else ('', False, .5, {})
        a = _angle(jumper, ptip, pp)
        lines.append(V.player_line(sur, team, {'tipw': 'tip', 'tip': 'tip', 'early': 'early', 'fin': 'fin'}.get(a, 'sneak'),
                                   salt + '|' + n, mem, strong_tip=(a == 'tipw')))
    return V.ticket_note(surs, lines, salt, mem, temple=temple)


def note(n, r, st, gm, salt):
    """The slip write-up: what the pick is, then why, in the Collins register. No digits after sentence one."""
    k = st.key(n, team=r['team']); p = st.P.get(k) or {}
    team = TEAM_NAME.get(r['team'], r['team'])
    sur = _sur(n)
    s = [f"{n} to score the first basket of {gm.replace('@', ' at ')}."]
    K = str(salt) + '|' + n
    if r['jumper']:
        s.append(_pk([f"{sur} goes up for the opening tip, and WHOOOA, the side that controls the tip usually strikes first!",
                      f"He's the big fella at center court for the {team}, and the tip is where first baskets are born, baby!",
                      f"{sur} takes the jump ball, and win the tip, take the first swing, that's how this game gets going!",
                      f"Center circle, bright lights, and {sur} in the middle of it all. The tip decides more of these than anything else!",
                      f"He's jumping center for the {team}, and you know what that means: first crack at the bucket!"], K + 'j'))
        if r['ptip'] >= .56:
            s.append(_pk(["And he's been winning these tips all season long. Look out below!",
                          "His history in the circle says he gets up there first. Oh my goodness!",
                          "He's been owning that jump ball, and that's a big, big deal!"], K + 'jt'))
    if (p.get('ef') or 0) >= .24 or (p.get('tf') or 0) >= .26:
        s.append(_pk([f"The {team} go to him early and often, and he is NOT shy about it!",
                      f"When the {team} run that first set, the ball has a funny way of finding {sur}!",
                      "He takes more early swings than a batting cage at sunrise!",
                      "The opening possessions are his playground, and he came to play!",
                      "Early in the game he's got the green light shining bright, and he floors it!"], K + 'e'))
    if len(s) == 1:   # neither the tip nor the early-shot angle fired: an opener that claims nothing new
        s.append(_pk([f"Here comes {sur}, and buddy, this one's got some sizzle!",
                      f"Don't sleep on {sur}. Ohhh, don't you dare sleep on {sur}!",
                      f"{sur} with the sneaky one, and sneaky is our favorite flavor!",
                      f"Grab the popcorn, because {sur} is a fun little ride tonight!"], K + 'o'))
    fgp = (p['fgm'] / p['fga']) if p.get('fga') else None
    if fgp and fgp >= .54:
        s.append(_pk(["And when he lets it fly, it goes in. Splash city!",
                      "He makes his shots, and making shots is the whole ballgame!",
                      "Buckets, buckets, buckets! The man finishes what he starts!",
                      "Soft touch, sweet stroke, and the net says thank you!"], K + 'f'))
    s.append(_pk(["The book has him priced like a bench guy. Pinch me, we'll take that all night long!",
                  "That price is longer than a summer afternoon, and we are HERE for it!",
                  "Everybody's lining up for the marquee names; we're taking the fella hiding in plain sight!",
                  "The market's snoozing on him. Wakey wakey, eggs and bakey!",
                  "Long price, big upside, and a whole lotta fun. Let's go!"], K + 'v'))
    return ' '.join(s)


def build(slate, state, date, cache=None, season=None, stamp='', now=None):
    _rec = V.recent_text(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'boards'), date)
    _MEM['card'], _MEM['note'] = V.Mem(date, _rec), V.Mem(date, _rec)
    st = F.State(json.load(open(state, encoding='utf-8')))
    params = st.params
    E, L, S = read_slate(slate, date)
    evs = sorted(E.values(), key=lambda e: (e['sched'], e['eid']))
    P, cands, meta_ko, games = {}, [], {}, {}
    for gi, ev in enumerate(evs, start=1):
        t0 = et(ev['sched'])
        gm = f"{ev['V']}@{ev['H']}"
        games[gi] = dict(ev, gm=gm, time=hhmm(t0), ko=t0.hour * 60 + t0.minute, ko_utc=t0.astimezone(datetime.timezone.utc).isoformat())
        meta_ko[str(gi)] = t0.hour * 60 + t0.minute
        starters, src = starters_for(ev, L.get(ev['eid'], []), st, S.get(ev['eid'], {}))
        for T in (ev['H'], ev['V']):
            priced_T = [n for n, r in (S.get(ev['eid'], {}) or {}).items() if r.get('team') == T]
            five = rw_confirm(T, priced_T)
            if five:
                if set(five) != set(starters.get(T) or []):
                    print(f'  RWLINEUP {T}: confirmed five differs from the priced guess -> {five}')
                starters[T] = five; src[T] = 'confirmed'
            elif src.get(T) in ('priced', 'none'):
                # RWEXPECTED-2026-10-24. Owner, on Alpha Diallo (DEN, questionable, not in anyone's five) anchoring:
                # "why on gods green earth is diallo on the board". With no BettingPros lineup the five was the five
                # shortest prices -- a bench man at +1100 squeezed in. RotoWire's EXPECTED five beats a price guess.
                five = rw_confirm(T, priced_T, want=('expected',))
                if five:
                    if set(five) != set(starters.get(T) or []):
                        print(f'  RWEXPECTED {T}: expected five replaces the priced guess -> {five}')
                    starters[T] = five; src[T] = 'expected'
        if len(starters.get(ev['H'], [])) != 5 or len(starters.get(ev['V'], [])) != 5:
            continue
        probs = F.game_probs(st, ev['H'], ev['V'], starters, params)
        sel = S.get(ev['eid'], {})
        mk = {}
        for n in probs:
            b = (sel.get(n) or {}).get('books') or {}
            c = b.get(CONS)
            if c is None and b:
                vals = sorted(am_to_dec(v) for kk, v in b.items() if kk != CONS)
                if vals: mk[n] = vals[len(vals) // 2]
            elif c is not None:
                mk[n] = am_to_dec(c)
        probs = F.blend(probs, mk, params)
        for n, r in probs.items():
            b = (sel.get(n) or {}).get('books') or {}
            fd = b.get(FD)
            ev_ = (r['pb'] * am_to_dec(fd) - 1) if fd is not None else None
            k = st.key(n, team=r['team']); sp = st.P.get(k) or {}
            fgp = (sp['fgm'] / sp['fga']) if sp.get('fga') else None
            T = r['team']; opp = ev['V'] if T == ev['H'] else ev['H']
            P[n] = dict(
                nm=n, code=T, team=TEAM_NAME.get(T, T), aT=100,
                khr=round(100 * r['pb'], 1), TOTAL=round(1000 * r['pb'], 1), baseTotal=round(1000 * r['pb'], 1),
                zonev=round(r['share'], 3), hh=pct(sp.get('ef')), la=pct(sp.get('tf')), pb=pct(r['ptip']),
                powidx=pct(r['pteam']), form=None, iso='—', iso_used=None, powraw=None, slot=None,
                bhand=(sel.get(n) or {}).get('pos') or ('C' if r['jumper'] else ''), hr9=None, phr9=None, wf=1.0,
                pull_tail=None, game=gi, gmatch=gm, gtime=games[gi]['time'], late=False, lunch=False, rain=False,
                out=False, void=False, status=('confirmed' if src.get(T) == 'confirmed' else 'projected'),
                opp=[TEAM_NAME.get(opp, opp), ''], oppERA=None, opp_code=opp, ftrend=None,
                odds=(int(round(fd)) if fd is not None else None), soft=(src.get(T) == 'priced'),
                why=why(n, r, st, gm, date), p_value=round(r['pb'], 4), p_model=round(r['p'], 4),
                p_mkt=(round(r['pm'], 4) if r.get('pm') is not None else None),
                odds_cons=(dec_to_am(mk[n]) if n in mk else None),
                ev=(round(ev_, 3) if ev_ is not None else None), jumper=r['jumper'], ptip=round(r['ptip'], 3),
                pteam=round(r['pteam'], 3), share=round(r['share'], 3), fgp=(round(fgp, 3) if fgp else None),
                ftd1=None, mkt_z=None, edge_z=None, blend=None, basis=src.get(T), basis_games=sp.get('nst'))
            if ev_ is not None and not blocked(T, n):
                cands.append(dict(game=gi, name=n, ev=ev_, odds=int(round(fd)), p=r['pb'], ko=games[gi]['ko']))
            elif blocked(T, n):
                print(f'  RWINJ: {n} ({T}) tagged {INJ.get((T, " ".join(_nk(n))))!r} -- not draftable')
    # ---- picks, sticky ----
    # ---- picks, sticky (PICKSTICKY-2026-10-17) ----
    # A posted pick never moves. Two exceptions, both before HIS game tips: he drops out of his team's five
    # (only he is replaced -- the other picks stand), or he was never priced. Once his game has started the
    # pick stands whatever the lineup says: the bet is placed, and a man who comes off the bench is still a
    # live (losing) bet while a man who never plays is refunded by the grader.
    now = datetime.datetime.now(datetime.timezone.utc) if now is None else now
    started = lambda x: bool(x.get('ko_utc')) and now >= datetime.datetime.fromisoformat(x['ko_utc'])
    picks, fresh, board, cached = None, False, None, None
    if cache and os.path.exists(cache):
        try:
            c = json.load(open(cache, encoding='utf-8'))
            if c.get('date') == date: cached = c
        except Exception:
            cached = None
    # BBDRAFT-2026-10-23: a slate first drafted under the old single-pick rule keeps it (a posted board never
    # changes shape mid-slate); every slate from BOARD_FROM drafts baseball's anchors + moons.
    legacy = (not (cached and cached.get('board') is not None)) and (bool(cached and cached.get('picks') is not None) or date < BOARD_FROM)
    if legacy:
        picks = cached.get('picks') if cached else None
        if picks is None:
            picks = [dict(x, picked_at=stamp) for x in F.pick(cands)]; fresh = True
        else:
            keep = [x for x in picks if x['name'] in P or started(x)]
            gone = [x for x in picks if x not in keep]
            if gone:
                print(f"  re-pick: {[x['name'] for x in gone]} no longer in a starting five")
                used = {x['game'] for x in keep}
                more = F.pick([c for c in cands if c['game'] not in used and c['name'] not in {g['name'] for g in gone}
                               and not started(dict(ko_utc=games[c['game']]['ko_utc']))], cap=F.MAX_PICKS - len(keep))
                if keep: more = [m for m in more if m['ev'] >= F.EV_MIN]     # the fallback single is for an empty slate only
                picks = keep + [dict(x, picked_at=stamp) for x in more]; fresh = True
    else:
        board = cached.get('board') if cached else None
        if board is None:
            board = F.draft_board(cands, fav=date >= FAV_FROM); fresh = True
            board = {'anchors': [dict(x, picked_at=stamp) for x in board['anchors']],
                     'moons': [[dict(x, picked_at=stamp) for x in m] for m in board['moons']]}
            print(f"  BBDRAFT: drafted {len(board['anchors'])} anchor(s) + {len(board['moons'])} moon(s)")
        else:
            # A posted leg never moves, except a man who drops out of his team's five before HIS game tips: he is
            # replaced by the strongest pool starter not already on the board, from a game the slip does not hold.
            pool = F.draft_pool(cands) or sorted(cands, key=lambda c: -F.value(c))
            def _st(x): g = games.get(x['game']) or {}; return started(dict(ko_utc=x.get('ko_utc') or g.get('ko_utc')))
            names = lambda: {x['name'] for x in board['anchors']} | {x['name'] for m in board['moons'] for x in m}
            def _next(avoid_games, fav=False):
                for c in (sorted(cands, key=lambda c: -c['p']) if fav else pool):   # FAVANCHOR: a favourite replaces a favourite
                    if c['name'] in names() or c['game'] in avoid_games: continue
                    if started(dict(ko_utc=(games.get(c['game']) or {}).get('ko_utc'))): continue
                    return dict(c, picked_at=stamp)
                return None
            # CONFLOCK-NBA-2026-10-24. Owner: "lock the basketball tickets from redrafting as soon as a leg is confirmed
            # green check starting. thats when people will start putting in the tickets. dont wait for tip off". A moon
            # latches the first time any of its legs is a confirmed starter (or its game has started) and never re-picks
            # again; the latch is stored in picks.json (board['locked']) so a later build cannot unlock it.
            _conf = lambda x: (P.get(x['name']) or {}).get('status') == 'confirmed'
            LOCK = set(board.get('locked') or [])
            for k_, m_ in enumerate(board['moons']):
                if any(_st(x) or _conf(x) for x in m_): LOCK.add(k_)
            for i, a in enumerate(list(board['anchors'])):
                dup = any(b['game'] == a['game'] for b in board['anchors'][:i])   # ANCHOR1G: a second anchor from one game
                if ((a['name'] in P and not blocked(P[a['name']]['code'], a['name'])) and not dup) or _st(a): continue
                mine = [m for m in board['moons'] if m and m[0]['name'] == a['name']]
                if any(_st(x) for m in mine for x in m[1:]) or any(k_ in LOCK for k_, m_ in enumerate(board['moons']) if m_ and m_[0]['name'] == a['name']):
                    continue                         # one of his slips is live or locked (CONFLOCK-NBA): it stands as placed
                avoid = {x['game'] for m in mine for x in m[1:]} | {b['game'] for k, b in enumerate(board['anchors']) if k != i}   # ANCHOR1G
                r = _next(avoid, fav=date >= FAV_FROM)
                if r:
                    print(f"  re-pick: anchor {a['name']} {'shares a game with another anchor' if dup else 'out of the five'} -> {r['name']}")
                    board['anchors'][i] = r
                    for m in mine: m[0] = r
                    fresh = True
            for k_, m in enumerate(board['moons']):
                if k_ in LOCK or any(_st(x) for x in m): continue  # locked (a confirmed leg) or a leg underway: it stands
                for j in range(1, len(m)):
                    if m[j]['name'] in P and not blocked(P[m[j]['name']]['code'], m[j]['name']): continue
                    r = _next({x['game'] for k, x in enumerate(m) if k != j})
                    if r:
                        print(f"  re-pick: moon leg {m[j]['name']} out of the five -> {r['name']}")
                        m[j] = r; fresh = True
        seen = set(); picks = []
        for x in board['anchors'] + [x for m in board['moons'] for x in m]:
            if x['name'] not in seen: seen.add(x['name']); picks.append(x)
    for x in picks:
        g = games.get(x['game']) or {}
        x.setdefault('ko_utc', g.get('ko_utc')); x.setdefault('gm', g.get('gm')); x.setdefault('gtime', g.get('time'))
        x.setdefault('code', (P.get(x['name']) or {}).get('code'))
    if board:
        for x in board['anchors'] + [x for m in board['moons'] for x in m]:
            g = games.get(x['game']) or {}
            x.setdefault('ko_utc', g.get('ko_utc')); x.setdefault('gm', g.get('gm')); x.setdefault('gtime', g.get('time'))
            x.setdefault('code', (P.get(x['name']) or {}).get('code'))
    MOONLOCK = set()
    if board:                                   # CONFLOCK-NBA: latch any moon with a confirmed / started leg (fresh drafts too)
        MOONLOCK = set(board.get('locked') or [])
        for k_, m_ in enumerate(board['moons']):
            if any((P.get(x['name']) or {}).get('status') == 'confirmed' or started(x) for x in m_): MOONLOCK.add(k_)
        if sorted(MOONLOCK) != list(board.get('locked') or []):
            board['locked'] = sorted(MOONLOCK); fresh = True
            print(f"  CONFLOCK-NBA: locked moons {board['locked']}")
    if cache and (fresh or not os.path.exists(cache)):
        os.makedirs(os.path.dirname(cache) or '.', exist_ok=True)
        out = {'date': date, 'picked_at': stamp}
        if board is not None: out['board'] = board
        else: out['picks'] = picks
        json.dump(out, open(cache, 'w', encoding='utf-8'), indent=1)
    # PRICEHOLD-2026-10-22. Owner, 7:25 PM: "why is the peyton watson price n/a now? and tbd". FanDuel pulls its
    # first-basket market at tip-off, so every build after 7:00 read Watson's FanDuel price as missing and posted
    # odds=None -- the card header said "n/a" and his chip "FB TBD" while the ticket held +1200. A price, once posted,
    # is kept for the slate (PRICEONCE, as in soccer and football): a man with no FanDuel price now carries the
    # last one this slate's archived board showed, and a pick falls back to the price it was picked at.
    _prior = {}
    if cache:
        _bp = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(cache)))), 'boards', f'{date}.json')
        try:
            _prior = (json.load(open(_bp, encoding='utf-8')).get('players') or {})
        except Exception:
            _prior = {}
    _held = []
    for n, p in P.items():
        if p.get('odds') is None:
            o = (_prior.get(n) or {}).get('odds')
            if o is None:
                o = next((x['odds'] for x in picks if x['name'] == n), None)
            if o is not None:
                p['odds'] = int(o); _held.append(n)
    if _held:
        print(f'  PRICEHOLD: FanDuel price gone (market closed at tip?) -- holding the posted price for {len(_held)}: '
              + ', '.join(_held[:8]))
    for x in picks:                      # a started pick who is not in tonight's five still renders and grades
        if x['name'] not in P and x.get('code'):
            T0 = x['code']
            P[x['name']] = dict(nm=x['name'], code=T0, team=TEAM_NAME.get(T0, T0), aT=100, khr=round(100 * x['p'], 1),
                                TOTAL=round(1000 * x['p'], 1), baseTotal=round(1000 * x['p'], 1), zonev=None, hh=None, la=None,
                                pb=None, powidx=None, form=None, iso='—', iso_used=None, powraw=None, slot=None, bhand='',
                                hr9=None, phr9=None, wf=1.0, pull_tail=None, game=x['game'], gmatch=x.get('gm'),
                                gtime=x.get('gtime'), late=False, lunch=False, rain=False, out=False, void=False,
                                status='projected', opp=['', ''], oppERA=None, opp_code='', ftrend=None, odds=int(x['odds']),
                                soft=True, why=f"{x['name']} was our pick before his team's five changed.", p_value=x['p'],
                                p_model=None, p_mkt=None, odds_cons=None, ev=round(x['ev'], 3), jumper=False, ptip=None,
                                pteam=None, share=None, fgp=None, ftd1=None, mkt_z=None, edge_z=None, blend=None,
                                basis='posted', basis_games=None)
    # ---- tickets ----
    doy = datetime.date.fromisoformat(date).timetuple().tm_yday
    T = []
    def _leg(n, o):
        p = P[n]
        return dict(name=n, team=p['team'], total=p['TOTAL'], aT=100, wf=1.0, gmatch=p['gmatch'], gtime=p['gtime'],
                    game=p['game'], late=False, odds=int(o), status=p['status'], ftd=True)
    singles = ([] if date >= FAV_FROM else board['anchors']) if board is not None else picks   # FAVANCHOR: anchors lead moons only
    for i, x in enumerate(singles):
        n = x['name']; p = P.get(n)
        if not p:
            continue
        o = int(x['odds'])
        T.append(dict(name=NAMES[(doy + i) % len(NAMES)], kind='fb', badge='⚡',
                      note=note(n, dict(team=p['code'], jumper=p['jumper'], ptip=p['ptip'] or .5), st, p['gmatch'], date),
                      players=[_leg(n, o)], nlegs=1, anchor=n, lock=re.sub(r'\s*ET\s*$', '', p['gtime']),
                      has_late=False, final=False, rr=None, wxsum={}, confleg=0, locked=False, priced=True,
                      parlay_am=o, payout10=round(10 * am_to_dec(o), 1), ftd=True, units=1,
                      ev=round(x['ev'], 3), p=round(x['p'], 4)))
    # CONFLOCK-NBA: a locked moon stays on the board even if a leg later leaves the five (owner: "if the other legs end
    # up voiding, its fine") -- the posted-pick stub above keeps him rendered; a man who never plays is voided by the
    # grader and the round robin settles on what is left (soccer_grade REDUCTION).
    for i, m in enumerate((board or {}).get('moons') or []):
        if not all(x['name'] in P for x in m):
            continue
        legs = [_leg(x['name'], x['odds']) for x in m]
        risk = round(F.RR_UNIT * F.rr_combos(len(legs)), 2)
        first = min(legs, key=lambda l: (games.get(l['game']) or {}).get('ko', 0))
        T.append(dict(name=MOON_NAMES[(doy + i) % len(MOON_NAMES)], kind='moon', badge='🚀',
                      note=moon_note([x['name'] for x in m], date + str(i), info=lambda n: (TEAM_NAME.get(P[n]['code'], P[n]['code']), bool(P[n]['jumper']), P[n]['ptip'] or .5, st.P.get(st.key(n, team=P[n]['code'])) or {})),
                      players=legs, nlegs=len(legs), anchor=m[0]['name'], lock=re.sub(r'\s*ET\s*$', '', first['gtime']),
                      has_late=False, final=False, wxsum={}, confleg=0, locked=(i in MOONLOCK), priced=True,
                      rr=dict(struct='by 2s, 3s & 4', risk=risk, maxprofit=round(F.rr_maxprofit([l['odds'] for l in legs]), 2),
                              bytwos=False),
                      parlay_am=None, payout10=None, ftd=True,
                      ev=round(sum(x['ev'] for x in m) / len(m), 3), p=None))
    # TEMPLE-2026-10-24. Owner: "i kind of want to do the anchors rr too" / "+ anything in this business is good" /
    # "the guy who put that ticket together tonight using the site was garrett. we should name the section after him"
    # -> "what about garrett's temple?". One ticket a night: the four favourite anchors (four different games), full
    # round robin 11 x 0.10u. Backtest 2021-26 under FanDuel rules: +172u on 747u (+23.0%), cashes 16.6% of nights,
    # max drawdown 72u; with the 8 moons the board goes +5,962u -> +6,134u. Its own ledger row (kind 'temple').
    if board is not None and date >= TEMPLE_FROM:
        A = [a for a in board['anchors'] if a['name'] in P]
        if len(A) == 4 and len({a['game'] for a in A}) == 4:
            legs = [_leg(a['name'], a['odds']) for a in A]
            first = min(legs, key=lambda l: (games.get(l['game']) or {}).get('ko', 0))
            tlock = any((P.get(a['name']) or {}).get('status') == 'confirmed' or started(a) for a in A) or bool(MOONLOCK)
            sa = [_sur(a['name']) for a in A]
            tnote = moon_note([a['name'] for a in A], date + 'temple',
                              info=lambda n: (TEAM_NAME.get(P[n]['code'], P[n]['code']), bool(P[n].get('jumper')), P[n].get('ptip') or .5,
                                              st.P.get(st.key(n, team=P[n]['code'])) or {}),
                              temple=True, openers=[f"Welcome to Garrett's Temple, baby! The four best bets on the board to score first: {sa[0]}, {sa[1]}, {sa[2]} and {sa[3]}!",
                                       f"Garrett lays the foundation and it's built out of chalk: {sa[0]}, {sa[1]}, {sa[2]} and {sa[3]}, the favourites in four different games!",
                                       f"Four pillars hold up the Temple tonight: {sa[0]}, {sa[1]}, {sa[2]} and {sa[3]}, the most likely first scorers on the slate!"])
            T.append(dict(name=TEMPLE_NAMES[doy % len(TEMPLE_NAMES)], kind='temple', badge='🏛️', note=tnote,
                          players=legs, nlegs=4, anchor=A[0]['name'], lock=re.sub(r'\s*ET\s*$', '', first['gtime']),
                          has_late=False, final=False, wxsum={}, confleg=0, locked=tlock, priced=True,
                          rr=dict(struct='by 2s, 3s & 4', risk=round(F.RR_UNIT * F.rr_combos(4), 2),
                                  maxprofit=round(F.rr_maxprofit([l['odds'] for l in legs]), 2), bytwos=False),
                          parlay_am=None, payout10=None, ftd=True,
                          ev=round(sum(a['ev'] for a in A) / 4, 3), p=None))
    sn = {}
    if season and os.path.exists(season):
        try: sn = json.load(open(season, encoding='utf-8'))
        except Exception: sn = {}
    return dict(players=P, pool=list(P.keys()), tickets=T,
                meta=dict(wx={str(k): dict(emoji='⚡', lean='Neutral', factor=1.0, park=v['gm'], cond='indoors', rain='', precip=0)
                              for k, v in games.items()}, build=stamp, face={}, maxAT=100, season=sn, date=date, gs={}, chalkever={},
                          chalkstate={}, chalk=[], cfg={'RR_UNIT': {'4': F.RR_UNIT}}, pool=len(P), gate=len(T), tickets=len(T), sport='nba',
                          ko=meta_ko, finals=[], games={str(k): v['gm'] for k, v in games.items()},
                          events={str(k): v['eid'] for k, v in games.items()}))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('slate'); ap.add_argument('state'); ap.add_argument('out')
    ap.add_argument('--date', required=True); ap.add_argument('--cache'); ap.add_argument('--season')
    ap.add_argument('--build', default='')
    A = ap.parse_args()
    D = build(A.slate, A.state, A.date, A.cache, A.season, A.build)
    json.dump(D, open(A.out, 'w', encoding='utf-8'), ensure_ascii=False, separators=(', ', ': '))
    print(f"{A.out}: {len(D['players'])} starters, {len(D['tickets'])} pick(s): "
          + '; '.join((f"{t['anchor']} {t['parlay_am']:+d} (ev {t['ev']:+.2f})" if not t.get('rr')
                       else f"{t['kind']} {'/'.join(_sur(l['name']) for l in t['players'])} {t['rr']['risk']}u")
                      for t in D['tickets']))
