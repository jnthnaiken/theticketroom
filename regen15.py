"""
The Ticket Room — assemble + inject step.

Runs AFTER the scorer (build15.py) has written D_0615.json = {players, meta}.
1) builds D['tickets'] via assemble_tickets.assemble() (pool gating, refill, names,
   notes — the brain), carrying over any game left suspended on the prior board,
2) injects the freshly assembled D into the published board's `const D=...` block.

The published index.html doubles as its own shell/template: we read it, swap the
data block, and write it back. All paths are repo-relative so it runs on the Action.
"""
import json, re, time
import assemble_tickets

BOARD = "index.html"       # published board == its own shell/template
DJSON = "D_0615.json"      # scorer output; assembled in place, then injected

D = json.load(open(DJSON))
for p in D.get('players', {}).values():        # assembler reads these flags
    p.setdefault('void', False); p.setdefault('out', False)

# carry any suspended game from the previously published board into today, then assemble
try:
    m = re.search(r'const D=(\{.*?\}),WX=D\.meta\.wx;', open(BOARD).read(), re.S)
    if m:
        assemble_tickets.carryover(D, json.loads(m.group(1)))
except Exception as e:
    print(f"  (carryover skipped: {e})")

assemble_tickets.assemble(D)                   # builds D['tickets']
json.dump(D, open(DJSON, 'w'), indent=1)       # persist the assembled board data

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
