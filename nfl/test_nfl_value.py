#!/usr/bin/env python3
"""VALUESINGLES-2026-09-27 -- the football value rule, tested with a cached history file (no network).

  * p_value is the MEAN of the board's model and the history model.
  * <= +400: any non-QB whose p_value x decimal > 1 is picked (core).
  * >  +400: WR/TE only, best LONGSHOT_CAP by p_value -- never a longshot RB.
  * a man ruled out is never picked; a failed history build falls back to p_model alone.
Run: python3 test_nfl_value.py
"""
import json, os, subprocess, sys, tempfile
H = os.path.dirname(os.path.abspath(__file__))
FAIL = []
def chk(ok, msg):
    print(('PASS  ' if ok else 'FAIL  ') + msg)
    if not ok: FAIL.append(msg)

def row(name, team, pos, odds, pm, **k):
    r = dict(name=name, team=team, pos=pos, odds=odds, p_model=pm, match='A-at-B'); r.update(k); return r

scored = [
    row('Core Hit', 'KC', 'RB', 200, 0.40),        # 0.40*3 = 1.2 > 1 -> core
    row('Core Miss', 'KC', 'WR', 200, 0.30),       # 0.30*3 = 0.9 -> no
    row('Fav Hit', 'BUF', 'RB', -110, 0.56),       # 0.56*1.909 = 1.07 -> core
    row('Long RB', 'BUF', 'RB', 800, 0.20),        # value, but a longshot RB -> never
    row('Long TE1', 'BUF', 'TE', 600, 0.30),
    row('Long WR2', 'KC', 'WR', 900, 0.25),
    row('Long TE3', 'KC', 'TE', 700, 0.20),
    row('Long WR4', 'KC', 'WR', 500, 0.19),
    row('Long WR5', 'KC', 'WR', 1200, 0.10),       # 5th best longshot by p -> cut by the cap
    row('Out Man', 'KC', 'TE', 200, 0.60, out=True),
    row('QB Guy', 'KC', 'QB', 200, 0.60),
]
d = tempfile.mkdtemp()
sp, fx, cache = os.path.join(d, 's.json'), os.path.join(d, 'fx.json'), os.path.join(d, 'p_hist.json')
json.dump({'season': 2026, 'matches': {}}, open(fx, 'w'))
# history model agrees exactly with p_model except for one man, where it halves the value
json.dump({'core miss|KC': 0.30, 'core hit|KC': 0.40, 'fav hit|BUF': 0.56, 'long te1|BUF': 0.10}, open(cache, 'w'))
json.dump(scored, open(sp, 'w'))
r = subprocess.run([sys.executable, os.path.join(H, 'nfl_value.py'), sp, fx, '--date', '2026-09-27', '--cache', cache],
                   capture_output=True, text=True)
chk(r.returncode == 0, 'runs off the cache with no network')
S = {s['name']: s for s in json.load(open(sp))}
pick = {n for n, s in S.items() if not s['novalue']}
chk(abs(S['Long TE1']['p_value'] - 0.20) < 1e-9, 'p_value = mean(p_model, p_hist)')
chk(S['Long WR2']['p_hist'] is None and S['Long WR2']['p_value'] == 0.25, 'no history row -> p_model alone')
chk({'Core Hit', 'Fav Hit'} <= pick and 'Core Miss' not in pick, 'core: value at <=+400 picked, no value dropped')
chk('Long RB' not in pick, 'never a longshot RB')
longs = {n for n in pick if S[n]['value_kind'] == 'longshot'}
chk(len(longs) <= 4, 'longshots capped at 4')
chk('Long WR5' not in pick and 'Long WR2' in pick, 'the cap keeps the best longshots by p_value')
chk('Out Man' not in pick and 'QB Guy' not in pick, 'out men and QBs never picked')
print('ALL GREEN -- value singles: core at <=+400, capped WR/TE longshots, never a longshot RB' if not FAIL else f'{len(FAIL)} FAILURE(S)')
sys.exit(1 if FAIL else 0)
