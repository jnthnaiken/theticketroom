/* nfl_draft_cli.js -- the server entry point for a first build.
 *     node nfl_draft_cli.js scored.json fixtures.json tickets.json
 *
 * ⚠️ THIS FILE DOES NOT CONTAIN A DRAFT. It configures soccer_draft.js and calls it.
 *
 * WHY REUSE AND NOT FORK. soccer_draft.js is already "one implementation, two callers"
 * (STAGE2-2026-08-27) and it is pure -- no DOM, no fetch, no clock -- with the whole shape
 * exposed as config: WIN, Z_GATE, GAME_CAP, ANCH, MOON_LEGS, MOONS_PER_ANC, ANCH_PER_GAME.
 * Nothing in the pool gate, the snake draft, the pairing rule or `redraft()` knows what sport it
 * is. Forking 75KB to change five numbers would give this project a THIRD copy of every guard we
 * have argued about this month -- CONFLOCK, MINTGUARD, the all-or-none pairing, the anchor cap --
 * and the soccer/MLB pair has already shown what happens when two copies drift: assemble_tickets
 * sat two board redesigns behind client_assemble because nobody noticed a silent fallback.
 * One draft, three sports. A fix lands once.
 *
 * WHAT IS ACTUALLY DIFFERENT ABOUT FOOTBALL, and it is only these:
 *
 *   WIN=60. NFL kicks off in WAVES, not on a rolling schedule: 13:00 (8 games), 16:25 (4) and
 *   20:20 (1) ET. Inside a wave the span between legs is ZERO, so a 3-leg moon is trivially
 *   in-window; across waves it is 205 minutes and must never be one slip. 60 keeps each moon
 *   inside a single wave, which is also the only span over which the inactives report -- 90
 *   minutes before kickoff -- resolves for every leg at once. That is the same reasoning that
 *   put soccer on 60 (WIN60-2026-08-29, team sheets an hour out), arrived at independently.
 *
 *   ⚠️ THE 20:20 GAME CANNOT FIELD A MOON. One game in the wave, and MOON_LEGS=3 requires three
 *   DISTINCT games. Its players are eligible as singles only. That is not a bug to route around;
 *   it is the same structural fact the 2-match soccer slate hit on 2026-09-03.
 *
 *   GAME_CAP=5. An NFL roster puts more plausible scorers on a card than a soccer XI does -- the
 *   market prices 15 a game -- so 4 would leave real bats unpooled.
 *
 *   Z_GATE=0.55. Set against the measured pool, not copied. See the tuning note in nfl_mock.py.
 */
'use strict';
const fs = require('fs');

/* soccer_draft.js prefers module.exports under node and only falls back to a global in a
   browser: `if (typeof module !== 'undefined' && module.exports) module.exports = api;`
   So take the require() value and accept the global only as the browser path. */
const Draft = require('./soccer_draft.js') || globalThis.SoccerDraft;
if (!Draft || !Draft.draft) { console.error('!! soccer_draft.js exported no draft()'); process.exit(3); }

/* The vocabulary is the ONLY cosmetic fork. NAMES/BADGE are exported on the api object precisely
   so a second sport can re-point them without touching the draft. */
Draft.NAMES.moon = ['Six Points', 'Money Down', 'The Pylon', 'Front of the End Zone', 'Play Action',
                    'Goal to Go', 'The Fade', 'Crossing Route', 'Chunk Play', 'Twelve Personnel',
                    'Empty Backfield', 'The Rollout'];
Draft.NAMES.builder = ['The Workhorse', 'Bell Cow', 'Goal Line Back', 'Red Zone Target',
                       'Short Yardage', 'The Checkdown', 'First Read', 'Move the Chains',
                       'Inside the Ten', 'The Sneak'];
Draft.NAMES.lunch = ['The One O’Clock', 'Early Window', 'First Wave', 'Sunday Opener'];
Draft.NAMES.late  = ['Sunday Night', 'Under Lights', 'Prime Time', 'The Late Window'];
Draft.BADGE.moon = '🏈';        /* 🏈 -- the soccer fork re-skins 🚀 -> 💥, same seam */

const CFG = {
  WIN: 60, Z_GATE: 0.55, GAME_CAP: 5,
  ANCH: 4, MOON_LEGS: 3, MOONS_PER_ANC: 2, ANCH_PER_GAME: 2,
  MOON_RISK: 2.0, SINGLE_STAKE: 1.0,
};

const [, , scoredPath, fixturesPath, outPath] = process.argv;
if (!scoredPath || !fixturesPath || !outPath) {
  console.error('usage: node nfl_draft_cli.js scored.json fixtures.json tickets.json');
  process.exit(2);
}
const players = JSON.parse(fs.readFileSync(scoredPath, 'utf8'));
const fx = JSON.parse(fs.readFileSync(fixturesPath, 'utf8'));

/* Kickoff minutes per MATCH.
   ⚠️ THE FIELD MUST BE `kickoff`. spanOk() reads `l.kickoff` and nothing else. The first cut set
   `p.ko` instead, and the failure was SILENT AND INVERTED: with every kickoff undefined, spanOk's
   `lo` stays Infinity and `hi` stays -Infinity, so `hi - lo` is -Infinity and `-Infinity <= WIN`
   is TRUE. The guard did not reject everything and blow up -- it ACCEPTED everything and shipped
   a board with Derrick Henry (13:00) beside Ashton Jeanty (16:25) and a 20:20 bat on a slip with
   two one-o'clock games. A missing field that makes a constraint vacuously true is worse than one
   that crashes, so it is asserted below rather than trusted. */
const KO = {};
Object.keys(fx.matches).forEach(k => { KO[k] = fx.matches[k].kickoff; });
players.forEach(p => { p.kickoff = KO[p.match]; });
const noKO = players.filter(p => typeof p.kickoff !== 'number');
if (noKO.length) {
  console.error(`!! ${noKO.length} priced players have no kickoff -- spanOk would pass vacuously. `
              + `First: ${noKO.slice(0, 3).map(p => p.name + '/' + p.match).join(', ')}`);
  process.exit(5);
}

const res = Draft.draft(players, CFG, { koOf: m => KO[m], slateMatches: Object.keys(fx.matches).length });

/* THE TWO SINGLES. soccer_draft.draft() returns moons + anchor builders and nothing else --
   the lunch/nightcap slots are minted downstream in both existing rooms. Football's equivalents
   are the EARLY WINDOW (first kickoff wave) and SUNDAY NIGHT (the last), and the 20:20 game
   matters here beyond garnish: it is the one game that structurally CANNOT field a moon, so
   without this its whole card is unrepresented on the board. Best free bat in each wave, never
   one already on a slip. */
(function () {
  const used = new Set();
  res.tickets.forEach(t => t.legs.forEach(l => used.add(l.name)));
  const waveOf = m => KO[m];
  const first = Math.min(...Object.values(KO)), last = Math.max(...Object.values(KO));
  [['lunch', first], ['late', last]].forEach(([kind, wave]) => {
    if (wave === first && wave === last) return;          // single-wave slate: no split to make
    const cand = res.byStrength.filter(p => waveOf(p.match) === wave && !used.has(p.name));
    if (!cand.length) { console.log(`no free bat in the ${kind} wave -- slot left empty`); return; }
    const pick = cand[0];
    used.add(pick.name);
    res.tickets.push({ kind, legs: [pick], risk: CFG.SINGLE_STAKE });
    console.log(`${kind}: ${pick.name} (${pick.odds > 0 ? '+' : ''}${pick.odds})`);
  });
})();

const waves = {};
Object.keys(KO).forEach(k => { waves[KO[k]] = (waves[KO[k]] || 0) + 1; });
console.log(`pool ${res.pool.length} of ${players.length} priced  |  anchors ${res.anchors}/${res.budget}`
          + (res.thin ? '  ⚠️ THIN' : '') + (res.singlesOnly ? '  (singles only)' : ''));
console.log('kickoff waves: ' + Object.keys(waves).sort((a, b) => a - b)
              .map(m => `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')} x${waves[m]}`).join('  '));

const out = res.tickets.map((t, i) => ({
  kind: t.kind,
  name: t.name || Draft.NAMES[t.kind][i % Draft.NAMES[t.kind].length],
  badge: Draft.BADGE[t.kind],
  anchor: t.legs[0].name,
  match: t.legs[0].match,
  risk: t.risk,
  legs: t.legs.map(l => ({ name: l.name, team: l.team, match: l.match, odds: l.odds,
                           TOTAL: l.TOTAL, pos: l.pos })),
}));
fs.writeFileSync(outPath, JSON.stringify(out, null, 1));

/* Post-condition, not a hope: every emitted multi-leg slip is inside WIN. */
let bad = 0;
out.forEach(t => {
  if (t.legs.length < 2) return;
  const ks = t.legs.map(l => KO[l.match]);
  const span = Math.max.apply(null, ks) - Math.min.apply(null, ks);
  if (span > CFG.WIN) { bad++; console.error(`!! ${t.name} spans ${span} min > WIN ${CFG.WIN}`); }
});
if (bad) { console.error(`!! ${bad} slip(s) violate the game-time window`); process.exit(6); }

const byKind = {};
out.forEach(t => { byKind[t.kind] = (byKind[t.kind] || 0) + 1; });
console.log(`tickets ${out.length}  ${JSON.stringify(byKind)}`);
out.forEach(t => console.log(`  ${(t.kind + '       ').slice(0, 8)} ${(t.name + '                     ').slice(0, 22)}`
  + t.legs.map(l => `${l.name} (${l.odds > 0 ? '+' : ''}${l.odds})`).join('  +  ')));
