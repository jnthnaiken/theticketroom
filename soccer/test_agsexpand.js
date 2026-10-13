#!/usr/bin/env node
/* test_agsexpand.js -- SCROLLFGS-2026-10-13. ags_scrape.js's First Goalscorer accordion.
 *
 * THE NIGHT IT WAS WRITTEN. The 2026-10-13 Champions League card scraped eight ties. On the first
 * one the FGS market came back empty and the log read:
 *
 *     expand=clicked  FGS ok=false n=0
 *
 * which reads as "oddschecker did not price a first-goalscorer market on this tie". It had. The
 * section is LAZY -- it hydrates when scrolled into view -- so a blind h2.click() on a header far
 * below the fold did nothing, the poll burned its whole 8000ms ceiling, and `expand` returned the
 * same 'clicked' it returns on success. Scrolling first opened it in ~500ms.
 *
 * Two separate defects, and the second is the one that cost the time: a function that cannot say
 * "I gave up" turns its own failure into a claim about the source. The return is now
 * 'none' | 'open' | 'opened' | 'timeout', and 'timeout' is a thing a caller can see.
 *
 *     node test_agsexpand.js
 */
'use strict';
const fs = require('fs');
const path = require('path');

let fail = 0;
const chk = (label, ok, detail) => {
  console.log((ok ? 'PASS  ' : 'FAIL  ') + label);
  if (!ok) { fail++; if (detail !== undefined) console.log('       ', detail); }
};

/* ---- a DOM just big enough for expand() -------------------------------------------------- */
function mkSection(title, opts) {
  opts = opts || {};
  const sec = {
    _wraps: opts.openAtStart ? 15 : 0,
    scrolled: false, clicked: 0,
    querySelector: sel => (sel === 'h2' ? { textContent: title, click() { sec.clicked++;
      if (opts.hydratesOnClick && (!opts.needsScrollFirst || sec.scrolled)) sec._wraps = 15; } } : null),
    querySelectorAll: () => ({ length: sec._wraps }),
    scrollIntoView() { sec.scrolled = true; if (opts.hydratesOnScroll) sec._wraps = 15; }
  };
  return sec;
}
function install(sections) {
  global.document = { querySelectorAll: sel => (sel === 'section' ? sections : []) };
  global.window = {};
}
/* real waits would make the timeout case 20s; the scraper only ever awaits setTimeout */
const realTimeout = global.setTimeout;
global.setTimeout = fn => realTimeout(fn, 0);

const ags = eval(fs.readFileSync(path.join(__dirname, 'ags_scrape.js'), 'utf8'));

(async () => {
  console.log('SCROLLFGS-2026-10-13 -- the First Goalscorer accordion\n');

  // 1. no such market on the page
  install([]);
  chk("a market that is not on the page returns 'none'", (await ags.expand('First Goalscorer')) === 'none');

  // 2. already open -> never touched
  let sec = mkSection('First Goalscorer', { openAtStart: true });
  install([sec]);
  chk("an already-open market returns 'open'", (await ags.expand('First Goalscorer')) === 'open');
  chk('  ...and is neither scrolled nor clicked', !sec.scrolled && sec.clicked === 0,
      { scrolled: sec.scrolled, clicked: sec.clicked });

  // 3. THE BUG: lazy section that hydrates on scroll alone, no click needed
  sec = mkSection('First Goalscorer', { hydratesOnScroll: true });
  install([sec]);
  let r = await ags.expand('First Goalscorer');
  chk("a lazy market hydrates on scroll and returns 'opened'", r === 'opened', r);
  chk('  ...was scrolled into view', sec.scrolled);
  chk('  ...and did NOT need a click', sec.clicked === 0, { clicked: sec.clicked });

  // 4. needs the click, but only AFTER the scroll -- the real 10-13 shape
  sec = mkSection('First Goalscorer', { hydratesOnClick: true, needsScrollFirst: true });
  install([sec]);
  r = await ags.expand('First Goalscorer');
  chk("a market that opens on click AFTER scrolling returns 'opened'", r === 'opened', r);
  chk('  ...scrolled before it clicked', sec.scrolled && sec.clicked >= 1,
      { scrolled: sec.scrolled, clicked: sec.clicked });

  // 5. THE REGRESSION GUARD: a market that never populates must SAY SO
  sec = mkSection('First Goalscorer', {});           // nothing opens it
  install([sec]);
  r = await ags.expand('First Goalscorer');
  chk("a market that never populates returns 'timeout', NOT 'clicked'", r === 'timeout', r);
  chk("  ...'clicked' is gone entirely -- it could not distinguish success from failure",
      r !== 'clicked', r);

  console.log();
  process.exit(fail ? 1 : 0);
})();
