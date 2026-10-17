/* nba/fb_scrape.js -- FIRSTBASKET-2026-10-17. BettingPros "Player to Score the First Basket" (market 142)
 * for one date -> the rows nba_payload.py reads (slates/<date>/fb.psv).
 *
 * RUN IT ON www.bettingpros.com (any page), in the browser:
 *     var fbs = eval(localStorage.getItem('FBS'));     // this file, stored once
 *     var psv = await fbs('2026-10-21');                // -> string, also left in window.FB_PSV
 * then carry FB_PSV to GitHub (window.name -> upload page -> nba/slates/<date>/fb.psv).
 *
 * THE KEY. BettingPros' API wants the x-api-key its own front end sends. It is the site's public key,
 * baked into its JS bundles; key() finds it there (any 30-60 char token near "api key" that answers
 * /v3/events with a 200) and caches it in localStorage.BPK. Nothing else is stored.
 *
 * ROWS (pipe-separated, one game per E row):
 *   E|date|event|sched_utc|HOME|AWAY|status|home_lineup_type|away_lineup_type
 *   L|date|event|h/a|status|bp_id|name|pos|team            -- BettingPros' projected/confirmed fives
 *   S|date|event|bp_id|name|pos|team|open_cost|open_book|book:cost,...   -- 10 FanDuel, 0 consensus
 * Regular season only. A +49000 line is BettingPros' placeholder for a suspended market; it is written
 * as-is and dropped by nba_payload.py.
 */
(function () {
  'use strict';
  var API = 'https://api.bettingpros.com/v3/';
  async function key() {
    var k = localStorage.getItem('BPK');
    if (k) {
      var r0 = await fetch(API + 'events?sport=NBA&date=2026-01-15', { headers: { 'x-api-key': k } });
      if (r0.status === 200) return k;
    }
    var urls = Array.from(new Set(performance.getEntriesByType('resource').map(function (e) { return e.name; })
      .concat(Array.from(document.scripts).map(function (s) { return s.src; }))
      .filter(function (u) { return /\.m?js(\?|$)/.test(u); })));
    var cands = new Set();
    for (var i = 0; i < urls.length; i++) {
      try {
        var t = await (await fetch(urls[i])).text(), re = /x-api-key|apikey|api_key|apiKey/ig, m;
        while ((m = re.exec(t))) {
          (t.slice(Math.max(0, m.index - 400), m.index + 400).match(/[A-Za-z0-9_\-]{24,64}/g) || []).forEach(function (x) {
            if (/[0-9]/.test(x) && /[A-Z]/.test(x) && /[a-z]/.test(x)) cands.add(x);
          });
        }
      } catch (e) {}
    }
    for (var c of cands) {
      var r = await fetch(API + 'events?sport=NBA&date=2026-01-15', { headers: { 'x-api-key': c } });
      if (r.status === 200) { localStorage.setItem('BPK', c); return c; }
    }
    throw new Error('no BettingPros key found -- load a BettingPros odds page first');
  }
  async function scrape(date) {
    var H = { headers: { 'x-api-key': await key() } }, rows = [];
    var ev = await (await fetch(API + 'events?sport=NBA&date=' + date, H)).json();
    var evs = (ev.events || []).filter(function (e) { return e.season_type === 'REG'; });
    evs.forEach(function (t) {
      var L = t.lineups || {};
      rows.push(['E', date, t.id, t.scheduled, t.home, t.visitor, t.status, L.home_lineup_type || '', L.away_lineup_type || ''].join('|'));
      [['home_lineup', 'h'], ['away_lineup', 'a'], ['visitor_lineup', 'a']].forEach(function (s) {
        (L[s[0]] || []).forEach(function (x) {
          if (!x || !x.participant) return;
          var pl = x.participant.player || {};
          rows.push(['L', date, t.id, s[1], x.status, x.participant.id, x.participant.name, pl.position || '', pl.team || ''].join('|'));
        });
      });
    });
    var ids = evs.map(function (e) { return e.id; }), nsel = 0;
    for (var i = 0; i < ids.length; i += 25) {
      for (var page = 1; ; page++) {
        var o = await (await fetch(API + 'offers?sport=NBA&market_id=142&event_id=' + ids.slice(i, i + 25).join(':') + '&limit=25&page=' + page, H)).json();
        (o.offers || []).forEach(function (of) {
          var P = {}; (of.participants || []).forEach(function (p) { P[p.id] = p; });
          (of.selections || []).forEach(function (s) {
            var p = P[s.participant] || {}, pl = p.player || {}, ol = s.opening_line || {};
            var bk = (s.books || []).map(function (b) {
              var l = (b.lines || []).find(function (x) { return x.main; }) || (b.lines || [])[0];
              return l && !l.is_off ? b.id + ':' + l.cost : null;
            }).filter(Boolean).join(',');
            rows.push(['S', date, of.event_id, s.participant, p.name || s.label, pl.position || '', pl.team || '', ol.cost, ol.book_id, bk].join('|'));
            nsel++;
          });
        });
        var pg = o._pagination || {};
        if (!pg.total_pages || page >= pg.total_pages) break;
      }
    }
    window.FB_PSV = rows.join('\n') + '\n';
    window.FB_SUM = { date: date, games: evs.length, prices: nsel, lineups: rows.filter(function (r) { return r[0] === 'L'; }).length };
    return window.FB_PSV;
  }
  scrape.key = key;
  return scrape;
})()
