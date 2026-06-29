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

# PRESERVE the prior board across same-slate rebuilds. A fresh assemble() each rebuild
# re-picks anchors as weather/strength drift and reshuffles confirmed/locked tickets.
# The live client engine (index.html) already does the prior-aware refill — keep locked
# tickets, replace only a scratched leg — so the server must NOT re-draft a slate it has
# already built. Draft fresh ONLY for a brand-new slate (no prior, or a different date).
_same_slate = bool(prevD and (prevD.get('meta') or {}).get('date') == (D.get('meta') or {}).get('date') and prevD.get('tickets'))
# self-clearing: a prior draft whose notes still say "ISO" predates the ISO drop -> re-draft once.
_stale = _same_slate and any(re.search(r'\bISO\b', (t.get('note') or '')) for t in prevD.get('tickets', []))
if _stale:
    print("  (prior draft has stale ISO notes -> forcing one fresh re-draft to purge)")
if _same_slate and not _stale:
    D['tickets'] = prevD['tickets']            # carry the prior draft forward unchanged; client handles live confirm/scratch/grade
    D.setdefault('meta', {})['tickets'] = len(D['tickets'])   # assemble() normally sets this; the header "Tickets" counter reads D.meta.tickets
    print("  (same slate -> preserved %d prior tickets; no re-draft)" % len(D['tickets']))
else:
    assemble_tickets.assemble(D)               # builds D['tickets'] (brand-new slate / first build)
json.dump(D, open(DJSON, 'w'), indent=1)       # persist the assembled board data (handoff name)
_dt = (D.get('meta') or {}).get('date')
if _dt:
    json.dump(D, open(f"D_{_dt}.json", 'w'), indent=1)   # dated archive (with tickets) -> grade_night folds it next morning

src = open(BOARD).read()

# --- ISO chip -> Pitcher hittability (0-100) display swap (idempotent) ---
# ISO no longer scores OR displays. The first stat chip now shows OUR opposing-pitcher
# term as a 0-100 hittability score: 50 = neutral, higher = a more HR-prone arm. It is
# derived live in the client from the same pitcher multiplier that scores the bat
# (p.phr9 -- baked allowed-trio for listed arms, recomputed HR/9 otherwise; both clamp
# to 0.85-1.15, so (phr9-0.85)/0.30 -> 0..1). Applied here every build so it survives
# regen against whatever template is live, and is a no-op once the chip is already swapped.
src, _nchip = re.subn(
    r"\['ISO',.*?\],\['POWER'",
    "['Pitcher',(p.phr9!=null?Math.max(0,Math.min(100,Math.round((p.phr9-0.85)/0.30*100))):'—')],['POWER'",
    src, count=1)
if _nchip:
    print("  (display: ISO chip -> Pitcher 0-100 hittability)")

# strip the client-side ISO phrase banks (note generators) so live re-draws stay ISO-free
_A = r"(?:else )?if\(iso&&parseFloat\('0'\+iso\)>=0\.\d+\)o\.push\(\[[\d.]+,'iso',\[.*?\]\]\);"   # verbose array form
_B = r"(?:else )?if\(iso&&parseFloat\('0'\+iso\)>=0\.\d+\)o\.push\(\[[\d.]+,'iso',(?!\[).*?\]\);"  # compact tag form
src, _na = re.subn(_A, "", src)
src, _nb = re.subn(_B, "", src)
if _na or _nb:
    print(f"  (display: stripped {_na+_nb} client-side ISO note bank(s))")

# footer: ISO no longer used anywhere -> drop it from the data-source credit (idempotent)
src, _nf = re.subn(r"TeamRankings \(ISO &amp; HR/9\)", "TeamRankings (HR/9)", src, count=1)
# builder cap: singles can't beat the market (35% odds weight already concedes this), so the
# client emitted EVERY pool bat as a builder. Cap to the top 8 strongest at <=+600 -- damage
# control on a -EV category, ranked by TOTAL (which carries the market term). Idempotent.
src, _ncap = re.subn(
    r"byS\(nonchalk\.filter\(function\(n\)\{return !spent\[n\];\}\)\)\.forEach",
    "byS(nonchalk.filter(function(n){return !spent[n]&&P[n].odds!=null&&P[n].odds<=600;})).slice(0,8).forEach",
    src, count=1)
if _nf or _ncap:
    print(f"  (display: footer credit fixed={bool(_nf)}; client builder cap applied={bool(_ncap)})")

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
