#!/usr/bin/env node
/* test_benchfix.js -- SIDETRUST / BENCHLOCK / NOAPPEAR, 2026-10-07.
 *
 * The incident: 2026-10-06 "The Nine", Jose Manuel Lopez (Argentina v Benin, a friendly). Argentina's
 * XI posted with him on the bench at 22:51Z; Benin's sheet never reached ESPN, so the match never
 * trusted, the drafter kept him, NOSHEETLOCK froze the slip at the 23:00Z kickoff, and the night
 * graded an unused sub as a -1u loss.
 *
 *   1  SIDETRUST  his own side's full XI is enough to re-draft him off before kickoff
 *   2  BENCHLOCK  a benched leg never locks on the clock; a slip already latched stays latched
 *   3  NOAPPEAR   at full time an unused sub on a complete side is VOID, a used sub is not
 *   4  teamnews   soccer_teamnews.py emits side_trusted for the complete side only
 */
const path = require('path');
const fs = require('fs');
const os = require('os');
const { execFileSync } = require('child_process');
const SD = require('./soccer_draft.js');
const L = require('./soccer_live.js');

let bad = 0;
const ok = (c, m) => { console.log((c ? '  ok   ' : '  FAIL ') + m); if (!c) bad++; };
const clone = o => JSON.parse(JSON.stringify(o));

/* A two-match top-singles card. Game 1 is a club match, no sheet yet. Game 2 is the friendly. */
function board() {
  const P = {};
  const add = (nm, game, TOTAL, odds, status) => {
    P[nm] = { nm, game, TOTAL, odds, status: status || 'projected', out: false, void: false,
              blend: (TOTAL - 100) / 30, gate_z: 1.0, team: game === 2 ? 'Argentina' : 'Club' };
  };
  add('Club Striker A', 1, 140, 150); add('Club Striker B', 1, 130, 180);
  add('Jose Manuel Lopez', 2, 131.8, -200, 'benched');
  add('Enzo Fernandez', 2, 125, 250, 'confirmed');
  add('Lautaro Martinez', 2, 150, -150, 'confirmed');
  const tickets = [
    { name: 'The Nine', kind: 'builder', players: [{ name: 'Jose Manuel Lopez', game: 2 }] },
    { name: 'Near Post', kind: 'builder', players: [{ name: 'Lautaro Martinez', game: 2 }] },
    { name: 'Back Post', kind: 'builder', players: [{ name: 'Club Striker A', game: 1 }] },
  ];
  return { players: P, tickets,
           meta: { date: '2026-10-06', ko: { 1: 1440, 2: 1380 }, nosheet: { 2: true } } };
}
const cfg = { TOP_SINGLES: 3, TOP_PER_MATCH: 2 };
const xi = SD.nameSet(['Enzo Fernandez', 'Lautaro Martinez']);
const names = r => r.tickets.map(t => t.players.map(l => l.name).join('+'));

console.log('1  SIDETRUST');
{
  /* What the drafter saw on 10/06: the match untrusted, so to it he was simply 'projected'. */
  const unknown = clone(board()); unknown.players['Jose Manuel Lopez'].status = 'projected';
  const before = SD.redraft(clone(unknown), { cfg, nowUTCmin: 1371, xi, xiMatches: {} });
  ok(names(before).includes('Jose Manuel Lopez'), 'without side trust (the 10/06 bug) he stays on');
  const D = clone(unknown);
  const r = SD.redraft(D, { cfg, nowUTCmin: 1371, xi, xiMatches: {},
                            xiSide: SD.nameSet(['Jose Manuel Lopez', 'Enzo Fernandez', 'Lautaro Martinez']) });
  ok(!names(r).includes('Jose Manuel Lopez'), 'with his side trusted he is re-drafted off before kickoff');
  ok(r.tickets.length === 3, 'and the seat is refilled from the field (3 singles on the card)');
  ok(names(r).includes('Club Striker A'), 'an unpublished club match is untouched (still draftable)');
}

console.log('2  BENCHLOCK');
{
  const D = clone(board());
  const koOf = g => D.meta.ko[g];
  ok(!SD.ticketIsLocked(D.tickets[0], D, 1381, koOf, false), 'benched leg does not lock on the clock at kickoff');
  ok(SD.ticketIsLocked(D.tickets[1], D, 1381, koOf, false), 'a confirmed leg still locks (CONFLOCK unchanged)');
  const t = clone(D.tickets[0]); t.locked = true;
  ok(SD.ticketIsLocked(t, D, 1381, koOf, false), 'a slip already latched stays latched (placed bet never unwound)');
  const r = SD.redraft(clone(board()), { cfg, nowUTCmin: 1381, xi, xiMatches: {} });
  ok(!names(r).includes('Jose Manuel Lopez'), 'after kickoff, even with no team news, the benched single is not frozen onto the card');
}

console.log('3  NOAPPEAR');
{
  const roster = (subLopezOn) => ([
    { team: { displayName: 'Argentina' }, roster:
      Array.from({ length: 11 }, (_, i) => ({ starter: true, subbedIn: false, athlete: { displayName: i === 0 ? 'Lautaro Martinez' : 'Arg Starter ' + i } }))
        .concat([{ starter: false, subbedIn: subLopezOn, athlete: { displayName: 'José Manuel López' } },
                 { starter: false, subbedIn: false, athlete: { displayName: 'Nico Paz' } }]) },
    { team: { displayName: 'Benin' }, roster: [] },
  ]);
  const run = (on, completed) => {
    const D = clone(board());
    D.meta.espn = { 2: ['fifa.friendly', '1'] };
    const live = L.makeLive({ D, fetchJSON: () => Promise.reject(new Error('unused')) });
    const sb = { status: { type: { completed, state: completed ? 'post' : 'in' } },
                 competitions: [{ competitors: [{ homeAway: 'home', score: '3' }, { homeAway: 'away', score: '0' }] }] };
    live.applyMatch(2, sb, { rosters: roster(on), keyEvents: [] });
    return D.players['Jose Manuel Lopez'];
  };
  ok(run(false, true).void === true, 'unused sub on a complete side, full time -> VOID');
  ok(run(true, true).void === false, 'a sub who came on is NOT voided');
  ok(run(false, false).void === false, 'nothing is voided before full time');
  ok(run(false, false).status === 'benched', 'half a sheet (his side complete) still states his status: benched');
}

console.log('4  teamnews side_trusted');
{
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'tnside-'));
  const m = 'argentina-v-benin';
  fs.writeFileSync(path.join(dir, 'ags.psv'), [m + '|Jose Manuel Lopez|-200', m + '|Enzo Fernandez|250', m + '|Steve Mounie|300'].join('\n') + '\n');
  const R = [['M', m, 'STATUS_SCHEDULED', '', 11, 0].join('|')];
  for (let i = 0; i < 10; i++) R.push(['R', m, 'Argentina', 'Arg Starter ' + i, 'XI'].join('|'));
  R.push(['R', m, 'Argentina', 'Enzo Fernández', 'XI'].join('|'));
  R.push(['R', m, 'Argentina', 'José Manuel López', 'SUB'].join('|'));
  R.push(['R', m, 'Benin', 'Steve Mounié', 'SUB'].join('|'));
  fs.writeFileSync(path.join(dir, 'tn.psv'), R.join('\n') + '\n');
  execFileSync('python3', [path.join(__dirname, 'soccer_teamnews.py'), path.join(dir, 'ags.psv'), path.join(dir, 'tn.psv'), path.join(dir, 'out.json')],
               { cwd: __dirname, stdio: 'pipe' });
  const tn = JSON.parse(fs.readFileSync(path.join(dir, 'out.json'), 'utf8'));
  ok(tn.trusted[m] === false, 'the match is still untrusted (Benin has no XI)');
  ok(!!tn.side_trusted['Jose Manuel Lopez'] && !!tn.side_trusted['Enzo Fernandez'], 'both Argentina names are side-trusted');
  ok(!tn.side_trusted['Steve Mounie'], 'the incomplete side (Benin) is not');
  ok(!tn.absent['Steve Mounie'], 'and absence is still never asserted from half a sheet');
}

if (bad) { console.log(`\n${bad} FAILED`); process.exit(1); }
console.log('\nALL GREEN -- a benched man comes off before kickoff, never locks, and an unused sub is a void');
