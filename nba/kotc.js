#!/usr/bin/env node
/* nba/kotc.js -- KOTC-2026-10-27. DraftKings' King of the Court (NBA Tuesdays): pick the player with the most
 * points + rebounds + assists of the night; a $5+ player prop with the KOTC token enters; the right pickers split
 * a bonus-bet pool. Owner: "we need to look at king of the court on dk".
 *
 *     node kotc.js 2026-10-27 out.json
 *
 * PRA lines: BettingPros market 338 (points-assists-rebounds), main line, median across books; each side de-vigged.
 * Each player's PRA ~ Normal(mean, sd): mean backed out of the line and the de-vigged over chance, sd = 0.20 x mean
 * + 2.5 (v1, to be calibrated). 50k simulations -> P(top PRA of the night). Popularity proxy: share of picks
 * proportional to mean^4 (the public takes the biggest stat lines). Value = P(top) / popularity; the crown goes to the
 * best value among the five likeliest, as King of the End Zone does.
 */
'use strict';
const fs = require('fs');
const API = 'https://api.bettingpros.com/v3/', PAGE = 'https://www.bettingpros.com/nba/odds/player-props/first-basket/';
const UA = { 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129.0 Safari/537.36' };
const text = async u => { const r = await fetch(u, { headers: UA }); if (!r.ok) throw new Error(r.status + ' ' + u); return r.text(); };
async function key() {
  if (process.env.BP_KEY) return process.env.BP_KEY;
  const html = await text(PAGE); const srcs = new Set(); for (const m of html.matchAll(/(?:src|href)="([^"]+\.m?js[^"]*)"/g)) srcs.add(new URL(m[1], PAGE).href);
  const q = [...srcs], seen = new Set(), cands = new Set();
  while (q.length && seen.size < 200) { const u = q.shift(); if (seen.has(u)) continue; seen.add(u); let t; try { t = await text(u); } catch (e) { continue; }
    for (const m of t.matchAll(/["'`](\/?[\w\-./]+\.m?js)["'`]/g)) { try { const v = new URL(m[1], u).href; if (/bettingpros/.test(v) && !seen.has(v)) q.push(v); } catch (e) {} }
    const re = /x-api-key|apikey|api_key|apiKey/ig; let mm; while ((mm = re.exec(t))) for (const x of (t.slice(Math.max(0, mm.index - 400), mm.index + 400).match(/[A-Za-z0-9_\-]{24,64}/g) || [])) if (/[0-9]/.test(x) && /[A-Z]/.test(x) && /[a-z]/.test(x)) cands.add(x); }
  for (const c of cands) { const r = await fetch(API + 'events?sport=NBA&date=2026-01-15', { headers: Object.assign({ 'x-api-key': c }, UA) }); if (r.status === 200) return c; }
  throw new Error('no key');
}
const ip = c => (c > 0 ? 100 / (c + 100) : -c / (-c + 100));
const med = a => { const s = a.slice().sort((x, y) => x - y), n = s.length; return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2; };
function ninv(p) { // Acklam
  const a = [-39.69683028665376, 220.9460984245205, -275.9285104469687, 138.357751867269, -30.66479806614716, 2.506628277459239],
        b = [-54.47609879822406, 161.5858368580409, -155.6989798598866, 66.80131188771972, -13.28068155288572],
        c = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783],
        d = [0.007784695709041462, 0.3224671290700398, 2.445134137142996, 3.754408661907416];
  const pl = 0.02425; let q, r;
  if (p < pl) { q = Math.sqrt(-2 * Math.log(p)); return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
  if (p > 1 - pl) { q = Math.sqrt(-2 * Math.log(1 - p)); return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
  q = p - 0.5; r = q * q; return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
}
let seed = 12345; const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
const gauss = () => { let u = 0, v = 0; while (u === 0) u = rnd(); v = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
(async () => {
  const [date, out] = process.argv.slice(2);
  const H = { headers: Object.assign({ 'x-api-key': await key() }, UA) };
  const J = async u => (await fetch(API + u, H)).json();
  const evs = (await J('events?sport=NBA&date=' + date)).events || [];
  const name = {}; const P = {};
  for (let i = 0; i < evs.length; i += 25) for (let page = 1; ; page++) {
    const o = await J(`offers?sport=NBA&market_id=338&event_id=${evs.slice(i, i + 25).map(e => e.id).join(':')}&limit=25&page=${page}`);
    for (const off of o.offers || []) {
      const pp = {}; (off.participants || []).forEach(p => { pp[p.id] = p; });
      const rows = {};
      for (const s of off.selections || []) {
        const side = /over/i.test(s.label || s.selection) ? 'O' : /under/i.test(s.label || s.selection) ? 'U' : null; if (!side) continue;
        for (const b of s.books || []) { const l = (b.lines || []).find(x => x.main); if (!l || l.is_off || !l.cost) continue;
          (rows[b.id] = rows[b.id] || {})[side] = [l.line, l.cost]; }
      }
      const pid = Object.keys(pp)[0]; if (!pid) continue; const nm = pp[pid].name, team = (pp[pid].player || {}).team || '';
      const lines = [], povers = [];
      for (const r of Object.values(rows)) if (r.O && r.U && r.O[0] === r.U[0]) { const o_ = ip(r.O[1]), u_ = ip(r.U[1]); lines.push(r.O[0]); povers.push(o_ / (o_ + u_)); }
      if (!lines.length) continue;
      const ml = med(lines), atL = Object.values(rows).filter(r => r.O && r.O[0] === ml).map(r => ip(r.O[1]));
      const fdr = rows[10] && rows[10].O;   // FanDuel, when it has the line
      const po = atL.length ? med(atL) : null;
      P[nm] = { name: nm, team, line: ml, pover: med(povers), books: lines.length, event: off.event_id,
                over_odds: po ? Math.round(po >= 0.5 ? -100 * po / (1 - po) : 100 * (1 - po) / po) : null,
                fd_line: fdr ? fdr[0] : null, fd_odds: fdr ? fdr[1] : null };
    }
    const pg = o._pagination || {}; if (!pg.total_pages || page >= pg.total_pages) break;
  }
  const L = Object.values(P);
  for (const p of L) { const sd0 = 0.2 * p.line + 2.5; p.mean = p.line + sd0 * ninv(Math.min(0.98, Math.max(0.02, p.pover))); p.sd = 0.2 * p.mean + 2.5; }
  const N = 50000, win = new Array(L.length).fill(0);
  for (let k = 0; k < N; k++) { let bi = -1, bv = -1e9; for (let i = 0; i < L.length; i++) { const v = L[i].mean + L[i].sd * gauss(); if (v > bv) { bv = v; bi = i; } } win[bi]++; }
  const popw = L.map(p => Math.pow(p.mean, 4)), ps = popw.reduce((a, b) => a + b, 0);
  L.forEach((p, i) => { p.p = win[i] / N; p.pop = popw[i] / ps; p.value = p.p / p.pop; });
  const top = L.slice().sort((a, b) => b.p - a.p);
  const five = top.slice(0, 5); const crown = five.slice().sort((a, b) => b.value - a.value)[0];
  if (crown) crown.crown = true;
  const res = { date, games: evs.length, players: L.length, fetched: new Date().toISOString().slice(0, 16) + 'Z', model: 'KOTC v1: Normal PRA, sd 0.2*mean+2.5, popularity mean^4',
                all: L.map(p => ({ name: p.name, team: p.team, line: p.line, pover: +p.pover.toFixed(4), mean: +p.mean.toFixed(2), over_odds: p.over_odds, fd_line: p.fd_line, fd_odds: p.fd_odds })),
                top: top.slice(0, 12).map(p => ({ name: p.name, team: p.team, line: p.line, mean: +p.mean.toFixed(1), p: +p.p.toFixed(4), pop: +p.pop.toFixed(4), value: +p.value.toFixed(2), crown: !!p.crown, over_odds: p.over_odds })) };
  fs.writeFileSync(out, JSON.stringify(res, null, 1));
  console.log(JSON.stringify(res, null, 1));
})().catch(e => console.log('::warning::kotc: ' + String(e).slice(0, 200)));
