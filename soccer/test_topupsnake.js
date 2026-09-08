/* test_topupsnake.js -- TOPUPSNAKE-2026-09-08. The LIVE TOP-UP obeys the draft order.
 *
 * DRAFTORDER-2026-09-04, in the owner's words: "the 1st pick goes to the 1st moon of the worst
 * of the anchors". draftN() has done that since. The live rebuild's pair top-up had NOT: it kept
 * TOPUPORDER-2026-08-30's strongest-first sort, written five days earlier when the fresh draft
 * also picked strongest-first, and never revisited when DRAFTORDER reversed it. So a board that
 * came through the rebuild -- which is every board once team news starts landing -- had the snake
 * quietly undone.
 *
 * Measured on the live 2026-09-08 board at 18:40Z, every screamer rebuilt as the Bournemouth and
 * Palace sheets landed:
 *
 *     Kylian Mbappe    197.7  strongest -> 143.8 142.6 140.1 127.7   mean 138.6
 *     Erling Haaland   195.9            -> 151.9 131.1 128.5 123.0   mean 133.6
 *     Serhou Guirassy  175.8  weakest   -> 128.2 119.6 118.7 113.3   mean 120.0
 *
 * Exactly inverted. Owner: "it looks like the worst anchor did not pick first. why?"
 *
 * The scenario below is the smallest thing that can tell the two orders apart: two anchors, each
 * holding a builder and needing a fresh pair, drawing from ONE shared candidate list. Whoever
 * picks first takes the strongest man in it.
 *
 * Run:  node test_topupsnake.js
 */
const SD = require('./soccer_draft.js');

let fail = 0;
function chk(label, ok, detail) {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`);
  if (!ok) { fail++; if (detail !== undefined) console.log('      ' + JSON.stringify(detail)); }
}

const KO = 19 * 60;                       // every match kicks at 19:00Z; nothing has started

/* Two anchors in two different matches, and eight partners spread over eight more, so that both
   anchors can legally reach every partner and the ONLY thing separating them is pick order.
   Eight is the smallest pool that fills BOTH pairs (2 anchors x 2 screamers x 2 partners), so a
   short board cannot be mistaken for a pick-order result. */
function board() {
  const P = {};
  const add = (name, game, total, odds) => {
    P[name] = {
      nm: name, game, gmatch: 'game ' + game, gtime: '3:00 PM', late: false,
      TOTAL: total, blend: total / 100, gate_z: 3.0, odds: odds || 200,   /* overridden below */
      team: 'T' + game, opp: ['X', '(H)'], status: 'projected',
      out: false, void: false, hr: false, goalmins: [], soft: false, unres: '',
    };
  };
  add('Strong Anchor', 1, 190.0);
  add('Weak Anchor',   2, 170.0);
  /* ANCHORGATE-2026-09-04: only men who clear Z_GATE on their own may hold an anchor seat, and
     the top-up draws from the WIDEST field. Putting the partners below the gate is what isolates
     the top-up -- the fresh draft cannot seat any of them, so the only thing that can build a
     pair here is the block under test. It is also the real shape: the pool is small and the
     partners are the ungated remainder. */
  add('Partner A', 3, 150.0);            // the prize -- whoever picks first takes him
  add('Partner B', 4, 145.0);
  add('Partner C', 5, 140.0);
  add('Partner D', 6, 135.0);
  add('Partner E', 7, 130.0);
  add('Partner F', 8, 125.0);
  add('Partner G', 9, 120.0);
  add('Partner H', 10, 115.0);

  ['Partner A','Partner B','Partner C','Partner D','Partner E','Partner F','Partner G','Partner H']
    .forEach(n => { P[n].gate_z = 0.2; });
  /* Both anchors are CONFIRMED, so their builders freeze (CONFLOCK) and each claims his anchor
     seat -- which is what makes REPAIRPAIR-2026-08-30 seed him at zero moons and rebuild. */
  P['Strong Anchor'].status = 'confirmed';
  P['Weak Anchor'].status = 'confirmed';

  const ko = {};
  Object.keys(P).forEach(n => { ko[String(P[n].game)] = KO; });

  /* A builder on the board IS the board's commitment to that anchor (REPAIRPAIR-2026-08-30),
     so each anchor is seeded at zero moons and the top-up rebuilds his pair. */
  const builder = (name) => ({
    kind: 'builder', name: 'Builder ' + name, badge: '⚽', note: '',
    players: [{ name, team: P[name].team, total: P[name].TOTAL, aT: 100, wf: 1.0,
                gmatch: P[name].gmatch, gtime: P[name].gtime, game: P[name].game,
                late: false, odds: P[name].odds, status: 'confirmed' }],
    nlegs: 1, anchor: name, lock: '3:00 PM', has_late: false, final: false, locked: false,
    rr: null, unres: 0, priced: 1,
  });

  return {
    players: P,
    tickets: [builder('Strong Anchor'), builder('Weak Anchor')],
    meta: { date: '2026-09-08', ko, gs: {}, finals: [], results: {}, espn: {} },
  };
}

function partnersOf(tickets, anchor) {
  return tickets
    .filter(t => t.kind === 'moon' && t.anchor === anchor)
    .flatMap(t => t.players.filter(p => p.name !== anchor).map(p => p.name))
    .sort();
}

const D = board();
const r = SD.redraft(D, { nowUTCmin: KO - 120 });
const out = r.tickets || D.tickets;

console.log('\n=== what the top-up built ===');
out.forEach(t => console.log('  ' + t.kind.padEnd(8) + ' ' +
  t.players.map(l => l.name + '(' + (D.players[l.name] || {}).TOTAL + ')').join(' + ')));
console.log('');

const weak = partnersOf(out, 'Weak Anchor');
const strong = partnersOf(out, 'Strong Anchor');
const val = ns => ns.map(n => D.players[n].TOTAL);
const mean = ns => ns.length ? val(ns).reduce((a, b) => a + b, 0) / ns.length : 0;

chk('both anchors got a full pair back', weak.length === 4 && strong.length === 4,
    { weak, strong });

/* THE RULE. The weakest anchor picks first, so the strongest man in the shared pool is his. */
chk('the WEAKEST anchor takes the strongest partner (Partner A)',
    weak.includes('Partner A'), { weak, strong });
chk('the strongest anchor does NOT get the strongest partner',
    !strong.includes('Partner A'), { strong });
chk('the weakest anchor ends with the better half of the pool',
    mean(weak) > mean(strong),
    { weakMean: mean(weak), strongMean: mean(strong), weak: val(weak), strong: val(strong) });

/* Determinism was TOPUPORDER-2026-08-30's actual job and is not what changed here: only the
   direction. Same input, same board, every time -- whatever order the tickets arrive in. */
const D2 = board();
D2.tickets.reverse();
const r2 = SD.redraft(D2, { nowUTCmin: KO - 120 });
const sig = ts => (ts || []).map(t => t.kind + ':' + t.players.map(l => l.name).join('+')).sort().join(' | ');
chk('the order the tickets arrive in does not change the board (determinism kept)',
    sig(r2.tickets || D2.tickets) === sig(out), { a: sig(out), b: sig(r2.tickets || D2.tickets) });

console.log('');
console.log(fail ? `FAILED ${fail}` : 'all checks pass');
process.exit(fail ? 1 : 0);
