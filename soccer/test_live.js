/* test_live.js -- soccer_live.js against the REAL 2026-08-25 ESPN feed.
 *
 * The slate is finished and its truth is checkable by hand, which is the point: a harness that
 * cannot fail is worthless (replay_check.js, 2026-08-17). Every assertion below is a fact about
 * a match that actually happened, not a fixture invented to match the code.
 */
const fs = require('fs');
const path = require('path');
const L = require('./soccer_live.js');

let fails = 0, checks = 0;
function ok(cond, what) {
  checks++;
  if (!cond) { fails++; console.log('  FAIL  ' + what); }
  else console.log('  ok    ' + what);
}
function eq(a, b, what) { ok(JSON.stringify(a) === JSON.stringify(b), what + '  (got ' + JSON.stringify(a) + ')'); }

/* ---------- 1. unit: own goals and goal variants -------------------------------- */
console.log('\n[1] goal typing');
ok(L.isScoringGoal('Goal'), 'Goal counts');
ok(L.isScoringGoal('Goal - Volley'), 'Goal - Volley counts');
ok(L.isScoringGoal('Goal - Header'), 'Goal - Header counts');
ok(L.isScoringGoal('Goal - Free-kick'), 'Goal - Free-kick counts');
ok(L.isScoringGoal('Penalty - Scored'), 'Penalty - Scored counts (6 in 26 real matches)');
ok(!L.isScoringGoal('Own Goal'), 'Own Goal does NOT count');
ok(!L.isScoringGoal('Penalty - Saved'), 'Penalty - Saved does NOT count');
ok(!L.isScoringGoal('Penalty - Hit Woodwork'), 'Penalty - Hit Woodwork does NOT count');
ok(!L.isScoringGoal('Goal', { shootout: true }), 'a SHOOTOUT kick never settles AGS');
ok(L.isScoringGoal('Goal', { shootout: false }), 'a non-shootout goal still counts');

/* ---------- 2. unit: the surname anchor ----------------------------------------- */
console.log('\n[2] name join (PIPELINE open item 1)');
ok(L.matchOne('Joy Lance Mickels', ['Joy-Lance Mickels']) === 'Joy-Lance Mickels',
   'hyphen/space differences join');
ok(L.matchOne('Pablo García', ['Pablo Garcia']) === 'Pablo Garcia',
   'accents join');
ok(L.matchOne('João Pedro', ['Joao Pedro Jota']) === null,
   'Joao Pedro does NOT settle Joao Pedro Jota (surname anchor)');
ok(L.matchOne('Fredrik André Bjørkan', ['Fredrik Bjorkan']) === 'Fredrik Bjorkan',
   'middle name dropped, surname present -> joins');
ok(L.matchOne('Samuel Adeniran', ['Samuel Adeniran', 'Sam Adeniran']) === 'Samuel Adeniran',
   'exact wins over a second surname candidate');
ok(L.matchOne('Some Unknown', ['Andreas Helmersen']) === null, 'no match -> null');

/* ---------- 3. build ESPN-shaped responses from the captured feed ---------------- */
const FIX = fs.readFileSync(path.join(__dirname, 'fixture-2026-08-25.psv'), 'utf8')
  .split('\n').map(s => s.trim()).filter(Boolean);

const GNUM = { '401909192': 1, '401909196': 2, '401903707': 3, '401882917': 4 };
const LG   = { '401909192': 'uefa.champions_qual', '401909196': 'uefa.champions_qual',
               '401903707': 'uefa.champions_qual', '401882917': 'esp.1' };

const sbEvents = {}, summaries = {};
FIX.forEach(line => {
  const c = line.split('|');
  if (c[0] === 'M') {
    const [, lg, id, name, desc, completed, score] = c;
    const [h, a] = score.split('/');
    sbEvents[id] = {
      id, name,
      status: { type: { description: desc, completed: completed === '1', state: completed === '1' ? 'post' : 'in' } },
      competitions: [{ competitors: [
        { homeAway: 'home', score: h.split(':')[1], team: { abbreviation: h.split(':')[0] } },
        { homeAway: 'away', score: a.split(':')[1], team: { abbreviation: a.split(':')[0] } }] }]
    };
    summaries[id] = summaries[id] || { keyEvents: [], rosters: [] };
  } else if (c[0] === 'G') {
    const [, id, type, who, clock] = c;
    summaries[id] = summaries[id] || { keyEvents: [], rosters: [] };
    summaries[id].keyEvents.push({ type: { text: type }, clock: { displayValue: clock },
                                   participants: [{ athlete: { displayName: who } }] });
  }
});

/* ---------- 4. the board: the REAL tickets that shipped on 08-25 ----------------- */
const LEGS = [
  ['Andreas Helmersen',   2, 110],
  ['Joy-Lance Mickels',   1, 150],
  ['Moses Usor',          3, 160],
  ['Cucho Hernandez',     4, 230],
  ['Kasper Hogh',         3, 180],
  ['Hugo Duro',           4, 225],
  ['Samuel Adeniran',     3, 145],
  ['Ole Didrik Blomberg', 2, 150],
  /* not on a ticket, but priced and IN the Bodo match: he put through the own goal.
     If the loop pays own goals, this man reads as a scorer. */
  ['Deveron Fonville',    2, 900],
];
const players = {};
LEGS.forEach(([n, g, odds]) => {
  players[n] = { nm: n, game: g, odds, hr: false, goalmins: [], out: false, void: false,
                 status: 'projected', unres: '' };
});

function T(kind, name, legs, risk) {
  const ps = legs.map(n => ({ name: n, odds: players[n].odds, game: players[n].game }));
  return { kind, name, players: ps, nlegs: ps.length,
           rr: ps.length >= 3 ? { struct: 'by 2s & 3', risk } : null };
}
const tickets = [
  T('moon', 'Top Corner',    ['Andreas Helmersen', 'Joy-Lance Mickels', 'Moses Usor'], 2.0),
  T('moon', 'From Distance', ['Andreas Helmersen', 'Cucho Hernandez', 'Kasper Hogh'], 2.0),
  T('builder', 'Six-Yard Box', ['Andreas Helmersen']),
  T('family', 'Off the Bench', ['Hugo Duro']),
  T('family', 'Fresh Legs',    ['Samuel Adeniran']),
  T('family', 'Late Doors',    ['Ole Didrik Blomberg']),
];

const D = {
  players, tickets, pool: Object.keys(players), familyFloor: 0,
  meta: { date: '2026-08-25', build: '2026-08-25 test', face: 'soccer', wx: {}, gs: {},
          finals: [], results: {}, pool: LEGS.length, gate: LEGS.length, tickets: tickets.length,
          espn: Object.keys(GNUM).reduce((m, id) => (m[GNUM[id]] = { lg: LG[id], ev: id }, m), {}),
          season: { since: '2026-08-25', history: [0], graded_nights: [], stake: 1,
                    cats: { lunch: z(), late: z(), builder: z(), moon: z(), family: z() } } }
};
function z() { return { graded: 0, won: 0, units: 0, staked: 0 }; }

/* ---------- 5. run the loop against the captured feed ---------------------------- */
console.log('\n[3] live loop');
const unmatched = [];
const live = L.makeLive({
  D,
  unmatched,
  fetchJSON: (url) => {
    const mSb = url.match(/\/([^/]+)\/scoreboard\?dates=(\d+)/);
    if (mSb) {
      const lg = mSb[1];
      return Promise.resolve({ events: Object.keys(sbEvents).filter(id => LG[id] === lg).map(id => sbEvents[id]) });
    }
    const mSum = url.match(/summary\?event=(\d+)/);
    if (mSum) return Promise.resolve(summaries[mSum[1]]);
    return Promise.reject(new Error('unexpected url ' + url));
  },
  stamp: () => {}, render: () => {}
});

live.run().then(() => {
  eq(D.meta.finals.slice().sort((a, b) => a - b), [1, 2, 3, 4], 'all four matches final');
  eq(D.meta.results[2], [3, 0], 'Bodo/Glimt 3-0 NEC');
  eq(D.meta.results[4], [0, 1], 'Valencia 0-1 Real Betis');
  eq(D.meta.gs, {}, 'no match left flagged live');

  ok(D.players['Joy-Lance Mickels'].hr === true, 'Mickels scored (115′)');
  eq(D.players['Joy-Lance Mickels'].goalmins, ['115'], 'Mickels goal minute');
  ok(D.players['Moses Usor'].hr === true, 'Usor scored (32′)');
  ok(D.players['Samuel Adeniran'].hr === true, 'Adeniran scored');
  eq(D.players['Samuel Adeniran'].goalmins, ['58', '109'], 'Adeniran BOTH goals kept');

  ok(D.players['Andreas Helmersen'].hr === false, 'Helmersen did NOT score');
  ok(D.players['Kasper Hogh'].hr === false, 'Hogh did NOT score');
  ok(D.players['Hugo Duro'].hr === false, 'Duro did NOT score');
  ok(D.players['Cucho Hernandez'].hr === false, 'Cucho did NOT score');
  ok(D.players['Ole Didrik Blomberg'].hr === false, 'Blomberg did NOT score');

  ok(D.players['Deveron Fonville'].hr === false,
     'OWN GOAL does not settle Fonville as a scorer');

  console.log('\n  unmatched feed scorers (expected: everyone not priced on this board): ' + unmatched.length);

  fs.writeFileSync(path.join(__dirname, 'D_test_2026-08-25.json'), JSON.stringify(D, null, 1));
  console.log('\n' + (fails ? 'FAILED ' + fails + '/' + checks : 'PASS ' + checks + '/' + checks));
  process.exit(fails ? 1 : 0);
}).catch(e => { console.log('THREW: ' + e.stack); process.exit(1); });
