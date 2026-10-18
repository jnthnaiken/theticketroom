/* IRLIST-2026-10-18 -- an inactives list with an IR man beside it is still the inactives list.
     node nfl/test_nfl_irlist.js */
const L = require('./nfl_live.js');
const f = L.looksLikeInactives, row = (n, s) => ({ athlete: { displayName: n }, status: s });
let fails = 0;
const chk = (c, m) => { console.log((c ? 'PASS  ' : 'FAIL  ') + m); if (!c) fails++; };
const gb = ['Aaron Banks', 'Benjamin St-Juste', 'Donovan Jennings', 'Jager Burton'].map(n => row(n, 'Out'))
  .concat([row('Jonathan Ford', 'Injured Reserve')]);
chk(f(gb), 'GB 10-18: four Out + one Injured Reserve reads as the inactives list');
chk(f(gb.slice(0, 4)), 'a plain five-Out list still reads as published');
chk(!f(gb.concat([row('X', 'Questionable')])), 'a Questionable means it is still the injury report');
chk(!f(gb.concat([row('Y', 'Doubtful')])), 'so does a Doubtful');
chk(!f([row('A', 'Out'), row('B', 'Injured Reserve'), row('C', 'Injured Reserve')]), 'one Out and two IR is not a list');
chk(!f([]), 'empty is not published');
console.log(fails ? `\n${fails} FAILED` : '\nALL GREEN -- an IR man beside the inactives no longer blocks the tick');
process.exit(fails ? 1 : 0);
