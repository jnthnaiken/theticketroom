#!/usr/bin/env python3
"""nfl_live_seams.py -- wire nfl_live.js into the football board.

NFLLIVE-2026-09-09. Owner: "the board should function just like the other two."

nfl_fork.py's 'liveloop' seam killed index.html's MLB live loop on 2026-09-03 and put a stub in
its place. That was correct and incomplete: it left the football room with NO results feed at
all, so `D.meta.finals` had no producer, nothing ever settled, and the only thing that ever
wrote it was a foreign localStorage snapshot leaking across the shared origin
(SNAPSHOTKEY-2026-09-09). This module supplies the missing half.

STRUCTURED EXACTLY LIKE soccer_live_seams.py, on purpose. Three rooms with three shapes of live
wiring is how they drift; three rooms with one shape is how a fix in any of them is portable.

  MODIFIED IN PLACE (count unchanged -- nfl_fork.py passes LIVELOOP_NEW to its existing seam):
      liveloop         the stub becomes the real boot + timer
  ADDED HERE (LIVE_SEAM_COUNT):
      livebtn-onclick  the button relabelled 'Update from ESPN' still CALLED liveUpdate()
      debug-handles    window.__liveUpdate / window.__assembleClient were still exported
      live-inject      nfl_live.js + the page glue

⚠️ TWO OF THOSE THREE ARE NOT NEW FEATURES, THEY ARE THE LIVEBTN-2026-08-26 BUG, SHIPPED AGAIN.
nfl_fork.py's 'live-btn' seam relabels the operator console's button from "Update from MLB" to
"Update from ESPN" -- and nothing repointed it. So the football board has been shipping a button
that promises ESPN and actually calls MLB's liveUpdate(): statsapi.mlb.com, api.open-meteo.com,
and then a RE-DRAFT of the football slate with baseball constants (GAME_CAP / CHALK_N / WIN=120
/ precipOf). The soccer fork made this exact mistake, wrote it down at length, and the note ends
"relabelling a control without repointing it is worse than leaving it alone." It was then copied
into this fork without the fix.

`window.__liveUpdate` and `window.__assembleClient` are the fourth door from DEBUGHANDLES-
2026-08-26: nothing on the page reaches them, so they are a footgun rather than a bug, and they
go for the same reason -- the honest answer to "can this board re-draft a live ticket?" is to
remove the path, not to explain why nobody would take it.

Grep for CALL SITES, not for the loop.
"""
import io, os

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- replacement for an EXISTING seam (modified, not added -> count unchanged) ------------

LIVELOOP_NEW = (
    "nflLive(); setInterval(nflLive, 3*60*1000)"
    "   /* NFLLIVE-2026-09-09: MLB's liveUpdate stays dead (StatsAPI + a baseball re-draft). "
    "This is the football loop: ESPN in; finals/gs/hr/out/status out; refreshAll(); no draft, "
    "no grading, no adoption. */"
)

GLUE = r"""
/* NFLLIVE-2026-09-09 -- page glue. Binds the module above to the board's own fetch, status line
   and renderer. Fails soft: any throw leaves the baked board exactly as it is, which is the
   property that makes a live loop safe to run against a board carrying real money. */
function nflLive(){
  try{
    if(typeof NflLive==='undefined'||typeof D==='undefined') return Promise.resolve();
    if(!nflLive._i){
      nflLive._unmatched=[];
      nflLive._i=NflLive.makeLive({
        D:D,
        unmatched:nflLive._unmatched,
        fetchJSON:function(u){
          return fetch(u,{cache:'no-store'}).then(function(r){
            if(!r.ok) throw new Error('http '+r.status);
            return r.json();
          });
        },
        stamp:(typeof stamp==='function'?stamp:function(){}),
        render:(typeof refreshAll==='function'?refreshAll:function(){})
      });
    }
    return nflLive._i.run();
  }catch(e){ return Promise.resolve(); }
}
if(typeof window!=='undefined'){ window.__nflLive=nflLive; }
"""


def live_seams():
    """The seams this module adds. APPEND THESE LAST -- live-inject must be injected at the
    same (final) position, so nothing is counted after it."""
    js = io.open(os.path.join(HERE, 'nfl_live.js'), encoding='utf-8').read()
    S = []

    # ---- THE THIRD DOOR: the operator console's manual button -----------------------------
    # See the module docstring. The label already said ESPN; the wire still went to MLB.
    S.append((
        'livebtn-onclick',
        "d.querySelector('#livebtn').onclick=function(){liveUpdate();};",
        "d.querySelector('#livebtn').onclick=function(){nflLive();};",
        1))

    # ---- THE FOURTH DOOR: the console debug handles ---------------------------------------
    # DEBUGHANDLES-2026-08-26. The backtest harness (backtest_true_draft.js) runs against the
    # MLB board, which keeps its handles; this fork has no harness that wants them.
    S.append((
        'debug-handles',
        "if(typeof window!=='undefined'){ window.__assembleClient=assembleClient; "
        "window.__liveUpdate=liveUpdate; window.__confirmResults=confirmResults; }",
        "/* NFL: MLB's console handles are NOT exported. __assembleClient re-drafts with "
        "baseball constants and __liveUpdate fetches StatsAPI -- neither has a caller on this "
        "board and neither should have a console one either. window.__nflLive is exported by "
        "the glue instead. See nfl_live_seams.py 'debug-handles'. */",
        1))

    # ---- THE LOOP ITSELF -- MUST BE LAST --------------------------------------------------
    # Function declarations hoist, so nflLive() is callable from the boot line below it.
    S.append((
        'live-inject',
        'function liveUpdate(){',
        '/* ==== nfl_live.js (injected by nfl_live_seams.py) ==== */\n'
        + js + GLUE +
        '/* ==== end nfl_live.js ==== */\nfunction liveUpdate(){',
        1))
    return S


LIVE_SEAM_COUNT = 3
