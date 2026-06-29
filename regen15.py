"""
The Ticket Room — assemble + inject step.

Runs AFTER the scorer (build15.py) has written D_0615.json = {players, meta}.
1) builds D['tickets'] via assemble_tickets.assemble() (pool gating, refill, names,
   notes — the brain), carrying over any game left suspended on the prior board,
2) injects the freshly assembled D into the published board's `const D=...` block.

The published index.html doubles as its own shell/template: we read it, swap the
data block, and write it back. All paths are repo-relative so it runs on the Action.
"""
import json, re, time, os, hashlib
import assemble_tickets

# Bump when the DRAFT RULES change (pool gate, caps, anchor logic). Folding this into the
# input signature forces exactly one re-draft on the next build so a rules change actually
# takes effect, then same-input rebuilds preserve as usual.
RULES_VERSION = "2026-06-29-drop-iso-power30"

BOARD = "index.html"       # published board == its own shell/template
DJSON = "D_0615.json"      # scorer output; assembled in place, then injected

D = json.load(open(DJSON))
for p in D.get('players', {}).values():        # assembler reads these flags
    p.setdefault('void', False); p.setdefault('out', False)

def _input_sig(Dd):
    """Fingerprint of the INPUT data the draft is built from (cards + ISO + odds),
    independent of live weather/HR9 (which drift every 30-min rebuild). Same inputs ->
    same sig -> preserve the prior draft (no reshuffle of locked tickets). New inputs
    committed (a fresh slate, corrected cards, updated odds) -> sig changes -> re-draft."""
    P = Dd.get('players', {})
    rows = [RULES_VERSION]
    for n in sorted(P):
        p = P[n]
        rows.append('|'.join(str(x) for x in (
            n, p.get('aT'), p.get('zonev'), p.get('form'), p.get('pb'),
            p.get('hh'), p.get('la'), p.get('iso_used'), p.get('odds'))))
    return hashlib.md5('\n'.join(rows).encode('utf-8')).hexdigest()

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

# PRESERVE the prior board across same-slate rebuilds -- but ONLY when the INPUTS are unchanged.
# A fresh assemble() each rebuild re-picks anchors as weather/strength drift and reshuffles
# confirmed/locked tickets, so a routine 30-min rebuild (same cards/odds, only weather moved)
# must keep the prior draft and let the live client engine do the leg-level confirm/scratch refill.
# BUT a build where the INPUT data changed (a brand-new slate, corrected cards, updated odds --
# detected by the input signature) MUST re-draft, or new inputs silently inherit the old tickets.
# Draft fresh when: no prior, a different date, or the input signature changed.
_cur_sig = _input_sig(D)
D.setdefault('meta', {})['sig'] = _cur_sig
_prev_sig = (prevD.get('meta') or {}).get('sig') if prevD else None
_same_slate = bool(prevD and (prevD.get('meta') or {}).get('date') == (D.get('meta') or {}).get('date')
                   and prevD.get('tickets') and _prev_sig == _cur_sig)
if _same_slate:
    D['tickets'] = prevD['tickets']            # same inputs -> carry the prior draft forward unchanged; client handles live confirm/scratch/grade
    D.setdefault('meta', {})['tickets'] = len(D['tickets'])
    print(f"  (same slate + unchanged inputs -> preserved {len(D['tickets'])} prior tickets; no re-draft)")
else:
    assemble_tickets.assemble(D)               # brand-new slate / different date / inputs changed -> fresh draft
    print(f"  (fresh draft: prev_sig={str(_prev_sig)[:8]} cur_sig={_cur_sig[:8]})")
json.dump(D, open(DJSON, 'w'), indent=1)       # persist the assembled board data (handoff name)
_dt = (D.get('meta') or {}).get('date')
if _dt:
    json.dump(D, open(f"D_{_dt}.json", 'w'), indent=1)   # dated archive (with tickets) -> grade_night folds it next morning

src = open(BOARD).read()
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
