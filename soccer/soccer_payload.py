#!/usr/bin/env python3
"""soccer_payload.py -- turn the mock scorer's output into the `D` object index.html expects.

READ SET (pCard / legRow / ticketCard / drawStats / avail / sortedNames):
    nm team opp[] game gmatch gtime late out void hr status odds TOTAL why form soft aT wf
  + soccer additions consumed by the forked seams:
    oppxga npxg90 xgshot minutes xgmatch sub{emoji,park,cond,rain,lean}

TWO CHIPS HAVE NO DATA and are written as None on purpose so they render "—":
  * oppxga   -- opponent xGA/90, needs understat teamsData
  * sub.park -- the successor's NAME, needs a squad-wide pull
"""
import json, io, sys, math, itertools, os, re, unicodedata

# The squad-roster club join reuses the team sheet's matcher rather than growing a second one.
# soccer_teamnews.py has no module-level side effects and imports nothing from here.
try:
    from soccer_teamnews import match_one as _match_one
except Exception:                                    # pragma: no cover
    def _match_one(name, squad):
        return None

# 2026-08-26 -- labels are the ESPN scoreboard displayName, so the card names the club the way
# the results feed will when it settles.
# FIXTURES-2026-08-27. MATCH_LABEL and ESPN_EVENT are data, not code -- see fixtures.json and
# PIPELINE.md open item 3. The literals below are the fallback for a slate directory that
# predates the file.
#
# SOCCERLIVE-2026-08-26. The live loop addresses matches by ESPN EVENT ID, never resolved at
# runtime by team name -- ESPN truncates display names ("Hapoel Be'er" for Hapoel Be'er Sheva)
# and fixture-name matching is the same class of bug as SPFIRST-2026-08-22.
MATCH_LABEL, ESPN_EVENT = {}, {}
if os.path.exists('fixtures.json'):
    _fx = json.load(io.open('fixtures.json', encoding='utf-8'))
    for _m, _d in _fx['matches'].items():
        MATCH_LABEL[_m] = (_d['home'], _d['away'])
        ESPN_EVENT[_m] = tuple(_d['espn'])
else:
    MATCH_LABEL = {
        'real-madrid-v-real-sociedad': ('Real Madrid', 'Real Sociedad'),
        'aek-athens-v-levski-sofia': ('AEK Athens', 'Levski Sofia'),
        'lyon-v-fenerbahce': ('Lyon', 'Fenerbahce'),
        'nk-celje-v-slovan-bratislava': ('NK Celje', 'Slovan Bratislava'),
        'viking-v-dinamo-zagreb': ('Viking FK', 'Dinamo Zagreb'),
    }
    ESPN_EVENT = {
        'real-madrid-v-real-sociedad': ('esp.1', '401882919'),
        'aek-athens-v-levski-sofia': ('uefa.champions_qual', '401909181'),
        'lyon-v-fenerbahce': ('uefa.champions_qual', '401909203'),
        'nk-celje-v-slovan-bratislava': ('uefa.champions_qual', '401909194'),
        'viking-v-dinamo-zagreb': ('uefa.champions_qual', '401909157'),
    }


def hook_read(avg_min, games):
    if not games or avg_min is None:
        return dict(emoji='🔄', park='—', cond='no minutes data', rain=None, lean='unknown')
    a = int(round(avg_min))
    if avg_min >= 82:
        return dict(emoji='🔄', park=f'{a}′', cond='usually finishes', rain=f'{games} apps', lean='plays 90')
    if avg_min >= 65:
        return dict(emoji='🔄', park=f'{a}′', cond='often hooked late', rain=f'{games} apps', lean='hooked')
    return dict(emoji='🔄', park=f'{a}′', cond='rotation risk', rain=f'{games} apps', lean='rotates')


def build(scored_path, tickets_path, xg_path, out_path, date,
          season_path=None, teamnews_path=None, squads_path=None):
    P = json.load(io.open(scored_path, encoding='utf-8'))
    T = json.load(io.open(tickets_path, encoding='utf-8'))
    TN = (json.load(io.open(teamnews_path, encoding='utf-8'))
          if teamnews_path and os.path.exists(teamnews_path) else {})
    XI, BENCH, ABSENT = TN.get('xi', {}), TN.get('bench', {}), TN.get('absent', {})
    TNGOALS, CLUB = TN.get('goals', {}), TN.get('club', {})
    # SQUADCLUB-2026-08-28. Owner, on Ferran Torres: *"who ferran torres plays for is just a -"*.
    #
    # The club label had exactly one source before team news lands: the club on the player's
    # UNDERSTAT row, which is the club he played for LAST SEASON. Torres's only row is
    # Barcelona 2025 and he is now at PSG, so `_side()` correctly refused to place him on
    # either side of Lille v PSG and the card showed "—". Refusing is right -- printing
    # "Barcelona" would assert a club he does not play for -- but "—" on the second-shortest
    # price of the night is not good enough, and it was 31 of 90 players board-wide, because
    # anyone with no understat row at all has no club either.
    #
    # ESPN's per-team ROSTER endpoint is a squad list, not a match document, so unlike the XI
    # it is available all day, days ahead. That is the missing source. Precedence, strongest
    # first: the published team sheet (this season, this fixture) > the squad roster (this
    # season) > the understat row (last season). Matching is soccer_teamnews.match_one -- the
    # same surname-anchored, tie-refusing join the team sheet uses, deliberately reused rather
    # than written twice.
    SQUADS = {}
    if squads_path and os.path.exists(squads_path):
        for line in io.open(squads_path, encoding='utf-8'):
            c = line.rstrip('\n').split('|')
            if len(c) >= 3 and c[0]:
                SQUADS.setdefault(c[0], []).append((c[2], c[1]))
        print(f'    squads: {sum(len(v) for v in SQUADS.values())} roster names '
              f'across {len(SQUADS)} matches')
    # WRONGCLUB-2026-08-30 -- see soccer_mock.py for the incident. squads.psv proves a priced
    # player is in NEITHER squad; OUTSQUAD-2026-08-29 already says that fact is recorded on
    # `out`, so it is recorded there and every consumer inherits it: buildPool drops him,
    # ticketIsLocked refuses to freeze him, and grading VOIDS his leg rather than losing it --
    # which is right, the bet was never placeable. Asserted only on surname_hits() == 0.
    WRONGCLUB = set()
    if SQUADS:
        from soccer_teamnews import surname_hits as _sur
        for _p in P:
            _sq = SQUADS.get(_p['match'])
            if _sq and _sur(_p['name'], _sq) == 0:
                WRONGCLUB.add(_p['name'])
        if WRONGCLUB:
            print(f'    wrong club: {len(WRONGCLUB)} priced in neither squad -> out: '
                  + ', '.join(sorted(WRONGCLUB)))

    LIVE = {m for m, st in (TN.get('status') or {}).items()
            if st.get('espn') not in ('STATUS_SCHEDULED', 'STATUS_FULL_TIME',
                                      'STATUS_POSTPONED', 'STATUS_CANCELED')}
    if TN:
        print(f'    team news: {len(XI)} confirmed XI, {len(BENCH)} benched, '
              f'{len(ABSENT)} out of squad; live: {sorted(LIVE) or "none"}')

    apps = {}
    for line in io.open(xg_path, encoding='utf-8'):
        c = line.rstrip('\n').split('|')
        if len(c) < 8:
            continue
        nm, g, mins = c[2], c[5], c[6]
        try:
            g, mins = int(g), int(mins)
        except ValueError:
            continue
        a = apps.setdefault(nm, [0, 0])
        a[0] += g
        a[1] += mins

    ko_of = lambda m: min(x['kickoff'] for x in P if x['match'] == m)
    # GNSORT-2026-08-26: sort by (kickoff, slug), NOT kickoff alone. Today all five matches
    # kick off at 19:00Z, so a tie-break on set-iteration order made `gn` -- and therefore
    # meta.finals, meta.espn and every p.game -- differ between builds of the same slate.
    matches = sorted({p['match'] for p in P}, key=lambda m: (ko_of(m), m))
    gnum = {m: i + 1 for i, m in enumerate(matches)}
    assert len(set(gnum.values())) == len(matches), 'gn collision'

    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo
    ET = ZoneInfo('America/New_York')
    slate = datetime.strptime(date, '%Y-%m-%d')

    def et_dt(mins):
        return (datetime(slate.year, slate.month, slate.day, tzinfo=timezone.utc)
                + timedelta(minutes=int(mins))).astimezone(ET)

    def gtime(mins):
        d = et_dt(mins)
        hh = d.hour % 12 or 12
        ap = 'AM' if d.hour < 12 else 'PM'
        return f'{hh}:{d.minute:02d} {ap}'

    def et_min(mins):
        d = et_dt(mins)
        off = (d.date() - slate.date()).days
        return d.hour * 60 + d.minute + off * 1440

    players = {}
    VOICE = Voice(P)
    avg_min = {}

    for p in P:
        n = p['name']
        home, away = MATCH_LABEL.get(p['match'], (p['match'], '?'))
        segs = [x.strip() for x in str(p.get('team') or '').split(',') if x.strip()]
        if CLUB.get(n):
            segs = [CLUB[n]] + segs
        elif SQUADS.get(p['match']):
            _hit = _match_one(n, SQUADS[p['match']])
            if _hit:
                segs = [_hit[1]] + segs

        # CLUBNORM-2026-08-28. The two sides of this comparison come from different feeds: `x`
        # is understat's team_title, `lab` is the ESPN scoreboard displayName baked into
        # fixtures.json. They disagree on punctuation -- understat writes "Paris Saint Germain",
        # ESPN writes "Paris Saint-Germain" -- and the raw substring test then fails, so Dembele
        # and Barcola came back with no club and no (H)/(A) on the first 2026-08-28 build.
        # Compare on a punctuation- and accent-free form. This only ever WIDENS the match, and
        # the label RETURNED is still `lab`, so the card still names the club ESPN's way.
        def _nrm(s):
            s = unicodedata.normalize('NFKD', s or '')
            s = ''.join(c for c in s if not unicodedata.combining(c))
            return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()

        def _side(x):
            xn = _nrm(x)
            if not xn:
                return None
            for lab in (home, away):
                ln = _nrm(lab)
                if xn == ln or xn in ln or ln in xn:
                    return lab
            return None
        t = next((_side(x) for x in segs if _side(x)), None)
        if t == home:
            opp, ha = away, '(H)'
        elif t == away:
            opp, ha = home, '(A)'
        else:
            t, opp, ha = None, f'{home} v {away}', ''
        g, mn = apps.get(n, (0, 0))
        avg = (mn / g) if g else None
        avg_min[n] = avg
        npx = p.get('npxg90')
        players[n] = {
            'nm': n,
            'league': p.get('league'),
            'team': t or '—',
            'code': (t[:3].upper() if t else '—'),
            'opp': [opp, ha],
            'game': gnum[p['match']],
            'gmatch': f'{home} v {away}',
            'gtime': gtime(ko_of(p['match'])),
            'late': et_min(ko_of(p['match'])) >= 17 * 60,
            'void': False,
            'unres': '',
            'hr': bool(TNGOALS.get(n)),
            'goalmins': TNGOALS.get(n, []),
            'status': ('confirmed' if n in XI else 'benched' if n in BENCH else 'projected'),
            'out': (n in ABSENT) or (n in WRONGCLUB),
            'soft': False, 'form': None,
            'aT': 100, 'wf': 1.0, 'khr': None, 'powidx': None, 'phr9': None, 'zonev': None,
            'odds': p.get('odds'),
            'TOTAL': round(p['TOTAL'], 1),
            'baseTotal': round(p['TOTAL'], 1),
            'blend': p.get('blend'),
            # STAGE2-2026-08-27: baked so the live re-draft applies the SAME pool gate the bake
            # did. soccer_draft.js can re-derive it from `blend` and gets the identical number
            # (same mean/sd over the same field), but a value that is computed twice is a value
            # that can drift once; this one is computed where it is defined.
            'gate_z': p.get('gate_z'),
            'mkt_z': p.get('mkt_z'), 'edge_z': p.get('edge_z'),
            'oppxga': None,
            'npxg90': npx,
            'xgshot': p.get('xgpershot'),
            'minutes': p.get('minutes'),
            'xgmatch': (round(npx * (avg or 90) / 90.0, 3) if npx else None),
            'sub': (dict(emoji='\U0001f504', park='BENCH', cond='named on the bench',
                         rain=(f'{avg:.0f}′ avg' if avg else None), lean='bench')
                    if n in BENCH else
                    dict(emoji='\U0001f504', park='XI',
                         cond=('usually finishes' if (avg or 0) >= 82 else
                               'often hooked late' if (avg or 0) >= 65 else
                               'rotation risk' if avg else 'in the starting XI'),
                         rain=(f'{avg:.0f}′ avg' if avg else 'no minutes data'),
                         lean='starts')
                    if n in XI else
                    dict(emoji='\U0001fa91', park='OUT', cond='not in the squad',
                         rain=None, lean='none')
                    if n in ABSENT else hook_read(avg, g)),
            'why': VOICE.why(p, avg),
        }

    # TITLEDUP-2026-08-29. shape_ticket() named a slip `pool[i % len(pool)]` off its GLOBAL
    # index, so two slips of the same kind whose indices are congruent mod the pool length get
    # the SAME title. builder's pool is 10 long, so builders at index 1 and 11 both came back
    # "The Poacher" -- seen the moment CONFLOCK-2026-08-29 reordered the card (builders landed
    # at 1/5/8/11 instead of 2/5/8/11). That is REDRAFT-2026-08-18's failure exactly: "the board
    # showed one ticket that had been two bets". Titles are how the owner refers to a slip, so
    # they have to be unique on a board. One shared `used` set, and each slip takes the first
    # free title from its own pool starting at the index it would have had.
    _used = set()
    T = [shape_ticket(t, players, i, VOICE, avg_min, _used) for i, t in enumerate(T)]

    GAME_CAP = 4
    gated = [x for x in sorted(P, key=lambda x: -x['TOTAL'])
             if x.get('gate_z', 0) >= 0.75 and (not XI or x['name'] in XI)]
    pool, _per = [], {}
    for x in gated:
        m = x['match']
        if _per.get(m, 0) >= GAME_CAP:
            continue
        pool.append(x['name'])
        _per[m] = _per.get(m, 0) + 1

    zero = {'graded': 0, 'won': 0, 'units': 0.0, 'staked': 0.0}
    prior = ({'since': date, 'history': [0], 'graded_nights': [],
              'cats': {k: dict(zero) for k in ('lunch', 'late', 'builder', 'moon', 'family')},
              'stake': 1})
    if season_path and os.path.exists(season_path):
        prior = json.load(io.open(season_path, encoding='utf-8'))
        for k in ('lunch', 'late', 'builder', 'moon', 'family'):
            prior.setdefault('cats', {}).setdefault(k, dict(zero))
        print(f'    ledger: carried {sum(c["graded"] for c in prior["cats"].values())} graded '
              f'from {len(prior.get("graded_nights", []))} night(s), '
              f'{sum(c["units"] for c in prior["cats"].values()):+.2f}u since {prior.get("since")}')
    else:
        print('    ledger: no prior season file -- board opens at 0-0')

    # 🚨 BUILDSTAMP-2026-09-04 -- A STAMP THAT NEVER MOVES IS NOT A STAMP.
    # This was `'build': f'{date} live'` -- the SAME string, "2026-09-04 live", on every build of
    # the slate, from the first pass to the last. That is what ADOPTSIG-2026-09-04 had to route
    # around: the live seam's adopt guard read `if(j.meta.build===D.meta.build) return;`, which was
    # true on every poll, so a tab never adopted anything after page load -- through every team
    # sheet, every demoted anchor, every replaced leg. ADOPTSIG fixed the seam by comparing the
    # BOARD instead, which is the half that had to be right; this fixes the stamp on its own terms,
    # because anything else reading it was equally blind. The page renders it (" · build <x>") and
    # the seam prints it on adopt ("board <x>") -- both were showing a constant.
    # UTC to match this workflow's own commit titles ("Soccer board 2026-09-04 (21:00Z)"), so a
    # board on screen can be tied to the commit that produced it by eye.
    # Nothing gates on this. soccer-build.yml's commit gate compares the ticket set and per-player
    # (odds, status, out, hr) and never looks at meta.build, so a moving stamp cannot cause a
    # spurious publish -- verified before shipping. Do not reintroduce a constant here.
    from datetime import datetime as _dtnow, timezone as _tzutc
    _build_stamp = f"{date} {_dtnow.now(_tzutc.utc):%H:%M}Z"

    D = {
        'players': players,
        'tickets': T,
        'pool': pool,
        'familyFloor': min([p['TOTAL'] for p in P], default=0),
        'meta': {
            'wx': {},
            'gs': {str(gnum[m]): 'live' for m in LIVE if m in gnum},
            'finals': [],
            'results': {},
            'unresolved': [],
            'espn': {str(gnum[m]): {'lg': ESPN_EVENT[m][0], 'ev': ESPN_EVENT[m][1]}
                     for m in matches if m in ESPN_EVENT},
            # STAGE2-2026-08-27. Kickoffs, UTC minutes past midnight, keyed by game number.
            # The live re-draft needs a real clock per match and must not get it by parsing
            # `gtime` back out of "3:00 PM": that string is ET, carries no date, and the round
            # trip breaks across DST. CONFLOCK ("has the earliest leg kicked off?") and
            # MINTGUARD ("is this slip being minted after its own kickoff?") are both
            # comparisons against this number. Purely additive -- nothing else reads it.
            'ko': {str(gnum[m]): int(ko_of(m)) for m in matches},
            'build': _build_stamp,
            'face': 'soccer',
            'maxAT': 100,
            'date': date,
            'pool': len(P),
            'gate': len(gated),
            'tickets': len(T),
            'season': {'since': prior.get('since', date),
                       'history': prior.get('history', [0]),
                       'graded_nights': prior.get('graded_nights', []),
                       'stake': prior.get('stake', 1),
                       'cats': prior['cats']},
        },
    }
    json.dump(D, io.open(out_path, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'ok  {out_path}  {len(players)} players / {len(T)} tickets / pool {len(pool)}')
    miss = sum(1 for p in players.values() if p['npxg90'] is None)
    print(f'    xG join: {len(players)-miss}/{len(players)} matched '
          f'({100*(len(players)-miss)/len(players):.0f}%)')
    print(f'    espn map: {len(D["meta"]["espn"])} matches addressable by event id')


NAMES = {
    'moon':    ['Top Corner', 'From Distance', 'Upper Ninety', 'Postage Stamp', 'Off the Underside',
                'Outside the Box', 'Dipping Effort', 'Curled Home', 'Half Volley', 'Thirty Yards',
                'Into the Roof', 'No Backlift'],
    'builder': ['Target Man', 'The Poacher', 'Six-Yard Box', 'Back Post', 'Near Post', 'The Nine',
                'First Time', 'Gets Across', 'Runs the Channel', 'Shoulder of the Last Man'],
    'family':  ['Off the Bench', 'Fresh Legs', 'Late Doors', 'Stoppage Time', 'Ninety Plus'],
    'lunch':   ['Early Doors', 'Lunchtime Kickoff', 'The Twelve Thirty', 'First Match On'],
    'late':    ['Under Lights', 'Last One On', 'The Late Kickoff', 'Sunday Night'],
}
BADGE = {'moon': '💥', 'builder': '⚓️', 'family': '💥', 'lunch': '🍱', 'late': '🌃'}


def _dec(am):
    return 1 + am / 100.0 if am > 0 else 1 + 100.0 / abs(am)


def _r1(x):
    return math.floor(x * 10 + 0.5) / 10


def rr_maxprofit(legs, risk):
    # RRSTAKE-2026-08-28. `risk` is the TOTAL across the round robin (2u on a moon = four bets at
    # 0.5u), so divide by the combination count instead of pricing 1u on each. See index.html's
    # rrmax(); this was overstating every printed max profit by about 2x.
    dec = [_dec(l['odds']) for l in legs if l.get('odds')]
    L = len(dec)
    s = 0.0
    n = 0
    for a in range(L):
        for b in range(a + 1, L):
            s += dec[a] * dec[b]; n += 1
    for a in range(L):
        for b in range(a + 1, L):
            for c in range(b + 1, L):
                s += dec[a] * dec[b] * dec[c]; n += 1
    if L >= 4:
        for a, b, c, d in itertools.combinations(range(L), 4):
            s += dec[a] * dec[b] * dec[c] * dec[d]; n += 1
    return _r1((risk / n) * s - risk) if n else 0.0


def _rr_block(legs, risk):
    return {'struct': 'by 2s & 3', 'risk': risk,
            'maxprofit': rr_maxprofit(legs, risk), 'bytwos': False}


def shape_ticket(t, players, i, voice, apps, used=None):
    kind = t['kind']
    legs = t.get('legs') or t.get('players') or []
    out_legs = []
    for l in legs:
        src = players.get(l['name'], {})
        out_legs.append({
            'name': l['name'],
            'team': src.get('team', '—'),
            'total': src.get('TOTAL', l.get('TOTAL', 0)),
            'aT': 100, 'wf': 1.0,
            'gmatch': src.get('gmatch', ''),
            'gtime': src.get('gtime', ''),
            'game': src.get('game', 0),
            'late': False,
            'odds': l.get('odds'),
            'status': src.get('status', 'projected'),
        })
    out_legs.sort(key=lambda l: -(l['total'] or 0))
    pool = NAMES.get(kind, NAMES['family'])
    if used is None:
        used = set()
    # NAMECARRY-2026-08-29: USE THE TITLE THE DRAFT ASSIGNED, when there is one.
    # soccer_draft.js owns naming (REDRAFT-2026-08-18): a surviving slip keeps its title, a
    # repaired slip keeps it through `priorName`, and a dead slip's name is spent for the night.
    # This function used to ignore all of that and derive the title from `i`, the ticket's array
    # INDEX -- so any reordering of the board (a demotion, a reseat, a new anchor) silently
    # reassigned titles between live bets. Carried names still go through `used`, so TITLEDUP's
    # guarantee (unique per board) is unchanged; a carried name that would collide falls through
    # to the pool walk below rather than shipping a duplicate.
    tname = t.get('name')
    if tname and tname in used:
        tname = None
    if tname is None:
        for k in range(len(pool)):                  # start where the index says, then walk
            cand = pool[(i + k) % len(pool)]
            if cand not in used:
                tname = cand
                break
    if tname is None:                               # pool exhausted -- never silently collide
        tname = '%s %d' % (pool[i % len(pool)], i + 1)
    used.add(tname)
    anchor = out_legs[0]['name'] if out_legs else None
    return {
        'name': tname,
        'kind': kind,
        'badge': BADGE.get(kind, '🎟'),
        'note': voice.ticket_note(out_legs, players, apps, tname),
        'players': out_legs,
        'nlegs': len(out_legs),
        'anchor': anchor,
        'lock': min((l['gtime'] for l in out_legs if l['gtime']), default=''),
        'has_late': False,
        'final': False,
        # LOCKCARRY-2026-08-30 -- was hardcoded False, which threw the CONFLOCK latch away
        # on every single build. See soccer_rebuild_cli.js for the incident. A fresh draft
        # has no locks and legitimately sends nothing, so the default stays False.
        'locked': bool(t.get('locked')),
        'rr': (_rr_block(out_legs, t.get('risk', 2.0)) if len(out_legs) >= 3 else None),
        'wxsum': {'boost': 0, 'supp': 0, 'dome': 0, 'neu': 0},
        'confleg': sum(1 for l in out_legs if players.get(l['name'], {}).get('status') == 'confirmed'),
        'unres': sum(1 for l in out_legs if (players.get(l['name'], {}).get('unres'))),
        'priced': sum(1 for l in out_legs if l['odds']),
    }


def _h(key):
    """FNV-1a. Any stable hash would do; the point is that it is STABLE. A note that
    reshuffles itself between builds is a diff nobody can review, and this board rebuilds
    every fifteen minutes."""
    h = 2166136261
    for ch in key:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def _pick(options, key):
    """Deterministic variety: same key -> same phrasing on every build."""
    return options[_h(key) % len(options)]


def _rot(seq, key, pin_last=('price',)):
    """Deterministic rotation of an angle list, with the weak angles pinned to the back.

    VOICE-2026-08-28. This is the fix for the real complaint. `angles()` returns candidates in
    a FIXED priority order -- rate, quality, volume, finish, minutes, price -- and the caller
    took the first unused one, so the highest-xG man on every slip led with "runs 0.xx xG a 90"
    and the board read like a mail merge. Rotating by the SLIP as well as the player means the
    same striker leads on his shot quality on one ticket and his minutes on the next, without
    any clause ever ceasing to be true of him.
    """
    # VOICE-2026-08-28b: rotating the WHOLE list let 'price' come out first, and "Kane -200"
    # is not a reason to back anybody -- it is the fact the reader can already see in the odds
    # column two inches to the right. Hold it (and anything else named in pin_last) at the
    # back so it stays a filler clause, and rotate only the angles that say something about
    # the player.
    head = [x for x in seq if x[0] not in pin_last]
    tail = [x for x in seq if x[0] in pin_last]
    if not head:
        return list(tail)
    n = _h(key) % len(head)
    return head[n:] + head[:n] + tail


# --------------------------------------------------------------------------------------
# VOICE-2026-08-28. Owner: *"ticket descriptions need way more creativity. reference the
# scottish announcer with colorful language for inspiration. need variety. no one wants to
# read the same bland bullshit on every ticket."*
#
# So: the register of Scottish football commentary -- idiomatic, physical, unimpressed by its
# own cleverness. Not an impersonation of any real commentator, and no invented quotes.
#
# THE HARD RULE IS UNCHANGED AND MATTERS MORE NOW: every clause is a restatement of a number
# that is actually in the payload. Colour is allowed in HOW a fact is said, never in WHAT is
# claimed. "He lives in there, 0.69 xG a 90" is the same fact as "runs 0.69 xG a 90"; "he'll
# score tonight" is not a fact at all and must never appear. Comparative claims are out too --
# `_hi()` only means "at or above this slate's 60th percentile", which is not "the best on the
# card", so nothing in these banks says that.
#
# Three sources of variety, in order of how much they actually help:
#   1. THE LEAD ANGLE ROTATES PER SLIP (_rot). Biggest win by far: the same player opens on a
#      different true fact on a different ticket.
#   2. Eight to eleven phrasings per angle instead of two or three.
#   3. The SENTENCE FRAME varies -- comma list, two short sentences, a colon after a short
#      opener -- so even two notes built from the same angles do not scan alike.
# --------------------------------------------------------------------------------------

OPENERS_3 = ['Three that can all find it', 'Three names, one afternoon', 'If all three turn up',
             'Everything has to land', 'The lot has to come off', 'Three to hear the net rustle',
             'All three or nothing', 'Three goals, three grounds', 'Nothing here is a formality',
             'Hold your nerve', 'Three that fancy it']
OPENERS_1 = ['One name', 'Straight up', 'Nothing fancy', 'The plain one', 'No frills',
             'Just the one', 'Keep it simple']

FRAMES_3 = ['{a}, {b}, and {c}.', '{o}: {a}, {b}, {c}.', '{a}. {b}, and {c}.',
            '{o} — {a}, {b}, and {c}.', '{a} and {b}. {c}.', '{a}; {b}; {c}.']
FRAMES_2 = ['{a} and {b}.', '{o}: {a}, {b}.', '{a}, and {b}.', '{o} \u2014 {a}, and {b}.']


class Voice:
    """Writes the prose. Holds the slate's own distribution so 'high' means high TONIGHT.

    A fixed threshold would call 0.30 xG90 good in June and good in a Champions League
    qualifier, which is how you end up describing every player as dangerous.

    Two registers. A CARD has room for a full sentence; a TICKET note is clamped to two lines
    by `.tnote` and carries three legs, so it gets the same fact in a shorter form. Same angle
    selection, same numbers, different length -- not a different claim.
    """

    def __init__(self, P):
        self.q = {}
        for k in ('npxg90', 'xgpershot', 'shots90'):
            v = sorted(x[k] for x in P if x.get(k) is not None)
            self.q[k] = (v[int(len(v) * 0.60)] if len(v) >= 3 else None)

    def _hi(self, k, v):
        return v is not None and self.q.get(k) is not None and v >= self.q[k]

    def angles(self, p, avg, who, salt='', lead=False):
        """[(key, brief, full)] for one player, best-first. `who` is how to name him.

        Every entry restates a number that is on the payload. Nothing here predicts anything.
        """
        out = []
        npx, xps, sh = p.get('npxg90'), p.get('xgpershot'), p.get('shots90')
        fin, odds = p.get('finish90'), p.get('odds')
        comp = ('the Champions League playoff round' if p.get('league') == 'UCL_PO'
                else 'his league')
        k = who + salt

        # VOICE-2026-08-28c. Some phrasings put the player in the OBJECT ("the manager leaves
        # Kane on", "+150 for Pulisic", "there is a goal in Kane most weeks"). Those are fine
        # mid-sentence, but if one LEADS, every later clause -- which `_depersonalise` has
        # reduced to a bare verb phrase -- attaches itself to the wrong subject: "The manager
        # leaves Harry Kane on ... and is not one for hitting them from forty yards" says it of
        # the manager. So when this call is producing the opening clause, choose only from the
        # forms where the player is the subject, and fall back to the whole bank if a given
        # angle has none.
        def say(opts, kk):
            if lead:
                subj = [o for o in opts if o.startswith(who + ' ')]
                if subj:
                    return _pick(subj, kk)
            return _pick(opts, kk)

        if npx is None:
            out.append(('noxg',
                        say([f'{who} has no xG behind him',
                               f'{who} rides the price alone',
                               f'nothing on {who} but the price',
                               f'{who} is unmodelled',
                               f'no numbers on {who} at all',
                               f'{who} on trust'], k + 'n'),
                        say([f'{who} has no top-five xG history behind him, so that price is the whole argument',
                               f"{who} sits outside Understat's five leagues — {comp} is not covered — so the market is carrying him",
                               f'there is no model on {who} at all; the price is doing the talking',
                               f'{who} is unscored on the edge half and rides the market alone',
                               f'{who} arrives with no xG whatsoever, so the price is doing the talking',
                               f'{who} has nothing behind him but the number beside his name',
                               f'{who} is a blank on the model half, which leaves the market to argue for him'], k + 'N')))
            if odds:
                out.append(('price',
                            say([f'{who} at {odds:+d}', f'{odds:+d} for {who}',
                                   f'{who} is {odds:+d}'], k + 'p'),
                            say([f'{who} is priced {odds:+d}',
                                   f'the book has {who} at {odds:+d}'], k + 'P')))
            return out

        if self._hi('npxg90', npx):
            out.append(('rate',
                        say([f'{who} at {npx:.2f} xG a 90',
                               f'{who} lives in there — {npx:.2f} a 90',
                               f'{who} carries {npx:.2f} a 90',
                               f'{who} has a goal in him, {npx:.2f} a 90',
                               f'{who} keeps turning up: {npx:.2f} a 90',
                               f'{who} is a menace at {npx:.2f} a 90',
                               f'{npx:.2f} xG a 90 for {who}',
                               f'{who} in the right postcode, {npx:.2f} a 90'], k + 'r'),
                        say([f'{who} is generating {npx:.2f} non-penalty xG every ninety he plays',
                               f'{who} spends his afternoons where the ball drops — {npx:.2f} non-penalty xG a 90',
                               f'{who} does not need many invitations: {npx:.2f} non-penalty xG a 90',
                               f'{who} is worth {npx:.2f} xG a 90 before anyone kicks a ball',
                               f'there is a goal in {who} most weeks, {npx:.2f} non-penalty xG a 90',
                               f'{who} runs {npx:.2f} non-penalty xG a 90'], k + 'R')))
        if self._hi('xgpershot', xps):
            out.append(('quality',
                        say([f'{who} {xps:.2f} xG a shot',
                               f'{who} picks his moment, {xps:.2f} a shot',
                               f'{who} does not waste them — {xps:.2f} a shot',
                               f'{who} is fussy: {xps:.2f} a shot',
                               f'{who} shoots from the good places ({xps:.2f})',
                               f'{xps:.2f} xG a shot for {who}'], k + 'q'),
                        say([f'{who} shoots from where it counts — {xps:.2f} xG a shot',
                               f'{who} is not one for hitting them from forty yards: {xps:.2f} xG a shot',
                               f'{who} gets himself into the right positions, {xps:.2f} xG a shot',
                               f'every attempt {who} takes is worth {xps:.2f} xG'], k + 'Q')))
        if self._hi('shots90', sh):
            out.append(('volume',
                        say([f'{who} {sh:.1f} shots a 90',
                               f'{who} will have a go — {sh:.1f} a 90',
                               f'{who} lets fly {sh:.1f} times a 90',
                               f'{who} rattles off {sh:.1f} a 90',
                               f'{who} does not need asking twice, {sh:.1f} a 90'], k + 'v'),
                        say([f'{who} gets {sh:.1f} attempts away every ninety',
                               f'{who} is never shy — {sh:.1f} shots a 90',
                               f'{who} will pull the trigger {sh:.1f} times a game'], k + 'V')))
        if fin is not None and fin >= 0.05:
            out.append(('finish',
                        say([f'{who} +{fin:.2f} on his xG',
                               f'{who} is beating the numbers, +{fin:.2f}',
                               f'{who} has been burying them, +{fin:.2f} a 90',
                               f'{who} ahead of his xG by {fin:.2f}'], k + 'f'),
                        say([f'{who} has been finishing better than the chances deserve, +{fin:.2f} a 90 on his xG',
                               f'{who} is {fin:.2f} a 90 to the good on his xG',
                               f'the ones that fall to {who} have been going in — +{fin:.2f} a 90 over his xG'], k + 'F')))
        elif fin is not None and fin <= -0.08:
            out.append(('finish',
                        say([f'{who} {fin:.2f} under his xG',
                               f'{who} has been wasteful, {fin:.2f} a 90',
                               f'{who} owed goals — {abs(fin):.2f} a 90 short',
                               f'{who} {abs(fin):.2f} a 90 light on his xG'], k + 'f'),
                        say([f'{who} is {abs(fin):.2f} a 90 short of his xG, which is a case for him only if you think that turns',
                               f'the chances have been falling to {who} and not going in — {abs(fin):.2f} a 90 under his xG'], k + 'F')))
        if avg:
            if avg >= 75:
                out.append(('mins',
                            say([f'{who} plays the ninety',
                                   f'{who} never comes off',
                                   f'{who} is on for the lot',
                                   f'{who} sees out the ninety',
                                   f'{who} does not get hooked',
                                   f'{who} is there at the death'], k + 'm'),
                            say([f'{who} plays the full ninety, {avg:.0f} minutes an appearance',
                                   f'{who} is on the pitch {avg:.0f} minutes a game, so he will be there at the death',
                                   f'the manager leaves {who} on — {avg:.0f} minutes an appearance',
                                   f'{who} does not come off — {avg:.0f} minutes an appearance',
                                   f'{who} sees out the ninety more often than not, {avg:.0f} minutes a game',
                                   f'{who} is still on the pitch when it matters, {avg:.0f} minutes an appearance'], k + 'M')))
            else:
                out.append(('mins',
                            say([f'{who} a {avg:.0f}-minute man',
                                   f'{who} usually gets the hook ({avg:.0f}′)',
                                   f'{who} wants it early — {avg:.0f}′ a game',
                                   f'{who} off around {avg:.0f}′'], k + 'm'),
                            say([f'{who} averages {avg:.0f} minutes an appearance, so he wants it before the hour',
                                   f'{who} tends to come off around the {avg:.0f}-minute mark',
                                   f'{who} averages only {avg:.0f} minutes an appearance',
                                   f'{who} gets the hook about the {avg:.0f}-minute mark, so he needs it early',
                                   f'{who} is rarely there at the end — {avg:.0f} minutes an appearance'], k + 'M')))
        if not out:
            out.append(('rate', f'{who} at {npx:.2f} xG a 90',
                        f'{who} runs {npx:.2f} non-penalty xG a 90'))
        if odds:
            out.append(('price',
                        say([f'{who} at {odds:+d}', f'{odds:+d} for {who}',
                               f'{who} is {odds:+d}'], k + 'p'),
                        say([f'{who} is priced {odds:+d}',
                               f'the book has {who} at {odds:+d}'], k + 'P')))
        return out

    def ticket_note(self, legs, players, apps, tname=''):
        """One sentence naming what each leg is FOR, in slip order, no angle used twice."""
        # a three-leg slip gets one clause per leg or the note overruns the two-line clamp;
        # a single (anchor / screamer) has the room for two and reads thin with one.
        per = 1 if len(legs) >= 3 else 2
        used, bits = set(), []
        for l in legs:
            p = players.get(l['name'])
            if not p:
                continue
            sur = _surname(l['name'])
            # Two passes over the SAME angle list: identical keys in identical order (the
            # rotation depends only on the keys), so index-free key lookup is safe.
            lead_of = {a[0]: a for a in self.angles(p, apps.get(l['name']), sur,
                                                    salt=tname, lead=True)}
            cands = _rot(self.angles(p, apps.get(l['name']), sur, salt=tname), tname + sur)
            took = 0
            for key, brief, full in cands:
                if key in used:
                    continue
                used.add(key)
                # A THREE-leg slip is three clauses inside a two-line clamp, so it gets the
                # short forms. A single carries one player and has room for the long ones, and
                # read like a telegram without them: "Haaland -105 - 0.69 xG a 90 for him."
                if took == 0:
                    _k, brief, full = lead_of.get(key, (key, brief, full))
                    bits.append(brief if per == 1 else full)
                else:
                    bits.append(_depersonalise(brief if per == 1 else full, sur))
                took += 1
                if took == per:
                    break
            if not took and cands:
                bits.append(cands[0][1] if per == 1 else cands[0][2])
        if not bits:
            return ''
        if len(bits) >= 3:
            body = _pick(FRAMES_3, tname + 'f3').format(
                a=bits[0], b=bits[1], c=', '.join(bits[2:]), o=_pick(OPENERS_3, tname + 'o3'))
        elif len(bits) == 2:
            body = _pick(FRAMES_2, tname + 'f2').format(
                a=bits[0], b=bits[1], o=_pick(OPENERS_1, tname + 'o1'))
        else:
            body = bits[0] + '.'
        body = re.sub(r'(?<=\. )([a-z])', lambda m: m.group(1).upper(), body)
        return body[0].upper() + body[1:]

    def why(self, p, avg):
        """Two or three clauses on one card, full name first, then the name drops away."""
        n = p['name']
        keep, used = [], set()
        lead_of = {a[0]: a for a in self.angles(p, avg, n, lead=True)}
        for key, _brief, full in _rot(self.angles(p, avg, n), n + 'card'):
            if key in used:
                continue
            used.add(key)
            keep.append(_depersonalise(full, n) if keep else lead_of.get(key, (0, 0, full))[2])
            if len(keep) == 3:
                break
        return _sentence(keep)


def _sentence(bits):
    bits = [b for b in bits if b]
    if not bits:
        return ''
    if len(bits) == 1:
        body = bits[0]
    elif len(bits) == 2:
        body = bits[0] + ' and ' + bits[1]
    else:
        body = ', '.join(bits[:-1]) + ', and ' + bits[-1]
    return body[0].upper() + body[1:] + '.'


def _surname(name):
    parts = [w for w in (name or '').split() if w]
    return parts[-1] if parts else (name or '')


def _depersonalise(clause, name):
    """Second and third clauses drop the name: 'Duro shoots 3.1 times' -> 'shoots 3.1 times'.

    VOICE-2026-08-28: the phrase banks now include forms where the name is an OBJECT rather
    than the subject ('nothing on Duro but the price', '+180 for Duro'). Stripping a LEADING
    name no longer covers those, and leaving them alone printed the surname twice in one
    sentence. A non-leading occurrence becomes 'him', which is grammatical in every bank entry
    precisely because the name is only ever an object there.
    """
    if clause.startswith(name + ' '):
        return clause[len(name) + 1:]
    if name in clause:
        return clause.replace(name, 'him', 1)
    return clause


if __name__ == '__main__':
    raw, argv, sp, tn, sq = sys.argv[1:], [], None, None, None
    i = 0
    while i < len(raw):
        if raw[i] in ('--season', '--teamnews', '--squads'):
            if raw[i] == '--season':
                sp = raw[i + 1]
            elif raw[i] == '--squads':
                sq = raw[i + 1]
            else:
                tn = raw[i + 1]
            i += 2
            continue
        argv.append(raw[i])
        i += 1
    if len(argv) != 5:
        sys.exit('usage: soccer_payload.py <scored.json> <tickets.json> <xg.psv> <out.json> '
                 '<date> [--season S.json] [--teamnews T.json]')
    build(*argv, season_path=sp, teamnews_path=tn, squads_path=sq)
