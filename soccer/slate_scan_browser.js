/* slate_scan_browser.js -- SCANPORT-2026-10-13. slate_scan.js, runnable from a browser tab.
 *
 * WHY THIS EXISTS, AND IT IS THE SAME REASON slate_scan.js EXISTS.
 * That file's header says it plainly: "is there a soccer board today?" kept being answered from
 * memory, and the fix "is not to remember harder, it is to stop remembering. Run this." It then
 * documents three wrong answers inside one hour on 2026-09-08, one of which was missing a cup
 * round that CUPSCOPE had scoped six days earlier.
 *
 * 🚨 ON 2026-10-13 IT HAPPENED AGAIN, AND THIS FILE IS WHY.
 * The container cannot reach ESPN -- slate_scan.js correctly refuses there (exit 3, "No board
 * decision was made"), so it is useless in the one place a session naturally reaches for it. With
 * no runnable tool, the scan got hand-rolled in the browser against SIX competitions: the five
 * core leagues plus MLS. Coverage is EIGHTEEN. The answer came back "no fixtures today -- it is an
 * international break" on an evening with a NINE-TIE CHAMPIONS LEAGUE MATCHDAY on it, and the only
 * thing that caught it was the owner separately asking whether the cups were still covered.
 *
 * A tool that cannot run where the work happens does not prevent the failure it was written for.
 * So: same gate, same refusal, same CUPSCOPE, in the place that can actually reach ESPN.
 *
 * HOW TO RUN IT. ESPN is not reachable cross-origin, so be ON an ESPN origin first, then paste:
 *
 *     // navigate to  https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/teams
 *     const r = await slateScan('2026-10-13');
 *     r.report                      // the printable summary
 *     r.admitted                    // the ties the board may draft from
 *     JSON.stringify(r.seed,null,1) // a fixtures.json skeleton, keyed and kickoff-stamped
 *
 * ⚠️ COVERAGE IS FETCHED, NEVER COPIED. soccer/coverage.json is the single list of what this board
 * covers (COVERAGE-2026-09-08). Inlining a second copy here is exactly how the two drift and how
 * a cup round goes missing, so this reads the committed file over raw.githubusercontent and
 * REFUSES if it cannot. raw caches ~5 min after a push, which is nothing against a list that
 * changes a few times a season.
 *
 * ⚠️ ESPN GROUPS BY LOCAL (ET) DATE AND THAT IS WHAT WE WANT -- a Wednesday-night MLS card comes
 * back under the Wednesday ET date even though four kickoffs are Thursday in UTC. Do not "correct"
 * it to UTC; the slate key must be the ET day or soccer_payload.et_min's nightcap flag breaks.
 * Verified again on 10-13: dates=20261014 returns 6 events dated 10-14Z and 9 dated 10-15Z, and
 * every one of them is ET 10-14.
 *
 * ⚠️ THIS CHECKS ONE HALF OF CUPSCOPE, exactly as slate_scan.js does. "At least one top-five side"
 * is checkable here. "The fixture's oddschecker page actually renders an Anytime Goalscorer
 * section" is only checkable on that page. ADMIT means "worth opening", not "shippable".
 */
(function (root) {
  'use strict';

  var API = 'https://site.api.espn.com/apis/site/v2/sports/soccer';
  var COVERAGE_URL = 'https://raw.githubusercontent.com/jnthnaiken/theticketroom/main/soccer/coverage.json';

  function slugs(o) { return Object.keys(o || {}).filter(function (k) { return k !== '_doc'; }); }

  async function getJSON(url) {
    var r = await fetch(url);
    if (!r.ok) throw new Error(r.status + ' ' + url);
    return r.json();
  }

  /* The gate set, from the core leagues' OWN team lists. RANGEDEAD-2026-09-21: it used to ask each
     league's scoreboard over a season-wide window and ESPN now 400s on any date RANGE, which made
     every league fail and the gate come back empty -- reported as "NOTHING ADMISSIBLE" on a
     21-fixture Sunday. /teams is one call per league and is immune. */
  async function eligibleClubs(core) {
    var out = {}, failed = [];
    for (var i = 0; i < slugs(core).length; i++) {
      var slug = slugs(core)[i];
      try {
        var j = await getJSON(API + '/' + slug + '/teams');
        var teams = (((j.sports || [])[0] || {}).leagues || [])[0];
        teams = (teams || {}).teams || [];
        if (!teams.length) { failed.push(slug); continue; }
        teams.forEach(function (t) { if (t && t.team && t.team.id) out[t.team.id] = core[slug]; });
      } catch (e) { failed.push(slug); }
    }
    return { clubs: out, failed: failed };
  }

  function slugify(s) {
    return String(s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '')
      .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  }

  async function slateScan(date, opts) {
    opts = opts || {};
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date || '')) throw new Error('usage: slateScan("YYYY-MM-DD")');
    var ymd = date.replace(/-/g, '');

    var COV = opts.coverage;
    if (!COV) {
      try { COV = await getJSON(opts.coverageUrl || COVERAGE_URL); }
      catch (e) {
        return { ok: false, why: 'coverage',
          report: '!! could not read coverage.json (' + e.message + ')\n'
                + '   REFUSING to scan against a coverage list I would have to invent.' };
      }
    }

    var gate = await eligibleClubs(COV.core || {});
    var top5 = gate.clubs, n = Object.keys(top5).length;
    /* 🚨 A BROKEN GATE IS A REFUSAL, NOT A FINDING. With no gate set every cup tie is dropped for
       want of a top-five side and the summary reads like an empty day. The two states are
       indistinguishable on the page and one of them is a lie. */
    if (gate.failed.length || n === 0) {
      return { ok: false, why: 'gate', clubs: n, failed: gate.failed,
        report: '!! eligible-club scan FAILED -- ' + n + ' clubs resolved (expected ~96)'
              + (gate.failed.length ? ', leagues that did not answer: ' + gate.failed.join(', ') : '')
              + '\n   Refusing to report a slate against a broken gate. No board decision was made.' };
    }

    var base = Date.UTC(+date.slice(0, 4), +date.slice(5, 7) - 1, +date.slice(8, 10));
    var groups = [[COV.core, false, 'core'], [COV.open, false, 'core'],
                  [COV.gated, true, null], [COV.intl || {}, false, 'intl: open it, JOINGATE decides']];
    var rows = [], errors = [];
    for (var g = 0; g < groups.length; g++) {
      var set = groups[g][0], gated = groups[g][1], openWhy = groups[g][2];
      var ss = slugs(set);
      for (var k = 0; k < ss.length; k++) {
        var slug = ss[k], j;
        try { j = await getJSON(API + '/' + slug + '/scoreboard?dates=' + ymd); }
        catch (e) { errors.push(slug + ': ' + e.message); continue; }
        (j.events || []).forEach(function (ev) {
          var comp = (ev.competitions || [])[0] || {};
          var cs = comp.competitors || [];
          var hit = cs.filter(function (c) { return top5[c.team.id]; })
                      .map(function (c) { return top5[c.team.id]; });
          var admit = !gated || hit.length > 0;
          var home = cs.filter(function (c) { return c.homeAway === 'home'; })[0] || {};
          var away = cs.filter(function (c) { return c.homeAway === 'away'; })[0] || {};
          rows.push({
            league: set[slug], slug: slug, id: ev.id, iso: ev.date,
            name: ev.name, short: ev.shortName,
            /* HOME AND AWAY COME FROM competitors, NEVER FROM ev.name -- ESPN writes soccer as
               "Away at Home", so parsing the string inverts every fixture on the card. */
            home: (home.team || {}).displayName || '', away: (away.team || {}).displayName || '',
            kickoffZ: String(ev.date || '').slice(11, 16),
            /* ⚠️ SLATE-RELATIVE, AND IT MAY EXCEED 1440. fixtures.json's `kickoff` is UTC minutes
               past midnight of the SLATE's UTC date, so an MLS tie at 02:30Z the next morning is
               1590, not 150 -- soccer_payload.et_min adds off*1440 to roll it back. Computing it
               from the wall clock alone silently files a nightcap as a lunchtime kickoff. */
            kickoff: ev.date ? Math.round((Date.parse(ev.date) - base) / 60000) : null,
            status: ((ev.status || {}).type || {}).name || '',
            admit: admit, why: admit ? (gated ? 'top5: ' + hit.join('+') : openWhy) : 'no top-five side'
          });
        });
      }
    }
    rows.sort(function (a, b) { return (a.kickoff == null ? 9999 : a.kickoff) - (b.kickoff == null ? 9999 : b.kickoff); });

    var admitted = rows.filter(function (r) { return r.admit; });
    var dropped = rows.filter(function (r) { return !r.admit; });

    /* A fixtures.json skeleton, keyed the way the committed slates are keyed: slugified ESPN
       display names, home first. The oddschecker URL slug is a DIFFERENT string and belongs only
       in the scrape -- coverage.json's _slugtraps records why. */
    var seed = { date: date, matches: {} };
    admitted.forEach(function (r) {
      if (!r.home || !r.away) return;
      seed.matches[slugify(r.home) + '-v-' + slugify(r.away)] = {
        home: r.home, away: r.away, kickoff: r.kickoff,
        league: r.league, espn: [r.slug, r.id]
      };
    });

    var line = function (r) {
      return '  ' + (r.admit ? 'ADMIT' : 'drop ') + '  ' + String(r.league || '').padEnd(14)
           + r.kickoffZ + 'Z  ' + (r.home && r.away ? r.home + ' v ' + r.away : (r.name || r.short))
           + '   [' + r.why + ']';
    };
    var report = date + ' -- gate ' + n + ' clubs | ' + rows.length + ' fixture(s) across '
               + (slugs(COV.core).length + slugs(COV.open).length + slugs(COV.gated).length
                  + slugs(COV.intl || {}).length) + ' competitions, '
               + admitted.length + ' ADMITTED, ' + dropped.length + ' dropped'
               + (errors.length ? '\n  ::warning:: ' + errors.join('; ') : '')
               + (rows.length ? '\n' + rows.map(line).join('\n')
                              : '\n  NOTHING ADMISSIBLE -- no board today');
    if (n < 80) report = '::warning:: only ' + n + ' eligible clubs resolved (expected ~96) -- gate may be thin\n' + report;

    return { ok: true, date: date, clubs: n, rows: rows, admitted: admitted, dropped: dropped,
             errors: errors, seed: seed, report: report };
  }

  var api = { slateScan: slateScan, eligibleClubs: eligibleClubs, slugify: slugify, API: API,
              COVERAGE_URL: COVERAGE_URL };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else { root.slateScan = slateScan; root.SlateScanBrowser = api; }
})(typeof globalThis !== 'undefined' ? globalThis : this);
