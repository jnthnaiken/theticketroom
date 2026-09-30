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
          season_path=None, teamnews_path=None, squads_path=None, fgs_path=None, ftd_cache=None):
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

    # NOSHEETLOCK-2026-09-22. One league label per match, and the set of competitions that have
    # no team-news source, read from coverage.json's `intl` group rather than spelled out here.
    # See meta.nosheet below for why this exists at all.
    lg_of = {}
    for _x in P:
        lg_of.setdefault(_x['match'], _x.get('league'))
    _NOSHEET_LEAGUES = set()
    try:
        _cov = json.load(io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                              'coverage.json'), encoding='utf-8'))
        _NOSHEET_LEAGUES = {v for k, v in (_cov.get('intl') or {}).items() if k != '_doc'}
    except Exception as _e:                                   # noqa: BLE001
        print(f'  ::warning::coverage.json unreadable ({_e}) -- meta.nosheet will be empty, '
              f'so an international slip would never freeze. Fix before building one.')

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
    # 🚨 XIPARTIALPAYLOAD-2026-09-09 -- THE SEVENTH CALLER. The rule "the XI filter is PER MATCH"
    # (XIPARTIAL-2026-08-28) was fixed in soccer_draft.js buildPool, soccer_rebuild_cli.js,
    # soccer_draft_cli.js and soccer_mock.py. This file was missed, and it is the one that writes
    # `pool` and `meta.gate` -- what the COVER counts. On 2026-09-09 (20 fixtures, sheets out for
    # the 6 European ties, 14 MLS matches still hours from theirs) the flat `x['name'] in XI`
    # dropped every player whose own match had not published: the cover read 13 pool players
    # across SIX matches on a twenty-match card. The DRAFT was unaffected -- it rebuilds the pool
    # in JS from scored.json and was correctly showing MLS moons -- so this was display only, and
    # that is exactly why it survived: the tickets looked right.
    #
    # A player in a match with no published sheet is UNKNOWN, not benched, so he stays in.
    # `published` is derived from the matches carrying any CLASSIFIED player (XI/bench/absent),
    # never an empty set -- an empty set means "nothing published", which silently re-disables
    # the filter. Same `is None` vs `set()` trap as the other five callers.
    #
    # Z_GATE is 0.70 (WIN75/ZGATE70-2026-08-30), not 0.75. The literal here predates that change
    # and made the DISPLAYED pool tighter than the one the draft actually uses.
    Z_GATE = 0.70
    MIN_ODDS = -200  # FLOOR200-2026-09-17 (was 100, PLUSMONEY-2026-09-11): a man shorter than -200 cannot be drafted, so he is not "in the gate"
    _mof = {x['name']: x['match'] for x in P}
    published = {_mof[n] for n in list(XI) + list(BENCH) + list(ABSENT) if n in _mof}
    gated = [x for x in sorted(P, key=lambda x: -x['TOTAL'])
             if x.get('gate_z', 0) >= Z_GATE
             and x.get('odds') is not None and x['odds'] >= MIN_ODDS
             and (not XI or x['name'] in XI or x['match'] not in published)]
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

    # FGS-2026-09-29 -- the one first-goalscorer pick (soccer_fgs.py). Rides in meta.ftd, outside
    # D.tickets, exactly like football's first-TD pick: kind 'ftd', leg flagged ftd:true, graded on
    # the player's ftd1 (scored his match's first goal). soccer_grade.fold() adds it to the tickets.
    ftd_t = None
    if fgs_path:
        import soccer_fgs
        from datetime import datetime as _dt, timezone as _tz
        _pm = {x['name']: x['match'] for x in P}
        _view = {n: dict(v, match=_pm.get(n)) for n, v in players.items()}
        _d0 = _dt.fromisoformat(date).replace(tzinfo=_tz.utc)
        _now = (_dt.now(_tz.utc) - _d0).total_seconds() / 60.0
        _started = lambda n: (n in _pm) and _now >= ko_of(_pm[n])
        _row = soccer_fgs.choose(_view, soccer_fgs.load_fgs(fgs_path), ftd_cache, _started)
        if _row and _row.get('name') in players:
            _p = players[_row['name']]
            _leg = {'name': _row['name'], 'team': _p['team'], 'total': _p['TOTAL'], 'aT': 100,
                    'wf': 1.0, 'gmatch': _p['gmatch'], 'gtime': _p['gtime'], 'game': _p['game'],
                    'late': False, 'odds': int(_row['odds']), 'status': _p['status'], 'ftd': True}
            _doy = _dt.fromisoformat(date).timetuple().tm_yday
            _o = int(_row['odds']); _dec = 1 + (_o / 100 if _o > 0 else 100 / -_o)
            ftd_t = {'name': FGS_NAMES[_doy % len(FGS_NAMES)], 'kind': 'ftd', 'badge': '⚡',
                     # HUDSON-2026-09-29: no percentage in the prose -- the colour man sells it.
                     'note': (f"{_row['name']} to score the first goal of {_p['gmatch']}. "
                              + _pick(OPENER_LINES, _row['name'] + date).format(who=_surname(_row['name']))),
                     'players': [_leg], 'nlegs': 1, 'anchor': _row['name'], 'lock': _p['gtime'],
                     'has_late': False, 'final': False, 'locked': False, 'rr': None,
                     'wxsum': {'boost': 0, 'supp': 0, 'dome': 0, 'neu': 0},
                     'confleg': 1 if _p['status'] == 'confirmed' else 0, 'unres': 0, 'priced': 1,
                     'parlay_am': _o, 'payout10': round(10 * _dec, 1), 'ftd': True}

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
            # 🚨 NOSHEETLOCK-2026-09-22. The matches that can NEVER produce a 'confirmed'
            # status, keyed by game number exactly as `ko` above is -- ticketIsLocked() reads
            # both with the same key and they must not drift apart.
            #
            # CONFLOCK freezes a slip when every leg is confirmed. soccer_teamnews.py scrapes
            # CLUB team sheets; nothing scrapes a national squad, so a leg in an international
            # fixture never reaches 'confirmed' and its slip would never freeze at all -- it
            # would still be re-drafting through its own kickoff, which is the football bug of
            # 2026-09-20 (claude/nfl-anchorwave-2026-09-20.md) arriving in this room.
            #
            # ⚠️ DERIVED FROM coverage.json, NOT A LIST OF LEAGUE LABELS SPELLED OUT HERE.
            # A second copy of "which competitions have no team news" is the thing that goes
            # stale the day a group is added: INTL-2026-09-22 added three competitions at once.
            # The `intl` group IS that answer, so it is read, not restated. An older
            # coverage.json with no `intl` key yields {} and nothing changes.
            'nosheet': {str(gnum[m]): True for m in matches
                        if lg_of.get(m) in _NOSHEET_LEAGUES},
            'build': _build_stamp,
            'ftd': ftd_t,          # FGS-2026-09-29: the first-goalscorer pick, or None
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
                       # RESTATED-2026-09-17: a flag only (the per-night detail stays in the file),
                       # so the tracker can say the record is restated.
                       'restated': bool(prior.get('restated')),
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
BADGE = {'moon': '💥', 'builder': '🥅', 'family': '💥', 'lunch': '🍱', 'late': '🌃', 'ftd': '⚡'}
# FGS-2026-09-29: one first-goalscorer slip a slate, its title rotated by date like every other pool.
# HUDSON-2026-09-29. The Opener's write-up. Owner: the "model gives him 13.5%" line was a stat read
# off a card that already prints it. The pick is the slate's best first-goal chance -- the most
# danger, starting -- so that is what gets sung. No digits, no promise he scores.
OPENER_LINES = [
    'Oh my word, {who} is the first name on the team sheet and the first name on ours. Magisterial!',
    '{who} lives in that box like a landlord collecting rent, and somebody has to break the seal. Why not him?',
    'Kickoff, and {who} is already prowling like a panther in the long grass. Glorious!',
    '{who} is the man to open the tin, a can opener in golden boots. Pure poetry!',
    'Early doors, somebody has to be the hero, and {who} was born for the role. Mamma mia!',
    '{who} smells the first chance before it even arrives, like a shark smelling one drop of blood from a mile off. Delicious!',
]

FGS_NAMES = ['Breaks the Deadlock', 'First Blood', 'Opening Account', 'Early Doors', 'Off the Mark',
             'First to the Net', 'The Opener', 'Sets the Tone', 'Draws First Blood', 'Ice Breaker',
             'Gets Us Going', 'Kick-Off Call', 'First on the Sheet', 'Breaks the Seal']


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
    # ANCHORCARRY-2026-09-06: capture the anchor in DRAFT order, before the display sort below.
    # soccer_draft_cli.js emits `legs` anchor-first and carries no explicit `anchor` field, so
    # legs[0] IS the seated anchor. `t.get('anchor')` covers a prior board being carried back in.
    _anchor_name = t.get('anchor') or (legs[0].get('name') if legs else None)
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
    # ANCHORCARRY-2026-09-06: CARRY the anchor the draft assigned, do not re-derive it.
    #
    # `out_legs` was sorted by TOTAL for DISPLAY four lines above. The anchor is the man the
    # draft seated, which is legs[0] in DRAFT order -- soccer_draft.js is careful about exactly
    # this and grabs `legs[0].name` BEFORE its own display sort, then ships it as `anchor`.
    # Reading `out_legs[0]` here threw that away and relabelled the slip with whichever leg
    # happened to have the highest TOTAL.
    #
    # It stayed invisible because until today the anchor WAS always the strongest man on his
    # own slip, so the two agreed on every board from 08-27 to 09-05 (checked: distinct anchors
    # == moons/2, zero singles, on all six). On 2026-09-06 Lamine Yamal (TOTAL 172.2) was drafted
    # as a LEG on Benjamin Sesko's slip (169.3) and took the label, which published a board
    # reading FIVE distinct moon anchors against ANCH=4, with Yamal and Sesko each showing a
    # single moon instead of a pair. The draft itself was correct -- the same engine run locally
    # on the same inputs seats four anchors and gives Sesko both slips.
    #
    # Same shape as NAMECARRY above: a field the draft owns must be carried, not recomputed.
    anchor = _anchor_name
    if anchor is None or not any(l['name'] == anchor for l in out_legs):
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


def _rot(seq, key, pin_last=('price', 'flair')):
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

OPENERS_3 = ['Oh, this is delicious', 'Three magicians, one afternoon', 'Get the smelling salts',
             'Pure poetry', 'Sheer theatre', 'Three artists, one canvas', 'Mamma mia',
             'Bring the brass band', 'Oh my word', 'What a trio', 'Hold on to your hats']
OPENERS_1 = ['Oh my word', 'Magisterial', 'Pure poetry', 'Mamma mia',
             'Sheer theatre', 'Oh, delicious', 'Get the smelling salts', 'Glorious']

FRAMES_3 = ['{a}, {b}, and {c}.', '{o}! {a}, {b}, {c}.', '{a}. {b}, and {c}.',
            '{o} — {a}, {b}, and {c}.', '{a} and {b}. {c}.', '{a}; {b}; {c}.']
FRAMES_2 = ['{a} and {b}.', '{o}! {a}, and {b}.', '{a}, and {b}.', '{o} \u2014 {a}, and {b}.']

# TNOTEFIT-2026-09-23: the two-line `.tnote` clamp, in characters. Measured, not guessed:
# every ticket note the board has ever shipped fitted at or under 94, and the widest that
# renders inside two lines at 12px in the narrowest card column is about this. A note over
# it gets recomposed shorter rather than truncated by the browser.
TNOTE_B = 100


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

        VOICE-2026-09-23. The register is operatic on purpose. The numbers are the same
        numbers they always were; the adjectives do the singing. Three rules keep an
        excitable voice honest, and all three are load-bearing:

          * EVERY clause still carries a figure off the payload, and NO clause says a goal is
            coming. "Magisterial at 0.61 a 90" describes 0.61. "He'll bury one tonight" would
            be a forecast, and there is not one of those in this file.
          * VOICE-2026-09-23b. THE FRAME IS ALWAYS GENEROUS. The first cut of this register
            was operatic about the good numbers and snide about the rest -- "cruel rather than
            bad", "the whole worry", "bless him", "a lovely blank space". That is not the
            register; the register never buries anybody. Note that the negative angles do not
            go away and the numbers do not move: a man 0.15 a 90 under his xG still gets that
            printed, he is just OWED it rather than wasteful, because the chances he got are
            a fact and the finishing is the part that has not happened yet. A short average
            is live minutes, not a countdown. No model on him is romance, not a blank.
            Generous framing of a true number is voice. Softening the number would be a lie,
            and the test file is there to catch anyone who confuses the two.
          * THE RAPTURE HAS A BUDGET. A ticket note is two of these clauses inside `.tnote`'s
            two-line clamp; a card is three. CLMPTIER-2026-09-23 is the fresh scar: prose that
            overflows its budget gets thrown away whole and replaced by a stub. So every
            `full` here is written to land in the sixties and seventies, not the hundreds, and
            the arias are short ones.
          * VOICE-2026-08-28c still applies below, and it bites harder in this register,
            because flourishes love the object position. See the `say` note.
        """
        out = []
        npx, xps, sh = p.get('npxg90'), p.get('xgpershot'), p.get('shots90')
        fin, odds = p.get('finish90'), p.get('odds')
        comp = ('the Champions League playoff round' if p.get('league') == 'UCL_PO'
                else 'his league')
        k = who + salt

        # VOICE-2026-08-28c. Some phrasings put the player in the OBJECT ("the manager will
        # not take Kane off", "+150 for Pulisic", "nobody is talking Kane out of it"). Those
        # are fine mid-sentence, but if one LEADS, every later clause -- which
        # `_depersonalise` has reduced to a bare verb phrase -- attaches itself to the wrong
        # subject: "The manager will not take Harry Kane off ... and shoots from where the
        # angels live" says it of the manager. So when this call is producing the opening
        # clause, choose only from the forms where the player is the subject, and fall back to
        # the whole bank if a given angle has none.
        #
        # The matching rule for a NON-leading form: the name must sit somewhere `him` reads
        # correctly, because that is exactly what `_depersonalise` swaps in. "the book has
        # {who} at -120" becomes "the book has him at -120" and is fine; "so {who} comes to us
        # with nothing" would become "so him comes to us" and is not. Every object-position
        # entry below was written against that substitution, not against the sentence it
        # happens to appear in here.
        def say(opts, kk):
            if lead:
                subj = [o for o in opts if o.startswith(who + ' ')]
                if subj:
                    return _pick(subj, kk)
            return _pick(opts, kk)

        # ⚽ HUDSON-2026-09-29. Owner: "soccer seems to have gotten away from the roy hudson language,
        # what happened? the write ups are supposed to be fun, they can see the data". What happened
        # is the HARD RULE above: every clause had to carry its number, so the rapture got welded to
        # "0.66 non-penalty xG a 90" and read like a stat sheet with a thesaurus. The card already
        # prints every figure. So the numbers leave the prose entirely and the adjectives get the
        # whole stage -- the over-the-top, poetic, gloriously unhinged colour-man register.
        #
        # WHAT STAYS: an angle still only FIRES when the payload earns it (same _hi() bands, same
        # finishing thresholds, same minutes split), the frame stays generous, no clause says a goal
        # is coming tonight, and the subject/object rules below are unchanged. The PRICE angle is
        # retired from the prose (the odds sit right beside it) and replaced as the always-there
        # floor by FLAIR, pinned last the way price was. Original phrasing in the style; no quotes.
        if npx is None:
            out.append(('noxg',
                        say([f'{who} plays pure jazz, no sheet music',
                             f'{who} is a mystery in golden boots',
                             f'{who} runs on instinct and mischief',
                             f'{who} is beyond the spreadsheets',
                             f'no computer on earth can explain {who}',
                             f'{who} is street football in a kit'], k + 'n'),
                        say([f'{who} plays pure jazz, no sheet music, just instinct and a wicked grin',
                             f'{who} is a mystery wrapped in an enigma wrapped in a gorgeous pair of boots',
                             f'{who} runs on instinct and mischief, and the spreadsheets can go and whistle',
                             f'{who} is beyond the reach of every model ever built, pure street football',
                             f'no computer on this earth can explain {who}, and thank heavens for that',
                             f'{who} is a riddle the analysts gave up on, all swagger and sorcery'], k + 'N')))
        else:
            if self._hi('npxg90', npx):
                out.append(('rate',
                            say([f'{who} haunts that box like a ghost with a grudge',
                                 f'{who} lives in the six-yard box',
                                 f'{who} is a fox in the henhouse',
                                 f'{who} smells blood in the box',
                                 f'{who} is a pickpocket in the penalty area',
                                 f'the box belongs to {who}'], k + 'r'),
                            say([f'{who} haunts that penalty box like a ghost with a grudge and a key to the front door',
                                 f'{who} lives in the six-yard box, pays no rent and eats all the biscuits',
                                 f'{who} is a fox in the henhouse with his napkin already tucked in',
                                 f'{who} sniffs out chances like a truffle pig in a Tuscan forest',
                                 f'{who} gets on the end of everything, as if the ball is on a string',
                                 f'the penalty box is a cathedral, with {who} lighting every candle'], k + 'R')))
            if self._hi('xgpershot', xps):
                out.append(('quality',
                            say([f'{who} shoots like a surgeon',
                                 f'{who} never wastes a bullet',
                                 f'{who} picks his spots like a jeweller',
                                 f'{who} waits for the perfect moment',
                                 f'{who} is all precision, no panic',
                                 f'every shot from {who} is a love letter'], k + 'q'),
                            say([f'{who} only shoots from where the angels live',
                                 f'{who} is a surgeon with a scalpel dipped in honey',
                                 f'{who} waits for the moment like a heron over a still pond',
                                 f'{who} picks his spots like a jeweller choosing diamonds',
                                 f'{who} never wastes a bullet, every shot a love letter to the net',
                                 f'every shot off the boot of {who} is a little work of art'], k + 'Q')))
            if self._hi('shots90', sh):
                out.append(('volume',
                            say([f'{who} shoots on sight',
                                 f'{who} lets fly from anywhere',
                                 f'{who} is trigger-happy and fearless',
                                 f'{who} will have a pop from the car park',
                                 f'{who} never stops shooting',
                                 f'nobody talks {who} out of a shot'], k + 'v'),
                            say([f'{who} shoots on sight, like a man with a personal grudge against goalkeepers',
                                 f'{who} fires away like a pirate ship with a hold full of cannonballs',
                                 f'{who} will have a dig from the car park, the corner flag, the tunnel',
                                 f'{who} is trigger-happy and fearless, the keeper\'s gloves are smoking',
                                 f'{who} never stops shooting, bless his thunderous boots',
                                 f'nobody on this earth can talk {who} out of a shot'], k + 'V')))
            if fin is not None and fin >= 0.05:
                out.append(('finish',
                            say([f'{who} is finishing like a god',
                                 f'{who} buries everything',
                                 f'{who} has ice in his veins',
                                 f'{who} is ruthless in front of goal',
                                 f'the net adores {who}'], k + 'f'),
                            say([f'{who} is burying chances like a pirate burying treasure',
                                 f'{who} is finishing with the cold blood of an assassin',
                                 f'{who} has ice in his veins and dynamite in his boots',
                                 f'{who} is ruthless in front of goal, lethal and utterly delicious',
                                 f'the net just throws its arms wide open for {who}'], k + 'F')))
            elif fin is not None and fin <= -0.08:
                out.append(('finish',
                            say([f'{who} is owed a goal or three',
                                 f'{who} is due, oh so due',
                                 f'{who} has been robbed by keepers',
                                 f'{who} keeps knocking on the door',
                                 f'the football gods owe {who}'], k + 'f'),
                            say([f'{who} keeps arriving in all the right places and the goals are overdue',
                                 f'{who} is owed, the chances keep coming and the dam is creaking',
                                 f'{who} has been robbed blind by goalkeepers and the debt is piling up',
                                 f'{who} keeps knocking on that door, and doors do not stay shut forever',
                                 f'the football gods owe {who} a big, fat, gorgeous one'], k + 'F')))
            if avg:
                if avg >= 75:
                    out.append(('mins',
                                say([f'{who} plays every last second',
                                     f'{who} never comes off',
                                     f'{who} is there at the death',
                                     f'{who} runs till the lights go out',
                                     f'the hook never comes for {who}'], k + 'm'),
                                say([f'{who} plays the full ninety like a marathon man with a grin on his face',
                                     f'{who} never comes off, the manager would sooner substitute himself',
                                     f'{who} is out there at the death, bless his iron lungs',
                                     f'{who} runs and runs until the floodlights go out',
                                     f'the manager would never dream of hooking {who}'], k + 'M')))
                else:
                    out.append(('mins',
                                say([f'{who} is a firecracker, not a candle',
                                     f'{who} packs his minutes with mischief',
                                     f'{who} is pure chaos in short bursts',
                                     f'{who} needs no ninety to cause a riot',
                                     f'every minute of {who} is box office'], k + 'm'),
                                say([f'{who} is a firecracker, not a candle, every minute a fireworks show',
                                     f'{who} packs his minutes with mischief and menace',
                                     f'{who} is pure chaos in short bursts, a cat among the pigeons',
                                     f'{who} does not need the full ninety to start a riot',
                                     f'every single minute of {who} on the pitch is box office'], k + 'M')))
        # THE FLOOR. Every man gets a beat even when no band fires, the way price used to fill in.
        out.append(('flair',
                    say([f'{who} is box office',
                         f'{who} is pure theatre in boots',
                         f'{who} could light up a wet Tuesday',
                         f'{who} brings the fireworks',
                         f'{who} plays with a twinkle in his eye',
                         f'{who} is a poet with a football'], k + 'x'),
                    say([f'{who} is box office, the kind of player who makes you spill your tea',
                         f'{who} is pure theatre in a pair of boots, a matinee idol',
                         f'{who} could light up a wet Tuesday in a car park',
                         f'{who} brings the fireworks, the confetti and the brass band',
                         f'{who} plays with a twinkle in his eye and mischief in his feet',
                         f'{who} is a poet with a football and a smile like a sunrise'], k + 'X')))
        return out

    def ticket_note(self, legs, players, apps, tname=''):
        """One sentence naming what each leg is FOR, in slip order, no angle used twice.

        TNOTEFIT-2026-09-23. `.tnote` is `-webkit-line-clamp:2` at 12px, so a note that runs
        long is not merely ugly: the browser cuts it mid-word and the last fact on the slip is
        simply gone off the end of the card. That never bit while the phrase banks were flat
        and every `full` was forty characters. VOICE-2026-09-23 made them expansive, and an
        expansive voice needs a floor under it rather than a promise that every hand-written
        variant is short enough -- there are sixty of them and they combine.

        So: compose, measure, and step down. Full clauses with an opener; then full clauses
        with no opener; then the short forms. Same legs, same angles, same numbers at every
        step -- only the wording shrinks. This is CLMPTIER's lesson applied before the fact
        instead of after it: shorten the sentence you want, do not lose the end of it.
        """
        for step in (0, 1, 2, 3, 4):
            body = self._compose(legs, players, apps, tname, step)
            if len(body) <= TNOTE_B:
                return body
        # TNOTECUT-2026-09-23. Three steps down and still long: three legs, three long
        # surnames, nothing left to shorten. Cut at a clause boundary rather than hand the
        # browser a sentence it will cut mid-word. This is CLMPTIER's judgement, verbatim --
        # whole clauses that fit beat a ragged tail -- and the clause we lose belongs to a leg
        # the card is already printing by name above the note.
        return _clmp(body, TNOTE_B) or body

    def _compose(self, legs, players, apps, tname, step=0):
        # a three-leg slip gets one clause per leg or the note overruns the two-line clamp;
        # a single (anchor / screamer) has the room for two and reads thin with one. `step` is
        # TNOTEFIT's ratchet: 1 drops the opener, 2 drops to the short forms as well.
        # HUDSON-2026-09-29: two more rungs. The sung clauses are longer than the numeric ones were,
        # so a single used to drop straight to ONE short clause ("Martinez is a pickpocket in the
        # penalty area.") -- two short clauses (steps 2-3) read far better before we go to one (4).
        per = 1 if (len(legs) >= 3 or step >= 4) else 2
        short = step >= 2
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
                    bits.append(brief if (per == 1 or short) else full)
                else:
                    bits.append(_depersonalise(brief if (per == 1 or short) else full, sur))
                took += 1
                if took == per:
                    break
            if not took and cands:
                bits.append(cands[0][1] if (per == 1 or short) else cands[0][2])
        if not bits:
            return ''
        _noop = (lambda fr: [f for f in fr if '{o}' not in f]) if step in (1, 3, 4) else (lambda fr: fr)
        if len(bits) >= 3:
            body = _pick(_noop(FRAMES_3), tname + 'f3').format(
                a=bits[0], b=bits[1], c=', '.join(bits[2:]), o=_pick(OPENERS_3, tname + 'o3'))
        elif len(bits) == 2:
            body = _pick(_noop(FRAMES_2), tname + 'f2').format(
                a=bits[0], b=bits[1], o=_pick(OPENERS_1, tname + 'o1'))
        else:
            body = bits[0] + '.'
        body = re.sub(r'(?<=[.!] )([a-z])', lambda m: m.group(1).upper(), body)
        return body[0].upper() + body[1:]

    def why(self, p, avg):
        """Two or three clauses on one card, full name first, then the name drops away.

        VOICE-2026-09-23c. 08-28c said the LEAD has to be a subject form, because the clauses
        after it are bare verb phrases that inherit its subject. That was half the rule. An
        object form anywhere but LAST does the same damage, because it brings a subject of its
        own and the next clause attaches to that instead:

            "Jason Shokalook takes them from the places that pay, 0.17 xG a shot, the football
             gods owe him 0.12 a 90 on his xG, and is magisterial in there ..."

        -- the gods are magisterial in there. It never showed up before because `_rot` pins
        `price` last and price was the object-heavy bank; VOICE-2026-09-23 put object forms in
        every bank and the bug walked straight out onto a card.

        So: pick the angles first, then render, and every clause but the final one is taken
        from the subject-form bank. The last clause is free, where an object form reads
        perfectly well ("and the book has him at +275") and is most of the variety.
        """
        n = p['name']
        chosen, used = [], set()
        lead_of = {a[0]: a for a in self.angles(p, avg, n, lead=True)}
        for key, _brief, full in _rot(self.angles(p, avg, n), n + 'card'):
            if key in used:
                continue
            used.add(key)
            chosen.append((key, full))
            if len(chosen) == 3:
                break
        keep = []
        for i, (key, full) in enumerate(chosen):
            if i < len(chosen) - 1:
                full = lead_of.get(key, (0, 0, full))[2]
            if i == 0:
                keep.append(full)
            elif full.startswith(n + ' '):
                keep.append('He ' + full[len(n) + 1:])     # subject form -> its own sentence
            else:
                keep.append(_depersonalise(full, n))       # object form, already has a subject
        return _sung(keep, n)


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


def _sung(bits, key=''):
    """HUDSON-2026-09-29. A card is short SENTENCES, the first one shouted: "Messi sniffs out chances
    like a truffle pig in a Tuscan forest! He is a firecracker, not a candle. And he is ..." -- not
    one comma-spliced paragraph, which is how the flourishes turned to porridge. Each clause after
    the first already carries its own subject ("He ..." or "the net adores him"), so a full stop is
    always a legal join. The last one opens with "And" on some cards, for the rhythm."""
    bits = [b for b in bits if b]
    if not bits:
        return ''
    cap = lambda t: t[0].upper() + t[1:]
    out = cap(bits[0]) + '!'
    for i, b in enumerate(bits[1:], 1):
        if i == len(bits) - 1 and len(bits) > 2 and _h(key + 'and') % 2:
            out += ' And ' + (b[0].lower() + b[1:] if b.startswith('He ') else b) + '.'
        else:
            out += ' ' + cap(b) + '.'
    return out


def _clmp(text, b):
    """Cut a note back to the last whole clause that fits inside `b`, or '' if none does.

    TNOTECUT-2026-09-23. Deliberately the same shape as clmp() in index.html: find a clause
    separator, cut there, re-punctuate. It returns '' rather than a fragment when the first
    clause alone is already too long, so the caller can decide that an overlong sentence beats
    a two-word one -- losing the end of a note to the browser is bad, losing all of it is worse.
    """
    if len(text) <= b:
        return text
    head = text[:b - 1]
    # Every separator FRAMES_2 and FRAMES_3 can put between two clauses. '. ' has to be in
    # here: the frame '{a} and {b}. {c}.' is the one that overflows worst, and a cut that only
    # knew about commas found no boundary in it at all and gave up.
    i = max(head.rfind(sep) for sep in ('. ', ', ', '; ', ' \u2014 ', ' and '))
    if i < 40:
        return ''
    return head[:i].rstrip(' ,;\u2014-') + '.'


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
    raw, argv, sp, tn, sq, fg, fc = sys.argv[1:], [], None, None, None, None, None
    i = 0
    while i < len(raw):
        if raw[i] in ('--season', '--teamnews', '--squads', '--fgs', '--ftd-cache'):
            if raw[i] == '--season':
                sp = raw[i + 1]
            elif raw[i] == '--squads':
                sq = raw[i + 1]
            elif raw[i] == '--fgs':
                fg = raw[i + 1]
            elif raw[i] == '--ftd-cache':
                fc = raw[i + 1]
            else:
                tn = raw[i + 1]
            i += 2
            continue
        argv.append(raw[i])
        i += 1
    if len(argv) != 5:
        sys.exit('usage: soccer_payload.py <scored.json> <tickets.json> <xg.psv> <out.json> '
                 '<date> [--season S.json] [--teamnews T.json]')
    build(*argv, season_path=sp, teamnews_path=tn, squads_path=sq, fgs_path=fg, ftd_cache=fc)
