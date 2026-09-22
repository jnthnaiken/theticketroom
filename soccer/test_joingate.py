#!/usr/bin/env python3
"""test_joingate.py -- JOINGATE-2026-09-22. The per-match xG join floor in soccer_mock.

WHY. coverage.json has stated this rule since 2026-09-08 and nothing enforced it:

    "a tie with one top-flight side joins xG at 73-87% ... two lower-division sides collapse to
     27%, and at 27% edge_z=0 means 'average' rather than 'unknown', so an unmodelled forward
     outranks a real one whose xG is genuinely below average. That is a price ranking wearing a
     model's clothes."

CUPSCOPE-2026-09-01's "at least one core-league side" is a PROXY for that sentence, evaluated in
slate_scan.js against ESPN club ids. It cannot be evaluated at all for a national team, which has
no club id -- which is what made internationals unshippable. MIN_JOIN checks the sentence itself.

WHAT IS PINNED, and it is the mechanism rather than any roster:

  1. a fixture BELOW the floor is dropped WHOLE -- every one of its players, not just the
     unjoined ones, because a half-modelled fixture is the exact failure above
  2. a fixture AT the floor is KEPT -- the comparison is `< MIN_JOIN`, and a boundary that
     drifts by one player is how a measured threshold turns into a different one
  3. the drop happens BEFORE z-scoring, so a dropped fixture cannot move any surviving
     player's mkt_z or edge_z
  4. a HEALTHY card is untouched -- this gate must be inert on a normal board, or it is not a
     gate, it is a redesign
  5. a slate where every fixture fails exits 3 rather than publishing an empty board

⚠️ RUN IT AGAINST THE PRE-GATE soccer_mock AND CASES 1/2/5 FAIL. Case 4 passes either way, which
is the point of including it: it is the control that says the gate is not doing anything else.

    python3 test_joingate.py
"""
import importlib.util, io, contextlib, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

# One understat row per name we want to JOIN. Eighteen columns, as soccer_mock parses them.
def xg_row(name, league='EPL', season='2026'):
    return (f'{league}|{season}|{name}|Someone|F|3|270|2|2|1.50|0.50|9|3.00|0.1666|'
            f'0.20|0.07|4|1.60')


def slate(matches, joined):
    """matches: {match: [priced names]}.  joined: set of names that get an xg.psv row."""
    ags = '\n'.join(f'{m}|{n}|2/1' for m, names in matches.items() for n in names) + '\n'
    xg = '\n'.join(xg_row(n) for n in joined) + '\n'
    fx = {'date': '2026-01-01', 'matches': {}}
    for i, m in enumerate(matches):
        fx['matches'][m] = {'home': 'A', 'away': 'B', 'kickoff': 1000 + i,
                            'league': 'EPL', 'espn': ['eng.1', str(i)]}
    import json
    return ags, xg, json.dumps(fx)


def run(matches, joined):
    """Import soccer_mock against a stub slate. It is a SCRIPT -- the tail needs a real pool and
    a node draft and will fail; everything this test asserts is bound long before that."""
    with tempfile.TemporaryDirectory() as tmp:
        ags, xg, fx = slate(matches, joined)
        for n, body in (('ags.psv', ags), ('xg.psv', xg), ('fixtures.json', fx)):
            open(os.path.join(tmp, n), 'w', encoding='utf-8').write(body)
        old = os.getcwd()
        os.chdir(tmp)
        spec = importlib.util.spec_from_file_location('sm_jg', os.path.join(HERE, 'soccer_mock.py'))
        m = importlib.util.module_from_spec(spec)
        code = None
        # ⚠️ fd-level capture, not contextlib.redirect_stdout. soccer_mock SHELLS OUT to
        # soccer_draft_cli.js, and a subprocess inherits fd 1 -- redirect_stdout only rebinds
        # sys.stdout inside this process, so the node draft prints a whole stub board straight
        # through the middle of the PASS lines. Dup the real fd instead.
        cap = os.path.join(tmp, '_out.txt')
        fd = os.open(cap, os.O_RDWR | os.O_CREAT)
        saved_out, saved_err = os.dup(1), os.dup(2)
        try:
            os.dup2(fd, 1); os.dup2(fd, 2)
            try:
                spec.loader.exec_module(m)
            except SystemExit as e:
                code = e.code
            except BaseException:
                pass
        finally:
            sys.stdout.flush(); sys.stderr.flush()
            os.dup2(saved_out, 1); os.dup2(saved_err, 2)
            os.close(saved_out); os.close(saved_err); os.close(fd)
            os.chdir(old)
        return m, open(cap, encoding='utf-8', errors='replace').read(), code


FAILS = []


def check(label, got, want):
    ok = got == want
    print(f'{"PASS" if ok else "FAIL"}  {label}')
    if not ok:
        FAILS.append(label)
        print(f'      got {got!r}, want {want!r}')


# ---------------------------------------------------------------------------------------
# 1 + 3 -- a fixture under the floor is dropped WHOLE, before scoring.
#          good 4/5 = 80% (keep) ; bad 2/5 = 40% (drop)
# ---------------------------------------------------------------------------------------
GOOD = ['G1', 'G2', 'G3', 'G4', 'G5']
BAD = ['B1', 'B2', 'B3', 'B4', 'B5']
m, out, code = run({'good': GOOD, 'bad': BAD}, {'G1', 'G2', 'G3', 'G4', 'B1', 'B2'})
if not hasattr(m, 'players'):
    raise SystemExit('soccer_mock never bound players -- test is invalid')

check('a 40% fixture is dropped', [d[0] for d in getattr(m, '_JOINDROP', [])], ['bad'])
check('...every one of its players goes, not just the unjoined ones',
      [p['name'] for p in m.players if p['match'] == 'bad'], [])
check('...including the two that DID join',
      {'B1', 'B2'} & {p['name'] for p in m.players}, set())
check('the 80% fixture is untouched',
      sorted(p['name'] for p in m.players if p['match'] == 'good'), GOOD)
check('...and it is the whole surviving board', len(m.players), 5)
check('the drop is announced with its number', 'JOINGATE dropped bad' in out and '40%' in out, True)

# ---------------------------------------------------------------------------------------
# 2 -- THE BOUNDARY. Exactly MIN_JOIN is KEPT. 3/5 = 60%.
# ---------------------------------------------------------------------------------------
m2, out2, _ = run({'edge': ['E1', 'E2', 'E3', 'E4', 'E5'], 'good': GOOD},
                  {'E1', 'E2', 'E3', 'G1', 'G2', 'G3', 'G4'})
check('MIN_JOIN is 60 (the measured floor)', m2.CFG.get('MIN_JOIN'), 60)
check('a fixture EXACTLY at the floor is kept', [d[0] for d in getattr(m2, '_JOINDROP', ['<no gate>'])], [])
check('...with all five of its players', len([p for p in m2.players if p['match'] == 'edge']), 5)

# one player worse -- 2/5 = 40% -- and the same fixture goes
m3, out3, _ = run({'edge': ['E1', 'E2', 'E3', 'E4', 'E5'], 'good': GOOD},
                  {'E1', 'E2', 'G1', 'G2', 'G3', 'G4'})
check('one join worse and it drops', [d[0] for d in getattr(m3, '_JOINDROP', [])], ['edge'])

# ---------------------------------------------------------------------------------------
# 4 -- THE CONTROL. A healthy card is inert. This passes against the pre-gate file too.
# ---------------------------------------------------------------------------------------
m4, out4, _ = run({'a': GOOD, 'b': BAD}, set(GOOD) | set(BAD))
check('a fully joined card drops nothing', [d[0] for d in getattr(m4, '_JOINDROP', [])], [])
check('...and keeps every player', len(m4.players), 10)
check('...and says nothing about dropping', 'JOINGATE dropped' in out4, False)

# ---------------------------------------------------------------------------------------
# 5 -- every fixture fails: refuse, do not publish an empty board.
# ---------------------------------------------------------------------------------------
m5, out5, code5 = run({'x': BAD, 'y': ['C1', 'C2', 'C3', 'C4', 'C5']}, {'B1', 'C1'})
check('a slate with no admissible fixture exits 3', code5, 3)
check('...and says so rather than printing a board',
      'JOINGATE dropped EVERY fixture' in out5, True)

print()
if FAILS:
    print(f'{len(FAILS)} FAILED')
    sys.exit(1)
print('ALL GREEN -- a fixture the model cannot see does not reach the pool, and a healthy card '
      'is untouched')
