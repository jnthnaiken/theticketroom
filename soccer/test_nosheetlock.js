#!/usr/bin/env node
/* test_nosheetlock.js -- NOSHEETLOCK-2026-09-22.
 *
 * WHY. CONFLOCK freezes a soccer slip when EVERY leg reaches status 'confirmed', which happens
 * when the club team sheet lands ~1h before kickoff. soccer_teamnews.py scrapes club leagues.
 * Nothing scrapes a national squad -- so with INTL-2026-09-22 coverage, a leg in an
 * international fixture never reaches 'confirmed', `allConf` is permanently unreachable, and
 * the slip NEVER FREEZES. It would still be re-drafting itself through its own kickoff, which
 * is the football bug of 2026-09-20 arriving in the other room:
 *
 *     "At 17:23Z -- 23 minutes AFTER those games kicked off -- every one of them had
 *      different legs, off byte-identical slate inputs."   (claude/nfl-anchorwave-2026-09-20)
 *
 * KICKLOCK framed the kickoff test as opt-in PER ROOM. That framing was true when the rooms
 * were the whole story and is not any more. The rule underneath is per FIXTURE:
 *
 *     a slip that can never become fully confirmed must freeze on the clock instead.
 *
 * WHAT IS PINNED:
 *   1. an all-international slip freezes at its first kickoff, with no team sheet anywhere
 *   2. a MIXED slip freezes too -- `some`, not `every`. One unconfirmable leg is enough to put
 *      allConf out of reach forever, and a mixed slip is exactly the one that would otherwise
 *      churn. Getting this backwards is a silent bug: the common case still passes.
 *   3. it is NOT a free pass past the `alive` guard -- a dead leg still refuses to freeze,
 *      which is the STANDASIS-2026-08-29 hazard the kickoff branch was deleted for once already
 *   4. BEFORE kickoff nothing changes -- the slip stays open and re-draftable
 *   5. a board with no meta.nosheet is byte-identical, which is what keeps every club board and
 *      every archived board behaving exactly as it did
 *
 * ⚠️ Run against the pre-NOSHEETLOCK soccer_draft.js and 1, 2 and 6 fail; 3, 4, 5 and 7 pass
 * either way, and that is deliberate -- they are the controls that say nothing else moved.
 *
 *     node test_nosheetlock.js
 */
'use strict';
const path = require('path');
const SD = require(path.join(__dirname, 'soccer_draft.js'));

let fail = 0;
function chk(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`);
  if (!ok) { fail++; console.log(`      got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`); }
}

/* A two-game slate. Game 1 kicks at 1000, game 2 at 1030.
   `nosheet` marks game 2 as a competition with no team-news source. */
function board(opts) {
  opts = opts || {};
  const mk = (name, game, status, dead) => ({
    name, game, status: status || 'projected',
    out: dead === 'out', void: dead === 'void', odds: 200, TOTAL: 100,
  });
  const D = {
    meta: { ko: { '1': 1000, '2': 1030 } },
    players: {
      ClubA: mk('ClubA', 1, opts.clubStatus),
      ClubB: mk('ClubB', 1, opts.clubStatus),
      IntlA: mk('IntlA', 2, 'projected', opts.intlDead),
      IntlB: mk('IntlB', 2, 'projected'),
    },
  };
  if (opts.nosheet !== false) D.meta.nosheet = { '2': true };
  return D;
}
const ticket = (names) => ({ kind: 'builder', name: 'T', players: names.map(n => ({ name: n })) });
const koOf = (g) => ({ '1': 1000, '2': 1030 }[String(g)]);

/* The engine does not export ticketIsLocked, so drive it through redraft(), which is how the
   rule is actually reached on a live board.
   ⚠️ ASSERT ON r.locked (the FROZEN COUNT), not on the emitted ticket's own flag. An OPEN slip
   is re-drafted, and on a four-man stub that usually means it is demoted and never appears in
   r.tickets at all -- so `tickets.find(...)` returns undefined for "not frozen" AND for "the
   engine threw it away", which are not the same answer. The first cut of this file read the
   flag and reported `null` on four of seven cases. */
function frozenCount(D, t, now) {
  const r = SD.redraft(
    Object.assign({}, D, { tickets: [t] }),
    { nowUTCmin: now, cfg: { LOCK_ON_KICKOFF: false }, xi: null, xiMatches: null }
  );
  return r.locked;
}
const lockedAt = (D, t, now) => frozenCount(D, t, now) === 1;

/* 1 -- an all-international slip freezes at its own first kickoff. */
chk('an all-international slip locks once its game starts',
    lockedAt(board(), ticket(['IntlA', 'IntlB']), 1031), true);

/* 2 -- THE ONE THAT IS EASY TO GET BACKWARDS. A mixed slip has one leg that can never confirm,
       so allConf is unreachable forever -- it must use the clock too. */
chk('a MIXED club+international slip locks as well (some, not every)',
    lockedAt(board(), ticket(['ClubA', 'IntlA']), 1031), true);

/* 3 -- the alive guard still governs both halves. STANDASIS-2026-08-29. */
chk('a dead leg still refuses to freeze, underway or not',
    lockedAt(board({ intlDead: 'out' }), ticket(['IntlA', 'IntlB']), 1031), false);
chk('...and a voided one likewise',
    lockedAt(board({ intlDead: 'void' }), ticket(['IntlA', 'IntlB']), 1031), false);

/* 4 -- before kickoff it is an ordinary open slip. */
chk('before kickoff an international slip is NOT locked',
    lockedAt(board(), ticket(['IntlA', 'IntlB']), 900), false);

/* 5 -- CONFLOCK is untouched where it can still fire. */
chk('an all-club slip with confirmed legs still locks the old way',
    lockedAt(board({ clubStatus: 'confirmed' }), ticket(['ClubA', 'ClubB']), 900), true);

/* 6 -- the first kickoff is the trigger, not the last. Game 1 has started, game 2 has not. */
chk('a mixed slip locks on the EARLIEST kickoff among its legs',
    lockedAt(board(), ticket(['ClubA', 'IntlA']), 1001), true);

/* 7 -- THE CONTROL. No meta.nosheet: a club board behaves exactly as before. */
chk('with no meta.nosheet nothing locks on the clock',
    lockedAt(board({ nosheet: false }), ticket(['IntlA', 'IntlB']), 1031), false);

console.log('');
if (fail) { console.error(`${fail} FAILED`); process.exit(1); }
console.log('ALL GREEN -- a slip that can never be confirmed freezes on the clock, and nothing '
          + 'else moved');
