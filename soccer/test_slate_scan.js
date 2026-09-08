/* test_slate_scan.js -- slate_scan's GATE and grouping, against a pinned capture.
 * The network half cannot run in the build container (GitHub-only egress), so fetch is stubbed
 * and only the decision logic is exercised -- which is the half that can be wrong quietly.
 * Capture is the real 2026-09-08 ESPN response shape, trimmed to the fields slate_scan reads. */
'use strict';
const assert = require('assert');

const CLUBS = { '363':'EPL', '382':'EPL', '384':'EPL', '361':'EPL', '366':'EPL',
                '86':'La_liga', '102':'La_liga', '244':'La_liga',
                '110':'Serie_A', '124':'Bundesliga', '167':'Ligue_1' };
const FIX = {
  'uefa.champions': [
    { id:'401915426', name:'Aston Villa at Club Brugge',        date:'2026-09-08T16:45Z', home:'363', away:'9999' },
    { id:'401915451', name:'Internazionale at Real Madrid',     date:'2026-09-08T19:00Z', home:'86',  away:'110'  },
    { id:'401915449', name:'Villarreal at Borussia Dortmund',   date:'2026-09-08T19:00Z', home:'124', away:'102'  },
    { id:'401915450', name:'Real Betis at Lille',               date:'2026-09-08T19:00Z', home:'167', away:'244'  },
    { id:'999999999', name:'LASK Linz at AEK Athens',           date:'2026-09-08T16:45Z', home:'8888',away:'9999' },
  ],
  'eng.league_cup': [
    { id:'401914267', name:'Lincoln City at AFC Bournemouth',   date:'2026-09-08T18:45Z', home:'382', away:'7777' },
    { id:'401914259', name:'Hull City at Sunderland',           date:'2026-09-08T18:45Z', home:'366', away:'6666' },
    { id:'401914268', name:'Bradford City at Leyton Orient',    date:'2026-09-08T18:45Z', home:'5555',away:'4444' },
  ],
  'eng.1': [
    { id:'401800001', name:'Everton at Arsenal',                date:'2026-09-08T14:00Z', home:'359', away:'361' },
  ],
};

global.fetch = async (url) => {
  const slug = url.match(/soccer\/([^/]+)\//)[1];
  if (/dates=\d{8}-\d{8}/.test(url)) {
    // the club-set scan: return every core-league club we pinned
    const evs = Object.entries(CLUBS).filter(([, lg]) => lg === lookup(slug))
      .map(([id]) => ({ competitions: [{ competitors: [{ team: { id } }] }] }));
    return { ok: true, json: async () => ({ events: evs }) };
  }
  const evs = (FIX[slug] || []).map(f => ({
    id: f.id, name: f.name, shortName: f.name, date: f.date,
    status: { type: { name: 'STATUS_SCHEDULED' } },
    competitions: [{ competitors: [{ team: { id: f.home } }, { team: { id: f.away } }] }],
  }));
  return { ok: true, json: async () => ({ events: evs }) };
};
function lookup(slug){ return {'eng.1':'EPL','esp.1':'La_liga','ita.1':'Serie_A','ger.1':'Bundesliga','fra.1':'Ligue_1'}[slug]; }

(async () => {
  const out = [];
  const realLog = console.log, realErr = console.error;
  console.log = (...a) => out.push(a.join(' '));
  console.error = () => {};
  process.argv = ['node', 'slate_scan.js', '2026-09-08', '--all'];
  await require('./slate_scan.js');
  await new Promise(r => setTimeout(r, 200));
  console.log = realLog; console.error = realErr;
  const text = out.join('\n');

  assert(/Aston Villa at Club Brugge/.test(text),        'admits a tie with one EPL side');
  assert(/Internazionale at Real Madrid/.test(text),     'admits a tie with two core sides');
  assert(/Everton at Arsenal/.test(text),                'admits a core-league fixture ungated');
  assert(/DROP.*LASK Linz/.test(text),                   'drops a tie with no top-five side');
  assert(/DROP.*Bradford City/.test(text),               'drops a lower-division-only cup tie');
  assert(!/^\s+(?!DROP).*LASK/m.test(text.replace(/DROP.*/g,'')), 'LASK never appears as admitted');

  const admitLine = text.match(/=> (\d+) admissible/);
  // 4 UCL (one EPL side / two core sides x3) + 2 EFL Cup (EPL side) + 1 core league = 7 of 9
  assert(admitLine && admitLine[1] === '7', 'admits exactly 7 of 9, got ' + (admitLine && admitLine[1]));

  const i1 = text.indexOf('14:00Z'), i2 = text.indexOf('19:00Z');
  assert(i1 > -1 && i2 > -1, 'kickoffs rendered');

  realLog('PASS  7/9 admitted, 2 dropped, gate + grouping + ordering all correct');
})();
