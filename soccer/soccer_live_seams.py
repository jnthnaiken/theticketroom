#!/usr/bin/env python3
"""soccer_live_seams.py -- turn the soccer board's live loop ON.

soccer_fork.py takes a small, reviewable diff:

    from soccer_live_seams import live_seams, LIVE_SEAM_COUNT, LIVELOOP_NEW, REFETCH_NEW
    EXPECT_SEAMS = 79 + LIVE_SEAM_COUNT          # 79 base + 4 live = 83

    # ...inside seams(), two EXISTING seams change their REPLACEMENT text only:
    #   add('liveloop',      <unchanged old>, LIVELOOP_NEW)
    #   add('step-refetch',  <unchanged old>, REFETCH_NEW)
    # ...and at the VERY END of seams(), before `return S`:
    #   S.extend(live_seams())

⚠️ ORDER MATTERS. `live-inject` must be the LAST seam in the list. Every seam is counted
against the progressively-replaced text, so injecting ~250 lines of JS before the other seams
run would let the injected code change another seam's match count and fail the build for a
reason that has nothing to do with index.html moving. Injected last, nothing is counted after
it. (The fork failing loudly here would be the safety property working, not a bug -- but it
would send the next reader hunting in the wrong place.)

WHY THE LOOP IS ON NOW. It was off because index.html's liveUpdate() fetches MLB StatsAPI and
Open-Meteo and then RE-DRAFTS with baseball constants (GAME_CAP / CHALK_N / WIN=120).
soccer_live.js does neither: it reads ESPN, writes the fields the render layer already
understands (finals / results / gs / hr / goalmins / status / out), and calls refreshAll().
  * It does NOT grade. index.html already grades tonight live off D.tickets (gradeTicket /
    liveCats / liveHist) -- that is why the 08-24 board showed 3-3 once its fixtures settled.
    A second grader here is the assemble_tickets.py mistake: two implementations of one rule
    set, drifting, contradicting each other on the same screen.
  * It does NOT draft. The soccer draft lives in soccer_mock.py, in Python, and has never been
    ported to __assembleClient. Stage 2.
  * It does NOT infer finality from a clock. Only the feed writes D.meta.finals.

⚠️ NO ADOPTION, DELIBERATELY. index.html's ADOPT-2026-08-16 re-fetches D_<date>.json and does
`D.tickets = j.tickets`, which DELETES a confirmed ticket the tab is holding before CONFLOCK
can see it. deploy-pages.yml carries the note in full: "ADOPTFILE, ENABLED THEN REVERTED THE
SAME DAY. DO NOT RE-ENABLE UNTIL adoption MERGES INSTEAD OF REPLACING." So this loop refreshes
results IN PLACE and never swaps the board out from under an open tab.
"""
import io, os

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- replacements for TWO EXISTING seams (modified, not added -> count unchanged) --------

LIVELOOP_NEW = (
    "soccerLive(); setInterval(soccerLive, 3*60*1000)"
    "   /* SOCCERLIVE-2026-08-26: MLB's liveUpdate stays dead (StatsAPI + a baseball re-draft). "
    "This is the soccer loop: ESPN in; finals/hr/goalmins/status out; refreshAll(); no draft, "
    "no grading, no adoption. */"
)

REFETCH_NEW = (
    'can change as team news lands. The board re-reads the results feed every few\n'
    '        minutes: goals, red cards and full time settle themselves on the card.'
)

GLUE = r"""
/* SOCCERLIVE-2026-08-26 -- page glue. Binds the module above to the board's own fetch,
   status line and renderer. Fails soft: any throw leaves the baked board exactly as it is. */
function soccerLive(){
  try{
    if(typeof SoccerLive==='undefined'||typeof D==='undefined') return Promise.resolve();
    if(!soccerLive._i){
      soccerLive._unmatched=[];
      soccerLive._i=SoccerLive.makeLive({
        D:D,
        unmatched:soccerLive._unmatched,
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
    return soccerLive._i.run();
  }catch(e){ return Promise.resolve(); }
}
"""


def live_seams():
    """(label, old, new, n) tuples, same shape soccer_fork.seams() builds.
    APPEND THESE LAST -- see the ORDER MATTERS note in the module docstring."""
    js = io.open(os.path.join(HERE, 'soccer_live.js'), encoding='utf-8').read()
    S = []

    # ---- STORAGE NAMESPACE ---------------------------------------------------------------
    # Both boards are served from theticketroom.live, so they share an ORIGIN and therefore
    # share localStorage. index.html uses ODDS_KEY='hr_ticket_odds' (a FIXED key) and
    # LOCK_KEY='hr_lock_'+date (keyed by DATE, not by sport) -- so on any given day the two
    # boards compute the SAME key. Left alone, the soccer board overwrites the MLB board's
    # saved results, prices and locked slips on every refresh, and vice versa. That is the
    # 2026-08-15 ODDSHOLD incident (one cashed single reading +388 on a desktop and +529 on a
    # phone, 1.4u apart) except across two sports on one device. loadLock() is also the third
    # door the Dingers retirement identified -- "a per-viewer door the server never sees" --
    # so a collision there puts MLB slips on the soccer board.
    S.append(('odds-key', "ODDS_KEY='hr_ticket_odds'", "ODDS_KEY='sr_ticket_odds'", 1))
    # Two sites, both read: the LOCK_KEY declaration and clearSaved()'s removeItem.
    S.append(('lock-key', "'hr_lock_'", "'sr_lock_'", 2))

    # ---- THE THIRD DOOR: the operator console's manual button ----------------------------
    # LIVEBTN-2026-08-26. soccer_fork's 'liveloop' seam kills the BOOT call and the 6-minute
    # timer, and 'live-btn' relabels the operator console's button to "Update from ESPN" -- but
    # the button's ONCLICK still called MLB's liveUpdate(). So the soccer board shipped with a
    # working button that fetched statsapi.mlb.com and api.open-meteo.com and then RE-DRAFTED
    # the slate with baseball constants (GAME_CAP / CHALK_N / WIN=120), under a label promising
    # ESPN. Relabelling a control without repointing it is worse than leaving it alone.
    #
    # This is the SAME failure as LIVELOOP-BOOT-2026-08-25 (killed the timer, left the boot
    # call) one turn later: there were THREE entry points into liveUpdate, not two, and killing
    # the two you can see is not killing the feature. Grep for CALL SITES, not for the loop.
    S.append((
        'livebtn-onclick',
        "d.querySelector('#livebtn').onclick=function(){liveUpdate();};",
        "d.querySelector('#livebtn').onclick=function(){soccerLive();};",
        1))

    # ---- THE LOOP ITSELF -- MUST BE LAST -------------------------------------------------
    # Function declarations hoist, so soccerLive() is callable from the boot line below it.
    S.append((
        'live-inject',
        'function liveUpdate(){',
        '/* ==== soccer_live.js (injected by soccer_live_seams.py) ==== */\n'
        + js + GLUE +
        '/* ==== end soccer_live.js ==== */\nfunction liveUpdate(){',
        1))
    return S


LIVE_SEAM_COUNT = 4
