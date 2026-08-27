/* test_teamnews_fetch.js -- soccer_teamnews_fetch.js against a stubbed ESPN.
 *
 * The container has no egress to ESPN, and the runner that will actually execute this has no
 * egress to understat or oddschecker, so neither machine can run the whole pipeline end to end.
 * That is exactly the situation `fixture-2026-08-25.psv` was captured for on the settle side:
 * pin the FEED SHAPE in a fixture and assert the parser against it, so the thing that breaks in
 * production is the network, not the code.
 *
 * Three scenarios, and the exit codes matter more than the rows: a workflow has to be able to
 * tell "not published yet" (20, come back) from "broken" (30, shout).
 */
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const HERE = __dirname;
const TMP = '/tmp/tnf';
fs.rmSync(TMP, { recursive: true, force: true });
fs.mkdirSync(TMP, { recursive: true });

const FIXTURES = {
  date: '2026-08-27',
  matches: {
    'celta-vigo-v-osasuna': { home: 'Celta Vigo', away: 'Osasuna', kickoff: 1110, league: 'La_liga', espn: ['esp.1', '401882924'] },
    'barcelona-v-athletic-club': { home: 'Barcelona', away: 'Athletic Club', kickoff: 1140, league: 'La_liga', espn: ['esp.1', '401882921'] }
  }
};
fs.writeFileSync(path.join(TMP, 'fixtures.json'), JSON.stringify(FIXTURES));

/* ESPN's real shapes, as soccer_live.js reads them. */
const roster = (club, xi, subs) => ({
  team: { displayName: club, abbreviation: club.slice(0, 3).toUpperCase() },
  roster: xi.map(n => ({ starter: true, athlete: { displayName: n } }))
    .concat(subs.map(n => ({ starter: false, athlete: { displayName: n } })))
});
const ELEVEN = p => Array.from({ length: 11 }, (_, i) => `${p} Starter${i + 1}`);

function stubFor(mode) {
  return `
    const SUMMARIES = ${JSON.stringify({
      '401882924': {
        rosters: [
          roster('Celta Vigo', ELEVEN('CEL').slice(0, 10).concat(['Ferran Jutgla']), ['Iago Aspas']),
          roster('Osasuna', ELEVEN('OSA').slice(0, 10).concat(['Raul Garcia']), ['Ante Budimir'])
        ],
        keyEvents: [
          { type: { text: 'Penalty - Scored' }, clock: { displayValue: "23'" }, participants: [{ athlete: { displayName: 'Ferran Jutgla' } }] },
          { type: { text: 'Own Goal' }, clock: { displayValue: "40'" }, participants: [{ athlete: { displayName: 'Raul Garcia' } }] }
        ]
      },
      '401882921': {
        rosters: [
          roster('Barcelona', ELEVEN('BAR').slice(0, 10).concat(['Raphinha']), ['Lamine Yamal']),
          roster('Athletic Club', ELEVEN('ATH'), [])
        ],
        keyEvents: []
      }
    })};
    const SCOREBOARD = { events: [
      { id: '401882924', date: '2026-08-27T18:30Z', status: { type: { name: 'STATUS_IN_PROGRESS' } } },
      { id: '401882921', date: '2026-08-27T19:00Z', status: { type: { name: 'STATUS_SCHEDULED' } } }
    ]};
    const MODE = ${JSON.stringify(mode)};
    global.fetch = function (u) {
      u = String(u);
      if (MODE === 'dead') return Promise.reject(new Error('ENOTFOUND'));
      if (u.indexOf('/scoreboard') >= 0) return Promise.resolve({ ok: true, json: () => Promise.resolve(SCOREBOARD) });
      const m = u.match(/event=(\\d+)/);
      let s = SUMMARIES[m[1]];
      if (MODE === 'partial' && m[1] === '401882921') s = { rosters: [], keyEvents: [] };
      return Promise.resolve({ ok: true, json: () => Promise.resolve(s) });
    };
  `;
}

let fail = 0;
const chk = (label, ok, detail) => {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`);
  if (!ok) { fail++; if (detail !== undefined) console.log('      ' + JSON.stringify(detail)); }
};

function run(mode) {
  const stub = path.join(TMP, `stub_${mode}.js`);
  fs.writeFileSync(stub, stubFor(mode));
  const out = path.join(TMP, `teamnews_${mode}.psv`);
  let code = 0, stdout = '';
  try {
    stdout = execFileSync('node', ['-r', stub, path.join(HERE, 'soccer_teamnews_fetch.js'),
      path.join(TMP, 'fixtures.json'), out], { encoding: 'utf8' });
  } catch (e) { code = e.status; stdout = (e.stdout || '') + (e.stderr || ''); }
  const rows = fs.existsSync(out) ? fs.readFileSync(out, 'utf8').trim().split('\n') : [];
  return { code, stdout, rows };
}

/* -------------------------------------------------------------------------------------
 * 1. Both sheets published -> exit 0, and the M/R/G rows are what soccer_teamnews.py eats.
 * ----------------------------------------------------------------------------------- */
{
  const r = run('full');
  console.log('--- 1. both team sheets published ---');
  chk('exit 0 when every sheet is complete', r.code === 0, { code: r.code, out: r.stdout.slice(-200) });

  const M = r.rows.filter(l => l.startsWith('M|'));
  const R = r.rows.filter(l => l.startsWith('R|'));
  const G = r.rows.filter(l => l.startsWith('G|'));
  chk('one M row per fixture', M.length === 2, M);
  chk('M carries status and the XI counts', /^M\|celta-vigo-v-osasuna\|STATUS_IN_PROGRESS\|.*\|11\|11$/.test(M[0]), M[0]);
  /* fixture 1 is 11+1 a side (24 rows), fixture 2 is 11+1 and 11+0 (23) -> 47 */
  const perFix = k => R.filter(l => l.split('|')[1] === k).length;
  chk('R rows carry club and XI/SUB',
    R.length === 47 && perFix('celta-vigo-v-osasuna') === 24 && perFix('barcelona-v-athletic-club') === 23
    && R.some(l => /\|XI$/.test(l)) && R.some(l => /\|SUB$/.test(l)),
    { n: R.length, cel: perFix('celta-vigo-v-osasuna'), bar: perFix('barcelona-v-athletic-club') });
  chk('the club comes off the team sheet', /^R\|celta-vigo-v-osasuna\|Celta Vigo\|/.test(R[0]), R[0]);

  /* the two that a naive parser gets wrong, and that soccer_live.js already gets right */
  chk('"Penalty - Scored" IS a goal', G.some(l => l === 'G|celta-vigo-v-osasuna|Ferran Jutgla|23'), G);
  chk('"Own Goal" is NOT this player\'s goal', !G.some(l => /Raul Garcia/.test(l)), G);
  chk('exactly one goal row', G.length === 1, G);
}

/* -------------------------------------------------------------------------------------
 * 2. One sheet not out yet -> 20. This is the whole gap between staggered kickoffs, and
 *    drafting through it would delete the unpublished match from the board.
 * ----------------------------------------------------------------------------------- */
{
  const r = run('partial');
  console.log('\n--- 2. one sheet still unpublished ---');
  chk('exit 20, not 0 and not a failure', r.code === 20, { code: r.code });
  chk('it still wrote what it DID learn', r.rows.some(l => l.startsWith('R|celta-vigo-v-osasuna|')), r.rows.length);
  chk('and said which fixture is missing', /SHEET NOT PUBLISHED/.test(r.stdout), r.stdout.slice(-200));
}

/* -------------------------------------------------------------------------------------
 * 3. ESPN unreachable -> 30, and NOTHING is written. A half-file here would be read as a
 *    team sheet in which everybody is absent.
 * ----------------------------------------------------------------------------------- */
{
  const r = run('dead');
  console.log('\n--- 3. ESPN unreachable ---');
  chk('exit 30', r.code === 30, { code: r.code });
  chk('no teamnews.psv written at all', r.rows.length === 0, r.rows.length);
}

console.log('');
console.log(fail ? `${fail} FAILURE(S)` : 'ALL GREEN -- the ESPN team-news pull is scripted');
process.exit(fail ? 1 : 0);
