/* NFLLIVE-2026-09-09 -- the football board's own live loop.
 *
 * WHY THIS EXISTS. nfl_fork.py's 'liveloop' seam killed index.html's liveUpdate() on 2026-09-03
 * and left a stub reading "/* NFL: the MLB live loop is not wired here yet. *\/". That was the
 * right call -- liveUpdate() fetches MLB StatsAPI and then RE-DRAFTS with baseball constants --
 * but it was only ever half the job, and the half that was missing is the one the owner met on
 * 2026-09-09: a room that cannot settle itself.
 *
 * D.meta.finals on that board had NO PRODUCER. Nothing in the page could ever write it. So the
 * only thing that ever did was a foreign localStorage snapshot leaking across the shared origin
 * (SNAPSHOTKEY-2026-09-09), which settled all four anchors two hours before kickoff. Fixing the
 * leak stopped the board being WRONG. It did not make it work. This file makes it work.
 *
 * WHAT THIS DOES, AND DELIBERATELY DOES NOT DO. Same contract as soccer_live.js, deliberately,
 * because three rooms running three different shapes of live loop is how they drift apart.
 *   DOES     read ESPN, and write only what the render layer already understands:
 *              D.meta.finals   (game numbers that are OVER -- only a real feed writes this)
 *              D.meta.gs       ('pre' | 'live' | 'final' | 'ppd', which isLive()/isFinal() read)
 *              p.hr / p.out / p.void / p.status
 *            then calls refreshAll().
 *   DOES NOT grade. index.html already grades tonight live off D.tickets (gradeTicket /
 *            liveCats / liveHist). A second grader here is the assemble_tickets.py mistake.
 *   DOES NOT re-draft. The NFL draft is nfl_draft_cli.js configuring soccer_draft.js, server
 *            side. __assembleClient is baseball and is not reachable from this board.
 *   DOES NOT infer finality from a clock. likelyEnded() may SUPPRESS a wrong "in progress"
 *            claim; it may never ASSERT a result. Only STATUS_FINAL writes finals.
 *   DOES NOT adopt. There is no nfl/D_<date>.json published yet, so there is nothing to adopt
 *            from. When the build starts writing one, port soccerAdopt() -- do not invent a
 *            second adoption rule.
 *
 * ADDRESSING -- BY TEAM CODE PAIR, NOT BY EVENT ID, AND THAT IS NOT A SHORTCUT.
 * soccer_live.js addresses by ESPN event id because ESPN truncates soccer club names ("Hapoel
 * Be'er") and soccer has no stable short codes. The NFL does: 32 teams, fixed 2-3 letter
 * abbreviations, and the board already carries the pair as p.gmatch ("NE@SEA"). This is exactly
 * how index.html's own confirmResults() addresses MLB games (g2i[code(away)+'@'+code(home)]),
 * alias map and all. Same rule set, third sport. If nfl_payload.py ever bakes event ids in,
 * switch to them -- an id is still exact and a code is still a join.
 */
(function (root) {
  'use strict';

  var ESPN = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/';
  var POLL_MS = 3 * 60 * 1000;

  /* ---- team codes -----------------------------------------------------------------
   * ESPN and the odds feed disagree on a handful. Mirrors the ALIAS map index.html carries
   * for MLB (CHW->CWS, AZ->ARI, ...). Both sides are folded, so it does not matter which
   * spelling arrives from where. */
  var TEAMALIAS = {
    WAS: 'WSH', WFT: 'WSH',
    LA: 'LAR', STL: 'LAR', RAM: 'LAR',
    SD: 'LAC', SDG: 'LAC',
    OAK: 'LV', LVR: 'LV', RAI: 'LV',
    JAC: 'JAX',
    ARZ: 'ARI', CRD: 'ARI',
    TAM: 'TB', TBB: 'TB',
    KAN: 'KC', KCC: 'KC',
    NOR: 'NO', NWE: 'NE', NEP: 'NE',
    GNB: 'GB', SFO: 'SF',
    HST: 'HOU', BLT: 'BAL', CLV: 'CLE'
  };
  function tcode(a) {
    a = String(a == null ? '' : a).toUpperCase().trim();
    return TEAMALIAS[a] || a;
  }
  function pairOf(away, home) { return tcode(away) + '@' + tcode(home); }

  /* ---- names ----------------------------------------------------------------------
   * PORTED VERBATIM from soccer_live.js. Every comment there was paid for by a real bad
   * settle, and every one of those failures has an NFL twin on tonight's 26-name slate:
   *   PUNCT-2026-08-28   two normalisations, spaced and deleted -- "A.J. Brown" (board) vs
   *                      "AJ Brown", and "AJ Barner" (board) vs "A.J. Barner".
   *   JRJOIN-2026-09-08  a generational suffix is not a surname -- this slate carries
   *                      "Emmanuel Henderson Jr." WITH the period, "Montorie Foster Jr"
   *                      WITHOUT it, and "Efton Chism III". Without dropSuf the anchor is
   *                      'jr' against 'henderson' and the join silently refuses.
   *   UNMATCHED-2026-08-28  a refused join is not an absence. See the note on `out` below --
   *                      on this board it cannot become one, by construction.
   * Do not "simplify" these. The XLIT table is dead weight for the NFL and stays anyway, so
   * that the three rooms keep ONE name rule rather than three that look alike.
   */
  var XLIT = { 'ø': 'o', 'Ø': 'o', 'æ': 'ae', 'Æ': 'ae', 'å': 'a', 'Å': 'a', 'ß': 'ss',
               'ł': 'l', 'Ł': 'l', 'đ': 'd', 'Đ': 'd', 'ð': 'd', 'Ð': 'd', 'þ': 'th', 'Þ': 'th',
               'œ': 'oe', 'Œ': 'oe', 'ı': 'i', 'İ': 'i', 'ħ': 'h', 'ŧ': 't' };
  function norm(s) {
    s = String(s == null ? '' : s);
    s = s.replace(/[øØæÆåÅßłŁđĐðÐþÞœŒıİħŧ]/g, function (c) { return XLIT[c] || c; });
    if (s.normalize) s = s.normalize('NFKD').replace(/[̀-ͯ]/g, '');
    s = s.toLowerCase().replace(/[.'’ʼ\-]/g, ' ');
    return s.replace(/\s+/g, ' ').trim();
  }
  function normDel(s) {
    s = String(s == null ? '' : s);
    s = s.replace(/[øØæÆåÅßłŁđĐðÐþÞœŒıİħŧ]/g, function (c) { return XLIT[c] || c; });
    if (s.normalize) s = s.normalize('NFKD').replace(/[̀-ͯ]/g, '');
    s = s.toLowerCase().replace(/[.'’ʼ\-]/g, '');
    return s.replace(/\s+/g, ' ').trim();
  }
  var NAMESUF = { jr: 1, jnr: 1, junior: 1, sr: 1, snr: 1, senior: 1, ii: 1, iii: 1, iv: 1, v: 1 };
  function dropSuf(list) {
    var kept = list.filter(function (w) { return !NAMESUF[w]; });
    return kept.length ? kept : list;
  }
  function toks(s) {
    return dropSuf(norm(s).split(' ').filter(function (w) { return w.length > 2; }));
  }
  function toksDel(s) {
    return dropSuf(normDel(s).split(' ').filter(function (w) { return w.length > 2; }));
  }
  function formsOf(s) { return [toks(s), toksDel(s)]; }

  function matchOne(feedName, candidates) {
    var fNorms = [norm(feedName), normDel(feedName)];
    var fForms = formsOf(feedName);

    var exact = candidates.filter(function (c) {
      return fNorms.indexOf(norm(c)) >= 0 || fNorms.indexOf(normDel(c)) >= 0;
    });
    if (exact.length === 1) return exact[0];
    if (exact.length > 1) return null;              // ambiguous -> never guess

    var hits = candidates.filter(function (c) {
      var cForms = formsOf(c);
      for (var i = 0; i < fForms.length; i++) {
        var ft = fForms[i];
        if (!ft.length) continue;
        var fset = {};
        ft.forEach(function (t) { fset[t] = 1; });
        for (var j = 0; j < cForms.length; j++) {
          var ct = cForms[j];
          if (!ct.length) continue;
          if (!fset[ct[ct.length - 1]]) continue;   // SURNAME ANCHOR
          var cset = {};
          ct.forEach(function (t) { cset[t] = 1; });
          var cInF = ct.every(function (t) { return fset[t]; });
          var fInC = ft.every(function (t) { return cset[t]; });
          if (cInF || fInC) return true;
        }
      }
      return false;
    });
    return hits.length === 1 ? hits[0] : null;
  }

  /* ---- touchdowns ------------------------------------------------------------------
   * 🚨 THE SCORER IS NOT THE PASSER. ESPN's scoringPlays type for a receiving touchdown is
   * "Passing Touchdown", and its text is "Ja'Marr Chase 13 Yd pass from Joe Burrow" -- the
   * scorer is named FIRST and the type names the play, not the man. Parsing that string is a
   * settle bug waiting to happen (two names in one sentence, and the wrong one is the QB, who
   * on this very slate is a priced anytime-TD leg at +420 and +1000).
   *
   * So the box score is the source, not the play text. Every stat group carries its own TD
   * column, addressed through `keys` by index rather than by position:
   *     rushing        rushingTouchdowns          <- counts
   *     receiving      receivingTouchdowns        <- counts
   *     defensive      defensiveTouchdowns        <- counts
   *     interceptions  interceptionTouchdowns     <- counts
   *     kickReturns    kickReturnTouchdowns       <- counts
   *     puntReturns    puntReturnTouchdowns       <- counts
   *     passing        passingTouchdowns          <- THROWN, NEVER SCORED. EXCLUDED.
   * "Anytime touchdown" is any touchdown the player SCORES, which is every column above except
   * the passing one. Drake Maye throwing three does not settle Drake Maye's +420; Drake Maye
   * running one in does.
   *
   * Enumerated against a completed game (ARI @ CIN, 401772954) rather than assumed. If ESPN
   * adds a group with a TD column, the /[Tt]ouchdowns$/ test picks it up automatically and the
   * PASSING exclusion is the only thing hard-coded -- which is the right way round.
   */
  var TD_EXCLUDE_GROUP = { passing: 1 };
  function tdsOf(statGroup) {
    var out = [];
    if (!statGroup || TD_EXCLUDE_GROUP[statGroup.name]) return out;
    var keys = statGroup.keys || [];
    var cols = [];
    keys.forEach(function (k, i) { if (/[Tt]ouchdowns$/.test(k)) cols.push(i); });
    if (!cols.length) return out;
    (statGroup.athletes || []).forEach(function (a) {
      var n = 0;
      cols.forEach(function (i) {
        var v = parseInt((a.stats || [])[i], 10);
        if (!isNaN(v) && v > 0) n += v;
      });
      if (n > 0 && a.athlete && a.athlete.displayName) {
        out.push({ name: a.athlete.displayName, id: a.athlete.id, tds: n });
      }
    });
    return out;
  }

  /* ---- inactives -------------------------------------------------------------------
   * 🚨 ABSENCE FROM AN NFL BOX SCORE IS NOT ABSENCE FROM THE GAME, and this is where the MLB
   * loop's rule must NOT be copied. index.html's confirmResults() marks a bat `out` when it is
   * missing from a started game's box, which is sound in baseball: a batting order is nine
   * names and every one of them appears. An NFL box lists only players who RECORDED something.
   * A WR who played 60 snaps and drew no targets is simply not in it. Tonight's board carries
   * ten names at +750 or longer -- exactly the profile of a man who dresses, plays, and never
   * touches the ball. Copying MLB's rule would refund every one of them as a scratch.
   *
   * So `out` on this board comes only from the injury feed saying so, and only for statuses
   * that MEAN it. Questionable and Doubtful are not out; they are the reason the board tells
   * you to wait for the tick.
   *
   * And it is one-way: this file sets `out`, it never clears it, and it never sets it on a man
   * who has already scored. UNMATCHED-2026-08-28 in its NFL form -- here a refused name join
   * simply leaves the player alone rather than asserting anything, so the "refused join read as
   * an absence" failure cannot occur by construction. That is why there is no surnameHits()
   * guard in this file: nothing here infers absence from silence.
   */
  var OUT_STATUS = /^(out|injured reserve|suspension|suspended|inactive|physically unable|non football)/i;

  function makeLive(opt) {
    var D = opt.D;
    var fetchJSON = opt.fetchJSON;
    var stamp = opt.stamp || function () {};
    var render = opt.render || function () {};
    var unmatched = opt.unmatched || [];

    /* candidates in ONE game for ONE team -- the team fold is what makes the name join safe.
     * Two men called Williams on one slate (Kyle Williams, NE) cannot cross-settle, because a
     * Seattle box score is never offered Patriots candidates. */
    function candidatesFor(gi, code) {
      var out = [];
      Object.keys(D.players).forEach(function (n) {
        var p = D.players[n];
        if (p.game !== gi) return;
        if (code && tcode(p.code) !== tcode(code)) return;
        out.push(n);
      });
      return out;
    }

    function applyGame(gi, ev, sum) {
      D.meta.gs = D.meta.gs || {};
      D.meta.finals = (D.meta.finals || []).map(Number);

      var st = (ev && ev.competitions && ev.competitions[0] && ev.competitions[0].status) || null;
      var tn = (st && st.type && st.type.name) || '';
      var state = (st && st.type && st.type.state) || '';
      var ppd = /POSTPONED|CANCELED|CANCELLED/i.test(tn);
      var fin = /STATUS_FINAL/i.test(tn) || (state === 'post' && !ppd);
      var live = state === 'in';

      D.meta.gs[gi] = ppd ? 'ppd' : (fin ? 'final' : (live ? 'live' : 'pre'));

      if (ppd) {
        /* a postponed game voids its legs, the same refund a scratch takes -- never a loss */
        Object.keys(D.players).forEach(function (n) {
          if (D.players[n].game === gi) D.players[n].void = true;
        });
        return;
      }

      if (fin && D.meta.finals.indexOf(Number(gi)) < 0) D.meta.finals.push(Number(gi));

      if (live) {
        D.meta.live = (D.meta.live || []).map(Number);
        if (D.meta.live.indexOf(Number(gi)) < 0) D.meta.live.push(Number(gi));
      }

      /* ---- touchdowns, from the box score of a game that has actually started ---- */
      var bp = (sum && sum.boxscore && sum.boxscore.players) || [];
      if ((live || fin) && bp.length) {
        bp.forEach(function (tb) {
          var code = tb.team && (tb.team.abbreviation || tb.team.shortDisplayName);
          var cands = candidatesFor(gi, code);
          if (!cands.length) return;
          (tb.statistics || []).forEach(function (sg) {
            tdsOf(sg).forEach(function (sc) {
              var who = matchOne(sc.name, cands);
              if (who) {
                D.players[who].hr = true;
                D.players[who].out = false;   // he scored; he was manifestly not inactive
                D.players[who].void = false;
              } else if (unmatched.indexOf(sc.name) < 0) {
                unmatched.push(sc.name);      // surfaced, never guessed at
              }
            });
          });
        });
      }

      /* ---- inactives, pre-kickoff only ---- */
      if (!live && !fin) {
        ((sum && sum.injuries) || []).forEach(function (tb) {
          var code = tb.team && (tb.team.abbreviation || tb.team.shortDisplayName);
          var cands = candidatesFor(gi, code);
          if (!cands.length) return;
          (tb.injuries || []).forEach(function (inj) {
            var who = inj.athlete && inj.athlete.displayName;
            if (!who) return;
            var status = String(inj.status || (inj.type && inj.type.description) || '');
            if (!OUT_STATUS.test(status)) return;
            var m = matchOne(who, cands);
            if (m && !D.players[m].hr) D.players[m].out = true;
          });
        });
      }

      /* ---- the tick ----------------------------------------------------------------
       * 🚨 A HONEST ✓, OR NONE. The board's own banner promises "A ticket is only final once
       * every player on it is confirmed in a posted lineup." The NFL analogue is the inactives
       * list, 90 minutes out -- but ESPN's injuries feed carries season-long statuses and looks
       * IDENTICAL before and after that list drops, so this file cannot tell "not announced
       * yet" from "announced and active". Inventing a ✓ out of that would be a promise the
       * data does not support, on the one chip the owner tells readers to wait for.
       * So confirmation here means the game is underway: at that point a man not marked out is
       * playing, which is the thing the tick claims. Everything before kickoff stays
       * `projected`. Wiring a real inactives source is the follow-up; faking it is not.
       */
      if (live || fin) {
        Object.keys(D.players).forEach(function (n) {
          var p = D.players[n];
          if (p.game === gi && !p.out && !p.void) p.status = 'confirmed';
        });
      }
    }

    function run() {
      if (!D || !D.meta || !D.players) return Promise.resolve('no board');
      var date = D.meta.date;
      if (!date) { stamp('no slate date'); return Promise.resolve('unwired'); }

      /* the board's games, by code pair, so an ESPN event resolves to a game NUMBER */
      var g2i = {};
      Object.keys(D.players).forEach(function (n) {
        var p = D.players[n];
        if (!p.gmatch || p.game == null) return;
        var pr = String(p.gmatch).split('@');
        if (pr.length === 2) g2i[pairOf(pr[0], pr[1])] = p.game;
      });
      if (!Object.keys(g2i).length) { stamp('no games on this board'); return Promise.resolve('unwired'); }

      var ymd = String(date).replace(/-/g, '');
      return fetchJSON(ESPN + 'scoreboard?dates=' + ymd).then(function (sb) {
        var evs = (sb && sb.events) || [];
        var jobs = [];
        evs.forEach(function (e) {
          var c = e.competitions && e.competitions[0];
          if (!c) return;
          var home = null, away = null;
          (c.competitors || []).forEach(function (t) {
            var ab = t.team && t.team.abbreviation;
            if (t.homeAway === 'home') home = ab; else away = ab;
          });
          if (!home || !away) return;
          var gi = g2i[pairOf(away, home)];
          if (gi == null) return;                       // an ESPN game this board never drafted
          var state = c.status && c.status.type && c.status.type.state;
          if (state === 'pre') {
            /* still need the injury feed, but not the (empty) box score */
            jobs.push(fetchJSON(ESPN + 'summary?event=' + e.id)
              .then(function (s) { applyGame(gi, e, s); })
              .catch(function () { applyGame(gi, e, null); }));
          } else {
            jobs.push(fetchJSON(ESPN + 'summary?event=' + e.id)
              .then(function (s) { applyGame(gi, e, s); })
              .catch(function () { applyGame(gi, e, null); }));
          }
        });
        return Promise.all(jobs);
      }).then(function () {
        try { render(); } catch (e) {}
        stamp('live ✓ ' + new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
        return 'ok';
      }).catch(function () {
        /* ESPN unreachable this pass -- leave the board exactly as it is, say so, try again */
        stamp('feed unreachable — board unchanged');
        return 'offline';
      });
    }

    return { run: run, applyGame: applyGame, candidatesFor: candidatesFor };
  }

  var api = { makeLive: makeLive, matchOne: matchOne, tdsOf: tdsOf, norm: norm, normDel: normDel,
              tcode: tcode, pairOf: pairOf, POLL_MS: POLL_MS };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.NflLive = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);

/* FOLLOW-UPS, stated rather than left implicit.
 *  1. ADOPTION. There is no nfl/D_<date>.json, so a tab left open cannot pick up a newer server
 *     board (ADOPT-2026-08-16). Publish one from the build, then port soccerAdopt() -- including
 *     ADOPTSIG-2026-09-04's board-signature comparison, not the build stamp.
 *  2. THE REAL TICK. An inactives source (90 minutes out) would let `status` mean what the
 *     banner says it means before kickoff rather than at it.
 *  3. LIVE RE-DRAFT on inactives is Stage 2 here exactly as it is in soccer, and for the same
 *     reason: it needs the NFL draft rules inside the client, under CONFLOCK and MINTGUARD.
 */
