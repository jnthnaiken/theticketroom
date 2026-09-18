#!/usr/bin/env python3
"""
state.py — print what the board ACTUALLY ships, by reading the running source.

WHY THIS EXISTS (2026-09-13)
----------------------------
Four times in one day a session acted on a confident, wrong belief about this board:

  1. WRONGBASKET  — benchmarked `_SIG` from a project doc instead of from build15.py. Four
                    experiments and three docs were built on a basket that had not been live
                    for ten days.
  2. CAREERKEY    — trusted `_zhrc`'s WEIGHT (0.4489) as evidence the term was working. It was
                    None on all 419 bats; 55% of the basket was dark and nothing threw.
  3. EVDRAFT      — wrote a hand-maintained "CURRENT STATE" doc saying the board ranks on `_SIG`.
                    It ranks on EV and has since 2026-09-10. The doc was stale within hours of
                    being written, by its own author.
  4. GAMECAP      — trusted two source COMMENTS that each said the drafters shared GAME_CAP.
                    index.html said 6, assemble_tickets.py said 4, and had since 2026-08-18.
                    Found only by diffing the constants, which is now board_config.json's job.

Each was the same failure: a claim was trusted instead of checked. A hand-written state doc
cannot fix that, because a hand-written doc IS a claim. This script is not a claim -- it reads
the source and the last shipped board every time it runs.

    python3 state.py              # human-readable
    python3 state.py --md         # the markdown that becomes claude/CURRENT-STATE.md
    python3 state.py --check      # exit 1 if the live board disagrees with the code

RULE: never hand-edit claude/CURRENT-STATE.md. Regenerate it.
"""
import json, re, os, sys, glob, ast
from collections import Counter
import boardcfg

HERE = os.path.dirname(os.path.abspath(__file__))
def _p(*a): return os.path.join(HERE, *a)


def read(fn):
    with open(_p(fn), encoding='utf-8') as fh:
        return fh.read()


def build15():
    """Everything the scorer decides, read out of build15.py itself."""
    s = read('build15.py')
    out = {}
    m = re.search(r'^_SIG=(\[[^\]]*\])', s, re.M)
    out['SIG'] = ast.literal_eval(m.group(1)) if m else None
    m = re.search(r'^W_PSW=([0-9.]+)', s, re.M)
    out['W_PSW'] = float(m.group(1)) if m else None
    m = re.search(r"BOARD_MODEL\s*=\s*os\.environ\.get\(\s*'BOARD_MODEL'\s*,\s*'([a-z0-9_]+)'", s)
    out['BOARD_MODEL'] = m.group(1) if m else None
    for g in ('MIN_CARD_BIP', 'MIN_DMG_BIP', 'MIN_CAREER_G'):
        m = re.search(r'^%s\s*=\s*(\d+)' % g, s, re.M)
        if m: out[g] = int(m.group(1))
    return out


def client():
    """Draft + stake constants.

    BOARDCFG-2026-09-13: these are NOT read out of index.html any more. `board_config.json` owns
    them; build15.py stamps them into `D.meta.cfg`; index.html reads that. Scraping the HTML was
    how this function ALREADY lied once -- `\\bMOON_LEGS\\s*=\\s*(\\d+)` matched the string
    "MOON_LEGS=3" inside a PROSE COMMENT describing the CFGSCOPE bug, and --check duly reported
    that the 4-leg board was illegal. A regex over prose is a claim, not a fact; the config file
    is the fact. index.html's own literals are now only a fallback for archived boards, and
    `client_fallbacks()` below checks that they still agree.
    """
    out = {k: v for k, v in boardcfg.load(quiet=True).items() if not k.startswith('_')}
    m = re.search(r'MOON_LEGS:\s*(\d+)', read('soccer/soccer_draft.js'))
    out['SOCCER_MOON_LEGS'] = int(m.group(1)) if m else None
    # the two genuinely-dead literals still sitting in index.html, read where they live
    s = '\n'.join(l for l in read('index.html').split('\n') if not l.startswith('const D={'))
    for k in ('GATE_N', 'FLOOR'):
        m = re.search(r'\b%s\s*=\s*(\d+)\s*[,;]' % k, s)
        if m: out[k] = int(m.group(1))
    return out


def client_fallbacks():
    """Every `cfg('KEY', default)` literal in index.html — the archived-board fallback path.

    A board built before BOARDCFG has no `meta.cfg`, so these literals are what renders it. They
    must equal board_config.json or an archived board and a live board drift apart silently.
    Returns {key: [defaults seen]} so a key written twice with two different values is visible.
    """
    s = '\n'.join(l for l in read('index.html').split('\n') if not l.startswith('const D={'))
    out = {}
    for k, v in re.findall(r"""cfg\(\s*['"]([A-Z_0-9]+)['"]\s*,\s*([0-9.]+|true|false)\s*\)""", s):
        val = {'true': True, 'false': False}.get(v)
        if val is None: val = float(v) if '.' in v else int(v)
        out.setdefault(k, [])
        if val not in out[k]: out[k].append(val)
    return out


DOCS = ('README.md', 'HANDOFF.md')
# A line may state a knob's value only if it is marked as history. Two markers, both visible to a
# human reader, so the exemption is never invisible: a line inside the HANDOFF correction table
# (starts with '>'), or a line carrying one of these words, which is how this repo already writes
# about superseded doctrine.
_HIST = re.compile(r'\b(was|were|used to|historically|superseded|stale|old|until|then|'
                   r'no longer|raised|drift\w*|says|said|wrongly|instead of)\b', re.I)


def doc_numbers():
    """Knob values hard-coded into README.md / HANDOFF.md that disagree with board_config.json.

    WHY THIS IS A CHECK AND NOT A CONVENTION (BOARDCFG-2026-09-13): the convention "don't write
    numbers in prose" already existed in spirit and was broken everywhere. On the day this was
    written, README said `WIN=120` (it was 150) and HANDOFF stated a stale `GAME_CAP=4` in three
    separate places and a stale `CHALK_N=4` in two, five days to 26 days after each had changed.
    Prose is the one part of this repo nothing executes, so it is the one part that rots unseen.
    A line that legitimately discusses an old value keeps it -- just say `was`, `used to`, or put
    it in a correction table, which is how a human tells the difference too.
    """
    C = {k: v for k, v in boardcfg.load(quiet=True).items() if not k.startswith('_')}
    bad = []
    for f in DOCS:
        try: s = read(f)
        except Exception: continue
        for ln, line in enumerate(s.split('\n'), 1):
            if line.lstrip().startswith('>') or _HIST.search(line):
                continue
            for k, v in C.items():
                if k == 'RR_UNIT' or isinstance(v, bool):
                    continue
                for m in re.finditer(r'`?\b%s\b`?\s*(?:=|is|of|at)\s*`?(\d+(?:\.\d+)?)' % k, line):
                    if float(m.group(1)) != float(v):
                        bad.append(f'{f}:{ln} states {k} = {m.group(1)}; board_config.json says {v}')
    return bad


def cfg_canon(v):
    """A config value reduced to what it MEANS, so two spellings of one number compare equal.

    JSONKEYS-2026-09-18. `meta.cfg` has been through JSON and board_config.json has been through
    boardcfg.load(), so the same config compared UNEQUAL on two spellings JSON cannot carry:
    RR_UNIT's keys are ints in the loader and strings in the board ({2: 2.0} vs {'2': 2}), and an
    int and a float of the same value are one number in JSON and two in Python. EVERY board built
    since BOARDCFG therefore reported "board was built with a different config" -- a permanent
    false alarm standing in front of the test suite, which is how a reader is taught to ignore a
    red check.

    Keys as strings, numbers as floats, and bools TAGGED -- `False == 0` in Python and a config
    that flipped a flag to a number is a real difference, not a spelling.
    """
    if isinstance(v, bool):
        return ('bool', v)
    if isinstance(v, dict):
        return {str(k): cfg_canon(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [cfg_canon(x) for x in v]
    return float(v) if isinstance(v, (int, float)) else v


def ranks_like(rows, key):
    """Does `TOTAL` rank the field the way `key` does? Walk the rows in `key` order and assert
    TOTAL never goes UP. Module-level and not a closure so test_statecheck.py can drive it.

    TIEBREAK-2026-09-18. The question used to be asked as `top 10 by TOTAL == top 10 by ev`,
    compared as ORDERED NAME LISTS, and that is a flake rather than a check. `TOTAL` ships
    rounded to one decimal while `ev` carries four, so two bats whose EV differs in the fourth
    decimal land on ONE TOTAL and the two sortings order that tie differently -- nothing has
    drifted, the board ranks on EV exactly as it claims. Measured on 2026-09-17: Isaac Paredes
    (ev -0.1814) and Wilyer Abreu (-0.1813) both at TOTAL 137.6, so `--check` reported
    "BOARD_MODEL is ev_v1 but TOTAL does not rank like ev" and exited 1 -- which, because it runs
    BEFORE the suite in tests.yml, took the whole test job red on every commit until some later
    board happened not to tie. A check nobody can act on is a check everybody learns to ignore.

    Monotonicity is the honest form of the same question: ties are legal by construction, a real
    re-ranking is still caught, and it reads the WHOLE priced field rather than ten rows --
    strictly stronger than what it replaces. Checked against the eight archived boards
    09-10..09-17: zero inversions in any of them, including the 09-17 board the old rule failed.
    """
    s = sorted([r for r in rows if r.get(key) is not None], key=lambda r: -r[key])
    return all(s[i]['TOTAL'] >= s[i + 1]['TOTAL'] - 1e-9 for i in range(len(s) - 1))


def board():
    """The newest shipped board. This is the FACT the code's claims get checked against."""
    fs = sorted(glob.glob(_p('D_2026-*.json')))
    if not fs: return None
    d = json.load(open(fs[-1]))
    P, T = d.get('players') or {}, d.get('tickets') or []
    b = {'file': os.path.basename(fs[-1]), 'date': d.get('meta', {}).get('date'),
         'build': d.get('meta', {}).get('build'), 'model': d.get('meta', {}).get('model'),
         'cfg': d.get('meta', {}).get('cfg'),
         'nplayers': len(P), 'kinds': Counter(t.get('kind') for t in T),
         'shape': Counter((len(t.get('players') or []), t.get('kind')) for t in T),
         'rr': sorted({(t['rr'].get('risk'), t['rr'].get('struct')) for t in T if t.get('rr')})}
    # signal coverage -- a weight is a claim, a populated column is the fact
    cols = [k for k in (list(P.values())[0] if P else {}) if k.startswith('_z')]
    b['coverage'] = {k: sum(1 for r in P.values() if r.get(k) is not None) for k in sorted(cols)}
    # does TOTAL actually rank like EV? -- see ranks_like() above, TIEBREAK-2026-09-18
    pr = [r for r in P.values() if r.get('ev') is not None and r.get('TOTAL') is not None]
    if pr:
        b['ranks_like_ev'] = ranks_like(pr, 'ev')
        b['ranks_like_kas'] = ranks_like(pr, 'kas_v1_total')
        b['top'] = [r['nm'] for r in sorted(pr, key=lambda r: (-r['TOTAL'], -r['ev']))[:5]]
    return b


def ledger():
    try: s = json.load(open(_p('season.json')))
    except Exception: return None
    c = s.get('cats') or {}
    return {'since': s.get('since'), 'cats': c,
            'units': sum(v.get('units', 0) for v in c.values()),
            'staked': sum(v.get('staked', 0) for v in c.values()),
            'graded': sum(v.get('graded', 0) for v in c.values()),
            'won': sum(v.get('won', 0) for v in c.values()),
            'nights': len(s.get('graded_nights') or [])}


def combos(L):
    from itertools import combinations
    return [c for sz in range(2, L + 1) for c in combinations(range(L), sz)]


def markdown():
    B, C, D, L = build15(), client(), board(), ledger()
    o = []
    A = o.append
    A('# CURRENT STATE — the MLB board, as it actually ships')
    A('')
    A('> ## ⚠️ GENERATED FILE — do not hand-edit')
    A('>')
    A('> Produced by `state.py` in the repo, which reads `build15.py`, `board_config.json`,')
    A('> `index.html`, `soccer/soccer_draft.js`, the newest `D_<date>.json` and `season.json`.')
    A('> Every number below was read from the running source, not written down by anyone.')
    A('>')
    A('> **Regenerate it. Never edit it.** A hand-written state doc is a claim, and claims in this')
    A('> project have gone stale within hours of being written — see the failure log at the bottom.')
    A('>')
    A('> ```')
    A('> python3 state.py --md > /tmp/s.md     # then write it to claude/CURRENT-STATE.md')
    A('> python3 state.py --check             # exit 1 if the board and the code disagree')
    A('> ```')
    A('')
    A('## What ranks the board')
    A('')
    A(f"`BOARD_MODEL` defaults to **`{B['BOARD_MODEL']}`** (`build15.py`).")
    if D:
        A(f"The newest board (`{D['file']}`, built {D['build']}) carries `meta.model = {D['model']}`.")
        if D.get('ranks_like_ev') is not None:
            A('')
            A(f"- `TOTAL` never rises as `ev` falls (ranks like ev)  → **{D['ranks_like_ev']}**")
            A(f"- `TOTAL` never rises as `kas_v1_total` falls → **{D['ranks_like_kas']}**")
    A('')
    A('Three models run in sequence and each overwrites `TOTAL`. **The last one is the board.**')
    A('')
    A('| layer | inputs | lands in |')
    A('|---|---|---|')
    A('| `mkt50` | the `_SIG` blend below + market z | `total_mkt50` — kept, NOT ranked on |')
    A('| `kas_v1` | 17 `c_*` columns via `shadow_inputs.py`. No price, no career terms | `kas_v1_total` |')
    A('| **`ev_v1`** | logistic on `z(kas_v1)` + the market log-odds | **`TOTAL` = 100 + 30·z(EV)** |')
    A('')
    A('`build15.py`: *"Everything downstream (pool gate, strength, anchors, legs) ranks on that."*')
    A('EV is negative on essentially every bat — it ranks the least-bad bets, it does not find +EV ones.')
    A('')
    A('## `_SIG` — the mkt50 basket (NOT the live ranking)')
    A('')
    A('```python')
    A(f"W_PSW = {B['W_PSW']}")
    A('_SIG = ' + json.dumps(B['SIG']).replace('[[', '[(').replace(']]', ')]').replace('], [', '), ('))
    A('```')
    if B['SIG']:
        A('')
        A(f"{len(B['SIG'])} terms, sum {sum(w for _, w in B['SIG']):.4f}.")
    A('')
    A('It produces `total_mkt50`, is the `BOARD_MODEL=mkt50` revert path, and is the fail-safe if')
    A('`kas_v1` throws. **Work on `_SIG` does not move the live board while `ev_v1` is the model.**')
    A('')
    A('## Signal coverage on the newest board')
    A('')
    A('A weight is a claim. A populated column is the fact. `_zhrc` sat at 0/419 for a full day at a')
    A('fitted weight of 0.4489.')
    A('')
    if D:
        A('```')
        for k, v in D['coverage'].items():
            bar = '#' * int(30 * v / max(D['nplayers'], 1))
            flag = '   <-- DARK' if v == 0 else ''
            A(f"{k:8} {v:4}/{D['nplayers']:<4} {bar}{flag}")
        A('```')
    A('')
    A('## The board it actually shipped')
    A('')
    if D:
        A('```')
        A(f"{D['file']}   built {D['build']}   model {D['model']}")
        for (n, k), c in sorted(D['shape'].items(), key=lambda x: (-x[1], str(x[0]))):
            A(f"  {c:>2} x {k:<8} {n} leg{'s' if n != 1 else ''}")
        A(f"  round robins: {D['rr']}")
        A('```')
        A('')
        A(f"Top 5 by `TOTAL`: {', '.join(D['top'])}" if D.get('top') else '')
    A('')
    A('## Draft and stake constants — `board_config.json`')
    A('')
    A('**Python owns these. Edit `board_config.json`, nothing else.** `build15.py` stamps the whole')
    A('config into `D.meta.cfg` on every build and `index.html` reads it from there; the literals in')
    A('the HTML are only the fallback that renders boards archived before this existed, and')
    A('`state.py --check` fails if they drift from this table. `assemble_tickets.py` imports the')
    A('same file. Before BOARDCFG these lived in both the engine and the fallback drafter by hand,')
    A('and two of the ten had already diverged (`CHALK_N` 0 vs 4, `FLOOR` 41 vs 130).')
    A('')
    A('| knob | value | what it does |')
    A('|---|---|---|')
    _WHAT = {
        'Z_GATE': 'a bat must clear this many z above the pool mean to be draftable',
        'GAME_CAP': 'most bats one game may put in the pool (both lineups combined)',
        'RESERVE_GAME_CAP': 'tighter cap on one game when a moon reaches BELOW the gate into the reserve tier — NOT a stale GAME_CAP',
        'ANCH': 'anchors, and therefore builders',
        'ANCH_PER_GAME': 'most anchors from any one game',
        'MOONS_PER_ANC': 'moons built off each anchor → 4 x 2 = 8 moons',
        'MOON_LEGS': 'anchor + 3 partners',
        'SHORT_MOON_FLOOR': 'legs a moon falls back to when the slate cannot geometrically hold MOON_LEGS',
        'MOON_SLACK': 'ranks past the gate a moon may reach for a partner',
        'WIN': 'minutes: every leg of a moon must start inside one window this wide',
        'NIGHT_WIN': 'minutes after the last first pitch that the nightcap draws from',
        'LUNCH_CUT_MIN': 'minutes past midnight local — first pitch before this is lunch (17:00)',
        'CHALK_N': 'chalk bats barred from the pool — 0, the ban is off',
        'CHEF_TICKET': "Chef's Table — retired",
        'DINGERS': 'Dingers / Family Meal — retired',
    }
    for k in ('Z_GATE', 'GAME_CAP', 'RESERVE_GAME_CAP', 'ANCH', 'ANCH_PER_GAME', 'MOONS_PER_ANC', 'MOON_LEGS',
              'SHORT_MOON_FLOOR', 'MOON_SLACK', 'WIN', 'NIGHT_WIN', 'LUNCH_CUT_MIN', 'CHALK_N',
              'CHEF_TICKET', 'DINGERS'):
        if k in C: A(f"| `{k}` | `{C[k]}` | {_WHAT.get(k,'')} |")
    A('')
    A('Deliberately **not** in the config file, because a dead constant in an authoritative-looking')
    A('file is how it gets resurrected — these stay in `index.html`, marked dead:')
    A('')
    for k in ('GATE_N', 'FLOOR'):
        if k in C: A(f"- `{k} = {C[k]}` — declared, never read")
    A('- `FAM_CAP` — declared *after* an early return, so it is unreachable as well as unread')
    A('')
    if C.get('RR_UNIT'):
        A('```')
        A(f"RR_UNIT = {C['RR_UNIT']}     risk = combos(L) x RR_UNIT[L]")
        A('a round robin buys EVERY combination from doubles to the full parlay')
        for Lg in sorted(C['RR_UNIT']):
            n = len(combos(Lg))
            A(f"  {Lg} legs -> {n:2} bets x {C['RR_UNIT'][Lg]:.2f}u = {n * C['RR_UNIT'][Lg]:.2f}u")
        A('```')
    A('')
    A('## Retired and unreachable')
    A('')
    A(f"- **Chef's Table** (`chef`) — `CHEF_TICKET = {C.get('CHEF_TICKET')}`, a closure `var`, not settable at runtime")
    A('- **Grand Salami** (`biggest`) — deleted 2026-08-14, not gated. No construction site anywhere,')
    A('  including the server fallback (`NOSALAMI-2026-09-13`)')
    A(f"- **Dingers / Family Meal** (`family`) — `DINGERS = {C.get('DINGERS')}`, mint block returns on its first statement")
    A(f"- **Chalk ban** — `CHALK_N = {C.get('CHALK_N')}`; `chalk` is provably always `{{}}`, nothing reserved or barred")
    A('')
    A('⚠️ `nonchalk` is still the draft pool despite the name, and `HYST_TOTAL` — declared between two')
    A('dead chef blocks — feeds the live anchor-overtake deadband. Do not delete either with the chalk code.')
    A('')
    A('## Ledger')
    A('')
    if L:
        A(f"**{L['units']:+.2f}u on {L['staked']:.1f}u staked — {L['graded']} graded, {L['won']} won "
          f"({100 * L['won'] / max(L['graded'], 1):.1f}%)**, since {L['since']}, {L['nights']} graded nights.")
        A('')
        A('| kind | graded | won | units | staked |')
        A('|---|---|---|---|---|')
        for k, v in sorted(L['cats'].items(), key=lambda x: -x[1].get('units', 0)):
            A(f"| {k} | {v.get('graded')} | {v.get('won')} | {v.get('units'):+.2f} | {v.get('staked')} |")
    A('')
    A('## Other sports are not this board')
    A('')
    A(f"Soccer screamers use their own `MOON_LEGS: {C.get('SOCCER_MOON_LEGS')}` in `soccer/soccer_draft.js`, staked 2.0u")
    A('"by 2s & 3". NFL is the same shape and also drafts on EV. A doc describing soccer or NFL that')
    A('way is **not** stale — only MLB moved to four legs.')
    A('')
    A('## Why this file is generated — the failure log')
    A('')
    A('Four wrong beliefs acted on in one day, 2026-09-13. Each is the same mistake — a claim')
    A('trusted instead of checked:')
    A('')
    A('| # | the belief | the fact | what would have caught it |')
    A('|---|---|---|---|')
    A('| 1 | `_SIG` is the 2026-08-13 five-signal basket (from a doc) | it was DMGRATIO, and had been for 10 days | read `_SIG` out of `build15.py` |')
    A('| 2 | `_zhrc` at 0.4489 is doing work | it was `None` on all 419 bats | count non-null values of the column |')
    A('| 3 | the board ranks on `_SIG` (from a doc I wrote hours earlier) | it ranks on EV, since 2026-09-10 | check `meta.model`, and that top-N by `TOTAL` == top-N by `ev` |')
    A('| 4 | the two drafters apply the same `GAME_CAP` (both files said so in comments) | engine 6, fallback 4, for 26 days | one config file both of them read |')
    A('')
    A('All four checks are in this script. Run it instead of trusting a doc — including this one,')
    A('which is only trustworthy because it is regenerated, never written.')
    A('')
    A('`--check` also **reads `README.md` and `HANDOFF.md` and fails on any knob value written into')
    A('their prose that disagrees with `board_config.json`.** Prose is the one part of this repo')
    A('nothing executes, so it is the one part that rots unseen: on the day this check was added it')
    A('found `WIN=120` in the README five days after the window moved to 150, a stale `GAME_CAP=4`')
    A('in three separate places in HANDOFF, and a stale `CHALK_N=4` in two more. A line may still')
    A('discuss an old value — say *was*, *used to*, *superseded*, or put it in a correction table,')
    A('which is how a human tells the difference too.')
    A('')
    A('#4 is the one worth dwelling on, because it was invisible in the way the others were not.')
    A('The owner raised `GAME_CAP` from 4 to 6 on 2026-08-18 and only `index.html` got it.')
    A('`assemble_tickets.py` kept a literal `4` under a comment claiming it mirrored the engine, and')
    A('`index.html` had a *second*, bare `6` under a comment reading "these two must agree or the')
    A('pool and the gate disagree about who is in" — an invariant enforced by a sentence. The cap')
    A('binds on **25 of the last 25 boards**: every night, the two drafters were gating different')
    A('pools. Nothing was red, because nothing compared them. `board_config.json` and')
    A('`state.py --check` exist so that a number can only be wrong in one place at a time.')
    A('')
    A('Audit: `claude/audit-2026-09-13.md`. Window: `claude/win120-2026-09-13.md`.')
    A('Doc status conventions and the list of superseded docs: `claude/DOC-STATUS.md`.')
    return '\n'.join(o)


def check():
    B, C, D = build15(), client(), board()
    bad = []
    if not D: return ['no board found']
    if D.get('model') != B.get('BOARD_MODEL'):
        bad.append(f"board meta.model={D['model']} but BOARD_MODEL default is {B['BOARD_MODEL']}")
    if B.get('BOARD_MODEL') == 'ev_v1' and D.get('ranks_like_ev') is False:
        bad.append('BOARD_MODEL is ev_v1 but TOTAL does not rank like ev')
    dark = [k for k, v in (D.get('coverage') or {}).items() if v == 0]
    sig = {k for k, _ in (B.get('SIG') or [])}
    darksig = sorted(set(dark) & sig)
    if darksig:
        bad.append('_SIG terms with ZERO coverage on the live board: ' + ', '.join(darksig))
    if B.get('SIG') and abs(sum(w for _, w in B['SIG']) - 1.0) > 1e-6:
        bad.append('_SIG does not sum to 1.0')
    # a moon ships at MOON_LEGS, or at SHORT_MOON_FLOOR when the slate geometrically cannot hold one
    ok_legs = {C.get('MOON_LEGS'), C.get('SHORT_MOON_FLOOR')}
    for (n, k), _ in D['shape'].items():
        if k == 'moon' and n not in ok_legs:
            bad.append(f'a moon shipped with {n} legs; legal are {sorted(x for x in ok_legs if x)} '
                       f'(MOON_LEGS / SHORT_MOON_FLOOR in board_config.json)')
    # every round robin on the board must be priced by RR_UNIT, not by a hard-coded per-kind stake
    for risk, struct in D['rr']:
        legal = {round(len(combos(L)) * u, 2) for L, u in (C.get('RR_UNIT') or {}).items()}
        if legal and round(risk or 0, 2) not in legal:
            bad.append(f'a ticket is staked {risk}u ({struct}); RR_UNIT can only produce {sorted(legal)}')
    # BOARDCFG: index.html's fallback literals render every archived board. They must not drift.
    for k, vals in client_fallbacks().items():
        if len(vals) > 1:
            bad.append(f"index.html gives cfg('{k}') two different fallbacks: {vals}")
        elif k in C and vals[0] != C[k]:
            bad.append(f"index.html falls back to {k}={vals[0]} but board_config.json says {C[k]} "
                       f"-- archived boards would render differently from live ones")
    bad += doc_numbers()          # stale knob values written into README.md / HANDOFF.md
    missing = [k for k in ('MOON_LEGS', 'SHORT_MOON_FLOOR', 'WIN', 'Z_GATE', 'MOONS_PER_ANC',
                           'CHALK_N', 'NIGHT_WIN', 'MOON_SLACK') if k not in client_fallbacks()]
    if missing:
        bad.append('index.html reads these without a cfg() fallback: ' + ', '.join(missing))
    # the board it shipped must carry the config it was built with.
    # The FACT is in build15.py's source; meta.cfg is only checkable once a board has been built
    # since BOARDCFG shipped, and boards archived before that legitimately have none.
    if not re.search(r"meta\s*=\s*\{[^}]*'cfg'", read('build15.py')):
        bad.append("build15.py no longer stamps board_config.json into meta.cfg -- the client "
                   "would silently fall back to index.html's literals on every live board")
    if D.get('cfg') is None:
        pass     # pre-BOARDCFG board; the source check above is the one that matters
    else:
        drift = {k: (D['cfg'][k], C[k]) for k in C
                 if not k.startswith('_') and k in D['cfg']
                 and cfg_canon(D['cfg'][k]) != cfg_canon(C[k])}
        if drift:
            bad.append('board was built with a different config than board_config.json now holds: '
                       + ', '.join(f'{k} {a}->{b}' for k, (a, b) in sorted(drift.items())))
    return bad


if __name__ == '__main__':
    if '--md' in sys.argv:
        print(markdown())
    elif '--check' in sys.argv:
        bad = check()
        if bad:
            print('MISMATCH between the code and the live board:')
            for b in bad: print('  !! ' + b)
            sys.exit(1)
        print('OK — the live board agrees with the code.')
    else:
        print(markdown())
