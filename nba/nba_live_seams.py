#!/usr/bin/env python3
"""nba_live_seams.py -- wire nba_live.js into the basketball board. NBALIVE-2026-10-17.

A copy of nfl_live_seams.py with the football names swapped, deliberately: same three seams, same order,
same reasons (read that file's docstring -- the console button and the debug handles are the doors the
soccer and football forks each left open once).
  MODIFIED IN PLACE: liveloop -> nbaLive() boot + 2-minute timer (first baskets happen fast)
  ADDED HERE:        livebtn-onclick, debug-handles, live-inject
"""
import io, os

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- replacement for an EXISTING seam (modified, not added -> count unchanged) ------------

LIVELOOP_NEW = (
    "nbaLive(); setInterval(nbaLive, 2*60*1000)"
    "   /* NBALIVE-2026-10-17: MLB's liveUpdate stays dead (StatsAPI + a baseball re-draft). "
    "This is the basketball loop: ESPN in; finals/gs/hr/out/status out; refreshAll(); no draft, "
    "no grading, no adoption. */"
)

GLUE = r"""
/* NBALIVE-2026-10-17 -- page glue. Binds the module above to the board's own fetch, status line
   and renderer. Fails soft: any throw leaves the baked board exactly as it is, which is the
   property that makes a live loop safe to run against a board carrying real money. */
function nbaLive(){
  try{
    if(typeof NbaLive==='undefined'||typeof D==='undefined') return Promise.resolve();
    if(!nbaLive._i){
      nbaLive._unmatched=[];
      nbaLive._i=NbaLive.makeLive({
        D:D,
        unmatched:nbaLive._unmatched,
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
    return nbaLive._i.run();
  }catch(e){ return Promise.resolve(); }
}
if(typeof window!=='undefined'){ window.__nbaLive=nbaLive; }
"""


def live_seams():
    """The seams this module adds. APPEND THESE LAST -- live-inject must be injected at the
    same (final) position, so nothing is counted after it."""
    js = io.open(os.path.join(HERE, 'nba_live.js'), encoding='utf-8').read()
    S = []

    # ---- THE THIRD DOOR: the operator console's manual button -----------------------------
    # See the module docstring. The label already said ESPN; the wire still went to MLB.
    S.append((
        'livebtn-onclick',
        "d.querySelector('#livebtn').onclick=function(){liveUpdate();};",
        "d.querySelector('#livebtn').onclick=function(){nbaLive();};",
        1))

    # ---- THE FOURTH DOOR: the console debug handles ---------------------------------------
    # DEBUGHANDLES-2026-08-26. The backtest harness (backtest_true_draft.js) runs against the
    # MLB board, which keeps its handles; this fork has no harness that wants them.
    S.append((
        'debug-handles',
        "if(typeof window!=='undefined'){ window.__assembleClient=assembleClient; "
        "window.__liveUpdate=liveUpdate; window.__confirmResults=confirmResults; }",
        "/* NBA: MLB's console handles are NOT exported. __assembleClient re-drafts with "
        "baseball constants and __liveUpdate fetches StatsAPI -- neither has a caller on this "
        "board and neither should have a console one either. window.__nbaLive is exported by "
        "the glue instead. See nba_live_seams.py 'debug-handles'. */",
        1))

    # ---- THE LOOP ITSELF -- MUST BE LAST --------------------------------------------------
    # Function declarations hoist, so nbaLive() is callable from the boot line below it.
    S.append((
        'live-inject',
        'function liveUpdate(){',
        '/* ==== nba_live.js (injected by nba_live_seams.py) ==== */\n'
        + js + GLUE +
        '/* ==== end nba_live.js ==== */\nfunction liveUpdate(){',
        1))
    return S


LIVE_SEAM_COUNT = 3
