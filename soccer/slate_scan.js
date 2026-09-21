#!/usr/bin/env node
/* slate_scan.js -- WHAT IS ON TODAY. Reads soccer/coverage.json, asks ESPN, applies the
 * CUPSCOPE gate, prints the fixtures the board may draft from.
 *
 * COVERAGE-2026-09-08. This exists because "is there a soccer board today?" was being answered
 * from memory, and on 2026-09-08 that answer was wrong three times inside one hour:
 *
 *     "no soccer today, leagues return Friday"   -- missed 14 MLS fixtures the next day
 *     "MLS was never built"                      -- it was; soccer_asa.js had been committed a week
 *     "five UCL ties today"                      -- there were also four EFL Cup ties, which
 *                                                   CUPSCOPE-2026-09-01 had scoped BY DATE AND BY
 *                                                   EVENT ID six days earlier
 *
 * Every one of those was a recall failure, not a data failure: ESPN had the fixtures the whole
 * time. So the fix is not to remember harder, it is to stop remembering. Run this.
 *
 *     node slate_scan.js 2026-09-08            # the day's admissible fixtures
 *     node slate_scan.js 2026-09-08 --all      # include what was dropped, and why
 *     node slate_scan.js 2026-09-08 --json     # machine-readable, for fixtures.json seeding
 *
 * ⚠️ THE GATE SET IS DERIVED, NOT LISTED. The eligible-club set is built from the five core
 * leagues' OWN team lists, so promotion and relegation need no edit here and cannot silently
 * rot. 96 clubs (20+20+20+18+18), which is the arithmetic.
 *
 * 🚨 RANGEDEAD-2026-09-21. It used to ask each core league's SCOREBOARD over a season-wide
 * window (`?dates=20260701-20270630`). ESPN now returns 400 for any date RANGE -- a month is
 * rejected too, only single dates work. So every core league failed, the gate set came back
 * EMPTY, and on 2026-09-20 -- a 21-fixture Sunday -- this tool printed:
 *
 *     2026-09-20 -- 0 fixture(s) across 15 competitions, 0 eligible clubs
 *       NOTHING ADMISSIBLE -- no board today
 *
 * The tool written *because* "is there a board today?" was being answered wrong from memory
 * answered it wrong with a straight face. `/{slug}/teams` is one call per league, returns the
 * same team ids, and is immune to the range restriction. Verified 2026-09-21: 20/20/20/18/18.
 *
 * 🚨 AND A FAILED SCAN IS NOW A REFUSAL, NOT A FINDING. "NOTHING ADMISSIBLE" was printable when
 * the gate set had not resolved -- the two states are indistinguishable on the page and one of
 * them is a lie. If the gate set does not resolve, this exits 3 and prints nothing else.
 *
 * ⚠️ THIS CHECKS ONE HALF OF CUPSCOPE. "At least one top-five side" is checkable from ESPN and is
 * checked here. "The fixture's oddschecker page actually renders an Anytime Goalscorer section"
 * is only checkable on the page -- a severe mismatch can carry 26 markets and zero player markets
 * (VfL Osnabruck v Bayern, DFB Pokal 2026-09-02). ADMIT here means "worth opening", not "shippable".
 *
 * ⚠️ ESPN GROUPS BY LOCAL DATE, WHICH IS WHAT WE WANT. usa.1 returns a Wednesday-night MLS card
 * under the Wednesday ET date even though four of its kickoffs are Thursday in UTC. Do not
 * "correct" this to UTC -- the slate key must be the ET day or et_min's nightcap flag breaks.
 */
'use strict';
const fs = require('fs');
const path = require('path');

const API = 'https://site.api.espn.com/apis/site/v2/sports/soccer';
const COV = JSON.parse(fs.readFileSync(path.join(__dirname, 'coverage.json'), 'utf8'));
const slugs = o => Object.keys(o).filter(k => k !== '_doc');

async function get(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(r.status + ' ' + url);
  return r.json();
}

/* The gate set, derived from the core leagues themselves -- their TEAM LISTS, not a scoreboard
   window. See RANGEDEAD-2026-09-21 in the header for why the window is gone.
   Returns {clubs, failed}: `failed` names the leagues that did not answer, and the caller
   REFUSES rather than reporting an empty slate off a broken gate. */
async function eligibleClubs() {
  const out = {}, failed = [];
  for (const slug of slugs(COV.core)) {
    let j;
    try { j = await get(`${API}/${slug}/teams`); }
    catch (e) { console.error(`::warning::${slug} club scan failed (${e.message})`); failed.push(slug); continue; }
    const teams = j?.sports?.[0]?.leagues?.[0]?.teams || [];
    if (!teams.length) { console.error(`::warning::${slug} club scan returned no teams`); failed.push(slug); continue; }
    for (const t of teams) if (t?.team?.id) out[t.team.id] = COV.core[slug];
  }
  return { clubs: out, failed };
}

async function scan(date, top5) {
  const ymd = date.replace(/-/g, '');
  const rows = [];
  const groups = [[COV.core, false], [COV.open, false], [COV.gated, true]];
  for (const [set, gated] of groups) {
    for (const slug of slugs(set)) {
      let j;
      try { j = await get(`${API}/${slug}/scoreboard?dates=${ymd}`); }
      catch (e) { console.error(`::warning::${slug} ${date} failed (${e.message})`); continue; }
      for (const ev of j.events || []) {
        const cs = ev.competitions?.[0]?.competitors || [];
        const hit = cs.filter(c => top5[c.team.id]).map(c => top5[c.team.id]);
        const admit = !gated || hit.length > 0;
        rows.push({
          league: set[slug], espn: [slug, ev.id], id: ev.id,
          name: ev.name, short: ev.shortName,
          kickoffZ: String(ev.date || '').slice(11, 16),
          kickoff: (() => { const t = String(ev.date || '').slice(11, 16).split(':');
                            return t.length === 2 ? (+t[0]) * 60 + (+t[1]) : null; })(),
          status: ev.status?.type?.name || '',
          admit, why: admit ? (gated ? 'top5: ' + hit.join('+') : 'core') : 'no top-five side'
        });
      }
    }
  }
  rows.sort((a, b) => (a.kickoff ?? 9999) - (b.kickoff ?? 9999));
  return rows;
}

(async () => {
  const date = process.argv[2];
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date || '')) {
    console.error('usage: slate_scan.js <YYYY-MM-DD> [--all] [--json]');
    process.exit(2);
  }
  const showAll = process.argv.includes('--all');
  const asJson  = process.argv.includes('--json');

  const { clubs: top5, failed } = await eligibleClubs();
  const n = Object.keys(top5).length;
  /* 🚨 RANGEDEAD-2026-09-21: a broken gate must not be reportable as an empty slate. The CUPSCOPE
     half of this tool is "at least one top-five side", so with no gate set every cup tie would be
     dropped for the wrong reason and the summary line would read like a finding. Refuse. */
  if (failed.length || n === 0) {
    console.error(`!! eligible-club scan FAILED -- ${n} clubs resolved (expected ~96)`
                + (failed.length ? `, leagues that did not answer: ${failed.join(', ')}` : ''));
    console.error('   Refusing to report a slate against a broken gate. No board decision was made.');
    process.exit(3);
  }
  /* Thin but not broken: every league answered, the count is just low. That is a warning, as it
     always was -- it is what a stub or a mid-season data oddity looks like, and it is NOT the
     2026-09-20 failure, which was leagues not answering at all. Refusing on thinness alone would
     make the tool untestable without pinning all 96 clubs. */
  if (n < 80) console.error(`::warning::only ${n} eligible clubs resolved (expected ~96) -- gate may be thin`);

  const rows = await scan(date, top5);
  const admit = rows.filter(r => r.admit);

  if (asJson) { console.log(JSON.stringify({ date, eligible_clubs: n, fixtures: rows }, null, 1)); return; }

  console.log(`${date} -- ${rows.length} fixture(s) across ${slugs(COV.core).length + slugs(COV.open).length + slugs(COV.gated).length} competitions, ${n} eligible clubs`);
  if (!admit.length) console.log('  NOTHING ADMISSIBLE -- no board today');
  const by = {};
  for (const r of admit) (by[r.league] = by[r.league] || []).push(r);
  for (const lg of Object.keys(by)) {
    console.log(`  ${lg} (${by[lg].length})`);
    for (const r of by[lg]) console.log(`    ${r.kickoffZ}Z  ${r.name}   [${r.why}]  ${r.espn[0]}:${r.id}`);
  }
  if (showAll) for (const r of rows.filter(x => !x.admit))
    console.log(`  DROP  ${r.kickoffZ}Z  ${r.league}  ${r.name}   ${r.why}`);
  console.log(`  => ${admit.length} admissible`);
})();
