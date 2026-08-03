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

# PRESERVE the prior board across same-slate rebuilds ONCE THE SLATE IS UNDERWAY. A fresh assemble()
# each rebuild re-picks anchors as weather/strength drift and reshuffles confirmed/locked tickets.
# The live client engine (index.html) already does the prior-aware refill — keep locked tickets,
# replace only a scratched leg — so the server must NOT re-draft a slate whose games have started.
#
# BEFORE FIRST PITCH, THOUGH, PRESERVING IS STRICTLY HARMFUL. Nothing is locked yet, and the client
# re-drafts from scratch on every page load regardless — so a preserved server draft doesn't stabilize
# anything the viewer sees, it just lets D_<date>.json drift away from the board on screen. And
# grade_night.py grades D_<date>.json. That gap is not theoretical: on 2026-08-03 the 17:01Z build
# drafted the Chef's Table off a 0%-rain forecast, the 17:18Z rebuild inherited a bad 56%/63% rain
# reading (see build15's precip provenance note), and the client — which re-drafts live — dropped the
# three shortest prices and showed Devers/Ohtani while the archive still said Schwarber/Rice. Whichever
# four were right, the night would have been graded on legs nobody was ever shown.
#
# So: re-draft while every game is still pending (server == what the client renders), and preserve only
# from first pitch onward (protecting a live board, which is what the rule was always for).
def _slate_started(_D):
    """True once ANY game on this slate has reached its first pitch (ET), matching the client's started())."""
    import datetime as _dtm
    try:
        from zoneinfo import ZoneInfo
        now = _dtm.datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        now = _dtm.datetime.now(_dtm.timezone.utc) - _dtm.timedelta(hours=4)
    if (_D.get('meta') or {}).get('date') and now.strftime('%Y-%m-%d') > _D['meta']['date']:
        return True                             # past midnight ET on the slate date -> everything has started
    nowmin = now.hour * 60 + now.minute
    for _p in (_D.get('players') or {}).values():
        m = re.match(r'(\d+):(\d+)\s*(AM|PM)', _p.get('gtime') or '')
        if m and nowmin >= (int(m.group(1)) % 12 + (12 if m.group(3) == 'PM' else 0)) * 60 + int(m.group(2)):
            return True
    return False

_same_slate = bool(prevD and (prevD.get('meta') or {}).get('date') == (D.get('meta') or {}).get('date') and prevD.get('tickets'))
if _same_slate and _slate_started(D):
    D['tickets'] = prevD['tickets']            # carry the prior draft forward unchanged; client handles live confirm/scratch/grade
    D.setdefault('meta', {})['tickets'] = len(D['tickets'])
    print(f"  (same slate, games underway -> preserved {len(D['tickets'])} prior tickets; no re-draft)")
else:
    assemble_tickets.assemble(D)               # builds D['tickets'] (brand-new slate, or same slate pre-first-pitch)
    if _same_slate:
        print(f"  (same slate, no first pitch yet -> re-drafted {len(D.get('tickets') or [])} tickets "
              f"so the archive matches what the client renders)")
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
