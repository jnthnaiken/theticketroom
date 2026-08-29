"""
MINTLOCK-2026-08-29 -- MINTGUARD's sibling kill unwound a PLACED BET.

WHAT IT COST, on the live board, tonight

    23:08  Murakami anchoring two moons, all three of his slips LOCKED.
    23:12  Caminero 258 -> 231, into the top-4 ban. Nobody else on either slip moved a cent.
           Both moons gone. Murakami left leading nothing for sixteen builds.

THE CHAIN, every step measured

  1. Caminero was a LEG on "The Way Back Machine". He went chalk, so CHALKOFF evicted that slip.
     That part is right and the owner ruled on it ("i dont care if they are locked").
  2. The repair minted Murakami a replacement moon, "Beyond the Bleachers", lock 7:10 PM ET.
  3. It was already 7:12 PM ET. MINTGUARD killed the new slip -- also right; you cannot mint a
     slip past its own first pitch.
  4. And then this:

         var _anch={}; _late.forEach(function(t){ if(t.kind==='moon'&&t.anchor)_anch[t.anchor]=1; });
         out.forEach(function(t){ if(t.kind==='moon'&&t.anchor&&_anch[t.anchor])_kill[t.name]=1; });

     Every OTHER moon of that anchor is killed too. No exemption for a locked one. So
     "Climbing the Ladder" -- Murakami + Chaparro + Bauers, carrying no chalk bat, nobody
     scratched, LOCKED, a placed bet -- was deleted because its SIBLING was minted too late.

         [latedbg] late=["Beyond the Bleachers/7:10 PM ET"]  kill=["Beyond the Bleachers",
                                                                   "Climbing the Ladder"]

THE RULE IT BREAKS, which the file already states twice

The all-or-none pair filter, forty lines earlier, does the same job and gets it right:

    // the anchor is demoted -- ALL its (non-locked) moons are dropped ...
    // Locked moons (placed bets) are never dropped.
    out=out.filter(function(t){ if(t.kind!=='moon'||t.locked)return true; ... });

Never showing a single-moon anchor is a display preference. Not unwinding a placed bet is a
money rule. Where they collide the money rule wins, and everywhere else in this engine it does.
This one path just never got the exemption.

THE FIX

Exempt locked moons from the sibling kill, in the same words the pair filter uses. The
too-late-minted slip still dies -- MINTGUARD is untouched. The anchor may be left showing one
moon, which is exactly the outcome the pair filter already accepts for a locked pair, and is
strictly better than deleting a bet somebody has struck.

VERIFIED on the real 23:08 -> 23:12 transition, prior and data both out of git:
    before   "Climbing the Ladder" GONE
    after    "Climbing the Ladder" SURVIVES, still locked, legs untouched

Block comments only -- 2026-08-08, a `//` swallowed a `var` declaration and cost a live slate.
"""
import sys
BOARD='index.html'
src=open(BOARD,encoding='utf-8').read()

OLD = """      out.forEach(function(t){ if(t.kind==='moon'&&t.anchor&&_anch[t.anchor])_kill[t.name]=1; });"""
NEW = """      /* MINTLOCK-2026-08-29: NOT A LOCKED ONE. Killing the anchor's other moons enforces
         all-or-none when a slip is minted past its own first pitch -- but a LOCKED moon is a
         placed bet, and this path was unwinding one because its SIBLING was late. 2026-08-28
         23:12Z: Caminero drifted into the ban, CHALKOFF evicted the moon he was a leg on, the
         repair minted "Beyond the Bleachers" at 7:10 PM with the clock already at 7:12, and the
         kill took "Climbing the Ladder" with it -- no chalk bat, nobody scratched, locked, and
         struck. The pair filter above already draws this line in these words: "Locked moons
         (placed bets) are never dropped." Never showing a single-moon anchor is a display
         preference; not unwinding a placed bet is a money rule. */
      out.forEach(function(t){ if(t.kind==='moon'&&t.anchor&&_anch[t.anchor]&&!t.locked)_kill[t.name]=1; });"""

n=src.count(OLD)
if n!=1:
    sys.exit(f"ABORT: expected exactly 1 occurrence, found {n} -- patch by hand")
src=src.replace(OLD,NEW,1)
print('  patched: the sibling kill no longer unwinds a locked moon')
open(BOARD,'w',encoding='utf-8').write(src)
print(f'wrote {BOARD} ({len(src)} bytes)')
