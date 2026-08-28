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
    WIN: 180,            // minutes: widest kickoff span one slip may bridge (MLB uses 120)
    Z_GATE: 0.75,        // pool gate, in SDs of blend above the slate mean
    GAME_CAP: 4,         // most pool players from any one match
    ANCH: 4,             // anchor TARGET -- see THINSLATE below, this is a ceiling not a promise
    MOON_LEGS: 3,        // legs on a screamer, each from a DIFFERENT match
    MOONS_PER_ANC: 2,
    ANCH_PER_GAME: 2,
    MOON_RISK: 2.0,
    SINGLE_STAKE: 1.0,
    LEFTOVER_CAP: 8      // LEFTOVERS-2026-08-28: most gated-but-undrafted players shipped as singles
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

    for (var i = 0; i < byStrength.length && anchors.length < n; i++) {
      var p = byStrength[i];
      if ((perG[p.match] || 0) < cfg.ANCH_PER_GAME) { anchors.push(p); perG[p.match] = (perG[p.match] || 0) + 1; }
    }
    if (anchors.length < n) return [];

    var used = nameSet(anchors);
    var partners = byStrength.filter(function (p) { return !used[p.name]; });

    var out = [], spent = {};
    for (var a = 0; a < anchors.length; a++) {
      var anc = anchors[a], made = [], local = {};
      for (var m = 0; m < cfg.MOONS_PER_ANC; m++) {
        var legs = [anc], seen = {}; seen[anc.match] = true;
        for (var c = 0; c < partners.length && legs.length < 3; c++) {
          var cand = partners[c];
          if (seen[cand.match] || spent[cand.name] || local[cand.name]) continue;
          if (spanOk(legs.concat([cand]), cfg)) { legs.push(cand); seen[cand.match] = true; local[cand.name] = true; }
        }
        if (legs.length === 3) made.push(legs);
      }
      if (made.length !== cfg.MOONS_PER_ANC) return [];      // this anchor count does not fit
      for (var q in local) if (local.hasOwnProperty(q)) spent[q] = true;
      made.forEach(function (legs) { out.push({ kind: 'moon', legs: legs, risk: cfg.MOON_RISK }); });
    }
    return out;
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

  /* LEFTOVERS-2026-08-28 -- owner's call. A player who CLEARED THE GATE and then made no slip is
   * a bet the board found and dropped on the floor. On a thin XI that is most of the pool: on
   * 2026-08-28, nine players cleared the gate, two anchors needed ten distinct names so the board
   * fell to ONE anchor, and four gated players went nowhere -- Antonio Martinez, Lucas Boye,
   * Aitor Manas, Luis Diaz. Ship them as straight singles.
   *
   * They are `builder` kind on purpose. It is the shape they already are (one leg, SINGLE_STAKE),
   * it renders through the same card path, and soccer_grade.py folds it into the ledger with no
   * change -- exactly the reasoning MLB used when the Family Meal was made a real ticket kind
   * rather than bespoke markup. A NEW kind would need the renderer, the grader and the tracker.
   *
   * MINTGUARD is not re-checked here and must not be: redraft() only ever hands this function a
   * field already filtered by placeable(), so a leftover in a match that has kicked off never
   * reaches the draft. On a first build there is no clock and nothing has started.
   *
   * Capped, because the point is the bets the draft nearly made, not a second players tab. */
  function leftoverSingles(byStrength, used, cfg) {
    var out = [];
    for (var i = 0; i < byStrength.length && out.length < cfg.LEFTOVER_CAP; i++) {
      var p = byStrength[i];
      if (used[p.name]) continue;
      out.push({ kind: 'builder', legs: [p], risk: cfg.SINGLE_STAKE });
    }
    return out;
  }

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
      var usedS = {}; singles.forEach(function (t) { usedS[t.legs[0].name] = true; });
      singles = singles.concat(leftoverSingles(byStrength, usedS, cfg));
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

    var used = {};
    tickets.forEach(function (t) { t.legs.forEach(function (l) { used[l.name] = true; }); });
    builders.forEach(function (t) { used[t.legs[0].name] = true; });
    var extras = leftoverSingles(byStrength, used, cfg);

    return {
      tickets: tickets.concat(builders, extras),
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
              'First Time', 'Gets Across', 'Runs the Channel', 'Shoulder of the Last Man']
  };
  var BADGE = { moon: '💥', builder: '⚓️' };

  function a2d(o) { return o > 0 ? 1 + o / 100 : 1 + 100 / Math.abs(o); }

  /* Round-robin max profit. Ported from soccer_payload.rr_maxprofit (which is itself
     index.html's rrmax): every 2-leg and 3-leg combination, minus the total risk. */
  function rrMaxProfit(legs, risk) {
    var dec = legs.filter(function (l) { return l.odds; }).map(function (l) { return a2d(l.odds); });
    var L = dec.length, s = -risk, a, b, c, d;
    for (a = 0; a < L; a++) for (b = a + 1; b < L; b++) s += dec[a] * dec[b];
    for (a = 0; a < L; a++) for (b = a + 1; b < L; b++) for (c = b + 1; c < L; c++) s += dec[a] * dec[b] * dec[c];
    if (L >= 4) for (a = 0; a < L; a++) for (b = a + 1; b < L; b++) for (c = b + 1; c < L; c++)
      for (d = c + 1; d < L; d++) s += dec[a] * dec[b] * dec[c] * dec[d];
    return Math.floor(s * 10 + 0.5) / 10;
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
   *   CONFLOCK   a slip is frozen once every leg is confirmed, OR its earliest leg has kicked
   *              off. A frozen slip is emitted verbatim and its players are spent -- a placed
   *              bet is a fact and nothing may re-draft it. (index.html, 2026-08-16.)
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
    var allConf = legs.every(function (l) {
      var p = D.players[l.name];
      return p && p.status === 'confirmed';
    });
    if (allConf) return true;
    var lo = Infinity;
    legs.forEach(function (l) { var k = koOf(l.game); if (k != null && k < lo) lo = k; });
    if (isFinite(lo) && nowUTCmin >= lo) return true;
    /* belt and braces: the feed says a leg's match is running or done, whatever the clock says */
    var gs = (D.meta && D.meta.gs) || {}, fin = (D.meta && D.meta.finals) || [];
    return legs.some(function (l) {
      return gs[String(l.game)] === 'live' || fin.indexOf(l.game) >= 0;
    });
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
    var spentAsPartner = {}, takenAnchors = {}, anchorMatchCounts = {};
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
        claimAnchor(legs[0]);
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
    /* available as a PARTNER: placeable, not spent on a frozen slip, and not an anchor */
    function freeForPartner(n) {
      return placeable(n) && !spentAsPartner[n] && !takenAnchors[n];
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
    orderedAnchors.forEach(function (an) {
      var g = groups[an];
      var already = !!takenAnchors[an];          // he already anchors a frozen slip
      if (!alive[an] || !placeable(an) || spentAsPartner[an]) {
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
      var cands = withStrength(buildPool(field, cfg, { xi: xi, xiMatches: xiM, exclude: usedPartners }))
        .filter(function (p) { return p.name !== an; });

      var fixed = [], ok = true, localUsed = {};
      for (var i = 0; i < g.moons.length && ok; i++) {
        var t = g.moons[i];
        var legs = [rowOf(an)], seen = {}; seen[String(g.anchor.game)] = true;
        /* PIN the legs that are still good, in their original order */
        t.players.slice(1).forEach(function (l) {
          if (legs.length >= 3) return;
          if (!alive[l.name] || !freeForPartner(l.name)) return;
          if (seen[String(l.game)] || usedPartners[l.name] || localUsed[l.name]) return;
          if (!spanOk(legs.concat([rowOf(l.name)]), cfg)) return;
          legs.push(rowOf(l.name)); seen[String(l.game)] = true; localUsed[l.name] = true;
        });
        /* REFILL whatever the pins left short */
        for (var c = 0; c < cands.length && legs.length < 3; c++) {
          var cd = cands[c];
          if (seen[cd.match] || usedPartners[cd.name] || localUsed[cd.name]) continue;
          if (!spanOk(legs.concat([cd]), cfg)) continue;
          legs.push(cd); seen[cd.match] = true; localUsed[cd.name] = true;
        }
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
        repaired.push({ kind: 'builder', legs: [rowOf(an)], risk: cfg.SINGLE_STAKE, priorName: b.name });
      });
    });

    /* ---- FRESH DRAFT for whatever anchor budget is still unspent ----------------------- */
    var budget = Math.max(0, cfg.ANCH - Object.keys(takenAnchors).length);
    var remaining = field.filter(function (p) { return !usedPartners[p.name] && !takenAnchors[p.name]; });
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
    var sig = function (ts) {
      return ts.map(function (t) {
        return t.kind + ':' + (t.players || []).map(function (l) { return l.name; }).join('+');
      }).sort().join('|');
    };
    return {
      tickets: out,
      changed: sig(out) !== sig(prior),
      locked: frozen.length,
      repaired: repairedT.length,
      minted: mintedT.length,
      released: open.length,
      demoted: demoted,
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
