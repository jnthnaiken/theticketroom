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

let xi = null, xiMatches = null;
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

  /* 🚨 XIPARTIALCOLD-2026-09-05 -- THE COLD DRAFT NEVER PASSED xiMatches.
     buildPool() has taken a per-match `xiMatches` since XIPARTIAL-2026-08-28 and warns in as many
     words: "Omit `xiMatches` and the old all-or-nothing behaviour is exactly preserved." This file
     omitted it. soccer_rebuild_cli.js -- the LIVE path -- builds and passes it, so the per-match
     rule was live on every redraft and absent from every FIRST build of a slate, the one pass with
     no prior board behind it.
     On a staggered card, once any sheet publishes every player whose own match has not published
     is filtered out slate-wide. Football XIs land ~1h before kickoff, so the cold draft could only
     ever see the earliest matches. Measured 2026-09-05 (21 matches, 12 sheets out, 9 not): 52
     gated men, 12 admitted; per-match admits 39. The 27 discarded were the top of the board --
     Harry Kane at gate_z +5.21, the highest on the slate, Donyell Malen +3.83, Lautaro Martinez,
     Mikautadze, Olise -- all in later, still-open kickoffs. It anchored gate_z +1.51 instead,
     because that man's sheet had landed. BOTH halves are required: soccer_mock.py's own pool gate
     had the same flat filter (XIPARTIALMOCK-2026-09-05) and either one alone still excludes them.
     `trusted` is per match; absent (older files) -> derive from the matches carrying any
     classified player, never `{}`, which would mean "nothing published" and re-disable it. */
  const TRUST = tn.trusted || {};
  xiMatches = {};
  Object.keys(TRUST).forEach(m => { if (TRUST[m] !== false) xiMatches[m] = true; });
  if (!Object.keys(xiMatches).length) {
    [tn.xi, tn.bench, tn.absent].forEach(o => Object.values(o || {}).forEach(m => { if (m) xiMatches[m] = true; }));
  }
  console.log(`  team news: ${keys.length} confirmed starters across ` +
              `${Object.keys(xiMatches).length} published sheet(s); matches without one stay draftable`);
} else {
  console.log('  team news: none supplied -- drafting from the whole priced field');
}

const res = SD.draft(scored, {}, { xi, xiMatches });
if (res.singlesOnly) {
  console.log(`  ${res.matches} match(es) on the slate and a screamer needs ${SD.DEFAULTS.MOON_LEGS} ` +
              `from different matches -- ANCHOR SINGLES ONLY (SINGLES-2026-08-27)`);
}
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
