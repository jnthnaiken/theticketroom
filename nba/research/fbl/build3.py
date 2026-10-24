"""FBL-REBUILD: extra per-game facts from nbastatsv3 PBP, keyed by gameId, to sit beside fbr/games2.json.
Per game: made FGs by method per player (dunk/layup/hook/jump2/three), FTM, points in the first 3:00
(incl FT), first team basket (first made FG per team) and its method, first FG method of the game."""
import pandas as pd, re, json, sys, glob
from multiprocessing import Pool

def clock_sec(c):
    m = re.match(r'PT(\d+)M([\d.]+)S', str(c))
    return int(m.group(1)) * 60 + float(m.group(2)) if m else None

def method(sub, val):
    s = str(sub).lower()
    if val == 3 or '3pt' in s: return 'three'
    if 'dunk' in s: return 'dunk'
    if 'layup' in s or 'finger roll' in s: return 'layup'
    if 'hook' in s: return 'hook'
    return 'jump2'

def one(f):
    season = int(re.search(r'(\d{4})', f).group(1))
    d = pd.read_csv(f, low_memory=False, usecols=['gameId','actionNumber','clock','period','teamTricode','personId','playerName',
                                                    'shotResult','isFieldGoal','actionType','subType','description','shotDistance','pointsTotal'])
    d = d[d.gameId.astype(str).str.startswith('2')].sort_values(['gameId','actionNumber'])
    out = {}
    for gid, g in d.groupby('gameId', sort=False):
        made, ftm, f3, tfb, tfbm = {}, {}, {}, {}, {}
        first_any = None
        for per, clk, pid, nm, tt, res, fg, at, sub, desc in zip(g.period, g.clock, g.personId, g.playerName, g.teamTricode,
                                                                 g.shotResult, g.isFieldGoal, g.actionType, g.subType, g.description):
            if not (pid and pid > 0) or not isinstance(tt, str): continue
            pid = int(pid)
            el = (per - 1) * 720 + 720 - (clock_sec(clk) or 0) if per <= 4 else 9999
            pts = 0
            if fg == 1 and res == 'Made':
                val = 3 if '3PT' in str(desc) else 2
                m = method(sub, val)
                made.setdefault(pid, {}); made[pid][m] = made[pid].get(m, 0) + 1
                pts = val
                if tt not in tfb: tfb[tt] = pid; tfbm[tt] = m
            elif at == 'Free Throw' and not str(desc).startswith('MISS'):
                ftm[pid] = ftm.get(pid, 0) + 1; pts = 1
            if pts:
                if first_any is None: first_any = (pid, tt, 'ft' if pts == 1 else None)
                if el <= 180: f3[pid] = f3.get(pid, 0) + pts
        out[int(gid)] = {'made': made, 'ftm': ftm, 'f3': f3, 'tfb': tfb, 'tfbm': tfbm, 'first_any': first_any}
    print(f, len(out), file=sys.stderr)
    return out

if __name__ == '__main__':
    R = {}
    with Pool(6) as p:
        for o in p.map(one, sorted(glob.glob('/home/claude/fbr/pbp/nbastatsv3_*.csv'))): R.update(o)
    json.dump({str(k): v for k, v in R.items()}, open('extra.json', 'w'))
    print('games', len(R))
