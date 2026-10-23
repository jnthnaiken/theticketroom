"""Build per-game records from nbastatsv3 PBP + shotdetail (dates, full names). -> games.json"""
import json, re, sys, glob
import pandas as pd

def clock_sec(c):
    m = re.match(r'PT(\d+)M([\d.]+)S', str(c))
    return int(m.group(1)) * 60 + float(m.group(2)) if m else None

names, dates = {}, {}
for f in sorted(glob.glob('sd/shotdetail_*.csv')):
    d = pd.read_csv(f, usecols=['GAME_ID', 'PLAYER_ID', 'PLAYER_NAME', 'GAME_DATE', 'HTM', 'VTM'])
    for pid, nm in zip(d.PLAYER_ID, d.PLAYER_NAME):
        names[int(pid)] = nm
    g = d.drop_duplicates('GAME_ID')
    for gid, dt, h, v in zip(g.GAME_ID, g.GAME_DATE, g.HTM, g.VTM):
        dates[int(gid)] = (str(dt), h, v)
print('names', len(names), 'dated games', len(dates), file=sys.stderr)

out, bad = [], {'nojump': 0, 'starters': 0, 'nodate': 0}
for f in sorted(glob.glob('pbp/nbastatsv3_*.csv')):
    season = int(re.search(r'(\d{4})', f).group(1))
    d = pd.read_csv(f, low_memory=False)
    d = d[d.gameId.astype(str).str.startswith('2')]          # regular season (gameId 2YY#####)
    d = d.sort_values(['gameId', 'actionNumber'])
    for gid, g in d.groupby('gameId', sort=False):
        gid = int(gid)
        if gid not in dates: bad['nodate'] += 1; continue
        date, H, V = dates[gid]
        pl = g[(g.personId > 0) & g.teamTricode.notna() & (g.teamTricode != '')]
        team_pid = {}
        for pid, tt, nm in zip(pl.personId, pl.teamTricode, pl.playerName):
            team_pid.setdefault(tt, {})[int(pid)] = str(nm)
        if H not in team_pid or V not in team_pid: continue
        fullname = lambda pid, sur: names.get(pid, sur)
        def by_sur(team, sur):
            sur = str(sur).strip()
            c = [p for p, s in team_pid.get(team, {}).items() if s == sur]
            return c[0] if len(c) == 1 else None
        q1 = g[g.period == 1]
        # starters
        starters = {}
        for T in (H, V):
            seen_in, st = set(), []
            for at, pid, tt, desc in zip(q1.actionType, q1.personId, q1.teamTricode, q1.description):
                if tt != T: continue
                if at == 'Substitution':
                    m = re.match(r'SUB:\s*(.+?)\s+FOR\s+(.+)$', str(desc))
                    if m:
                        inc = by_sur(T, m.group(1))
                        if inc: seen_in.add(inc)
                    if pid > 0 and int(pid) not in seen_in and int(pid) not in st: st.append(int(pid))
                    continue
                if pid > 0 and int(pid) in team_pid[T] and int(pid) not in seen_in and int(pid) not in st:
                    st.append(int(pid))
            starters[T] = st[:5] if len(st) >= 5 else st
        if any(len(starters[T]) != 5 for T in (H, V)):
            bad['starters'] += 1; continue
        # jump ball
        jumpers, tip = None, None
        jb = q1[q1.actionType == 'Jump Ball'].head(1)
        if len(jb):
            r = jb.iloc[0]
            m = re.match(r'Jump Ball\s+(.+?)\s+vs\.?\s+(.+?):\s*Tip to\s+(.+)$', str(r.description))
            if m and r.personId > 0:
                a_pid, a_t = int(r.personId), r.teamTricode
                b_t = V if a_t == H else H
                b_pid = by_sur(b_t, m.group(2))
                z = m.group(3).strip()
                zt = [T for T in (H, V) if by_sur(T, z)]
                if b_pid:
                    hj, aj = (a_pid, b_pid) if a_t == H else (b_pid, a_pid)
                    jumpers = (fullname(hj, team_pid[H].get(hj)), fullname(aj, team_pid[V].get(aj)))
                if len(zt) == 1: tip = zt[0]
        if not jumpers: bad['nojump'] += 1
        fg = g[(g.isFieldGoal == 1) & (g.personId > 0)]
        fga, fgm, efga, tfirst = {}, {}, {}, {}
        fb, fbT = None, None
        for per, clk, pid, tt, res in zip(fg.period, fg.clock, fg.personId, fg.teamTricode, fg.shotResult):
            nm = fullname(int(pid), team_pid.get(tt, {}).get(int(pid)))
            fga[nm] = fga.get(nm, 0) + 1
            if res == 'Made':
                fgm[nm] = fgm.get(nm, 0) + 1
                if fb is None: fb, fbT = nm, tt
            if per == 1 and (clock_sec(clk) or 0) >= 420: efga[nm] = efga.get(nm, 0) + 1
            if tt not in tfirst: tfirst[tt] = nm
        q1s = q1[(q1.isFieldGoal == 1) & (q1.personId > 0)]
        shots = []
        for clk, pid, tt, res, dist, val, desc in zip(q1s.clock, q1s.personId, q1s.teamTricode, q1s.shotResult, q1s.shotDistance if 'shotDistance' in q1s else [0]*len(q1s), q1s.shotValue if 'shotValue' in q1s else [3 if '3PT' in str(x) else 2 for x in q1s.description], q1s.description):
            el = 720 - (clock_sec(clk) or 0)
            if el > 480: break
            nm = fullname(int(pid), team_pid.get(tt, {}).get(int(pid)))
            m = re.search(r'\((\S.*?) \d+ AST\)', str(desc)); ast = None
            if m:
                ap = by_sur(tt, m.group(1));
                if ap: ast = fullname(ap, team_pid[tt][ap])
            shots.append([round(el, 1), tt, nm, int(dist or 0), 1 if res == 'Made' else 0, int(val or 0), ast])
        team_of = {}
        for T in (H, V):
            for pid, s in team_pid[T].items(): team_of[fullname(pid, s)] = T
        out.append({'gid': gid, 'season': season, 'date': date, 'H': H, 'V': V,
                    'starters': {T: [fullname(p, team_pid[T][p]) for p in starters[T]] for T in (H, V)},
                    'jumpers': jumpers, 'tip': tip, 'fb': fb, 'fbT': fbT, 'fga': fga, 'fgm': fgm, 'efga': efga,
                    'tfirst': tfirst, 'team_of': team_of, 'shots': shots})
    print(f, len(out), bad, file=sys.stderr)
out.sort(key=lambda x: (x['date'], x['gid']))
json.dump(out, open('games2.json', 'w'))
print('games', len(out), bad)
