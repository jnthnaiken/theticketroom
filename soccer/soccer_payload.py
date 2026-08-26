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
import json, io, sys, math, itertools, os

# 2026-08-26 -- labels are the ESPN scoreboard displayName, so the card names the club the way
# the results feed will when it settles.
MATCH_LABEL = {
    'real-madrid-v-real-sociedad': ('Real Madrid', 'Real Sociedad'),
    'aek-athens-v-levski-sofia': ('AEK Athens', 'Levski Sofia'),
    'lyon-v-fenerbahce': ('Lyon', 'Fenerbahce'),
    'nk-celje-v-slovan-bratislava': ('NK Celje', 'Slovan Bratislava'),
    'viking-v-dinamo-zagreb': ('Viking FK', 'Dinamo Zagreb'),
}

# SOCCERLIVE-2026-08-26. The live loop addresses matches by ESPN EVENT ID, baked here, never
# resolved at runtime by team name -- ESPN truncates display names ("Hapoel Be'er" for Hapoel
# Be'er Sheva) and fixture-name matching is the same class of bug as SPFIRST-2026-08-22.
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
          season_path=None, teamnews_path=None):
    P = json.load(io.open(scored_path, encoding='utf-8'))
    T = json.load(io.open(tickets_path, encoding='utf-8'))
    TN = (json.load(io.open(teamnews_path, encoding='utf-8'))
          if teamnews_path and os.path.exists(teamnews_path) else {})
    XI, BENCH, ABSENT = TN.get('xi', {}), TN.get('bench', {}), TN.get('absent', {})
    TNGOALS, CLUB = TN.get('goals', {}), TN.get('club', {})
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

        def _side(x):
            for lab in (home, away):
                if x == lab or x in lab or lab in x:
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
            'out': n in ABSENT,
            'soft': False, 'form': None,
            'aT': 100, 'wf': 1.0, 'khr': None, 'powidx': None, 'phr9': None, 'zonev': None,
            'odds': p.get('odds'),
            'TOTAL': round(p['TOTAL'], 1),
            'baseTotal': round(p['TOTAL'], 1),
            'blend': p.get('blend'),
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

    T = [shape_ticket(t, players, i, VOICE, avg_min) for i, t in enumerate(T)]

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
            'build': f'{date} live',
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
    dec = [_dec(l['odds']) for l in legs if l.get('odds')]
    L = len(dec)
    s = -risk
    for a in range(L):
        for b in range(a + 1, L):
            s += dec[a] * dec[b]
    for a in range(L):
        for b in range(a + 1, L):
            for c in range(b + 1, L):
                s += dec[a] * dec[b] * dec[c]
    if L >= 4:
        for a, b, c, d in itertools.combinations(range(L), 4):
            s += dec[a] * dec[b] * dec[c] * dec[d]
    return _r1(s)


def _rr_block(legs, risk):
    return {'struct': 'by 2s & 3', 'risk': risk,
            'maxprofit': rr_maxprofit(legs, risk), 'bytwos': False}


def shape_ticket(t, players, i, voice, apps):
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
    anchor = out_legs[0]['name'] if out_legs else None
    return {
        'name': pool[i % len(pool)],
        'kind': kind,
        'badge': BADGE.get(kind, '🎟'),
        'note': voice.ticket_note(out_legs, players, apps),
        'players': out_legs,
        'nlegs': len(out_legs),
        'anchor': anchor,
        'lock': min((l['gtime'] for l in out_legs if l['gtime']), default=''),
        'has_late': False,
        'final': False,
        'locked': False,
        'rr': (_rr_block(out_legs, t.get('risk', 2.0)) if len(out_legs) >= 3 else None),
        'wxsum': {'boost': 0, 'supp': 0, 'dome': 0, 'neu': 0},
        'confleg': sum(1 for l in out_legs if players.get(l['name'], {}).get('status') == 'confirmed'),
        'unres': sum(1 for l in out_legs if (players.get(l['name'], {}).get('unres'))),
        'priced': sum(1 for l in out_legs if l['odds']),
    }


def _pick(options, key):
    h = 0
    for ch in key:
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    return options[h % len(options)]


class Voice:
    def __init__(self, P):
        self.q = {}
        for k in ('npxg90', 'xgpershot', 'shots90'):
            v = sorted(x[k] for x in P if x.get(k) is not None)
            self.q[k] = (v[int(len(v) * 0.60)] if len(v) >= 3 else None)

    def _hi(self, k, v):
        return v is not None and self.q.get(k) is not None and v >= self.q[k]

    def angles(self, p, avg, who, brief=False):
        out = []
        npx, xps, sh = p.get('npxg90'), p.get('xgpershot'), p.get('shots90')
        fin, odds = p.get('finish90'), p.get('odds')
        comp = ('the Champions League playoff round' if p.get('league') == 'UCL_PO'
                else 'his league')
        if npx is None:
            if brief:
                out.append(('noxg', _pick([
                    f'{who} has no xG behind him',
                    f'{who} has no model behind him',
                    f'{who} rides the price alone',
                ], who)))
            else:
                out.append(('noxg', _pick([
                    f'{who} has no top-five xG history behind him, so that price is the whole argument',
                    f'{who} sits outside Understat\'s five leagues — {comp} is not covered — so the market is carrying him',
                    f'{who} is unscored on the edge half and rides the market alone',
                ], who)))
            if odds:
                out.append(('price', f'{who} is {odds:+d}' if brief else
                            _pick([f'{who} is the shortest of them at {odds:+d}',
                                   f'{who} is priced {odds:+d}'], who + 'p')))
            return out
        if self._hi('npxg90', npx):
            out.append(('rate', f'{who} runs {npx:.2f} xG a 90' if brief else _pick([
                f'{who} runs {npx:.2f} non-penalty xG a 90',
                f'{who} is generating {npx:.2f} xG every 90 he plays',
                f'{who} carries {npx:.2f} xG a 90 into it',
            ], who)))
        if self._hi('xgpershot', xps):
            out.append(('quality', f'{who} is at {xps:.2f} xG a shot' if brief else _pick([
                f'{who} gets into the right positions — {xps:.2f} xG a shot',
                f'{who} takes the better chance at {xps:.2f} xG a shot',
                f'{who} shoots from where it counts ({xps:.2f} xG a shot)',
            ], who + 'q')))
        if self._hi('shots90', sh):
            out.append(('volume', f'{who} shoots {sh:.1f} a 90' if brief else _pick([
                f'{who} gets {sh:.1f} attempts away every 90',
                f'{who} shoots {sh:.1f} times a 90',
            ], who + 'v')))
        if fin is not None and fin >= 0.05:
            out.append(('finish', f'{who} is +{fin:.2f} on his xG' if brief else
                        f'{who} has been beating his xG by {fin:.2f} a 90'))
        elif fin is not None and fin <= -0.08:
            out.append(('finish', f'{who} is {fin:.2f} under his xG' if brief else
                        f'{who} sits {abs(fin):.2f} a 90 short of his xG, which is a case for him '
                        f'only if you believe that regresses'))
        if avg:
            if avg >= 75:
                out.append(('mins', f'{who} plays the ninety' if brief else _pick([
                    f'{who} plays the full ninety ({avg:.0f} minutes an appearance)',
                    f'{who} is on the pitch {avg:.0f} minutes a game',
                ], who + 'm')))
            else:
                out.append(('mins', f'{who} is a {avg:.0f}-minute man' if brief else
                            f'{who} averages only {avg:.0f} minutes an appearance'))
        if not out:
            out.append(('rate', f'{who} runs {npx:.2f} xG a 90' if brief else
                        f'{who} runs {npx:.2f} non-penalty xG a 90'))
        if odds:
            out.append(('price', f'{who} is {odds:+d}' if brief else f'{who} is priced {odds:+d}'))
        return out

    def ticket_note(self, legs, players, apps):
        per = 1 if len(legs) >= 3 else 2
        used, bits = set(), []
        for l in legs:
            p = players.get(l['name'])
            if not p:
                continue
            cands = self.angles(p, apps.get(l['name']), _surname(l['name']), brief=True)
            took = 0
            for k, c in cands:
                if k in used:
                    continue
                used.add(k)
                bits.append(c if took == 0 else _depersonalise(c, _surname(l['name'])))
                took += 1
                if took == per:
                    break
            if not took and cands:
                bits.append(cands[0][1])
        return _sentence(bits)

    def why(self, p, avg):
        n = p['name']
        keep, used = [], set()
        for k, c in self.angles(p, avg, n):
            if k in used:
                continue
            used.add(k)
            keep.append(_depersonalise(c, n) if keep else c)
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
    return clause[len(name) + 1:] if clause.startswith(name + ' ') else clause


if __name__ == '__main__':
    raw, argv, sp, tn = sys.argv[1:], [], None, None
    i = 0
    while i < len(raw):
        if raw[i] in ('--season', '--teamnews'):
            if raw[i] == '--season':
                sp = raw[i + 1]
            else:
                tn = raw[i + 1]
            i += 2
            continue
        argv.append(raw[i])
        i += 1
    if len(argv) != 5:
        sys.exit('usage: soccer_payload.py <scored.json> <tickets.json> <xg.psv> <out.json> '
                 '<date> [--season S.json] [--teamnews T.json]')
    build(*argv, season_path=sp, teamnews_path=tn)
