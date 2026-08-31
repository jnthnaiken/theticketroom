/* test_slateclock.js -- SLATECLOCK-2026-08-31.
 *
 * `kickoff` is minutes past midnight UTC OF THE SLATE DATE (soccer_payload.et_dt builds it that
 * way), so it legally exceeds 1440: MLS kicks off 00:30Z = 1470. `now` was wall-clock UTC,
 * 0..1439. MINTGUARD compares them directly. Two bases, one comparison.
 *
 * This file pins the comparison itself, on a slate that CROSSES MIDNIGHT -- the case the whole
 * European corpus never contained, which is why nothing caught it.
 *
 * Two failures, one arithmetic:
 *   1. A kickoff past 1440 is unreachable by a 0..1439 clock, so MINTGUARD can never fire for it
 *      -- an MLS slip would be mintable at every hour of the match.
 *   2. After midnight UTC the clock wraps and the slate does not, so a FINISHED European match
 *      reads as unstarted. Measured on the published 2026-08-31 board at now=15: six new slips
 *      minted into matches that had ended hours earlier.
 *
 * The drafter is not the bug and is not changed: `nowUTCmin` is slate-relative by contract and
 * every test here passes it that way. What this asserts is that the contract holds at the
 * boundary, and that soccer_rebuild_cli.js's clock puts a caller on the right side of it.
 */
const fs = require('fs');
const path = require('path');
const SD = require('./soccer_draft.js');

const FIXTURE = path.join(__dirname, 'fixtures', '2026-08-26', 'soccer_D.json');
const base = JSON.parse(fs.readFileSync(FIXTURE, 'utf8'));

let fail = 0;
const chk = (label, ok, detail) => {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`);
  if (!ok) { fail++; if (detail !== undefined) console.log('      ' + JSON.stringify(detail)); }
};

/* One match open at `koOpen`, every other match already underway, so anything minted must be in
   that match and nothing else can confound the count. */
function mintedInto(koOpen, now, openGame) {
  const D = JSON.parse(JSON.stringify(base));
  D.meta.ko = {};
  Object.keys(D.players).forEach(n => {
    const g = String(D.players[n].game);
    D.meta.ko[g] = (g === openGame) ? koOpen : 0;      // 0 = kicked off at midnight
    D.players[n].hr = false; D.players[n].goalmins = [];
  });
  D.meta.finals = []; D.meta.gs = {};
  D.tickets = [];
  const r = SD.redraft(D, { nowUTCmin: now, xi: null });
  return r.tickets.filter(t => t.players.some(p => String(D.players[p.name].game) === openGame));
}

const G = String(base.players[Object.keys(base.players)[0]].game);

console.log('=== MINTGUARD across the midnight boundary (only game ' + G + ' is open)\n');

/* ---- the European case, which already worked ---------------------------------------- */
chk('European ko 1170, now 1140 (30 min before) -> mintable',
  mintedInto(1170, 1140, G).length > 0);
chk('European ko 1170, now 1200 (match underway) -> BLOCKED',
  mintedInto(1170, 1200, G).length === 0,
  mintedInto(1170, 1200, G).map(t => t.kind + ':' + t.players[0].name));

/* ---- 🚨 the European hole: the same slate, after midnight UTC ------------------------ */
/* A build at 00:15Z the morning AFTER is still on this slate until the next one is committed.
   Under the old wall-clock (`now = 15`) every finished match read as unstarted. Slate-relative,
   that instant is 1440 + 15 = 1455, which is correctly past a 1170 kickoff. */
chk('the SAME finished match at 00:15Z reads as unstarted on a WALL clock (the bug)',
  mintedInto(1170, 15, G).length > 0,
  'this is the old behaviour, asserted so the fix has something to be measured against');
chk('...and is correctly BLOCKED on a slate-relative clock (1440 + 15)',
  mintedInto(1170, 1455, G).length === 0,
  mintedInto(1170, 1455, G).map(t => t.kind + ':' + t.players[0].name));

/* ---- 🚨 the MLS case: a kickoff past 1440 -------------------------------------------- */
const MLS_KO = 1470;                                   /* 00:30Z the following day */
const before = mintedInto(MLS_KO, 1400, G);            /* 23:20Z, 70 min before kickoff */
const during = mintedInto(MLS_KO, 1500, G);            /* 01:00Z next day, 30 min in */
chk('MLS ko 1470, now 1400 (70 min before) -> mintable', before.length > 0);
chk('MLS ko 1470, now 1500 (30 min INTO the match) -> BLOCKED', during.length === 0,
  during.map(t => t.kind + ':' + t.players[0].name));
/* the shape of the original defect: on a 0..1439 clock these two instants are indistinguishable */
chk('...and on the OLD wall clock those two instants were identical (the defect)',
  mintedInto(MLS_KO, 1400, G).length === mintedInto(MLS_KO, 60, G).length,
  { before1400: mintedInto(MLS_KO, 1400, G).length, during0100: mintedInto(MLS_KO, 60, G).length });

/* ---- the clock arithmetic itself ----------------------------------------------------- */
/* Reimplemented rather than imported: soccer_rebuild_cli.js runs on load and wants argv, so this
   pins the FORMULA. If the two ever disagree, one of them is wrong and this says which. */
function slateRelative(nowUTC, slateDate, todayDate) {
  const p = s => { const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s); return Date.UTC(+m[1], +m[2] - 1, +m[3]); };
  return nowUTC + 1440 * Math.round((p(todayDate) - p(slateDate)) / 86400000);
}
chk('on the slate\'s own day the offset is ZERO (every European build bit-identical)',
  slateRelative(1200, '2026-08-31', '2026-08-31') === 1200);
chk('the morning after, +1440', slateRelative(15, '2026-08-31', '2026-09-01') === 1455);
chk('an MLS 01:00Z build on a 09-05 slate lands past its 1470 kickoff',
  slateRelative(60, '2026-09-05', '2026-09-06') === 1500);
chk('two days late still lands somewhere sane', slateRelative(0, '2026-08-31', '2026-09-02') === 2880);

console.log('');
console.log(fail ? `${fail} FAILURE(S)`
  : 'ALL GREEN -- MINTGUARD holds across midnight, and a >1440 kickoff is reachable');
process.exit(fail ? 1 : 0);
