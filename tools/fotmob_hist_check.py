"""XGFOTMOB check: FotMob current-season history vs the understat base's 2026 rows (to 2026-09-16), same matches."""
import sys, pandas as pd
bt = pd.read_csv(f'{sys.argv[1]}/team_matches.csv.gz'); bp = pd.read_csv(f'{sys.argv[1]}/player_matches.csv.gz')
ft = pd.read_csv(f'{sys.argv[2]}/team_matches.csv.gz'); fp = pd.read_csv(f'{sys.argv[2]}/player_matches.csv.gz')
b26 = bt[bt.season == 2026]
print('fotmob team rows', len(ft), 'player rows', len(fp), 'dates', ft.date.min(), '..', ft.date.max())
print('synthetic pids', (fp.pid >= 10_000_000).mean().round(3), ' positions', fp.position.value_counts().to_dict())
m = b26.merge(ft, on=['date', 'team', 'h_a'], suffixes=('_u', '_f'))
print('team-match rows matched to understat by date+club+side:', len(m), 'of', len(b26), 'understat 2026 rows')
if len(m):
    print('  team xG corr', round(m.xG_u.corr(m.xG_f), 3), ' npxG corr', round(m.npxG_u.corr(m.npxG_f), 3), ' mean xG u/f', round(m.xG_u.mean(), 3), round(m.xG_f.mean(), 3),
          ' goals agree', round((m.scored_u == m.scored_f).mean(), 3))
pb = bp[bp.season == 2026]
mm = pb.merge(fp, on=['pid', 'date'], suffixes=('_u', '_f'))
print('player-match rows matched by pid+date:', len(mm), 'of', len(pb), 'understat rows')
if len(mm):
    print('  minutes agree within 5', round(((mm.time_u - mm.time_f).abs() <= 5).mean(), 3), ' goals agree', round((mm.goals_u == mm.goals_f).mean(), 3),
          ' npxG corr', round(mm.npxG_u.corr(mm.npxG_f), 3), ' shots corr', round(mm.shots_u.corr(mm.shots_f), 3))
print('unmapped club names:', sorted(set(ft.team) - set(bt[bt.season >= 2025].team))[:20])
