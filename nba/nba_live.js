/* NBALIVE-2026-10-17 -- the basketball board's own live loop. Built from nfl_live.js on purpose (same
 * contract, same name rules, same shape), because rooms that run different shapes of live loop drift apart.
 *
 *   DOES     read ESPN, and write only what the render layer already understands:
 *              D.meta.finals / D.meta.gs / D.meta.live
 *              p.ftd1  -- TRUE on the man who scored his game's FIRST POINTS (free throws count -- FanDuel, FDRULES), FALSE on everyone else in
 *                         that game, and only once a field goal exists (before that nobody has lost).
 *                         Free throws are not a basket (ESPN marks them shooting plays worth 1).
 *              p.hr    -- mirrors ftd1, so the player card says who scored first
 *              p.status 'confirmed' when ESPN's box score lists him as a starter
 *              p.void  -- he did not play (didNotPlay) once his game is underway: the bet is refunded.
 *                         A man who plays but did not start is NOT voided -- the book keeps that bet.
 *            then calls refreshAll().
 *   DOES NOT grade (index.html grades D.tickets live; nba_settle.py grades the ledger), re-draft, or infer
 *            a result from a clock.
 *
 * ADDRESSING by AWAY@HOME tricode pair, as nfl_live.js does. ESPN writes GS / NO / NY / SA / UTAH / WSH;
 * the board writes the NBA tricodes, and both sides are folded through TEAMALIAS.
 */
(function (root) {
  'use strict';

  var ESPN = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/';
  var POLL_MS = 2 * 60 * 1000;
  var TEAMALIAS = { GS: 'GSW', NO: 'NOP', NOR: 'NOP', NY: 'NYK', SA: 'SAS', UTAH: 'UTA', UTH: 'UTA',
                    WSH: 'WAS', PHO: 'PHX', BRK: 'BKN', CHO: 'CHA' };
  function tcode(a) {
    a = String(a == null ? '' : a).toUpperCase().trim();
    return TEAMALIAS[a] || a;
  }
  function pairOf(away, home) { return tcode(away) + '@' + tcode(home); }

  /* ---- names: PORTED VERBATIM from nfl_live.js (which ported them from soccer_live.js) ---- */
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
  /* 🚨 INITIALS-2026-09-09 -- AN INITIAL IS THE DISCRIMINATOR, NOT A PARTICLE.
   * soccer_live.js filters tokens with `w.length > 2`, which is right there: the short tokens in
   * a football name are particles (de, van, dos, bin) and dropping them helps. In the NFL the
   * short tokens are INITIALS, and they are the only thing telling two men apart.
   *
   * MEASURED ON THE LIVE FEED, 2026-09-09 22:5xZ, before kickoff: ESPN's NE injury list carries
   * "Ben Brown = Out". The board carries "A.J. Brown" at +170 on Red Zone Target. Under `> 2`
   * the board name tokenised to ['brown'] -- the initials filtered away -- so the surname anchor
   * fired, ['brown'] was a subset of ['ben','brown'], the join was UNIQUE (one Brown on the
   * roster), and this file marked A.J. Brown OUT. One offensive lineman's ankle would have
   * voided a live anytime-TD leg in every reader's browser.
   *
   * Two changes, and both are needed:
   *   (1) keep 2-character tokens, so 'aj' survives normDel and can discriminate; and
   *   (2) MONONYM GUARD in matchOne -- a candidate that reduces to ONE token may only match on
   *       that token if the name really is one word. "A.J. Brown" is three pieces that happen to
   *       filter down to one; "Raphinha" is one. rawCount() tells them apart.
   * (1) alone does not fix it: norm('A.J. Brown') is still 'a j brown' and still reduces to
   * ['brown'] under any length filter above 1. The guard is the load-bearing half.
   */
  function toks(s) {
    return dropSuf(norm(s).split(' ').filter(function (w) { return w.length > 1; }));
  }
  function toksDel(s) {
    return dropSuf(normDel(s).split(' ').filter(function (w) { return w.length > 1; }));
  }
  function formsOf(s) { return [toks(s), toksDel(s)]; }
  /* how many pieces the name ACTUALLY has, before any filtering -- a true mononym is 1 */
  function rawCount(s) { return norm(s).split(' ').filter(Boolean).length; }

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
          /* MONONYM GUARD -- see INITIALS-2026-09-09 above. A one-token side may carry the
             join only if that side is genuinely a one-word name. */
          if (ct.length < 2 && rawCount(c) > 1) continue;
          if (ft.length < 2 && rawCount(feedName) > 1) continue;
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


  function makeLive(opt) {
    var D = opt.D;
    var fetchJSON = opt.fetchJSON;
    var stamp = opt.stamp || function () {};
    var render = opt.render || function () {};
    var unmatched = opt.unmatched || [];

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

    function isFG(p) {
      var t = String((p.type && p.type.text) || '').toLowerCase();
      return !!p.shootingPlay && t.indexOf('free throw') < 0 && (p.scoreValue == null || p.scoreValue === 0 || p.scoreValue >= 2);
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
        Object.keys(D.players).forEach(function (n) { if (D.players[n].game === gi) D.players[n].void = true; });
        return;
      }
      if (fin && D.meta.finals.indexOf(Number(gi)) < 0) D.meta.finals.push(Number(gi));
      if (live) {
        D.meta.live = (D.meta.live || []).map(Number);
        if (D.meta.live.indexOf(Number(gi)) < 0) D.meta.live.push(Number(gi));
      }
      if (!(live || fin) || !sum) return;

      /* the box score: who is who, who started, who played */
      var ath = {}, teamOf = {}, starters = {}, played = {}, listed = {};
      ((sum.boxscore && sum.boxscore.players) || []).forEach(function (tb) {
        var code = tcode(tb.team && tb.team.abbreviation);
        (tb.statistics || []).forEach(function (sg) {
          (sg.athletes || []).forEach(function (a) {
            var at = a.athlete || {}; if (!at.displayName) return;
            ath[String(at.id)] = at.displayName; teamOf[at.displayName] = code; listed[at.displayName] = 1;
            if (a.starter) starters[at.displayName] = 1;
            if (!a.didNotPlay && (a.stats || []).length) played[at.displayName] = 1;
          });
        });
      });
      Object.keys(D.players).forEach(function (n) {
        var p = D.players[n];
        if (p.game !== gi) return;
        var names = Object.keys(teamOf).filter(function (x) { return teamOf[x] === tcode(p.code); });
        if (!names.length) return;
        var who = matchOne(n, names);
        if (!who) { if (unmatched.indexOf(n) < 0) unmatched.push(n); return; }
        if (starters[who]) { p.status = 'confirmed'; p.out = false; }
        /* FDRULES-2026-10-24: FanDuel refunds a listed player who does not START (bench minutes included) */
        /* VOIDGUARD-2026-10-25 (owner: "whats with all of the voids on the basketball page?"). ESPN's live box score can sit
           half-built mid-game -- every man didNotPlay, nobody flagged starter -- and the old `!played` branch voided
           Holmgren, Isaiah Jackson and Wendell Carter Jr., who had all jumped center (Jackson scored LAC@OKC's first
           basket). A void now needs ESPN's two starting fives listed; until then nobody is voided. */
        if (Object.keys(starters).length >= 10 && !starters[who]) { p.void = true; p.ftd1 = false; p.hr = false; }
        else p.void = false;
      });

      /* the game's first FIELD GOAL */
      var plays = sum.plays || [];
      for (var i = 0; i < plays.length; i++) {
        var pl = plays[i];
        if (!pl.scoringPlay || !((pl.scoreValue || 0) >= 1)) continue;   /* FDRULES: first SCORE, free throws count (FanDuel) */
        var sid = pl.participants && pl.participants[0] && pl.participants[0].athlete && pl.participants[0].athlete.id;
        var sname = ath[String(sid)] || '';
        var fwho = sname ? matchOne(sname, candidatesFor(gi, teamOf[sname])) : null;
        D.meta.fb = D.meta.fb || {}; D.meta.fb[String(gi)] = sname;
        candidatesFor(gi).forEach(function (n) {
          D.players[n].ftd1 = (n === fwho) && !D.players[n].void;   /* a refunded non-starter cannot win (FanDuel) */
          D.players[n].hr = D.players[n].ftd1;
        });
        break;
      }
    }

    function run() {
      if (!D || !D.meta || !D.players) return Promise.resolve('no board');
      var date = D.meta.date;
      if (!date) { stamp('no slate date'); return Promise.resolve('unwired'); }
      var g2i = {};
      Object.keys(D.meta.games || {}).forEach(function (k) {
        var pr = String(D.meta.games[k]).split('@');
        if (pr.length === 2) g2i[pairOf(pr[0], pr[1])] = Number(k);
      });
      if (!Object.keys(g2i).length) { stamp('no games on this board'); return Promise.resolve('unwired'); }
      var ymd = String(date).replace(/-/g, '');
      /* NONESPN-2026-10-25 (owner: "fuck espn dude. only use them for a last resort"). The build bakes nba.com's live
         state (nba_livebake.py) into nba_D.json every pass; pull that first and take every game it covers. ESPN is
         read only for a game nba.com did not cover (D.meta.nbacom.games), or when the board file can't be fetched. */
      var covered = {};
      function pullBoard() {
        return fetchJSON('nba_D.json?t=' + Date.now()).then(function (F) {
          if (!F || !F.meta || F.meta.date !== D.meta.date) return;
          ((F.meta.nbacom && F.meta.nbacom.games) || []).forEach(function (g) { covered[Number(g)] = 1; });
          ['gs', 'fb', 'finals', 'live', 'nbacom', 'dt'].forEach(function (k) { if (F.meta[k] != null) D.meta[k] = F.meta[k]; });
          Object.keys(F.players || {}).forEach(function (n) {
            var p = D.players[n], q = F.players[n];
            if (!p || !q || !covered[Number(q.game)]) return;
            ['status', 'void', 'out', 'ftd1', 'hr'].forEach(function (k) { if (k in q) p[k] = q[k]; });
          });
        }).catch(function () {});
      }
      return pullBoard().then(function () {
        if (Object.keys(g2i).every(function (k) { return covered[g2i[k]]; })) return null;
        return fetchJSON(ESPN + 'scoreboard?dates=' + ymd);
      }).then(function (sb) {
        var jobs = [];
        ((sb && sb.events) || []).forEach(function (e) {
          var c = e.competitions && e.competitions[0];
          if (!c) return;
          var home = null, away = null;
          (c.competitors || []).forEach(function (t) {
            var ab = t.team && t.team.abbreviation;
            if (t.homeAway === 'home') home = ab; else away = ab;
          });
          var gi = g2i[pairOf(away, home)];
          if (gi == null || covered[gi]) return;   /* NONESPN: nba.com has this game */
          var state = c.status && c.status.type && c.status.type.state;
          if (state === 'pre') { applyGame(gi, e, null); return; }
          jobs.push(fetchJSON(ESPN + 'summary?event=' + e.id)
            .then(function (s) { applyGame(gi, e, s); })
            .catch(function () { applyGame(gi, e, null); }));
        });
        return Promise.all(jobs);
      }).then(function () {
        try { reconcileTickets(); } catch (e) {}
        try { render(); } catch (e) {}
        stamp('live ✓ ' + new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
        return 'ok';
      }).catch(function () {
        stamp('feed unreachable — board unchanged');
        return 'offline';
      });
    }

    function reconcileTickets() {
      (D.tickets || []).forEach(function (t) {
        t.confleg = (t.players || []).filter(function (l) {
          var p = D.players[l.name];
          return !!(p && p.status === 'confirmed' && !p.out && !p.void);
        }).length;
      });
    }

    return { run: run, applyGame: applyGame, candidatesFor: candidatesFor, reconcileTickets: reconcileTickets };
  }

  var api = { makeLive: makeLive, matchOne: matchOne, norm: norm, normDel: normDel,
              tcode: tcode, pairOf: pairOf, POLL_MS: POLL_MS };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.NbaLive = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
