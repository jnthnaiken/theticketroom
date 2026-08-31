/* soccer_asa.js -- MLS xG rows for xg.psv, from American Soccer Analysis.
 * ASAXG-2026-08-31. Owner: "lets find a second xg source for mls" -> "wire it".
 *
 * WHY A SECOND SOURCE AT ALL. Understat is SIX leagues and stops: EPL, La liga, Bundesliga,
 * Serie A, Ligue 1, RFPL. Checked on the site itself 2026-08-31, and the six are the whole nav.
 * There is no MLS there and there is not going to be. Without an xG row a player still prices --
 * `soccer_mock` gives him `has_xg: False` and he scores on the market term alone (blend =
 * 0.5 * mkt_z) -- so an all-MLS board would have been pure "back the shortest price", which is
 * the thing Z_GATE and the edge blend exist to prevent.
 *
 * THE SOURCE. https://app.americansocceranalysis.com/api/v1/mls/ -- free, public, JSON, no key.
 * Three endpoints:
 *     players/xgoals?season_name=YYYY              minutes, shots, goals, xgoals, key_passes, xassists
 *     players/xgoals?...&shot_pattern=Penalty      the same, penalties only
 *     players?player_id=a,b,c   /   teams          names (batch these -- ~300 ids per call)
 *
 * 🚨 npxG IS NOT `xgoals`. ASA's xgoals INCLUDES penalties, so npxG has to be derived:
 *
 *     npxG   = xgoals(all) - xgoals(Penalty)
 *     npg    = goals(all)  - goals(Penalty)
 *     shots  = shots(all)  - shots(Penalty)
 *
 * which is exactly Understat's definition. Verified on the live 2026 season: 51 of 642 qualified
 * players have penalties, at ~0.78 xG each, which is the standard penalty value.
 *
 * ⚠️ DO NOT USE `shot_pattern=Regular` FOR THIS. It returns 200 and looks like what you want, but
 * "Regular" means OPEN PLAY -- it drops set pieces and corners as well as penalties. Using it
 * would quietly understate every target man on the board. Penalty-and-subtract is the only
 * spelling that matches what npxG means everywhere else in this pipeline.
 *
 * TWO xG MODELS ON ONE BOARD IS SAFE HERE, AND THE REASON IS STRUCTURAL. soccer_mock standardises
 * PER LEAGUE -- mkt_z, every sig_z, edge_z and shrink()'s mean all run inside `{p['league']}`
 * groups -- so nothing ever compares a raw ASA npxG to a raw Understat npxG, and a systematically
 * hotter or colder model washes out in the z-scores. It is the same reason Bundesliga and Ligue 1
 * already coexist. ⚠️ Any future change that pools leagues before standardising breaks this.
 *
 * TWO COLUMNS ASA CANNOT FILL, and both are free: `games` and `xGChain` are parsed at
 * soccer_mock.py:109-112 and NEVER READ AGAIN -- SIG uses npxg90/xgpershot/finish90/xa90,
 * blend_seasons uses those plus npg/npxg/minutes/pos/team, shrink weights by minutes. Checked by
 * grep, not assumed. They are written as 0 and that is not a silent loss.
 *
 * This file is the PURE TRANSFORM and has no network in it, so it is testable in a container with
 * no egress (test_asa.js, against fixtures/asa-2026-08-31.json). soccer_asa_fetch.js is the thin
 * fetching shell around it.
 */
(function (root) {
  'use strict';

  /* xg.psv column order, from soccer_mock.py's own parser. Keep them in this order. */
  var COLS = ['league', 'season', 'name', 'team', 'pos', 'games', 'minutes', 'goals', 'npg',
              'npxg', 'npxg90', 'shots', 'shots90', 'xgpershot', 'xa', 'xa90', 'kp', 'xgchain'];

  function r2(x, n) {
    var f = Math.pow(10, n == null ? 4 : n);
    return Math.round((x || 0) * f) / f;
  }

  /* per-90, guarding the zero-minute players ASA does return (Aron John, 3 minutes; Shane
     Donovan, 6). A divide by zero here would ship NaN into the PSV and poison zscores for the
     whole league, since `float('nan')` parses fine and then contaminates every mean. */
  function per90(v, mins) { return mins > 0 ? (v * 90) / mins : 0; }

  /* ROWS. `all` and `pen` are the two xgoals pulls, `players` and `teams` the lookups.
     A player with no penalty row simply has none -- pen defaults to zero across the board. */
  function rows(payload, opts) {
    opts = opts || {};
    var season = String(payload.season || opts.season || '');
    var league = opts.league || 'MLS';

    var nameOf = {}, teamOf = {}, penOf = {};
    (payload.players || []).forEach(function (p) { nameOf[p.player_id] = p.player_name; });
    (payload.teams || []).forEach(function (t) { teamOf[t.team_id] = t.team_name; });
    (payload.pen || []).forEach(function (p) { penOf[p.player_id] = p; });

    var out = [], skipped = [];
    (payload.all || []).forEach(function (a) {
      var name = nameOf[a.player_id];
      /* ⚠️ NO NAME, NO ROW. An xg.psv line keyed on a player id nobody can join to is worse than
         no line: `lookup()` would never match it, and it would still sit in the league group
         dragging every z-score toward itself. */
      if (!name) { skipped.push(a.player_id); return; }

      var pen = penOf[a.player_id] || { shots: 0, goals: 0, xgoals: 0 };
      var mins   = a.minutes_played || 0;
      var npxg   = (a.xgoals || 0) - (pen.xgoals || 0);
      var npg    = (a.goals  || 0) - (pen.goals  || 0);
      var shots  = (a.shots  || 0) - (pen.shots  || 0);
      /* floating-point subtraction can land a hair below zero on a player whose only shot was a
         penalty; a negative npxG is not a real quantity and would invert his edge term. */
      if (npxg  < 0) npxg  = 0;
      if (npg   < 0) npg   = 0;
      if (shots < 0) shots = 0;

      out.push({
        league:   league,
        season:   season,
        name:     name,
        team:     teamOf[a.team_id] || '?',
        pos:      a.general_position || '?',
        games:    0,                                   /* ASA has no appearance count -- unused */
        minutes:  mins,
        goals:    a.goals || 0,
        npg:      npg,
        npxg:     r2(npxg),
        npxg90:   r2(per90(npxg, mins)),
        shots:    shots,
        shots90:  r2(per90(shots, mins)),
        xgpershot: shots > 0 ? r2(npxg / shots) : 0,
        xa:       r2(a.xassists || 0),
        xa90:     r2(per90(a.xassists || 0, mins)),
        kp:       a.key_passes || 0,
        xgchain:  0                                    /* not in ASA -- unused, see the header */
      });
    });

    out.sort(function (x, y) { return (y.npxg90 - x.npxg90) || (x.name < y.name ? -1 : 1); });
    return { rows: out, skipped: skipped };
  }

  /* PSV. No header line -- soccer_mock.py splits every non-blank line on '|' and reads by
     position, so a header would parse as a player called "name" with int('games') blowing up. */
  function toPSV(rows) {
    return rows.map(function (r) {
      return COLS.map(function (c) { return r[c]; }).join('|');
    }).join('\n') + (rows.length ? '\n' : '');
  }

  var api = { COLS: COLS, rows: rows, toPSV: toPSV, per90: per90 };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.SoccerASA = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
