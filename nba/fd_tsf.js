#!/usr/bin/env node
/* nba/fd_tsf.js -- TSF-2026-11-11. Archive FanDuel's "Team to Score First" prices for the slate (Winter's "first team
 * basket" -- owner: "bro team to score first is the same thing, come on"), so a tip-loser / first-team play can be
 * tracked against FanDuel's own price, not only BettingPros' history. Same shape and rules as fd_threes.js.
 *
 *     node fd_tsf.js 2026-11-11 slates/2026-11-11/tsf.psv
 *
 * Rows:  date|eventId|AWAY@HOME|team|american|fetched_at       (1st-quarter tab, marketType TEAM_TO_SCORE_FIRST)
 * Only games that have NOT tipped are (re)fetched; their rows replace the old ones, so the file keeps each game's last
 * pre-tip prices. Rows for games already underway are kept as they are. Never fatal: exit 0, file untouched on failure.
 * FanDuel's sbapi is reachable from a GitHub runner; TEAM_TO_SCORE_FIRST sits on the event page's 1st-quarter tab (probe 11-11).
 */
'use strict';
const fs = require('fs');
const AK = 'FhMFpcPWXMeyZxOx', UA = { 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36' };
const TEAM = { 'Atlanta Hawks': 'ATL', 'Boston Celtics': 'BOS', 'Brooklyn Nets': 'BKN', 'Charlotte Hornets': 'CHA', 'Chicago Bulls': 'CHI',
  'Cleveland Cavaliers': 'CLE', 'Dallas Mavericks': 'DAL', 'Denver Nuggets': 'DEN', 'Detroit Pistons': 'DET', 'Golden State Warriors': 'GSW',
  'Houston Rockets': 'HOU', 'Indiana Pacers': 'IND', 'Los Angeles Clippers': 'LAC', 'LA Clippers': 'LAC', 'Los Angeles Lakers': 'LAL',
  'Memphis Grizzlies': 'MEM', 'Miami Heat': 'MIA', 'Milwaukee Bucks': 'MIL', 'Minnesota Timberwolves': 'MIN', 'New Orleans Pelicans': 'NOP',
  'New York Knicks': 'NYK', 'Oklahoma City Thunder': 'OKC', 'Orlando Magic': 'ORL', 'Philadelphia 76ers': 'PHI', 'Phoenix Suns': 'PHX',
  'Portland Trail Blazers': 'POR', 'Sacramento Kings': 'SAC', 'San Antonio Spurs': 'SAS', 'Toronto Raptors': 'TOR', 'Utah Jazz': 'UTA',
  'Washington Wizards': 'WAS' };
const etDate = iso => new Date(Date.parse(iso) - 4 * 3600e3).toISOString().slice(0, 10);   // EDT; an EST slate shifts by an hour, harmless for evening tips

(async () => {
  const [date, out] = process.argv.slice(2);
  const q = `&_ak=${AK}&timezone=America%2FNew_York`, base = 'https://sbapi.nj.sportsbook.fanduel.com/api/';
  const get = async u => { const r = await fetch(base + u + q, { headers: UA }); if (!r.ok) throw new Error(r.status + ' ' + u); return r.json(); };
  let old = [];
  try { old = fs.readFileSync(out, 'utf8').split('\n').filter(Boolean); } catch (e) {}
  const page = await get('content-managed-page?page=CUSTOM&customPageId=nba');
  const evs = Object.values((page.attachments || {}).events || {})
    .filter(e => / @ /.test(e.name) && !/\(/.test(e.name) && etDate(e.openDate) === date);   // "(KNIGHT)" etc. are virtual games
  const now = Date.now(), stamp = new Date().toISOString().slice(0, 16) + 'Z';
  const fresh = [], refetched = new Set();
  for (const e of evs) {
    if (Date.parse(e.openDate) <= now) continue;               // tipped: keep its last pre-tip rows
    const [a, h] = e.name.split(' @ '), gm = (TEAM[a] || a) + '@' + (TEAM[h] || h);
    try {
      const k = await get(`event-page?eventId=${e.eventId}&tab=1st-quarter`);
      for (const m of Object.values((k.attachments || {}).markets || {})) {
        if (m.marketType !== 'TEAM_TO_SCORE_FIRST') continue;
        for (const r of m.runners || []) {
          const am = ((r.winRunnerOdds || {}).americanDisplayOdds || {}).americanOddsInt;
          if (r.runnerStatus !== 'ACTIVE' || typeof am !== 'number') continue;
          fresh.push([date, e.eventId, gm, TEAM[r.runnerName.trim()] || r.runnerName.trim(), am, stamp].join('|'));
        }
      }
      refetched.add(String(e.eventId));
    } catch (err) { console.log(`  ::warning::fd_tsf ${gm}: ${String(err).slice(0, 100)}`); }
  }
  if (!refetched.size) { console.log(`fd_tsf ${date}: nothing to refetch (${evs.length} games on FanDuel, all tipped or unreadable)`); return; }
  const keep = old.filter(l => !refetched.has(l.split('|')[1]));
  fs.writeFileSync(out, keep.concat(fresh).join('\n') + '\n');
  console.log(`fd_tsf ${date}: ${refetched.size} game(s) refreshed, ${fresh.length} rows, ${keep.length} kept`);
})().catch(e => console.log('::warning::fd_tsf: ' + String(e).slice(0, 200)));
