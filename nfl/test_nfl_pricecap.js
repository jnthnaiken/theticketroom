/* test_nfl_pricecap.js -- PRICECAP-2026-09-15.
 * The football draft never seats a man longer than MAX_ODDS; soccer (MAX_ODDS null) is untouched.
 *     node test_nfl_pricecap.js
 */
'use strict';
const assert = require('assert');
const path = require('path');
const Draft = require(path.join(__dirname, '..', 'soccer', 'soccer_draft.js'));

const cfgNfl = Draft.cfgOf({ MAX_ODDS: 500, MIN_ODDS: 100 });   /* FLOOR200: NFL pins +100 */
const cfgSoc = Draft.cfgOf({});

assert.strictEqual(cfgSoc.MAX_ODDS, null, 'soccer default must stay uncapped');
assert.strictEqual(Draft.priceOk({ odds: 2200 }, cfgSoc), true, 'soccer: +2200 still eligible');
assert.strictEqual(Draft.priceOk({ odds: -110 }, cfgSoc), true, 'soccer: -110 is inside the -200 floor (FLOOR200)');
assert.strictEqual(Draft.priceOk({ odds: -250 }, cfgSoc), false, 'soccer: MIN_ODDS -200 still applies');

assert.strictEqual(Draft.priceOk({ odds: 500 }, cfgNfl), true, 'nfl: +500 is inside the band');
assert.strictEqual(Draft.priceOk({ odds: 501 }, cfgNfl), false, 'nfl: +501 is out');
assert.strictEqual(Draft.priceOk({ odds: 100 }, cfgNfl), true, 'nfl: evens is in');
assert.strictEqual(Draft.priceOk({ odds: -120 }, cfgNfl), false, 'nfl: minus money still out');
assert.strictEqual(Draft.priceOk({ odds: null }, cfgNfl), false, 'nfl: unpriced never drafts');

/* End to end: a slate whose best-scored men are all longshots drafts none of them. */
const players = [];
const matches = ['a', 'b', 'c', 'd'];
matches.forEach((m, gi) => {
  for (let i = 0; i < 6; i++) {
    const long = i < 2;
    players.push({
      name: `${m}${i}`, match: m, team: `${m.toUpperCase()}${i % 2}`, pos: 'WR',
      odds: long ? 1200 + 100 * i : 250 + 40 * i,
      TOTAL: long ? 190 - i : 140 - i, blend: long ? 3 - i * 0.1 : 1.2 - i * 0.05,
      gate_z: long ? 2.5 : 0.9 - i * 0.02, kickoff: 780, out: false, void: false,
    });
  }
});
const res = Draft.draft(players, Draft.cfgOf({ WIN: 60, Z_GATE: 0.55, GAME_CAP: 5, MAX_ODDS: 500, MIN_ODDS: 100 }),
                        { koOf: () => 780, slateMatches: matches.length });
const legs = res.tickets.flatMap(t => t.legs);
assert.ok(legs.length > 0, 'the capped slate still drafts');
legs.forEach(l => assert.ok(l.odds <= 500, `${l.name} +${l.odds} got past the cap`));
console.log(`PASS test_nfl_pricecap -- ${res.tickets.length} tickets, longest leg +${Math.max(...legs.map(l => l.odds))}`);
