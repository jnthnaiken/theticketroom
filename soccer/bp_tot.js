#!/usr/bin/env node
/* soccer/bp_tot.js -- AUTOSOCCER-2026-10-25. tot.psv (the Goal Line's prices) from BettingPros, no browser.
 *
 *     node bp_tot.js slates/<date>/fixtures.json slates/<date>/tot.psv [--dump]
 *
 * Owner, 10-25 1:27 AM: "totals should be priced too, whats the hold up with the goal line?" The Goal Line read
 * oddschecker through Chrome; oddschecker is 403 from the runner. Rows are soccer_tot.load_prices' own format:
 *     match|WIN|H/D/A|-|american      match|TG/TH/TA|O/U|line|american      match|BT|Y/N|-|american
 * Price = MEDIAN implied probability across books (soccer_tot caps every posted leg at market-fair anyway).
 * Fixtures join on team names (both sides must match). --dump prints raw samples for each market instead.
 * Exit 0 writing nothing on failure.
 */
'use strict';
const fs = require('fs');
const API = 'https://api.bettingpros.com/v3/';
const PAGE = 'https://www.bettingpros.com/nba/odds/player-props/first-basket/';
const UA = { 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36' };
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
  throw new Error('no key');
}
const ip = c => (c > 0 ? 100 / (c + 100) : -c / (-c + 100));
const toAm = p => Math.round(p >= 0.5 ? -100 * p / (1 - p) : 100 * (1 - p) / p);
const med = xs => { const a = xs.slice().sort((x, y) => x - y), n = a.length; return n % 2 ? a[(n - 1) / 2] : (a[n / 2 - 1] + a[n / 2]) / 2; };
const norm = s => String(s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase()
  .replace(/\b(fc|cf|afc|sc|ac|as|ss|ssc|us|rc|cd|ud|sd|rcd|ca|vfl|vfb|tsg|sv|1\.|fsv|bsc|hsc|ogc|stade|olympique|de|club|calcio|real|athletic)\b/g, ' ')
  .replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim();
const toks = s => { let t = norm(s).split(' ').filter(w => w.length > 2); if (!t.length) t = String(s || '').toLowerCase().split(/[^a-z0-9]+/).filter(w => w.length > 2); return new Set(t); };
const sim = (a, b) => { const A = toks(a), B = toks(b); if (!A.size || !B.size) return 0; let n = 0; for (const x of A) if (B.has(x) || [...B].some(y => y.startsWith(x) || x.startsWith(y))) n++; return n / Math.min(A.size, B.size); };

(async () => {
  const [fxPath, out, flag] = process.argv.slice(2);
  const dump = flag === '--dump';
  const fx = JSON.parse(fs.readFileSync(fxPath, 'utf8'));
  try {
    const k = await key(), H = { headers: Object.assign({ 'x-api-key': k }, UA) };
    const J = async u => (await fetch(API + u, H)).json();
    const mk = await J('markets?sport=SOCCER&limit=500');
    const markets = mk.markets || mk;
    const ML = (markets.find(m => /^(moneyline|3-way|three-way|match-result|1x2|result)/.test(m.slug) && m.period === 'game') || {}).id;
    if (dump) console.log('game markets:', markets.filter(m => /game-odds|game-props/.test(m.category)).map(m => m.id + ':' + m.slug).join(' '));
    const d1 = new Date(Date.parse(fx.date + 'T12:00:00Z') + 864e5).toISOString().slice(0, 10);
    const evs = [];
    for (const d of [fx.date, d1]) evs.push(...((await J('events?sport=SOCCER&date=' + d)).events || []));
    const nm = e => { const P = e.participants || []; const f = id => (P.find(p => p.id === id) || {}).name || '';
      return [f(e.home) || (e.event_name || '').split(/ vs\.? | v | @ /)[1] || '', f(e.visitor) || (e.event_name || '').split(/ vs\.? | v | @ /)[0] || '']; };
    if (dump) for (const e of evs.slice(0, 3)) console.log('event', JSON.stringify(e).slice(0, 700));
    const join = {};
    for (const [slug, m] of Object.entries(fx.matches)) {
      let best = null, bs = 0;
      for (const e of evs) { const [h, a] = nm(e); const s = Math.min(sim(m.home, h), sim(m.away, a)); if (s > bs) { bs = s; best = e; } }
      if (best && bs >= 0.5) join[best.id] = { slug, m, e: best };
      else console.log(`  unjoined: ${slug} (best ${bs.toFixed(2)})`);
    }
    const ids = Object.keys(join);
    console.log(`bp_tot ${fx.date}: ${ids.length}/${Object.keys(fx.matches).length} fixtures joined; moneyline market ${ML}`);
    const acc = {};
    const add = (k2, c) => { if (typeof c === 'number' && c !== 0) (acc[k2] = acc[k2] || []).push(ip(c)); };
    for (const [mid, tag] of [[ML, 'WIN'], [243, 'TG'], [426, 'TT'], [410, 'BT']]) {
      if (!mid) continue;
      let shown = 0;
      for (let page = 1; ; page++) {
        const o = await J(`offers?sport=SOCCER&market_id=${mid}&event_id=${ids.join(':')}&limit=25&page=${page}`);
        for (const off of (o.offers || [])) {
          const J0 = join[off.event_id]; if (!J0) continue;
          if (dump && shown < 1) { console.log(tag, JSON.stringify(off).slice(0, 1500)); shown++; }
          const P = {}; (off.participants || []).forEach(p => { P[p.id] = p; });
          for (const s of (off.selections || [])) {
            const lab = String(s.label || s.selection || '').toLowerCase();
            const pn = (P[s.participant] || {}).name || '';
            for (const b of (s.books || [])) for (const l of (b.lines || [])) {
              if (l.is_off) continue;
              const line = l.line;
              if (tag === 'WIN') {
                const side = /draw|tie/.test(lab) || /draw|tie/i.test(pn) ? 'D'
                  : (sim(J0.m.home, pn || lab) >= .5 ? 'H' : (sim(J0.m.away, pn || lab) >= .5 ? 'A' : null));
                if (side) add(`${J0.slug}|WIN|${side}|-`, l.cost);
              } else if (tag === 'BT') {
                const side = /^(yes|y)$/.test(lab) ? 'Y' : (/^(no|n)$/.test(lab) ? 'N' : null);
                if (side) add(`${J0.slug}|BT|${side}|-`, l.cost);
              } else {
                const side = /over|^o$/.test(lab) ? 'O' : (/under|^u$/.test(lab) ? 'U' : null);
                if (!side || line == null) continue;
                let mkt = 'TG';
                if (tag === 'TT') { const who = (P[off.team_id] || {}).name || pn || ''; mkt = sim(J0.m.home, who) >= .5 ? 'TH' : (sim(J0.m.away, who) >= .5 ? 'TA' : null); }
                if (mkt) add(`${J0.slug}|${mkt}|${side}|${+line}`, l.cost);
              }
            }
          }
        }
        const pg = o._pagination || {};
        if (!pg.total_pages || page >= pg.total_pages) break;
      }
    }
    const rows = Object.entries(acc).map(([k2, ps]) => { const am = toAm(med(ps)); return k2 + '|' + (am > 0 ? '+' : '') + am; });
    const per = {}; rows.forEach(r => { const [m, t] = r.split('|'); (per[m] = per[m] || new Set()).add(t); });
    const full = Object.entries(per).filter(([, s]) => s.has('WIN') && s.has('TG')).length;
    console.log(`bp_tot ${fx.date}: ${rows.length} prices; ${full} matches with result + total (Goal Line needs both)`);
    for (const [m, s] of Object.entries(per)) console.log(`  ${m}: ${[...s].join(',')}`);
    if (rows.length && full && !dump) fs.writeFileSync(out, rows.join('\n') + '\n');
    if (dump) console.log(rows.slice(0, 60).join('\n'));
  } catch (e) { console.log(`::warning::bp_tot: ${String(e).slice(0, 300)}`); }
})();
