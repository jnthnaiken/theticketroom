"""test_nfl_kingfreeze.py -- KINGFREEZE-2026-10-20: the King of the End Zone pick is frozen at kickoff."""
import datetime as dt, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nfl_payload import freeze_longtd
fail = 0
def chk(l, ok, d=None):
    global fail
    print(('PASS  ' if ok else 'FAIL  ') + l)
    if not ok: fail += 1; print('      ', d)
M = {'WAS-at-SF': {'kickoff': 20 * 60 + 15}}
ev = [{'match': 'WAS-at-SF', 'game': 1, 'picks': [{'name': 'Mike Evans', 'crown': True}]}]
ki = [{'match': 'WAS-at-SF', 'game': 1, 'picks': [{'name': 'George Kittle', 'crown': True}]}]
prior = {'meta': {'date': '2026-10-19', 'longtd': ev}}
at = lambda h, m, day=19: dt.datetime(2026, 10, day, h, m, tzinfo=dt.timezone.utc)
crown = lambda L: [p['name'] for p in L[0]['picks'] if p['crown']][0]
chk('before kickoff: the recompute stands (a pre-game scratch can still move the crown)',
    crown(freeze_longtd(ki, prior, '2026-10-19', M, now=at(22, 0))) == 'George Kittle')
chk('after kickoff: the prior crown is held (Evans, 10-19)',
    crown(freeze_longtd(ki, prior, '2026-10-19', M, now=at(2, 1, 20))) == 'Mike Evans')
chk('after kickoff with nothing computed: still held', crown(freeze_longtd(None, prior, '2026-10-19', M, now=at(2, 1, 20))) == 'Mike Evans')
chk('a prior board from another date is ignored',
    crown(freeze_longtd(ki, {'meta': {'date': '2026-10-12', 'longtd': ev}}, '2026-10-19', M, now=at(2, 1, 20))) == 'George Kittle')
print(f'\n{fail} FAILED' if fail else '\nall KINGFREEZE checks pass'); sys.exit(1 if fail else 0)
