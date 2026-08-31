/* test_stage2_page.js -- THE PAGE DOES NOT DRAFT, IN THE BUILT PAGE, under a frozen clock.
 *
 * 🚨 REWRITTEN FOR ONEAUTHOR-2026-08-30. This file used to prove the opposite: that
 * soccerRedraft() was wired into the live loop and that the board on screen MOVED when team news
 * landed. That was STAGE2-2026-08-27's contract and it is retired. Owner, after betting a slip
 * the server did not hold: "the page and server evaluate at different instants with different
 * team news, so their frozen sets can still differ, yea this doesnt work for me, fix it".
 *
 * The contract now: the server is the only author of the board. The page renders what was
 * published, adopts a newer published board when one appears, and never mints, repairs or tops
 * up a slip of its own. What this file proves is that the page LEAVES THE BOARD ALONE while the
 * live loop does its other work -- results, goal minutes, confirmed/out status, the renderer --
 * and that adoption swaps the board without eating a bet.
 *
 * The audit method is unchanged and is the whole point: TAG THE ACTUAL TICKET OBJECTS. A
 * signature comparison would pass a re-draft that happened to reproduce the same slips; a tag
 * that survives proves the array was never replaced.
 *
 * This is the check the 2026-08-26 audit asked for. That audit's method is the one used here:
 * TAG THE ACTUAL TICKET OBJECTS. A signature comparison would pass a re-draft that happened to
 * reproduce the same slips; a tag that survives proves the array was never replaced.
 *
 * ESPN is stubbed, so nothing here touches the network. The clock is frozen per scenario, so
 * this test means the same thing whenever it is run.
 *
 *   node test_stage2_page.js <built.html> <payload.json>
 */
const { chromium } = require('playwright');
const fs = require('fs');

/* TESTPIN-2026-08-28. These used to default to /tmp/stage2_pre.html and /tmp/pre_D.json --
   files nothing in the repo creates. Run without arguments, the test died on ENOENT with a raw
   stack trace before a single assertion executed, which is how it sat "failing" on main without
   anyone learning anything from it. It now builds its own page from the PINNED fixture (the same
   one test_redraft.js and test_draft_golden.js use) via soccer_fork.py, exactly as the workflow
   does. Explicit arguments still override, so a built board can still be pointed at. */
const path = require('path');
const { execFileSync } = require('child_process');
const FIXTURE = path.join(__dirname, 'fixtures', '2026-08-26', 'soccer_D.json');
let FILE = process.argv[2], PAYLOAD = process.argv[3];
if (!FILE || !PAYLOAD) {
  PAYLOAD = PAYLOAD || FIXTURE;
  FILE = FILE || path.join(require('os').tmpdir(), 'stage2_pre_fixture.html');
  const base = path.join(__dirname, '..', 'index.html');
  if (!fs.existsSync(base)) {
    console.error('!! ' + base + ' is missing -- cannot fork a soccer page to test');
    process.exit(2);
  }
  execFileSync('python3', [path.join(__dirname, 'soccer_fork.py'), base, PAYLOAD, FILE],
               { cwd: __dirname, stdio: 'inherit' });
}
const D0 = JSON.parse(fs.readFileSync(PAYLOAD, 'utf8'));
const KO = 19 * 60;                                   // every match kicks off 19:00Z
const DATE = D0.meta.date;

/* STAGE2KO-2026-08-29 -- THE FORKED PAGE HAD NO KICKOFFS, so the live loop never reached the
 * drafter and scenario 2 could not possibly pass. Dumping D.meta out of the running page gave
 * `date, finals, gs` and no `ko`, and soccerRedraft()'s first guard is
 *     if(!D.meta.ko||!Object.keys(D.meta.ko).length) return;   // board baked before STAGE2
 * The pinned fixture is 2026-08-26 and boards baked before STAGE2-2026-08-27 carry no meta.ko --
 * test_redraft.js documents exactly this and synthesises them in three lines. This file already
 * declares KO above and builds all three scenario clocks from it; it simply never wrote the value
 * into the payload it forks from, so it has been asking the page to repair a board an hour before
 * a kickoff the page did not know about.
 * The FIXTURE ON DISK IS NOT TOUCHED -- it is the committed artifact and immutable by design
 * (TESTPIN-2026-08-28). The kickoffs go into a temp copy, and that copy is what is forked. */
if (!D0.meta.ko || !Object.keys(D0.meta.ko).length) {
  D0.meta.ko = {};
  Object.keys(D0.players).forEach(n => { D0.meta.ko[String(D0.players[n].game)] = KO; });
  PAYLOAD = path.join(require('os').tmpdir(), 'stage2_payload_ko.json');
  fs.writeFileSync(PAYLOAD, JSON.stringify(D0));
  console.log(`  (kickoffs synthesised at 19:00Z for ${Object.keys(D0.meta.ko).length} matches -- `
    + `the pinned 2026-08-26 board predates STAGE2 and carries none)`);
  execFileSync('python3', [path.join(__dirname, 'soccer_fork.py'), path.join(__dirname, '..', 'index.html'),
                           PAYLOAD, FILE], { cwd: __dirname, stdio: 'inherit' });
}

/* every board name, grouped by game, so the stub can publish a real-looking team sheet */
const byGame = {};
Object.keys(D0.players).forEach(n => {
  const g = D0.players[n].game;
  (byGame[g] = byGame[g] || []).push(n);
});
const EV = D0.meta.espn;
const evToGame = {};
Object.keys(EV).forEach(g => { evToGame[EV[g].ev] = Number(g); });

/* the leg we are going to drop out of the squad */
const target = D0.tickets.find(t => t.kind === 'moon');
const ANCHOR = target.players[0].name;
const KEEP = target.players[1].name;
const DEAD = target.players[2].name;

function squadFor(g, publish, dropped) {
  if (!publish) return [];
  const names = byGame[g];
  const half = Math.ceil(names.length / 2);
  const mk = (list, start) => list.map((n, i) => ({
    athlete: { displayName: n },
    starter: !dropped[n] && (start ? i < 11 : i < 11)
  })).filter(p => !dropped[p.athlete.displayName]);
  return [
    { team: { abbreviation: 'H' + g }, roster: mk(names.slice(0, half), true) },
    { team: { abbreviation: 'A' + g }, roster: mk(names.slice(half), true) }
  ];
}

let fail = 0;
const chk = (label, ok, detail) => {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`);
  if (!ok) { fail++; if (detail !== undefined) console.log('      ' + JSON.stringify(detail)); }
};

async function run(atISO, publish, dropped, label, serveBoard, pre, pageFile) {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1280, height: 1000 } });

  await ctx.addInitScript(`(()=>{const F=new Date('${atISO}').getTime(),R=Date;
     class D extends R{constructor(...a){if(!a.length)super(F);else super(...a);}static now(){return F;}}
     window.Date=D;})();`);

  const payload = { publish, dropped, byGame, evToGame, DATE, serveBoard: serveBoard || null };
  await ctx.addInitScript(`window.__STUB=${JSON.stringify(payload)};
    (()=>{
      const S=window.__STUB;
      /* TRUSTPARITY-2026-08-31. This stub's job, per the comment on byGame above, is to
         "publish a real-looking team sheet". It used to emit only the PRICED names in the game
         -- eight and seven a side on the pinned fixture -- and soccer_live.js believed it,
         because squadOf() asked only that both rosters be non-empty. It now holds the server's
         bar (TRUST-2026-08-25: eleven starters a side), so a seven-man sheet is correctly
         disbelieved and nobody is marked out of squad.
         That is the fix working, not a regression. ESPN fills 'rosters' with the matchday squad
         while every starter flag is still false, and believing THAT is what showed Raphinha
         benched while he was starting -- and, one branch lower, is what let a one-name stub
         assert 'out' on a man who was playing. (No backticks in here: this whole stub lives
         inside a template literal.) So pad each side to a real XI. The filler names
         cannot collide with the priced field, so matchOne() ignores them and the scenario under
         test -- does the PAGE re-draft when a man is dropped -- is unchanged. */
      function squad(g){
        if(!S.publish) return [];
        const names=S.byGame[g]||[]; const half=Math.ceil(names.length/2);
        const mk=(list,side)=>{
          const r=list.filter(n=>!S.dropped[n]).map(n=>({athlete:{displayName:n},starter:true}));
          for(let i=r.length;i<11;i++) r.push({athlete:{displayName:'Reserve '+side+g+' '+i},starter:true});
          return r;
        };
        return [{team:{abbreviation:'H'+g},roster:mk(names.slice(0,half),'H')},
                {team:{abbreviation:'A'+g},roster:mk(names.slice(half),'A')}];
      }
      window.__espnCalls=0;
      window.__boardCalls=0;
      window.fetch=function(u){
        u=String(u);
        if(u.indexOf('espn')>=0) window.__espnCalls++;
        let body={};
        if(u.indexOf('soccer_D.json')>=0){
          window.__boardCalls++;
          if(!S.serveBoard) return Promise.resolve({ok:false,status:404,json:()=>Promise.resolve(null)});
          return Promise.resolve({ok:true,status:200,json:()=>Promise.resolve(S.serveBoard)});
        }
        if(u.indexOf('/scoreboard')>=0){
          body={events:Object.keys(S.evToGame).map(ev=>({
            id:ev,status:{type:{completed:false,state:'pre'}},
            competitions:[{competitors:[{homeAway:'home',score:'0'},{homeAway:'away',score:'0'}]}]
          }))};
        } else if(u.indexOf('/summary')>=0){
          const m=u.match(/event=(\\d+)/); const g=m?S.evToGame[m[1]]:null;
          body={keyEvents:[],rosters:squad(g)};
        }
        return Promise.resolve({ok:true,status:200,json:()=>Promise.resolve(body)});
      };
    })();`);

  const p = await ctx.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push(String(e).slice(0, 200)));
  const net = [];
  p.on('request', r => { const u = r.url(); if (!u.startsWith('file:')) net.push(u.slice(0, 80)); });

  await p.goto('file://' + (pageFile || FILE), { waitUntil: 'load' });
  /* tag the ticket objects the way the 2026-08-26 audit did */
  await p.evaluate(() => { (D.tickets || []).forEach((t, i) => { t.__probe = 'probe' + i; }); });
  const before = await p.evaluate(() => (D.tickets || []).map(t => ({
    name: t.name, kind: t.kind, probe: t.__probe, legs: t.players.map(l => l.name)
  })));

  if (pre) await p.evaluate(pre);
  /* ⚠️ CLOSURE-2026-08-30. This used to read
       await p.evaluate(() => (typeof soccerLive === 'function' ? soccerLive() : null));
     and it has NEVER ONCE FIRED. soccerLive() lives inside the page's module closure, so at
     global scope `typeof soccerLive` is 'undefined' and the ternary quietly evaluated to null.
     Every scenario in this file has only ever observed the BOOT pass, which the LIVELOOP seam
     starts on its own (`soccerLive(); setInterval(soccerLive, 3*60*1000)`). That is the right
     thing to observe -- it is what a reader's tab actually does -- so the call is gone rather
     than replaced, and the waits below are what give the boot pass time to finish. */
  await p.waitForTimeout(1200);

  const espnCalls = await p.evaluate(() => window.__espnCalls || 0);
  const boardCalls = await p.evaluate(() => window.__boardCalls || 0);
  const build = await p.evaluate(() => (D.meta && D.meta.build) || null);
  const after = await p.evaluate(() => (D.tickets || []).map(t => ({
    name: t.name, kind: t.kind, probe: t.__probe, locked: !!t.locked, legs: t.players.map(l => l.name)
  })));
  const statuses = await p.evaluate(() => {
    const o = {};
    Object.keys(D.players).forEach(n => { o[n] = D.players[n].status + (D.players[n].out ? '!' : ''); });
    return o;
  });

  await b.close();
  return { before, after, statuses, errs, net, espnCalls, boardCalls, build };
}

const BAKED = JSON.stringify(D0.tickets.map(t => t.players.map(l => l.name)));
const legsOf = after => JSON.stringify(after.map(t => t.legs));

(async () => {
  console.log(`board: ${D0.tickets.length} slips · anchor under test ${ANCHOR} · dropping ${DEAD}\n`);

  /* -------------------------------------------------------------------------------------
   * 1. Five hours out, no team sheets published. The loop runs; the draft must NOT.
   * ----------------------------------------------------------------------------------- */
  {
    const r = await run(`${DATE}T14:00:00Z`, false, {}, 'pre-publish');
    console.log('--- 1. loop runs, no team news published yet ---');
    chk('no page errors', r.errs.length === 0, r.errs);
    chk('the loop actually called ESPN', r.espnCalls > 0, r.espnCalls);
    chk('TICKET OBJECTS SURVIVED (no re-draft)',
      r.after.every((t, i) => t.probe === 'probe' + i) && r.after.length === r.before.length,
      r.after.map(t => t.probe));
    chk('the board still matches the baked payload', legsOf(r.after) === BAKED, r.after.map(t => t.legs));
  }

  /* -------------------------------------------------------------------------------------
   * 2. One hour out, sheets published, one baked leg is NOT in the squad.
   *    ONEAUTHOR: the page MARKS him out and leaves the board alone. Replacing him is the
   *    server's job on its next build; until then the card renders its own
   *    "🪑 Out of lineup: X — will not hit as built" banner, so the reader sees the dead leg
   *    rather than a silently different bet.
   * ----------------------------------------------------------------------------------- */
  {
    const dropped = {}; dropped[DEAD] = true;
    const r = await run(`${DATE}T18:00:00Z`, true, dropped, 'team-news');
    console.log('\n--- 2. team news lands an hour before kickoff ---');
    chk('no page errors', r.errs.length === 0, r.errs);
    chk('ESPN was read', r.espnCalls > 0, r.espnCalls);
    chk('the dropped man is marked out of the squad', /!$/.test(r.statuses[DEAD] || ''), r.statuses[DEAD]);
    chk('THE PAGE DID NOT RE-DRAFT -- board still matches the published one',
      legsOf(r.after) === BAKED, r.after.map(t => t.legs));
    chk('TICKET OBJECTS SURVIVED -- the array was never replaced',
      r.after.every((t, i) => t.probe === 'probe' + i) && r.after.length === r.before.length,
      r.after.map(t => t.probe));
    chk('the dropped man is still ON his slip, visible, not swapped behind the reader',
      r.after.some(t => t.legs.indexOf(DEAD) >= 0), r.after.map(t => t.legs));
  }

  /* -------------------------------------------------------------------------------------
   * 3. After kickoff, same picture. Nothing about the clock lets the page start drafting.
   * ----------------------------------------------------------------------------------- */
  {
    const dropped = {}; dropped[DEAD] = true;
    const r = await run(`${DATE}T19:30:00Z`, true, dropped, 'post-kickoff');
    console.log('\n--- 3. thirty minutes after kickoff ---');
    chk('no page errors', r.errs.length === 0, r.errs);
    chk('the board is still the published one', legsOf(r.after) === BAKED, r.after.map(t => t.legs));
    chk('TICKET OBJECTS SURVIVED', r.after.every((t, i) => t.probe === 'probe' + i),
      r.after.map(t => t.probe));
    chk('nothing was minted', r.after.length === r.before.length,
      { after: r.after.length, before: r.before.length });
  }

  /* -------------------------------------------------------------------------------------
   * 4. ADOPTION. A newer board is published while the tab is open.
   *
   * This is the half ADOPTFILE-2026-08-17 could not have: deploy-pages.yml refused to stage the
   * board file "UNTIL adoption MERGES INSTEAD OF REPLACING", because `D.tickets = j.tickets`
   * deleted a CONFIRMED slip out of a live tab. With the page no longer drafting, the tab can
   * only be holding slips the server also holds -- but the carry is asserted here anyway, and
   * loudly, because that is the failure that cost a bet.
   * ----------------------------------------------------------------------------------- */
  {
    /* The tab loads a board with one slip LOCKED. The server then publishes a board that has
       moved on AND does not carry that slip. Adoption must take the new board and keep the bet. */
    const bakedLocked = JSON.parse(JSON.stringify(D0));
    const bet = bakedLocked.tickets[bakedLocked.tickets.length - 1];
    bet.locked = true;
    const lockedPage = path.join(require('os').tmpdir(), 'stage2_adopt_fixture.html');
    const lockedPayload = path.join(require('os').tmpdir(), 'stage2_adopt_payload.json');
    fs.writeFileSync(lockedPayload, JSON.stringify(bakedLocked));
    execFileSync('python3', [path.join(__dirname, 'soccer_fork.py'),
                             path.join(__dirname, '..', 'index.html'), lockedPayload, lockedPage],
                 { cwd: __dirname, stdio: 'ignore' });

    const served = JSON.parse(JSON.stringify(D0));
    served.meta.build = 'TEST-NEWER-BUILD';
    served.tickets = served.tickets.slice(0, -1);        /* the bet is NOT on the new board */

    const r = await run(`${DATE}T18:00:00Z`, true, {}, 'adopt', served, null, lockedPage);

    console.log('\n--- 4. a newer board is published while the tab is open ---');
    chk('no page errors', r.errs.length === 0, r.errs);
    chk('the page asked for the published board', r.boardCalls > 0, r.boardCalls);
    chk('ADOPTED -- the tab is now on the newly published build',
      r.build === 'TEST-NEWER-BUILD', { build: r.build });
    chk('THE LOCKED SLIP THE NEW BOARD OMITTED WAS KEPT -- a placed bet is never adopted away',
      r.after.some(t => t.name === bet.name), { bet: bet.name, on: r.after.map(t => t.name) });
    chk('and nothing else was invented alongside it',
      r.after.length === served.tickets.length + 1,
      { after: r.after.length, served: served.tickets.length });
  }

  console.log('');
  console.log(fail ? `${fail} FAILURE(S)` : 'ALL GREEN -- the page renders the published board and never authors one');
  process.exit(fail ? 1 : 0);
})();
