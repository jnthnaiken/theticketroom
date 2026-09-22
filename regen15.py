"""
The Ticket Room — assemble + inject step.

Runs AFTER the scorer (build15.py) has written D_0615.json = {players, meta}.
1) builds D['tickets'] via assemble_tickets.assemble() (pool gating, refill, names,
   notes — the brain), carrying over any game left suspended on the prior board,
2) injects the freshly assembled D into the published board's `const D=...` block.

The published index.html doubles as its own shell/template: we read it, swap the
data block, and write it back. All paths are repo-relative so it runs on the Action.
"""
import json, re, time, os
import assemble_tickets

BOARD = "index.html"       # published board == its own shell/template
DJSON = "D_0615.json"      # scorer output; assembled in place, then injected

D = json.load(open(DJSON))
for p in D.get('players', {}).values():        # assembler reads these flags
    p.setdefault('void', False); p.setdefault('out', False)

# carry any suspended game from the previously published board into today, then assemble
prevD = None
try:
    m = re.search(r'const D=(\{.*?\}),WX=D\.meta\.wx;', open(BOARD).read(), re.S)
    if m:
        prevD = json.loads(m.group(1))
        assemble_tickets.carryover(D, prevD)
        # The published board is the running ledger. If the scorer couldn't fold the night
        # (offline: no PRIOR_D/NIGHT_LOG and no season.json), it leaves a NEUTRAL season.
        # In that case only (season.json ALSO absent), carry the prior board's real season. A present
        # season.json -- even a deliberate reset to 0.0 -- is authoritative and must NOT be overwritten.
        cur = (D.get('meta') or {}).get('season') or {}
        neutral = (not cur.get('cats')) and (cur.get('history') in (None, [0.0], [0], []))
        ps = (prevD.get('meta') or {}).get('season')
        if neutral and not os.path.exists('season.json') and ps and (ps.get('cats') or (ps.get('history') and ps['history'] != [0.0])):
            D.setdefault('meta', {})['season'] = ps
            print(f"  (carried prior season ledger: {len(ps.get('cats',{}))} cats, history {len(ps.get('history',[]))})")
except Exception as e:
    print(f"  (carryover skipped: {e})")

# ---------------------------------------------------------------------------------------------
# DRAFT. One rule, one implementation: a ticket is LOCKED once every one of its legs is confirmed
# (in the posted lineup) or already in progress, and none are scratched. Everything else re-drafts
# against the current odds, lineups and weather on every build.
#
# That rule has always lived in __assembleClient() inside index.html, which re-runs on every page
# load and decides what a person actually sees. assemble_tickets.py implements the same intent in
# Python, but it drafts from scratch with no notion of a prior board -- so the server could only
# ever choose between re-drafting confirmed tickets (breaks the lock) or freezing everything
# (breaks the re-draft). Neither is the rule.
#
# The gap was not cosmetic: grade_night.py grades D_<date>.json, the SERVER's draft. On 2026-08-03
# a bad rain reading (see build15's precip provenance note) reached the 17:18Z build, the client
# dropped the three shortest Chef's Table prices, and the archive still said Schwarber/Rice --
# the night would have been graded on legs nobody was shown.
#
# So the server now RUNS the client's engine (client_assemble.js) instead of paraphrasing it.
# index.html is the single source of truth for the draft; the archive is what the board shows, by
# construction, and there is no second implementation to keep in sync. assemble_tickets.assemble()
# stays as the fallback if Node or the engine is unavailable.
# FORCE_REBUILD: a data-fix re-run of a slate that already shipped. Handing the prior board to the engine
# is what makes the lock rule work on a normal build -- but on a rebuild every game is long final, so every
# prior ticket would lock and the corrected data would change nothing. Draft this one from scratch instead.
_force = os.environ.get('FORCE_REBUILD', '').lower() == 'true'
if _force:
    print("  (FORCE_REBUILD -> ignoring the prior board; drafting this slate from scratch)")
    # ...and draft it as of five minutes before the first pitch, not as of right now. See client_assemble.js.
    def _gmin(gt):
        import re as _re
        m = _re.match(r'\s*(\d+):(\d+)\s*(AM|PM)', gt or '', _re.I)
        if not m: return None
        h = int(m.group(1)) % 12
        if m.group(3).upper() == 'PM': h += 12
        return h * 60 + int(m.group(2))
    _mins = [x for x in (_gmin((p or {}).get('gtime')) for p in D.get('players', {}).values()) if x is not None]
    if _mins:
        _t = max(0, min(_mins) - 5)
        os.environ['ASOF'] = "%sT%02d:%02d:00-04:00" % (D['meta']['date'], _t // 60, _t % 60)
        print(f"  (as-of {os.environ['ASOF']} -- five minutes before the first lock)")
_same_slate = (not _force) and bool(prevD and (prevD.get('meta') or {}).get('date') == (D.get('meta') or {}).get('date') and prevD.get('tickets'))
if _same_slate:
    D['tickets'] = prevD['tickets']            # hand the prior board to the engine AS PRIOR -> it locks the confirmed ones
    print(f"  (same slate -> {len(D['tickets'])} prior tickets handed to the draft engine)")
    # LOCKEVICT-2026-08-29: carry the night's CHALK UNION too. `meta` comes fresh from build15 on
    # every build, so without this the union resets every five minutes and remembers nothing. The
    # engine reads it, unions today's ban into it, and republishes it; the ONLY consumer is the
    # localStorage latch, which uses it to refuse to resurrect a slip CHALKOFF already evicted.
    # (2026-08-28: Alvarez was banned at 21:36Z and his three slips died; by 23:12Z he was 252 and
    # out of the ban, and any tab that had been closed through that window put "Sea Legs" back on
    # a board the server publishes without it -- through every hard refresh, since localStorage
    # survives one.) Guarded by _same_slate for the same reason the tickets are: a ban belongs to
    # one slate, and a new date correctly starts empty.
    _ever = (prevD.get('meta') or {}).get('chalkever')
    if _ever:
        D.setdefault('meta', {})['chalkever'] = _ever
        print(f"  (carried the night's chalk union: {len(_ever)} bat(s))")
    # RETRACTEDCARRY-2026-08-30: carry `meta.retracted` the same way, for the same reason.
    # RETRACTED-2026-08-29 shipped the READER half only -- the localStorage latch reads
    # `D.meta.retracted` and declines to resurrect a signature listed there -- but nothing ever
    # put it in the next build's `meta`, and `meta` comes fresh from build15 every five minutes.
    # So a signature written into the published board survived exactly ONE build, and any tab
    # that loaded outside that window put the withdrawn slip back. That is what happened on
    # 2026-08-30: the board was repaired by hand at 18:55Z, "Set the Hook" (Esmerlyn Valdez) was
    # withdrawn, the owner's tab re-admitted it out of his own lock store, and the page showed a
    # fifth anchor the server does not carry. Same shape and same guard as `chalkever` above:
    # one slate, read in exactly ONE place, one power -- decline to resurrect a slip the
    # published board does not have. It reaches no draft decision and cannot change the board.
    _retr = (prevD.get('meta') or {}).get('retracted')
    if _retr:
        D.setdefault('meta', {})['retracted'] = _retr
        print(f"  (carried the night's retracted signatures: {len(_retr)})")

# ---------------------------------------------------------------------------------------------
# CONFLOCKSETTLE-2026-09-22 -- WHEN did each side's card post? The board never knew. `status` is a
# per-build boolean recomputed from scratch every five minutes, so "confirmed" carried no age and a
# card one minute old locked a ticket exactly as hard as one that had stood for three hours.
#
# It matters because posted cards get REVISED. 11 slates of committed slate_auto pulls (09-12..09-22,
# 2,276 pulls, claude/cardrevision-2026-09-22.md): 273 sides posted a confirmed nine and 10 were later
# changed -- 3.7%, about one a slate -- at lags of 24..200 min from first post, median 50. Four of those
# reached a placed slip this season (Soderstrom 08-11, Goodman 08-17, Freeman 09-09, Eldridge 09-18).
# None of them were a RotoWire error: every one was MLB's OWN card, revised after we had already locked
# on it. That is why a second source would not have caught any of them and a settling period does.
#
# So: stamp the epoch second a side FIRST appears confirmed-with-a-nine, carry it across builds, and let
# the engine refuse to latch a ticket whose legs are younger than CONFLOCK_SETTLE_MIN. Keyed `game|code`
# -- game number, not matchup, because a doubleheader is two sides of the same two teams. Verified stable
# from first build to last across 09-19/20/21.
# Scoped by DATE alone, deliberately NOT by `_same_slate` above: that flag also requires the prior board
# to carry tickets, and a stamp is a fact about a card, not about whether we had a board drafted yet. A
# morning build that produces no tickets must not throw away the morning's stamps and re-age every card.
_pa_same = (not _force) and bool(prevD and (prevD.get('meta') or {}).get('date') == (D.get('meta') or {}).get('date'))
_pa_prev = ((prevD.get('meta') or {}).get('posted_at') if _pa_same else None)
# GRANDFATHER, and it is the whole reason this ships mid-slate safely. Two cases stamp 0 = "posted long
# ago, already settled": the build that FIRST creates the map on a running slate (cards are standing and
# we have no idea for how long -- stamping them `now` would mark the entire posted board unsettled and
# hold off every latch for two hours, churning exactly the placed slips this rule exists to protect), and
# FORCE_REBUILD (a finished slate has no live card age, and the rebuild must reproduce what shipped).
# A map that already EXISTS -- including the empty one a fresh slate morning writes before anything posts
# -- means every new key is a real, observed post and gets the real clock.
_pa_grand = _force or (_pa_same and _pa_prev is None)
_pa_prev = dict(_pa_prev or {})
_pa_now, _pa_new = int(time.time()), 0

# 🚨 FLICKER-2026-09-22 -- THE STAMP IS "STANDING SINCE", NOT "FIRST SEEN", AND THIS COST US A SLIP.
# The first cut of this block said `if _k in _pa: continue` -- once a side had a stamp it was never
# touched again. That measures age since a card was first SEEN, and what the lock actually needs is
# how long it has stood WITHOUT INTERRUPTION.
#
# 2026-09-22, the evening this shipped: Texas posted and un-posted FIVE times between 20:27Z and
# 22:41Z (on/off/on/off/on/off/on/off/on/off -- 112 pulls). Under first-seen, that card read
# "standing since 20:27" the whole time, so "Chart a Course" latched on Justin Foscue during one of
# the ON windows and stayed locked -- the latch is one-way -- while the feed showed him projected.
# Three more locked slips carried a Texas leg, though those froze on the clock half, not on this.
#
# ⚠️ AND THE MEASUREMENT COULD NOT SEE IT. claude/cardrevision-2026-09-22.md compared posted nines
# against posted nines and SKIPPED pulls where a side was not posted, so all five dropouts were
# invisible to it. Its 3.7% is revisions-while-posted only; it says nothing about feed stability.
# For scale: 09-19 and 09-20 had ZERO dropouts across 426 pulls, so this is rare, not routine --
# which is exactly why it went unmodelled.
#
# So the map now holds ONLY the sides posted RIGHT NOW. A side that drops off loses its stamp and
# starts a fresh clock when it comes back, which means a card flickering like Texas never settles at
# all and its slips wait for first pitch. That is the correct answer for a feed we cannot trust.
#
# Note this does NOT invert the fail-open rule in index.html's settledP(): an unstamped side is only
# read as "settled" when it is ALSO confirmed, and a side that has dropped off is not confirmed, so
# it never reaches that branch. Deleting a stamp can only ever delay a latch.
#
# Bounded cost of the paranoid case: if a whole pull comes back empty (a feed outage rather than a
# card change) every stamp resets and nothing NEW latches for CONFLOCK_SETTLE_MIN. Slips already
# latched are untouched, and the clock half still locks everything at first pitch, so the worst case
# is "tonight's board locks on the clock" -- the pre-CONFLOCK behaviour, not a broken board.
_posted_now = set()
for _p in (D.get('players') or {}).values():
    if _p.get('status') != 'confirmed' or _p.get('out') or _p.get('void'):
        continue
    _posted_now.add("%s|%s" % (_p.get('game'), _p.get('code')))
_pa = {}
for _k in _posted_now:
    if _k in _pa_prev:
        _pa[_k] = _pa_prev[_k]          # still standing -- the clock keeps running
    else:
        _pa[_k] = 0 if _pa_grand else _pa_now
        _pa_new += 1
_pa_lost = sorted(set(_pa_prev) - _posted_now)
D.setdefault('meta', {})['posted_at'] = _pa
print("  posted_at: %d side(s) standing, %d new this build%s%s" % (
    len(_pa), _pa_new, " (GRANDFATHERED as already settled)" if (_pa_grand and _pa_new) else "",
    ("; DROPPED OFF THE FEED -> clock reset: " + ", ".join(_pa_lost)) if _pa_lost else ""))

json.dump(D, open(DJSON, 'w'), indent=1)       # the engine reads/writes this file in place

_drafted = False
if os.path.exists('client_assemble.js') and os.path.exists(BOARD):
    import subprocess
    try:
        r = subprocess.run(['node', 'client_assemble.js', DJSON, BOARD],
                           capture_output=True, text=True, timeout=120)
        if r.stdout.strip(): print(r.stdout.rstrip())
        if r.returncode == 0:
            D = json.load(open(DJSON))         # engine rewrote tickets/pool in place
            _drafted = bool(D.get('tickets'))
        else:
            print(f"  !! client engine exited {r.returncode}: {(r.stderr or '').strip()[:200]}")
    except Exception as e:
        print(f"  !! client engine unavailable ({str(e)[:120]})")
# A forced rebuild starts with no prior board, so the engine takes the FRESH draftF path, and a browser
# loading that board would immediately run the preserve path on top of it. Run the engine a second time,
# feeding it its own output as prior -- the same two steps a visitor's browser performs -- and archive
# whatever that settles on. That is what keeps the archive and the screen agreeing.
#
# STALE RATIONALE, corrected 2026-09-13: this used to say the second pass existed because of the SALAMI
# BACKSTOP -- a preserve-path block that shipped a Grand Salami when draftF's pre-chosen salami anchor got
# absorbed into a moon. That block is gone (the salami was deleted from index.html on 2026-08-14; only a
# historical comment survives, and NOSALAMI-2026-09-13 took it out of assemble_tickets.py too). The second
# pass is KEPT because archive-vs-screen parity is the general rule, not because of the salami -- but if
# you are ever hunting dead work, this is a fair thing to re-test.
if _force and _drafted:
    json.dump(D, open(DJSON, 'w'), indent=1)
    try:
        r2 = subprocess.run(['node', 'client_assemble.js', DJSON, BOARD],
                            capture_output=True, text=True, timeout=120)
        if r2.stdout.strip(): print("  second pass:" + r2.stdout.rstrip())
        if r2.returncode == 0:
            D = json.load(open(DJSON))
        else:
            print(f"  !! second pass exited {r2.returncode}: {(r2.stderr or '').strip()[:200]}")
    except Exception as e:
        print(f"  !! second pass failed ({str(e)[:120]})")

if not _drafted:
    print("  !! FALLING BACK to assemble_tickets.py -- the archive may not match the rendered board")
    assemble_tickets.assemble(D)               # same rules, but no prior-board lock: last resort only

# THINBAT-2026-09-15: tripwire for the owner's rule that a bat under MIN_CARD_BIP batted balls is never
# drafted. The engine (index.html) enforces it; this only SHOUTS if a board still carries one -- e.g. the
# assemble_tickets.py fallback above, which knows nothing about `thin`, or a slip that locked before the
# rule shipped. It does not exit: a failed step here would stop the ledger/calibration commit too.
_thin = [(t.get('name'), l.get('name')) for t in (D.get('tickets') or [])
         for l in (t.get('players') or [])
         if ((D.get('players') or {}).get(l.get('name')) or {}).get('thin')]
if _thin:
    print(f"::error::THINBAT: {len(_thin)} ticket leg(s) on a bat under the batted-ball floor: "
          + '; '.join(f"{a} <- {b}" for a, b in _thin))

D.setdefault('meta', {})['tickets'] = len(D.get('tickets') or [])
json.dump(D, open(DJSON, 'w'), indent=1)       # persist the assembled board data (handoff name)
_dt = (D.get('meta') or {}).get('date')
if _dt:
    json.dump(D, open(f"D_{_dt}.json", 'w'), indent=1)   # dated archive (with tickets) -> grade_night folds it next morning

src = open(BOARD).read()

# --- DOUBLEHEADER live-grade fix (idempotent) ---
# The live grader disambiguates a doubleheader by matching the board's expected game time
# to the schedule game's ET start time. It compared the board gtime "H:MM PM ET" (carries a
# " ET" suffix) against etOf()'s "H:MM PM" (no zone), so `_got !== _want` was ALWAYS true and
# BOTH halves of a DH were skipped -> a HR in the game actually being played never registered
# live (e.g. 2026-07-11 Valdez in MIL@PIT game 1). Strip the trailing " ET" from both sides
# before comparing so the correct half matches. No-op once the file already carries the fix.
src, _ndh = re.subn(
    r"var _want=\(expectGt\[gm\]\|\|''\)\.replace\([^)]*\)\.trim\(\),_got=etOf\(g\);",
    (lambda mm: "var _want=(expectGt[gm]||'').replace(/[\\u202f\\s]+/g,' ').replace(/\\s*ET$/i,'').trim(),_got=(etOf(g)||'').replace(/\\s*ET$/i,'').trim();"),
    src, count=1)
if _ndh:
    print(f"  (live-engine doubleheader ET-match fix applied x{_ndh})")

dj = 'const D=' + json.dumps(D, ensure_ascii=True) + ',WX=D.meta.wx;'
src, n = re.subn(r'const D=[\s\S]*?,WX=D\.meta\.wx;', (lambda mm: dj), src, count=1)
assert n == 1, f"could not find the `const D=...,WX=D.meta.wx;` block in {BOARD}"

for attempt in range(5):                       # transient Errno5 retry on this volume
    try:
        open(BOARD, 'w').write(src); break
    except OSError:
        if attempt == 4:
            raise
        time.sleep(0.4)
print(f"assembled {len(D['tickets'])} tickets; injected -> {len(src)} bytes; players {len(D['players'])}")
