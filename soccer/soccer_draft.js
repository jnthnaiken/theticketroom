/* soccer_draft.js -- THE soccer draft. One implementation, two callers.
 *
 * WHY THIS FILE EXISTS. Until now the soccer draft lived in soccer_mock.py and nowhere else,
 * which meant the board could not re-draft when team news landed: the only engine that runs in
 * the browser is index.html's `assembleClient`, and that is a BASEBALL drafter (GAME_CAP,
 * CHALK_N, WIN=120, rain bands, lunch/nightcap windows, a fixed four anchors). Pointing the
 * live loop at it would re-draft a soccer slate against rules that do not apply -- which is
 * exactly why soccer_fork.py's 'liveloop' seam killed it in the first place.
 *
 * The alternative that was NOT taken: seam soccer constants into `assembleClient`. That body is
 * ~700 lines of accumulated MLB incident logic (scratch-kills-ticket, re-anchor continuity,
 * shape repair, chalk seats, rain bands). Making it behave like soccer_mock.draft() means
 * disabling most of it from the outside, through string seams that can only check that a match
 * occurred -- never that the result is still correct. That is not a port, it is a rewrite inside
 * a body that fights it.
 *
 * So: the draft rules move HERE, once, and both sides call this file. That is the same fix
 * `client_assemble.js` is for the baseball board -- the archive is drafted by the code the
 * browser runs, so server and screen cannot drift.
 *
 *   server  soccer_mock.py  ->  node soccer_draft_cli.js   (bakes soccer_D.json)
 *   browser soccer_live.js  ->  redraft()                  (when team news moves)
 *
 * ⚠️ THIS MODULE IS PURE. No DOM, no fetch, no Date. Everything time-dependent is passed in as
 * `nowUTCmin`, because a draft that reads the clock cannot be tested against a frozen slate and
 * cannot be replayed. clock.js exists for exactly that reason.
 */
(function (root) {
  'use strict';

  var DEFAULTS = {
    /* WIN60-2026-08-29. Was 180. The owner: "soccer's game time window needs to be 60 min.
       this isnt working for me at 180 and all slips with lineup risks. makes it impossible to
       place a slip."
       WHY 180 DOES NOT WORK ON A FOOTBALL CARD. Team sheets publish about an hour before each
       kickoff, so a slip bridging three hours is NEVER fully confirmed at one moment: by the time
       the last leg's XI is known the first leg has been playing for two hours, and the bet cannot
       be placed as one slip any more. A 60-minute span means every leg's sheet lands inside the
       same hour, so the whole slip resolves its lineup risk together and is placeable while all
       three matches are still ahead of you. Baseball uses 120 and does not have this problem
       because lineups post on a much longer runway.
       Keep this in step with CFG['WIN'] in soccer_mock.py -- two copies, one rule.

       WIN75 / ZGATE70-2026-08-30. Owner: "just loosen both gates to .7 and 75 minutes".
       WHAT FORCED IT. The 2026-08-30 card (15 matches) drafted NOTHING at 60 / 0.75. draftN picks
       anchors strength-first and is all-or-none, and the strongest player is in every attempt
       down to n=1 -- so one unfillable top name zeroes the whole board. Lautaro Martinez
       (TOTAL 201.6, strongest on the slate by 34) sat in Cagliari-Inter at ko 1125, and only TWO
       pool matches lay within 60 minutes of him; a screamer needs three from three. The two that
       would have opened the window each missed by a hair: Lazio-Genoa's best man gated at +0.74
       against a 0.75 bar, and Aubameyang at ko 1050 was 75 minutes out against a 60-minute span.
       Both new numbers clear exactly those two margins. The 08-29 reasoning below still holds --
       75 minutes still lands every leg's sheet inside roughly one hour -- this widens it by a
       quarter hour, it does not go back to 180.
       See claude/soccer-2026-08-30-emptydraft.md. */
    WIN: 75,             // minutes: widest kickoff span one slip may bridge (MLB uses 120)
    Z_GATE: 0.70,        // pool gate, in SDs of blend above the slate mean
    GAME_CAP: 4,         // most pool players from any one match
    ANCH: 4,             // anchor TARGET -- see THINSLATE below, this is a ceiling not a promise
    MOON_LEGS: 3,        // legs on a screamer, each from a DIFFERENT match
    MOONS_PER_ANC: 2,
    ANCH_PER_GAME: 2,
    MOON_RISK: 2.0,
    SINGLE_STAKE: 1.0
  };

  function cfgOf(o) {
    var c = {}, k;
    for (k in DEFAULTS) if (DEFAULTS.hasOwnProperty(k)) c[k] = DEFAULTS[k];
    for (k in (o || {})) if (o.hasOwnProperty(k)) c[k] = o[k];
    return c;
  }

  /* byName: array -> {name: true}. Callers pass sets as plain objects so this runs on any
     engine the board might be opened in. */
  function nameSet(arr) {
    var s = {};
    (arr || []).forEach(function (x) { s[typeof x === 'string' ? x : x.name] = true; });
    return s;
  }

  /* ---- POOL -----------------------------------------------------------------------------
   * Mirrors soccer_mock.py exactly:
   *     pool = [p for p in players if p.gate_z >= Z_GATE and (XI is None or p.name in XI)]
   *     pool.sort(key=lambda p: (-p['TOTAL'], p['name']))
   *     then GAME_CAP per match, in that order.
   *
   * The XI filter is the whole reason Stage 2 exists. `xi` null means "no team news on hand" ->
   * draft the full priced field, which is what the board did before 2026-08-26. An EMPTY xi
   * object is NOT the same thing and must never be passed as one: it filters the pool to nothing
   * and mints an empty board. soccer_mock.py has the same trap (`_XI is None` vs `set()`), and
   * it is why the live wrapper below refuses to re-draft on an incomplete squad sheet.
   */
  function buildPool(players, cfg, opts) {
    opts = opts || {};
    var xi = opts.xi || null, excl = opts.exclude || {};
    /* XIPARTIAL-2026-08-28 -- THE XI FILTER IS PER MATCH, NOT PER SLATE.
     * `xiMatches` is the set of match keys whose team sheet has actually published. A player in
     * a match that has NOT published is UNKNOWN, not benched, so he stays eligible; only inside
     * a published match does "not in the XI" mean "do not draft him".
     * Before this, one unpublished sheet meant the whole slate had to wait -- and on a staggered
     * card (2026-08-28: kickoffs 17:00Z through 19:30Z, sheets landing ~1h before each) the set
     * is NEVER complete while the early matches are still mintable. The board therefore never
     * re-drafted a benched player at all. Omit `xiMatches` and the old all-or-nothing behaviour
     * is exactly preserved, which is what every existing caller and test relies on. */
    var xiM = opts.xiMatches || null;
    var gated = function (p) { return !xiM || !!xiM[String(p.match)]; };
    var elig = players.filter(function (p) {
      /* WRONGCLUB-2026-08-30. `out` means NOT IN THE SQUAD (OUTSQUAD-2026-08-29) and it must
         keep a man out of the FRESH draft too, not only the live one. redraft()'s alive[] has
         always honoured it; buildPool never asked, so a player the squad file proved absent was
         still fully draftable and Nicolas Jackson -- an Aston Villa forward -- anchored
         Chelsea v Brighton on 2026-08-30. Rows without the field are undefined and fall
         through unchanged, so every earlier slate and the 08-26 golden board are untouched. */
      if (p.out || p.void) return false;
      if (p.gate_z == null || p.gate_z < cfg.Z_GATE) return false;
      if (excl[p.name]) return false;
      if (xi && gated(p) && !xi[p.name]) return false;
      return true;
    });
    elig.sort(function (a, b) {
      if (b.TOTAL !== a.TOTAL) return b.TOTAL - a.TOTAL;
      return a.name < b.name ? -1 : a.name > b.name ? 1 : 0;
    });
    var per = {}, out = [];
    elig.forEach(function (p) {
      var k = p.match;
      if ((per[k] || 0) < cfg.GAME_CAP) { out.push(p); per[k] = (per[k] || 0) + 1; }
    });
    return out;
  }

  /* strength = TOTAL normalised across the POOL (not the field). Used only for draft order, so
     it is monotone in TOTAL and the sort below is the same order buildPool already produced --
     kept explicit anyway so the two cannot drift if either sort ever changes. */
  function withStrength(pool) {
    var tmin = Infinity, tmax = -Infinity;
    pool.forEach(function (p) { if (p.TOTAL < tmin) tmin = p.TOTAL; if (p.TOTAL > tmax) tmax = p.TOTAL; });
    if (!isFinite(tmin)) { tmin = 0; tmax = 1; }
    return pool.map(function (p) {
      var s = tmax > tmin ? (p.TOTAL - tmin) / (tmax - tmin) : 0.5;
      var q = {}; for (var k in p) if (p.hasOwnProperty(k)) q[k] = p[k];
      q.strength = s;
      return q;
    }).sort(function (a, b) {
      if (b.strength !== a.strength) return b.strength - a.strength;
      return a.name < b.name ? -1 : a.name > b.name ? 1 : 0;
    });
  }

  function spanOk(legs, cfg) {
    var lo = Infinity, hi = -Infinity;
    legs.forEach(function (l) { if (l.kickoff < lo) lo = l.kickoff; if (l.kickoff > hi) hi = l.kickoff; });
    return (hi - lo) <= cfg.WIN;
  }

  /* COMPLETABILITY-2026-09-04, ported from index.html's canComplete() (added there 2026-08-13).
   *
   * spanOk() validates a screamer AS IT STANDS -- distinct matches, span <= WIN. It never asks
   * whether a THIRD leg is still reachable after the pick, so filling by strength can strand the
   * slip on its own second leg. The baseball incident it was written for: Contreras (3:07) took
   * Crow-Armstrong (4:05) as his first partner on BOTH moons, pinning the window to [2:05, 5:07]
   * -- his own game barred as a duplicate, 4:05 already on the ticket, and the three 1:10 games
   * and the 1:35 now out of window. Both moons stalled at two legs, he was demoted, and the
   * strongest bat on the board fell to a partner leg under a weaker anchor.
   *
   * ⚠️ IT COUNTS DISTINCT MATCHES, NOT PLAYERS. Every remaining leg has to come from a match this
   * screamer does not already hold, so five in-window candidates from one match are worth exactly
   * one leg. Counting players would say "plenty left" and strand the slip anyway, which is the
   * bug wearing a lookahead.
   *
   * Cheap by construction: it stops as soon as it has found `left` usable matches.
   */
  function canComplete(t, cand, pool, cfg) {
    var left = cfg.MOON_LEGS - t.legs.length - 1;
    if (left <= 0) return true;
    var legs = t.legs.concat([cand]);
    var used = {};
    legs.forEach(function (x) { used[x.match] = true; });
    var cnt = 0, seen = {};
    for (var i = 0; i < pool.length; i++) {
      var m = pool[i];
      if (m === cand || used[m.match] || seen[m.match]) continue;
      if (!spanOk(legs.concat([m]), cfg)) continue;
      seen[m.match] = true;
      if (++cnt >= left) return true;
    }
    return false;
  }

  /* ---- DRAFT AT EXACTLY n ANCHORS --------------------------------------------------------
   * ALL-OR-NONE, and that is deliberate: an anchor that ships one moon instead of two is a
   * lopsided board, so the whole attempt is thrown away and the caller steps n down. Ported
   * line-for-line from soccer_mock.draft().
   *
   * `spent` is board-wide and `local` is per-anchor: a partner is used once on the whole card,
   * and an anchor's two moons never share a partner. `partners` excludes anchors, so an anchor
   * is never a leg on someone else's slip.
   */
  function draftN(byStrength, n, cfg, opts) {
    opts = opts || {};
    var reservedAnchorMatches = opts.anchorMatchCounts || {};
    var anchors = [], perG = {};
    var k;
    for (k in reservedAnchorMatches) if (reservedAnchorMatches.hasOwnProperty(k)) perG[k] = reservedAnchorMatches[k];

    /* SKIPUNFILLABLE-2026-08-31 -- AN ANCHOR WHO CANNOT BE PAIRED IS PASSED OVER, NOT FATAL.
       The body below is UNCHANGED. What is new is the loop around it: when a chosen anchor cannot
       fill both screamers, he is struck off and the NEXT candidate by strength takes his chair,
       and the whole pairing pass is re-run from the top. Every attempt therefore still reserves
       the COMPLETE anchor set out of `partners` before any pair is built -- which is the
       invariant "no anchor appears as a partner", and re-deriving partners per candidate instead
       breaks it (measured: test_redraft's leg-repair case seeded a board carrying Dion Beljo as
       both an anchor and a partner on someone else's screamer).
       WHY: draftN was all-or-none over the whole SET, and the strongest player is in every attempt
       right down to n=1, so ONE unpairable top name zeroed the entire board -- Lautaro Martinez on
       2026-08-30 (ko 1125, two matches inside WIN) and Donyell Malen on 2026-08-31 (ko 990: only
       990 and 1050 are inside WIN, and a screamer needs three DIFFERENT matches).
       claude/soccer-2026-08-30-emptydraft.md ends by naming this exact recurrence and this exact
       question. 08-30 was answered by tuning (WIN75/ZGATE70) because the two blocking partners sat
       within a few hundredths of the bars. No tuning reaches 08-31: Malen's window holds two
       matches at ANY Z_GATE, and opening it needs WIN >= 135 -- a slip spanning two and a quarter
       hours, which is the thing WIN60-2026-08-29 was written to stop.
       ALL-OR-NONE IS NOT WEAKENED. It was always a rule about ONE ANCHOR -- "an anchor that ships
       one moon instead of two is a lopsided board" -- and that still holds exactly: an anchor
       seats with MOONS_PER_ANC screamers or does not seat at all. What changes is only that his
       failure no longer condemns the other three. n is still stepped down by the caller when the
       pool genuinely cannot seat n, so THINSLATE still reports the honest number.
       The skipped player is not deleted: he is not an anchor, so he stays in `partners` and can
       still be drafted as a leg of somebody else's screamer -- which is where an unpairable man
       belongs. With nothing unpairable the loop runs exactly once and the draft is bit-identical;
       the 2026-08-26 golden board reproduces unchanged. */
    var struck = {};
    for (var attempt = 0; attempt <= byStrength.length; attempt++) {
      anchors = []; perG = {};
      for (k in reservedAnchorMatches) if (reservedAnchorMatches.hasOwnProperty(k)) perG[k] = reservedAnchorMatches[k];
      for (var i = 0; i < byStrength.length && anchors.length < n; i++) {
        var p = byStrength[i];
        if (struck[p.name]) continue;
        if ((perG[p.match] || 0) < cfg.ANCH_PER_GAME) { anchors.push(p); perG[p.match] = (perG[p.match] || 0) + 1; }
      }
      if (anchors.length < n) return [];

      var used = nameSet(anchors);
      var partners = byStrength.filter(function (p) { return !used[p.name]; });

      /* SNAKEDRAFT-2026-09-04 -- AN ANCHOR'S SCREAMERS FILL TOGETHER, NOT ONE THEN THE OTHER.
         This block used to run `for m` over the anchor's moons and, inside it, walk the
         strength-sorted `partners` from the top -- so moon 1 took the two best legal partners and
         moon 2 took the next two. Moon 1 was stronger than moon 2 by construction on every anchor
         of every board this file has drafted (2026-09-13 football: Hampton 177.5/170.9 against
         149.7/149.6, a 49-point gap). Owner: "it looks like it is drafting one of an anchor's
         moons entirely before drafting the other. thats not how it works."
         It is index.html's fillRound(), which baseball has always used and which this file never
         got because it was ported from soccer_mock.draft(): rounds rather than a sequential fill,
         the anchor order reversed every other round, and within an anchor the moon holding FEWER
         legs picks first. Removing a pick from the shared pool at once keeps BOTH old invariants
         -- a partner is used at most once board-wide (was `spent`) and an anchor's two moons never
         share one (was `local`). */
      var out = [], failed = null;
      var avail = partners.slice(), shells = [];
      for (var a = 0; a < anchors.length; a++) {
        for (var m = 0; m < cfg.MOONS_PER_ANC; m++) {
          var sh = { rank: a, anc: anchors[a], legs: [anchors[a]], seen: {} };
          sh.seen[anchors[a].match] = true;
          shells.push(sh);
        }
      }
      var needy = function (t) { return t.legs.length < cfg.MOON_LEGS; };
      for (var rnd = 0; shells.some(needy); rnd++) {
        var order = [];
        for (var r0 = 0; r0 < anchors.length; r0++) order.push(r0);
        if (rnd % 2) order.reverse();
        var progress = false;
        order.forEach(function (r) {
          shells.filter(function (t) { return t.rank === r; })
                .sort(function (x, y) { return x.legs.length - y.legs.length; })
                .forEach(function (t) {
            if (!needy(t)) return;
            for (var c = 0; c < avail.length; c++) {
              var cand = avail[c];
              if (t.seen[cand.match]) continue;
              if (!spanOk(t.legs.concat([cand]), cfg)) continue;
              /* COMPLETABILITY-2026-09-04: never take a partner that leaves too few distinct
                 in-window matches to finish this screamer. */
              if (!canComplete(t, cand, avail, cfg)) continue;
              t.legs.push(cand); t.seen[cand.match] = true;
              avail.splice(c, 1); progress = true;
              return;
            }
          });
        });
        if (!progress) break;
      }
      /* ALL-OR-NONE, unchanged in meaning. Strike the WEAKEST anchor among those that actually
         failed, not the first one found: index.html records (2026-08-13) that demoting the wrong
         anchor eats every good one beneath it and ends with an empty board. */
      var short = {};
      shells.forEach(function (t) { if (needy(t)) short[t.anc.name] = true; });
      for (var a2 = anchors.length - 1; a2 >= 0; a2--) {
        if (short[anchors[a2].name]) { failed = anchors[a2]; break; }
      }
      if (!failed) {
        shells.forEach(function (t) {
          out.push({ kind: 'moon', legs: t.legs, risk: cfg.MOON_RISK });
        });
        return out;
      }
      struck[failed.name] = true;
    }
    return [];
  }

  /* ---- THE DRAFT ------------------------------------------------------------------------
   * THINSLATE-2026-08-26 (owner's call). ANCH was fixed at 4, a number sized for a fifteen-game
   * MLB slate. Once team news was wired the soccer field fell from 75 priced to 25 starting, the
   * all-or-none demote fired on every anchor, and the board minted NOTHING. Take the LARGEST
   * anchor count the pool fully supports rather than lowering Z_GATE until a pool appears --
   * loosening the gate to hit a target ticket count is fitting the bar to the answer.
   */
  /* SINGLES-2026-08-27 (owner's call). A screamer needs MOON_LEGS legs from MOON_LEGS DIFFERENT
   * matches, so on a slate with fewer matches than that NO screamer can exist -- draftN returns
   * [] at every anchor count and the board mints nothing at all. Today's slate is two La Liga
   * matches and that is exactly what happened.
   *
   * The same-match ban is NOT the thing to relax. It was reaffirmed 2026-08-24 on placeability
   * grounds: two legs from one match is a same-game parlay, which is not a straight multi and
   * is not what the round-robin prices assume. Nor is a two-leg "screamer" the answer -- a
   * two-leg round robin is just a double, so 'by 2s & 3' and the rr block would stop meaning
   * what they say on the card.
   *
   * So the board gets smaller instead, which is the same answer THINSLATE-2026-08-26 gave when
   * four anchors would not fit: ship what the slate actually supports rather than lowering a
   * bar until something appears. Here that is the anchors alone, as builder singles -- straight
   * bets, placeable, and the exact line every screamer would have been built around anyway.
   */
  function anchorsOnly(byStrength, cfg, opts) {
    var budget = opts.anchorBudget != null ? opts.anchorBudget : cfg.ANCH;
    var perG = {}, k;
    for (k in (opts.anchorMatchCounts || {})) perG[k] = opts.anchorMatchCounts[k];
    var out = [];
    for (var i = 0; i < byStrength.length && out.length < budget; i++) {
      var p = byStrength[i];
      if ((perG[p.match] || 0) >= cfg.ANCH_PER_GAME) continue;
      out.push({ kind: 'builder', legs: [p], risk: cfg.SINGLE_STAKE });
      perG[p.match] = (perG[p.match] || 0) + 1;
    }
    return out;
  }

  /* UNLEFTOVER-2026-08-28. leftoverSingles() lived here and is GONE, not disabled.
   * SCREAMERS-2026-08-26 retired the leftover section to match the MLB Dingers retirement
   * ("its just bleeding money" -- family went 11-80, -33.34u, -36.6% ROI, and its 12 graded
   * nights were backed out of season.json). LEFTOVERS-2026-08-28 was that section again in a
   * different coat: every gated player who made no slip, one unit each, capped at eight. On a
   * healthy board that is six extra singles a night at +200 to +350 -- the dross beneath the
   * draft, which is exactly what was retired. It escaped notice because it minted `builder`
   * rather than `family`, so every check enforcing the retirement looked past it.
   * The thin-slate answer is anchorsOnly() below: ship THE ANCHORS as singles. Not the leftovers.
   */

  function draft(players, cfgIn, opts) {
    var cfg = cfgOf(cfgIn);
    opts = opts || {};
    var pool = buildPool(players, cfg, opts);
    var byStrength = withStrength(pool);

    var budget = opts.anchorBudget != null ? opts.anchorBudget : cfg.ANCH;

    /* ⚠️ THE SLATE'S match count, not the residual pool's. A live re-draft is handed only the
       players nobody has committed yet, so once a full board is frozen the leftovers can easily
       span one match -- and keying the fallback off THAT mints a stray single on a five-match
       night where the right answer is "there is nothing left to mint". Caught by test_redraft's
       'nothing was minted over them'. redraft() passes meta.ko's size, which is every match on
       the board whatever is still free. */
    var mCount = opts.slateMatches;
    if (mCount == null) {
      var seenM = {}; mCount = 0;
      players.forEach(function (p) { if (!seenM[p.match]) { seenM[p.match] = 1; mCount++; } });
    }
    if (mCount < cfg.MOON_LEGS) {
      var singles = anchorsOnly(byStrength, cfg, opts);
      return {
        tickets: singles, pool: pool, byStrength: byStrength,
        anchors: singles.length,
        /* `thin` means FEWER ANCHORS THAN ASKED FOR, which is a different fact from
           `singlesOnly` (no screamer is possible at all). Reporting thin:true whenever the
           singles path runs made the CLI print "4 anchors do not fit; drafted 4", which is
           not true and is exactly the kind of confidently-wrong log line that sends the next
           reader hunting for a pool problem that does not exist. */
        thin: singles.length < budget, singlesOnly: true,
        matches: mCount, budget: budget
      };
    }
    var tickets = [], usedN = 0;
    for (var n = budget; n >= 1; n--) {
      tickets = draftN(byStrength, n, cfg, opts);
      if (tickets.length) { usedN = n; break; }
    }

    /* one builder per distinct moon anchor, in first-seen order */
    var seenA = {}, builders = [];
    tickets.forEach(function (t) {
      if (t.kind !== 'moon') return;
      var a = t.legs[0];
      if (seenA[a.name]) return;
      seenA[a.name] = true;
      builders.push({ kind: 'builder', legs: [a], risk: cfg.SINGLE_STAKE });
    });

    return {
      tickets: tickets.concat(builders),
      pool: pool,
      byStrength: byStrength,
      anchors: usedN,
      thin: usedN > 0 && usedN < budget,
      budget: budget
    };
  }

  /* ======================================================================================
   * TICKET CONSTRUCTION
   * ======================================================================================
   * index.html builds client-minted slips with mkParlay(), but mkParlay / cwName / lockOf /
   * nextIdx / NAMES / rrmax all live INSIDE assembleClient's closure (indent 4, one scope), so
   * none of them is reachable from the live loop. They are rebuilt here instead of exported,
   * because exporting them is re-opening a door the DEBUGHANDLES-2026-08-26 audit closed.
   *
   * The shape below is soccer_payload.py's ticket dict, field for field. `note` is left empty:
   * index.html renders `t.note?'<div class="tnote">'+t.note+'</div>':''`, and mkParlay itself
   * ships note:"" for every client-minted slip, so an absent note is a supported state and not
   * a hole. Prose is a bake-time luxury; a correct draft is not.
   */
  var NAMES = {
    moon:    ['Top Corner', 'From Distance', 'Upper Ninety', 'Postage Stamp', 'Off the Underside',
              'Outside the Box', 'Dipping Effort', 'Curled Home', 'Half Volley', 'Thirty Yards',
              'Into the Roof', 'No Backlift'],
    builder: ['Target Man', 'The Poacher', 'Six-Yard Box', 'Back Post', 'Near Post', 'The Nine',
              'First Time', 'Gets Across', 'Runs the Channel', 'Shoulder of the Last Man'],
    /* SHAPEREPAIR-2026-08-31. Until now the drafter could only MINT moons and builders --
       ORPHANSECTION reaches 'lunch' and 'late' by rewriting `t.kind` on a slip that already
       carries a builder's title. A minted special has no title to inherit and pickName() fell
       through to its `|| ['Ticket']` fallback, shipping a slip called "Ticket" -- and
       NAMECARRY-2026-08-29 makes that stick, because soccer_payload.shape_ticket USES the title
       the draft assigned. Copied EXACTLY from soccer_payload.py's NAMES; two copies, one rule,
       same as WIN / Z_GATE across DEFAULTS and soccer_mock.CFG. Change one, change both. */
    lunch:   ['Early Doors', 'Lunchtime Kickoff', 'The Twelve Thirty', 'First Match On'],
    late:    ['Under Lights', 'Last One On', 'The Late Kickoff', 'Sunday Night']
  };
  var BADGE = { moon: '💥', builder: '⚓️', lunch: '🍱', late: '🌃' };

  function a2d(o) { return o > 0 ? 1 + o / 100 : 1 + 100 / Math.abs(o); }

  /* Round-robin max profit. Ported from soccer_payload.rr_maxprofit (which is itself
     index.html's rrmax): every 2-leg and 3-leg combination, minus the total risk. */
  /* RRSTAKE-2026-08-28. `risk` is the TOTAL staked across the round robin -- 2u on a moon, which
     is 3 doubles + 1 treble at 0.5u each, NOT 1u each. Summing the bare decimal products priced
     4u on a slip that risks 2 and roughly DOUBLED every max profit the board printed. Fixed in
     lockstep with index.html's rrmax(), soccer_payload.rr_maxprofit(), grade_night.py and
     soccer_grade._rrnet -- five copies of one formula, which is its own lesson. */
  function rrMaxProfit(legs, risk) {
    var dec = legs.filter(function (l) { return l.odds; }).map(function (l) { return a2d(l.odds); });
    var L = dec.length, s = 0, n = 0, a, b, c, d;
    for (a = 0; a < L; a++) for (b = a + 1; b < L; b++) { s += dec[a] * dec[b]; n++; }
    for (a = 0; a < L; a++) for (b = a + 1; b < L; b++) for (c = b + 1; c < L; c++) { s += dec[a] * dec[b] * dec[c]; n++; }
    if (L >= 4) for (a = 0; a < L; a++) for (b = a + 1; b < L; b++) for (c = b + 1; c < L; c++)
      for (d = c + 1; d < L; d++) { s += dec[a] * dec[b] * dec[c] * dec[d]; n++; }
    return n ? Math.floor(((risk / n) * s - risk) * 10 + 0.5) / 10 : 0;
  }

  function legOf(name, src) {
    return {
      name: name,
      team: src.team,
      total: src.TOTAL,
      aT: src.aT != null ? src.aT : 100,
      wf: src.wf != null ? src.wf : 1,
      gmatch: src.gmatch || '',
      gtime: src.gtime || '',
      game: src.game,
      late: !!src.late,
      odds: src.odds,
      status: src.status || 'projected'
    };
  }

  /* ⚠️ LOCK IS COMPUTED FROM KICKOFF MINUTES, NOT FROM THE TIME STRING.
   * soccer_payload.py does `min(l['gtime'] for ...)`, a LEXICOGRAPHIC min over strings like
   * "3:00 PM". It has been right so far only because every kickoff on every soccer slate to
   * date has been identical, and it stays right today ("2:30 PM" < "3:00 PM"). It is wrong the
   * first time a slate pairs "9:00 AM" with "10:00 AM" -- "10:00 AM" sorts first, so a slip's
   * lock becomes its LATEST leg and CONFLOCK stops protecting it. Same defect as
   * assemble_tickets.add() on the baseball side. Sorting on minutes cannot have that bug. */
  function lockOf(legs, koOf) {
    var best = null, bestKo = Infinity;
    legs.forEach(function (l) {
      var k = koOf(l.game);
      if (k != null && k < bestKo) { bestKo = k; best = l; }
    });
    return best ? (best.gtime || '') : (legs[0] ? legs[0].gtime || '' : '');
  }

  function mkTicket(kind, legs, risk, name, koOf, players) {
    var out = legs.slice().sort(function (a, b) { return (b.total || 0) - (a.total || 0); });
    return {
      name: name,
      kind: kind,
      badge: BADGE[kind] || '🎟',
      note: '',
      players: out,
      nlegs: out.length,
      anchor: out.length ? out[0].name : null,
      lock: lockOf(out, koOf),
      has_late: false,
      final: false,
      locked: false,
      rr: out.length >= 3
        ? { struct: 'by 2s & 3', risk: risk, maxprofit: rrMaxProfit(out, risk), bytwos: false }
        : null,
      wxsum: { boost: 0, supp: 0, dome: 0, neu: 0 },
      confleg: out.filter(function (l) {
        var p = players[l.name]; return p && p.status === 'confirmed';
      }).length,
      unres: out.filter(function (l) { var p = players[l.name]; return p && p.unres; }).length,
      priced: out.filter(function (l) { return l.odds; }).length
    };
  }

  /* ======================================================================================
   * THE LIVE RE-DRAFT -- CONFLOCK + MINTGUARD
   * ======================================================================================
   * The rules are the baseball board's, because they are about BETS, not about a sport:
   *
   *   CONFLOCK   a slip is frozen once EVERY LEG IS CONFIRMED. A frozen slip is emitted verbatim
   *              and its players are spent -- a placed bet is a fact and nothing may re-draft it.
   *              (index.html, 2026-08-16.)
   *
   *              🚨 CONFLOCK-2026-08-29. It used to ALSO freeze once the earliest leg had kicked
   *              off. The owner's rule: "the slip shouldnt be frozen until ALL legs are
   *              confirmed." The kickoff branch froze slips that had never been fully confirmed --
   *              on 2026-08-29 "From Distance" carried Beto, named on Everton's bench an hour
   *              before HIS OWN 14:00Z kickoff, and the slip locked at 13:30Z because two OTHER
   *              legs (Leverkusen, Frankfurt) kicked off first. A benched striker then rode a live
   *              moon that no rule could touch. Confirmation is the thing being waited on, so
   *              confirmation is what closes the slip.
   *
   *              THIS DOES NOT RE-OPEN A PLACED BET, and it needs no help to avoid doing so.
   *              A slip anyone could have PLACED is a slip whose legs are all confirmed, which
   *              is exactly what this freezes -- latched, emitted verbatim, graded with its out
   *              player still on it (OUTSQUAD). A slip that is NOT all-confirmed was never
   *              placeable, so when repair fails it DEMOTES, underway or not.
   *              🚨 STANDASIS-2026-08-29: the code that used to hold such a slip on the board
   *              anyway is gone -- it was a second freeze rule keyed on kickoff, i.e. this very
   *              branch rebuilt somewhere the owner could not see it. See redraft().
   *   MINTGUARD  a slip is never CREATED after its own earliest kickoff. A bet nobody could
   *              have placed still grades, and on this board a screamer dies as a pair, so a
   *              late mint takes its anchor's whole run with it. Implemented as a pool
   *              exclusion: a player whose match has kicked off cannot appear on a NEW slip,
   *              so a minted slip necessarily locks in the future. (index.html, 2026-08-16.)
   *
   * Everything time-dependent arrives as `nowUTCmin`. Nothing here reads a clock.
   */
  function ticketIsLocked(t, D, nowUTCmin, koOf) {
    if (t.locked) return true;
    var legs = t.players || [];
    if (!legs.length) return false;
    /* OUTSQUAD-2026-08-29 -- `!p.out && !p.void` IS PART OF THE RULE, and was missing.
       `status` is set to 'confirmed' the first time a player appears in a posted sheet and is
       never taken back; being DROPPED from the squad is recorded on `out`. Testing status alone
       therefore read "every leg confirmed" for a slip carrying a man who was not in the XI, so it
       locked, went into `frozen`, and the leg-level repair below -- which already excludes
       `p.out` via alive[] -- never saw it. 2026-08-29, test_stage2_page scenario 2: team news
       lands an hour before kickoff, the card correctly shows the dropped man as out, and his slip
       is untouchable anyway with a full replacement pool available.
       CONFLOCK's definition has always said otherwise ("every leg in the posted lineup / game
       underway, NONE SCRATCHED"), and the baseball engine says it in code -- pinnedP() is
       `!p.out && !p.void && (p.status==='confirmed' || started(n))`. This is that clause, in the
       same shape, so the two rooms state one rule.
       ⚠️ NOT AN UNLOCK. `t.locked` above is a latch and is untouched, so a placed bet is never
       unwound and a late team-news wobble cannot flip a slip on and off the board. This reaches
       only the window before a slip has ever locked, which is exactly when the board is still
       entitled to repair itself.
       CONFLOCK-2026-08-29: the kickoff branch that used to follow is GONE -- see the rule block
       above. `allConf` is THE WHOLE TEST and it is the board's ONLY freeze rule.
       🚨 STANDASIS-2026-08-29: if you are about to add "...but hold it anyway when its match is
       underway" somewhere downstream, that is this deleted branch growing back. It was tried the
       same afternoon it was removed and it put three out-of-squad men on live moons. */
    var allConf = legs.every(function (l) {
      var p = D.players[l.name];
      return p && p.status === 'confirmed' && !p.out && !p.void;
    });
    return allConf;
  }

  /* gate_z is recomputed rather than trusted from the bake, because the bake's value was
     computed over the PRICED FIELD at build time and nothing about team news changes it. It is
     derived here from `blend` -- the same definition soccer_mock.py uses -- so a board baked
     before this field existed still re-drafts correctly. */
  function gateZ(players) {
    var bl = players.map(function (p) { return p.blend; }).filter(function (v) { return v != null; });
    if (bl.length < 2) return function () { return 0; };
    var m = bl.reduce(function (a, b) { return a + b; }, 0) / bl.length;
    var sd = Math.sqrt(bl.reduce(function (a, b) { return a + (b - m) * (b - m); }, 0) / (bl.length - 1)) || 1;
    return function (p) { return p.blend == null ? null : (p.blend - m) / sd; };
  }

  function redraft(D, opts) {
    opts = opts || {};
    var cfg = cfgOf(opts.cfg);
    var now = opts.nowUTCmin;
    var KO = (D.meta && D.meta.ko) || {};
    var koOf = function (g) { var v = KO[String(g)]; return v == null ? null : Number(v); };
    if (now == null) return { tickets: D.tickets, changed: false, why: 'no clock supplied' };
    if (!Object.keys(KO).length) return { tickets: D.tickets, changed: false, why: 'no kickoffs baked (meta.ko)' };

    var xi = opts.xi || null, xiM = opts.xiMatches || null;
    /* XIPARTIAL-2026-08-28: see buildPool. A player whose match has no published
       sheet is UNKNOWN, and unknown is not a dead leg. */
    var xiKnown = function (p) { return !xiM || !!xiM[String(p.game)]; };
    var prior = (D.tickets || []).slice();
    var frozen = [], open = [];
    prior.forEach(function (t) {
      if (ticketIsLocked(t, D, now, koOf)) { t.locked = true; frozen.push(t); }
      else open.push(t);
    });

    /* ONE PLAYER, ONE SLIP -- WITH THE ANCHOR EXCEPTION.
     * "The only legal repeat is an anchor mirroring onto his own builder" (index.html), and on
     * this board an anchor also carries BOTH of his screamers. So a frozen slip spends its
     * PARTNERS outright, but its anchor is not spent -- he is still the anchor of his own other
     * slips, and blocking him from himself is what made the first cut demote Mbappe off a pair
     * he was already anchoring. Anchors are tracked separately, against the budget instead. */
    var spentAsPartner = {}, takenAnchors = {}, anchorMatchCounts = {}, spentAsSingle = {};
    /* LEFTOVERANCHOR-2026-08-28: which frozen builders are REALLY anchors. A builder backs an
       anchor when a moon on this board names him, or when there are no moons at all and the
       board is singles-only. Any other single-leg builder anchors nothing and must not spend
       a seat against ANCH. (Written for LEFTOVERS-2026-08-28, backed out by
       UNLEFTOVER-2026-08-28; kept because it is true of any such builder, whatever mints it.) */
    var frozenMoonAnchor = {};
    frozen.forEach(function (t) {
      if (t.kind === 'moon' && (t.players || []).length) frozenMoonAnchor[t.players[0].name] = true;
    });
    var boardHasMoons = (D.tickets || []).some(function (t) { return t.kind === 'moon'; });
    function claimAnchor(l) {
      if (takenAnchors[l.name]) return;
      takenAnchors[l.name] = true;
      anchorMatchCounts[String(l.game)] = (anchorMatchCounts[String(l.game)] || 0) + 1;
    }
    frozen.forEach(function (t) {
      var legs = t.players || [];
      if (!legs.length) return;
      if (t.kind === 'moon') {
        claimAnchor(legs[0]);
        legs.slice(1).forEach(function (l) { spentAsPartner[l.name] = true; });
      } else if (t.kind === 'builder') {
        /* A frozen BUILDER spends nobody as a PARTNER -- its single leg is its anchor, and on a
           moon+builder board that anchor is already claimed by his screamer, so this is a no-op
           (claimAnchor dedupes by name).
           ⚠️ IT MUST STILL CLAIM THE ANCHOR SLOT. On a SINGLES-ONLY board (SINGLES-2026-08-27)
           there are no moons at all, so this was the only place the anchor could be claimed --
           and skipping it left him absent from `takenAnchors`, free of `freeForPartner`, and
           minted a SECOND TIME by the fresh draft. Caught 2026-08-27 building the scheduled
           rebuild: a four-single board came back as seven slips with three players on two
           tickets each. */
        /* LEFTOVERANCHOR-2026-08-28: only if he anchors something. Under the (since backed
           out) leftover section, eight frozen singles could claim eight seats against an ANCH
           budget of four and zero it out -- no repair, no mint, for the rest of the night. Such
           a builder is spent (not re-mintable, not draftable as a partner) without taking a
           seat. */
        if (frozenMoonAnchor[legs[0].name] || !boardHasMoons) claimAnchor(legs[0]);
        else spentAsSingle[legs[0].name] = true;
      } else {
        legs.forEach(function (l) { spentAsPartner[l.name] = true; });
      }
    });

    var gz = gateZ(Object.keys(D.players).map(function (n) { return D.players[n]; }));
    function rowOf(n) {
      var p = D.players[n], ko = koOf(p.game);
      return {
        name: n, match: String(p.game), game: p.game, kickoff: ko,
        odds: p.odds, TOTAL: p.TOTAL, blend: p.blend,
        gate_z: (p.gate_z != null ? p.gate_z : gz(p)),
        status: p.status, team: p.team, gmatch: p.gmatch, gtime: p.gtime,
        late: p.late, aT: p.aT, wf: p.wf
      };
    }
    /* PLACEABLE. Independent of who is already using him: is he in the squad, priced, and is
       his match still to kick off? The last clause is MINTGUARD -- a player whose match is
       underway can never join a NEW or REPAIRED leg, so no slip is ever created past its own
       kickoff. The XI filter belongs to buildPool, not here, so a pinned leg can survive while
       team news is still incomplete. */
    function placeable(n) {
      var p = D.players[n], ko = koOf(p.game);
      if (!p || p.out || p.void) return false;
      if (p.odds == null) return false;
      if (ko == null || now >= ko) return false;
      return true;
    }
    /* PINNABLE. placeable() MINUS the kickoff clause. MINTGUARD's own wording is that a player
       whose match is underway "can never join a NEW or REPAIRED leg, so no slip is never
       created past its own kickoff" -- it is about CREATING a bet nobody could have placed.
       A leg that is ALREADY on the slip staying exactly where it is creates nothing. Applying
       MINTGUARD to it instead deletes a live, correct leg the moment its own match starts, and
       because the anchor check below is the same test, it demotes the whole anchor group and
       takes two healthy screamers and a builder down with the one bad leg. That is the exact
       opposite of the doctrine three lines up -- "the re-draft replaces just that leg while
       CONFIRMED LEGS STAY PINNED". Out / void / unpriced still disqualify, and the XI filter
       still runs through alive[]. */
    function pinnable(n) {
      var p = D.players[n];
      if (!p || p.out || p.void) return false;
      if (p.odds == null) return false;
      return true;
    }
    function freeToPin(n) {
      return pinnable(n) && !spentAsPartner[n] && !takenAnchors[n] && !spentAsSingle[n];
    }
    /* available as a PARTNER: placeable, not spent on a frozen slip, and not an anchor */
    function freeForPartner(n) {
      return placeable(n) && !spentAsPartner[n] && !takenAnchors[n] && !spentAsSingle[n];
    }
    var field = Object.keys(D.players).filter(freeForPartner).map(rowOf);

    /* ---- LEG-LEVEL REPAIR of the OPEN slips -------------------------------------------
     * MLB doctrine, and the reason slip-level rebuild is wrong: "a scratched leg drops it out
     * of confirmed and the re-draft replaces just that leg while CONFIRMED LEGS STAY PINNED."
     * Rebuilding the whole slip instead loses the anchor, and if that anchor is spent on a
     * frozen slip elsewhere on the card he cannot be drafted back -- so a single unconfirmed
     * partner silently deletes a screamer. That is what the first cut of this function did.
     *
     * An anchor-group is one anchor, his open moons and his builder. All-or-none still applies
     * to the PAIR: if either moon cannot be repaired to three legs the anchor is demoted whole
     * and his slot returns to the budget, exactly as soccer_mock.draft() would have done.
     */
    var alive = {};
    Object.keys(D.players).forEach(function (n) {
      var p = D.players[n];
      alive[n] = !p.out && !p.void && p.odds != null && (!xi || !xiKnown(p) || xi[n]);
    });

    var groups = {}, orderedAnchors = [];
    open.forEach(function (t) {
      if (!t.players || !t.players.length) return;
      var a = t.players[0].name;
      if (!groups[a]) { groups[a] = { anchor: t.players[0], moons: [], builders: [] }; orderedAnchors.push(a); }
      if (t.kind === 'moon') groups[a].moons.push(t);
      else groups[a].builders.push(t);
    });

    var repaired = [], usedPartners = {}, demoted = [];

    /* ==================================================================================
     * 🚨 STANDASIS IS GONE. THERE IS ONE FREEZE RULE AND IT IS CONFLOCK. STANDASIS-2026-08-29.
     * ==================================================================================
     * Owner, looking at the 16:52Z board: "now there are benched players still in lineups."
     * He was right, and this is what put them there.
     *
     * What standAsIs() did: when a group could not be repaired AND any of its matches was
     * underway, it froze the group instead of demoting it -- pushing it onto `frozen`, claiming
     * the anchor, and emitting it verbatim with its dead legs still on it.
     *
     * ⚠️ WHY THAT WAS ALWAYS WRONG, and it is structural, not a tuning question:
     * `groups` is built from `open` ONLY (see above) -- the slips ticketIsLocked() deliberately
     * left UNFROZEN. So every standAsIs() call froze a slip CONFLOCK had just decided not to
     * freeze. It was a SECOND FREEZE RULE, keyed on KICKOFF, sitting behind the first -- which
     * is precisely the branch the owner had deleted from ticketIsLocked() four hours earlier
     * the same day. The rule went out the front door and came back through this one.
     *
     * Measured on the live 16:52Z board, replayed at 17:00Z:
     *     with standAsIs     locked 9  ->  CONFLOCK freezes 6, standAsIs froze 3 more, and
     *                        those 3 are DIPPING EFFORT (Kean, Richarlison), CURLED HOME
     *                        (Osula) and HALF VOLLEY (Pinamonti) -- three out-of-squad men
     *                        riding live moons, which is the Beto complaint verbatim.
     *     without            locked 6, demoted 2, minted 3, reseated 1 -- 12 tickets, four
     *                        moon anchors, Guirassy's orphaned single reseated to the lunch
     *                        special, and NO out or benched player anywhere on the card.
     *
     * The argument for it was "never delete a bet that was already live". That argument is
     * answered by the owner's own rule and does not need this code: a slip he could have PLACED
     * is a slip whose legs are all confirmed, and CONFLOCK freezes exactly those -- latched, so
     * `t.locked` survives and it is emitted verbatim and graded (OUTSQUAD: "the out player is
     * STILL on his slip"). A slip that is NOT all-confirmed was never placeable as a slip, so
     * demoting it deletes nothing that was ever a bet; it removes a card that cannot hit.
     * `ledger-rule-2026-08-29` protects PLACED bets. It was never a licence to freeze open ones.
     *
     * So: repair if you can, and if you cannot, the group demotes -- underway or not. The board
     * would rather be short a slip than show one that is dead on the page. */

    orderedAnchors.forEach(function (an) {
      var g = groups[an];
      var already = !!takenAnchors[an];          // he already anchors a frozen slip
      if (!alive[an] || !pinnable(an) || spentAsPartner[an]) {
        demoted.push({ anchor: an, why: 'anchor is no longer startable' }); return;
      }
      if (!already && (anchorMatchCounts[String(g.anchor.game)] || 0) >= cfg.ANCH_PER_GAME) {
        demoted.push({ anchor: an, why: 'match already at ANCH_PER_GAME' }); return;
      }
      if (!already && Object.keys(takenAnchors).length >= cfg.ANCH) {
        demoted.push({ anchor: an, why: 'anchor budget full' }); return;
      }

      /* candidate partners, strongest first: the gated pool minus the anchor and anything
         already committed anywhere on the card */
      /* ANCHORS ARE NEVER PARTNERS. A cold draft gets this for free -- anchors are seated first
         and removed from the partner pool -- but the repair path walks anchor groups one at a
         time, so an anchor whose OWN group has not been reached yet is still absent from
         `takenAnchors` and `freeForPartner` happily hands him to somebody else's moon. He then
         anchors his own two screamers as well, and the board ships one man on four slips with
         three moons under a MOONS_PER_ANC of 2. Measured 2026-08-29: repairing Schick's moon
         drafted Serhou Guirassy as its third leg, and Guirassy came out anchoring three.
         `groups[name]` is truthy exactly for the anchors of the open groups, which is the set
         to exclude. Scoped to `cands` on purpose -- `field` and the fresh draft below are
         untouched, so a DEMOTED anchor can still be re-drafted. */
      var cands = withStrength(buildPool(field, cfg, { xi: xi, xiMatches: xiM, exclude: usedPartners }))
        .filter(function (p) { return p.name !== an && !groups[p.name]; });

      /* 🚨 REPAIRWIDE-2026-08-30 -- REPAIR DRAWS FROM THE SAME WIDE POOL THE TOP-UP DOES.
       * Owner, on losing a leg that had already scored: "why get rid of aubamayeng though?"
       * `cands` above is `buildPool`, so leg repair is GATED while the pair top-up below is not.
       * On a thin field that asymmetry does not merely fail to repair -- it DESTROYS the slip,
       * and the all-or-none pair rule takes its partner slip with it.
       * Measured 2026-08-30 18:07Z: Anssumane Fati went out of Monaco's squad. Repairing his
       * leg needed one man from a third match, unstarted, above Z_GATE -- there were three such
       * men on the whole card and they spanned two matches. Repair failed, the pair was demoted,
       * and PIERRE-EMERICK AUBAMEYANG WENT WITH IT -- a pinned leg that had already SCORED, 17'.
       * The board then re-minted around him. A leg that has hit is the last thing a re-draft
       * should be allowed to throw away.
       * So when the gated pool cannot finish a slip, fall through to the same field the top-up
       * uses: ALIVE (so the XI filter still applies -- benched is still benched) and PLACEABLE
       * (so MINTGUARD still holds), just without Z_GATE and GAME_CAP. Owner's 2026-08-30 ruling
       * -- "leave it ungated, just for soccer though, the pool seems to be smaller" -- was made
       * about exactly this shape of field; this is the same rule reaching the same problem one
       * block earlier, where it saves the pinned legs instead of replacing them.
       * ⚠️ GATED FIRST, ALWAYS. The wide list is a FALLBACK, never a preference: a slip that can
       * be finished from the pool the model actually likes is finished from it, and this only
       * runs when the alternative is deleting the bet. */
      var wide = withStrength(field.filter(function (p) { return alive[p.name]; }))
        .filter(function (p) { return p.name !== an && !groups[p.name]; });

      var fixed = [], ok = true, localUsed = {};
      for (var i = 0; i < g.moons.length && ok; i++) {
        var t = g.moons[i];
        var legs = [rowOf(an)], seen = {}; seen[String(g.anchor.game)] = true;
        /* PIN the legs that are still good, in their original order */
        t.players.slice(1).forEach(function (l) {
          if (legs.length >= 3) return;
          if (!alive[l.name] || !freeToPin(l.name)) return;
          if (seen[String(l.game)] || usedPartners[l.name] || localUsed[l.name]) return;
          if (!spanOk(legs.concat([rowOf(l.name)]), cfg)) return;
          legs.push(rowOf(l.name)); seen[String(l.game)] = true; localUsed[l.name] = true;
        });
        /* REFILL whatever the pins left short -- the gated pool first, the wide field only if
           the slip would otherwise die (REPAIRWIDE-2026-08-30). */
        [cands, wide].forEach(function (list) {
          for (var c = 0; c < list.length && legs.length < 3; c++) {
            var cd = list[c];
            if (seen[cd.match] || usedPartners[cd.name] || localUsed[cd.name]) continue;
            if (!spanOk(legs.concat([cd]), cfg)) continue;
            legs.push(cd); seen[cd.match] = true; localUsed[cd.name] = true;
          }
        });
        if (legs.length !== 3) ok = false; else fixed.push({ t: t, legs: legs });
      }

      if (!ok || fixed.length !== g.moons.length) {
        demoted.push({ anchor: an, why: 'could not repair the pair' });
        return;
      }
      claimAnchor(g.anchor);
      Object.keys(localUsed).forEach(function (k) { usedPartners[k] = true; });
      fixed.forEach(function (f) {
        repaired.push({ kind: 'moon', legs: f.legs, risk: cfg.MOON_RISK, priorName: f.t.name });
      });
      g.builders.forEach(function (b) {
        /* ⚠️ `b.kind`, NOT 'builder'. SHAPEREPAIR-2026-08-31. The group split above files every
           single-leg slip under `builders`, so a 🍱 lunch special or a 🌃 nightcap arrives here
           too -- and hardcoding the kind turned it back into a builder on every build. That was
           masked for as long as ORPHANSECTION existed to relabel it a few lines later, and stood
           up the moment UNORPHAN removed the relabel: the specials section emptied, shape repair
           minted a fresh single into it, and the board grew by one slip every five minutes.
           A repair swaps a LEG. It does not get to change what kind of bet the slip is. */
        repaired.push({ kind: b.kind || 'builder', legs: [rowOf(an)], risk: cfg.SINGLE_STAKE,
                        priorName: b.name });
      });
    });

    /* ---- FRESH DRAFT for whatever anchor budget is still unspent ----------------------- */
    var budget = Math.max(0, cfg.ANCH - Object.keys(takenAnchors).length);
    var remaining = field.filter(function (p) { return !usedPartners[p.name] && !takenAnchors[p.name] && !spentAsSingle[p.name]; });
    var res = budget > 0
      ? draft(remaining, cfg, { xi: xi, xiMatches: xiM, anchorBudget: budget, anchorMatchCounts: anchorMatchCounts,
                                slateMatches: Object.keys(KO).length })
      : { tickets: [], pool: [], anchors: 0, thin: false };

    /* NAMING. A slip whose exact leg set survives keeps its title, so an unchanged draft does
       not churn every name on the card. Anything else takes the next unused title: a killed
       slip's name is SPENT for the night (REDRAFT-2026-08-18 -- a re-minted nightcap once came
       back under the dead ticket's own name, so the board showed one ticket that had been two
       bets). Names in use on frozen slips are spent by definition. */
    var spent = {};
    frozen.forEach(function (t) { spent[t.name] = true; });
    function pickName(kind, priorName) {
      /* A REPAIRED slip keeps its own title -- it is the same bet with a leg swapped, and
         renaming it every time team news moves would churn the whole card for nothing. A slip
         that could not be repaired is dead and its name is SPENT for the night
         (REDRAFT-2026-08-18: a re-minted nightcap once came back under the dead ticket's own
         name, so the board showed one ticket that had been two bets). */
      if (priorName && !spent[priorName]) { spent[priorName] = true; return priorName; }
      var pool = NAMES[kind] || ['Ticket'];
      for (var i = 0; i < pool.length; i++) if (!spent[pool[i]]) { spent[pool[i]] = true; return pool[i]; }
      return pool[0];
    }
    /* names belonging to demoted anchors are burnt before anything new is handed one */
    demoted.forEach(function (d) {
      var g = groups[d.anchor];
      if (!g) return;
      g.moons.concat(g.builders).forEach(function (t) { spent[t.name] = true; });
    });

    function build(list) {
      return list.map(function (t) {
        var legs = t.legs.map(function (p) { return legOf(p.name, D.players[p.name]); });
        return mkTicket(t.kind, legs, t.risk, pickName(t.kind, t.priorName), koOf, D.players);
      });
    }
    var repairedT = build(repaired);
    var mintedT = build(res.tickets.map(function (t) { return { kind: t.kind, legs: t.legs, risk: t.risk }; }));

    var out = frozen.concat(repairedT, mintedT);

    /* ==================================================================================
     * ORPHANSECTION-2026-08-29 -- a single with no moons behind it is a LUNCH SPECIAL or a
     * NIGHTCAP, not an anchor.
     * ==================================================================================
     * Owner: "then use the lunch special and nightcap. thats what theyre for."
     *
     * How the orphan appears: team news kills an anchor's partners, his PAIR cannot be rebuilt
     * (all-or-none), so the group is demoted -- but his BUILDER has already latched under
     * CONFLOCK because its only leg is confirmed, so it is emitted verbatim and survives him.
     * LEFTOVERANCHOR-2026-08-28 then correctly refuses to let that moonless builder hold a seat
     * against ANCH, the budget frees, and the fresh draft mints a replacement anchor. The card
     * is right and every rule fired as written -- but it SHOWS five names where ANCH is four,
     * because a lone builder is drawn exactly like an anchor. That is the question the owner
     * asked on 2026-08-26 about the baseball board (`stranded-anchor-2026-08-26.md`), where the
     * options were listed and "move the orphan, keep the bet" was the safest. This is that move,
     * with the section he named.
     *
     * ⚠️ THE BET IS NOT TOUCHED. Same player, same stake, same price, SAME TITLE -- only the
     * section changes. Renaming a live slip is REDRAFT-2026-08-18's failure ("the board showed
     * one ticket that had been two bets"), so the title rides along even though it came from the
     * builder pool.
     *
     * lunch vs nightcap is the board's OWN flag: soccer_payload.py stamps
     * `late = et_min(kickoff) >= 17*60` on every player and rowOf() already carries it, so the
     * cutoff is defined once and this module still reads no clock. It matches the section copy
     * the fork writes -- Lunch Special is "one player, best model score in an EARLY KICKOFF",
     * and the nightcap's empty state is "no LATE play posted right now".
     *
     * `soccer_grade.py` KINDS already contains 'lunch' and 'late', and soccer_payload's ledger
     * `cats` already counts them, so a relabelled slip grades and books exactly as before. It
     * also retires the fork's `lunch-empty` copy ("the scorer drafts anchors and screamers
     * only"), which stops being true the first time this fires.
     */
    /* ==================================================================================
     * FINALREPAIR-2026-08-29 -- NEVER SHIP A SHORT MOON. Port of index.html's FINAL REPAIR.
     * ==================================================================================
     * Owner: "now jonathan david only has one moon. what is the fucking problem. its the same
     * fucking draft system as baseball" -- then: "minus the chalkban".
     *
     * He is right that it is the same system, and this is the piece soccer never got.
     * index.html:2665, verbatim:
     *
     *     FINAL REPAIR (shared, both paths, on the near-final ticket set): pair any LIVE moon
     *     anchor still short of MOONS_PER_ANC from the WIDEST pool (any scored bat with odds,
     *     alive, in-window, distinct game). Uses out.push directly and runs after both branches,
     *     so nothing upstream prevents it. NEVER SHIPS A SHORT MOON.
     *
     * ⚠️ THE POINT IS THE **WIDEST** POOL. Everything above this -- repair `cands`, the fresh
     * draft -- draws from buildPool(), i.e. Z_GATE + GAME_CAP + the XI filter. When team news
     * kills a partner late in a staggered card that pool is nearly empty, the pair cannot be
     * rebuilt, the group demotes, and the anchor ships ONE moon. Measured 2026-08-29: David lost
     * "Curled Home" and the board fell to 8 slips with three anchors holding 2/1/1 moons, while
     * fourteen priced, alive, unstarted players sat in the field unused because they were below
     * the gate. The gate decides who is worth ANCHORING. It is not a reason to ship a lopsided
     * anchor.
     *
     * ⚠️ MINUS THE CHALK BAN, per the owner. Baseball filters `!chalk[n]`; soccer has no chalk
     * ban (CHALK_N is not a soccer constant at all), so that clause is simply absent.
     *
     * ⚠️ NO MINTGUARD HERE, AND THAT IS DELIBERATE -- IT IS WHAT BASEBALL DOES.
     * The baseball filter is `!pl[n] && n!==a && !chalk[n] && !P[n].out && !P[n].void &&
     * P[n].odds!=null`, and its anchor test is `pinnedP(a) || (aliveP(a) && inPool[a])`. NEITHER
     * excludes a bat whose game has started -- unlike the SHAPE REPAIR block twenty lines below
     * it, which does test `started(n)`. That asymmetry is in the baseball engine on purpose:
     * shape repair MINTS A NEW SECTION, while final repair COMPLETES A SHAPE the board already
     * committed to when it seated the anchor. The pair is one bet in two halves; finishing it is
     * not creating a new one.
     * The first cut of this port added placeable() anyway. The owner had authorised exactly one
     * deviation -- "minus the chalkban" -- and that was a second one, so it came straight back
     * out. It was also not academic: it is precisely why David stayed on one moon after his own
     * 18:45Z kickoff. Everything ELSE the draft mints still goes through placeable(); this block
     * alone follows baseball.
     *
     * Runs BEFORE the ORPHANSECTION block below on purpose, so a single that gets its screamers
     * back is counted as a real anchor and never reseated to the lunch special. */
    var moonCnt = {}, onSlip = {};
    out.forEach(function (t) {
      var legs = t.players || [];
      if (t.kind === 'moon' && legs.length) moonCnt[legs[0].name] = (moonCnt[legs[0].name] || 0) + 1;
      legs.forEach(function (l) { onSlip[l.name] = true; });
    });
    /* 🚨 REPAIRPAIR-2026-08-30 -- AN ANCHOR WHO LOST BOTH SCREAMERS IS STILL AN ANCHOR.
     * Owner, on Anssumane Fati going out of Monaco's squad and nobody arriving to replace him:
     * "is there a reason fati isnt getting replaced?" -- then "yes" to re-pairing from the
     * ungated field.
     * `moonCnt` is built by walking `out` and counting MOONS, so an anchor whose pair was
     * demoted whole has NO ENTRY and the top-up below never looks at him. That is the exact
     * case that needs it most. Measured 2026-08-30 18:12Z: Fati went `out` and Andrea Pinamonti
     * was benched, so BOTH of Lautaro Martinez's screamers failed repair -- the gated pool had
     * three men left in unstarted matches spanning only TWO matches and a screamer needs three
     * -- the all-or-none pair rule took the pair, and he was left as a stranded single. The
     * ungated top-up had candidates the whole time (games 14 and 15 are full of alive, priced
     * men, just none above Z_GATE) and could not reach him, because he had dropped out of the
     * list it iterates.
     * A builder on the board IS the board's commitment to that anchor, so seed him at zero and
     * let the same block below rebuild his pair.
     * ⚠️ MINTGUARD APPLIES TO A FROM-ZERO RE-PAIR, and this is the one place it must. The
     * top-up deliberately skips `placeable()` when COMPLETING a pair -- "finishing it is not
     * creating a new one" -- but re-pairing from nothing creates two brand-new slips, and a
     * slip built out of matches already underway is a bet nobody could have placed. So the
     * anchor and every candidate must still be ahead of the clock here. Pair completion is
     * untouched and behaves exactly as before. */
    var zeroMoon = {};
    /* A DEMOTED ANCHOR IS A BUILDER, AND THAT IS HOW WE FIND HIM AGAIN.
     * REPAIRPAIR-2026-08-30's case is real and measured: when both of Lautaro Martinez's
     * screamers failed repair the all-or-none pair rule took them, `moonCnt` had no entry for
     * him, and the ungated top-up below -- which had candidates the whole time -- could not
     * reach him. A builder on the board IS the board's commitment to that anchor, so seed him at
     * zero and let the same block rebuild his pair.
     *
     * ⚠️ NARROWED BY UNORPHAN-2026-08-31. This used to match one-leg SHAPE rather than kind,
     * because ORPHANSECTION had relabelled the demoted anchor 'lunch' and looking for a builder
     * found nothing. That relabel is gone, so the kind is honest again -- and matching shape is
     * exactly what turned a minted lunch special into a full anchor with two screamers on the
     * next build. A 🍱 or 🌃 is NOT a stranded anchor: it is its own bet, in its own section,
     * and it is not promoted into the anchors by a top-up. It stays one leg for the night.
     *
     * The ANCH budget still guards this -- a board that is not short of anchors promotes
     * nobody. */
    var _anchorsNow = Object.keys(takenAnchors).length + (res.anchors || 0);
    out.forEach(function (t) {
      var legs = t.players || [];
      if (legs.length !== 1) return;
      if (t.kind !== 'builder') return;
      var an = legs[0].name;
      if (moonCnt[an] != null) return;
      if (_anchorsNow >= cfg.ANCH) return;
      if (!alive[an] || !placeable(an)) return;
      moonCnt[an] = 0; zeroMoon[an] = true; _anchorsNow++;
    });

    var topped = [];
    /* 🚨 TOPUPORDER-2026-08-30. THE ANCHORS ARE TOPPED UP STRONGEST FIRST, NOT IN THE ORDER
       THEY HAPPEN TO SIT IN `out`.
       `Object.keys(moonCnt)` is insertion order, and `moonCnt` is filled by walking `out` --
       frozen slips, then repaired, then minted, then the fresh draft. WHICH SLIPS ARE FROZEN
       DEPENDS ON THE INSTANT THE CALLER RUNS, so the page and the server reach this block with
       different anchor order and the top-up is a first-come draw over one shared candidate list.
       Same slate, same minute, two different boards.
       MEASURED 2026-08-30, and this is the incident: the owner's tab topped Kylian Mbappe first,
       took Moussa Sylla (124.8, game 8, distinct from Mbappe's game 6), and Esteban Lepaul's pair
       then took the strongest man left -- Jude Bellingham -- giving the slip he actually placed,
       Lepaul + Bellingham + Rashford. The server had Sylla already frozen on Lepaul's slip, so
       Mbappe's top-up skipped Bellingham (same match as the anchor, blocked by `seenG`) and fell
       to Santos Matheus Cunha. Neither board is wrong under the rule; they simply arrived here in
       a different order, and only one of them is what the owner had money on.
       Sorting by TOTAL then name is the ordering `withStrength` already uses everywhere else in
       this file, so both callers now walk the anchors identically whatever their frozen set.
       ⚠️ THIS DOES NOT GATE THE TOP-UP. Owner's ruling, 2026-08-30: "leave it ungated, just for
       soccer though, the pool seems to be smaller" -- on a 225-name card with 15-37 through
       Z_GATE, gating the pair completion would demote anchors rather than finish them. The
       "widest pool means no Z_GATE and no GAME_CAP" rule below stands exactly as written; this
       changes only the ORDER in which anchors draw from it. */
    Object.keys(moonCnt).sort(function (x, y) {
      var dx = (D.players[y] ? D.players[y].TOTAL || 0 : 0) - (D.players[x] ? D.players[x].TOTAL || 0 : 0);
      return dx || (x < y ? -1 : x > y ? 1 : 0);
    }).forEach(function (an) {
      var ap = D.players[an];
      if (!ap || !alive[an] || !pinnable(an)) return;      // a dead anchor is not topped up
      if (zeroMoon[an] && !placeable(an)) return;          // REPAIRPAIR: MINTGUARD on a new pair
      var guard = 0;
      while (moonCnt[an] < cfg.MOONS_PER_ANC && guard++ < cfg.MOONS_PER_ANC) {
        var rows = [rowOf(an)], seenG = {};
        seenG[String(ap.game)] = true;
        /* ⚠️ "ALIVE" IS alive[], NOT `!out && !void`. Baseball writes the filter as
           `!P[n].out && !P[n].void && P[n].odds!=null` because a scratched bat is exactly what
           `out` means there. On the soccer board a man dropped from a published XI is not
           flagged `out` -- he is simply absent from `xi`, and only alive[] (which folds in
           XIPARTIAL's per-match `xiKnown`) knows that. The first cut of this port used the
           baseball spelling literally and re-drafted LUKA JOVIC, the very leg team news had just
           removed, back onto a fresh moon -- caught by test_redraft "the dropped leg appears
           nowhere". Widest pool means no Z_GATE and no GAME_CAP. It does not mean benched. */
        var cnd = Object.keys(D.players).filter(function (n) {
          /* REPAIRPAIR-2026-08-30: `placeable` only for a from-zero re-pair -- see above. A pair
             being COMPLETED keeps the widest pool exactly as it always has. */
          return !onSlip[n] && n !== an && alive[n] && (!zeroMoon[an] || placeable(n));
        }).sort(function (x, y) {
          var dx = (D.players[y].TOTAL || 0) - (D.players[x].TOTAL || 0);
          return dx || (x < y ? -1 : x > y ? 1 : 0);
        });
        for (var ci = 0; ci < cnd.length && rows.length < 3; ci++) {
          var n = cnd[ci], r = rowOf(n);
          if (seenG[String(D.players[n].game)]) continue;
          if (!spanOk(rows.concat([r]), cfg)) continue;
          rows.push(r); seenG[String(D.players[n].game)] = true;
        }
        if (rows.length < 3) break;
        rows.forEach(function (r) { onSlip[r.name] = true; });
        out.push(mkTicket('moon', rows.map(function (r) { return legOf(r.name, D.players[r.name]); }),
                          cfg.MOON_RISK, pickName('moon', null), koOf, D.players));
        moonCnt[an]++;
        topped.push({ anchor: an, legs: rows.map(function (r) { return r.name; }) });
      }
    });

    /* UNORPHAN-2026-08-31. THE ORPHANSECTION RECLASSIFY LIVED HERE AND IS GONE, NOT DISABLED.
     * Owner: "orphan is not part of baseball, get rid of it. especially if its messing things up."
     *
     * ORPHANSECTION-2026-08-29 / ORPHANSURPLUS / ANCHORISMOONS rewrote a moonless single-leg
     * slip's `kind` to 'lunch' or 'late'. Baseball had the same question and answered it the
     * other way, and the answer is still in index.html:1006 with nothing calling it:
     *
     *     const _stranded=t=>t.kind==='builder'&&t.anchor&&!_mAnch[t.anchor];
     *     /* ... it is a real placed builder and it grades as one. So it renders under Anchors
     *        again, where its own kind always said it belonged. `_stranded` is left defined;
     *        nothing else calls it. *(/)
     *
     * Baseball's 🍱 and 🌃 are not where demoted anchors go -- they are minted from the FIELD by
     * SHAPE REPAIR (index.html:2755). Soccer took the demotion and never took the mint.
     * SHAPEREPAIR-2026-08-31 adds the mint; this removes the demotion.
     *
     * It was also the ratchet. The relabel PERSISTS onto the next build's prior board, so the
     * promotion block below had to match a slip's SHAPE rather than its kind to find a demoted
     * anchor again -- which meant it adopted ANY single-leg slip as a zero-moon anchor and
     * FINALREPAIR built it a pair. Reproduced on the unpatched engine: a lunch special becomes a
     * full anchor with two screamers on the next build, 7 slips to 9. With the relabel gone a
     * moonless single IS a builder, so that block looks for a builder again.
     *
     * `reseated` stays and is now always empty: soccer_rebuild_cli.js and the workflow read it,
     * and a key that vanishes is a crash somewhere I have not looked. */
    var reseated = [];

    /* ==================================================================================
     * 🚨 THE SPECIALS ARE PART OF THE SHAPE. SHAPEREPAIR-2026-08-31.
     * ==================================================================================
     * Owner: "yea it shouldnt be only anchors that can fall through to the specials."
     *
     * ORPHANSECTION above RECLASSIFIES a single that is already in `out`; it never mints one. The
     * only thing that can BE such a single is an anchor's builder, so the lunch special and the
     * nightcap were reachable by exactly one route -- be drafted as an anchor, then lose your
     * screamers. When the anchor dies his builder dies with him and nothing is left to fall
     * through: on 2026-08-31, with Raphinha struck out, the board redrafted to ZERO tickets while
     * 24 alive priced players sat in two matches that had not kicked off.
     *
     * This is index.html's SHAPE REPAIR (REDRAFT-2026-08-18) in soccer's spelling -- "The board's
     * shape is fixed ... A PLACED single that dies stays dead: that is a settled bet. An EMPTY
     * SLOT gets drafted, same as a short anchor." One per empty section, from the whole field,
     * which is the same cap that block states: "one nightcap and one lunch play, full stop."
     *
     * ⚠️ NOT UNLEFTOVER-2026-08-28. That minted a single for EVERY gated player who made no slip,
     * capped at eight -- six a night on a healthy board. This mints at most one, and only into a
     * section that is empty. Measured over the five committed boards: 3 slips, -1.00u, which is
     * not a sample and is recorded in shaperepair_fix.py only so nobody mistakes it for evidence.
     *
     * ⚠️ THE GUARD IS THE SLATE, NOT THE BOARD. `outHasMoons` is false both on a two-match
     * singles-only slate -- where every builder IS an anchor, and reclassifying "turned it into
     * four lunch specials on the first cut" -- and on a board that drafted nothing, which is the
     * case this exists for. So ask the slate directly, which is SINGLES-2026-08-27's own test.
     *
     * `alive[]` and not `!p.out`: a man dropped from a published XI is not flagged `out` on this
     * board, and the first cut of the REPAIRWIDE port used the baseball spelling literally and
     * re-drafted the very leg team news had just removed. `freeForPartner()` carries MINTGUARD
     * (no slip created past its own kickoff) and the partner / anchor / burnt-single exclusions.
     * TOTAL order with a name tiebreak, so the pick is deterministic and testable. */
    var shaped = [];
    if (Object.keys(KO).length >= cfg.MOON_LEGS) {
      var haveKind = {}, onBoard = {};
      out.forEach(function (t) {
        haveKind[t.kind] = true;
        (t.players || []).forEach(function (l) { onBoard[l.name] = true; });
      });
      [['lunch', false], ['late', true]].forEach(function (spec) {
        var kind = spec[0], wantLate = spec[1];
        if (haveKind[kind]) return;
        var c = Object.keys(D.players).filter(function (n) {
          return !onBoard[n] && alive[n] && freeForPartner(n) &&
                 !!(D.players[n].late) === wantLate;
        }).sort(function (x, y) {
          var dx = (D.players[y].TOTAL || 0) - (D.players[x].TOTAL || 0);
          return dx || (x < y ? -1 : x > y ? 1 : 0);
        });
        if (!c.length) return;
        var n = c[0];
        out.push(mkTicket(kind, [legOf(n, D.players[n])], cfg.SINGLE_STAKE,
                          pickName(kind, null), koOf, D.players));
        onBoard[n] = true;
        haveKind[kind] = true;
        shaped.push({ name: n, kind: kind });
      });
    }

    /* ==================================================================================
     * SHORTLAST-2026-08-29 -- an anchor that is short a screamer sorts to the BOTTOM.
     * ==================================================================================
     * Owner: "leave it then but put it at the bottom so the other anchor's moons arent split up."
     *
     * When team news kills a pair that cannot be repaired (MINTGUARD leaves no legal partner once
     * the window has kicked off), an anchor can finish the day with ONE moon instead of
     * MOONS_PER_ANC. That slip is a real bet and stays -- the owner ruled on that directly. But
     * emitted in place it lands BETWEEN two complete anchors' pairs, so the screamers section
     * reads pair / single / pair and the pairs no longer sit together.
     *
     * So: stable sort, complete anchors first, short anchors last. Nothing else moves --
     * `(a.i - b.i)` keeps every other slip in the order the draft emitted it.
     *
     * ⚠️ SAFE ONLY BECAUSE TITLES NO LONGER RIDE ON POSITION. soccer_payload.shape_ticket used to
     * derive every title from the ticket's ARRAY INDEX, so any reorder renamed live slips --
     * REDRAFT-2026-08-18's exact failure. See NAMECARRY-2026-08-29: the title the draft assigned
     * here now travels in tickets.json and the payload uses it. Do not reintroduce an ordering
     * change without that carry in place.
     * `sig()` sorts before comparing, so a pure reorder is correctly reported as UNCHANGED and
     * does not churn a commit. */
    var moonCount = {};
    out.forEach(function (t) {
      if (t.kind === 'moon' && (t.players || []).length) {
        var a = t.players[0].name; moonCount[a] = (moonCount[a] || 0) + 1;
      }
    });
    var isShortAnchor = function (t) {
      var legs = t.players || []; if (!legs.length) return false;
      var c = moonCount[legs[0].name] || 0;
      return c > 0 && c < cfg.MOONS_PER_ANC;      /* 0 moons = a lunch/nightcap, its own section */
    };
    /* ⚠️ AND KEEP EACH ANCHOR'S SLIPS TOGETHER. ANCHORGROUP-2026-08-29.
       Owner: "oskarson and davids moons arent next to each other now. 1 of each are next to
       each other."
       FINALREPAIR pushes a topped-up moon onto the END of `out`, so an anchor's second screamer
       landed after everyone else's and the screamers section read Schick / Schick / David /
       Oskarsson / David / Oskarsson. Sorting on `s` alone could not fix it: once the top-up has
       run nobody IS short, so SHORTLAST no longer moves anything.
       Sort key is (short?, the anchor's FIRST appearance, original index) -- so complete anchors
       come first in the order the draft seated them, every anchor's slips are contiguous, and
       within an anchor the emit order is untouched. Still a stable display sort and still
       invisible to `sig()`, which sorts before comparing. */
    var anchorFirst = {};
    out.forEach(function (t, i) {
      var legs = t.players || []; if (!legs.length) return;
      var a = legs[0].name;
      if (anchorFirst[a] == null) anchorFirst[a] = i;
    });
    var groupKey = function (t) {
      var legs = t.players || [];
      return legs.length ? anchorFirst[legs[0].name] : 1e9;
    };
    out = out.map(function (t, i) { return { t: t, i: i, s: isShortAnchor(t) ? 1 : 0, g: groupKey(t) }; })
             .sort(function (a, b) { return (a.s - b.s) || (a.g - b.g) || (a.i - b.i); })
             .map(function (x) { return x.t; });

    var sig = function (ts) {
      return ts.map(function (t) {
        return t.kind + ':' + (t.players || []).map(function (l) { return l.name; }).join('+');
      }).sort().join('|');
    };
    /* RELEASED means "left the board", and it used to be reported as `open.length` -- every slip
       that was not frozen at the TOP of the pass, whether or not it survived. That was only ever
       right because the old CONFLOCK froze everything at kickoff, so `open` was empty exactly
       when nothing could be lost. With CONFLOCK-2026-08-29 a slip can be open, be repaired or
       stand, and still be on the board at the end -- so count what actually went missing. */
    var sigOf1 = function (t) {
      return t.kind + ':' + (t.players || []).map(function (l) { return l.name; }).join('+');
    };
    var outSet = {};
    out.forEach(function (t) { outSet[sigOf1(t)] = true; });
    var releasedN = prior.filter(function (t) { return !outSet[sigOf1(t)]; }).length;
    return {
      tickets: out,
      changed: sig(out) !== sig(prior),
      locked: frozen.length,
      repaired: repairedT.length,
      minted: mintedT.length,
      released: releasedN,
      demoted: demoted,
      reseated: reseated,
      shaped: shaped,
      topped: topped,
      anchors: Object.keys(takenAnchors).length + (res.anchors || 0),
      thin: !!res.thin,
      poolSize: (res.pool || []).length
    };
  }

  var api = {
    DEFAULTS: DEFAULTS, cfgOf: cfgOf, buildPool: buildPool, withStrength: withStrength,
    spanOk: spanOk, draftN: draftN, draft: draft, nameSet: nameSet,
    NAMES: NAMES, BADGE: BADGE, a2d: a2d, rrMaxProfit: rrMaxProfit,
    legOf: legOf, lockOf: lockOf, mkTicket: mkTicket,
    ticketIsLocked: ticketIsLocked, gateZ: gateZ, redraft: redraft
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.SoccerDraft = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
