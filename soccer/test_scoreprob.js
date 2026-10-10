/* test_scoreprob.js -- SCOREPROB-2026-10-10: the conviction line.
   A player carrying `pscore` is draftable only at pscore >= DEFAULTS.MIN_P, and for him the line
   REPLACES the -200 floor. A player with no pscore (any board built before the change, and NFL)
   keeps the old floor exactly -- and the old eight-a-night ceiling (NOCAP8-2026-10-10). */
const SD = require('./soccer_draft.js');
let bad = 0;
const chk = (m, c) => { console.log((c ? 'ok   ' : 'FAIL ') + m); if (!c) bad++; };
const C = SD.cfgOf({});
chk('DEFAULTS.MIN_P is 0.45', C.MIN_P === 0.45);
chk('pscore 0.62 at -250 is in (the line replaces the floor)', SD.priceOk({ odds: -250, pscore: 0.62 }, C));
chk('pscore 0.44 at +130 is out (below the line)', !SD.priceOk({ odds: 130, pscore: 0.44 }, C));
chk('pscore 0.45 at +120 is in (the line is inclusive)', SD.priceOk({ odds: 120, pscore: 0.45 }, C));
chk('pscore present but no price is out', !SD.priceOk({ odds: null, pscore: 0.7 }, C));
chk('NO pscore at -250 is out (old floor intact)', !SD.priceOk({ odds: -250 }, C));
chk('NO pscore at +300 is in (old rules: a +300 starter was draftable)', SD.priceOk({ odds: 300 }, C));
chk('MIN_P null switches it off (pscore 0.30 at +250 back on old rules)', SD.priceOk({ odds: 250, pscore: 0.30 }, SD.cfgOf({ MIN_P: null })));
const N = require('../nfl/nfl_cfg.js').CFG;
chk('NFL pins MIN_P null', N.MIN_P === null);
/* NOCAP8-2026-10-10: under the line there is no nightly ceiling -- the card is everyone who clears it. */
{
  const fs = require('fs');
  const scored = JSON.parse(fs.readFileSync(__dirname + '/fixtures/2026-08-26/scored.json', 'utf8'));
  const matches = [...new Set(scored.map(p => p.match))];
  // give every priced man a pscore of 0.5: the card must be 2 per match, not 8
  const withP = scored.map(p => Object.assign({}, p, { pscore: p.odds != null ? 0.5 : null }));
  const r = SD.draft(withP, {}, {});
  const b = r.tickets.filter(t => t.kind === 'builder');
  const per = {}; b.forEach(t => per[t.legs[0].match] = (per[t.legs[0].match] || 0) + 1);
  const want = matches.reduce((a, m) => a + Math.min(2, withP.filter(p => p.match === m && SD.priceOk(p, SD.DEFAULTS) && !p.out && !p.void).length), 0);
  chk(`pscore card has no ceiling: ${b.length} picks = 2 a match over ${matches.length} matches (${want})`, b.length === want && b.length > 8);
  chk('per-match cap still holds', Object.values(per).every(v => v <= 2));
  const noP = SD.draft(scored, {}, {});
  chk('a field with no pscore still drafts TOP_SINGLES (8)', noP.tickets.filter(t => t.kind === 'builder').length === SD.DEFAULTS.TOP_SINGLES);
}
console.log(bad ? `${bad} FAILED` : 'ALL GREEN -- the conviction line gates scored players, and nothing built before it moves');
process.exit(bad ? 1 : 0);
