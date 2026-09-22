#!/usr/bin/env python3
"""test_anchorcap.py -- ANCHORCAP-2026-09-22. A bat we cannot rank must not hold an anchor seat.

WHY THIS RULE EXISTS. `claude/backtest15-priceband-2026-09-13.md` is the only price study this
project has run against REAL posted odds -- 17,932 priced bats over 80 slates. It held price
constant and asked whether our top half out-hits our bottom half:

    +450-550   +3.13pp        +650-750   -0.14pp   (n_bot 932)
    +550-650   +2.19pp        +750-850   -0.11pp   (n_bot 1,683)

Zero, twice. Above +850 the test cannot run at all -- our top half holds 68 bats, then 25, i.e.
we essentially never rank a +900 bat highly, so every +900 seat is taken on price alone. +650 is
where the measured ability to RANK stops. An anchor rides two moons AND a builder, so it is the
most leveraged seat on the board and the one that should be inside the skill band.

LEGS ARE DELIBERATELY NOT CAPPED. `claude/moon-legprice-2026-08-24.md` killed every leg-price
rule -- the apparent +350 cliff was role composition, not a price effect -- and nothing has
reopened it. This test asserts that asymmetry so a future session does not "tidy it up".

⚠️ THE OTHER STUDY DISAGREES, AND IT IS NOT THE ONE WE FOLLOW. `claude/daily15-2026-09-13.md`
crowned an anchor band of +300..+1150 across 2,604 slates. It priced off a SYNTHETIC book, and
its own doc says so: "picking on our score while pricing off a second noisy model manufactures
edge that a real market would never hand over." Where a synthetic-price study and a real-price
study disagree, the real one wins. That is the whole reason this file names both.

WHAT IT GUARDS
  1. the knob exists, in board_config.json AND boardcfg.DEFAULTS, and they agree
  2. BOTH drafters read it -- BOARDCFG-2026-09-13 exists because index.html and
     assemble_tickets.py have silently drifted before (CHALK_N was 0 in one and 4 in the other)
  3. the behaviour, on pinned committed slates: no anchor above the cap
  4. the control: 2026-06-18 shipped FIVE anchors above the cap, so this suite fails without
     the fix rather than passing vacuously

    python3 test_anchorcap.py
"""
import copy, importlib.util, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def check(ok, label, detail=''):
    (print if ok else FAILS.append)(f"  {'ok  ' if ok else 'FAIL'} {label}" + (f"   {detail}" if detail else ''))
    if not ok:
        print(f"  FAIL {label}" + (f"   {detail}" if detail else ''))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


print('ANCHORCAP-2026-09-22 -- anchors stay inside the band where the model can rank\n')

# ---- 1. the knob -------------------------------------------------------------------------
cfg_json = json.load(open(os.path.join(HERE, 'board_config.json')))
boardcfg = load('boardcfg', 'boardcfg.py')
CAP = cfg_json.get('ANCHOR_MAX_ODDS')

check(CAP is not None, 'board_config.json declares ANCHOR_MAX_ODDS', f'= {CAP}')
check(boardcfg.DEFAULTS.get('ANCHOR_MAX_ODDS') == CAP,
      'boardcfg.DEFAULTS agrees with board_config.json',
      f"DEFAULTS={boardcfg.DEFAULTS.get('ANCHOR_MAX_ODDS')} config={CAP}")
check('ANCHOR_MAX_ODDS' in boardcfg._INT, 'ANCHOR_MAX_ODDS is coerced to int by boardcfg')
check(isinstance(CAP, int) and 100 < CAP < 5000, 'the cap is a sane American price', str(CAP))

# ---- 2. BOTH drafters read it ------------------------------------------------------------
html = open(os.path.join(HERE, 'index.html'), encoding='utf-8').read()
atpy = open(os.path.join(HERE, 'assemble_tickets.py'), encoding='utf-8').read()

m = re.search(r"""cfg\(\s*['"]ANCHOR_MAX_ODDS['"]\s*,\s*([0-9]+)\s*\)""", html)
check(bool(m), 'index.html reads ANCHOR_MAX_ODDS through cfg()')
check(bool(m) and int(m.group(1)) == CAP,
      'index.html fallback literal equals board_config.json',
      f"html={m.group(1) if m else None} config={CAP}")
check('ANCHOR_MAX_ODDS' in atpy and '_CFG.ANCHOR_MAX_ODDS' in atpy,
      'assemble_tickets.py reads _CFG.ANCHOR_MAX_ODDS')
# the client must apply it where candA is built, not merely declare it
cand = html[html.find('candA=[]'):html.find('candA=[]') + 2500]
check('ANCHOR_MAX_ODDS' in cand and 'byG[g]=byG[g]||[]' in cand,
      'index.html applies the cap in the candA (anchor candidate) filter')

# ---- 3 + 4. behaviour, on pinned committed slates ----------------------------------------
at = load('assemble_tickets', 'assemble_tickets.py')

# 2026-06-18 is the control: it shipped five anchors above +650.
# 2026-09-22 is today's slate: Abimelec Ortiz anchored at +775.
PINNED = ['2026-06-18', '2026-06-19', '2026-08-17', '2026-09-20', '2026-09-22']
control_had_violations = 0

for date in PINNED:
    path = os.path.join(HERE, f'D_{date}.json')
    if not os.path.exists(path):
        print(f"  skip  D_{date}.json not in the repo")
        continue
    D = json.load(open(path))
    P = D.get('players') or {}

    shipped = []
    for t in (D.get('tickets') or []):
        a = t.get('anchor')
        if a and a not in shipped:
            shipped.append(a)
    over_before = [(a, (P.get(a) or {}).get('odds')) for a in shipped
                   if (P.get(a) or {}).get('odds') and (P[a]['odds'] > CAP)]
    control_had_violations += len(over_before)

    try:
        out = at.assemble(copy.deepcopy(D))
    except Exception as e:                                    # a pinned board that will not assemble is itself a failure
        check(False, f'{date}: assemble() ran', f'{type(e).__name__}: {e}')
        continue

    tickets = out.get('tickets') if isinstance(out, dict) else out
    anchors = []
    for t in (tickets or []):
        a = t.get('anchor')
        if a and a not in anchors:
            anchors.append(a)
    over = [(a, (P.get(a) or {}).get('odds')) for a in anchors
            if (P.get(a) or {}).get('odds') and P[a]['odds'] > CAP]

    check(not over, f'{date}: no anchor above +{CAP} after the fix',
          '; '.join(f'{n} {o}' for n, o in over))
    print(f"        {date}: {len(anchors)} anchors, "
          f"was {len(over_before)} over the cap as shipped"
          + (f" ({', '.join(f'{n} {o}' for n, o in over_before)})" if over_before else ''))

check(control_had_violations > 0,
      'the control bites: the pinned slates DID ship anchors above the cap before this fix',
      f'{control_had_violations} of them')

print()
if FAILS:
    print(f"{len(FAILS)} FAILURE(S)")
    sys.exit(1)
print('all assertions passed')
