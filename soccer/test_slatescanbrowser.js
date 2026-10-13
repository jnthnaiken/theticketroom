#!/usr/bin/env node
/* test_slatescanbrowser.js -- SCANPORT-2026-10-13.
 *
 * WHY. slate_scan.js answers "is there a board today?" and CANNOT RUN IN THE CONTAINER (no ESPN
 * egress -- it refuses, correctly). So on 2026-10-13 the scan was hand-rolled in the browser
 * against six competitions instead of eighteen, and the session reported "no fixtures today" on an
 * evening carrying a NINE-TIE CHAMPIONS LEAGUE MATCHDAY. slate_scan_browser.js is that tool in the
 * place the work actually happens; this pins the behaviour that made the miss possible.
 *
 * Every case here is a real failure mode, not a shape:
 *   1. the 10-13 card itself -- cups ARE scanned, and CUPSCOPE admits 8 of 9
 *   2. a broken gate REFUSES and never prints NOTHING ADMISSIBLE (RANGEDEAD-2026-09-21)
 *   3. a genuinely empty day still CAN say NOTHING ADMISSIBLE -- that answer must stay reachable
 *   4. an MLS kickoff past midnight UTC is >1440, not wrapped (soccer_payload.et_min)
 *   5. home/away come from competitors, because ESPN writes soccer as "Away at Home"
 *   6. unreadable coverage is a refusal, not an assumed list
 *
 *     node test_slatescanbrowser.js
 */
'use strict';
const path = require('path');

let fail = 0;
const chk = (label, ok, detail) => {
  console.log((ok ? 'PASS  ' : 'FAIL  ') + label);
  if (!ok) { fail++; if (detail !== undefined) console.log('       ', detail); }
};

const COVERAGE = {
  core: { 'eng.1': 'EPL', 'esp.1': 'La_liga', 'ita.1': 'Serie_A', 'ger.1': 'Bundesliga', 'fra.1': 'Ligue_1' },
  open: { 'usa.1': 'MLS' },
  gated: { 'uefa.champions': 'UCL', 'uefa.europa': 'UEL', 'eng.league_cup': 'EFL_Cup' },
  intl: { 'uefa.nations': 'UNL' }
};

/* ids: 1..18 are EPL, 21..38 La Liga, etc. Only membership matters. */
const CLUBS = { 'eng.1': ['1', '2'], 'esp.1': ['21', '22'], 'ita.1': ['31', '32'],
                'ger.1': ['41', '42'], 'fra.1': ['51', '52'] };

function ev(id, iso, homeName, homeId, awayName, awayId) {
  return { id, date: iso, name: awayName + ' at ' + homeName, shortName: 'X',
           status: { type: { name: 'STATUS_SCHEDULED' } },
           competitions: [{ competitors: [
             { homeAway: 'home', team: { id: homeId, displayName: homeName } },
             { homeAway: 'away', team: { id: awayId, displayName: awayName } }] }] };
}

function stub(events, opts) {
  opts = opts || {};
  global.fetch = async (url) => {
    if (url.indexOf('coverage.json') >= 0) {
      if (opts.coverageDead) return { ok: false, status: 500 };
      return { ok: true, json: async () => COVERAGE };
    }
    const m = url.match(/soccer\/([^/]+)\/(teams|scoreboard)/);
    if (!m) return { ok: false, status: 404 };
    const [, slug, kind] = m;
    if (kind === 'teams') {
      if ((opts.deadLeagues || []).indexOf(slug) >= 0) return { ok: false, status: 400 };
      return { ok: true, json: async () => ({ sports: [{ leagues: [{ teams:
        (CLUBS[slug] || []).map(id => ({ team: { id } })) }] }] }) };
    }
    return { ok: true, json: async () => ({ events: (events[slug] || []) }) };
  };
}

const { slateScan } = require(path.join(__dirname, 'slate_scan_browser.js'));

(async () => {
  console.log('SCANPORT-2026-10-13 -- the browser scan\n');

  /* ---- 1. the real 10-13 shape: a UCL matchday and nothing in the core leagues -------------- */
  stub({ 'uefa.champions': [
    ev('401915418', '2026-10-13T16:45Z', 'Lens', '51', 'Sporting CP', '900'),          // Ligue_1 home
    ev('401915436', '2026-10-13T16:45Z', 'Sabah FK', '901', 'Slavia Prague', '902'),   // neither
    ev('401915411', '2026-10-13T19:00Z', 'Viking FK', '903', 'Bayern Munich', '41'),   // Bundesliga away
    ev('401915410', '2026-10-13T19:00Z', 'Villarreal', '21', 'Napoli', '31')] });      // two core sides
  let r = await slateScan('2026-10-13');
  chk('the scan succeeds', r.ok === true, r.report);
  chk('CUPSCOPE admits the three ties with a top-five side', r.admitted.length === 3,
      r.admitted.map(x => x.home + ' v ' + x.away));
  chk('and drops the one with none', r.dropped.length === 1 && r.dropped[0].home === 'Sabah FK',
      r.dropped.map(x => x.home + ' v ' + x.away));
  chk('a cup competition is scanned at all -- the 10-13 miss', r.rows.length === 4, r.rows.length);
  chk('the report names all 18-ish competitions, not just the core', /across 10 competitions/.test(r.report),
      r.report.split('\n')[0]);
  chk('a two-core tie reports BOTH leagues', (r.admitted.filter(x => x.home === 'Villarreal')[0] || {}).why
      === 'top5: La_liga+Serie_A', (r.admitted.filter(x => x.home === 'Villarreal')[0] || {}).why);

  /* ---- 5. home/away from competitors, NOT from ev.name ------------------------------------- */
  const viking = r.admitted.filter(x => x.id === '401915411')[0];
  chk('home/away come from competitors, not the "Away at Home" name string',
      viking.home === 'Viking FK' && viking.away === 'Bayern Munich',
      { name: viking.name, home: viking.home, away: viking.away });
  chk('the seed key is slugified ESPN names, home first',
      Object.keys(r.seed.matches).indexOf('viking-fk-v-bayern-munich') >= 0,
      Object.keys(r.seed.matches));
  chk('kickoffs are slate-relative minutes', r.seed.matches['viking-fk-v-bayern-munich'].kickoff === 1140,
      r.seed.matches['viking-fk-v-bayern-munich'].kickoff);

  /* ---- 2. a broken gate REFUSES ------------------------------------------------------------ */
  stub({ 'uefa.champions': [ev('1', '2026-10-13T19:00Z', 'Villarreal', '21', 'Napoli', '31')] },
       { deadLeagues: ['eng.1', 'esp.1', 'ita.1', 'ger.1', 'fra.1'] });
  r = await slateScan('2026-10-13');
  chk('a dead gate refuses', r.ok === false && r.why === 'gate', r.report);
  chk('  ...and NEVER says NOTHING ADMISSIBLE off a broken gate',
      !/NOTHING ADMISSIBLE/.test(r.report), r.report);
  chk('  ...and names the leagues that did not answer', /eng\.1/.test(r.report), r.report);

  /* a PARTIAL gate is also a refusal -- 4 of 5 silently drops a league's cup ties */
  stub({}, { deadLeagues: ['fra.1'] });
  r = await slateScan('2026-10-13');
  chk('a PARTIALLY dead gate is also a refusal', r.ok === false && r.why === 'gate', r.report);

  /* ---- 3. a genuinely empty day must still be sayable -------------------------------------- */
  stub({});
  r = await slateScan('2026-10-13');
  chk('a real empty day succeeds and says NOTHING ADMISSIBLE',
      r.ok === true && /NOTHING ADMISSIBLE/.test(r.report), r.report);

  /* ---- 4. MLS rollover: 02:30Z the NEXT morning is 1590, not 150 --------------------------- */
  stub({ 'usa.1': [ev('9001', '2026-10-15T02:30Z', 'LA Galaxy', '700', 'Portland Timbers', '701'),
                   ev('9002', '2026-10-14T23:30Z', 'Toronto FC', '702', 'Orlando City', '703')] });
  r = await slateScan('2026-10-14');
  const gal = r.admitted.filter(x => x.id === '9001')[0];
  const tor = r.admitted.filter(x => x.id === '9002')[0];
  chk('an MLS kickoff past midnight UTC exceeds 1440', gal.kickoff === 1590, gal.kickoff);
  chk('  ...and a same-day one does not', tor.kickoff === 1410, tor.kickoff);
  chk('  ...so they sort in real order', r.admitted[0].id === '9002', r.admitted.map(x => x.id));
  chk('MLS is admitted with no gate', gal.why === 'core', gal.why);

  /* ---- 6. unreadable coverage is a refusal, not an invented list --------------------------- */
  stub({}, { coverageDead: true });
  r = await slateScan('2026-10-13');
  chk('unreadable coverage.json refuses rather than assuming a list',
      r.ok === false && r.why === 'coverage', r.report);

  console.log();
  process.exit(fail ? 1 : 0);
})();
