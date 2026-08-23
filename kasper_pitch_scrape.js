/* kasper_pitch_scrape.js -- per-game opposing-starter scrape for pitch.json
 *
 * WHY (2026-08-23): Kasper's own slate breakdowns lean on the STARTER's swing-and-miss more than
 * on anything else on the pitcher side -- "does Sugano have any swinging miss? No he does not,
 * these Guardians look to match up well." He wants a LOW-whiff arm, because a ball has to be put
 * in play before it can leave the yard. We were not collecting it: pitchers_<date>.json carried
 * only {brl, pbrl, hh, fb}, verified across 08-12 .. 08-22. calibrate.py has had p_csw / p_swstr
 * columns waiting since 2026-08-02 and they have been ~empty the whole time.
 *
 * The data was always right there -- the pitcher Summary table is IDENTIFIED by a header
 * containing both `Split` and `CSW%`, and we were throwing the column away.
 *
 * USE: paste into the console on each kasperbaseball.win/?game=<pk> page, or run it as part of
 * the accumulate loop the daily workflow already does:
 *     Object.assign(PITCH_ACCUM, window.__PSCRAPE());
 * then write PITCH_ACCUM to pitch.json and hand it to slate_assemble.py as usual.
 *
 * SHAPE -- strictly additive, nothing renamed:
 *   {"Nick Martinez": {
 *      brl, pbrl, hh, fb,              <- unchanged, what build15.pbrl_mult already reads
 *      csw, swstr, cs, ball, xwoba, la, bip, pit,     <- new flat fields off the "All" row
 *      vR: {...same keys...},          <- new: the vs RHH split row
 *      vL: {...same keys...}           <- new: the vs LHH split row
 *   }}
 *
 * The vR / vL splits are collected but NOT scored. build15 reads only the flat fields today;
 * the splits are there so the platoon matchup becomes measurable later without a re-scrape.
 * pitchers_<date>.json is archived per slate, so anything captured now is recoverable
 * retroactively by calibrate.repair().
 *
 * VERIFIED 2026-08-23 live on ?game=824799 (TB @ ---): two starters, both complete.
 *   Nick Martinez  brl 7.3  pbrl 4.7  hh 39.0  fb 27.1  csw 27.0  swstr 9.8
 *                  vR swstr 9.6 / vL swstr 10.1
 *   Shane Baz      brl 8.4  pbrl 5.0  hh 48.2  fb 25.7  csw 26.4  swstr 10.8
 *
 * NOTE the starter-name lookup walks UP from the table looking for "TEAM Starter<Name>". The
 * 2026-07-11 HANDOFF note says the name is at `up(table,3)[2]`; on the current build it is
 * `up(table,3)[0]`. The regex below does not care about the index, which is the point.
 * Suffixes are stripped (Jr./Sr./II/III/IV) -- build15's norm() is suffix-SENSITIVE, so an
 * unstripped starter silently loses his match.
 */
window.__PSCRAPE = function () {
  const num = s => {
    if (s == null) return null;
    const m = String(s).replace(/,/g, '').match(/-?\d+(\.\d+)?/);
    return m ? parseFloat(m[0]) : null;
  };
  const strip = s => String(s || '').replace(/\s+(Jr\.?|Sr\.?|II|III|IV)$/i, '').replace(/\./g, '').trim();
  const out = {};

  document.querySelectorAll('table').forEach(t => {
    const hs = [...t.querySelectorAll('th')].map(h => h.textContent.trim());
    // a pitcher Summary table is the one whose header carries BOTH Split and CSW%
    if (!(hs.some(h => h.includes('Split')) && hs.some(h => h.includes('CSW')))) return;

    let e = t, name = null;
    for (let d = 0; d < 6 && e; d++, e = e.parentElement) {
      const m = (e.textContent || '').match(/([A-Z]{2,3})\s*Starter([A-Za-z'.\- ]+?)(?:Summary|Arsenal|Split|$)/);
      if (m) { name = strip(m[2]); break; }
    }
    if (!name) return;

    const idx = {};
    hs.forEach((h, i) => { idx[h] = i; });
    const pick = (cells, label) => (idx[label] != null ? num(cells[idx[label]]) : null);

    const rows = [...t.querySelectorAll('tr')]
      .map(r => [...r.querySelectorAll('td,th')].map(c => c.textContent.trim()));

    const rec = {};
    for (const cells of rows) {
      const split = (cells[0] || '').replace(/[▸\s]/g, '');
      if (!['All', 'vsRHH', 'vsLHH'].includes(split)) continue;
      const v = {
        brl:   pick(cells, 'Brl/BIP%'),
        pbrl:  pick(cells, 'PullBrl%'),
        hh:    pick(cells, 'HardHit%'),
        fb:    pick(cells, 'FB%'),
        csw:   pick(cells, 'CSW%'),
        swstr: pick(cells, 'SwStr%'),
        cs:    pick(cells, 'CS%'),
        ball:  pick(cells, 'Ball%'),
        xwoba: pick(cells, 'xwOBA'),
        la:    pick(cells, 'LA'),
        bip:   pick(cells, 'BIP'),
        pit:   pick(cells, 'Pit'),
      };
      if (split === 'All') Object.assign(rec, v);
      else rec[split === 'vsRHH' ? 'vR' : 'vL'] = v;
    }
    if (Object.keys(rec).length) out[name] = rec;
  });

  return out;
};

/* A starter Kasper does not cover stays ABSENT from the file -- do NOT emit an empty row for him.
 * That is the designed unlisted-arm path (build15 falls back to live HR/9), and an empty row
 * both feeds nulls into the barrel-against multiplier and suppresses slate_validate's warning.
 * Dropping such a row is also what set up the SPFIRST-2026-08-22 surname collision, so leave the
 * arm out entirely and let the validator say so. */
