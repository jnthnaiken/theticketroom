/* soccer/tot_scrape.js — GOALLINE-2026-10-15. oddschecker Win Market + Total Goals Over/Under +
 * Total Home Goals + Total Away Goals -> tot.psv rows, for the daily goals parlay (soccer_tot.py).
 *
 * WHERE THE MARKETS ARE. All four are sections on the fixture's /winner page, the same page the
 * Anytime Goalscorer scrape (ags_scrape.js) already visits. Win Market ships open; the three totals
 * sections ship COLLAPSED and LAZY (see SCROLLFGS-2026-10-13 in ags_scrape.js): scroll into view,
 * then click the h2, then wait for wrappers. expand() below is that same routine.
 *
 * THE LAYOUT (measured 2026-10-15, Frankfurt v Cologne). Each totals section renders a header row
 * "Under | Over" and two ExpanderBestOddsColumn blocks in that order; each wrapper's innerText is
 * "<line>\n\n<best price>" with an optional percentage or n/a between them. The column HEADER is
 * read, never assumed, so a swapped layout cannot flip every over into an under. textContent welds
 * the line onto the price ("1.55/6" = line 1.5 at 5/6) -- innerText keeps them apart; use it.
 *
 * USAGE (per fixture page, after navigating to .../<slug>/winner):
 *     var tot = eval(localStorage.getItem('TOT'));
 *     await tot('<canonical fixtures.json key>')      // {dry:true} parses without storing
 * Appends "match|market|side|line|odds" to localStorage.TOT_ROWS and returns a summary.
 *   market WIN  side H/D/A  line -
 *   market TG/TH/TA (game / home team / away team goals)  side O/U  line 0.5 ...
 */
(function () {
  'use strict';
  var ODDS = /^(\d+\/\d+|EVS|EVENS?|[+-]\d{3,})$/i;

  function section(title) {
    title = String(title).toLowerCase();
    var secs = [].slice.call(document.querySelectorAll('section'));
    for (var i = 0; i < secs.length; i++) {
      var h = secs[i].querySelector('h2');
      if (h && String(h.textContent).trim().toLowerCase() === title) return secs[i];
    }
    return null;
  }
  function wrappers(sec) { return [].slice.call(sec.querySelectorAll('[class*=MarketExpanderBetWrapper]')); }

  async function expand(title) {
    var sec = section(title);
    if (!sec) return 'none';
    if (wrappers(sec).length) return 'open';
    if (sec.scrollIntoView) sec.scrollIntoView({ block: 'center' });
    await new Promise(function (r) { setTimeout(r, 700); });
    if (wrappers(sec).length) return 'opened';
    sec.querySelector('h2').click();
    for (var w = 0; w < 20000 && !wrappers(sec).length; w += 400)
      await new Promise(function (r) { setTimeout(r, 400); });
    return wrappers(sec).length ? 'opened' : 'timeout';
  }

  /* SHOWMORE: the under column hides its short lines (Under 0.5 for a team, the quarter lines) until
     "Show More" is clicked; it is an in-section text toggle, not a dialog. Clicked until it is gone. */
  async function showMore(sec) {
    for (var k = 0; k < 3; k++) {
      var b = [].slice.call(sec.querySelectorAll('span,button')).filter(function (x) {
        return x.children.length === 0 && /^show more$/i.test(String(x.textContent).trim()); })[0];
      if (!b) return;
      (b.closest('button') || b).click();
      await new Promise(function (r) { setTimeout(r, 1000); });
    }
  }

  function tokens(el) {
    return String(el.innerText || el.textContent || '').split(/\n+/).map(function (s) { return s.trim(); })
      .filter(function (s) { return s && !/%$/.test(s) && !/^n\/a$/i.test(s); });
  }
  function odds(s) {
    s = String(s || '').trim();
    if (!ODDS.test(s)) return null;
    return /^EVEN/i.test(s) || /^EVS$/i.test(s) ? '1/1' : s;
  }

  /* "Under | Over" columns -> rows. Returns {rows, bad, sides}. */
  function ouSection(sec, mkey, mkt) {
    /* The selector must exclude ExpanderBestOddsColumnHeader_*, which also matches *=Column (measured:
       4 hits = 2 headers + 2 columns). Headers give the side; columns hold the wrappers. */
    var cols = [].slice.call(sec.querySelectorAll('[class*=ExpanderBestOddsColumn_]'));
    var head = [].slice.call(sec.querySelectorAll('[class*=ExpanderBestOddsColumnHeader_]'))
      .map(function (h) { return String(h.innerText || h.textContent).trim().toLowerCase(); });
    var rows = [], bad = [];
    if (cols.length !== 2 || head.length !== 2) return { rows: rows, bad: ['layout cols=' + cols.length + ' head=' + head.join('/')] };
    cols.forEach(function (c, ci) {
      var side = head[ci] === 'over' ? 'O' : 'U';
      wrappers(c).forEach(function (w) {
        var t = tokens(w);
        var line = t[0], o = odds(t[t.length - 1]);
        if (!/^\d+(\.\d+)?$/.test(line || '') || !o) { bad.push(t.join(' ')); return; }
        rows.push([mkey, mkt, side, String(parseFloat(line)), o].join('|'));
      });
    });
    return { rows: rows, bad: bad };
  }

  async function scrape(mkey, opts) {
    opts = opts || {};
    var out = [], notes = {};
    var win = section('Win Market');
    if (win) {
      var w = wrappers(win).slice(0, 3);
      var sides = ['H', 'D', 'A'];
      if (w.length === 3) {
        w.forEach(function (x, i) {
          var t = tokens(x), o = odds(t[t.length - 1]);
          if (o) out.push([mkey, 'WIN', sides[i], '-', o].join('|'));
        });
        notes.win = w.map(function (x) { return tokens(x)[0]; }).join(' / ');
      } else notes.win = 'wrappers=' + w.length;
    } else notes.win = 'none';
    var M = [['Total Goals Over/Under', 'TG'], ['Total Home Goals', 'TH'], ['Total Away Goals', 'TA']];
    for (var i = 0; i < M.length; i++) {
      var e = await expand(M[i][0]);
      var sec = section(M[i][0]);
      if (sec) await showMore(sec);
      if (!sec || !wrappers(sec).length) { notes[M[i][1]] = e; continue; }
      var r = ouSection(sec, mkey, M[i][1]);
      out = out.concat(r.rows);
      notes[M[i][1]] = e + ' n=' + r.rows.length + (r.bad.length ? ' bad=' + JSON.stringify(r.bad.slice(0, 3)) : '');
    }
    var need = ['WIN|H', 'WIN|D', 'WIN|A', 'TG|O|2.5', 'TG|U|2.5'];
    var have = out.map(function (r) { var p = r.split('|'); return p[1] === 'WIN' ? p[1] + '|' + p[2] : p[1] + '|' + p[2] + '|' + p[3]; });
    var ok = need.every(function (n) { return have.indexOf(n) >= 0; });
    if (!opts.dry) {
      var all = JSON.parse(localStorage.getItem('TOT_ROWS') || '[]');
      localStorage.setItem('TOT_ROWS', JSON.stringify(all.concat(out)));
    }
    return { match: mkey, ok: ok, n: out.length, notes: notes, rows: opts.dry ? out : undefined };
  }
  scrape.expand = expand;
  return scrape;
})()
