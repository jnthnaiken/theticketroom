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
RULES_VERSION = "2026-07-02-redraft2"      # bump to force a one-time re-draft when draft rules change
_same_slate = bool(prevD and (prevD.get('meta') or {}).get('date') == (D.get('meta') or {}).get('date') and prevD.get('tickets'))
# self-clearing: re-draft once if the prior draft predates the ISO drop OR was built under older rules.
_stale = _same_slate and any(re.search(r'\bISO\b', (t.get('note') or '')) for t in prevD.get('tickets', []))
_ruleschg = _same_slate and ((prevD.get('meta') or {}).get('rules_version') != RULES_VERSION)
_scratched = _same_slate and any((((D.get('players') or {}).get(l.get('name')) or {}).get('out')) or (((D.get('players') or {}).get(l.get('name')) or {}).get('void')) for t in prevD.get('tickets', []) for l in (t.get('players') or []))   # ROOT FIX: a preserved ticket has a now-scratched/void leg -> re-draft so the committed board never grades a benched player
if _stale or _ruleschg or _scratched:
    print("  (forcing one fresh re-draft: %s)" % ("stale ISO notes" if _stale else ("draft rules changed" if _ruleschg else "a leg was scratched/void")))
if _same_slate and not _stale and not _ruleschg and not _scratched:
    D['tickets'] = prevD['tickets']            # carry the prior draft forward unchanged; client handles live confirm/scratch/grade
    D.setdefault('meta', {})['tickets'] = len(D['tickets'])
    print("  (same slate -> preserved %d prior tickets; no re-draft)" % len(D['tickets']))
else:
    assemble_tickets.assemble(D)               # builds D['tickets'] (brand-new slate / first build)
# (no preserve-trim needed: a rules change forces a re-draft via RULES_VERSION above)
D.setdefault('meta', {})['rules_version'] = RULES_VERSION   # stamp so a later build detects rule changes
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
    "['Pitcher',(p.phr9!=null?Math.max(0,Math.min(100,Math.round((p.phr9-0.70)/0.60*100))):'—')],['POWER'",
    src, count=1)
if _nchip:
    print("  (display: ISO chip -> Pitcher 0-100 hittability)")
# re-scale the Pitcher 0-100 chip to the widened pitcher term (phr9 now 0.70-1.30 for listed arms).
src, _nps = re.subn(r"\(p\.phr9-0\.85\)/0\.30\*100", "(p.phr9-0.70)/0.60*100", src)
if _nps:
    print(f"  (display: re-scaled Pitcher chip to 0.70-1.30 range x{_nps})")
# NO base score -> the base chip now shows OUR model score (TOTAL). Relabel Match/khr -> Model. Idempotent.
src, _nlab = re.subn(r"\['(?:Match|khr)',p\.aT!=null\?p\.aT\.toFixed\(1\):'—'\]",
                     "['Model',p.TOTAL!=null?Math.round(p.TOTAL):'—']", src, count=1)
# the brick "base" badge shows the (display-only) khr score, looked up live from D.players by
# the leg name (legs carry .total/.aT but not khr). Matches the original aT form OR the prior
# TOTAL form. Idempotent.
src, _nbb = re.subn(r"🧱 \$\{(?:Math\.round\(p\.TOTAL\)|p\.aT\.toFixed\(1\))\}",
                    "🧱 ${(D.players[p.name]||{}).khr!=null?(D.players[p.name]||{}).khr:'—'}", src)
# no base -> repoint UI sorts off the flat aT onto TOTAL
src, _nsrt = re.subn(r"D\.players\[b\]\.aT-D\.players\[a\]\.aT", "D.players[b].TOTAL-D.players[a].TOTAL", src)
if _nlab or _nsrt:
    print(f'  (display: base chip->Model x{_nlab}; base badge->Model x{_nbb}; aT-sort->TOTAL x{_nsrt})')

# strip the client-side ISO phrase banks (note generators) so live re-draws stay ISO-free
_A = r"(?:else )?if\(iso&&parseFloat\('0'\+iso\)>=0\.\d+\)o\.push\(\[[\d.]+,'iso',\[.*?\]\]\);"   # verbose array form
_B = r"(?:else )?if\(iso&&parseFloat\('0'\+iso\)>=0\.\d+\)o\.push\(\[[\d.]+,'iso',(?!\[).*?\]\);"  # compact tag form
src, _na = re.subn(_A, "", src)
src, _nb = re.subn(_B, "", src)
if _na or _nb:
    print(f"  (display: stripped {_na+_nb} client-side ISO note bank(s))")

# footer: ISO no longer used anywhere -> drop it from the data-source credit (idempotent)
src, _nf = re.subn(r"TeamRankings \(ISO &amp; HR/9\)", "TeamRankings (HR/9)", src, count=1)
# role-selection: rank by TOTAL alone (drop the 0.35 implied double-count; market already ~70% of TOTAL). Idempotent.
src, _nrank = re.subn(r"return 0\.65\*nt\+0\.35\*ni;", "return nt;", src, count=1)
if _nrank: print("  (client: strength -> TOTAL alone)")
# builders = the moon/salami ANCHORS plus any anchor-eligible bat at least as strong as the
# weakest shipped anchor (passed over only on game-time fit). Emitted client-side from the
# drafted tickets in `out` + candidate anchors `candA`. Replaces any prior variant. Idempotent.
_BLD_NEW = ("(function(){var par=out.filter(function(t){return t.kind==='moon'||t.kind==='biggest';});var usedN={};par.forEach(function(t){(t.players||t.legs||[]).forEach(function(l){usedN[l.name]=1;});});var lf=Infinity;par.forEach(function(t){(t.players||t.legs||[]).forEach(function(l){var s=strength(l.name);if(s<lf)lf=s;});});if(lf===Infinity)lf=-1;var done={};par.forEach(function(t){if(t.anchor&&!done[t.anchor]&&P[t.anchor].odds!=null&&P[t.anchor].odds<=600){done[t.anchor]=1;mkF('builder','\\uD83D\\uDCB0',[t.anchor]);}});byS(nonchalk).forEach(function(n){if(usedN[n]||done[n])return;if(strength(n)>=lf-1e-9&&P[n].odds!=null&&P[n].odds<=600){done[n]=1;mkF('builder','\\uD83D\\uDCB0',[n]);}});})();")
_blines = src.split("\n"); _ncap = 0
for _i, _ln in enumerate(_blines):
    if "mkF('builder'," in _ln and ("byS(nonchalk" in _ln or "var seen" in _ln or "var anc" in _ln):
        _new = _ln[:len(_ln) - len(_ln.lstrip())] + _BLD_NEW
        if _blines[_i] != _new:
            _blines[_i] = _new; _ncap += 1
src = "\n".join(_blines)
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
