#!/usr/bin/env node
/* test_trayfit.js -- TRAYFIT-2026-10-13. The research panel vs. the sticky controls bar.
 *
 * THE COMPLAINT, TWICE. 2026-10-12: "the sticky bars are overlapping. cant see what some of the
 * columns are when you scroll down." That was fixed -- .rswrap got position:sticky and a height
 * cap -- and the owner was told it was fixed. On 2026-10-13 the SAME overlap was still there, and
 * the only reason it looked fixed is that every check had been run with an EMPTY SLIP.
 *
 * The slip tray is 0px when empty and 58px when up. .rswrap's height reserve was a flat 206px
 * whose own comment claimed it covered "the slip tray" -- a constant cannot cover a thing that is
 * sometimes 0 and sometimes 58. So with a slip open the panel kept its full height, had 58px less
 * viewport to travel in, ran out of containing block before reaching its sticky offset, and
 * seated UNDER the bar. Measured at maximum scroll: 27px of covered column header in baseball and
 * football, 45px in soccer, whose bar carries two rows of game chips.
 *
 * So this measures ONE number, in BOTH tray states, in ALL THREE rooms, at MAXIMUM SCROLL:
 *
 *     overlap = bar.bottom - thead.top        <= 0 is clean, > 0 is a hidden column label
 *
 * and it also asserts the MECHANISM -- that the panel actually shrinks as the tray rises. The
 * number alone can go green on a tall enough window while the bug is still in the rule, so a
 * future edit that drops var(--sliph) from the max-height has to fail something here.
 *
 *     node test_trayfit.js
 */
'use strict';
const path = require('path');
const { chromium } = require('playwright');

const ROOT = __dirname;
const ROOMS = [
  ['baseball', path.join(ROOT, 'index.html')],
  ['football', path.join(ROOT, 'nfl', 'index.html')],
  ['soccer', path.join(ROOT, 'soccer', 'index.html')]
];
/* the short viewport is the binding case -- it is a 768px window with browser chrome, and it is
   where the panel runs out of room first. The tall one is there so a pass is not an artifact of
   one screen. */
const VIEWPORTS = [[1280, 576], [1280, 632], [1440, 900]];   /* 576: FIVEROWS-2026-10-15, the owner's window */

let fail = 0;
const chk = (label, ok, detail) => {
  console.log((ok ? 'PASS  ' : 'FAIL  ') + label);
  if (!ok) { fail++; if (detail !== undefined) console.log('       ', detail); }
};

const measure = (pg) => pg.evaluate(() => {
  const R = (s) => document.querySelector(s).getBoundingClientRect();
  const tray = document.querySelector('#tray');
  return {
    overlap: Math.round(R('.bar.rsbar').bottom - R('#rstab thead th').top),
    wrapH: Math.round(R('.rswrap').height),
    capH: Math.round(parseFloat(getComputedStyle(document.querySelector('.rswrap')).maxHeight)),
    trayUp: !!(tray && tray.classList.contains('up')),
    sliph: getComputedStyle(document.documentElement).getPropertyValue('--sliph').trim() || '0px',
    atBottom: Math.round(scrollY) >= Math.round(document.scrollingElement.scrollHeight - innerHeight) - 2
  };
});

/* a real wheel, not scrollTo: the page re-measures --rsbar on scroll and the programmatic path
   does not always settle where it claims to. */
async function toBottom(pg) {
  for (let i = 0; i < 16; i++) { await pg.mouse.wheel(0, 600); await pg.waitForTimeout(80); }
  await pg.waitForTimeout(300);
}

(async () => {
  console.log('TRAYFIT-2026-10-13 -- the research panel under the sticky bar\n');
  const b = await chromium.launch();

  for (const [w, h] of VIEWPORTS) {
    console.log('-- viewport ' + w + 'x' + h);
    for (const [room, file] of ROOMS) {
      const pg = await b.newPage({ viewport: { width: w, height: h } });
      const errs = [];
      pg.on('pageerror', e => errs.push(e.message));
      await pg.goto('file://' + file, { waitUntil: 'load' });
      await pg.waitForTimeout(700);
      await pg.click('#tab-b');
      await pg.waitForTimeout(400);
      await pg.mouse.move(Math.round(w / 2), Math.round(h / 2));

      await toBottom(pg);
      const down = await measure(pg);

      await pg.evaluate(async () => {
        for (let i = 0; i < 3; i++) {
          const a = [...document.querySelectorAll('#rstab tbody .rsadd')]
            .filter(x => !x.classList.contains('on'))[0];
          if (!a) break;
          a.click();
          await new Promise(r => setTimeout(r, 300));
        }
      });
      await pg.waitForTimeout(350);
      await toBottom(pg);
      const up = await measure(pg);

      const tag = room.padEnd(8);
      chk(tag + ' column headers clear with an EMPTY slip', down.overlap <= 0, down);
      chk(tag + ' the slip tray actually opened', up.trayUp && up.sliph !== '0px', up);
      chk(tag + ' column headers clear with the slip OPEN -- the 10-13 bug',
          up.overlap <= 0, up);
      /* FIVEROWS-2026-10-15: measured on the height CAP, not the rendered height. With 40px rows a short
         card (football's 12 players at 900px) fits entirely under the cap, so the panel is content-height
         and has nothing to shrink -- the rule is still right, the old check just could not see it. */
      chk(tag + ' the panel cap shrinks by the tray height -- the mechanism, not just the symptom',
          down.capH - up.capH === parseInt(up.sliph, 10),
          { capH: down.capH + ' -> ' + up.capH, wrapH: down.wrapH + ' -> ' + up.wrapH, sliph: up.sliph });
      chk(tag + ' measured at maximum scroll, where sticky runs out of containing block',
          down.atBottom && up.atBottom, { down: down.atBottom, up: up.atBottom });
      chk(tag + ' no page errors', errs.length === 0, errs);

      await pg.close();
    }
    console.log();
  }

  await b.close();
  process.exit(fail ? 1 : 0);
})();
