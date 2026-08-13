#!/usr/bin/env node
/* backtest_true, stage 3 -- cold-draft every (night, condition) through the REAL client
 * engine: the current index.html drafter, headless, ALL network blocked, clock pinned to
 * 10:00 ET on the slate date, tickets stripped (no locks, no carry). This is the fix for
 * backtest_mix.py grading assemble_tickets.py -- an engine the product does not ship.
 *
 * Reads bt_patches.json (from backtest_true_prep.py) + D_<date>.json + index.html.
 * Writes bt_results/<date>_<cond>.json. Resume-safe: existing results are skipped.
 * Needs: npm i playwright && npx playwright install chromium.
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = fs.readFileSync('index.html', 'utf8');
const lines = BASE.split('\n');
const dIdx = lines.findIndex(l => l.startsWith('const D={'));
if (dIdx < 0) throw new Error('index.html: no `const D={` line -- injection format drifted');
let acIdx = lines.findIndex(l => /^\s*function assembleClient\(D\)\{/.test(l));
if (acIdx < 0) throw new Error('index.html: assembleClient not found');
let iife = acIdx; while (iife > 0 && lines[iife].trim() !== '(function(){') iife--;

function buildHtml(Djson) {
  const L = lines.slice();
  L[dIdx] = 'const D=' + Djson + ',WX=D.meta.wx;';
  L.splice(dIdx + 1, 0, 'globalThis.__D=D;');
  const ii = iife > dIdx ? iife + 1 : iife;
  L.splice(ii + 1, 0, '  try{globalThis.__ac=assembleClient;}catch(e){}');
  return L.join('\n');
}

(async () => {
  const patches = JSON.parse(fs.readFileSync('bt_patches.json', 'utf8'));
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined })
    .catch(() => chromium.launch());
  const ctx = await browser.newContext();
  await ctx.route('**/*', r => r.request().url().startsWith('file://') ? r.continue() : r.abort());
  fs.mkdirSync('bt_results', { recursive: true });
  let done = 0, fail = 0;
  for (const dt of Object.keys(patches).sort()) {
    const D0 = JSON.parse(fs.readFileSync(`D_${dt}.json`, 'utf8'));
    for (const cond of Object.keys(patches[dt])) {
      const outfile = `bt_results/${dt}_${cond}.json`;
      if (fs.existsSync(outfile)) { done++; continue; }
      const D = JSON.parse(JSON.stringify(D0));
      const patch = patches[dt][cond];
      for (const n in patch) {
        if (!D.players[n]) continue;
        D.players[n].blend = patch[n][0];
        D.players[n].baseTotal = patch[n][1];
        D.players[n].TOTAL = patch[n][2];
      }
      D.tickets = [];
      const tmp = path.resolve(`.bt_tmp.html`);
      fs.writeFileSync(tmp, buildHtml(JSON.stringify(D)));
      const page = await ctx.newPage();
      page.on('pageerror', () => {});
      let rec = { date: dt, cond, err: null, tickets: [] };
      try {
        await page.goto('file://' + tmp, { waitUntil: 'domcontentloaded', timeout: 20000 });
        await page.waitForFunction('!!globalThis.__ac', null, { timeout: 15000 });
        rec = await page.evaluate(({ dt, cond }) => {
          const RealDate = Date;
          const min = 600; // 10:00 ET -- before any lock on the slate
          const ep = RealDate.UTC(+dt.slice(0, 4), +dt.slice(5, 7) - 1, +dt.slice(8, 10), Math.floor(min / 60) + 4, min % 60);
          function F(...a) { return a.length === 0 ? new RealDate(ep) : new RealDate(...a); }
          F.now = () => ep; F.parse = RealDate.parse; F.UTC = RealDate.UTC; F.prototype = RealDate.prototype;
          globalThis.Date = F;
          const D = globalThis.__D;
          let err = null;
          try { globalThis.__ac(D); } catch (e) { err = String(e && e.message || e); }
          globalThis.Date = RealDate;
          return { date: dt, cond, err, tickets: D.tickets || [] };
        }, { dt, cond });
      } catch (e) {
        rec.err = 'HARNESS: ' + e.message;
      }
      await page.close();
      fs.unlinkSync(tmp);
      fs.writeFileSync(outfile, JSON.stringify(rec));
      if (rec.err) { fail++; console.log(`${dt} ${cond} ERR ${rec.err}`); }
      else done++;
      if ((done + fail) % 20 === 0) console.log(`${done + fail} done (${fail} errors)`);
    }
  }
  console.log(`FINISHED: ${done} ok, ${fail} errors`);
  await browser.close();
  process.exit(fail ? 1 : 0);
})();
