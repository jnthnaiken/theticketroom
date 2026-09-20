#!/usr/bin/env node
/* nfl_rebuild_cli.js -- a SAME-SLATE football rebuild that cannot re-draft a placed bet.
 *
 * This is soccer_rebuild_cli.js for the football room, and it exists for a reason that was
 * measured, not predicted. From claude/nfl-anchorwave-2026-09-20.md:
 *
 *   nfl-build.yml ran `node nfl_draft_cli.js` -- a FRESH DRAFT -- on every build-tick, i.e.
 *   every five minutes, all day. At 16:52Z the four 1:00 PM slips were Chase Brown/Goedert/
 *   Etienne, Chase Brown/Doubs/Smith, Monangai/Henderson/Marks and Monangai/Warren/Gainwell.
 *   At 17:23Z -- 23 minutes after those games kicked off -- every one of them had different
 *   legs. `git diff` on slates/2026-09-20/ across that build is EMPTY: same fixtures, same
 *   prices, same atd. Only the draft moved.
 *
 * soccer_rebuild_cli.js's header already said what this costs, in its own words: "a fresh
 * draft() each pass is exactly that bug: prices drift all afternoon, so the draft moves, and a
 * slip someone backed at 14:00 is quietly gone at 14:05." Football had no equivalent, so it did
 * exactly that, every five minutes, for the whole slate.
 *
 * So a rebuild does NOT re-draft. It takes the PRIOR board, refreshes what is knowable (the
 * injury report, live results), and runs SoccerDraft.redraft() -- the same function soccer
 * runs -- which freezes what is locked, mints nothing past its own kickoff, and repairs open
 * slips leg by leg.
 *
 *     node nfl_rebuild_cli.js <prior nfl_D.json> <scored.json> <out tickets.json> [--now <min>]
 *
 * ⚠️ THE CLOCK IS ET MINUTES PAST MIDNIGHT, NOT UTC. This is the one place this file must NOT
 * copy soccer. nfl/mkfixtures.py builds `kickoff` as `int(hh)*60+int(mm)` in ET (1:00 PM ET =
 * 780), while soccer_payload.et_dt() builds its kickoff as minutes past midnight UTC of the
 * slate date. redraft() compares `now` against meta.ko directly, so handing it a UTC clock
 * would put every football slip four or five hours into its own future -- every ticket frozen
 * from the first build of the morning, which looks exactly like this working and is the
 * opposite of it. The basis is asserted below rather than trusted.
 *
 * There is no first-build path here on purpose: with no prior board there is nothing to
 * preserve, and nfl_draft_cli.js is the right tool. The workflow picks between them.
 */
'use strict';
const fs = require('fs');
const path = require('path');
/* ⚠️ STAGEPATH-2026-09-20. The workflow runs this from nfl/.work, where the staging step has
   copied soccer_draft.js in FLAT (`cp ../soccer/soccer_draft.js .work/`) -- so the repo-relative
   path is wrong there and the sibling path is wrong here. nfl_draft_cli.js only ever ran staged
   and hardcodes './soccer_draft.js'; this file has to work in both, because the tests run it
   from the repo. Try the staged layout first, fall back to the repo one. */
function loadDraft() {
  const here = path.join(__dirname, 'soccer_draft.js');
  const repo = path.join(__dirname, '..', 'soccer', 'soccer_draft.js');
  return require(fs.existsSync(here) ? here : repo);
}
const SD = loadDraft();
const { CFG, applyVocabulary } = require('./nfl_cfg.js');
applyVocabulary(SD);

const args = process.argv.slice(2);
const flag = (n) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : null; };
const pos = args.filter((a, i) => !a.startsWith('--') && !(i > 0 && String(args[i - 1]).startsWith('--')));
const [PRIOR, SCORED, OUT] = pos;
if (!PRIOR || !SCORED || !OUT) {
  console.error('usage: nfl_rebuild_cli.js <prior nfl_D.json> <scored.json> <tickets.json> [--now m]');
  process.exit(2);
}

const D = JSON.parse(fs.readFileSync(PRIOR, 'utf8'));
const scored = JSON.parse(fs.readFileSync(SCORED, 'utf8'));

if (!D.meta || !D.meta.ko || !Object.keys(D.meta.ko).length) {
  console.error('!! prior board carries no meta.ko -- it cannot be re-drafted safely');
  process.exit(4);
}

/* ⚠️ ET BASIS ASSERTED, NOT ASSUMED. Every real NFL kickoff is between 09:30 ET (London) and
   20:20 ET, i.e. 570..1220. A UTC-based ko map for the same slate lands at 870..1520+ and a
   Sunday card would show a 1:00 game at 1020. If this map is not on the ET basis the clock
   below is meaningless, and a wrong clock here silently freezes the whole board. */
const koVals = Object.keys(D.meta.ko).map(k => Number(D.meta.ko[k])).filter(isFinite);
const koMax = Math.max.apply(null, koVals), koMin = Math.min.apply(null, koVals);
if (!(koMin >= 480 && koMax <= 1320)) {
  console.error(`!! meta.ko spans ${koMin}..${koMax}, which is not ET minutes past midnight `
              + `(expected 480..1320). Refusing to place the clock against it.`);
  process.exit(4);
}

/* ET minutes past midnight OF THE SLATE DATE, so a board still being rebuilt after ET midnight
   (a 20:20 kickoff runs past it) keeps counting up instead of wrapping to 0 and un-starting
   every game -- soccer's SLATECLOCK-2026-08-31, in the zone football actually uses. */
function etNow(slateDate) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).formatToParts(new Date()).reduce((a, p) => (a[p.type] = p.value, a), {});
  let h = Number(parts.hour); if (h === 24) h = 0;
  const wall = h * 60 + Number(parts.minute);
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(slateDate || ''));
  if (!m) return wall;
  const slate = Date.UTC(+m[1], +m[2] - 1, +m[3]);
  const today = Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day));
  return wall + 1440 * Math.round((today - slate) / 86400000);
}

let now;
if (flag('--now') != null) {
  now = Number(flag('--now'));
  if (!isFinite(now)) { console.error('!! --now must be a number (ET minutes past slate midnight)'); process.exit(2); }
} else {
  if (!D.meta.date) { console.error('!! no --now and the prior board carries no meta.date'); process.exit(2); }
  now = etNow(D.meta.date);
}
const hh = Math.floor(((now % 1440) + 1440) % 1440 / 60), mm = ((now % 60) + 60) % 60;
console.log(`  clock: slate ${D.meta.date}, now ${now} ET min (${hh}:${String(mm).padStart(2, '0')} ET)`
          + `  |  kickoffs ${koMin}..${koMax}`);

const koOf = g => { const v = D.meta.ko[String(g)]; return v == null ? null : Number(v); };

/* ---- refresh what is knowable ------------------------------------------------------------
 * PRICEONCE (nfl-build.yml's own header): "soccer and football price ONE TIME at build, like
 * baseball. any changes in model total would be due to live weather updates etc." So odds are
 * NOT refreshed here -- prices.json is committed and held by nfl_mock.py's merge anyway, and
 * a rebuild that re-priced would be doing by the back door what the merge forbids by the front.
 *
 * What DOES cross: `out`. INJOUT-2026-09-11 put the injury report in front of the draft after
 * Brock Bowers rode a live moon two days after being ruled Out; the same reasoning applies
 * here, and harder, because `out` is the ONLY thing standing between a rebuild and freezing a
 * slip with a dead leg on it (ticketIsLocked's `alive` guard). It only ever goes false -> true:
 * soccer's WRONGCLUB-2026-08-30 records what happens when a rebuild reads `out` off the prior
 * payload and hands a scratched man back his seat.
 */
const byName = {};
scored.forEach(p => { byName[p.name] = p; });

let newlyOut = [], held = 0, wouldMove = 0, frozenPrice = 0;
Object.keys(D.players).forEach(n => {
  const p = D.players[n], s = byName[n];
  if (!s) return;
  if (s.out && !p.out) { p.out = true; newlyOut.push(n); }
  else if (s.out) p.out = true;
  const ko = koOf(p.game);
  if (ko != null && now >= ko) { frozenPrice++; return; }   /* underway: PRICEFREEZE */
  if (p.odds !== s.odds || p.TOTAL !== Math.round((s.TOTAL || 0) * 10) / 10) wouldMove++;
  held++;
});
if (newlyOut.length) console.log(`  injury report: ${newlyOut.length} newly out -> ${newlyOut.join(', ')}`);

const before = (D.tickets || []).map(t => t.kind + ':' + t.players.map(l => l.name).join('+')).sort();

/* No xi / xiMatches: football has no team sheet. That is the whole reason LOCK_ON_KICKOFF
   exists (KICKLOCK-2026-09-20) -- `status` is 'projected' for every player on every build, so
   CONFLOCK alone can never freeze anything on this board. */
const r = SD.redraft(D, { nowUTCmin: now, cfg: CFG, xi: null, xiMatches: null });

console.log(`  price: ${held} held by PRICEONCE [${wouldMove} would have moved], ${frozenPrice} frozen (underway)`);
console.log(`  redraft: ${r.locked} locked · ${r.repaired} repaired · ${r.minted} new`
          + (r.demoted && r.demoted.length ? ` · ${r.demoted.length} demoted` : '')
          + `  -> ${r.changed ? 'CHANGED' : 'unchanged'}`);
(r.demoted || []).forEach(d => console.log(`    demoted ${d.anchor}: ${d.why}`));
(r.shaped || []).forEach(x => console.log(`    shape repair: no ${x.kind} on the board -> minted ${x.name}`));

/* The emitted shape is nfl_draft_cli.js's, because nfl_payload.py reads both from the same
   tickets.json: kind, name, badge, anchor, match, risk, legs[{name,team,match,odds,TOTAL,pos}].
   `locked` rides along -- LOCKCARRY-2026-09-20 fixed nfl_payload.py to stop hardcoding it
   False, and without the field here that fix has nothing to read. */
const out = r.tickets.map(t => {
  const legs = t.players || [];
  const anc = legs[0] || {};
  return {
    kind: t.kind,
    name: t.name,
    badge: SD.BADGE[t.kind] || t.badge || '',
    anchor: t.anchor || anc.name,
    match: (D.players[anc.name] || {}).gmatch || anc.gmatch || '',
    risk: (t.rr && t.rr.risk) || (t.kind === 'moon' ? CFG.MOON_RISK : CFG.SINGLE_STAKE),
    locked: !!t.locked,
    legs: legs.map(l => {
      const src = D.players[l.name] || {};
      return {
        name: l.name,
        team: l.team || src.team,
        match: src.gmatch || l.gmatch || '',
        odds: l.odds != null ? l.odds : src.odds,
        TOTAL: l.total != null ? l.total : src.TOTAL,
        pos: src.slot || l.pos || '',
      };
    }),
  };
});

/* Post-condition, not a hope: the same WIN check nfl_draft_cli.js runs on a fresh draft.
   A carried slip predates any config change, so a locked one is reported and kept -- it is a
   placed bet and narrowing WIN later does not un-place it -- while an OPEN slip that breaks
   the span is a live bug in the repair path and must be loud. */
let bad = 0;
out.forEach(t => {
  if (t.legs.length < 2) return;
  const ks = t.legs.map(l => koOf((D.players[l.name] || {}).game)).filter(v => v != null);
  if (!ks.length) return;
  const span = Math.max.apply(null, ks) - Math.min.apply(null, ks);
  if (span > CFG.WIN) {
    if (t.locked) console.log(`    note: locked slip ${t.name} spans ${span} min > WIN ${CFG.WIN} (carried, it is a placed bet)`);
    else { console.error(`!! OPEN slip ${t.name} spans ${span} min > WIN ${CFG.WIN}`); bad++; }
  }
});
if (bad) process.exit(6);

fs.writeFileSync(OUT, JSON.stringify(out, null, 1));
const after = out.map(t => t.kind + ':' + t.legs.map(l => l.name).join('+')).sort();
console.log(`  ${out.length} tickets written to ${OUT}`
          + `  (${out.filter(t => t.locked).length} locked)`);

/* exit 10 = the draft did not move, so the caller may skip the rest of the build. The commit
   gate still hashes scores, so a weather-only change republishes through the normal path. */
process.exit(JSON.stringify(before) === JSON.stringify(after) ? 10 : 0);
