"""
CHALKPLACED-2026-08-28 -- a rule written for the CHEF SEAT is silently gutting the CHALK BAN.

WHAT THE OWNER ASKED
    "is this the correct draft or did people get left off on some bullshit again?"

He did, and this is the bullshit. One man, by one cent.

WHAT THE BOARD LOOKED LIKE

    #1  +205  Pete Alonso                    banned
    #2  +208  Matt Olson                     banned
    #3  +230  Kyle Schwarber                 banned
    #4  +249  Yordan Alvarez                 ANCHORING -- 2 moons and a builder
    #5  +250  Christian Encarnacion-Strand   BANNED, off the board entirely

The ban is "the CHALK_N shortest prices". It had the fourth-shortest price on the board leading
two moons, and banned the fifth instead. Instrumented on the live board, the chalk fill loop
prints its own answer:

    4 Yordan Alvarez +249  chalk=false  placedLeg=TRUE   <- skipped
    5 Christian Encarnacion-Strand +250  chalk=true      <- takes the seat instead

THE RULE DOING IT, AND WHY IT IS IN THE WRONG PLACE

ONE BAT, ONE SLIP (2026-08-13), in its own words:

    "`chalk` is a per-build SNAPSHOT of the CHALK_N chef seats ... A placed bet is a fact and the
     chef seat is still open, so the OPEN thing moves: a bat already on a placed parlay is not
     chef-eligible."

That is correct reasoning about a seat a bat GETS. The Chef's Table handed a bat a slip, and a bat
already riding a placed parlay should not also be handed a chef seat -- otherwise the board shows
one bat on two slips, which is the bug it was written for (Contreras, 08-13).

The Chef's Table was retired on 2026-08-14. The same `chalk` map now means the exact opposite
thing: not a seat you get, a seat you are BARRED from. And the reasoning inverts with it. Skipping
a placed bat no longer protects him from double-booking; it lets the SHORTEST PRICE ON THE SLATE
keep anchoring and drops the ban onto a longer one. The ban's whole purpose -- keep the shortest
prices off the parlays -- is defeated by the one bat most likely to trigger it, because a bat whose
price is shortening is exactly the bat whose slips confirm early.

It also makes CHALKOFF-2026-08-26 unreachable for the bats it was written about. The owner then:

    "yea no if he's in the top 4 ban he needs to be taken off."
    "i dont care if they are locked."

CHALKOFF evicts a locked chalk slip. `_placedLeg` guarantees a locked bat never becomes chalk. The
newer rule cannot fire on the case the older one has already removed -- the same shape as
CHALKSEAT-2026-08-28 earlier tonight, an older rule quietly disabling a newer one.

THE FIX

Confine the skip to `CHEF_TICKET`, the flag that gates the retired slip it was written for. With
CHEF_TICKET off (today) the chalk ban is what it says on the tin: the CHALK_N shortest prices, full
stop. Flip CHEF_TICKET back on and the 08-13 behaviour returns exactly, because the guard is still
there behind it. `_chefKeep` and `pending()` are untouched -- a suspended bat is still not
bannable, which is about data quality, not about who has already bet.

THE COST, WHICH IS REAL AND WHICH THE OWNER HAS ALREADY RULED ON

Alvarez's builder and both his moons had locked. They come off. CHALKOFF's own comment states the
tradeoff and accepts it: "A REMOVED SLIP DOES NOT GRADE. That is the owner's explicit call, and it
is the one real cost: if the slip was placed before the bat became chalk, the ledger will not see
it." This is precisely that case.

MEASURED on the live 2026-08-28 board:

    before   14 tickets, 4 anchors -- Goodman, Murakami, Mayo, ALVAREZ(+249, 4th shortest)
    after    14 tickets, 4 anchors -- Goodman, Murakami, Mayo, ENCARNACION-STRAND(+250)
             every one of the four shortest prices off the board, which is the rule

Line comments are forbidden inside this script block (2026-08-08: a `//` swallowed a `var`
declaration and cost a live slate) -- everything below uses the block form.
"""
import sys

BOARD = 'index.html'
src = open(BOARD, encoding='utf-8').read()

OLD = "      if(_chefKeep[_ccn]||_placedLeg[_ccn]||pending(_ccn))continue;"

NEW = ("      /* CHALKPLACED-2026-08-28: `_placedLeg` is ONE BAT, ONE SLIP (2026-08-13), and that\n"
       "         rule is about a seat a bat GETS -- do not hand a chef slip to a bat already riding a\n"
       "         placed parlay. `chalk` stopped meaning that on 2026-08-14 when the chef slip was\n"
       "         retired; it now means BARRED. Skipping a placed bat here does not protect him, it\n"
       "         lets the shortest price on the slate keep anchoring and drops the ban on a longer\n"
       "         one -- 2026-08-28: Alvarez +249 leading two moons while Encarnacion-Strand +250 was\n"
       "         banned. It also made CHALKOFF-2026-08-26 unreachable for exactly the bats it was\n"
       "         written about (\"i dont care if they are locked\"), because a locked bat could never\n"
       "         become chalk in the first place. Confined to CHEF_TICKET so flipping that flag back\n"
       "         on restores 08-13 behaviour exactly. */\n"
       "      if(_chefKeep[_ccn]||(CHEF_TICKET&&_placedLeg[_ccn])||pending(_ccn))continue;")

n = src.count(OLD)
if n != 1:
    sys.exit(f"ABORT: expected exactly 1 occurrence of the chalk fill guard, found {n} -- "
             f"the source moved, patch by hand")
src = src.replace(OLD, NEW, 1)
print("  patched chalk fill guard -> _placedLeg confined to CHEF_TICKET")

open(BOARD, 'w', encoding='utf-8').write(src)
print(f"wrote {BOARD} ({len(src)} bytes)")
