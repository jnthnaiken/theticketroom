#!/usr/bin/env node
/* test_slatescan.js -- RANGEDEAD-2026-09-21.
 *
 * WHY. slate_scan.js exists because "is there a soccer board today?" was answered from memory and
 * was wrong three times in an hour. On 2026-09-20 it answered the same question wrong itself, on a
 * 21-fixture Sunday:
 *
 *     2026-09-20 -- 0 fixture(s) across 15 competitions, 0 eligible clubs
 *       NOTHING ADMISSIBLE -- no board today
 *
 * `eligibleClubs()` asked each core league's SCOREBOARD over a season-wide window, and ESPN now
 * returns 400 for any date RANGE. Every core league failed, the gate came back empty, and the
 * summary line reported that as a finding. The tool did not crash; it lied.
 *
 * So the two things under test are the fix AND the refusal:
 *   1. the gate is built from /{slug}/teams and resolves 96 clubs
 *   2. a real empty day still says NOTHING ADMISSIBLE -- that answer must stay reachable
 *   3. a BROKEN gate exits non-zero and NEVER prints NOTHING ADMISSIBLE
 *   4. a PARTIALLY broken gate is also a refusal -- 78 clubs is not "nearly right", it silently
 *      drops a whole league's cup ties for want of a top-five side
 *
 * The container cannot reach ESPN, so `fetch` is stubbed. That is the point: these are the
 * failure modes, and they are not reproducible against a working network.
 *
 *     node test_slatescan.js
 */
'use strict';
const { execFileSync } = require('child_process');
const path = require('path');

const SCAN = path.join(__dirname, 'slate_scan.js');
const CORE = { 'eng.1': 20, 'esp.1': 20, 'ita.1': 20, 'ger.1': 18, 'fra.1': 18 };

let fail = 0;
function chk(label, ok, detail) {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`);
  if (!ok) { fail++; if (detail !== undefined) console.log('      ' + String(detail).slice(0, 400)); }
}

/* Run slate_scan with a stubbed global fetch. The plan travels in an env var and the harness
   lives in its own file rather than a -e string: escaping a fetch stub through two levels of
   template literal is how the first cut of this test failed to compile, which looks exactly like
   a failing assertion. */
const HARNESS = path.join(require('os').tmpdir(), 'slatescan_harness.js');
require('fs').writeFileSync(HARNESS, `
'use strict';
const PLAN = JSON.parse(process.env.PLAN);
const CORE = JSON.parse(process.env.CORE);
const SCAN = process.env.SCAN;
let seq = 0;
function teamsPayload(slug) {
  const n = CORE[slug] || 0, arr = [];
  for (let i = 0; i < n; i++) arr.push({ team: { id: slug + '-' + i, displayName: slug + ' club ' + i } });
  return { sports: [{ leagues: [{ teams: arr }] }] };
}
globalThis.fetch = async function (url) {
  const tm = /\\/([a-z0-9._]+)\\/teams$/.exec(url);
  if (tm) {
    const slug = tm[1];
    if ((PLAN.deadTeams || []).indexOf(slug) >= 0) return { ok: false, status: 400, json: async () => ({}) };
    if ((PLAN.emptyTeams || []).indexOf(slug) >= 0)
      return { ok: true, status: 200, json: async () => ({ sports: [{ leagues: [{ teams: [] }] }] }) };
    return { ok: true, status: 200, json: async () => teamsPayload(slug) };
  }
  if (/scoreboard\\?dates=\\d{8}-\\d{8}/.test(url)) return { ok: false, status: 400, json: async () => ({}) };
  const sb = /\\/([a-z0-9._]+)\\/scoreboard/.exec(url);
  const slug = sb ? sb[1] : '';
  const list = (PLAN.fixtures || {})[slug] || [];
  const events = list.map(function (e) {
    seq++;
    return {
      id: 'ev' + seq, name: e.name, shortName: e.name,
      date: '2026-09-20T' + e.z + ':00Z',
      status: { type: { name: 'STATUS_SCHEDULED' } },
      competitions: [{ competitors: (e.ids || []).map(function (id) { return { team: { id: id } }; }) }]
    };
  });
  return { ok: true, status: 200, json: async () => ({ events: events }) };
};
process.argv = ['node', SCAN].concat(JSON.parse(process.env.ARGS));
require(SCAN);
`);

function run(date, plan, extraArgs) {
  const env = Object.assign({}, process.env, {
    PLAN: JSON.stringify(plan || {}), CORE: JSON.stringify(CORE), SCAN: SCAN,
    ARGS: JSON.stringify([date].concat(extraArgs || [])),
  });
  try {
    const out = execFileSync(process.execPath, [HARNESS], { encoding: 'utf8', env, stdio: ['ignore', 'pipe', 'pipe'] });
    return { code: 0, out, err: '' };
  } catch (e) {
    return { code: e.status == null ? -1 : e.status, out: String(e.stdout || ''), err: String(e.stderr || '') };
  }
}

/* 1 -- the fix: the gate resolves off /teams, and a real card is reported. */
{
  const r = run('2026-09-20', { fixtures: { 'eng.1': [{ name: 'Fulham v Manchester United', z: '15:30', ids: ['eng.1-0', 'eng.1-1'] }] } });
  chk('healthy gate resolves 96 clubs from /teams', /96 eligible clubs/.test(r.out), r.out + r.err);
  chk('a core fixture is reported', /Fulham v Manchester United/.test(r.out), r.out);
  chk('exit 0', r.code === 0, r.code);
}

/* 2 -- a genuinely empty day must still be sayable. This is 2026-09-21. */
{
  const r = run('2026-09-21', { fixtures: {} });
  chk('a real empty day still says NOTHING ADMISSIBLE', /NOTHING ADMISSIBLE/.test(r.out), r.out + r.err);
  chk('...and exits 0, because that is a finding', r.code === 0, r.code);
}

/* 3 -- THE 2026-09-20 CASE. Gate dead, fixtures present. Must refuse, must not report. */
{
  const r = run('2026-09-20', {
    deadTeams: Object.keys(CORE),
    fixtures: { 'eng.1': [{ name: 'Fulham v Manchester United', z: '15:30', ids: ['eng.1-0', 'eng.1-1'] }] },
  });
  chk('broken gate never prints NOTHING ADMISSIBLE', !/NOTHING ADMISSIBLE/.test(r.out), r.out);
  chk('broken gate never prints a fixture count line', !/fixture\(s\) across/.test(r.out), r.out);
  chk('broken gate exits 3', r.code === 3, r.code + ' :: ' + r.err.slice(0, 200));
  chk('broken gate says so on stderr', /eligible-club scan FAILED/.test(r.err), r.err);
}

/* 4 -- one league silently returning nothing is also a refusal, not a 78-club near-miss. */
{
  const r = run('2026-09-20', { emptyTeams: ['ger.1'], fixtures: {} });
  chk('a partially resolved gate is also refused', r.code === 3, r.code);
  chk('...and names the league that did not answer', /ger\.1/.test(r.err), r.err);
}

console.log('');
if (fail) { console.error(`${fail} FAILED`); process.exit(1); }
console.log('ALL GREEN -- the gate builds off /teams, and a broken gate refuses instead of reporting');
