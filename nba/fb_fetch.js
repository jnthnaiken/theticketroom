#!/usr/bin/env node
/* nba/fb_fetch.js -- FBFETCH-2026-10-17. fb_scrape.js for the build runner: BettingPros first-basket
 * prices + projected lineups for one date -> slates/<date>/fb.psv, with no browser.
 *
 *     node fb_fetch.js 2026-10-21 slates/2026-10-21/fb.psv
 *
 * Same rows, same rules as fb_scrape.js (read its header). The API key is BettingPros' own public
 * front-end key: it is read out of the site's JS bundles exactly the way a browser receives it, and is
 * never written to the repo. Exit 0 with nothing written when the site or the key cannot be reached, so
 * the build falls back to whatever fb.psv was committed from the browser.
 * Writes only when the scrape found at least one game; a later scrape REPLACES the file (prices and
 * lineups move all day -- the picks themselves are frozen in picks.json, not here).
 */
'use strict';
const fs = require('fs'), path = require('path');
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
    while ((m = re.exec(t))) {
      for (const x of (t.slice(Math.max(0, m.index - 400), m.index + 400).match(/[A-Za-z0-9_\-]{24,64}/g) || []))
        if (/[0-9]/.test(x) && /[A-Z]/.test(x) && /[a-z]/.test(x)) cands.add(x);
    }
  }
  for (const c of cands) {
    const r = await fetch(API + 'events?sport=NBA&date=2026-01-15', { headers: Object.assign({ 'x-api-key': c }, UA) });
    if (r.status === 200) return c;
  }
  throw new Error(`no key (${seen.size} scripts, ${cands.size} candidates)`);
}

async function scrape(date, k) {
  const H = { headers: Object.assign({ 'x-api-key': k }, UA) }, rows = [];
  const ev = await (await fetch(API + 'events?sport=NBA&date=' + date, H)).json();
  const evs = (ev.events || []).filter(e => e.season_type === 'REG');
  for (const t of evs) {
    const L = t.lineups || {};
    rows.push(['E', date, t.id, t.scheduled, t.home, t.visitor, t.status, L.home_lineup_type || '', L.away_lineup_type || ''].join('|'));
    for (const [k2, s] of [['home_lineup', 'h'], ['away_lineup', 'a'], ['visitor_lineup', 'a']])
      for (const x of (L[k2] || [])) {
        if (!x || !x.participant) continue;
        const pl = x.participant.player || {};
        rows.push(['L', date, t.id, s, x.status, x.participant.id, x.participant.name, pl.position || '', pl.team || ''].join('|'));
      }
  }
  const ids = evs.map(e => e.id); let nsel = 0;
  for (let i = 0; i < ids.length; i += 25) {
    for (let page = 1; ; page++) {
      const o = await (await fetch(API + 'offers?sport=NBA&market_id=142&event_id=' + ids.slice(i, i + 25).join(':') + '&limit=25&page=' + page, H)).json();
      for (const off of (o.offers || [])) {
        const P = {}; (off.participants || []).forEach(p => { P[p.id] = p; });
        for (const s of (off.selections || [])) {
          const p = P[s.participant] || {}, pl = p.player || {}, ol = s.opening_line || {};
          const bk = (s.books || []).map(b => {
            const l = (b.lines || []).find(x => x.main) || (b.lines || [])[0];
            return l && !l.is_off ? b.id + ':' + l.cost : null;
          }).filter(Boolean).join(',');
          rows.push(['S', date, off.event_id, s.participant, p.name || s.label, pl.position || '', pl.team || '', ol.cost, ol.book_id, bk].join('|'));
          nsel++;
        }
      }
      const pg = o._pagination || {};
      if (!pg.total_pages || page >= pg.total_pages) break;
    }
  }
  return { rows, games: evs.length, prices: nsel, lineups: rows.filter(r => r[0] === 'L').length };
}

/* RWLINEUP-2026-10-20. Owner, 10-20 2:46 PM: "rosters are out for the boston detroit game. why isnt it green
   check?" BettingPros' events feed carried NO lineup rows all day (lineup_type 'projected', empty arrays), and
   the page only ticks a man from ESPN's box score, which exists from tip-off. RotoWire's lineups page flips each
   side to "Confirmed Lineup" ~30 min before tip and is server-rendered, so it is read here as a second source:
       R|date|TEAM|visit/home|confirmed/expected|Full Name      (the five, in order)
   nba_payload.py only uses it to CONFIRM: a confirmed five whose names all join that team's priced men. */
async function rotowire(date) {
  const html = await text('https://www.rotowire.com/basketball/nba-lineups.php');
  const out = [];
  const blocks = html.split(/<div class="lineup is-nba/).slice(1);
  for (const b of blocks) {
    const ab = [...b.matchAll(/class="lineup__abbr">\s*([A-Z]{2,4})\s*</g)].map(m => m[1]);
    if (ab.length < 2) continue;
    for (const [side, i] of [['visit', 0], ['home', 1]]) {
      const m = b.match(new RegExp('<ul class="lineup__list is-' + side + '"([\\s\\S]*?)</ul>'));
      if (!m) continue;
      const parts = m[1].split(/lineup__title/); const body = parts[0];
      const st = /lineup__status is-confirmed/.test(body) ? 'confirmed' : (/lineup__status is-expected/.test(body) ? 'expected' : 'unknown');
      // RWINJ-2026-10-24: each <li> may carry <span class="lineup__inj">Prob|Ques|Doubt|Out|GTD</span>; the list after
      // the title is MAY NOT PLAY. The tag rides as a 7th field on R rows and as I rows for the may-not-play list.
      const clean = n => n.replace(/&#039;|&apos;/g, "'").replace(/&amp;/g, '&');
      const lis = h => [...h.matchAll(/<li class="lineup__player[^"]*"[\s\S]*?<a [^>]*title="([^"]+)"[\s\S]*?<\/li>/g)]
        .map(x => [clean(x[1]), ((x[0].match(/lineup__inj[^>]*>\s*([^<\s][^<]*?)\s*</) || [])[1] || '')]);
      const five = lis(body).slice(0, 5);
      if (five.length === 5) five.forEach(([n, tag]) => out.push(['R', date, ab[i], side, st, n, tag].join('|')));
      for (const rest of parts.slice(1)) for (const [n, tag] of lis(rest)) if (tag) out.push(['I', date, ab[i], n, tag].join('|'));
    }
  }
  return out;
}

(async () => {
  const [date, out] = process.argv.slice(2);
  if (!date || !out) { console.error('usage: fb_fetch.js <date> <out.psv>'); process.exit(2); }
  try {
    const k = await key();
    const r = await scrape(date, k);
    try {
      const rw = await rotowire(date);
      r.rows.push(...rw);
      console.log(`fb_fetch ${date}: rotowire ${rw.filter(x => x[0] === 'R').length / 5} lineup(s), ${rw.filter(x => x.includes('|confirmed|')).length / 5} confirmed, ${rw.filter(x => x[0] === 'I').length} injury tag(s)`);
    } catch (e) { console.log(`::warning::rotowire lineups: ${String(e).slice(0, 150)}`); }
    console.log(`fb_fetch ${date}: ${r.games} games, ${r.prices} prices, ${r.lineups} lineup rows`);
    if (!r.games) return;
    fs.mkdirSync(path.dirname(out), { recursive: true });
    fs.writeFileSync(out, r.rows.join('\n') + '\n');
  } catch (e) {
    console.log(`::warning::fb_fetch ${date}: ${String(e).slice(0, 200)} -- keeping the committed fb.psv`);
  }
})();
