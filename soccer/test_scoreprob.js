/* test_scoreprob.js -- SCOREPROB-2026-10-10: the conviction line.
   A player carrying `pscore` is draftable only at pscore >= DEFAULTS.MIN_P, and for him the line
   REPLACES the -200 floor. A player with no pscore (any board built before the change, and NFL)
   keeps the old floor exactly. */
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
console.log(bad ? `${bad} FAILED` : 'ALL GREEN -- the conviction line gates scored players, and nothing built before it moves');
process.exit(bad ? 1 : 0);
