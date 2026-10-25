/* TRIPPROBE-2026-10-24: owner away 10-28..11-10 with his only computer. What can the GitHub runner reach for
   soccer + football inputs without a browser? Prints a report; the workflow saves it to soccer-data:trip/probe.txt. */
const UA = { 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36',
             'accept': 'text/html,application/json;q=0.9,*/*;q=0.8', 'accept-language': 'en-US,en;q=0.9' };
async function get(u, h) { try { const r = await fetch(u, { headers: Object.assign({}, UA, h || {}) }); const t = await r.text(); return [r.status, t]; } catch (e) { return ['ERR ' + String(e).slice(0, 80), '']; } }
function line(k, s, t, extra) { console.log(`${k.padEnd(34)} ${String(s).padEnd(6)} len=${t.length} ${extra || ''}`); }
const API = 'https://api.bettingpros.com/v3/';
const PAGE = 'https://www.bettingpros.com/nba/odds/player-props/first-basket/';
async function text(u) { const r = await fetch(u, { headers: UA }); if (!r.ok) throw new Error(r.status + ' ' + u); return r.text(); }

async function key_() {
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
  for (const [k, u, test] of [
    ['oddschecker winner page', 'https://www.oddschecker.com/football/english/premier-league/liverpool-v-brighton/winner', t => /Anytime Goalscorer/i.test(t)],
    ['oddschecker EPL index', 'https://www.oddschecker.com/football/english/premier-league', t => /-v-/.test(t)],
    ['oddschecker NFL', 'https://www.oddschecker.com/us/american-football/nfl', t => /-v-|-at-/.test(t)],
    ['understat EPL 2026', 'https://understat.com/league/EPL/2026', t => /playersData/.test(t)],
    ['understat league API', 'https://understat.com/getLeagueData/EPL/2026', t => /players/.test(t)],
    ['ESPN soccer scoreboard', 'https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard', t => /events/.test(t)],
    ['ESPN NFL scoreboard', 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard', t => /events/.test(t)],
    ['ASA MLS xgoals', 'https://app.americansocceranalysis.com/api/v1/mls/players/xgoals?season_name=2026', t => /player_id/.test(t)],
    ['DraftKings sportsbook API', 'https://sportsbook-nash.draftkings.com/api/sportscontent/dkusnj/v1/leagues/88808', t => /events/i.test(t)],
    ['FanDuel sbapi NFL', 'https://sbapi.nj.sportsbook.fanduel.com/api/content-managed-page?page=CUSTOM&customPageId=nfl&_ak=FhMFpcPWXMeyZxOx', t => /attachments/.test(t)],
  ]) { const [s, t] = await get(u); line(k, s, t, test(t) ? 'CONTENT-OK' : 'no-content'); }
  // BettingPros: the key the NBA room already uses, then NFL + soccer coverage
  let key = null; try { key = await key_(); console.log('BettingPros key: found'); } catch (e) { console.log('BettingPros key: ' + String(e).slice(0, 120)); }
  if (!key) { console.log('BettingPros key: none (probe uses fb_fetch.js path below)'); }
  const H = key ? { 'x-api-key': key } : {};
  for (const sp of ['NFL', 'EPL', 'SOCCER', 'MLS', 'LALIGA', 'SERIEA', 'BUNDESLIGA', 'LIGUE1', 'UCL']) {
    const [s, t] = await get(API + 'events?sport=' + sp + '&date=2026-10-25', H);
    let n = '-'; try { n = (JSON.parse(t).events || []).length; } catch (e) {}
    line('BP events ' + sp, s, t, 'events=' + n);
  }
  for (const sp of ['NFL', 'EPL', 'SOCCER']) {
    const [s, t] = await get(API + 'markets?sport=' + sp + '&limit=200', H);
    let names = ''; try { names = (JSON.parse(t).markets || []).map(m => m.id + ':' + (m.name || m.title || m.label || '')).filter(x => /touch|td|goal|scor/i.test(x)).slice(0, 25).join(' ; '); } catch (e) {}
    line('BP markets ' + sp, s, t, names);
  }
})();
