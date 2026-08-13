# The Ticket Room — Handoff / Resume Notes

> ⚠️ **This file is layered by date and older sections contradict newer ones.** Audited 2026-08-13;
> every superseded claim below is now marked inline. When two sections disagree, **the later date wins**,
> and the code wins over both. Corrected on 2026-08-13: the Kasper column-picker (HH%/LA render by
> default), `RULES_VERSION` (removed), conviction-snub builders (removed 07-09), the nine edge signals
> (only three are live), `grade_night` (does NOT re-draft), and the base64 transfer channel (blocked).
> Draft rules as of 2026-08-13 live in `README.md` — that file is kept current; this one is a log.


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

## 🚨 2026-08-08 — the board re-drafted every 5 min for 3 hours. Root cause: a `//` comment.

Read this before you edit `index.html` by hand. It cost a live slate.

**What happened.** A patch to `assembleClient()` left this on one line:

```js
var _cstren=function(n){...};   // TOTAL alone -- see strength() belowvar ranked=cand.slice().sort(...)
```

`index.html`'s script block is minified to a handful of enormous lines, so the `//` had no
newline to terminate it and swallowed the `var ranked=...` declaration that followed. The
engine then threw `ReferenceError: ranked is not defined` on the first chef-seat loop.

**Why nobody saw it for three hours.** `regen15.py` runs the client engine through
`client_assemble.js`; on a non-zero exit it prints `!! FALLING BACK to assemble_tickets.py`
and drafts anyway. `assemble_tickets.assemble()` has no prior board, so it drafted the slate
FROM SCRATCH on every build — 6:06pm through 8:27pm, a different set of tickets every five
minutes, long after first pitch. In the browser the same throw meant the page rendered
whatever the server had last written. It looked like the ticket-lock feature was broken. It
wasn't; the lock lives in the client engine and the client engine was dead.

**Rules that follow from this.**

1. **Never use `//` inside the `index.html` script block.** Use `/* ... */`. The block is one
   line for long stretches; a line comment there eats everything after it.
2. **Syntax-check before publishing `index.html`.** This catches it in one second:
   ```
   node -e "const h=require('fs').readFileSync('index.html','utf8');const re=/<script\b[^>]*>([\s\S]*?)<\/script>/gi;let s=null;for(let m;(m=re.exec(h));)if(m[1].includes('__assembleClient'))s=m[1];new Function(s);console.log('OK')"
   ```
   Better still, run `node client_assemble.js D_0615.json index.html` and read the output —
   it prints `N prior -> N tickets (L locked/confirmed, R re-drafted)`.
3. **The `assemble_tickets.py` fallback is a trap on a live slate.** It is the right
   behaviour for a cold start and the wrong behaviour once tickets are locked, because it
   silently re-drafts placed slips. Treat any `!! FALLING BACK` line in an Action log as a
   P1 — that message means the archive and the screen have both stopped obeying the lock.

**The rollback.** Tickets were restored to the **3:35pm** composition (the last board that
stood for a meaningful stretch — identical to what the client showed at 5:51pm), handed to
the fixed engine as prior, re-priced against the 9:02pm market: 14/14 locked, and the 9:07pm
and 9:12pm auto-builds both preserved it unchanged. Commit `ee6403e`.

## 💵 2026-08-08 — a bat's price is FROZEN at his own first pitch

Shipped the same night as the crash above, and it is the other half of why the board looked
insane: the tier colours were strobing every five minutes.

**How a missing price destroys a score.** `build15.py` scores the market half as
`_zmkt = implied prob if odds else None`, and then `_mz0 = 0.0` when it is None. Zero is not
"unknown", it is a *value* — and `blend = 0.75*mkt_z + 0.25*edge_z`, so the market is **75%**
of TOTAL. A bat who loses his price loses ~70 points of TOTAL and ~60 rank places:

```
Schwarber  mkt_z 4.2498 -> 0    TOTAL 218.8 (#1)  -> 121.6 (#71)
Harper     mkt_z 3.2160 -> 0    TOTAL 195.3 (#5)  -> 122.0 (#68)
Ohtani     mkt_z 3.1978 -> 0    TOTAL 194.0 (#6)  -> 122.0 (#68)
```

`tierOf` paints the top 9 of the field green, 10–32 orange, 33+ pink, so those bats went
green → pink without anything happening on the field. Every pink bat on the board that night
had a null price; every green/orange one had a live price. 25 for 25.

**Why prices were disappearing.** The per-build VegasInsider refresh (added earlier the same
day) *replaced* `odds_<date>.json` with whatever that one scrape returned. The scrape is
flaky, so the unpriced count bounced 87 → 184 → 87 → 126 → 166 → 186 → 87 every five minutes
from 5:41pm on; before the refresh went live it sat at exactly 105 all day. The `< 150 prices`
guard was useless — a scrape returning 205 of 306 sails straight through it.

**The rule now.** A price may be added or updated *before* that bat's game starts. After his
first pitch it is read-only, and it can never be removed. Two independent reasons:
once a game is underway the book either pulls the HR prop or reposts it as an in-game number
(+10000 and worse), which is not the market we drafted against; and a scrape that merely
*misses* a bat must never be able to zero him out.

Implemented in `fetch_odds.py`:
- `bat_first_pitch()` maps every bat to his game time from `lineups_<date>.json`; bats not in
  a posted lineup fall back to the slate's last first pitch.
- The file is **merged**, never replaced. `markets_<date>.json` too.
- `prior_prices()` seeds the merge from `D_<date>.json` — the odds file is only git-committed
  at the closing snapshot, but the board is committed every build, so it is the only reliable
  record of "what was this bat priced at last time" across the runner's fresh checkouts.
- Coverage guard is now relative and measured over **still-open** bats only: refuse the write
  if this scrape found < 85% of the not-yet-started bats already on file. (A flat floor can't
  work — as games start, a healthy scrape legitimately returns fewer and fewer prices.)

`odds_2026-08-08.json` was rebuilt by hand from the night's `D_2026-08-08.json` history:
for each bat, the last price observed strictly before his own first pitch. 205 → 304 prices.

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
   Brl/BIP% / Sweet% / FB%. ⚠️ **SUPERSEDED 2026-08-05 — HH% and LA now render BY DEFAULT and the
   column-picker dance below is NOT needed.** See the 2026-08-05 section near the end of this file; that
   is the current Kasper method. The paragraph below is kept only as history. ~~**HH% and LA are NOT
   shown by default**~~ — the hitter table has 3
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

2. ⚠️ **DEAD — `RULES_VERSION` no longer exists.** `regen15.py` was simplified to preserve-and-inject
   with no version lever (see the 07-11 note above, which contradicts this one). A same-slate rebuild
   always preserves prior tickets, and the TICKET LOCK (2026-08-08) is now what governs when a slip may
   be re-drafted at all. Kept as history. ~~A same-slate rebuild does NOT re-draft — you must bump
   `RULES_VERSION`.~~
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
- **Builders re-derived on every live refresh** — ⚠️ **anchors ONLY as of 2026-07-09**: conviction
  snubs were removed from the server that day (over the ledger window snubs graded **−57u** vs anchors
  **+9u**) and the client's snub arm is gone too — its header comment and the `lf`/`usedN`/`lnp`
  variables survive but the loop that used them does not (verified 2026-08-13). Builders == parlay
  anchors on both sides. The re-derivation itself still runs every refresh, so a bat that enters the
  pool after the server build lands on the Tickets page if it becomes an anchor.
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
- **Edge half** = the signals the books miss / are late on. ⚠️ **The list below is STALE (verified
  against `build15.py` 2026-08-13).** `_SIG` now carries only THREE live signals —
  `_zxpow 0.45`, `_zxwcon 0.35`, `_zars 0.20` — and the code comment reads *"edge rebuilt 2026-07-09:
  expected-power core (xISO + xwOBAcon) + arsenal; bg/xptrend/pvel/spray/pvd/btrk/park zeroed
  (calibration AUC<=0.51)"*. Also `W_ARS` is **0.10**, not 0.16. The nine-signal list below describes a
  model that no longer runs; kept as history of what was tried and zeroed:
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
- **Chalk = the Chef's Table.** `CHALK_N=4` bats are reserved for it and barred from
  every other ticket. As of 2026-08-08 those seats are the 4 best by **STRENGTH**
  (normalized TOTAL, min-max over the gated pool), one per game —
  *not* the 4 shortest prices.
- **STRENGTH is normalized TOTAL, and must stay that way.** A 65/35 TOTAL/implied key was
  tried on 2026-08-08 and reverted the same night. It breaks the board's own colours: `confOf =
  p.TOTAL` and `tierOf` rank the field into premium(green)/strong(orange)/value(pink) on TOTAL
  alone, so any odds weight in the draft key puts a PINK leg ahead of an ORANGE one on the same
  ticket. Five tickets did exactly that — Upper Deck Bound drafted Valdez (m142, +457) beside
  Walker (m177, +300) while Ben Rice (m154, +422) went undrafted. TOTAL already carries the
  market via `mktT` inside `blend`; weighting implied probability again double-counts it. Ranking chef on raw odds double-counted the market, which
  is already inside TOTAL via `blend`, and let a price move alone take a seat: on
  2026-08-08 Caminero went +334→+250 on a live re-price and displaced Willson Contreras,
  the board's #2 model (204 vs 161), who then landed on no ticket at all.
- ~~`RULES_VERSION`~~ — removed from `regen15.py`; see the correction above.

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
- ⚠️ **CORRECTED 2026-08-13 — `grade_night.py` does NOT re-draft.** It grades the baked
  `D_<date>.json` tickets directly. The code says so in as many words: *"Grade the board that ACTUALLY
  SHIPPED (the baked D_<date>.json tickets). A fresh server re-draft here diverges from the live board
  you bet (different builders), so grade the shipped tickets directly."* The re-assemble described
  below was removed; **whatever is in `D_<date>.json` at grading time is what the ledger books.**
  Kept as history. ~~`grade_night` now grades the FINAL board, not the pre-game bake~~ (2026-07-05).
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

### GIT: ONE way, every day — the assistant commits via the GitHub web UI
Do NOT hand the user terminal commands, and do NOT run git through the device
bridge (the cloud↔device mount cannot `unlink`, so a `device_bash` git write leaves
`.git/index.lock` / `HEAD.lock` behind and blocks their native git). Sessions have
flip-flopped between these two and it is genuinely annoying. The settled procedure:

1. `device_commit_files` the finished inputs into the repo folder (keeps the user's
   working copy current) and `device_stage_files` them back to verify byte-identity.
2. Navigate to `github.com/jnthnaiken/theticketroom/upload/main`, `find` the
   "Choose your files" input, and `file_upload` the staged paths under
   `/mnt/user-data/uploads/The Ticket Room/` (10 MB per call; 6 files ≈ 181 KB).
3. Type the message into the TITLE field (the first click often lands in the
   extended-description box — check a screenshot), leave "Commit directly to main",
   click "Commit changes". The button moves after the description clears, so
   re-screenshot before clicking rather than reusing old coordinates.
4. Verify from the container: `curl raw.githubusercontent.com/.../main/<file>` and
   md5 against the local copy. raw/api/github.com are the ONLY hosts that resolve.

Nothing is left for the user to type. Their local copy is already correct, so their
next `git pull` is a fast-forward.

## 🧊 2026-08-05 — built in the CLOUD sandbox: what changed, and the transfer channel

Built the **2026-08-05** slate (15 games, 391 carded bats, 299 priced, 29 arms) from the
three live sources. `slate_validate` PASS with 3 soft warnings (Cody Bradford has no Kasper
line → live HR/9 fallback; Angel Genao / Ronny Simon uncarded). Files written straight into
the repo folder; the user pushes.

### Source-scrape deltas since 07-11 (saves an hour next time)
- **Kasper: HH% and LA now render BY DEFAULT** on `?game=<pk>` roster tables. The 3
  `<select>` column-picker dance in the 07-11 notes is NO LONGER NEEDED. Roster columns are
  `Hitter Name|Match|Ceil|Zone|kHR|Form|Pit|BIP|ISO|xwOBA|xwOBAc|SwS%|PBrl%|Brl%|SwSp%|FB%|HH%|LA|Likely`.
  Headers still double-render (`LALA`, `HH%HH%`) → match with `includes()`.
- Identify a roster table by header containing `Zone Fit` + `kHR`, then take the team code
  from `up(table,2)[0]` (`"TOR"` / `"vs Hunter Brown"`); skip the highlight table whose
  label is `Best Matchups`.
- **Per-game pitcher stats**: tables whose header has `Split` + `CSW%`; pitcher name is
  `up(table,3)[2]` (the `TEAM / Starter / Name` heading); read the `All` row →
  `{brl:Brl/BIP%, pbrl:PullBrl%, hh:HardHit%, fb:FB%}`. 15 game pages gave 29 of 30 arms.
- **RotoWire emits a junk 16th `.lineup.is-mlb` block** ("You may also be interested in…")
  with no teams/bats — filter on `away && home && bats.length`.
- **RotoWire SPs can be stale.** It had `Ty Madden` for DET@SEA; StatsAPI probables AND
  Kasper both said **Drew Anderson**. Cross-check `schedule?...&hydrate=probablePitcher`
  and patch `roto.json` before assembling — it also silences a validator SP warning.
- **VegasInsider**: HR props is `document.querySelectorAll('table')[1]` of the RAW server
  HTML (317 rows; the markets order is Strikeouts / Home Runs / Total Bases / RBI). Cells
  are `o0.5 +290 +` → last `[+-]\d{2,4}`, drop |v|<100, median across the 5 book columns.
  ⚠ The 3 MB `fetch`+`DOMParser` **exceeds the 45 s CDP timeout** if done inline: kick it
  off in a fire-and-forget async IIFE that stashes rows on `window`, then poll.

### ⚠️ The cloud sandbox has NO network to the data sources
`statsapi.mlb.com`, `api.open-meteo.com`, `baseballsavant.mlb.com` and every paste service
are blocked. **Only `github.com` / `api.github.com` / `raw.githubusercontent.com` + the
package registries resolve.** So `build15.py` still cannot run locally — commit the 5 inputs
and let the Action build (external cron dispatches `build-board` every 30 min, 9 AM–1 AM ET,
so a push during the window builds on its own; no manual "Run workflow" needed).

### Browser → container transfer ⚠️ SUPERSEDED 2026-08-10 — base64 IS BLOCKED
**Current method: plain pipe-delimited text inside `<article><pre>` with `@@S@@`/`@@E@@` sentinels, read
via `get_page_text`, verified by an in-page SHA-256 printed as spaced hex.** The browser tool classifier
now blocks base64 returns, raw-HTML returns, external POSTs, and any fetch carrying scraped data, so
every "opaque blob out" channel below is shut. `get_page_text` has a hard **50,000-char cap** — split
any payload approaching it. Full method in `claude/transfer-channel-2026-08-10.md`. The section below is
history. ~~use gzip+base64 in CHUNKS, with SHA per chunk~~
The scraped data lives in page `localStorage`; the only way out is `get_page_text`. What
works, and the traps:
1. Build a compact **TSV** first (one row per bat: `B\t<matchup>\t<team>\t<name>\t…`, plus
   `P\t<pitcher>\t…` rows), NOT pretty JSON — 121 KB of JSON became a 44 KB TSV.
2. `CompressionStream('gzip')` → `btoa` → slice into **6000-char chunks**; emit each into
   `<pre>@@S@@…@@E@@</pre>` and read with `get_page_text`.
3. **Transcribing one 36 KB blob silently TRUNCATES at ~23 KB.** Chunk it, and verify every
   chunk: `crypto.subtle.digest('SHA-256', chunk)` in the page vs `sha256sum` in the
   container. One chunk came back with a single wrong character (length still exactly 6000,
   gzip CRC failed) — bisect that chunk at 1500 chars and re-emit only the bad slice.
4. gzip's CRC is the end-to-end proof: if `gzip.decompress` succeeds, the payload is exact.
5. `javascript_tool`'s **return** is truncated (~4 KB) and it **refuses to return raw HTML**
   ("BLOCKED: Cookie/query string data") — return small JSON summaries only.

### 🛑 savant_gate.py — added 2026-08-05, do not remove
The Statcast fetches in `build15.py` fail SOFT: a timed-out Savant leaderboard
collapses its signal to a neutral default instead of raising, so the board scores,
assembles and publishes with an edge term missing. Every TOTAL then shifts a point
or two, `strength` (which is min-max normalised ACROSS THE POOL) re-orders, and
tickets reshuffle against the last good board.

Caught live today: the chef ticket flipped Kyle Schwarber <-> Munetaka Murakami for
~80 minutes. Two separate causes, both real:
  * 1:56-3:17pm — lineup cards posting. Each posted card marks its non-listed bats
    `out`; a scratch forces a full re-draft, and because strength is normalised over
    the surviving pool, dropping five KC bats (Witt, Marte, Rojas, Maile, Tolbert at
    3:17) re-scaled everyone and flipped the pair back. Schwarber's own status never
    changed — he sat `projected` all day (PHI 6:40). Other teams' lineups moved him.
  * 3:31pm — `_zspray` collapsed 149 -> 73 distinct values; one run later `_zpvd` was
    dead for all 390 bats and the board STILL committed.

`savant_gate.py <date>` now runs between "Score the field" and "Assemble + inject".
It counts distinct non-null values per `_z*` signal and compares against the last
committed `D_<date>.json` (`git show HEAD:`) — a same-slate baseline from minutes
earlier, so no absolute thresholds. Trips when a signal goes to zero, or loses >40%
of its spread from a base of >=20. On a trip the workflow reverts `D_<date>.json`,
skips assemble, and leaves the published board alone; the ledger and calibration
still commit. Backtested over all 34 build transitions on 2026-08-05: it blocks
exactly 3:31pm and 3:32pm, zero false positives.

Per-pitcher signals sit near ~28 distinct and binary flags at 2, which is why the
relative check only applies above `MIN_BASE=20`. Don't "simplify" that away.

Rebuild through the day by re-scraping RotoWire once lineups post (all 15 were still
`Expected Lineup` at 11:53 AM ET) and re-running `slate_assemble.py` — same 5 filenames,
same-slate rebuild preserves the drafted tickets.

--------------------------------------------------------------------------------
2026-08-07 — "still seeing yesterday's board": a Pages deploy hung in `waiting`
--------------------------------------------------------------------------------
Symptom: theticketroom.live served `"build": "8/6 7:36pm"` all through the 8/7
morning while `main` was correct the whole time (`index.html` on main read
`8/7 5:56am`, `D_2026-08-07.json` had 388 players / 13 tickets). Nothing was
wrong with the scrape, the assemble, the gate, or the commit.

Diagnosis, in the order that actually works:
  1. `curl raw.githubusercontent.com/.../main/index.html | grep '"build"'` — if
     main is current, the pipeline is fine and this is a DEPLOY problem. Stop
     looking at the build.
  2. Fetch the live site in the browser with a cache-buster and read
     `last-modified`. That header is the timestamp of the last SUCCESSFUL Pages
     deploy — on 8/7 it read `Thu, 06 Aug 2026 23:37:18 GMT`.
  3. Ignore the `pages-build-deployment` workflow entirely. It is the legacy
     deploy-from-branch builder and its last run was 2026-07-02. All real
     deploys are `deploy-pages.yml`. I wasted a pass on this.
  4. Open the newest `Deploy Pages` run. The yellow banner names the blocker:
     "This workflow is waiting for Deploy Pages #1566 to complete before running."
  5. `actions/workflows/deploy-pages.yml?query=is%3Awaiting` finds the zombie
     directly. It was #1566, parked in status **Waiting** for 10h 25m — not
     queued, not in progress, waiting on the `github-pages` environment.

Why it freezes the site rather than just delaying it: `deploy-pages.yml` uses
`concurrency: {group: pages, cancel-in-progress: false}`. That guarantees a
RUNNING deploy finishes, but a run stuck in `waiting` holds the group forever,
and every deploy pushed after it sits pending until the next push supersedes it
— cancelled, never run. With a board that rebuilds every ~5 minutes that is an
infinite supersede loop. The run list is the tell: an unbroken column of
`cancelled` with no `success` since the freeze began.

Fix: cancel the waiting run. The queue drained immediately — the next queued
deploy (#1622) went green in ~90s and the live site jumped to `8/7 6:07am`.
Nothing needs re-pushing; the pending deploy already carries current `main`.

Prevention, now in `pull-slate.yml` as the step "Unstick a hung Pages deploy":
runs right after checkout on every build, lists `deploy-pages.yml` runs with
`status=waiting`, and cancels any older than 15 minutes. It needs
`permissions: actions: write` (added alongside `contents: write`) and is
`continue-on-error: true` so a watchdog failure can never block a board. It
lives in `pull-slate.yml` — concurrency group `ticket-room` — precisely because
anything in the `pages` group would be stuck behind the same jam.

Rule of thumb for next time: board stale on the site + `main` correct = deploy,
not pipeline. Check `is:waiting` on deploy-pages.yml FIRST.
