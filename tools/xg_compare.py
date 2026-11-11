"""XGFOTMOB-2026-11-11 check: FotMob-built xg.psv rows vs the last understat rows (11-08 slate), same players."""
import sys, unicodedata, re, statistics as S
def nk(s): s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower(); return re.sub(r'[^a-z ]', ' ', s).split()
def load(p):
    D = {}
    for l in open(p, encoding='utf-8'):
        a = l.rstrip('\n').split('|')
        if len(a) == 18: D[(a[0], a[1], ' '.join(nk(a[2])))] = a
    return D
U, F = load(sys.argv[1]), load(sys.argv[2])
srcF = {k: v for k, v in F.items() if k not in U or v != U.get(k)}
for lg in ('EPL', 'La_liga', 'Serie_A', 'Bundesliga', 'Ligue_1'):
    for season in ('2025', '2026'):
        fk = [k for k in F if k[0] == lg and k[1] == season]; uk = [k for k in U if k[0] == lg and k[1] == season]
        both = [k for k in fk if k in U]
        if not both: print(lg, season, 'fotmob', len(fk), 'understat', len(uk), 'overlap 0'); continue
        dm = [int(F[k][6]) - int(U[k][6]) for k in both]
        xs = [(float(U[k][9]), float(F[k][9])) for k in both if int(U[k][6]) >= 450]
        r = S.correlation([a for a, b in xs], [b for a, b in xs]) if len(xs) > 5 else float('nan')
        ratio = sum(b for a, b in xs) / max(sum(a for a, b in xs), 1e-9)
        team_same = sum(F[k][3] == U[k][3] for k in both) / len(both)
        print(f'{lg:10s} {season} fotmob {len(fk):4d} understat {len(uk):4d} overlap {len(both):4d} | npxG corr {r:.3f} total ratio {ratio:.2f} | '
              f'minutes diff median {S.median(dm):+.0f} | team spelled the same {team_same:.0%}')
