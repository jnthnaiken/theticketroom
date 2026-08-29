"""
LOCKEVICT-2026-08-29 (part 2) -- seed tonight's `meta.chalkever`, and carry it across builds.

`chalkever` accumulates FORWARD. Left to itself it would start empty on the next build, so
"Sea Legs" would keep being restored from viewers' localStorage for the rest of tonight's slate --
which is the board the owner is looking at right now. So it is seeded once, here, from the
archive, and then carried.

TWO EDITS.

1. regen15.py -- CARRY IT. `prevD` is the published board, already read for `carryover()` and
   already the source of `D['tickets']` on a same-slate build. `meta` is NOT carried: it comes
   fresh from build15's D_0615.json every time. So without this line the union resets every five
   minutes and remembers nothing.

   Guarded by `_same_slate`, the same condition that governs handing over the prior tickets: a
   ban belongs to ONE slate. A new date starts with an empty union, which is correct.

2. index.html -- SEED IT, into the published board's own baked `const D=` block, so the very next
   build reads it back as `prevD` and the chain starts.

   The seeded value is the union of `meta.chalk` OBSERVED ACROSS THE COMMITTED ARCHIVE of this
   slate. ⚠️ CHALKOBS-2026-08-28 only shipped at 21:36Z, so 44 of the day's 106 builds carry the
   field and the other 62 contribute nothing. The seed is therefore UNDER-inclusive. It is NOT
   recomputed from prices -- recomputing the ban here would be a second implementation of the
   rule, which is the failure mode that produced most of 2026-08-28. An under-inclusive seed
   restores fewer evicted slips than perfect knowledge would; an invented one could delete a slip
   that was never banned. From the next slate the union is complete by construction.

       Pete Alonso 44   Matt Olson 44   Kyle Schwarber 44   Junior Caminero 32
       Yordan Alvarez 8   Christian Encarnacion-Strand 3   Coby Mayo 1

   Six of those seven hold slips that are on the served board right now, so the latch never
   examines them (`_pSig` returns first). Only Alvarez has a stored slip the board does not carry.

THE PUBLISHED BOARD IS NOT REDRAFTED. This writes one key into meta. `D.tickets` is untouched,
byte for byte -- verified below by comparing the ticket block before and after.
"""
import json, sys

EVER = ["Pete Alonso", "Matt Olson", "Kyle Schwarber", "Junior Caminero",
        "Yordan Alvarez", "Christian Encarnacion-Strand", "Coby Mayo"]

# ------------------------------------------------------------------ 1. regen15.py carries it
R = 'regen15.py'
rsrc = open(R, encoding='utf-8').read()

OLD_R = """if _same_slate:
    D['tickets'] = prevD['tickets']            # hand the prior board to the engine AS PRIOR -> it locks the confirmed ones
    print(f"  (same slate -> {len(D['tickets'])} prior tickets handed to the draft engine)")"""

NEW_R = """if _same_slate:
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
        print(f"  (carried the night's chalk union: {len(_ever)} bat(s))")"""

n = rsrc.count(OLD_R)
if n != 1:
    sys.exit(f"ABORT: expected exactly 1 same-slate block in {R}, found {n}")
open(R, 'w', encoding='utf-8').write(rsrc.replace(OLD_R, NEW_R, 1))
print(f"  patched {R}: carry meta.chalkever across builds of the same slate")

# ------------------------------------------------------------------ 2. seed the published board
B = 'index.html'
src = open(B, encoding='utf-8').read()
i = src.index('const D={')
D, end = json.JSONDecoder().raw_decode(src, i + len('const D='))

if (D.get('meta') or {}).get('date') != '2026-08-28':
    sys.exit(f"ABORT: the published board is {(D.get('meta') or {}).get('date')}, not 2026-08-28 -- "
             f"the slate rolled over, drop the seed and let the union accumulate on its own")

before = json.dumps(D.get('tickets'), sort_keys=True)
have = set((D.get('meta') or {}).get('chalkever') or [])
D.setdefault('meta', {})['chalkever'] = sorted(have | set(EVER))
after = json.dumps(D.get('tickets'), sort_keys=True)
if before != after:
    sys.exit('ABORT: the ticket block changed -- this seed must touch meta only')

# re-emit exactly the way regen15.py does it (line 147: ensure_ascii=True, default separators),
# so the injected block is byte-identical in shape to what every build writes.
src = src[:i] + 'const D=' + json.dumps(D, ensure_ascii=True) + src[end:]
open(B, 'w', encoding='utf-8').write(src)
print(f"  seeded {B}: meta.chalkever = {len(D['meta']['chalkever'])} bat(s); "
      f"{len(D['tickets'])} tickets unchanged")
print(f"wrote {B} ({len(src)} bytes)")
