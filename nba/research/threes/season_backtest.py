#!/usr/bin/env python3
"""season_backtest.py -- DOWNTOWN-2026-10-26. Restate Downtown for this season's nights so far.

Owner: "and we backtest for this season and update the ledger too" / "so there should be tickets for it from tonight".

Walk-forward and leak-free on the model: the state is the 2022-26 history replay (seed_state.py), then each night is
PICKED from the state as of the morning, at that night's real FanDuel main-line over prices (BettingPros 162 pull),
and only then learned. Lineups use the actual starters and the actual absentees -- what the confirmed lineups and the
injury report give at lock. Graded off nba.com's box score (DNP = void).

    python3 season_backtest.py pbp_dir sd_dir odds_2026-10-20.psv.gz 2026-10-20 2026-10-25 out.json
"""
import datetime, glob, gzip, json, os, sys
from collections import defaultdict
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
import nba_threes as T
import nba_nbacom as N
from boxlib import minutes_of

PBP, SD, ODDS, D0, D1, OUT = sys.argv[1:7]
BPTEAM = {'UTH': 'UTA', 'NOR': 'NOP', 'NO': 'NOP', 'PHO': 'PHX', 'BRK': 'BKN', 'GS': 'GSW', 'NY': 'NYK', 'SA': 'SAS', 'WSH': 'WAS', 'CHO': 'CHA'}

# ---- history replay (identical to seed_state.py) ----
games, names = {}, {}
for f in sorted(glob.glob(os.path.join(SD, '**', 'shotdetail_*.csv'), recursive=True)):
    d = pd.read_csv(f, usecols=['GAME_ID', 'GAME_DATE', 'HTM', 'VTM', 'PLAYER_ID', 'PLAYER_NAME'], low_memory=False)
    for gid, gd, h, v in d.drop_duplicates('GAME_ID')[['GAME_ID', 'GAME_DATE', 'HTM', 'VTM']].itertuples(index=False):
        s = str(int(gd)); games[int(gid)] = (f'{s[:4]}-{s[4:6]}-{s[6:]}', h, v)
    for pid, nm in d.drop_duplicates('PLAYER_ID')[['PLAYER_ID', 'PLAYER_NAME']].itertuples(index=False):
        names[int(pid)] = nm
rows = []
for f in sorted(glob.glob(os.path.join(PBP, '**', 'nbastatsv3_*.csv'), recursive=True)):
    cols = pd.read_csv(f, nrows=0).columns
    want = [c for c in ('gameId', 'personId', 'teamTricode', 'isFieldGoal', 'shotValue', 'shotResult', 'description', 'period',
                        'clock', 'actionType', 'subType', 'actionId', 'actionNumber', 'playerName') if c in cols]
    d = pd.read_csv(f, usecols=want, low_memory=False)
    d = d[(d.personId > 0) & d.teamTricode.notna() & (d.teamTricode != '')]
    three = (d.shotValue == 3) if 'shotValue' in d else d.description.astype(str).str.contains('3PT')
    d['a3'] = ((d.isFieldGoal == 1) & three).astype(int)
    d['m3'] = (d.a3 == 1) & (d.shotResult == 'Made')
    agg = d.groupby(['gameId', 'personId']).agg(team=('teamTricode', 'first'), att=('a3', 'sum'), made=('m3', 'sum')).reset_index()
    rows.append(agg.merge(minutes_of(d), on=['gameId', 'personId'], how='left'))
B = pd.concat(rows, ignore_index=True)
B = B[B.gameId.isin(games)]
B['date'] = B.gameId.map(lambda g: games[g][0])
B['opp'] = [games[g][2] if games[g][1] == t else games[g][1] for g, t in zip(B.gameId, B.team)]
st = T.State()
for date, day in B.sort_values(['date', 'gameId']).groupby('date', sort=True):
    st.update_day([dict(pid=str(r.personId), name=names.get(r.personId), team=r.team, opp=r.opp, gid=str(r.gameId),
                        tpa=int(r.att), tpm=int(r.made), mins=float(r.mins or 0), started=bool(r.started))
                   for r in day.itertuples(index=False)])
print('history through', date, flush=True)

# ---- prices ----
O = pd.read_csv(ODDS, sep='|', header=None, quoting=3,
                names=['date', 'event', 'home', 'visitor', 'bp', 'name', 'pos', 'team', 'book', 'line', 'side', 'cost', 'main'])
O = O[(O.book == T.FANDUEL) & (O.main == 1) & O.side.isin(['O', 'U'])]   # DTUNDER-2026-10-26: unders too
O['team'] = O.team.map(lambda t: BPTEAM.get(str(t), str(t)))

out = {}
d = datetime.date.fromisoformat(D0)
while d <= datetime.date.fromisoformat(D1):
    ds = d.isoformat()
    sb = [r for r in N.scoreboard(ds) if r[4]]
    boxes = {}
    for gid, away, home, *_ in sb:
        boxes[(away, home)] = (gid, N.parse(N.summary(gid))['box'])
    picks = []; unders = []
    od = O[O.date == ds]
    for (away, home), (gid, box) in boxes.items():
        played = {b['pid'] for b in box if b['played']}
        best = None
        for r in od[od.team.isin([away, home])].itertuples(index=False):
            T_ = r.team; opp = home if T_ == away else away
            pid = st.pid_of(r.name, T_)
            if not pid: continue
            b = next((x for x in box if x['pid'] == pid), None)
            started = bool(b and b['started'])
            regs = st.regulars(T_)
            tot = sum(st.att(x) for x in regs)
            miss = sum(st.att(x) for x in regs if x not in played)
            f = st.features(pid, opp, started, miss / tot if tot > 0 else 0.0)
            if not f: continue
            p, mu = T.p_over(f, float(r.line))
            if r.side == 'U':
                pu = 1 - p; evu = pu * T.dec(r.cost) - 1
                if float(r.line) >= T.U_LINE_MIN and pu >= T.U_P_MIN and evu >= T.U_EV_MIN:
                    pk = dict(name=r.name, code=T_, gmatch=f'{away}@{home}', line=float(r.line), kmin=int(float(r.line) + 0.5), side='U',
                              odds=int(r.cost), p=round(pu, 4), mu=round(mu, 2), ev=round(evu, 3), started=started,
                              status='confirmed', locked=True, final=True)
                    pk['dnp'] = not (b and (b['played'] or b['tpa'])); pk['made'] = b['tpm'] if b else None
                    pk['res'] = T.grade(pk); unders.append(pk)
                continue
            ev = p * T.dec(r.cost) - 1
            if ev >= T.EV_MIN and (best is None or ev > best['ev']):
                pk = dict(name=r.name, code=T_, gmatch=f'{away}@{home}', line=float(r.line), kmin=int(float(r.line) + 0.5),
                          odds=int(r.cost), p=round(p, 4), mu=round(mu, 2), ev=round(ev, 3), started=started,
                          status='confirmed', locked=True, final=True)
                pk['dnp'] = not (b and (b['played'] or b['tpa']))
                pk['made'] = b['tpm'] if b else None
                pk['res'] = T.grade(pk)
                best = pk
        if best: picks.append(best)
    picks = sorted(picks, key=lambda x: -x['ev'])[:T.MAX_NIGHT]
    on = {(x['gmatch'], x['name']) for x in picks}
    picks += sorted([u for u in unders if (u['gmatch'], u['name']) not in on], key=lambda x: -x['ev'])[:T.U_MAX_NIGHT]
    units = sum((T.dec(x['odds']) - 1) if x['res'] == 'win' else (-1 if x['res'] == 'loss' else 0) for x in picks)
    out[ds] = dict(picks=picks, units=round(units, 2))
    print(ds, len(sb), 'games', [(x.get('side', 'O'), x['name'], x['line'], x['odds'], x['made'], x['res']) for x in picks], f'{units:+.2f}u', flush=True)
    # learn the night
    day = []
    for (away, home), (gid, box) in boxes.items():
        for b in box:
            if b['played']:
                day.append(dict(pid=b['pid'], name=b['name'], team=b['team'], opp=home if b['team'] == away else away,
                                gid=gid, tpa=b['tpa'], tpm=b['tpm'], mins=b['mins'], started=b['started']))
    if day: st.update_day(day)
    d += datetime.timedelta(days=1)
json.dump(out, open(OUT, 'w'), indent=1)
tot = sum(v['units'] for v in out.values()); n = sum(len(v['picks']) for v in out.values())
w = sum(1 for v in out.values() for x in v['picks'] if x['res'] == 'win')
print(f'SEASON: {n} picks, {w} won, {tot:+.2f}u')
