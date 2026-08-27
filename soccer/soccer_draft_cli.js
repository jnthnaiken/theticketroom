#!/usr/bin/env node
/* soccer_draft_cli.js -- run THE draft server-side, from Python.
 *
 * This is the soccer equivalent of client_assemble.js. regen15.py exists in the shape it does
 * because of one lesson the baseball board paid for twice: if the archive is drafted by
 * different code from the screen, the two diverge and the ledger books a board nobody saw.
 * soccer_mock.py used to own a second copy of the draft in Python; now it shells out to here,
 * so the baked soccer_D.json and the live re-draft come from the same file.
 *
 *   node soccer_draft_cli.js <scored.json> <out tickets.json> [teamnews.json]
 *
 * teamnews.json is OPTIONAL and the distinction matters: absent means "no team news on hand"
 * and the draft runs over the whole priced field; present-but-empty would filter the pool to
 * nothing and mint an empty board. If the file is there but carries no XI, this exits non-zero
 * rather than quietly shipping nothing.
 */
const fs = require('fs');
const SD = require('./soccer_draft.js');

const [, , scoredPath, outPath, tnPath] = process.argv;
if (!scoredPath || !outPath) {
  console.error('usage: soccer_draft_cli.js <scored.json> <tickets.json> [teamnews.json]');
  process.exit(2);
}

const scored = JSON.parse(fs.readFileSync(scoredPath, 'utf8'));

let xi = null;
if (tnPath) {
  const tn = JSON.parse(fs.readFileSync(tnPath, 'utf8'));
  const keys = Object.keys(tn.xi || {});
  if (!keys.length) {
    console.error('!! teamnews.json is present but carries an EMPTY xi. That filters the pool to\n' +
                  '   nothing and mints an empty board. Either the ESPN pull ran before the team\n' +
                  '   sheets were published, or the join broke. Refusing to draft.');
    process.exit(3);
  }
  xi = SD.nameSet(keys);
  console.log(`  team news: drafting from ${keys.length} confirmed starters`);
} else {
  console.log('  team news: none supplied -- drafting from the whole priced field');
}

const res = SD.draft(scored, {}, { xi });
if (res.thin) {
  console.log(`  thin slate: ${res.budget} anchors do not fit; drafted ${res.anchors}`);
}
console.log(`  pool after Z_GATE ${SD.DEFAULTS.Z_GATE} + XI filter + GAME_CAP ${SD.DEFAULTS.GAME_CAP}: ${res.pool.length}`);

const out = res.tickets.map(t => ({
  kind: t.kind,
  risk: t.risk,
  legs: t.legs.map(l => ({
    name: l.name, odds: l.odds, match: l.match,
    TOTAL: Math.round(l.TOTAL * 10) / 10
  }))
}));
fs.writeFileSync(outPath, JSON.stringify(out, null, 1));

const kinds = {};
out.forEach(t => { kinds[t.kind] = (kinds[t.kind] || 0) + 1; });
console.log(`  TICKETS: ${JSON.stringify(kinds)}   total staked ${out.reduce((s, t) => s + t.risk, 0).toFixed(1)}u`);
out.filter(t => t.kind === 'moon').forEach(t => {
  console.log(`    💥 screamer  ${t.legs.map(l => `${l.name} (${l.odds > 0 ? '+' : ''}${l.odds})`).join(' + ')}`);
});
out.filter(t => t.kind === 'builder').forEach(t => {
  console.log(`    ⚓️ anchor    ${t.legs[0].name} (${t.legs[0].odds > 0 ? '+' : ''}${t.legs[0].odds})`);
});
