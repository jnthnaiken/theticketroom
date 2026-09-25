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

/* SQUADAUTO-2026-09-25. The squad pull reads the two team ids out of the summary HEADER -- not
   out of rosters[], which is empty until the sheets drop -- and then calls /teams/<id>/roster.
   `hdr` is that header, and it is what makes the ids discoverable at all. */
const hdr = (h, a) => ({ competitions: [{ competitors: [
  { homeAway: 'home', team: { id: h } }, { homeAway: 'away', team: { id: a } }] }] });
const SQUAD = (p, n) => Array.from({ length: n }, (_, i) => `${p} Squad${i + 1}`);

function stubFor(mode) {
  return `
    const SUMMARIES = ${JSON.stringify({
      '401882924': {
        header: hdr('1', '2'),
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
        header: hdr('3', '4'),
        rosters: [
          roster('Barcelona', ELEVEN('BAR').slice(0, 10).concat(['Raphinha']), ['Lamine Yamal']),
          roster('Athletic Club', ELEVEN('ATH'), [])
        ],
        keyEvents: []
      }
    })};
    /* ⚠️ TEAM 2 USES THE GROUPED SHAPE. ESPN ships soccer rosters as a flat "athletes" array and
       the American sports as position groups; rosterNames() reads both, and if it ever stops
       doing so this side comes back with zero names, fails the both-sides rule, and the fixture
       silently loses its club labels. That is the regression this asserts. */
    const ROSTERS = ${JSON.stringify({
      '1': { team: { displayName: 'Celta Vigo' }, athletes: SQUAD('CEL', 24).map(n => ({ displayName: n })) },
      '2': { team: { displayName: 'Osasuna' },
             athletes: [{ position: 'goalkeeper', items: SQUAD('OSA', 3).map(n => ({ displayName: n })) },
                        { position: 'outfield', items: SQUAD('OSAO', 19).map(n => ({ displayName: n })) }] },
      '3': { team: { displayName: 'Barcelona' }, athletes: SQUAD('BAR', 25).map(n => ({ displayName: n })) },
      '4': { team: { displayName: 'Athletic Club' }, athletes: SQUAD('ATH', 23).map(n => ({ displayName: n })) }
    })};
    const SCOREBOARD = { events: [
      { id: '401882924', date: '2026-08-27T18:30Z', status: { type: { name: 'STATUS_IN_PROGRESS' } } },
      { id: '401882921', date: '2026-08-27T19:00Z', status: { type: { name: 'STATUS_SCHEDULED' } } }
    ]};
    const MODE = ${JSON.stringify(mode)};
    global.__calls = [];
    global.fetch = function (u) {
      u = String(u);
      global.__calls.push(u);
      if (MODE === 'dead') return Promise.reject(new Error('ENOTFOUND'));
      if (u.indexOf('/scoreboard') >= 0) return Promise.resolve({ ok: true, json: () => Promise.resolve(SCOREBOARD) });
      const rm = u.match(/teams\\/(\\d+)\\/roster/);
      if (rm) {
        if (MODE === 'norosters') return Promise.reject(new Error('http 500'));
        let r = ROSTERS[rm[1]];
        /* one side of ONE fixture comes back too short to be a squad */
        if (MODE === 'shortsquad' && rm[1] === '4') r = { team: { displayName: 'Athletic Club' }, athletes: [{ displayName: 'Lone Trialist' }] };
        return Promise.resolve({ ok: true, json: () => Promise.resolve(r) });
      }
      const m = u.match(/event=(\\d+)/);
      let s = SUMMARIES[m[1]];
      if (MODE === 'partial' && m[1] === '401882921') s = { rosters: [], keyEvents: [], header: SUMMARIES[m[1]].header };
      return Promise.resolve({ ok: true, json: () => Promise.resolve(s) });
    };
    process.on('exit', function () {
      try { require('fs').writeFileSync(process.env.CALLS_OUT, global.__calls.join('\\n')); } catch (e) {}
    });
  `;
}

let fail = 0;
const chk = (label, ok, detail) => {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`);
  if (!ok) { fail++; if (detail !== undefined) console.log('      ' + JSON.stringify(detail)); }
};

function run(mode, opts) {
  opts = opts || {};
  const tag = opts.tag || mode;
  const stub = path.join(TMP, `stub_${tag}.js`);
  fs.writeFileSync(stub, stubFor(mode));
  const out = path.join(TMP, `teamnews_${tag}.psv`);
  const sqOut = opts.squads === false ? null : path.join(TMP, `squads_${tag}.psv`);
  const callsOut = path.join(TMP, `calls_${tag}.txt`);
  const argv = [path.join(TMP, 'fixtures.json'), out];
  if (sqOut) argv.push(sqOut);
  let code = 0, stdout = '';
  try {
    stdout = execFileSync('node', ['-r', stub, path.join(HERE, 'soccer_teamnews_fetch.js'), ...argv],
      { encoding: 'utf8', env: Object.assign({}, process.env, { CALLS_OUT: callsOut }) });
  } catch (e) { code = e.status; stdout = (e.stdout || '') + (e.stderr || ''); }
  const rows = fs.existsSync(out) ? fs.readFileSync(out, 'utf8').trim().split('\n') : [];
  const sq = sqOut && fs.existsSync(sqOut)
    ? fs.readFileSync(sqOut, 'utf8').trim().split('\n').filter(Boolean) : [];
  const calls = fs.existsSync(callsOut)
    ? fs.readFileSync(callsOut, 'utf8').split('\n').filter(Boolean) : [];
  return { code, stdout, rows, sq, sqOut, calls };
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

/* -------------------------------------------------------------------------------------
 * 4. SQUADAUTO-2026-09-25 -- squads.psv, the club label, pulled on the runner.
 *    Was a hand-scrape into the slate directory since SQUADCLUB-2026-08-28.
 * ----------------------------------------------------------------------------------- */
{
  const r = run('full', { tag: 'sqfull' });
  console.log('\n--- 4. squads.psv from /teams/<id>/roster ---');
  chk('exit code is unchanged by the squad pull', r.code === 0, { code: r.code });
  chk('it wrote match|team|player rows', r.sq.length === 24 + 22 + 25 + 23, r.sq.length);
  chk('keyed by the fixture slug, named by the team',
    r.sq[0] === 'celta-vigo-v-osasuna|Celta Vigo|CEL Squad1', r.sq[0]);
  const per = k => r.sq.filter(l => l.split('|')[0] === k).length;
  chk('both fixtures covered', per('celta-vigo-v-osasuna') === 46 && per('barcelona-v-athletic-club') === 48,
    { cel: per('celta-vigo-v-osasuna'), bar: per('barcelona-v-athletic-club') });
  /* the grouped-athletes shape, flattened -- see the note on ROSTERS in the stub */
  chk('a POSITION-GROUPED roster is flattened, not dropped',
    r.sq.filter(l => /\|Osasuna\|/.test(l)).length === 22,
    r.sq.filter(l => /\|Osasuna\|/.test(l)).length);
  chk('the ids came from the summary header, so /teams/<id>/roster was called',
    r.calls.filter(u => /teams\/\d+\/roster/.test(u)).length === 4,
    r.calls.filter(u => /teams\/\d+\/roster/.test(u)));

  /* ⚠️ THE ONE THAT MATTERS. squads.psv arms soccer_mock's WRONGCLUB gate, which drops a priced
     player who is in NEITHER squad. A fixture with one side missing would read as "every man on
     that side is out of the squad" and take them all off the board, so a half-pulled fixture
     must contribute NOTHING rather than half. */
  const s = run('shortsquad', { tag: 'sqshort' });
  console.log('\n--- 5. one side is not a real squad ---');
  chk('the short fixture contributes NO rows at all',
    s.sq.filter(l => l.split('|')[0] === 'barcelona-v-athletic-club').length === 0,
    s.sq.filter(l => l.split('|')[0] === 'barcelona-v-athletic-club').slice(0, 3));
  chk('and it does not take the healthy fixture down with it',
    s.sq.filter(l => l.split('|')[0] === 'celta-vigo-v-osasuna').length === 46,
    s.sq.filter(l => l.split('|')[0] === 'celta-vigo-v-osasuna').length);
  chk('it says which fixture it skipped and why', /WRONGCLUB stays disarmed/.test(s.stdout),
    s.stdout.slice(-300));
  chk('a roster miss is still exit 0 -- the squad is a LABEL, the exit code is the team SHEET',
    s.code === 0, { code: s.code });

  /* ⚠️ AND IT NEVER CLOBBERS. The workflow copies the committed slate squads.psv into place
     before this runs, so an empty write would replace a good file with one that disarms both
     the label and the gate -- the `_XI is None` trap, third time. */
  console.log('\n--- 6. every roster call fails ---');
  const n = run('norosters', { tag: 'sqnone' });
  fs.writeFileSync(n.sqOut, 'celta-vigo-v-osasuna|Celta Vigo|Iago Aspas\n');
  const n2 = run('norosters', { tag: 'sqnone' });
  chk('an existing squads.psv is left exactly as it was found',
    n2.sq.length === 1 && n2.sq[0] === 'celta-vigo-v-osasuna|Celta Vigo|Iago Aspas', n2.sq);
  chk('and it says so rather than failing the build',
    /left as it was found/.test(n2.stdout) && n2.code === 0, { code: n2.code });

  /* THE CACHE. A 22-fixture slate rebuilding every four minutes would be 44 extra ESPN calls a
     pass for a list that changes when a manager names a squad. */
  console.log('\n--- 7. squads already on disk ---');
  const c = run('full', { tag: 'sqcache' });
  const c2 = run('full', { tag: 'sqcache' });
  chk('the first pass called the roster endpoint',
    c.calls.filter(u => /roster/.test(u)).length === 4, c.calls.filter(u => /roster/.test(u)).length);
  chk('the second pass did not call it at all',
    c2.calls.filter(u => /roster/.test(u)).length === 0, c2.calls.filter(u => /roster/.test(u)));
  chk('and said why', /already covers all 2 fixture/.test(c2.stdout), c2.stdout.slice(0, 200));
  chk('the file survives the skipped pass', c2.sq.length === c.sq.length, { a: c.sq.length, b: c2.sq.length });

  /* Backwards compatible: no third argument, no squad pull, nothing else changes. */
  console.log('\n--- 8. called the old way, with two arguments ---');
  const o = run('full', { tag: 'sqoff', squads: false });
  chk('no squads.psv is written and no roster call is made',
    o.calls.filter(u => /roster/.test(u)).length === 0 && o.code === 0,
    { calls: o.calls.filter(u => /roster/.test(u)).length, code: o.code });
  chk('the M/R/G rows are unchanged', o.rows.length === r.rows.length, { a: o.rows.length, b: r.rows.length });

  /* 🚨 AND THE CACHE ASKS THE SAME QUESTION THE WRITER DOES. Measured on the committed slates:
     2026-08-28 and 2026-08-29 carry squads.psv files with both sides present and as few as TWO
     names on the smaller one -- team-sheet fragments. 20 such fixtures, 31 priced players flagged
     "in neither squad" between them, Sorloth and Pinamonti among them. A cache test that only
     asked "are there rows for this fixture?" would accept one of those forever, and the fixtures
     most in need of a real squad would be the ones never re-pulled. */
  console.log('\n--- 9. a PARTIAL squads.psv on disk ---');
  const p = run('full', { tag: 'sqpartial' });
  fs.writeFileSync(p.sqOut,
    ['celta-vigo-v-osasuna|Celta Vigo|A One', 'celta-vigo-v-osasuna|Osasuna|B One',
     'barcelona-v-athletic-club|Barcelona|C One', 'barcelona-v-athletic-club|Athletic Club|D One'].join('\n') + '\n');
  const p2 = run('full', { tag: 'sqpartial' });
  chk('a two-name-a-side file does NOT count as cover -- it is re-pulled',
    p2.calls.filter(u => /roster/.test(u)).length === 4, p2.calls.filter(u => /roster/.test(u)).length);
  chk('and is replaced by the real squads', p2.sq.length === 24 + 22 + 25 + 23, p2.sq.length);
}

console.log('');
console.log(fail ? `${fail} FAILURE(S)` : 'ALL GREEN -- the ESPN team-news pull is scripted');
process.exit(fail ? 1 : 0);
