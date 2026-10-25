#!/usr/bin/env python3
"""nba_settle.py -- FIRSTBASKET-2026-10-17. Grade finished basketball boards, and roll the model's state forward.

TWO JOBS, ONE ESPN READ (nba_espn.parse):
  1. GRADE. Every archived board nba/boards/<date>.json not yet in nba_season.json graded_nights whose games
     are all FINAL: stamp each priced man's `ftd1` (he scored his game's first points, FREE THROWS COUNT -- FanDuel, FDRULES), void a man who did
     not play, write meta.finals, and fold with soccer_grade.fold() -- the same grader and ledger shape every
     room uses. A first-basket leg reads `ftd1`, never `hr` (soccer_grade.grade_ticket: l['ftd']).
  2. LEARN. Every regular-season game after state.meta.through, oldest first, goes through
     nba_fb.State.update() -- the same function the 2014-26 replay built the state with -- and `through`
     advances one whole day at a time, only once every game that day is final. A day is never half-learned.

    python3 nba_settle.py [--season nba_season.json] [--boards boards] [--state nba_state.json]
Exit 0 always unless the arguments are wrong; a network miss leaves the work for the next build.
"""
import argparse, datetime, glob, io, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, '..', 'soccer'), os.path.join(HERE, '..', 'nfl')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import nba_espn as E
import nba_fb as F

ZERO = {'graded': 0, 'won': 0, 'units': 0.0, 'staked': 0.0}


def today_et():
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=4)).date()


def _match(name, cands):
    """Board name -> ESPN name, inside one team. Exact normalized name, then initial+surname."""
    n = F.norm(name)
    for c in cands:
        if F.norm(c) == n: return c
    ik = F.ikey(name)
    hits = [c for c in cands if F.ikey(c) == ik]
    return hits[0] if len(hits) == 1 else None


def grade_board(path, season_path, getsum=E.summary, getsb=E.scoreboard):
    import soccer_grade
    D = json.load(io.open(path, encoding='utf-8'))
    date = D['meta'].get('date')
    season = json.load(io.open(season_path, encoding='utf-8')) if os.path.exists(season_path) else {}
    if not date or date in (season.get('graded_nights') or []):
        return 'already'
    want = {int(k): v for k, v in (D['meta'].get('games') or {}).items()}
    if not want:
        return 'no games'
    try:
        sb = getsb(date)
    except Exception as e:
        print(f'  {date}: scoreboard unreachable ({str(e)[:80]})'); return 'network'
    byp = {f'{a}@{h}': (eid, st, done) for eid, a, h, st, done, ty, _ in sb}
    finals, nfb, nvoid = [], 0, 0
    for gi, gm in sorted(want.items()):
        hit = byp.get(gm)
        if not hit:
            print(f'  ::warning::{date}: no ESPN event for {gm} -- not settling'); return 'unmatched'
        eid, st, done = hit
        if not done:
            if st == 'post':                       # postponed / cancelled: every leg on it voids
                for p in D['players'].values():
                    if p.get('game') == gi: p['void'] = True
                finals.append(gi); continue
            print(f'  {date}: {gm} not final yet'); return 'not final'
        try:
            g = E.parse(getsum(eid))
        except Exception as e:
            print(f'  {date}: summary {eid} unreachable ({str(e)[:80]})'); return 'network'
        for n, p in D['players'].items():
            if p.get('game') != gi: continue
            cands = [c for c, t in g['team_of'].items() if t == p.get('code')]
            who = _match(n, cands)
            # FDRULES-2026-10-24: FanDuel grades the first SCORE (free throws count) and refunds a listed player who
            # does not start -- even if he comes off the bench and scores first.
            starters = set(sum((g['starters'].get(T, []) for T in g['starters']), []))
            if who is None or who not in starters:
                p['ftd1'] = False; p['hr'] = False; p['void'] = True; nvoid += 1
                continue
            p['void'] = False
            p['ftd1'] = bool(g['fs']) and who == g['fs']
            p['hr'] = p['ftd1']
            if p['ftd1']: nfb += 1
        D['meta'].setdefault('fb', {})[str(gi)] = g['fs']
        finals.append(gi)
    D['meta']['finals'] = finals
    json.dump(D, io.open(path, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print(f'  {date}: {len(finals)} final game(s), {nfb} priced first-basket scorer(s), {nvoid} void(s)')
    if not os.path.exists(season_path):
        json.dump({'since': date, 'history': [0], 'graded_nights': [], 'cats': {'fb': dict(ZERO)}, 'stake': 1},
                  io.open(season_path, 'w', encoding='utf-8'), indent=1)
    soccer_grade.fold(path, season_path)
    return 'graded'


def learn(state_path, max_days=30, getsum=E.summary, getsb=E.scoreboard, until=None):
    st = F.State(json.load(io.open(state_path, encoding='utf-8')))
    through = datetime.date.fromisoformat(st.meta.get('through', '2026-04-12'))
    until = until or (today_et() - datetime.timedelta(days=1))
    d, n_days, n_games = through + datetime.timedelta(days=1), 0, 0
    while d <= until and n_days < max_days:
        try:
            sb = getsb(d.isoformat())
        except Exception as e:
            print(f'  learn {d}: scoreboard unreachable ({str(e)[:80]})'); break
        reg = [x for x in sb if x[5] == 2]            # regular season only, as the replay
        if any(not x[4] and x[3] != 'post' for x in reg):
            print(f'  learn {d}: not every game final -- stopping here'); break
        recs = []
        try:
            for eid, a, h, stt, done, ty, iso in sorted(reg, key=lambda x: (x[6] or '', x[0])):
                if not done: continue                   # postponed
                g = E.parse(getsum(eid))
                if len(g['starters'].get(g['H'], [])) != 5 or len(g['starters'].get(g['V'], [])) != 5:
                    print(f'  ::warning::learn {d}: {a}@{h} starters {[len(v) for v in g["starters"].values()]} -- skipped')
                    continue
                recs.append(g)
        except Exception as e:
            print(f'  learn {d}: summary unreachable ({str(e)[:80]}) -- stopping'); break
        for g in recs:
            st.update(g); n_games += 1
        st.meta['through'] = d.isoformat()
        d += datetime.timedelta(days=1); n_days += 1
    if n_days:
        json.dump(st.dump(), io.open(state_path, 'w', encoding='utf-8'), separators=(',', ':'))
    print(f'  learn: {n_days} day(s), {n_games} game(s), through {st.meta.get("through")}')
    return n_days


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--season', default=os.path.join(HERE, 'nba_season.json'))
    ap.add_argument('--boards', default=os.path.join(HERE, 'boards'))
    ap.add_argument('--state', default=os.path.join(HERE, 'nba_state.json'))
    A = ap.parse_args()
    for b in sorted(glob.glob(os.path.join(A.boards, '*.json'))):
        try:
            grade_board(b, A.season)
        except Exception as e:
            print(f'  ::warning::{os.path.basename(b)}: {e.__class__.__name__}: {e}')
    try:
        learn(A.state)
    except Exception as e:
        print(f'  ::warning::learn: {e.__class__.__name__}: {e}')
