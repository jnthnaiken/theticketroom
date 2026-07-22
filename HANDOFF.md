# The Ticket Room — Handoff / Resume Notes (2026-07-08)

Quick-start status so a fresh session can continue without re-deriving context.

## ⛔ DAILY BUILD WORKFLOW — READ THIS FIRST, DO NOT ASK

Three live sources build a slate: **RotoWire** (lineups), **VegasInsider** (odds),
**Kasper** (cards + khr extras + pitchers). The user has all three tabs + the repo + the
live client open. Just build it — do not ask which sources or how.

**KASPER: WE DO NOT USE THE EXPORT. GO THROUGH EVERY MATCHUP PAGE, ONE BY ONE.**
Kasper's Export / Rolling / Zones are under construction — never touch them. For EACH game
on the slate, open its matchup detail page `kasperbaseball.win/?game=<pk>` and scrape that
game's roster tables. Accumulate across all games (N varies daily — 15 on a full slate),
then compile the three sidecars:
- `cards_<date>.json`  — per bat: name, form_pct, form_arrow, pb, hh, la, zone (roster
  columns: Zone Fit / kHR / HR Form / PullBrl% / HH% / LA).
- `kasper_extras_<date>.json` — per bat: `khr` (the 🧱 base-score badge), rounded int.
- `pitchers_<date>.json` — per opposing starter: brl, pbrl, hh, fb (pitcher / Top Slate
  Pitchers table).
Strip ALL name suffixes (Jr./Sr./II/III). The browser localStorage may hold a prior day's
`__cards_json`/`__extras_json`/`__pitchers_json` — those are STALE; clear the accumulator
(`__cards_accum` + `TT_*`) and re-pull today's games before compiling. Verify freshness by
checking the pitchers are today's starters, not yesterday's.

Do NOT propose using the Kasper export or ask the user to run it. Going matchup-by-matchup
IS the workflow, every single day.

## 🎯 2026-07-11 session — ledger reconciled, doubleheader live-grade FIXED, Kasper method locked

Built the **2026-07-11** board end-to-end (15 games, 388 bats, 13 tickets: 6 moon / 1 salami /
1 nightcap / 1 lunch / 4 anchors-only builders). Ledger stands at **+350.1u** (corrected
324.11 through 07-09, then 07-10 folded +25.95u). Carry these forward:

**1. The board's season total = SUM of category units, NOT `history[-1]`.** `drawTracker()`
sums `cats.{builder,moon,biggest,lunch,late}.units` for the big "+Nu" number; `history` only
feeds the sparkline. To correct the displayed total, edit the category `units` AND keep
`history[-1]` consistent (add the same delta to both). We hit this reconciling 07-09.

**2. 07-09 ledger correction (bet board vs re-drafted board).** A mid-slate `RULES_VERSION`
bump under the OLD regen15 force-re-drafted an already-confirmed board and swapped a confirmed
moon leg (Rice → Contreras); the wrong leg then graded (+11 instead of +103). Fixed surgically:
moon `units += 91.69`, `history[-1] += 91.69` → 324.11. **Lesson: never re-score / bump
`RULES_VERSION` while a slate is live and confirmed.** The CURRENT `regen15.py` is the
simplified preserve-and-inject with **no `RULES_VERSION`** — a same-slate rebuild ALWAYS
preserves the prior tickets, so this can't recur.

**3. DOUBLEHEADER live-grade bug — FIXED (deployed via a `regen15.py` swap).** On a DH the
live grader disambiguates by matching the board's expected game time to the schedule game's ET
start. It compared board gtime `"12:05 PM ET"` (carries a " ET" suffix) to `etOf()`'s
`"12:05 PM"` (no zone), so `_got !== _want` was ALWAYS true → BOTH halves skipped → a HR in
the game actually being played never registered (07-11 Valdez in MIL@PIT game 1). Fix: a
`re.subn` in `regen15.py` strips a trailing " ET" from both sides before comparing (idempotent;
bakes in on every build). Verified: board went from 0 HRs detected to catching Valdez/Bauers/
Frelick, lunch ticket graded a +5.48u win. **DH gotcha:** StatsAPI `gamePk` order does NOT
match game order — game 1 can have the HIGHER pk. Use `gameNumber`; when deduping a DH for the
slate, favor the game actually being played (In Progress). The nightly `grade_night.py` reads
every game's play-by-play by name, so the LEDGER always counts a DH HR regardless — only the
live board needed the fix.

### Kasper extraction — the exact fast method (matchup-by-matchup, NO export)

Kasper is a **static Next.js build**: the whole slate's data is baked into the JS bundle and
rendered per view — there is **no data API** to fetch. The per-game roster (with HH%/LA) only
renders on the game detail page. Method that worked cleanly on 07-11:

1. Build `pk→matchup` from StatsAPI (`schedule?sportId=1&date=<d>&hydrate=team`). Kasper's
   `?game=<pk>` uses the MLB `gamePk`. Dedupe DHs to one pk per matchup.
2. Per game: navigate `kasperbaseball.win/?game=<pk>`, then scrape the hitter roster tables
   (a table is a roster if its headers include `Zone Fit` and `kHR`). Columns present by
   default: Ceiling / Zone Fit / kHR / HR Form / ISO / xwOBA / xwOBAc / SwStr% / PullBrl% /
   Brl/BIP% / Sweet% / FB%. **HH% and LA are NOT shown by default** — the hitter table has 3
   `<select>` column-pickers whose options include `HH%` and `LA`; set two of them (native
   value setter + `change` event) so those columns render, then scrape. Team = the
   "TEAM vs Pitcher" heading above each roster table (skip the small unlabeled highlight table —
   it's a duplicate subset). Headers double-render (`"LALA"`, `"HH%HH%"`) → match by
   `includes()` and detect LA as `/LALA/`. Strip `LHB/RHB/SHB` + name suffixes off each name.
3. Accumulate into **`localStorage`** (a `window` var resets on navigation). Store the scraper
   itself in `localStorage` and run it per page as `await (eval(localStorage.getItem('SCRAPE')))()`;
   chain `navigate + scrape` ~5 games per `browser_batch` call to go fast.
4. Pitchers: the ROOT slate page's "Top Slate Pitchers" table has all ~12 arms in one place →
   `{name:{pbrl:PulledBarrel%, brl:BarrelBIP%, hh:HardHit%, fb:FB%}}`. Names are "Last, First" →
   reverse them.
5. Compile `cards`/`kasper_extras`/`pitchers`; transfer to disk via the base64-sink →
   `read_network_requests`(saved-to-file) → bash-reassemble channel; validate (every lineup bat
   has a card, stars matched suffix-less, teams == lineup teams); commit all 5 + run the Action.

## 🔧 2026-07-08 session — built today's board; two data-shape traps found & fixed

Built the full **2026-07-08** board end-to-end from the three live sources (RotoWire
lineups, VegasInsider odds, Kasper cards/khr/pitchers). Final board: **15 tickets**
(6 moon / 1 salami / 1 lunch / 1 nightcap / 6 builder), 388 pool bats, 291 priced,
388 khr, 362 bats carrying live pitcher barrel-against. Ledger rolled forward to
**builder 18-97** (graded 07-07's shipped board — 26 builders, 2 winners — on top
of the 16-73 that stood through 07-06). `RULES_VERSION` is now `"2026-07-08-redraft4"`.

Two traps cost most of the session — both DATA-shape issues, not model bugs:

1. **`gn` MUST be unique per game (1,2,3,…N).** `build15.py` does `gamemeta[gn]=g`
   and stamps each bat `game = gn`. Hardcode `gn:1` for every game and all games
   collapse onto game 1, `meta.wx` ends up with a single entry, and the `GAME_CAP=4`
   per-game cap throttles the ENTIRE pool to 4 bats → a 4-ticket board. Symptom:
   healthy scores (dozens pass the z-gate) but only 4 tickets, all singles, all tagged
   `game 1`. Fix: number the games sequentially when building `lineups_<date>.json`.

2. **A same-slate rebuild does NOT re-draft — you must bump `RULES_VERSION`.**
   `regen15.py` preserves the prior board's tickets on any same-date rebuild
   (`_same_slate` → carries `prevD['tickets']` forward). So after you FIX a bad input
   and rebuild the same slate, it keeps the OLD (bad) draft. To force one clean
   re-assemble, bump `RULES_VERSION` in `regen15.py` (sets `_ruleschg=True`). This
   session the gn-fix rebuild re-scored the players correctly but still shipped the
   stale 4 tickets until the version bump. (`_scratched` — a preserved leg going
   out/void — and `_stale` ISO notes also force a re-draft, but `RULES_VERSION` is the
   reliable manual lever.)

**VegasInsider odds parsing.** The HR-props table cells are formatted `o0.5 +575 +`
(over-0.5 line, American odds, indicator) across 5 book columns, NOT bare numbers.
Parse the last `[+-]\d{2,4}` per cell, drop `0`/blank, take the median across books.
Two extra gotchas: (a) the live-RENDERED DOM collapses most cells to `0` — read the
RAW server HTML instead (`fetch(url+'?_cb='+Date.now(),{cache:'no-store'})` then
`DOMParser`), which carries every book's real line; (b) the article headline can lag a
day (still shows yesterday's date) while the table underneath is today's — trust the
table, not the headline. This session's pull was 292 priced bats.

**pitchers file is now built for every starter** (not skipped). `pitchers_<date>.json`
= `{PitcherName:{brl, pbrl}}`, keyed by the OPPOSING starter's (suffix-less) name,
`brl`=Kasper "Brl/BIP%", `pbrl`="PullBrl%", read off each game page's
`{TEAM} Starter{Name}` → "Summary" split table ("All" row). Feeds the barrel-against
multiplier vs `BRL_BASE=7.5 / PBRL_BASE=5.0` in `build15.py`. Spot starters/openers
Kasper doesn't cover (this slate: Lazar, Kolek) are simply absent → live HR/9 fallback.


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
- `RULES_VERSION = "2026-07-08-redraft4"` in `regen15.py` (bumped 2026-07-08 to force a re-draft).

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
- **`grade_night` now grades the FINAL board, not the pre-game bake** (2026-07-05).
  Before scoring a night it imports `assemble_tickets`, marks any carded bat that took
  no plate appearance as `out`, and re-runs the draft — so the ledger grades the board
  that actually shipped (same pool the browser re-drafts on), not the tickets baked
  hours earlier. Wrapped in try/except: if the re-assemble fails it falls back to
  grading the baked board.
- **Frozen boards are never re-drafted** (2026-07-05). `pull-slate.yml`'s verify step
  now flags a slate whose games are all `final` and sets `fresh=false`, skipping the
  score/assemble/commit steps. Stops a locked, graded board from being re-drafted by a
  later scheduled run; the slate only moves when a new day's `cards_<date>.json` lands.
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
3. **Server-salami rework (ledger consistency):** the client now builds th
## 🛡️ 2026-07-21 — SLATE INPUT SCHEMA + SAFEGUARDS (read before assembling)

A mid-build container reclaim forced the input-assembler to be rebuilt from a
compaction summary, and three format regressions shipped and broke the live
board. To make that impossible again, two tools now live in the repo. USE THEM.

**`slate_assemble.py`** — canonical scraped-intermediates → 5 dated files. Never
hand-roll this transform again; if you must, diff against this file.
    python3 slate_assemble.py <YYYY-MM-DD> --dir <dir with cards.json/extras.json/pitch.json/roto.json/odds.json>
It writes the 5 files AND auto-runs the validator; it exits non-zero on any hard error.

**`slate_validate.py`** — pre-commit gate. ALWAYS run before commit/push:
    python3 slate_validate.py <YYYY-MM-DD>        # in the repo dir
Exit 0 = safe to commit+build. Exit 1 = DO NOT COMMIT.

### The 5-file contract build15.py actually consumes
- `cards_<d>.json`         `{MATCHUP:{TEAM:[{name,form_pct,form_arrow,pb,hh,la,zone,test}]}}`
- `kasper_extras_<d>.json` `{name:{khr,...}}`
- `odds_<d>.json`          `{name: american_int}`   (number, not string)
- `pitchers_<d>.json`      `{name:{brl,pbrl,hh,fb}}`
- `lineups_<d>.json`       `{"date":<d>, "games":[ per-game ]}`   ← OBJECT, not a bare list

### lineups per-game keys (every one required)
`gn`(int, UNIQUE per game), `matchup`, `away`, `home`, `time`, `status`,
`away_sp:[name,hand]`, `home_sp:[name,hand]`, `dome`(bool),
`precip`(int), `temp`(int), `wind`(str; "Dome" for domes),
`away_bats:[names]`, `away_hands:[hands]`, `home_bats`, `home_hands`.

### The three bugs that broke 2026-07-21 (all now caught by slate_validate.py)
1. **lineups written as a bare `[...]` list** instead of `{"games":[...]}` →
   build15 crashes at `lin['games']` (list indices must be int, not str).
2. **precip/temp emitted as strings** ("67%","81") instead of ints → build15 does
   `precip < 30`; the frontend skew/emoji logic misreads them.
3. **`gn` hardcoded to 1 for every game.** gn is the WEATHER-MAP KEY
   (`wx[str(gn)]`, `gamemeta[gn]=g`). All-1 collapses 15 games to one wx entry;
   the ticket renderer then hits `wxOf(p.game)` → undefined → crash
   "Cannot read properties of undefined (reading 'emoji')", and the header/date +
   summary tiles fall back to the June-15 defaults with `undefined` denominators.
   gn MUST be unique per kept game (1..N; doubleheaders keep game 1 only).

### GIT: do NOT run git through the device bridge
The cloud↔device mount cannot `unlink`, so every git write via `device_bash`
leaves `.git/index.lock` / `HEAD.lock` / `MERGE_HEAD` behind that then blocks the
user's native git. Let the USER run all git in their own terminal:
    git pull --no-rebase --no-edit   # scheduled build auto-commits to main; pull first
    git push
The `--no-edit` avoids the merge-message editor. If push is rejected, repeat
pull+push (the build races you). Assistant work stops at "files written to repo".
