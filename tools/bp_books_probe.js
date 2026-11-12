// BESTBOOK-2026-11-11 probe: BettingPros book ids -> names
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


(async () => {
  const k = await key(); const H = { headers: Object.assign({ 'x-api-key': k }, UA) };
  const r = await fetch(API + 'books', H); const j = await r.json();
  for (const b of j.books || []) console.log([b.id, b.display_name, b.name, b.exclude_from_best ? 'exclude' : '', b.is_prediction_market ? 'pm' : '', (b.locations || []).length].join(' | '));
})();
