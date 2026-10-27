#!/usr/bin/env node
/* soccer/auto_slate.js -- AUTOSOCCER-2026-10-26. A whole soccer slate with no browser:
 *
 *     node auto_slate.js 2026-10-26 slates/2026-10-26
 *
 * Owner, 1:15 AM 10-26: "its past 1am. shouldnt the soccer board have fired already?" -- the board had flipped as far
 * as it could: 10-25 was graded, but no 10-26 slate existed, because slates were still built by hand in Chrome
 * (oddschecker + understat pages). He is away 10-28..11-10 with his only computer. Same files, cloud sources:
 *   fixtures.json  ESPN: slate_scan.js decides WHICH fixtures (coverage.json + CUPSCOPE gate); this keys them the way
 *                  slate_scan_browser.js does (slugified ESPN names, home first; kickoff = minutes from <date>T00:00Z,
 *                  so an ET-evening MLS kickoff can exceed 1440)
 *   ags.psv        BettingPros 412 anytime goalscorer   match|player|american   (median across books)
 *   fgs.psv        BettingPros 417 first goalscorer     match|player|american
 *   xg.psv         understat getLeagueData (XHR header) for the slate's big-five leagues, this season + last, in
 *                  understat_rows.js' exact column order; MLS from American Soccer Analysis (soccer_asa_fetch.js)
 * Writes nothing for a file it could not build. Exit 0 always; the workflow decides what is enough to commit.
 */
'use strict';
const fs = require('fs'), path = require('path'), { execFileSync } = require('child_process');
const ESPN = 'https://site.api.espn.com/apis/site/v2/sports/soccer';
const API = 'https://api.bettingpros.com/v3/';
const PAGE = 'https://www.bettingpros.com/nba/odds/player-props/first-basket/';
const UA = { 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36' };
const UNDERSTAT = { EPL: 'EPL', La_liga: 'La_liga', Serie_A: 'Serie_A', Bundesliga: 'Bundesliga', Ligue_1: 'Ligue_1' };

async function text(u, h) { const r = await fetch(u, { headers: Object.assign({}, UA, h || {}) }); if (!r.ok) throw new Error(r.status + ' ' + u); return r.text(); }
async function getJSON(u, h) { return JSON.parse(await text(u, h)); }
const slugify = s => String(s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
const ip = c => (c > 0 ? 100 / (c + 100) : -c / (-c + 100));
const toAm = p => Math.round(p >= 0.5 ? -100 * p / (1 - p) : 100 * (1 - p) / p);
const med = xs => { const a = xs.slice().sort((x, y) => x - y), n = a.length; return n % 2 ? a[(n - 1) / 2] : (a[n / 2 - 1] + a[n / 2]) / 2; };
const norm = s => String(s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase()
  .replace(/\b(fc|cf|afc|sc|ac|as|ss|ssc|us|rc|cd|ud|sd|rcd|ca|vfl|vfb|tsg|sv|1\.|fsv|bsc|hsc|ogc|stade|olympique|de|club|calcio|real|athletic)\b/g, ' ')
  .replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim();
// FDCUP-2026-10-27: the same club spelled two ways (ESPN vs FanDuel)
const ALIAS = [[/\bcologne\b/g, 'koln'], [/\bmonchengladbach\b/g, 'mgladbach'], [/\bmunich\b/g, 'bayern'],
  [/\bsporting cp\b/g, 'sporting'], [/\bpsg\b|\bparis saint germain\b|\bparis st g\b/g, 'paris'], [/\binternazionale\b/g, 'inter'],
  [/\bmanchester\b/g, 'man'], [/\bwolverhampton wanderers\b/g, 'wolves'], [/\btottenham hotspur\b/g, 'tottenham']];
const alias = s => ALIAS.reduce((x, [re, to]) => x.replace(re, to), s);
const toks = s => { let t = alias(norm(s)).split(' ').filter(w => w.length > 2); if (!t.length) t = String(s || '').toLowerCase().split(/[^a-z0-9]+/).filter(w => w.length > 2); return new Set(t); };
const sim = (a, b) => { const A = toks(a), B = toks(b); if (!A.size || !B.size) return 0; let n = 0; for (const x of A) if (B.has(x) || [...B].some(y => y.startsWith(x) || x.startsWith(y))) n++; return n / Math.min(A.size, B.size); };

async function bpKey() {
  const html = await text(PAGE);
  const srcs = new Set();
  for (const m of html.matchAll(/(?:src|href)="([^"]+\.m?js[^"]*)"/g)) srcs.add(new URL(m[1], PAGE).href);
  const queue = [...srcs], seen = new Set(), cands = new Set();
  while (queue.length && seen.size < 200) {
    const u = queue.shift(); if (seen.has(u)) continue; seen.add(u);
    let t; try { t = await text(u); } catch (e) { continue; }
    for (const m of t.matchAll(/["'`](\/?[\w\-./]+\.m?js)["'`]/g)) { try { const v = new URL(m[1], u).href; if (/bettingpros/.test(v) && !seen.has(v)) queue.push(v); } catch (e) {} }
    const re = /x-api-key|apikey|api_key|apiKey/ig; let m;
    while ((m = re.exec(t))) for (const x of (t.slice(Math.max(0, m.index - 400), m.index + 400).match(/[A-Za-z0-9_\-]{24,64}/g) || []))
      if (/[0-9]/.test(x) && /[A-Z]/.test(x) && /[a-z]/.test(x)) cands.add(x);
  }
  for (const c of cands) { const r = await fetch(API + 'events?sport=NBA&date=2026-01-15', { headers: Object.assign({ 'x-api-key': c }, UA) }); if (r.status === 200) return c; }
  throw new Error('no BettingPros key');
}

async function fixtures(date) {
  const out = execFileSync('node', [path.join(__dirname, 'slate_scan.js'), date, '--json'], { encoding: 'utf8', maxBuffer: 1 << 24 });
  const rows = JSON.parse(out).fixtures.filter(r => r.admit);
  const base = Date.parse(date + 'T00:00:00Z'), ymd = date.replace(/-/g, '');
  const seed = { date, _note: `AUTOSOCCER: built in the cloud by auto_slate.js at ${new Date().toISOString()}`, matches: {} };
  const bySlug = {};
  for (const r of rows) (bySlug[r.espn[0]] = bySlug[r.espn[0]] || []).push(r);
  for (const [lg, rs] of Object.entries(bySlug)) {
    const j = await getJSON(`${ESPN}/${lg}/scoreboard?dates=${ymd}`);
    for (const r of rs) {
      const ev = (j.events || []).find(e => String(e.id) === String(r.id)); if (!ev) continue;
      const cs = (ev.competitions || [{}])[0].competitors || [];
      const home = ((cs.find(c => c.homeAway === 'home') || {}).team || {}).displayName;
      const away = ((cs.find(c => c.homeAway === 'away') || {}).team || {}).displayName;
      if (!home || !away) continue;
      seed.matches[slugify(home) + '-v-' + slugify(away)] = { home, away, kickoff: Math.round((Date.parse(ev.date) - base) / 60000), league: r.league, espn: [lg, String(r.id)] };
    }
  }
  return seed;
}

async function scorers(fx, key) {
  const H = { headers: Object.assign({ 'x-api-key': key }, UA) };
  const J = async u => (await fetch(API + u, H)).json();
  const d1 = new Date(Date.parse(fx.date + 'T12:00:00Z') + 864e5).toISOString().slice(0, 10);
  const evs = [];
  for (const d of [fx.date, d1]) evs.push(...((await J('events?sport=SOCCER&date=' + d)).events || []));
  const nm = e => { const P = e.participants || []; const f = id => (P.find(p => p.id === id) || {}).name || ''; return [f(e.home), f(e.visitor)]; };
  const join = {};
  for (const [slug, m] of Object.entries(fx.matches)) {
    let best = null, bs = 0;
    for (const e of evs) { const [h, a] = nm(e); const s = Math.min(sim(m.home, h), sim(m.away, a)); if (s > bs) { bs = s; best = e; } }
    if (best && bs >= 0.5) join[best.id] = slug; else console.log(`  scorers: no BettingPros event for ${slug}`);
  }
  const ids = Object.keys(join), out = {};
  for (const [mid, tag] of [[412, 'ags'], [417, 'fgs']]) {
    const acc = {};
    for (let i = 0; i < ids.length; i += 25) for (let page = 1; ; page++) {
      const o = await J(`offers?sport=SOCCER&market_id=${mid}&event_id=${ids.slice(i, i + 25).join(':')}&limit=25&page=${page}`);
      for (const off of (o.offers || [])) {
        const slug = join[off.event_id]; if (!slug) continue;
        const P = {}; (off.participants || []).forEach(p => { P[p.id] = p; });
        for (const s of (off.selections || [])) {
          const lab = String(s.label || s.selection || '').toLowerCase();
          if (/^(no|under)\b/.test(lab) || /no goalscorer|no scorer/.test(lab)) continue;
          const p = P[s.participant] || {}; const name = (p.name || s.label || '').trim();
          if (!name || !p.player) continue;
          for (const b of (s.books || [])) { const l = (b.lines || []).find(x => x.main) || (b.lines || [])[0];
            if (l && !l.is_off && typeof l.cost === 'number' && l.cost !== 0 && Math.abs(l.cost) < 40000) (acc[slug + '|' + name] = acc[slug + '|' + name] || []).push(ip(l.cost)); }
        }
      }
      const pg = o._pagination || {}; if (!pg.total_pages || page >= pg.total_pages) break;
    }
    out[tag] = Object.entries(acc).map(([k, ps]) => { const a = toAm(med(ps)); return k + '|' + (a > 0 ? '+' : '') + a; });
    console.log(`  ${tag}: ${out[tag].length} prices across ${new Set(out[tag].map(r => r.split('|')[0])).size} matches`);
  }
  return out;
}

// FDSOCCER-2026-10-26. Owner: "yes do that" -- BettingPros carries no goalscorer prices for some leagues (Ligue 1:
// PSG v Lyon on 10-26 cost the board its tickets). For any slate match BettingPros left unpriced, FanDuel's own
// sportsbook API (one book, not a median): event list from the soccer SPORT page, then event-page tab=goal-scorer,
// markets TO_SCORE (anytime) and FIRST_GOAL_SCORER. Reachable from a GitHub runner (probe 10-26).
const FD_AK = 'FhMFpcPWXMeyZxOx';
async function fanduel(fx, missing) {
  const out = { ags: [], fgs: [] };
  if (!missing.length) return out;
  const q = `&_ak=${FD_AK}&timezone=America%2FNew_York`;
  let base = null, evs = [];
  for (const st of ['nj', 'ny', 'pa']) {
    try { const j = await getJSON(`https://sbapi.${st}.sportsbook.fanduel.com/api/content-managed-page?page=SPORT&eventTypeId=1${q}`);
      evs = Object.values((j.attachments || {}).events || {}).filter(e => / v /.test(e.name)); base = `https://sbapi.${st}.sportsbook.fanduel.com/api/`; break; }
    catch (e) { console.log(`  FanDuel ${st}: ${String(e).slice(0, 100)}`); }
  }
  if (!base) return out;
  // FDCUP-2026-10-27. Owner: "the prices are already up. it should be done at the same time". The SPORT page lists only a
  // rotating subset of FanDuel's matches (10-27: 3 of 16 DFB-Pokal ties, no Copa del Rey or League Cup). When a match is
  // missing, read every competition's own listing (competition-page) too, so cup ties price in the same run.
  const findOk = () => missing.every(slug => { const m = fx.matches[slug]; return evs.some(e => { const [h, a] = e.name.split(' v ');
    return Math.min(sim(m.home, h), sim(m.away, a)) >= 0.5; }); });
  if (!findOk()) {
    let comps = [];
    try { const j = await getJSON(`${base}content-managed-page?page=SPORT&eventTypeId=1${q}`); comps = Object.values((j.attachments || {}).competitions || {}); } catch (e) {}
    const seen = new Set(evs.map(e => String(e.eventId)));
    for (let i = 0; i < comps.length; i += 8) {
      await Promise.all(comps.slice(i, i + 8).map(async c => {
        try {
          const j = await getJSON(`${base}competition-page?competitionId=${c.competitionId}&eventTypeId=1${q}`);
          for (const e of Object.values((j.attachments || {}).events || {}))
            if (/ v /.test(e.name) && !/\(/.test(e.name) && !seen.has(String(e.eventId))) { seen.add(String(e.eventId)); evs.push(e); }
        } catch (e) {}
      }));
    }
    console.log(`  FanDuel: ${evs.length} events after reading ${comps.length} competition listings`);
  }
  for (const slug of missing) {
    const m = fx.matches[slug], ko = Date.parse(fx.date + 'T00:00:00Z') + m.kickoff * 60000;
    let best = null, bs = 0;
    for (const e of evs) {
      if (Math.abs(Date.parse(e.openDate) - ko) > 6 * 3600e3) continue;
      const [h, a] = e.name.split(' v '); const s = Math.min(sim(m.home, h), sim(m.away, a));
      if (s > bs) { bs = s; best = e; }
    }
    if (!best || bs < 0.5) { console.log(`  FanDuel: no event for ${slug}`); continue; }
    try {
      const j = await getJSON(`${base}event-page?eventId=${best.eventId}&tab=goal-scorer${q}`);
      const n0 = out.ags.length;
      for (const mk of Object.values((j.attachments || {}).markets || {})) {
        const tag = mk.marketType === 'TO_SCORE' ? 'ags' : mk.marketType === 'FIRST_GOAL_SCORER' ? 'fgs' : null;
        if (!tag) continue;
        for (const r of (mk.runners || [])) {
          const a = (((r.winRunnerOdds || {}).americanDisplayOdds) || {}).americanOddsInt;
          if (r.runnerStatus !== 'ACTIVE' || typeof a !== 'number' || !a || /no goal ?scorer/i.test(r.runnerName)) continue;
          out[tag].push(`${slug}|${r.runnerName.trim()}|${a > 0 ? '+' : ''}${a}`);
        }
      }
      console.log(`  FanDuel ${slug} (${best.name}): ${out.ags.length - n0} anytime prices`);
    } catch (e) { console.log(`  ::warning::FanDuel ${slug}: ${String(e).slice(0, 120)}`); }
  }
  return out;
}

async function xg(fx) {
  let lgs = [...new Set(Object.values(fx.matches).map(m => m.league))];
  // FDCUP-2026-10-27: a cup tie (DFB-Pokal, Copa del Rey, League Cup...) has no understat league of its own -- its clubs
  // live in the domestic leagues, so a slate with any non-league fixture reads all five big leagues.
  if (lgs.some(l => !UNDERSTAT[l] && l !== 'MLS')) lgs = [...new Set(lgs.concat(Object.keys(UNDERSTAT)))];
  const y = +fx.date.slice(0, 4), mo = +fx.date.slice(5, 7), cur = mo >= 7 ? y : y - 1;
  const f = (x, n) => Number(x || 0).toFixed(n), rows = [];
  for (const lg of lgs.filter(l => UNDERSTAT[l])) for (const season of [cur - 1, cur]) {
    try {
      const j = await getJSON(`https://understat.com/getLeagueData/${UNDERSTAT[lg]}/${season}`,
        { 'X-Requested-With': 'XMLHttpRequest', referer: `https://understat.com/league/${UNDERSTAT[lg]}/${season}` });
      for (const p of (j.players || [])) {
        const t = +p.time, np = +p.npxG, sh = +p.shots;
        rows.push([UNDERSTAT[lg], season, p.player_name, p.team_title, p.position, p.games, p.time, p.goals, p.npg, f(np, 2), f(t ? np / t * 90 : 0, 2),
          p.shots, f(t ? sh / t * 90 : 0, 2), f(sh ? np / sh : 0, 4), f(p.xA, 2), f(t ? p.xA / t * 90 : 0, 2), p.key_passes, f(p.xGChain, 2)].join('|'));
      }
      console.log(`  understat ${lg} ${season}: ok`);
    } catch (e) { console.log(`  ::warning::understat ${lg} ${season}: ${String(e).slice(0, 120)}`); }
  }
  if (lgs.includes('MLS')) {
    for (const season of [cur, cur - 1].map(String)) {
      try {
        execFileSync('node', [path.join(__dirname, 'soccer_asa_fetch.js'), season, '/tmp/mls_' + season + '.psv'], { stdio: 'inherit' });
        rows.push(...fs.readFileSync('/tmp/mls_' + season + '.psv', 'utf8').split('\n').filter(Boolean));
      } catch (e) { console.log(`  ::warning::ASA MLS ${season}: ${String(e).slice(0, 120)}`); }
    }
  }
  rows.sort((a, b) => { const A = a.split('|'), B = b.split('|'); return (A[1] + A[0] + A[2]).localeCompare(B[1] + B[0] + B[2]); });
  return rows;
}

(async () => {
  const [date, dir] = process.argv.slice(2);
  fs.mkdirSync(dir, { recursive: true });
  let fx;
  try { fx = await fixtures(date); } catch (e) { console.log('::error::fixtures: ' + String(e).slice(0, 200)); return; }
  const n = Object.keys(fx.matches).length;
  console.log(`auto_slate ${date}: ${n} fixtures`);
  if (!n) return;
  fs.writeFileSync(path.join(dir, 'fixtures.json'), JSON.stringify(fx, null, 1) + '\n');
  let sc = { ags: [], fgs: [] };
  try { sc = await scorers(fx, await bpKey()); } catch (e) { console.log('::warning::BettingPros scorers: ' + String(e).slice(0, 200)); }
  try {
    const priced = new Set(sc.ags.map(r => r.split('|')[0]));
    const fd = await fanduel(fx, Object.keys(fx.matches).filter(s => !priced.has(s)));
    sc.ags.push(...fd.ags);
    const fpriced = new Set(sc.fgs.map(r => r.split('|')[0]));
    sc.fgs.push(...fd.fgs.filter(r => !fpriced.has(r.split('|')[0])));
    if (sc.ags.length) fs.writeFileSync(path.join(dir, 'ags.psv'), sc.ags.join('\n') + '\n');
    if (sc.fgs.length) fs.writeFileSync(path.join(dir, 'fgs.psv'), sc.fgs.join('\n') + '\n');
  } catch (e) { console.log('::warning::scorers: ' + String(e).slice(0, 200)); }
  const x = await xg(fx);
  console.log(`  xg rows: ${x.length}`);
  if (x.length) fs.writeFileSync(path.join(dir, 'xg.psv'), x.join('\n') + '\n');
})();
