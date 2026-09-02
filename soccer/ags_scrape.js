/* soccer/ags_scrape.js — oddschecker Anytime Goalscorer -> ags.psv rows.
 *
 * WHY THIS FILE EXISTS. Until 2026-09-02 this scrape was a RECIPE in PIPELINE.md, re-derived by
 * hand every slate. That is exactly the arrangement slate_assemble.py was written to end on the
 * MLB side ("keep this in the repo so it is NEVER rebuilt from memory again"), and it cost the
 * soccer board twice: AGSNA-2026-08-29 (54 of 330 names corrupted) and BETPCT-2026-09-02 below.
 * A parse rule that lives only in prose gets re-typed slightly differently every time.
 *
 * WHERE THE MARKET IS. There is no /anytime-goalscorer URL — that 404s. The market is a section
 * on the fixture's /winner page:  section > h2 == "Anytime Goalscorer", one
 * [class*=MarketExpanderBetWrapper] per bet, 15 names per match. "Show More" is cosmetic.
 * ⚠️ oddschecker is NAVIGATE-ONLY since 2026-08-29: a fetch() for any path that is not the loaded
 * one returns a ~929 KB shell. Navigate to each fixture, then run this.
 * ⚠️ Some fixture pages hydrate the market late — 0 wrappers on first load, 15 after ~3 s
 * (2026-08-30: freiburg, augsburg, paris-fc). Wait before harvesting or you ship a short card.
 *
 * THE WRAPPER TEXT, AND THE TWO WAYS IT HAS BITTEN. textContent runs the name, the bet
 * percentage and the price together with no separators:
 *
 *     "Alexander Isak48.52%6/5"      <- BETPCT-2026-09-02
 *     "Bradley Barcola34.36%2/1"
 *     "Federico Chiesan/a23/10"      <- AGSNA-2026-08-29
 *     "Victor Munoz12/5"             <- neither
 *
 * AGSNA-2026-08-29 stripped a trailing `n/a` and an INTEGER `%`. On 2026-09-02 oddschecker
 * started rendering the percentage as a DECIMAL, so `\d+%$` no longer matched and the digits
 * welded to the surname: "Alexander Isak48.". That hits precisely the SHORTEST-PRICED bats — a
 * percentage only renders where there is enough action to compute one — i.e. the anchors. Each
 * one then misses its xG join in soccer_mock.lookup() and scores on the market term alone.
 *
 * Order matters: strip the percentage first, then `n/a`. A row carries one or the other.
 *
 * USAGE (per fixture page, after navigating to .../<slug>/winner):
 *     var ags = eval(localStorage.getItem('AGS'));   // the file EVALUATES TO the function
 *     ags('<canonical fixtures.json key>')            // add {dry:true} to parse without storing
 * It appends "match|player|fraction" rows to localStorage.AGS_ROWS and returns a summary.
 * Emit AGS_ROWS through the @@S@@/@@E@@ + get_page_text channel when every fixture is done.
 * ⚠️ Wipe document.body.innerHTML before appending the payload article — get_page_text picks the
 * PAGE's <article> if it has one, and silently returns the site's copy instead of your payload.
 */
(function () {
  'use strict';

  /* "Alexander Isak48.52%6/5" -> {name:"Alexander Isak", odds:"6/5"} */
  function parseWrapper(raw) {
    var t = String(raw == null ? '' : raw).replace(/\u00a0/g, ' ').trim();
    var m = t.match(/^(.*?)(\d+\/\d+|EVS|SP)$/);
    if (!m) return null;
    var name = m[1], odds = m[2];
    name = name
      .replace(/\d+(?:\.\d+)?%$/, '')   /* BETPCT-2026-09-02: decimal percentage */
      .replace(/n\/a$/i, '')            /* AGSNA-2026-08-29 */
      .replace(/\s+/g, ' ')
      .trim();
    if (!name) return null;
    if (odds === 'SP') return null;     /* starting price -> no number to score */
    if (odds === 'EVS') odds = '1/1';   /* soccer_mock.frac_to_am splits on "/" */
    return { name: name, odds: odds };
  }

  function agsSection() {
    var secs = [].slice.call(document.querySelectorAll('section'));
    for (var i = 0; i < secs.length; i++) {
      var h = secs[i].querySelector('h2');
      if (h && /^\s*Anytime Goalscorer\s*$/i.test(h.textContent)) return secs[i];
    }
    return null;
  }

  function scrape(matchKey, opts) {
    opts = opts || {};
    var sec = agsSection();
    if (!sec) return { match: matchKey, ok: false, why: 'no Anytime Goalscorer section (not priced, or not hydrated yet)' };

    var wraps = [].slice.call(sec.querySelectorAll('[class*=MarketExpanderBetWrapper]'));
    var rows = [], bad = [], seen = {};
    for (var i = 0; i < wraps.length; i++) {
      var p = parseWrapper(wraps[i].textContent);
      if (!p) { bad.push(String(wraps[i].textContent).trim().slice(0, 40)); continue; }
      if (seen[p.name]) continue;       /* the market can render a name twice; first price wins */
      seen[p.name] = 1;
      rows.push(matchKey + '|' + p.name + '|' + p.odds);
    }
    if (!opts.dry) {
      var all = JSON.parse(localStorage.getItem('AGS_ROWS') || '[]');
      localStorage.setItem('AGS_ROWS', JSON.stringify(all.concat(rows)));
    }
    return { match: matchKey, ok: rows.length > 0, n: rows.length, unparsed: bad, rows: rows };
  }

  scrape.parseWrapper = parseWrapper;   /* exposed so the self-test can run without a page */
  return scrape;
})()
