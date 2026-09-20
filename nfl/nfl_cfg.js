#!/usr/bin/env node
/* nfl_cfg.js -- the ONE football config, shared by nfl_draft_cli.js and nfl_rebuild_cli.js.
 *
 * ⚠️ CFGDRIFT-2026-09-20. This block used to live inline in nfl_draft_cli.js. The moment a
 * second entry point existed (the rebuild, KICKLOCK-2026-09-20) an inline copy became two
 * copies of PRICECAP, FLOOR200, WIN and Z_GATE that nothing forced to agree -- and a rebuild
 * drafting to a different cap than the build it is replacing is a silent, unreviewable way to
 * put a +600 leg on a card. One file, both callers.
 *
 * The vocabulary fork is here for the same reason: NFLBADGE-2026-09-17 records that without the
 * pin every football single shipped a soccer goal, and a rebuild that mints a ticket is exactly
 * as able to ship the wrong badge as a fresh draft is.
 */
'use strict';

/* The vocabulary is the ONLY cosmetic fork. NAMES/BADGE are exported on the api object precisely
   so a second sport can re-point them without touching the draft. */
function applyVocabulary(Draft) {
  Draft.NAMES.moon = ['Six Points', 'Money Down', 'The Pylon', 'Front of the End Zone', 'Play Action',
                      'Goal to Go', 'The Fade', 'Crossing Route', 'Chunk Play', 'Twelve Personnel',
                      'Empty Backfield', 'The Rollout'];
  Draft.NAMES.builder = ['The Workhorse', 'Bell Cow', 'Goal Line Back', 'Red Zone Target',
                         'Short Yardage', 'The Checkdown', 'First Read', 'Move the Chains',
                         'Inside the Ten', 'The Sneak'];
  Draft.NAMES.lunch = ['The One O’Clock', 'Early Window', 'First Wave', 'Sunday Opener'];
  Draft.NAMES.late  = ['Sunday Night', 'Under Lights', 'Prime Time', 'The Late Window'];
  Draft.BADGE.moon = '🏈';        /* 🏈 -- the soccer fork re-skins 🚀 -> 💥, same seam */
  /* NFLBADGE-2026-09-17: football singles keep the anchor. soccer_draft.js now defaults builder to 🥅
     (the soccer Top Bin, TOPBIN-2026-09-17), and without this pin every NFL single shipped a soccer
     goal. Pin the whole football vocabulary here so a soccer re-skin can never leak across again. */
  Draft.BADGE.builder = '⚓️';
  Draft.BADGE.lunch = '🍱';
  Draft.BADGE.late = '🌃';
  return Draft;
}

const CFG = {
  WIN: 60, Z_GATE: 0.55, GAME_CAP: 5,
  ANCH: 4, MOON_LEGS: 3, MOONS_PER_ANC: 2, ANCH_PER_GAME: 2,
  MOON_RISK: 2.0, SINGLE_STAKE: 1.0,
  /* PRICECAP-2026-09-15 -- nothing longer than MAX_ODDS is draftable, anchor, leg or single.
     +500 at first; +400 the same day, owner's call on the NFL backtest (nfl/backtest/
     RESULTS-2026-09-15.md: pooled ROI +400 -0.2% vs +500 -3.7%, within noise of each other).
     Week 1 under EV ranking drafted +320..+1000 on Sunday and +1100..+2200 on Monday night and
     the moons went 0-8 (-16u). With MIN_ODDS 100 (soccer_draft DEFAULTS) the football card is
     +100..+400. A judgement call, not a fit: replaying week 1's singles, +400/+500/+600/+800
     caps land anywhere from -3.7u to +5.4u on 20 picks, which is noise. Revisit once
     nfl_ev_fit.py has enough graded weeks to calibrate the long end properly. */
  MAX_ODDS: 400,
  /* FLOOR200-2026-09-17 -- soccer_draft DEFAULTS.MIN_ODDS moved to -200 for SOCCER. Football keeps
     the owner's +100 floor (PLUSMONEY-2026-09-11), so it is pinned here rather than inherited. */
  MIN_ODDS: 100,
  /* TOP8-2026-09-17: the top-N singles board is SOCCER only; football keeps anchors + moons. */
  TOP_SINGLES: 0,
  /* KICKLOCK-2026-09-20 -- football runs the `started` half of index.html's pinnedP().
     Soccer leaves this off (STANDASIS-2026-08-29: a published XI is the better signal there).
     Football has no team sheet, so `status` is 'projected' on every build and CONFLOCK can
     never fire -- without this nothing on the board can lock, which is how the 1:00 slips were
     re-drafted 23 minutes after kickoff on 2026-09-20. The `!out && !void` guard in
     ticketIsLocked() is what keeps a dead leg repairable; see nfl/test_nfl_kicklock.js. */
  LOCK_ON_KICKOFF: true,
};

module.exports = { CFG: CFG, applyVocabulary: applyVocabulary };
