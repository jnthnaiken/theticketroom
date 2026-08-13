#!/usr/bin/env node
/* client_assemble.js -- run the REAL assembleClient out of index.html under a pinned clock.
 *
 *   node client_assemble.js <index.html> [--from HH:MM] [--to HH:MM] [--step MIN] [--date YYYY-MM-DD]
 *
 * Loads the page in headless Chromium with ALL network blocked, so the board that runs is exactly
 * the one baked into the file. Chains the sweep: each step's output board is fed in as the next
 * step's prior, which is the only way the lock/merge/shrink-guard paths get exercised.
 *
 * Asserts at every step:
 *   1. ticket count (total + per kind)          -- both 08-09 bugs left every slip individually fine
 *   2. locked-slip integrity                    -- nothing locked vanishes or changes legs
 *   3. builders == parlay anchors               -- claude/anchors-invariant-2026-08-09.md
 *   4. moon pairing                             -- each anchor's moons form ONE contiguous run
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const argv = process.argv.slice(2);
const SRC = argv[0];
const opt = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };
if (!SRC) { console.error('usage: client_assemble.js <index.html> [--from HH:MM] [--to HH:MM] [--step MIN]'); process.exit(2); }

const DATE = opt('date', '2026-08-11');
const hhmm = s => { const p = s.split(':'); return (+p[0]) * 60 + (+p[1]); };
const mmss = m => String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0');
const FROM = hhmm(opt('from', '17:30'));
const TO = hhmm(opt('to', '23:00'));
const STEP = +opt('step', 20);

// ---- build the instrumented copy: expose assembleClient + a pristine snapshot of the baked board ----
const raw = fs.readFileSync(SRC, 'utf8');
const lines = raw.split('\n');

let dLine = lines.findIndex(l => l.startsWith('const D={'));
if (dLine < 0) throw new Error('could not find the embedded `const D={...}` board');
lines.splice(dLine + 1, 0, 'globalThis.__D=D;globalThis.__D0=JSON.parse(JSON.stringify(D.tickets));');

let acScope = lines.findIndex(l => /^\s*function assembleClient\(D\)\{/.test(l));
if (acScope < 0) throw new Error('could not find assembleClient');
// function declarations hoist, so exporting from the top of the enclosing IIFE is safe
let iife = acScope; while (iife > 0 && lines[iife].trim() !== '(function(){') iife--;
lines.splice(iife + 1, 0, '  try{globalThis.__ac=assembleClient;}catch(e){}');

const TESTFILE = path.resolve(path.dirname(SRC), '.client_assemble.test.html');
fs.writeFileSync(TESTFILE, lines.join('\n'));

// ---- invariants ----
const INVARIANTS = `
function gmin(gt){var m=/(\\d+):(\\d+)\\s*(AM|PM)/.exec(gt||'');if(!m)return 0;var h=(+m[1])%12+(m[3]=='PM'?12:0);return h*60+(+m[2]);}
function sig(t){return t.kind+'|'+(t.players||[]).map(function(l){return l.name;}).slice().sort().join(',');}
function counts(ts){var c={_total:ts.length};ts.forEach(function(t){c[t.kind]=(c[t.kind]||0)+1;});return c;}
function pairing(ts){
  // every anchor's moons must occupy ONE contiguous run in board order
  var seq=ts.filter(function(t){return t.kind==='moon';}).map(function(t){return t.anchor;});
  var runs={},bad=[],last=null;
  seq.forEach(function(a){ if(a!==last){ if(runs[a]) bad.push(a); runs[a]=1; last=a; } });
  return {seq:seq,bad:bad.filter(function(v,i,s){return s.indexOf(v)===i;})};
}
function structural(ts){
  // 2026-08-13: a ticket must be a WHOLE ticket. moon>=3 legs, salami>=4, and players must never be
  // shorter than the nlegs it advertises. The published 08-13 board shipped a 1-leg Grand Salami
  // carrying nlegs:4 (anchor-dedup rewrote t.players, the "keep prior intact" revert shipped the stub).
  var bad=[];
  ts.forEach(function(t){
    var n=(t.players||[]).length;
    if(t.kind==='moon'&&n<3)bad.push(t.name+' moon has '+n+' legs');
    else if(t.kind==='biggest'&&n<4)bad.push(t.name+' salami has '+n+' legs');
    else if(n<1)bad.push(t.name+' has no legs');
    if(t.nlegs&&n<t.nlegs)bad.push(t.name+' players='+n+' < nlegs='+t.nlegs);
  });
  return bad;
}
function oneSlip(ts){
  // 2026-08-13: ONE BAT, ONE SLIP. Chalk (a chef seat) is exclusive -- a chef leg may appear nowhere else.
  // Every other repeat is legal only for an ANCHOR mirroring onto its own builder / its own pair of moons.
  var by={}; ts.forEach(function(t){(t.players||[]).forEach(function(l){(by[l.name]=by[l.name]||[]).push(t);});});
  var bad=[];
  Object.keys(by).forEach(function(n){
    var list=by[n]; if(list.length<2)return;
    if(list.some(function(t){return t.kind==='chef';})){
      bad.push(n+' on chef + '+list.filter(function(t){return t.kind!=='chef';}).map(function(t){return t.kind;}).join('/')); return; }
    if(!list.every(function(t){return t.anchor===n;}))
      bad.push(n+' on '+list.length+' slips as a non-anchor ('+list.map(function(t){return t.kind;}).join('/')+')');
  });
  return bad;
}
function anchorsEqBuilders(ts){
  var bl=ts.filter(function(t){return t.kind==='builder';}).map(function(t){return t.players[0].name;}).sort();
  var an=[];ts.forEach(function(t){if((t.kind==='moon'||t.kind==='biggest')&&t.anchor&&an.indexOf(t.anchor)<0)an.push(t.anchor);});
  an.sort();
  return {ok:JSON.stringify(bl)===JSON.stringify(an),builders:bl,anchors:an};
}
`;

(async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium/chrome-linux/chrome' })
    .catch(() => chromium.launch());
  const ctx = await browser.newContext();
  await ctx.route('**/*', r => r.request().url().startsWith('file://') ? r.continue() : r.abort());
  const page = await ctx.newPage();
  page.on('pageerror', () => {});
  await page.goto('file://' + TESTFILE, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction('!!globalThis.__ac', null, { timeout: 15000 });

  const steps = [];
  for (let m = FROM; m <= TO; m += STEP) steps.push(m);

  const report = await page.evaluate(({ steps, DATE, INV }) => {
    eval(INV);
    const RealDate = Date;
    const pin = (min) => {
      const ep = RealDate.UTC(+DATE.slice(0, 4), +DATE.slice(5, 7) - 1, +DATE.slice(8, 10), Math.floor(min / 60) + 4, min % 60);
      function F(...a) { return a.length === 0 ? new RealDate(ep) : new RealDate(...a); }
      F.now = () => ep; F.parse = RealDate.parse; F.UTC = RealDate.UTC; F.prototype = RealDate.prototype;
      globalThis.Date = F;
    };

    const D = globalThis.__D;
    D.tickets = JSON.parse(JSON.stringify(globalThis.__D0));
    const out = { steps: [], viol: { count: 0, integrity: 0, anchors: 0, pairing: 0, structural: 0, oneslip: 0 }, checks: 0, first: null };
    let prevCounts = null, prevBoard = null;

    for (const min of steps) {
      pin(min);
      let err = null;
      try { globalThis.__ac(D); } catch (e) { err = e.message; }
      const ts = D.tickets;
      const c = counts(ts), pr = pairing(ts), ab = anchorsEqBuilders(ts), st = structural(ts), os1 = oneSlip(ts);
      const rec = { t: min, err, counts: c, moonSeq: pr.seq, split: pr.bad, anchorsOk: ab.ok, structural: st, oneslip: os1, integrity: [],
                    set: ts.map(t => t.name + '::' + sig(t)).sort() };

      if (prevCounts && c._total !== prevCounts._total) { out.viol.count++; rec.countDrift = prevCounts._total + '->' + c._total; }
      if (!ab.ok) { out.viol.anchors++; rec.ab = ab; }
      if (st.length) { out.viol.structural += st.length; }
      if (os1.length) { out.viol.oneslip += os1.length; }
      if (pr.bad.length) { out.viol.pairing++; if (!out.first) out.first = { t: min, seq: pr.seq, split: pr.bad }; }

      if (prevBoard) {
        const now = {}; ts.forEach(t => now[t.name] = sig(t));
        prevBoard.forEach(t => {
          if (gmin(t.lock) > min - 0) return;              // only slips that were locked at the prior clock
          out.checks++;
          if (!(t.name in now)) { out.viol.integrity++; rec.integrity.push('VANISHED ' + t.name); }
          else if (now[t.name] !== sig(t)) { out.viol.integrity++; rec.integrity.push('CHANGED ' + t.name); }
        });
      }
      prevCounts = c;
      prevBoard = JSON.parse(JSON.stringify(ts));
      out.steps.push(rec);
    }
    globalThis.Date = RealDate;
    return out;
  }, { steps, DATE, INV: INVARIANTS });

  const name = path.basename(SRC);
  console.log('\n=== ' + name + '  ' + DATE + '  ' + mmss(FROM) + '->' + mmss(TO) + ' every ' + STEP + 'm ===');
  for (const s of report.steps) {
    const flag = s.split.length ? '  SPLIT: ' + s.split.join(', ') : '';
    console.log(
      mmss(s.t) +
      '  n=' + s.counts._total +
      '  moons[' + s.moonSeq.map(n => n.split(' ').pop()).join(' ') + ']' +
      (s.anchorsOk ? '' : '  ANCHOR!=BUILDER') +
      (s.integrity.length ? '  ' + s.integrity.join('; ') : '') +
      (s.structural && s.structural.length ? '  STRUCT: ' + s.structural.join('; ') : '') +
      (s.oneslip && s.oneslip.length ? '  DUP: ' + s.oneslip.join('; ') : '') +
      (s.err ? '  ERR ' + s.err : '') + flag
    );
  }
  console.log('---');
  console.log('locked-slip integrity checks: ' + report.checks);
  console.log('violations  count=' + report.viol.count +
    '  integrity=' + report.viol.integrity +
    '  anchors!=builders=' + report.viol.anchors +
    '  pairing=' + report.viol.pairing +
    '  structural=' + report.viol.structural +
    '  one-bat-one-slip=' + report.viol.oneslip);
  if (opt('dump', null)) fs.writeFileSync(opt('dump'), JSON.stringify(report.steps.map(s => ({ t: s.t, set: s.set })), null, 0));
  fs.unlinkSync(TESTFILE);
  await browser.close();
  process.exit(report.viol.count + report.viol.integrity + report.viol.anchors + report.viol.pairing + report.viol.structural + report.viol.oneslip ? 1 : 0);
})();
