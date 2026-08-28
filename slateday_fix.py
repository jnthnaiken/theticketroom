"""
SLATEDAY-2026-08-28 -- the draft engine read the BAKED board, not the one it was handed.

`_slateDay()` lives at module scope in index.html's script block and closes over the page's own
`const D`. `started()` inside assembleClient() calls it. In a browser that is correct and always
was: the page calls `__assembleClient(D)` with that very object, and the ADOPT-2026-08-16 refresh
mutates it in place, so the two never diverge.

Server-side they DO diverge. regen15.py injects the freshly drafted board into index.html AFTER
the draft, so at draft time the baked board is still YESTERDAY'S. On the first build of a new
slate date `_slateDay()` therefore compares today against yesterday's date, returns 1, and
`started()` goes true for EVERY bat regardless of first pitch:

    var draftPool = nonchalk.filter(function(n){ return !usedG[n] && !started(n); });

draftPool empties -> candA empties -> searchBest returns null -> `out` is empty ->
client_assemble.js exits 67 ("engine returned 0 tickets -- refusing to write") -> regen15.py
falls back to assemble_tickets.py, which drafts from scratch with no prior-board lock and still
builds a retired Grand Salami.

Measured on 2026-08-28, same D, only the baked date differing:

    baked 2026-08-27:  slateDay=1  nonchalk=47  started=47  draftPool=0   ->  0 tickets
    baked 2026-08-28:  slateDay=0  nonchalk=47  started=0   draftPool=47  -> 14 tickets
                                                             {moon 8, builder 4, lunch 1, late 1}

The board that shipped was 13 tickets, moon 6 + biggest 1, and every later build re-derived off
it down to 5 tickets with one anchor carrying both moons.

replay_check.js has the same blind spot from the other side: it loads the engine from the CURRENT
index.html and replays archived boards against a fixed clock, so `_td < D.meta.date` and
`_slateDay()` returns -1 -> `started()` is ALWAYS false for every replayed build. That is why
1,075 chained builds never caught this.

THE FIX (both call sites, one behaviour change, none of it in the browser)

  1. `_slateDay(B)` takes the board to measure, defaulting to the baked `D`. Every existing
     caller -- hasStarted(), likelyEnded() -- is byte-for-byte unchanged in behaviour.
  2. `started()` inside assembleClient passes `D`, which there is the FUNCTION PARAMETER and
     shadows the module-level const.

In the browser assembleClient is invoked with the module-level board, so `_slateDay(D)` is
identical to `_slateDay()` and this patch is a provable no-op. Server-side and in replay_check
the engine now measures the board it is actually drafting.

Line comments are forbidden inside this script block (2026-08-08: a `//` swallowed a `var`
declaration and cost a live slate) -- everything below uses /* */.
"""
import re, sys

BOARD = 'index.html'
src = open(BOARD, encoding='utf-8').read()

OLD_SLATEDAY = ("function _slateDay(){try{var _td=new Date().toLocaleDateString('en-CA',"
                "{timeZone:'America/New_York'});if(D.meta&&D.meta.date){if(_td<D.meta.date)"
                "return -1;if(_td>D.meta.date)return 1;}}catch(e){}return 0;}")

NEW_SLATEDAY = ("function _slateDay(B){/* SLATEDAY-2026-08-28: measure the board we were GIVEN. "
                "Defaults to the baked board so hasStarted()/likelyEnded() are unchanged; "
                "assembleClient passes its own D, which server-side is NOT the baked one. */"
                "B=B||D;try{var _td=new Date().toLocaleDateString('en-CA',"
                "{timeZone:'America/New_York'});if(B.meta&&B.meta.date){if(_td<B.meta.date)"
                "return -1;if(_td>B.meta.date)return 1;}}catch(e){}return 0;}")

OLD_STARTED = ("function started(n){var m=tmin(n); if(m==null)return false; "
               "var _d=_slateDay();if(_d)return _d>0; return nowMin()>=m;}")

NEW_STARTED = ("function started(n){var m=tmin(n); if(m==null)return false; "
               "/* SLATEDAY-2026-08-28: _slateDay(D) -- D here is assembleClient's PARAMETER and "
               "shadows the baked board. regen15.py injects after the draft, so on the first build "
               "of a new slate date the baked date is yesterday's; reading it marked every bat "
               "started, emptied the draft pool and dropped the board onto the "
               "assemble_tickets.py fallback. */"
               "var _d=_slateDay(D);if(_d)return _d>0; return nowMin()>=m;}")

for old, new, label in ((OLD_SLATEDAY, NEW_SLATEDAY, '_slateDay'),
                        (OLD_STARTED, NEW_STARTED, 'started')):
    n = src.count(old)
    if n != 1:
        sys.exit(f"ABORT: expected exactly 1 occurrence of {label}, found {n} -- "
                 f"the source moved, patch by hand")
    src = src.replace(old, new, 1)
    print(f"  patched {label}")

open(BOARD, 'w', encoding='utf-8').write(src)
print(f"wrote {BOARD} ({len(src)} bytes)")
