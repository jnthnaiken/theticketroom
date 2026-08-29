"""
LOCKEVICT-2026-08-29 -- a slip the board killed for chalk came back through a viewer's browser.

    owner: "yordan is still a single. he was in the ban at the time everyone locked"
    owner: "i know what im doing. i did multiple hard refreshes. im not retarded"

He was right and I was wrong twice. I told him it was a stale tab and then a cache. It is
neither, and a hard refresh CANNOT fix it, because the thing that puts the slip back survives a
hard refresh: localStorage.

MEASURED, on the live site, just now:

    what the server publishes (fetched /mlb/ fresh, parsed the baked `const D=`):
        14 tickets. NO Sea Legs. meta.chalk = Alonso / Olson / Caminero / Schwarber.

    what the same page holds after the engine runs:
        15 tickets. Sea Legs -- Yordan Alvarez, +252, LOCKED -- rendered in the DOM.

    the extra slip comes from localStorage: hr_lock_2026-08-28 entry 14,
        sig "builder|Yordan Alvarez", t.locked true.

The archive agrees with the server and not with the screen. Alvarez has had no slip on any
committed board since 21:36Z:

    21:31Z  249  on the board   Sea Legs[L], Ballistic Arc[L], Orbital Insertion[L]
    21:36Z  249  GONE           -- CHALKOFF: he was in the top-4 shortest prices
    22:28Z-23:08Z 246-249       meta.chalk lists him, in the ban, no slips
    23:12Z onward 252           out of the ban, still no slips        <- the board is correct
    01:31Z  252  14 tickets, no Sea Legs                              <- HEAD, what is served

THE MECHANISM

LOCKPERSIST-2026-08-24 seeds `lmap` from localStorage and re-admits any stored locked ticket the
board dropped. It exists for a real reason -- before it, a locked slip lived exactly as long as
the server kept sending it. Its guards are: not a retired kind, not `chalkBanned` NOW, no dead
leg, `validT`.

"not chalkBanned NOW" is the hole. CHALKOFF's eviction is permanent for the night in the
archive, but the ban itself moves with the price, and Alvarez moved 249 -> 252 and out of it. The
guard is re-evaluated against a ban that has since changed, so the slip the board killed at 21:36
is handed back the moment his price ticks two cents the other way.

⚠️ AND THE VIEWER NEED NEVER HAVE SEEN THE EVICTION. `saveLock` writes the union of what is on
the board, so a tab that IS open through the banned window prunes the entry and is fine. A tab
that is closed at 21:36 and opened at 23:12 still holds the 21:31 entry, sees a bat who is not
chalk right now, and restores it. That is why this is invisible from the archive, invisible from
the served payload, and unaffected by any refresh: the state lives in the browser and only the
browser's own history decides whether it was cleaned.

THE FIX -- the ban is remembered for the night, and only the latch reads it

  1. `D.meta.chalkever` -- the union of every ban this slate has settled on. Accumulated from the
     board handed in, unioned with today's `chalk`, republished. regen15.py carries it across
     builds (it already carries `prevD['tickets']`; this is the same one-line idea for one meta
     key).

  2. The latch refuses a stored slip whose bat has been in the ban AT ANY POINT today. Once
     CHALKOFF has taken a slip, no later price move hands it back.

WHAT THIS IS NOT

  * NOT CHALKHYST. That patch read a stored ban as INPUT TO THE DRAFT to hold an incumbent's
    seat, which necessarily inverts the ban -- a longer price banned while a shorter one plays --
    and it is reverted. Nothing here touches the draft. `chalkever` is read in exactly one place,
    the localStorage latch, and its only possible effect is to DECLINE TO RESURRECT a slip the
    published board does not carry. The board the server publishes is byte-for-byte unchanged.

  * NOT A SECOND BAN RULE. The membership test reuses `chalkBanned`'s own dispatch rather than
    re-stating it: `chalkBannedIn(t,set)` is extracted and `chalkBanned(t)` becomes
    `chalkBannedIn(t,chalk)`. So a locked slip is still judged on its ANCHOR only
    (CHALKLOCK-2026-08-29: a placed bet is not torn up because a PARTNER went chalk) and an open
    one on any leg. One definition, two sets. Writing a second copy of that dispatch is the exact
    failure that produced most of 2026-08-28.

THE SEED, and its honest limit

`chalkever` accumulates forward, so tonight's board would start empty and Sea Legs would keep
coming back for the rest of the slate. seed_chalkever.py bakes the union OBSERVED IN THE ARCHIVE
into the published board's meta so the fix bites now:

    Pete Alonso(44) Matt Olson(44) Kyle Schwarber(44) Junior Caminero(32)
    Yordan Alvarez(8) Christian Encarnacion-Strand(3) Coby Mayo(1)

⚠️ That is the union over the 44 builds that carry `meta.chalk` -- CHALKOBS-2026-08-28 only
shipped at 21:36Z, so the 62 earlier builds of this slate contribute nothing. The seed is
UNDER-inclusive, not over-. It is not recomputed from prices: recomputing the ban here would be a
second implementation of the rule, which is the thing to avoid. From tomorrow the union is
complete by construction.

Of the seven, six (Alonso, Olson, Schwarber, Caminero, Encarnacion-Strand, Mayo) hold slips that
are ON the served board right now, so the latch never looks at them -- `_pSig` short-circuits
first. Only Alvarez has a stored slip the board does not carry. The seed changes exactly one
thing on the screen, which is the thing the owner is looking at.

Line comments are forbidden inside index.html's script block (2026-08-08: a `//` swallowed a
`var` declaration and cost a live slate) -- block comments only below.
"""
import sys

BOARD = 'index.html'
src = open(BOARD, encoding='utf-8').read()

# ---------------------------------------------------------------------------- 1. one dispatch, two sets
OLD_FN = ("""    function chalkBanned(t){ var lg=(t&&t.players)||[];
      if(t&&t.locked) return !!(lg.length&&chalk[lg[0].name]);
      for(var i=0;i<lg.length;i++){ if(chalk[lg[i].name]) return true; } return false; }""")

NEW_FN = ("""    function chalkBannedIn(t,set){ var lg=(t&&t.players)||[];
      if(t&&t.locked) return !!(lg.length&&set[lg[0].name]);
      for(var i=0;i<lg.length;i++){ if(set[lg[i].name]) return true; } return false; }
    /* LOCKEVICT-2026-08-29: the dispatch above is EXTRACTED, not duplicated. `chalkBanned` is the
       live ban; the localStorage latch asks the same question of `_chalkEver`, the union of every
       ban this slate has settled on. Two sets, one rule -- a locked slip is judged on its ANCHOR
       (CHALKLOCK-2026-08-29: a placed bet is not unwound because a PARTNER went chalk), an open
       one on any leg. A second copy of this dispatch is how 2026-08-28 happened. */
    function chalkBanned(t){ return chalkBannedIn(t,chalk); }""")

# ---------------------------------------------------------------------------- 2. publish the union
OLD_OBS = "    if(D.meta)D.meta.chalk=Object.keys(chalk);"
NEW_OBS = ("""    if(D.meta)D.meta.chalk=Object.keys(chalk);
    /* LOCKEVICT-2026-08-29 -- THE BAN, REMEMBERED FOR THE NIGHT. The union of every ban this
       slate has settled on: what came in on the board, plus today's. Read in exactly ONE place,
       the localStorage latch below, where its only power is to DECLINE TO RESURRECT a slip the
       published board does not carry. No draft decision reads it and the published board is
       unchanged by it.
       Why it has to exist: CHALKOFF's eviction is permanent in the archive but the ban moves with
       the price. Yordan Alvarez was in the top-4 at 21:36Z and his three slips died; by 23:12Z he
       was 252 and out of it. A tab that was CLOSED through that window still held the 21:31 lock
       entry, saw a bat who is not chalk right now, and put "Sea Legs" back on a board the server
       had published without it -- through every hard refresh, because localStorage survives one.
       NOT CHALKHYST, which fed a stored ban back into the DRAFT to hold an incumbent's seat and
       thereby inverted the ban. This never reaches the draft. */
    var _prevEver=(D.meta&&D.meta.chalkever)||[];
    for(var _ce=0;_ce<_prevEver.length;_ce++)_chalkEver[_prevEver[_ce]]=1;
    Object.keys(chalk).forEach(function(_cn){_chalkEver[_cn]=1;});
    if(D.meta)D.meta.chalkever=Object.keys(_chalkEver);""")

# ---------------------------------------------------------------------------- 3. the latch honours it
OLD_LATCH = ("      if(retiredKind(t.kind) || chalkBanned(t) || !legs.length || !validT(t)) return;"
             "   /* a locked dinger in a viewer's localStorage must not re-admit a retired kind */")
NEW_LATCH = ("""      /* LOCKEVICT-2026-08-29: `chalkBannedIn(t,_chalkEver)` and not `chalkBanned(t)`. Once
         CHALKOFF has taken a slip it is gone for the night; a later price move must not hand it
         back. The old guard asked whether the bat is chalk RIGHT NOW, and Alvarez went 249 -> 252
         and back out of the ban, so a tab that missed the eviction restored a slip the archive
         killed at 21:36Z and the server has not published since. Refusing it here also prunes it:
         `lmap` below is built from `prior`, so an entry that is not re-admitted is not re-saved.
         A slip that is STILL on the board never reaches this line -- `_pSig` above returns first
         -- so a bat who merely dipped into the ban keeps everything he actually holds. */
      if(retiredKind(t.kind) || chalkBannedIn(t,_chalkEver) || !legs.length || !validT(t)) return;   /* a locked dinger in a viewer's localStorage must not re-admit a retired kind */""")

# `_chalkEver` is assigned at the CHALKOBS site and read ~180 lines later in the latch; declare it
# up front with the other engine-wide maps so the read is never a hoisting accident.
OLD_DECL = "    var _killed={};"
NEW_DECL = ("    var _killed={};\n"
            "    var _chalkEver={};   /* LOCKEVICT-2026-08-29: filled at the CHALKOBS publish below, read by the localStorage latch */")

for old, new, label in ((OLD_FN,    NEW_FN,    'extract chalkBannedIn(t,set)'),
                        (OLD_DECL,  NEW_DECL,  'declare _chalkEver'),
                        (OLD_OBS,   NEW_OBS,   'publish D.meta.chalkever'),
                        (OLD_LATCH, NEW_LATCH, 'the latch reads the night-long ban')):
    n = src.count(old)
    if n != 1:
        sys.exit(f"ABORT: expected exactly 1 occurrence of [{label}], found {n} -- "
                 f"the source moved, patch by hand")
    src = src.replace(old, new, 1)
    print(f"  patched {label}")

for bad, why in (('function chalkBanned(t){ var lg', 'the old body survived'),
                 ('chalkBannedIn(t,chalk)) return;', 'the latch is still on the live ban')):
    if bad in src:
        sys.exit(f'ABORT: {why} -- patch by hand')

open(BOARD, 'w', encoding='utf-8').write(src)
print(f"wrote {BOARD} ({len(src)} bytes)")
