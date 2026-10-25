#!/usr/bin/env node
/* nfl/bp_fetch.js -- AUTONFL-2026-10-24. atd.psv + ftd.psv for one slate from BettingPros, no browser.
 *
 *     node bp_fetch.js slates/2026-10-25/fixtures.json slates/2026-10-25
 *
 * Owner, 10-24, away 10-28..11-10 with his only computer: "in theory i want this to run itself anyways".
 * oddschecker (the Chrome source) is 403 from the runner; BettingPros is not. Markets: 78 anytime TD,
 * 66 first TD. Rows are match|player|american, the same shape nfl_mock.load_prices already reads, so
 * nothing downstream changes. The price written is the MEDIAN across books (see med() below). D/ST and "No Touchdown" style selections are dropped at the source.
 * Exit 0 writing nothing on failure, so a committed browser slate is never overwritten by an empty one.
 */
'use strict';
const fs = require('fs'), path = require('path');
const API = 'https://api.bettingpros.com/v3/';
const PAGE = 'https://www.bettingpros.com/nba/odds/player-props/first-basket/';
const UA = { 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36' };
const MKT = { atd: 78, ftd: 66 };
// BettingPros abbreviations -> nflverse (fixtures.json uses nflverse).
const TEAM = { LAR: 'LA', JAC: 'JAX', WSH: 'WAS', OAK: 'LV', SD: 'LAC', STL: 'LA' };
const T = a => TEAM[a] || a;

async function text(u) { const r = await fetch(u, { headers: UA }); if (!r.ok) throw new Error(r.status + ' ' + u); return r.text(); }
async function key() {
  if (process.env.BP_KEY) return process.env.BP_KEY;
  const html = await text(PAGE);
  const srcs = new Set();
  for (const m of html.matchAll(/(?:src|href)="([^"]+\.m?js[^"]*)"/g)) srcs.add(new URL(m[1], PAGE).href);
  const queue = [...srcs], seen = new Set(), cands = new Set();
  while (queue.length && seen.size < 200) {
    const u = queue.shift(); if (seen.has(u)) continue; seen.add(u);
    let t; try { t = await text(u); } catch (e) { continue; }
    for (const m of t.matchAll(/["'`](\/?[\w\-./]+\.m?js)["'`]/g)) {
      try { const v = new URL(m[1], u).href; if (/bettingpros/.test(v) && !seen.has(v)) queue.push(v); } catch (e) {}
    }
    const re = /x-api-key|apikey|api_key|apiKey/ig; let m;
    while ((m = re.exec(t)))
      for (const x of (t.slice(Math.max(0, m.index - 400), m.index + 400).match(/[A-Za-z0-9_\-]{24,64}/g) || []))
        if (/[0-9]/.test(x) && /[A-Z]/.test(x) && /[a-z]/.test(x)) cands.add(x);
  }
  for (const c of cands) {
    const r = await fetch(API + 'events?sport=NBA&date=2026-01-15', { headers: Object.assign({ 'x-api-key': c }, UA) });
    if (r.status === 200) return c;
  }
  throw new Error(`no key (${seen.size} scripts, ${cands.size} candidates)`);
}
const am = c => (c > 0 ? '+' : '') + c;
// Median across books (in implied probability). Best-of-books picked up fringe exchange lines on the first run
// (McCaffrey anytime +223); the median is what a reader can actually get at a mainstream book.
const ip = c => (c > 0 ? 100 / (c + 100) : -c / (-c + 100));
const toAm = p => Math.round(p >= 0.5 ? -100 * p / (1 - p) : 100 * (1 - p) / p);
const med = xs => { const a = xs.slice().sort((x, y) => x - y), n = a.length; return n % 2 ? a[(n - 1) / 2] : (a[n / 2 - 1] + a[n / 2]) / 2; };

(async () => {
  const [fxPath, outDir] = process.argv.slice(2);
  if (!fxPath || !outDir) { console.error('usage: bp_fetch.js <fixtures.json> <outdir>'); process.exit(2); }
  const fx = JSON.parse(fs.readFileSync(fxPath, 'utf8'));
  const bySides = {};
  for (const [slug, m] of Object.entries(fx.matches)) bySides[m.away + '@' + m.home] = slug;
  try {
    const k = await key(), H = { headers: Object.assign({ 'x-api-key': k }, UA) };
    // ET date and the day after: BettingPros buckets late kickoffs by UTC date.
    const d0 = new Date(fx.date + 'T12:00:00Z'), d1 = new Date(d0.getTime() + 864e5).toISOString().slice(0, 10);
    const evs = {};
    for (const d of [fx.date, d1]) {
      const j = await (await fetch(API + 'events?sport=NFL&date=' + d, H)).json();
      for (const e of (j.events || [])) {
        const slug = bySides[T(e.visitor) + '@' + T(e.home)];
        if (slug) evs[e.id] = slug;
      }
    }
    const ids = Object.keys(evs);
    console.log(`bp_fetch ${fx.date}: ${ids.length}/${Object.keys(fx.matches).length} fixtures found on BettingPros`);
    if (!ids.length) { console.log('::warning::no BettingPros events joined the fixtures -- writing nothing'); return; }
    let sample = 0;
    for (const [name, mid] of Object.entries(MKT)) {
      const best = {};   // slug|player -> best american
      for (let page = 1; ; page++) {
        const o = await (await fetch(API + `offers?sport=NFL&market_id=${mid}&event_id=${ids.join(':')}&limit=25&page=${page}`, H)).json();
        for (const off of (o.offers || [])) {
          const slug = evs[off.event_id]; if (!slug) continue;
          const P = {}; (off.participants || []).forEach(p => { P[p.id] = p; });
          for (const s of (off.selections || [])) {
            const lab = String(s.label || s.selection || '');
            if (/^(under|no)$/i.test(lab) || /^no /i.test(lab)) continue;
            const p = P[s.participant] || {};
            const nm = (p.name || '').replace(/['’]/g, '').trim();
            if (!nm || !p.player || /D\/ST|Defense/i.test(nm)) continue;
            if (sample < 3) { console.log('  sample', name, slug, nm, lab, JSON.stringify((s.books || [])[0] || {}).slice(0, 160)); sample++; }
            for (const b of (s.books || [])) {
              const l = (b.lines || []).find(x => x.main) || (b.lines || [])[0];
              if (l && !l.is_off && typeof l.cost === 'number' && l.cost !== 0) (best[slug + '|' + nm] = best[slug + '|' + nm] || []).push(ip(l.cost));
            }
          }
        }
        const pg = o._pagination || {};
        if (!pg.total_pages || page >= pg.total_pages) break;
      }
      const rows = Object.entries(best).filter(([, ps]) => ps.length).map(([k2, ps]) => k2 + '|' + am(toAm(med(ps))));
      const games = new Set(rows.map(r => r.split('|')[0])).size;
      console.log(`bp_fetch ${fx.date} ${name}: ${rows.length} prices across ${games} games`);
      if (rows.length) { fs.mkdirSync(outDir, { recursive: true }); fs.writeFileSync(path.join(outDir, name + '.psv'), rows.join('\n') + '\n'); }
    }
  } catch (e) {
    console.log(`::warning::bp_fetch ${fx.date}: ${String(e).slice(0, 200)} -- writing nothing`);
  }
})();
