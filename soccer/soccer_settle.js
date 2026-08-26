#!/usr/bin/env node
/* soccer_settle.js -- settle a finished soccer board from the REAL ESPN feed, headlessly.
 *
 *     node soccer_settle.js <D.json> [--force]
 *
 * WHY THIS EXISTS. The published board settles itself in the browser: soccer_live.js runs every
 * three minutes, writes finals/hr/goalmins/status into the in-page `D`, and index.html grades
 * tonight live off D.tickets. All of that is per-tab and dies with the tab. NOTHING wrote the
 * night into soccer_season.json, which is why 2026-08-25 was still missing from the ledger a day
 * later while the board had been showing its own result correctly the whole time.
 *
 * ⚠️ IT RUNS soccer_live.js ITSELF -- the same module the page runs, required, not reimplemented.
 * A second settlement implementation is the assemble_tickets.py mistake: two copies of one rule
 * set, drifting, disagreeing about the same night. If the goal vocabulary or the surname anchor
 * changes, it changes in ONE file and both the page and this script get it.
 *
 * WHAT IT DOES NOT DO. It does not grade and it does not touch season.json -- soccer_grade.py
 * does that, and only when this script says the night is COMPLETE. That split is the whole point
 * of the exit code below.
 *
 * EXIT CODES (the workflow branches on these -- they are the interface):
 *     0   every match on the board is final. Safe to fold.
 *    20   the board settled cleanly but NOT every match is final yet. DO NOT FOLD.
 *    30   no board, or no results feed wired (D.meta.espn missing).
 *
 * ⚠️ 20 IS NOT AN ERROR AND MUST NOT BE TREATED AS ONE. soccer_grade.fold() marks the date in
 * `graded_nights` as soon as it runs, and grade_ticket() returns None for a ticket whose match is
 * still open -- so folding a half-final night SILENTLY DROPS every unsettled ticket and can never
 * be redone. A late kickoff, extra time or a penalty shootout is a normal reason to come back in
 * an hour, not a reason to settle what you have.
 *
 * --force folds anyway. It exists for a match that will never go final (abandoned, postponed off
 * the slate) and it is a decision a person makes, having looked. It is not a retry.
 */
const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const FORCE = args.includes('--force');
const DPATH = args.filter(a => !a.startsWith('--'))[0];
if (!DPATH) { console.error('usage: soccer_settle.js <D.json> [--force]'); process.exit(2); }

const L = require(path.join(__dirname, 'soccer_live.js'));
const D = JSON.parse(fs.readFileSync(DPATH, 'utf8'));

const EV = (D.meta && D.meta.espn) || {};
const total = Object.keys(EV).length;
if (!total) { console.log('SETTLE  no results feed wired (D.meta.espn empty)'); process.exit(30); }

/* One shared fetch, so a flaky league is visible rather than silently swallowed. soccer_live.js
   catches per-league failures on purpose (a page must not blank the board because one feed
   blipped); here we want the count, because "0 of 5 final" caused by a network fault reads
   identically to "0 of 5 final" caused by matches not having kicked off yet. */
let calls = 0, failed = 0;
function fetchJSON(u) {
  calls++;
  return fetch(u, { headers: { 'cache-control': 'no-store' } }).then(r => {
    if (!r.ok) throw new Error('http ' + r.status);
    return r.json();
  }).catch(e => { failed++; throw e; });
}

const live = L.makeLive({
  D: D,
  fetchJSON: fetchJSON,
  stamp: () => {},
  render: () => {}
});

live.run().then(() => {
  const finals = (D.meta.finals || []).slice().sort((a, b) => a - b);
  const complete = finals.length === total;

  fs.writeFileSync(DPATH, JSON.stringify(D, null, 1), 'utf8');

  const scorers = Object.keys(D.players)
    .filter(n => D.players[n].hr)
    .map(n => n + (D.players[n].goalmins || []).map(m => ' ' + m + "'").join(''));

  console.log(`SETTLE  ${D.meta.date}  ${finals.length}/${total} final` +
              `  ${calls} feed calls, ${failed} failed`);
  console.log('        results  ' + JSON.stringify(D.meta.results || {}));
  console.log('        scorers  ' + (scorers.length ? scorers.join(' · ') : '(none on the board)'));

  if (calls && failed === calls) {
    /* Nothing was learned this pass. Exiting 0 here would let a total outage look like a
       settled night whenever the board already carried finals from an earlier pass -- the
       fold would then run against stale data and mark the date done forever. */
    console.log('SETTLE  every feed call failed -- nothing learned this pass, not folding');
    process.exit(30);
  }
  if (failed && !complete) {
    /* Do not let a network fault masquerade as "matches still running". */
    console.log('        ⚠ some feeds failed this pass -- the final count is not trustworthy');
  }
  if (complete) { console.log('SETTLE  complete -- safe to fold'); process.exit(0); }
  if (FORCE)    { console.log('SETTLE  INCOMPLETE but --force given -- folding anyway'); process.exit(0); }
  console.log('SETTLE  incomplete -- not folding (this is normal; come back later)');
  process.exit(20);
}).catch(e => {
  console.error('SETTLE  failed: ' + (e && e.message));
  process.exit(30);
});
