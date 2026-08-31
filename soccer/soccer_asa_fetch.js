#!/usr/bin/env node
/* soccer_asa_fetch.js -- pull an MLS season from American Soccer Analysis into xg.psv rows.
 * ASAXG-2026-08-31.
 *
 *     node soccer_asa_fetch.js <season> <out.psv> [--json raw.json]
 *     node soccer_asa_fetch.js 2026 mls_xg.psv
 *
 * This is the THIN NETWORK SHELL. Every decision that can be wrong about the numbers lives in
 * soccer_asa.js, which has no network in it and is tested against a pinned capture
 * (test_asa.js / fixtures/asa-2026-08-31.json). Keep it that way: anything added here is
 * untestable in the build container, which has GitHub-only egress.
 *
 * ⚠️ THE NETWORK PATH IS UNVERIFIED FROM THE BUILD CONTAINER, and that is stated rather than
 * glossed. ASA was confirmed reachable and correct FROM A BROWSER on 2026-08-31; this container
 * cannot reach it to prove the same, and whether the GitHub Actions runner can is unknown -- the
 * runner reaches ESPN but not understat or oddschecker (see soccer_teamnews_fetch.js). So the
 * supported flow today is the one every other slate input already uses: run this where it CAN
 * reach ASA, commit the PSV into soccer/slates/<date>/. If a runner turns out to reach ASA, this
 * file is already shaped to be called from the workflow -- but do not wire that until a real run
 * proves it, and treat exit 30 as "no xG for MLS tonight", never as a build failure.
 *
 * EXIT CODES, matching soccer_teamnews_fetch.js's convention:
 *     0   rows written
 *     2   usage
 *     20  reached ASA but it returned nothing for that season
 *     30  could not reach ASA at all -- the caller should carry on WITHOUT MLS xG, which is a
 *         degraded board (market term only for those players), not a broken one
 */
const fs = require('fs');
const SA = require('./soccer_asa.js');

const BASE = 'https://app.americansocceranalysis.com/api/v1/mls/';
const BATCH = 300;                 /* player_id batches; 300 is comfortable, 805 in one is not */

const [, , season, outPath, ...rest] = process.argv;
if (!season || !outPath) {
  console.error('usage: soccer_asa_fetch.js <season> <out.psv> [--json raw.json]');
  process.exit(2);
}
const jsonAt = rest.indexOf('--json');
const rawPath = jsonAt >= 0 ? rest[jsonAt + 1] : null;

async function getJSON(url) {
  const r = await fetch(url, { headers: { accept: 'application/json' } });
  if (!r.ok) throw new Error(url.replace(BASE, '') + ' -> HTTP ' + r.status);
  return r.json();
}

(async () => {
  let all, pen, teams, players = [];
  try {
    all = await getJSON(BASE + 'players/xgoals?season_name=' + encodeURIComponent(season));
    /* 🚨 PENALTIES ONLY, and NOT shot_pattern=Regular. ASA's `xgoals` includes penalties, so npxG
       is a subtraction -- see the header of soccer_asa.js. `Regular` also returns 200 but means
       OPEN PLAY, dropping set pieces and corners too, which would understate every target man. */
    pen = await getJSON(BASE + 'players/xgoals?season_name=' + encodeURIComponent(season)
                        + '&shot_pattern=Penalty');
    teams = await getJSON(BASE + 'teams');
    const ids = [...new Set((all || []).map(r => r.player_id))];
    for (let i = 0; i < ids.length; i += BATCH) {
      players = players.concat(await getJSON(BASE + 'players?player_id=' + ids.slice(i, i + BATCH).join(',')));
    }
  } catch (e) {
    console.error('!! ASA unreachable or refusing: ' + e.message);
    console.error('   The board can still be built -- those players score on the market term');
    console.error('   alone (has_xg=False). Do not fail the build on this.');
    process.exit(30);
  }

  if (!Array.isArray(all) || !all.length) {
    console.error(`!! ASA returned no players for season ${season}. Check the season name before`);
    console.error('   assuming the API broke -- it takes the calendar year, e.g. 2026.');
    process.exit(20);
  }

  const payload = {
    season: String(season),
    all: all,
    pen: (pen || []).filter(r => r.shots > 0),      /* only the rows that carry a penalty */
    players: players,
    teams: teams
  };
  if (rawPath) fs.writeFileSync(rawPath, JSON.stringify(payload));

  const { rows, skipped } = SA.rows(payload);
  fs.writeFileSync(outPath, SA.toPSV(rows));

  const withPen = payload.pen.length;
  const withXg = rows.filter(r => r.npxg > 0).length;
  console.log(`  ASA ${season}: ${rows.length} players -> ${outPath}`);
  console.log(`  ${withPen} with penalties (subtracted out of npxG), ${withXg} with non-zero npxG`);
  if (skipped.length) {
    console.log(`  ::warning::${skipped.length} priced by ASA but unnameable, dropped: `
                + skipped.slice(0, 5).join(', '));
  }
})();
