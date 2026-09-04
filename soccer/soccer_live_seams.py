#!/usr/bin/env python3
"""soccer_live_seams.py -- turn the soccer board's live loop ON.

soccer_fork.py takes a small, reviewable diff:

    from soccer_live_seams import live_seams, LIVE_SEAM_COUNT, LIVELOOP_NEW, REFETCH_NEW
    EXPECT_SEAMS = 80 + LIVE_SEAM_COUNT          # 80 base + 5 live = 85

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
    return soccerAdopt().then(function(){
      return soccerLive._i.run();
    });
  }catch(e){ return Promise.resolve(); }
}

/* 🚨 ONEAUTHOR-2026-08-30 -- THE SERVER IS THE ONLY AUTHOR OF THE BOARD.
 *
 * Owner, after a slip he had money on turned out not to be the slip the server held:
 * "the page and server evaluate at different instants with different team news, so their frozen
 * sets can still differ, yea this doesnt work for me, fix it".
 *
 * WHAT WENT WRONG. soccerRedraft() let the PAGE mint, repair and top up slips. The server does
 * the same work every few minutes from its own inputs. Both are correct under the rules and they
 * do not have to agree: 2026-08-30 the owner's tab topped Kylian Mbappe's pair first and took
 * Moussa Sylla, leaving Jude Bellingham as the strongest man free for Esteban Lepaul's pair, and
 * he placed Lepaul + Bellingham + Rashford off a card stamped LOCKED. The server had Sylla frozen
 * on Lepaul's slip already, so its top-up fell to Santos Matheus Cunha and it published a
 * different board. Bellingham scored; Sylla did not. Same slate, same minute, 3.03u apart, and
 * the board never graded the bet he actually had on. TOPUPORDER-2026-08-30 pinned the anchor
 * order, which removes one source of that; it cannot remove the other, because the two callers
 * genuinely run at different instants against different team news.
 *
 * SO THE PAGE STOPS DRAFTING. It renders the published board and nothing else. Every slip on
 * screen is a slip the server wrote down, which is the only property that makes a card safe to
 * bet from.
 *
 * ⚠️ THIS RETIRES STAGE2's PAGE-SIDE RE-DRAFT, deliberately. Its job -- swap a leg the team sheet
 * has just dropped -- now belongs to the server alone, which rebuilds every ~5 minutes, and the
 * card already renders "🪑 Out of lineup: X — will not hit as built" the moment the live feed
 * marks a leg absent. A benched leg is therefore VISIBLE immediately and REPLACED within one
 * build, instead of being replaced instantly on screen and never in the record.
 *
 * ⚠️ AND IT MAKES ADOPTION SAFE, which is the other half. ADOPTFILE-2026-08-17 turned adoption on
 * for baseball and reverted it the same day: `D.tickets = j.tickets` deleted a CONFIRMED Family
 * Meal single (Michael Toglia) out of a live tab before CONFLOCK could see it, and the standing
 * instruction in deploy-pages.yml is "Fix adoption to carry forward every prior ticket that is
 * underway or fully confirmed, THEN restore the staging line." That condition is met here from
 * the other side: a page that never invents a slip can only be holding slips the server also
 * holds, so replacing the tab's board with the server's can never delete a bet. The carry below
 * is still written out explicitly rather than assumed -- a locked slip the incoming board does
 * not name is KEPT, and says so in the console, because that combination now means something is
 * wrong upstream and must never be silent again.
 *
 * Fails soft in every direction: no network, a 404, a downloaded copy, or a build stamp that has
 * not moved all leave the baked board exactly as it is. */
function soccerAdopt(){
  try{
    if(typeof D==='undefined'||!D.meta||!D.meta.date) return Promise.resolve();
    return fetch('soccer_D.json?cb='+Date.now(),{cache:'no-store'})
      .then(function(r){ return r.ok?r.json():null; })
      .then(function(j){
        if(!j||!j.meta||!j.players||!j.tickets) return;
        /* ADOPTSIG-2026-09-04 -- ADOPT ON THE BOARD, NOT ON A STAMP THAT NEVER MOVES.
           This used to read `if(j.meta.build===D.meta.build) return;`. meta.build is the string
           "2026-09-04 live" and is IDENTICAL on every build of the slate, so the guard was true on
           every poll and a tab never adopted anything after page load -- through every team sheet,
           every demoted anchor, every replaced leg. Owner: "why is godts still an anchor?" -- he
           was not, on the published board; he was on the tab, which had stopped listening.
           That defeats ONEAUTHOR-2026-08-30, whose whole point is that "every slip on screen is a
           slip the server wrote down": it was, just not the current one, with nothing saying so.
           So compare the BOARD. Ticket set (kind, title, legs in order, locked) plus a digest of
           every player's status/out/void/hr, so a board whose slips are unchanged but whose team
           news has moved is still adopted and the tick marks follow. Identical board in, identical
           signature out, no adopt -- the no-churn property the stamp was reaching for, now keyed on
           what actually changed. */
        var _bsig=function(o){
          var ts=(o.tickets||[]).map(function(t){
            return t.kind+'|'+t.name+'|'+(t.players||[]).map(function(l){return l.name;}).join('>')+'|'+(t.locked?1:0);
          }).join(';');
          var P=o.players||{}, ns=Object.keys(P).sort(), ps=[];
          for(var i=0;i<ns.length;i++){ var p=P[ns[i]];
            ps.push(ns[i]+':'+(p.status||'')+(p.out?'O':'')+(p.void?'V':'')+(p.hr?'H':'')); }
          return ts+'||'+ps.join(',');
        };
        if(_bsig(j)===_bsig(D)) return;                       /* the board has not moved */
        /* live facts this tab has already seen outrank a board that was written before them */
        var _hr={}; Object.keys(D.players).forEach(function(n){
          if(D.players[n].hr){ _hr[n]={hr:true,goalmins:(D.players[n].goalmins||[]).slice()}; }
        });
        var _locked={}; (D.tickets||[]).forEach(function(t){ if(t.locked) _locked[t.name]=t; });
        D.players=j.players; D.pool=j.pool||[]; D.tickets=j.tickets; D.meta=j.meta;
        Object.keys(_hr).forEach(function(n){
          if(D.players[n]){ D.players[n].hr=true; D.players[n].goalmins=_hr[n].goalmins; }
        });
        /* ADOPTFILE's condition, stated out loud: a slip this tab had FROZEN must survive the
           swap. With the page no longer drafting this should never fire; if it does, the boards
           have diverged upstream and the bet wins the argument. */
        var have={}; D.tickets.forEach(function(t){ have[t.name]=true; });
        Object.keys(_locked).forEach(function(nm){
          if(!have[nm]){
            D.tickets.push(_locked[nm]);
            if(typeof console!=='undefined')
              console.log('ONEAUTHOR: kept a locked slip the published board does not carry:',nm);
          }
        });
        D.meta.tickets=D.tickets.length;
        if(typeof CACHE!=='undefined') CACHE=null;
        if(typeof stamp==='function') stamp('board '+j.meta.build);
      }).catch(function(){});
  }catch(e){ return Promise.resolve(); }
}

/* STAGE2-2026-08-27 -- THE LIVE RE-DRAFT ON TEAM NEWS.
 *
 * Football XIs publish about an hour before kickoff. A named player who is not in the XI is a
 * dead leg, and the board should replace him BEFORE kickoff -- that is the trigger the baseball
 * board answers when a lineup posts. Until now the soccer board could not: its draft lived in
 * Python and the only drafter in the browser was assembleClient, which is baseball. The rules
 * now live in soccer_draft.js and both sides call it.
 *
 * ⚠️ THIS DOES NOT CALL assembleClient, AND MUST NOT. The 2026-08-26 audit closed four separate
 * doors into it (timer, boot call, #livebtn, window.__*) and the answer to "are you sure it
 * cannot re-draft a placed bet" was to remove the path rather than explain why nobody would
 * take it. Re-opening it here to get a drafter would undo all of that and bring GAME_CAP /
 * CHALK_N / WIN=120 / rain bands with it.
 *
 * THREE GUARDS, and each one is a way this feature could quietly ruin a board:
 *
 *  1. AT LEAST ONE MATCH MUST HAVE PUBLISHED, and the XI filter is scoped to the matches that
 *     HAVE. The original concern is real and unchanged: the XI filter keeps only confirmed
 *     starters, so applying it slate-wide while one sheet is missing deletes that entire match
 *     from the board and piles the whole card onto whichever fixture published first.
 *
 *     🚨 XIPARTIALGATE-2026-08-29. The answer to that was "re-draft only when all of them are
 *     in", and on a real card that is never. Football XIs land about an hour before kickoff, so
 *     a slate spanning 11:30Z-19:30Z (2026-08-29: 22 fixtures) has SOME sheet outstanding for
 *     essentially the whole day -- the page therefore never re-drafted on team news at all.
 *     Beto was named on Everton's bench at ~13:00Z and rode a live moon to kickoff behind this
 *     guard. XIPARTIAL-2026-08-28 already solved this properly inside soccer_draft.js:
 *     `buildPool` takes `xiMatches` and gates a player ONLY inside a match whose sheet is out;
 *     a player in an unpublished match is UNKNOWN, not benched, and stays eligible. That is the
 *     same shape soccer_rebuild_cli.js has used on the server since 08-28. This makes the page
 *     agree with it instead of standing in front of it.
 *
 *     Omitting `xiMatches` restores the old all-or-nothing behaviour exactly, which is what
 *     every existing caller and test relies on -- so this is additive, not a change of contract.
 *  2. A NON-EMPTY XI. soccer_mock.py's `_XI is None` vs `set()` trap, in the browser: no team
 *     news means draft the whole field, but an EMPTY XI gates the pool to nothing and mints an
 *     empty board. Absent and empty are different facts.
 *  3. NOTHING MOVED, NOTHING DRAFTED. The loop runs every three minutes for the whole night.
 *     Re-drafting on a signature that has not changed would churn the card against nothing.
 *
 * CONFLOCK and MINTGUARD live inside SoccerDraft.redraft() and are tested in test_redraft.js:
 * a frozen slip is emitted verbatim, and no slip is ever minted past its own kickoff.
 */
function soccerRedraft(){
  try{
    if(typeof SoccerDraft==='undefined'||typeof D==='undefined'||!D.meta||!D.players) return;
    if(!D.meta.ko||!Object.keys(D.meta.ko).length) return;   /* board baked before STAGE2 */

    var names=Object.keys(D.players);
    if(!names.length) return;

    /* guard 1 -- at least one match has published, and the filter is scoped to those */
    var byGame={};
    names.forEach(function(n){ var p=D.players[n]; (byGame[p.game]=byGame[p.game]||[]).push(p); });
    var xiMatches={},nready=0;
    Object.keys(byGame).forEach(function(g){
      var pub=byGame[g].some(function(p){
        /* 🚨 OUTNOTSHEET-2026-08-30. `||p.out===true` used to be a third clause here and it
           deleted a live anchor's whole run. PUBLICATION IS A TEAM-NEWS FACT. When this guard
           was written `out` could only be set by soccer_teamnews.py inside a match whose sheet
           had published, so it was a fair proxy. WRONGCLUB-2026-08-30 gave `out` a SECOND
           meaning -- "not in his club's squad", a season-long fact stamped on the row at build
           time, hours before any sheet exists. One such name then asserted that his whole match
           had published. Inside a match falsely marked published NOBODY is confirmed, so
           buildPool's `xi && gated(p) && !xi[p.name]` gated out every player in it, and any
           open slip needing a leg there could not be repaired and died.
           MEASURED on the 2026-08-30 board at 16:29Z: 13 of 15 matches marked published against
           10 real sheets; games 11/13/14 had ZERO confirmed players; Lautaro Martinez's two
           screamers and his builder were deleted, 9 tickets -> 6. With the clause gone,
           xiMatches is 10, the three slips repair, and redraft reports changed:false.
           The server never had this bug -- soccer_rebuild_cli.js builds xiMatches from
           soccer_teamnews.py's per-fixture `trusted` map and has never consulted `out`. This is
           the page catching back up to it, which is the whole point of one shared engine.
           Nothing is lost: a genuinely published sheet always names a confirmed or benched
           player, so the two remaining clauses cover every real case. */
        return p.status==='confirmed'||p.status==='benched';
      });
      if(pub){ xiMatches[String(g)]=true; nready++; }
    });
    if(!nready) return;

    /* guard 2 -- a real XI */
    var xi={},nxi=0;
    names.forEach(function(n){ if(D.players[n].status==='confirmed'){ xi[n]=true; nxi++; } });
    if(!nxi) return;

    /* guard 3 -- team news actually moved since the last pass */
    var sig=names.map(function(n){
      var p=D.players[n]; return n+':'+(p.status||'')+(p.out?'!':'');
    }).join('|');
    if(sig===soccerRedraft._sig) return;
    soccerRedraft._sig=sig;

    /* the clock, in UTC minutes past midnight OF THE SLATE DATE -- which is what meta.ko is
       measured in. Past midnight UTC the raw figure wraps to 0 and every kickoff would look
       like it is still ahead of us, so a slip could be minted on a match that finished hours
       ago. The date comparison is the fix, not a nicety. */
    var d=new Date(), ymd=d.toISOString().slice(0,10);
    var mins=d.getUTCHours()*60+d.getUTCMinutes();
    if(ymd>D.meta.date) mins+=24*60;          /* the day rolled: everything is in the past */
    else if(ymd<D.meta.date) mins=-1;         /* not the slate day yet */

    var r=SoccerDraft.redraft(D,{nowUTCmin:mins,xi:xi,xiMatches:xiMatches});
    if(!r||!r.changed) return;
    D.tickets=r.tickets;
    D.meta.tickets=r.tickets.length;
    if(typeof stamp==='function'){
      stamp('team news ✓ '+r.locked+' locked · '+r.repaired+' repaired · '+r.minted+' new');
    }
    if(typeof refreshAll==='function') refreshAll();
  }catch(e){ /* a failed re-draft leaves the baked board exactly as it was */ }
}
"""


def live_seams():
    """(label, old, new, n) tuples, same shape soccer_fork.seams() builds.
    APPEND THESE LAST -- see the ORDER MATTERS note in the module docstring."""
    js = io.open(os.path.join(HERE, 'soccer_live.js'), encoding='utf-8').read()
    # STAGE2-2026-08-27. soccer_draft.js rides in on the SAME seam rather than taking one of its
    # own, so LIVE_SEAM_COUNT and therefore EXPECT_SEAMS are unchanged. That is deliberate: the
    # seam count is a tripwire for index.html moving underneath the fork, and bumping it for
    # our own additions is exactly how a real upstream change gets waved through. It goes FIRST
    # because the glue below calls SoccerDraft, and it is injected at the same (last) position,
    # so nothing here is counted against any other seam.
    js = io.open(os.path.join(HERE, 'soccer_draft.js'), encoding='utf-8').read() + '\n' + js
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

    # ---- THE FOURTH DOOR: the console debug handles ---------------------------------------
    # DEBUGHANDLES-2026-08-26, found by auditing after the owner asked, plainly, whether the
    # board could re-draft a locked or in-progress ticket. Statically and in production it
    # cannot: `assembleClient(D)` has exactly ONE call site and it sits inside liveUpdate()'s
    # body, which the 'liveloop' and 'livebtn-onclick' seams leave with no caller. But
    # index.html also hangs both functions on `window` for the console and for
    # backtest_true_draft.js -- so on the soccer board `window.__liveUpdate()` was still a live
    # path to StatsAPI + Open-Meteo + a baseball re-draft, one paste away.
    #
    # Nothing in the page reaches them, so this is a footgun rather than a bug. It goes anyway:
    # today already produced LIVEBTN (the timer and the boot call killed, the BUTTON missed), and
    # the honest response to "are you sure it can't re-draft" is to remove the path, not to
    # explain why nobody would take it. The backtest harness runs against the MLB board, which
    # keeps its handles; the soccer fork has no harness that wants them.
    S.append((
        'debug-handles',
        "if(typeof window!=='undefined'){ window.__assembleClient=assembleClient; "
        "window.__liveUpdate=liveUpdate; window.__confirmResults=confirmResults; }",
        "/* SOCCER: MLB's console handles are NOT exported. __assembleClient re-drafts with "
        "baseball constants and __liveUpdate fetches StatsAPI -- neither has a caller on this "
        "board and neither should have a console one either. See soccer_live_seams.py "
        "'debug-handles'. */",
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


LIVE_SEAM_COUNT = 5
