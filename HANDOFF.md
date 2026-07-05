# The Ticket Room — Handoff / Resume Notes (2026-07-04)

Quick-start status so a fresh session can continue without re-deriving context.

## 🎫 Live-engine ticket fixes (2026-07-04 session — DEPLOYED & verified)

All client-side in `index.html`'s live re-draft (`__assembleClient`), except the cap
which is mirrored server+client. Verified on `theticketroom.live` via in-page
`__assembleClient` simulation + a scratch stress-test (every single-leg, anchor, and
8-player heavy-scratch scenario → zero invariant violations).

- **Leg score = live model TOTAL.** Ticket-leg badge now reads the live `D.players[name].TOTAL`
  (falls back to `p.total`), so the Players-tab score and the Tickets weather-badge score match.
- **Builders re-derived on every live refresh** — anchors + conviction snubs from the *live*
  pool, so a bat that enters the pool after the server build (weather shift, e.g. James Wood)
  lands on the Tickets page, not only the Players tab.
- **Moon pairing enforced live (all-or-none).** After refill, an anchor short of
  `MOONS_PER_ANC`(2) is repaired from the free pool or demoted whole — never a single-moon anchor.
- **Per-game cap raised 3 → 4** in BOTH `assemble_tickets.py` (`GAME_CAP=4`, ~line 126) and
  `index.html` (the `_TC[t]>=4` nonchalk gate + the `_poolTeam…<4` span-fill). Pools stay
  identical; pool grew ~33 → ~42 bats, all still z-gate-passing. Adds depth so a scratched
  leg refills in-gate instead of starving the slip.
- **Salami built/rebuilt client-side from leftovers, seed-based.** Runs LAST (after moon
  pairing+repair) so it can't cannibalize a moon leg. Covers a baked salami that lost a leg
  to a scratch AND a slate where the server drafted no salami (its salami rides a pre-chosen
  anchor a deep pool absorbs into a moon). Seed-based: tries each candidate as a start seed
  (strongest first) → completes a 4-leg, distinct-game, in-`WIN` set. (Greedy-by-strength
  alone grabbed a time-isolated bat and stranded the slip — that was the bug.)
- **Re-anchor WIN guard.** A scratched-anchor moon re-anchors to one replacement for the pair;
  a `spanOk` check now drops kept legs outside the replacement's time window, so a re-anchored
  moon never exceeds `WIN`(120 min) — it refills in-window or demotes.
- ⚠️ **Grading divergence (known, not new):** a client-built salami the server didn't bake is
  NOT in the graded ledger (`grade_night.py` reads the server board). Same divergence that
  already applies to any live-refilled leg. Clean follow-up: make the *server* salami also
  build from leftovers (decouple it from the pre-chosen-anchor search) so the baked board matches.

The deploy loop this session: upload `index.html` (+ `assemble_tickets.py` for the cap) via
GitHub `/upload/main`, commit, run `pull-slate.yml` with slate `2026-07-04` (rebuilds July-4
`D` on top, preserves the JS), then GitHub Pages auto-deploys (`Deploy Pages` #… green). Pages
was congested and some deploys failed — the next `build-board` auto-run usually re-deployed;
otherwise re-run the Deploy Pages workflow.

## Where the model stands (DEPLOYED, server-side, verified working)

**Scoring is an ADDITIVE 50/50 z-score blend: market half + edge half.**
(This replaced the old multiplicative "market half × edge half" from the 6/30 handoff.)

```
edge_z = standardized( Σ w_i · z(signal_i) )    # the 9 edge signals below
mkt_z  = standardized( z(market implied prob) )
blend  = 0.5·mkt_z + 0.5·edge_z
baseTotal = 100 + 30·blend                       # weather-free blend score, centered ~100
TOTAL  = baseTotal · wxMult(wf)                   # × live Open-Meteo park factor (±10% cap)
```

Both halves are re-standardized to unit variance before the 0.5/0.5 blend, so the
edge bites exactly as hard as the market regardless of how thin the edge is
(`build15.py` ~lines 534–556). No auto-computed `MKT_EXP` exponent anymore.

- **Market half** (`mkt_z`) carries everything the books already price — power,
  opposing pitcher, park, weather, platoon, slot, zone, form.
- **Edge half** = the signals the books miss / are late on. Weights (all reasoned
  guesses, NOT yet fitted) live in `build15.py` `_SIG`:
  - `_zbg`   bullpen-game/opener flag — **W_BG = 0.20**
  - `_zxpow` expected power (xISO, park-neutral) — **W_XPOW = 0.18**
  - `_zars`  pitch-arsenal matchup (batter RV/100 × pitcher pitch mix) — **W_ARS = 0.16**
  - `_zxptr` recent expected-power trend (14d xwOBAcon vs season) — **W_XPTREND = 0.12**
  - `_zpvel` perceived velo (effective_speed, falls back to raw velo) — **W_PVEL = 0.10**
  - `_zspray` spray-angle × park pull-side × wind — **W_SPRAY = 0.09**
  - `_zpvd`  pitcher velo decline (recent raw velo vs season) — **W_PVDECL = 0.08**
  - `_zbtrk` ball-tracking (whiff/zone-contact) — **W_BTRK = 0.04**
  - `_zpark` park hitter's-eye (hand-set judgment dict `PARK_TRK`) — **W_PARKTRK = 0.03**
- **Server pool gate is Z-THRESHOLD based**: keep bats whose `blend` z-score is
  `>= Z_GATE (0.75)` SDs above the slate mean (`assemble_tickets.py` ~line 129).
  Scale/slate-independent. `FLOOR=130` is dead — only a fallback if a board is
  missing `blend`. The old fixed-40 rank cut is also fallback-only.
- **Chalk ban is removed** — `CHALK_N` still defined but `chalk = set()`; the top-4
  favorites now draft into moons/salami/builders like any other bat.
- `RULES_VERSION = "2026-07-04-redraft3"` in `regen15.py`.

## ✅ Both prior "BROKEN" items are FIXED (verified in current code)

1. **Client FLOOR gate** — `index.html:498` now sets `FLOOR=41` and line 552 does
   `fullrank.slice(0, FLOOR)` (a rank slice, top 41 by TOTAL), not a `TOTAL>=130`
   threshold. Scale-independent; a compressed TOTAL can't empty the pool.
2. **Client weather live re-score — RE-ADDED 2026-07-05 (weather-only, draft-only).**
   `build15.py` ships `baseTotal` (the weather-free blend) and bakes
   `TOTAL = baseTotal * wxMult(wf)`; `wxMult(wf)=clamp(1+WX_K*(wf-1),1-WX_CAP,1+WX_CAP)`
   with `WX_K=1.0, WX_CAP=0.10` (±10% cap). `liveUpdate()` refreshes `p.wf` (Open-Meteo)
   then recomputes `p.TOTAL = p.baseTotal * wxMult(p.wf)` before the re-draft (fallback
   to the baked `p.TOTAL` when `baseTotal` is absent, so older boards still render). The
   client `wfFor()` was brought to parity with the server `wf_of()` (elevation term +
   clamp) so baked `wf` == live `wf`. Weather moves the **draft** (ordering/roles via
   TOTAL) only — the pool gate stays on the weather-free `blend`. This is NOT the old
   multiplicative `TOTAL/(weather×pitcher)` re-score; it's a bounded, slate-independent
   multiplier on a shipped base score, so client and server never desync.

## ✅ The 4 "expected/unpriced" signals are BUILT (all in `build15.py`)

1. **Pitch-arsenal matchup** — `fetch_arsenal()` + `arsenalTfn`/`arsenal_raw` → `_zars` (W_ARS=0.16).
2. **Recent expected-power trend** — `fetch_bat_recent()` + `xptrendTfn` → `_zxptr` (W_XPTREND=0.12).
3. **Pitcher velo/stuff decline** — `fetch_pit_ext()` `release_speed` agg + `pvdTfn` → `_zpvd` (W_PVDECL=0.08).
4. **Spray-angle × park alignment** — `fetch_bat_spray()` + `pull_tail_of()` + `sprayTfn` → `_zspray` (W_SPRAY=0.09).

All still on educated-guess weights — no fitted outcomes yet (see Backtest reality).

## Data infra (reuse it) — in `build15.py`

- `_savant_csv(u, to=25)` — browser User-Agent (Savant WAF blocks default urllib), timeout param.
- `fetch_bat_track()` — chase/whiff/zone-contact + barrel/xiso/xwoba/xwobacon (batter custom leaderboard).
- `fetch_bat_spray()` — batter pull% (spray-angle leaderboard).
- `fetch_bat_recent(ids)` — rolling last-14d xwOBAcon per batter id (date-windowed statcast_search).
- `fetch_arsenal(kind)` — pitch-arsenal-stats: per player per pitch type → usage% + run_value/100 (both `'batter'` and `'pitcher'`).
- `fetch_pit_velo()` — fastball velo/arm/player_id (pitcher custom leaderboard).
- `fetch_pit_ext(ids)` — per-pitch perceived-velo (effective_speed), release_extension, AND raw release_speed. **URL needs `all=true` + full param scaffold** or the statcast_search CSV returns 0 rows.
- `PARK_TRK` dict + the `*Tfn` term functions.
- `calibrate.py` logs the model inputs + outcome per bat per night → `calibration.jsonl` (the fitting dataset).

Note: the old multiplicative lambdas (`powT`, `zoneT`, `fF`, `parkT`, `pM`, `mktT`)
and the `_mm` multiplicative term (~line 532) are computed but NO LONGER feed TOTAL —
effectively vestigial. `powidx` is still used (notes/display).

## ⚠️ Daily inputs — the gotchas that break a build

The build (`build15.py`) requires these per-slate inputs, keyed `<stem>_<date>.json`.
A missing one silently falls back to the **prior day**, which then mismatches the rest.

| file | required? | source | notes |
|---|---|---|---|
| `cards_<date>.json` | **yes** | Kasper matchup pages | `{MATCHUP:{TEAM:[{name,form_pct,form_arrow,pb,hh,la,zone,test}]}}` |
| `lineups_<date>.json` | **yes** | **RotoWire (MANUAL)** | see below — this is the #1 trap |
| `odds_<date>.json` | **yes** | VegasInsider HR props | `{name: american}` |
| `kasper_extras_<date>.json` | optional | Kasper matchup pages | carries `khr` (the 🧱 base-score badge) |
| `pitchers_<date>.json` | optional | Kasper "Top Slate Pitchers" | `{name:{brl,pbrl,hh,fb}}`; unlisted arms → live HR/9 |

**`lineups_<date>.json` is NOT auto-pulled.** `fetch_mlb.py` only writes `slate_auto`
(weather + HR/9); nothing generates `lineups_`. It's a manual RotoWire input. If it's
missing, `build15` uses yesterday's games and dies with `KeyError: '<old matchup>'`
because today's cards don't have that matchup. This is what failed the 07-03 build.
Format: `{games:[{matchup,time,away,home,away_sp:[name,hand],home_sp:[name,hand],status,dome,precip,temp,wind,away_bats:[...],away_hands:[L/R/S],home_bats:[...],home_hands:[...],gn}]}`.
Team codes must match the cards keys — use **AZ** (not ARI), **ATH** (not OAK), **CWS**.

**Name-suffix convention — everything must be suffix-LESS.** `build15`'s `norm()` is
suffix-SENSITIVE (it does NOT strip `Jr./Sr./II/III`). So cards, odds, extras, and
lineups must ALL drop suffixes or a star silently loses its odds/khr (e.g. card
"Vladimir Guerrero Jr." never matches odds "Vladimir Guerrero"). The Kasper matchup
pages KEEP suffixes → strip them when building cards/extras. VegasInsider and the user's
historical files are already suffix-less. (Stripping on 07-03 lifted odds coverage
241→248 and khr 330→337.)

**khr sourcing.** Kasper's Export is "under construction," so `kasper_extras` is now
hand-built by reading the KHR column off each of the 13 matchup pages (`?game=<pk>`),
rounded to int. cards fields come from the same matchup roster tables.

## 🩹 Grading / behavior fixes (this session)

- **Benched/DNP legs now VOID (refund), never a loss.** Old code only voided
  *postponed* games, so a benched player (game played, 0 plate appearances) graded as a
  miss → loss. Fixed in all three graders: `grade_night.py` (builds a `played` set from
  play-by-play), the client tonight-grader `gradeTicket`, and the client yesterday-grader
  `priorGrade` (with a boxscore-fetch guard so a failed fetch never false-voids).
- **Scratched singles are dropped from the board** (client `singleAlive` filter) — a
  benched builder/lunch/nightcap single disappears instead of showing as a SOLD loss.
- **Footer sources corrected** in `index.html` (Kasper, Savant, StatsAPI, RotoWire,
  Open-Meteo, multi-book odds — TeamRankings was dead).
- Not retroactive: nights already in `graded_nights` won't re-grade. Recompute if a
  benched-player loss is already baked into `season.json`.

## Backtest reality (important for weighting)

- Backtested the log (2,264 bats / 252 HR, 6/18–6/29): established signals don't beat
  the market; weather backtested flat. That's why the market carries its own half and
  the edge half is only unpriced signals.
- The edge signals still have thin/zero fitted outcomes — weights are reasoned guesses,
  not fitted. They firm up once a few more nights log + grade.
- README reality check: model AUC ≈ 0.58 vs market ≈ 0.61. Treat the board as a
  ranking/research tool, not a guaranteed-profit system.

## Deploy mechanics (how we ship)

- **Local `.py` files can't be run reliably** — the bash mount truncates long lines /
  injects nulls (confirmed: `build15.py` reads as a binary/null-injected file). The
  Read/Edit tools are authoritative. Short-line scripts DO run; keep generated `.py`
  data on short lines, or better, do merges/parsing in browser JS or write JSON directly.
- **The build itself must run on the GitHub Action** — the sandbox has no network (403
  to StatsAPI/Savant/Open-Meteo) and can't run `build15.py`. So: commit inputs, then run
  the Action.
- **Committing input JSON via the GitHub web editor (works, verified today):** open
  `/new/main` (or `/delete/main/<file>` then `/new/main` to replace), set the filename
  input via the native value setter + `input` event, then paste content into CM6 by
  dispatching a synthetic `ClipboardEvent('paste',{clipboardData})` on `.cm-content`.
  **Transport big content as a JS string in the `javascript_tool` call itself** (its
  input isn't truncated; only its *return* is). Validate before committing with a
  char-count check (`C.length === <bytes>` — Python `len()` of the UTF-8 decoded string
  equals JS `.length` for BMP text) plus `JSON.parse`. Then click "Commit changes…" →
  the dialog's "Commit changes" (defaults to commit-to-`main`).
  - To READ a committed/local file back into a JS string for injection, `get_page_text`
    does NOT truncate (unlike `javascript_tool`'s return) — dump the string into a
    `<pre>@@S@@…@@E@@</pre>` and read it back whole.
- **Run** = `workflow_dispatch` on `pull-slate.yml` ("Run workflow", blank slate-date =
  latest committed cards). The `verify` step skips score+commit if the StatsAPI pull
  isn't fresh (0 HR/9 arms) — a fast "success" (~29s) that DIDN'T rebuild; a real build
  is ~90s and writes `D_<date>.json`.
- **Verify** = fetch `raw.githubusercontent.com/.../main/D_<date>.json` and check
  `players`/`tickets`/`meta.build`. GitHub Pages (`theticketroom.live`) redeploys within
  ~1 min of the commit; compare its `index.html` byte length to `main`'s to confirm.

## Suggested resume order

1. **Each slate: commit all 5 inputs, then run the Action.** Don't forget
   `lineups_<date>.json` (manual, RotoWire) and keep every file suffix-less. Verify the
   run actually rebuilt (`D_<date>.json` present, ~90s) — a 29s "success" skipped it.
2. Let more nights log + grade, then backtest the 9 edge signals for real and refit
   the `_SIG` weights (they're currently guesses).
3. **Server-salami rework (ledger consistency):** the client now builds the salami from
   leftovers when the server ships none, but the graded ledger reads the *server* board.
   Decouple `assemble_tickets.py`'s salami from the pre-chosen-anchor search — build it from
   whatever the moons leave behind (mirror the client's seed-based leftover build) — so the
   baked board carries the same salami the user sees/bets.
4. Optional cleanup: fix the stale `liveUpdate` comment and prune the vestigial
   multiplicative lambdas/`_mm` in `build15.py`.
5. Keep an eye on the edge-vs-market AUC gap; the edge half is unproven.

(Last verified: 07-04 board built & deployed with the live-engine ticket fixes above —
cap=4 pool (42 bats), 6 paired moons + salami + builders + nightcap, salami robust to
scratches, zero invariant violations across the scratch stress-test.)
