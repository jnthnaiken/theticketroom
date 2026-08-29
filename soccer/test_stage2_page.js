/* test_stage2_page.js -- the live re-draft, IN THE BUILT PAGE, under a frozen clock.
 *
 * The unit tests (test_redraft.js) prove the rules. This proves the WIRING: that soccer_draft.js
 * is actually reachable inside soccer/index.html, that soccerRedraft() is called by the live
 * loop, that its three guards fire in the right order, and that a board on screen moves when
 * team news lands and stops moving at kickoff.
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

async function run(atISO, publish, dropped, label) {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1280, height: 1000 } });

  await ctx.addInitScript(`(()=>{const F=new Date('${atISO}').getTime(),R=Date;
     class D extends R{constructor(...a){if(!a.length)super(F);else super(...a);}static now(){return F;}}
     window.Date=D;})();`);

  const payload = { publish, dropped, byGame, evToGame, DATE };
  await ctx.addInitScript(`window.__STUB=${JSON.stringify(payload)};
    (()=>{
      const S=window.__STUB;
      function squad(g){
        if(!S.publish) return [];
        const names=S.byGame[g]||[]; const half=Math.ceil(names.length/2);
        const mk=list=>list.filter(n=>!S.dropped[n]).map((n,i)=>({athlete:{displayName:n},starter:true}));
        return [{team:{abbreviation:'H'+g},roster:mk(names.slice(0,half))},
                {team:{abbreviation:'A'+g},roster:mk(names.slice(half))}];
      }
      window.__espnCalls=0;
      window.fetch=function(u){
        u=String(u);
        if(u.indexOf('espn')>=0) window.__espnCalls++;
        let body={};
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

  await p.goto('file://' + FILE, { waitUntil: 'load' });
  /* tag the ticket objects the way the 2026-08-26 audit did */
  await p.evaluate(() => { (D.tickets || []).forEach((t, i) => { t.__probe = 'probe' + i; }); });
  const before = await p.evaluate(() => (D.tickets || []).map(t => ({
    name: t.name, kind: t.kind, probe: t.__probe, legs: t.players.map(l => l.name)
  })));

  await p.evaluate(() => (typeof soccerLive === 'function' ? soccerLive() : null));
  await p.waitForTimeout(1200);

  const espnCalls = await p.evaluate(() => window.__espnCalls || 0);
  const after = await p.evaluate(() => (D.tickets || []).map(t => ({
    name: t.name, kind: t.kind, probe: t.__probe, locked: !!t.locked, legs: t.players.map(l => l.name)
  })));
  const statuses = await p.evaluate(() => {
    const o = {};
    Object.keys(D.players).forEach(n => { o[n] = D.players[n].status + (D.players[n].out ? '!' : ''); });
    return o;
  });

  await b.close();
  return { before, after, statuses, errs, net, espnCalls };
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
   *    The board must repair that slip: anchor kept, healthy partner pinned, dead leg swapped.
   * ----------------------------------------------------------------------------------- */
  {
    const dropped = {}; dropped[DEAD] = true;
    const r = await run(`${DATE}T18:00:00Z`, true, dropped, 'team-news');
    console.log('\n--- 2. team news lands an hour before kickoff ---');
    chk('no page errors', r.errs.length === 0, r.errs);
    chk('the dropped man is marked out of the squad', /!$/.test(r.statuses[DEAD] || ''), r.statuses[DEAD]);
    /* the boot pass fires before the tag can be applied, so the witness is the BAKED payload */
    chk('the board moved off the baked draft', legsOf(r.after) !== BAKED, r.after.map(t => t.legs));
    chk('ESPN was read', r.espnCalls > 0, r.espnCalls);

    const same = r.after.find(t => t.name === target.name);
    chk('the repaired slip kept its name', !!same, r.after.map(t => t.name));
    if (same) {
      chk('the anchor survived', same.legs.indexOf(ANCHOR) >= 0, same.legs);
      chk('the healthy partner stayed pinned', same.legs.indexOf(KEEP) >= 0, same.legs);
      chk('the dead leg was replaced, not dropped', same.legs.length === 3 && same.legs.indexOf(DEAD) < 0, same.legs);
    }
    chk('the dead leg is on no slip at all',
      !r.after.some(t => t.legs.indexOf(DEAD) >= 0), r.after.map(t => t.legs));
    chk('every remaining leg is a confirmed starter',
      r.after.every(t => t.legs.every(n => r.statuses[n] === 'confirmed')),
      r.after.map(t => t.legs.map(n => n + '=' + r.statuses[n])));
  }

  /* -------------------------------------------------------------------------------------
   * 3. After kickoff. Team news is in, but every slip is frozen and MINTGUARD is shut.
   * ----------------------------------------------------------------------------------- */
  {
    const dropped = {}; dropped[DEAD] = true;
    const r = await run(`${DATE}T19:30:00Z`, true, dropped, 'post-kickoff');
    console.log('\n--- 3. thirty minutes after kickoff ---');
    chk('no page errors', r.errs.length === 0, r.errs);
    chk('TICKET OBJECTS SURVIVED (nothing re-drafted after kickoff)',
      r.after.every((t, i) => t.probe === 'probe' + i), r.after.map(t => t.probe));
    chk('the board still matches the baked draft even though a leg is out of the squad',
      legsOf(r.after) === BAKED, r.after.map(t => t.legs));
    chk('the out player is STILL on his slip -- a placed bet is not unwound, it is graded',
      r.after.some(t => t.legs.indexOf(DEAD) >= 0), DEAD);
  }

  console.log('');
  console.log(fail ? `${fail} FAILURE(S)` : 'ALL GREEN -- Stage 2 works in the built page');
  process.exit(fail ? 1 : 0);
})();
