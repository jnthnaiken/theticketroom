/* SOCCERLIVE-2026-08-26 -- the soccer board's own live loop.
 *
 * WHY THIS EXISTS. soccer_fork.py's 'liveloop' seam KILLED index.html's liveUpdate() outright,
 * because that function fetches MLB StatsAPI + Open-Meteo and then RE-DRAFTS with baseball
 * constants (GAME_CAP / CHALK_N / WIN=120 / precipOf). Pointed at a soccer board it would
 * re-draft the tickets against rules that do not apply. So the board never refreshed, never
 * settled, and sat with a ticking clock on a slate that finished a day earlier.
 *
 * WHAT THIS DOES, AND DELIBERATELY DOES NOT DO.
 *   DOES     read ESPN, and write the four things the render layer already understands:
 *              D.meta.finals   (game numbers that are OVER -- see the finality rule below)
 *              D.meta.results  (score, for display)
 *              D.meta.gs       ('live' per game, which isLive() reads)
 *              p.hr / p.goalmins / p.status / p.out / p.unres
 *            then calls refreshAll().
 *   DOES NOT grade. index.html ALREADY grades tonight live off D.tickets (gradeTicket /
 *            liveCats / liveHist) -- that is why the 08-24 board showed 3-3 once its fixtures
 *            settled. Writing a second grader here would be the assemble_tickets.py mistake:
 *            two implementations of one rule set, drifting apart, disagreeing on the same
 *            screen. soccer_grade.py mirrors gradeTicket for the SERVER ledger; this file
 *            feeds both and implements neither.
 *   DOES NOT re-draft. The soccer draft lives in soccer_mock.py, in Python, and has never been
 *            ported to __assembleClient. Until it is, a live re-draft would use MLB rules.
 *            Stage 2. See the note at the bottom.
 *   DOES NOT infer finality from a clock. isFinal() reads D.meta.finals and ONLY a real results
 *            feed writes it -- deliberate on the baseball side and kept here. likelyEnded()
 *            may SUPPRESS a wrong "in progress" claim; it may never ASSERT a result.
 *
 * ADDRESSING. Matches are addressed by ESPN event id, baked into D.meta.espn by
 * soccer_payload.py as {gnum:{lg,ev}}. It is NOT resolved at runtime by team name, because
 * ESPN truncates display names ("Hapoel Be'er" for Hapoel Be'er Sheva) and name-matching
 * fixtures is the same class of bug as SPFIRST-2026-08-22. An id is exact.
 */
(function (root) {
  'use strict';

  var ESPN = 'https://site.api.espn.com/apis/site/v2/sports/soccer/';
  var POLL_MS = 3 * 60 * 1000;

  /* ---- names ----------------------------------------------------------------------
   * SURNAME-ANCHORED, and that is not a stylistic choice. PIPELINE.md open item 1: the
   * loose token-subset rule matched Real Betis's "Pablo Garcia" to EPL's "Pablo", and
   * Celtic's "Joao Pedro Jota" to Chelsea's "Joao Pedro" -- two different people each time.
   * On a SCORER feed that bug does not merely mis-score a player, it settles the wrong man's
   * ticket. Pablo Garcia scored the only goal of Valencia v Betis on 2026-08-25, so this is
   * the live path, not a hypothetical.
   *
   * Rule: the last significant token of the BOARD name (the surname slot) must appear in the
   * feed name's tokens, AND one token set must contain the other, AND the winner must be
   * UNIQUE. Ambiguity resolves to no-match, never to a guess.
   */
  /* NFKD + combining-mark stripping handles é/á/ñ, and NOTHING ELSE. A whole class of European
   * letters are single code points with no decomposition: ø æ å(sometimes) ß ł đ ı ð þ œ.
   * Caught by the test on 2026-08-26: "Fredrik André Bjørkan" (ESPN) would not join
   * "Fredrik Bjorkan" (board) because the surname anchor compared bjørkan to bjorkan. He
   * scored in the Bodo/Glimt match on 08-25, so this is a scorer the loop would have dropped
   * on its first live night. A soccer feed is Nordic/Polish/Turkish every week; baseball never
   * needed this, which is why build15.norm() has no equivalent. */
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
  function toks(s) {
    return norm(s).split(' ').filter(function (w) { return w.length > 2; });
  }
  function matchOne(feedName, candidates) {
    var fn = norm(feedName);
    var ft = toks(feedName), fset = {};
    ft.forEach(function (t) { fset[t] = 1; });

    var exact = candidates.filter(function (c) { return norm(c) === fn; });
    if (exact.length === 1) return exact[0];
    if (exact.length > 1) return null;              // ambiguous -> never guess

    var hits = candidates.filter(function (c) {
      var ct = toks(c);
      if (!ct.length || !ft.length) return false;
      if (!fset[ct[ct.length - 1]]) return false;   // SURNAME ANCHOR
      var cset = {};
      ct.forEach(function (t) { cset[t] = 1; });
      var cInF = ct.every(function (t) { return fset[t]; });
      var fInC = ft.every(function (t) { return cset[t]; });
      return cInF || fInC;
    });
    return hits.length === 1 ? hits[0] : null;
  }

  /* ---- ESPN shapes ----------------------------------------------------------------
   * Goal types on the feed are "Goal", "Goal - Volley", "Goal - Header", "Penalty - Scored"
   * ... and "Own Goal". An own goal is credited to the OTHER side and settles NOBODY's
   * anytime-goalscorer bet. A naive /goal/i test pays it out. 2026-08-25 had exactly one:
   * Deveron Fonville, 73', credited to Bodo/Glimt.
   */
  /* The vocabulary below is not guessed. Enumerated 2026-08-26 over 26 completed matches across
   * esp.1 / eng.1 / ita.1 / ger.1 / fra.1 / uefa.champions_qual:
   *     Goal x47   Goal - Header x8   Goal - Volley x3   Goal - Free-kick x2
   *     Penalty - Scored x6          <- IS a goal. Contains no "goal", so a /goal/i test drops it.
   *     Own Goal x1                  <- is NOT this player's goal
   *     Penalty - Saved x1   Penalty - Hit Woodwork x1   <- obviously not
   * "Penalty - Scored" turned up 6 times in 26 matches, so dropping it is not an edge case,
   * it is roughly one match in four settling a winner as a loser.
   *
   * SHOOTOUT. Every keyEvent carries a `shootout` boolean. A shootout kick never settles an
   * anytime-goalscorer bet -- that is the book's rule, not a preference. In the one shootout
   * checked (Kairat Almaty v Omonia, 2026-07-29) ESPN did not even put the kicks in keyEvents,
   * but the flag is honoured rather than relying on that staying true. */
  function isScoringGoal(typeText, ev) {
    var t = String(typeText || '').trim();
    if (ev && ev.shootout === true) return false;
    if (/^own\s*goal/i.test(t)) return false;
    if (/^goal\b/i.test(t)) return true;
    if (/^penalty\s*-\s*scored\b/i.test(t)) return true;
    return false;
  }
  function goalsOf(summary) {
    var out = [];
    ((summary && summary.keyEvents) || []).forEach(function (k) {
      if (!isScoringGoal(k.type && k.type.text, k)) return;
      var a = (k.participants || [])[0] || {};
      var nm = a.athlete && (a.athlete.displayName || a.athlete.fullName);
      if (!nm) return;
      var mn = String((k.clock && k.clock.displayValue) || '').replace(/'/g, '').trim();
      out.push({ name: nm, min: mn });
    });
    return out;
  }
  /* Squad sheet. `out` REFUNDS a leg at grading, so it is the strong claim and is asserted
   * only when BOTH teams published a non-empty roster -- absent from a sheet we never saw is
   * not the same fact as absent from the sheet. Same standard soccer_payload.py applies. */
  function squadOf(summary) {
    var rs = (summary && summary.rosters) || [];
    var complete = rs.length >= 2 && rs.every(function (r) { return ((r.roster) || []).length > 0; });
    var xi = {}, bench = {}, all = {};
    rs.forEach(function (r) {
      ((r.roster) || []).forEach(function (pl) {
        var nm = (pl.athlete || {}).displayName;
        if (!nm) return;
        all[nm] = 1;
        if (pl.starter) xi[nm] = 1; else bench[nm] = 1;
      });
    });
    return { complete: complete, xi: xi, bench: bench, all: all };
  }

  /* ---- the loop ------------------------------------------------------------------- */
  function makeLive(env) {
    var D = env.D, fetchJSON = env.fetchJSON;
    var stamp = env.stamp || function () {};
    var render = env.render || function () {};

    function playersInGame(g) {
      var names = [];
      Object.keys(D.players).forEach(function (n) {
        if (D.players[n].game === g) names.push(n);
      });
      return names;
    }

    function applyMatch(g, sbEv, summary) {
      var st = ((sbEv && sbEv.status) || {}).type || {};
      var done = !!st.completed;
      var state = st.state || (done ? 'post' : 'pre');
      var names = playersInGame(g);
      if (!names.length) return;

      /* score, for display */
      var comp = ((sbEv && sbEv.competitions) || [])[0] || {};
      var cs = comp.competitors || [];
      if (cs.length === 2) {
        var h = cs.filter(function (c) { return c.homeAway === 'home'; })[0] || cs[0];
        var a = cs.filter(function (c) { return c.homeAway === 'away'; })[0] || cs[1];
        D.meta.results = D.meta.results || {};
        D.meta.results[g] = [Number(h.score), Number(a.score)];
      }

      /* live flag -- 'the ball is rolling', which is not a claim of finality */
      D.meta.gs = D.meta.gs || {};
      if (state === 'in') D.meta.gs[String(g)] = 'live';
      else delete D.meta.gs[String(g)];

      /* FINALITY: only the feed may assert it */
      if (done) {
        D.meta.finals = D.meta.finals || [];
        if (D.meta.finals.indexOf(g) < 0) D.meta.finals.push(g);
      }

      if (!summary) return;   // status applied; no detail this pass

      /* --- goals --------------------------------------------------------------------
       * Authoritative for THIS match on a successful fetch: a player who is not in the
       * feed's goal list did not score. But a FAILED fetch must never clear a goal, which
       * is why this only runs when `summary` came back. */
      var gl = goalsOf(summary);
      var scored = {};
      gl.forEach(function (ev) {
        var who = matchOne(ev.name, names);
        if (!who) { (env.unmatched || []).push({ game: g, feed: ev.name }); return; }
        (scored[who] = scored[who] || []).push(ev.min);
      });
      names.forEach(function (n) {
        var p = D.players[n];
        if (scored[n]) { p.hr = true; p.goalmins = scored[n]; }
        else if (done) { p.hr = false; p.goalmins = []; }
      });

      /* --- squad sheet --------------------------------------------------------------- */
      var sq = squadOf(summary);
      if (sq.complete) {
        names.forEach(function (n) {
          var p = D.players[n];
          var who = matchOne(n, Object.keys(sq.all));
          if (who && sq.xi[who]) { p.status = 'confirmed'; p.out = false; }
          else if (who && sq.bench[who]) { p.status = 'benched'; p.out = false; }
          else if (!who && !p.hr) { p.out = true; }
          /* a man who SCORED is on the sheet by definition, whatever the join said */
          if (p.hr) { p.out = false; p.status = 'confirmed'; }
        });
      }

      /* --- unres: we have data now, so stop saying we do not ------------------------- */
      if (done && summary) {
        names.forEach(function (n) {
          var p = D.players[n];
          if (p.unres && (sq.complete || gl.length)) p.unres = '';
        });
      }
    }

    function run() {
      if (!D || !D.meta || !D.players) return Promise.resolve('no board');
      var date = D.meta.date;
      var EV = D.meta.espn || {};
      var keys = Object.keys(EV);
      if (!date || !keys.length) { stamp('no results feed wired'); return Promise.resolve('unwired'); }

      var ymd = String(date).replace(/-/g, '');
      var byLg = {};
      keys.forEach(function (g) {
        var e = EV[g] || {};
        if (!e.lg || !e.ev) return;
        (byLg[e.lg] = byLg[e.lg] || []).push({ g: Number(g), ev: String(e.ev) });
      });

      var lgs = Object.keys(byLg);
      return Promise.all(lgs.map(function (lg) {
        return fetchJSON(ESPN + lg + '/scoreboard?dates=' + ymd)
          .then(function (sb) {
            var idx = {};
            ((sb && sb.events) || []).forEach(function (e) { idx[String(e.id)] = e; });
            return Promise.all(byLg[lg].map(function (m) {
              var sbEv = idx[m.ev] || null;
              return fetchJSON(ESPN + lg + '/summary?event=' + m.ev)
                .then(function (s) { applyMatch(m.g, sbEv, s); })
                .catch(function () { applyMatch(m.g, sbEv, null); });
            }));
          })
          .catch(function () { /* league unreachable this pass -- leave the board alone */ });
      })).then(function () {
        try { render(); } catch (e) {}
        stamp('live ✓ ' + new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
        return 'ok';
      });
    }

    return { run: run, applyMatch: applyMatch };
  }

  var api = { makeLive: makeLive, matchOne: matchOne, goalsOf: goalsOf,
              squadOf: squadOf, isScoringGoal: isScoringGoal, norm: norm, POLL_MS: POLL_MS };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.SoccerLive = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);

/* STAGE 2 -- LIVE RE-DRAFT ON TEAM NEWS, deliberately not done here.
 * Football XIs publish about an hour before kickoff, so a named player who is not in the XI is
 * a dead leg and the board should replace him BEFORE kickoff. That is the same trigger MLB's
 * board answers when a lineup posts. It needs the soccer draft rules inside __assembleClient
 * (the MLB constants there are baseball: GAME_CAP, CHALK_N, WIN=120, rain bands), and it must
 * run under the MLB lock doctrine -- CONFLOCK freezes a slip whose legs are confirmed or whose
 * earliest leg is underway, MINTGUARD forbids MINTING a slip past its own kickoff -- so a
 * re-draft can never move a bet already placed. This file writes p.status/p.out, which is
 * exactly the input that stage needs, and stops there.
 */
