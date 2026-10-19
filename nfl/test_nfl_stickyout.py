"""STICKYOUT-2026-10-19: an out survives ESPN swapping its injury report for the inactives list."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl_injuries as I

fails = 0
def check(ok, what):
    global fails
    print(('PASS  ' if ok else 'FAIL  ') + what); fails += (not ok)

d = tempfile.mkdtemp()
board = os.path.join(d, 'b.json'); seed = os.path.join(d, 's.json')
json.dump({'players': {'Jacory Croskey-Merritt': {'code': 'WAS', 'team': 'Commanders', 'out': True, 'out_why': 'Out'}}}, open(board, 'w'))
json.dump({'outs': [{'name': 'Christian McCaffrey', 'team': 'SF', 'why': 'hand seed'}]}, open(seed, 'w'))

sc = [{'name': 'Jacory Croskey-Merritt', 'team': 'WAS'}, {'name': 'Christian McCaffrey', 'team': 'SF'},
      {'name': 'Stefon Diggs', 'team': 'SF'}]
got = I.carry_prior_outs(sc, 'x', board_paths=[board], seed_paths=[seed])
check(sc[0].get('out') is True, 'a man out on the prior board stays out when ESPN stops listing him')
check(sc[1].get('out') is True, 'a hand-seeded out is applied')
check(not sc[2].get('out'), 'nobody else is touched')
check(sorted(got) == ['Christian McCaffrey', 'Jacory Croskey-Merritt'], 'reports exactly the carried names')

sc = [{'name': 'Jacory Croskey-Merritt', 'team': 'SF'}]
I.carry_prior_outs(sc, 'x', board_paths=[board], seed_paths=['/nope'])
check(not sc[0].get('out'), 'matched by team, not by name alone')

sc = [{'name': 'Jacory Croskey-Merritt', 'team': 'WAS'}]
check(I.carry_prior_outs(sc, 'x', board_paths=['/nope'], seed_paths=['/nope']) == [] and not sc[0].get('out'),
      'no prior board and no seed: nothing changes')

print('ALL GREEN -- an out sticks for the slate' if not fails else f'{fails} FAILURE(S)')
sys.exit(1 if fails else 0)
