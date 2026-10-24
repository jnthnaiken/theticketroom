"""BBTUNE moons: anchors fixed at current rules; moon settings chosen walk-forward (2021..S-1), played blind in S."""
import itertools, collections
from tune import days, NIGHTS, pool, moons, rr
grid = [(pa, lg, df) for pa in (1, 2, 3) for lg in (3, 4, 5) for df in (1, 2, 3) if df <= lg - 1]
U = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0.0]))
for k in NIGHTS:
    P = pool(days[k], 0.75, 4, None, None)
    for s in grid:
        for m in moons(P, 4, *s):
            u, st = rr(m, 0.10); r = U[s][k[0]]; r[0] += u; r[1] += st
CUR = (2, 4, 2)
line = lambda s: ' '.join(f'{S%100}:{U[s][S][0]:+.0f}' for S in range(2021, 2026))
print('current', CUR, line(CUR))
wf = st = 0.0
for S in range(2022, 2026):
    best = max(grid, key=lambda s: sum(U[s][T][0] for T in range(2021, S)))
    wf += U[best][S][0]; st += U[best][S][1]
    print(f'  {S}: chosen {best} (per anchor, legs, differ) -> {U[best][S][0]:+.0f}u')
c = sum(U[CUR][S][0] for S in range(2022, 2026)); cs = sum(U[CUR][S][1] for S in range(2022, 2026))
print(f'MOONS walk-forward tuned 2022-25: {wf:+.0f}u ({wf/st:+.1%}) | current same seasons: {c:+.0f}u ({c/cs:+.1%})')
for s in sorted(grid, key=lambda s: -sum(U[s][T][0] for T in range(2021, 2026)))[:6]: print('   hindsight', s, line(s))
