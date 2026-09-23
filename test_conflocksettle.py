#!/usr/bin/env python3
"""test_conflocksettle.py -- CONFLOCKSETTLE-2026-09-22. A posted card must STAND before it can freeze a slip.

WHY THIS RULE EXISTS. CONFLOCK made the lock "every leg confirmed", and LOCK IS A LATCH (2026-08-17)
made that one-way: once `t.locked` is true it never comes back. Both are right. What neither knew is
WHEN the card behind a leg appeared -- `status` is a boolean recomputed from scratch every five
minutes, so a card one second old locked a ticket exactly as hard as one that had stood three hours.

`claude/cardrevision-2026-09-22.md` measured the cost. Walking every committed `slate_auto_<date>.json`
over 11 slates (2026-09-12..09-22, 2,276 pulls), 273 sides posted a confirmed nine and 10 of them were
later REVISED -- 3.7%, about one a slate -- at these lags from first post:

    24, 24, 25, 30, 30, 70, 83, 105, 110, 200 minutes        median 50, mean 70

Four reached a placed slip this season: Soderstrom 08-11, Goodman 08-17, Freeman 09-09, Eldridge 09-18.
⚠️ EVERY ONE WAS MLB'S OWN CARD CHANGING UNDER US. None was a bad RotoWire pull. That is the finding
that killed the two-source proposal (`claude/twosource-2026-09-22.md`, corrected) and produced this
instead: a second source cannot catch a revision to the source of truth. Only waiting can.

WHY 120. Cards post a median 180 min before first pitch (min 113, p10 148; only 2 of 60 sides posted
inside 120). So the settling period is spent almost entirely on lead time we already had:

    N=30 -> 5/10 caught    N=90  -> 7/10
    N=60 -> 5/10           N=120 -> 9/10, ~60 min of median lock window left    N=150 -> 9/10, no better

Eldridge (200 min) is not reachable by any N that leaves a usable window; that one belongs to VOIDKEEP.

WHAT IT GUARDS
  1. the knob exists in board_config.json AND boardcfg.DEFAULTS and they agree, and the client's
     cfg() fallback literal matches both (BOARDCFG-2026-09-13 exists because these have drifted)
  2. both halves of the mechanism are present: regen15.py WRITES meta.posted_at, index.html READS it
  3. the latch is gated on settledP, not on status==='confirmed' -- the latch is the one-way door
  4. settledP is defined at module scope reach and CONFLOCK_SETTLE_MIN is not re-declared inside
     assembleClient (a hoisted `var` of the same name would shadow it as undefined for the whole
     function and silently disable the rule while every identifier-grep below still passed --
     this is exactly how ANCHORCAP nearly shipped inert on 2026-09-22)
  5. FAILS OPEN, three ways: no map -> settled; unstamped side -> settled; knob 0 -> settled
  6. THE BEHAVIOUR, replayed through the real engine on the real committed board:
       - cards stamped one second ago  -> tickets do NOT latch
       - cards stamped 130 min ago     -> tickets latch exactly as before the fix
       - the grandfather sentinel 0    -> latches exactly as before the fix
  7. THE SAFETY PROPERTY, which matters more than the rule: a ticket already locked on the prior
     board stays locked no matter how fresh the cards are. This rule delays a first latch; it must
     never unlock a slip somebody has already placed.
  8. the control: with the fix reverted, scenario 6a latches more tickets than with it, so this
     suite fails without the fix rather than passing vacuously
  9. FLICKER-2026-09-22: the stamp is STANDING-SINCE, not FIRST-SEEN. Texas posted and un-posted
     five times on the evening this shipped; under first-seen that card read settled the whole
     time and "Chart a Course" latched on it. Replayed end to end through the real regen15.py --
     a side posts, drops off, comes back, and must get a FRESH clock, not the one it had before.
     The live StatsAPI confirm path has to start a clock too, or it bypasses the rule entirely.

    python3 test_conflocksettle.py
"""
import json, os, re, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def check(ok, label, detail=''):
    line = f"  {'ok  ' if ok else 'FAIL'} {label}" + (f"   {detail}" if detail else '')
    print(line)
    if not ok:
        FAILS.append(line)


def read(name):
    return open(os.path.join(HERE, name), encoding='utf-8').read()


print('CONFLOCKSETTLE-2026-09-22 -- the settling period on the confirm lock\n')

# ---------------------------------------------------------------- 1. the knob agrees everywhere
CFGJSON = json.load(open(os.path.join(HERE, 'board_config.json'), encoding='utf-8'))
sys.path.insert(0, HERE)
import boardcfg

N_JSON = CFGJSON.get('CONFLOCK_SETTLE_MIN')
N_PY = boardcfg.DEFAULTS.get('CONFLOCK_SETTLE_MIN')
check(N_JSON == 120, 'board_config.json carries CONFLOCK_SETTLE_MIN = 120', f'got {N_JSON!r}')
check(N_PY == N_JSON, 'boardcfg.DEFAULTS agrees with board_config.json', f'{N_PY!r} vs {N_JSON!r}')
check('CONFLOCK_SETTLE_MIN' in boardcfg._INT, "boardcfg coerces it to int (JSON would hand over a float)")
check(boardcfg.load(quiet=True)['CONFLOCK_SETTLE_MIN'] == 120, 'the resolved config reads 120')

IDX = read('index.html')
fb = set(re.findall(r"cfg\(\s*'CONFLOCK_SETTLE_MIN'\s*,\s*([0-9]+)\s*\)", IDX))
check(len(fb) == 1, 'index.html uses ONE fallback literal for the knob', f'found {sorted(fb)}')
check(fb == {str(N_JSON)}, "the archived-board fallback matches board_config.json",
      f'index.html {sorted(fb)} vs config {N_JSON}')

# a config that cannot bite must be refused, and 0 must stay legal as the kill switch
for bad_val in (-1, 241, 600):
    try:
        boardcfg._validate(dict(boardcfg.DEFAULTS, CONFLOCK_SETTLE_MIN=bad_val))
        check(False, f'_validate refuses CONFLOCK_SETTLE_MIN={bad_val}')
    except ValueError:
        check(True, f'_validate refuses CONFLOCK_SETTLE_MIN={bad_val}')
try:
    boardcfg._validate(dict(boardcfg.DEFAULTS, CONFLOCK_SETTLE_MIN=0))
    check(True, '_validate ALLOWS 0 -- the kill switch stays legal')
except ValueError as e:
    check(False, '_validate ALLOWS 0 -- the kill switch stays legal', str(e))

# ---------------------------------------------------------------- 2. both halves of the mechanism
REG = read('regen15.py')
check("['posted_at']" in REG or "'posted_at'" in REG,
      'regen15.py writes meta.posted_at (the WRITER half)')
check('_pa_grand' in REG, 'regen15.py has the grandfather branch (mid-slate introduction is safe)')
check('posted_at' in IDX, 'index.html reads meta.posted_at (the READER half)')

# ------------------------------------------------- 2b. FLICKER-2026-09-22: standing, not first-seen
# The first cut kept a stamp forever (`if _k in _pa: continue`), so a card that dropped off the feed
# and came back never restarted its clock. Texas flickered five times on 2026-09-22 and "Chart a
# Course" latched on it. These assertions are the ones that would have been red that evening.
check('_posted_now' in REG and 'set(_pa_prev) - _posted_now' in REG,
      'regen15.py rebuilds the map from the sides posted RIGHT NOW, dropping the rest')
check(not re.search(r'if\s+_k\s+in\s+_pa\s*:\s*\n\s*continue', REG),
      'the first-seen shortcut (`if _k in _pa: continue`) is GONE -- it is what let the flicker through')
check('_pa_lost' in REG, 'regen15.py reports the sides whose clock it reset (a silent reset is unreviewable)')
# and the live feed, which confirms a side on its own between builds, must start a clock too
live = re.search(r"pl\.status='confirmed';\s*pl\.out=false;[\s\S]{0,2200}?\n\s*\}\n", IDX)
check(bool(live) and 'posted_at' in live.group(0),
      'the live StatsAPI confirm path stamps posted_at -- otherwise it bypasses the rule entirely')
check(bool(live) and '==null' in live.group(0).replace(' ', ''),
      'and it only ever writes a MISSING key, so it cannot shorten a wait or overwrite the server')

# ---------------------------------------------------------------- 3. the latch is what is gated
# The latch is the one-way door: `t.locked=true` is never cleared, so the age check has to sit on
# the predicate that opens it, not only on pinnedP.
latch = re.search(r'var\s+_allConf\s*=([\s\S]{0,900}?)\}\s*\)\s*;', IDX)
check(bool(latch), 'the _allConf latch predicate is still findable')
if latch:
    body = latch.group(1)
    check('settledP(' in body, 'the latch tests settledP(), not a bare status check')
    check(not re.search(r"p\.status\s*===\s*'confirmed'", body),
          "the latch no longer tests p.status==='confirmed' directly")

pin = re.search(r'function\s+pinnedP\(n\)\s*\{[^}]*\}', IDX)
check(bool(pin) and 'settledP(n)' in pin.group(0), 'pinnedP() is gated on settledP()')
check(bool(pin) and 'started(n)' in pin.group(0),
      'pinnedP() KEEPS the clock half -- first pitch still locks regardless of card age')

# ---------------------------------------------------------------- 4. no hoisted shadow
# ANCHORCAP nearly shipped inert this way: a `var X` inside assembleClient hoists to the top of the
# function and is `undefined` until its assignment runs, so every read before that line silently
# disabled the gate while identifier-grepping tests kept passing.
_m = re.search(r'^\s*function\s+assembleClient\s*\(', IDX, re.M)
check(bool(_m), 'the assembleClient declaration is findable'
                ' (NOT a bare find("assembleClient") -- the baked const D mentions it too)')
ac = _m.start() if _m else len(IDX)
check(not re.search(r'\bvar\s+CONFLOCK_SETTLE_MIN\b', IDX[ac:]),
      'CONFLOCK_SETTLE_MIN is NOT re-declared with var inside assembleClient (hoisted-shadow guard)')
check(bool(re.search(r'\bCONFLOCK_SETTLE_MIN\s*=\s*cfg\(', IDX[:ac])),
      'the knob is bound OUTSIDE assembleClient, where syncCfg() can re-bind it per board')
check(len(re.findall(r"CONFLOCK_SETTLE_MIN\s*=\s*cfg\(", IDX)) == 2,
      'bound in exactly two places: the module-scope declaration and syncCfg()',
      f"found {len(re.findall(r'CONFLOCK_SETTLE_MIN=cfg', re.sub(chr(32), '', IDX)))}")

# ---------------------------------------------------------------- 5. fails open, three ways
sp = re.search(r'function\s+settledP\(n\)\s*\{[\s\S]{0,600}?\n\s*(?=function\s)', IDX)
spb = sp.group(0) if sp else ''
check(bool(spb), 'settledP() is findable')
check('!_PA' in spb, 'no posted_at map on the board -> settled (archived boards render unchanged)')
check('!CONFLOCK_SETTLE_MIN' in spb, 'knob 0 -> settled (kill switch)')
check('t==null' in spb.replace(' ', ''), 'a confirmed side with no stamp -> settled')

# ---------------------------------------------------------------- 6/7/8. behaviour, through the engine
def latest_board():
    """The newest board that can actually EXERCISE this suite.

    ⚠️ It must carry at least one LATCHED ticket, and that is not a detail. The safety assertion --
    "a ticket already locked on the prior board stays locked" -- is vacuous on a board with nothing
    locked, and on 2026-09-23 the newest board was a 11:38am one with zero latches, so the suite
    went red at "0 in, 0 kept" against code that was fine. That is the THIRD time in two days a
    fixture here quietly stopped being the thing it was named after (the like-for-like compare, then
    the no-map board, now this). Pick a board that has the property the test is about; fall back to
    any board with tickets and SAY the safety check could not run, rather than failing on it.
    """
    ds = sorted(f for f in os.listdir(HERE) if re.fullmatch(r'D_\d{4}-\d{2}-\d{2}\.json', f))
    fallback = (None, None)
    for f in reversed(ds):
        D = json.load(open(os.path.join(HERE, f), encoding='utf-8'))
        if not (D.get('tickets') and any(p.get('status') == 'confirmed' for p in D.get('players', {}).values())):
            continue
        if any(t.get('locked') for t in D['tickets']):
            return f, D
        if fallback[0] is None:
            fallback = (f, D)
    return fallback


NAME, BOARD = latest_board()
print()
if not BOARD:
    check(False, 'a committed board with tickets and confirmed bats to replay')
elif not shutil.which('node'):
    print('  ..  node unavailable -- behavioural replay skipped (static assertions above still ran)')
else:
    print(f"  replaying {NAME} ({len(BOARD['tickets'])} tickets, "
          f"{sum(1 for t in BOARD['tickets'] if t.get('locked'))} already latched) through the real engine\n")
    sides = {(p['game'], p['code']) for p in BOARD['players'].values() if p.get('status') == 'confirmed'}
    now = int(time.time())

    def variant(stamp, clear_locked):
        E = json.loads(json.dumps(BOARD))
        E['meta']['posted_at'] = {f'{g}|{c}': stamp for g, c in sides}
        if clear_locked:
            for t in E['tickets']:
                t.pop('locked', None)
        return E

    def draft(E, html):
        d = tempfile.mkdtemp()
        try:
            j = os.path.join(d, 'w.json')
            json.dump(E, open(j, 'w'), indent=1)
            r = subprocess.run(['node', os.path.join(HERE, 'client_assemble.js'), j, html],
                               capture_output=True, text=True, timeout=180, cwd=HERE)
            if r.returncode != 0:
                return None
            O = json.load(open(j, encoding='utf-8'))
            return [(t.get('name'), bool(t.get('locked')),
                     tuple(l['name'] for l in t.get('players', []))) for t in O.get('tickets', [])]
        finally:
            shutil.rmtree(d, ignore_errors=True)

    LIVE = os.path.join(HERE, 'index.html')
    nlock = lambda o: sum(1 for t in o if t[1]) if o else -1

    # ⚠️ STRIP the map, do not just reuse the board. Every board committed since this feature shipped
    # CARRIES a posted_at, so `BOARD` as-is is not the no-map case it was on the day this was written
    # -- and a stamp with a real recent time (a side that just came back on the feed) makes it differ
    # from the grandfathered one for a perfectly correct reason. This assertion is about the board
    # having NO map at all, which is what an archived night looks like, so build that explicitly.
    def no_map():
        E = json.loads(json.dumps(BOARD)); (E.get('meta') or {}).pop('posted_at', None); return E
    base = draft(no_map(), LIVE)                                # no posted_at at all -> fail-open
    fresh_nl = draft(variant(now, True), LIVE)                  # cards one second old, nothing latched
    old_nl = draft(variant(now - 130 * 60, True), LIVE)         # cards 130 min old, nothing latched
    grand_nl = draft(variant(0, True), LIVE)                    # grandfather sentinel
    fresh_keep = draft(variant(now, False), LIVE)               # cards one second old, prior latches intact
    grand_keep = draft(variant(0, False), LIVE)                 # grandfathered, prior latches intact

    # the reference: the same board through the SAME engine with the rule switched off at the knob
    off_nl = None
    E = variant(now, True)
    E['meta'].setdefault('cfg', {})['CONFLOCK_SETTLE_MIN'] = 0
    off_nl = draft(E, LIVE)

    check(base is not None and nlock(base) == nlock(draft(no_map(), LIVE)),
          'the engine runs and is deterministic on this board')
    check(nlock(off_nl) > nlock(fresh_nl),
          'THE CONTROL BITES: with the knob at 0 the same second-old cards latch more tickets',
          f'knob 0 -> {nlock(off_nl)} latched, knob 120 -> {nlock(fresh_nl)} latched')
    check(nlock(old_nl) == nlock(off_nl),
          'cards 130 min old latch exactly as they did before the rule',
          f'{nlock(old_nl)} vs {nlock(off_nl)}')
    check(grand_nl == old_nl,
          'the grandfather sentinel 0 behaves as fully settled',
          f'{nlock(grand_nl)} vs {nlock(old_nl)}')
    # LIKE FOR LIKE. `grand_nl` has its prior latches stripped and `base` does not, so comparing
    # those two asserts nothing about fail-open -- it asserts that clearing the latches changes
    # nothing, which is false the moment the two differ. (It passed by coincidence on the 17:47
    # board and went red on the 18:01 one, which is the only reason this comment exists.)
    check(base == grand_keep,
          'a board with NO posted_at drafts identically to a fully-grandfathered one (fail-open)')

    # 7. the safety property. Every ticket latched on the way in is still latched on the way out.
    was = {t.get('name') for t in BOARD['tickets'] if t.get('locked')}
    still = {t[0] for t in (fresh_keep or []) if t[1]}
    if not was:
        print('  ..  SAFETY check SKIPPED -- no board on disk carries a latched ticket yet '
              '(a morning board has none); it is vacuous, not passing')
    else:
        check(was <= still,
              'SAFETY: every ticket already locked on the prior board stays locked with second-old cards',
              f'{len(was)} in, {len(was & still)} kept' + (f'  LOST: {sorted(was - still)}' if was - still else ''))

    # and the one thing that SHOULD still latch on freshly-posted cards: a game already underway
    if fresh_nl is not None:
        clock = [t[0] for t in fresh_nl if t[1]]
        print(f"        second-old cards latch {len(clock)} ticket(s) on the clock half alone"
              + (f": {', '.join(clock)}" if clock else ''))


# ---------------------------------------------- 9. THE FLICKER, end to end through regen15.py
# Three builds: a side posts, drops off the feed, comes back. The stamp must be issued, then
# removed, then issued AFRESH -- not restored to the original. Run the real script, not a copy of
# its logic; a second implementation of the rule is how most of this file's history happened.
print()
if BOARD and shutil.which('node'):
    import shutil as _sh
    sand = tempfile.mkdtemp()
    try:
        for f in ('regen15.py', 'assemble_tickets.py', 'boardcfg.py', 'board_config.json',
                  'client_assemble.js', 'cardnotes.py', 'index.html', 'season.json'):
            src = os.path.join(HERE, f)
            if os.path.exists(src):
                _sh.copy(src, sand)

        side = None
        for n, p in BOARD['players'].items():
            if p.get('status') == 'confirmed' and not p.get('out'):
                side = (p['game'], p['code']); break
        key = f'{side[0]}|{side[1]}'

        def build(drop_side):
            """One build: write build15's output, run regen15, read back the published stamp."""
            E = json.loads(json.dumps(BOARD))
            E.pop('tickets', None); E.pop('pool', None); E['meta'].pop('posted_at', None)
            if drop_side:                      # the card vanishes from the feed
                for p in E['players'].values():
                    if (p.get('game'), p.get('code')) == side:
                        p['status'] = 'projected'
            json.dump({'players': E['players'], 'meta': E['meta']},
                      open(os.path.join(sand, 'D_0615.json'), 'w'), indent=1)
            subprocess.run([sys.executable, 'regen15.py'], cwd=sand,
                           capture_output=True, text=True, timeout=180)
            s = open(os.path.join(sand, 'index.html'), encoding='utf-8').read()
            m = re.search(r'const D=(\{.*?\}),WX=D\.meta\.wx;', s, re.S)
            return (json.loads(m.group(1))['meta'] or {}).get('posted_at') or {}

        one = build(False)                     # posted  -> stamped (grandfathered on first creation)
        check(key in one, f'build 1: {key} is stamped while its card is up')
        time.sleep(1.1)
        two = build(True)                      # dropped -> stamp REMOVED
        check(key not in two, f'build 2: {key} drops off the feed and LOSES its stamp',
              f'still {two.get(key)!r}')
        check(len(two) == len(one) - 1, 'build 2: only that one side is affected',
              f'{len(one)} -> {len(two)}')
        time.sleep(1.1)
        three = build(False)                   # returns -> stamped AFRESH, clock restarted
        check(key in three, f'build 3: {key} comes back and is stamped again')
        check(three.get(key) not in (None, one.get(key)),
              'build 3: the returning card gets a FRESH clock, not the one it had before',
              f'was {one.get(key)!r}, now {three.get(key)!r}')
        check(three.get(key, 0) > 0,
              'build 3: and a real timestamp, not the grandfather sentinel',
              f'{three.get(key)!r}')
    finally:
        _sh.rmtree(sand, ignore_errors=True)
else:
    print('  ..  flicker replay skipped (no board or no node)')

print()
if FAILS:
    print(f'{len(FAILS)} FAILURE(S)')
    sys.exit(1)
print('all assertions passed')
