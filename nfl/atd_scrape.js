/* atd_scrape.js -- ANYTIME TOUCHDOWN prices off oddschecker, as CODE not a prose recipe.
 *
 * Sibling of soccer/ags_scrape.js and deliberately a near-copy: same site, same React component,
 * and `parseWrapper` is BYTE-IDENTICAL to the soccer one. That is the point -- the two markets
 * share a renderer, so they must share a parser, or a fix to one silently rots the other.
 * The soccer parser was validated on NFL before this file existed: 15/15 parsed, 0 unparsed,
 * on Falcons at Steelers.
 *
 * THREE THINGS THAT DIFFER FROM SOCCER, all NFL-specific:
 *
 *   1. THE MARKET IS COLLAPSED. Soccer's Anytime Goalscorer renders expanded; the NFL page ships
 *      it as an accordion (h2 role=button aria-expanded=false) with ZERO bet wrappers in the DOM
 *      until it is opened. A navigate-only scrape returns "no section" or 0 rows and looks like
 *      an unpriced market. So this one clicks the header and waits for hydration. It is a DOM
 *      click on an accordion, not a dialog -- no alert/confirm is reachable from it.
 *
 *   2. D/ST IS IN THE MARKET AND IS NOT A PLAYER. Oddschecker lists "Pittsburgh Steelers D/ST"
 *      and "Atlanta Falcons D/ST" alongside the skill players. A defence has no row in the model
 *      (no touches, no depth slot, no roster id) so it would join to nothing, score on the market
 *      term alone, and could still land on a ticket as if it were a bat. Dropped here, at the
 *      source, and counted so a silent format change shows up.
 *
 *   3. THE MARKET IS THE TOP 15 BY PRICE. Not a truncation this scraper can lift -- there is no
 *      show-more control in the section, only affiliate links. 15 x 13 Sunday games = ~195 priced
 *      names, against 297 on a full MLB card, and they are the SHORT end, which is the end the
 *      board drafts from. Recorded so nobody later reads a 15-row match as a partial scrape.
 *
 * USAGE (browser console / javascript_tool, one fixture at a time, navigate between):
 *     var f = eval(localStorage.getItem('ATD'));
 *     await f('atlanta-falcons-at-pittsburgh-steelers');
 *   rows accumulate in localStorage.ATD_ROWS as  match|player|fractional-odds
 *   f.parseWrapper is exposed so the self-test can run with no page attached.
 */
(function () {
  'use strict';

  /* BYTE-IDENTICAL to soccer/ags_scrape.js parseWrapper. Do not "improve" one copy alone.
     BETPCT-2026-09-02: a bet-percentage suffix welds to the surname ("Isak48.52%6/5").
     AGSNA-2026-08-29: an unpriced book renders "n/a" before the fraction. */
  function parseWrapper(raw) {
    var t = String(raw == null ? '' : raw).replace(/ /g, ' ').trim();
    var m = t.match(/^(.*?)(\d+\/\d+|EVS|SP)$/);
    if (!m) return null;
    var name = m[1], odds = m[2];
    name = name.replace(/\d+(?:\.\d+)?%$/, '').replace(/n\/a$/i, '').replace(/\s+/g, ' ').trim();
    if (!name) return null;
    if (odds === 'SP') return null;          /* starting price -- no number to score */
    if (odds === 'EVS') odds = '1/1';
    return { name: name, odds: odds };
  }

  function atdSection() {
    var secs = [].slice.call(document.querySelectorAll('section'));
    for (var i = 0; i < secs.length; i++) {
      var h = secs[i].querySelector('h2');
      if (h && /^\s*Anytime Touchdown Scorer\s*$/i.test(h.textContent)) return secs[i];
    }
    return null;
  }

  /* A defence is not a bat. Oddschecker spells it "<Team> D/ST"; the guard is deliberately
     loose (D/ST, DST, "Defense") because the label is theirs to change, not ours. */
  function isTeamEntry(name) {
    return /\bD\s*\/\s*ST\b/i.test(name) || /\bDST\b/i.test(name) || /\bDefense\b/i.test(name);
  }

  async function scrape(matchKey, opts) {
    opts = opts || {};
    var sec = atdSection();
    if (!sec) return { match: matchKey, ok: false, why: 'no Anytime Touchdown Scorer section' };

    var h2 = sec.querySelector('h2');
    if (h2 && h2.getAttribute('aria-expanded') === 'false') {
      h2.click();
      var waited = 0;
      while (waited < 8000) {                       /* poll rather than one fixed sleep */
        await new Promise(function (r) { setTimeout(r, 400); });
        waited += 400;
        if (sec.querySelectorAll('[class*=MarketExpanderBetWrapper]').length) break;
      }
    }

    var wraps = [].slice.call(sec.querySelectorAll('[class*=MarketExpanderBetWrapper]'));
    if (!wraps.length) return { match: matchKey, ok: false, why: 'section never hydrated' };

    var rows = [], bad = [], teams = [], seen = {};
    for (var i = 0; i < wraps.length; i++) {
      var p = parseWrapper(wraps[i].textContent);
      if (!p) { bad.push(String(wraps[i].textContent).trim().slice(0, 40)); continue; }
      if (isTeamEntry(p.name)) { teams.push(p.name); continue; }
      if (seen[p.name]) continue;                   /* first price wins, as in soccer */
      seen[p.name] = 1;
      rows.push(matchKey + '|' + p.name + '|' + p.odds);
    }
    if (!opts.dry) {
      var all = JSON.parse(localStorage.getItem('ATD_ROWS') || '[]');
      localStorage.setItem('ATD_ROWS', JSON.stringify(all.concat(rows)));
    }
    return { match: matchKey, ok: rows.length > 0, n: rows.length,
             dropped_team_entries: teams, unparsed: bad, rows: rows };
  }

  scrape.parseWrapper = parseWrapper;
  scrape.isTeamEntry = isTeamEntry;
  return scrape;
})()
