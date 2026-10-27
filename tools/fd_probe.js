// KOTC-2026-10-27 probe: BettingPros NBA markets (find points+rebounds+assists) and a sample of tonight's PRA offers
'use strict';
const { execSync } = require('child_process');
const API = 'https://api.bettingpros.com/v3/', UA = { 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129.0 Safari/537.36' };
(async () => {
  const src = require('fs').readFileSync('nba/fb_fetch.js', 'utf8');
  // reuse fb_fetch's key finder by requiring it as a module is awkward; copy the page/JS scan
  const PAGE = 'https://www.bettingpros.com/nba/odds/player-props/first-basket/';
  const text = async u => { const r = await fetch(u, { headers: UA }); if (!r.ok) throw new Error(r.status); return r.text(); };
  const html = await text(PAGE); const srcs = new Set(); for (const m of html.matchAll(/(?:src|href)="([^"]+\.m?js[^"]*)"/g)) srcs.add(new URL(m[1], PAGE).href);
  const q = [...srcs], seen = new Set(), cands = new Set();
  while (q.length && seen.size < 200) { const u = q.shift(); if (seen.has(u)) continue; seen.add(u); let t; try { t = await text(u); } catch (e) { continue; }
    for (const m of t.matchAll(/["'`](\/?[\w\-./]+\.m?js)["'`]/g)) { try { const v = new URL(m[1], u).href; if (/bettingpros/.test(v) && !seen.has(v)) q.push(v); } catch (e) {} }
    const re = /x-api-key|apikey|api_key|apiKey/ig; let mm; while ((mm = re.exec(t))) for (const x of (t.slice(Math.max(0, mm.index - 400), mm.index + 400).match(/[A-Za-z0-9_\-]{24,64}/g) || [])) if (/[0-9]/.test(x) && /[A-Z]/.test(x) && /[a-z]/.test(x)) cands.add(x); }
  let key; for (const c of cands) { const r = await fetch(API + 'events?sport=NBA&date=2026-01-15', { headers: Object.assign({ 'x-api-key': c }, UA) }); if (r.status === 200) { key = c; break; } }
  const H = { headers: Object.assign({ 'x-api-key': key }, UA) };
  const mk = await (await fetch(API + 'markets?sport=NBA&limit=300', H)).json();
  const list = (mk.markets || []).filter(m => m.category === 'player-props' && m.period === 'game');
  console.log('NBA player-prop markets:', list.map(m => m.id + ':' + m.slug).join(', '));
  const pra = list.find(m => /points-rebounds-assists|pra/.test(m.slug));
  const ev = await (await fetch(API + 'events?sport=NBA&date=2026-10-27', H)).json();
  const ids = (ev.events || []).map(e => e.id); console.log('events tonight', ids.length);
  if (pra && ids.length) {
    const o = await (await fetch(API + `offers?sport=NBA&market_id=${pra.id}&event_id=${ids.join(':')}&limit=25&page=1`, H)).json();
    console.log('PRA offers page1', (o.offers || []).length, 'pages', JSON.stringify(o._pagination));
    for (const off of (o.offers || []).slice(0, 3)) { const P = {}; (off.participants || []).forEach(p => P[p.id] = p.name);
      for (const s of (off.selections || []).slice(0, 2)) console.log(' ', P[s.participant], s.label, (s.books || []).slice(0, 4).map(b => b.id + ':' + JSON.stringify((b.lines || []).filter(l => l.main).map(l => [l.line, l.cost]))).join(' ')); }
  }
})().catch(e => console.log('ERR', e));
