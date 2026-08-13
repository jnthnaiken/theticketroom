# The Ticket Room

A daily MLB home-run–prop handicapping board. It scores every carded bat with an
**additive 50/50 z-score blend** — half the market's implied probability, half a
basket of "unpriced-edge" signals the books miss or are late on (see Scoring) —
drafts the day's tickets (moons, salami round-robin, builder singles,
lunch/nightcap), and ships a single self-contained `index.html` that updates
itself live as lineups post and games finish.

There is **no base/projection score.** Kasper's `khr` projection is still shown on
each card as a display-only reference, but it does **not** feed the math.

---

## Daily workflow

Drop the day's input files in this folder (named with the slate date,
`YYYY-MM-DD`), then run the pipeline in order:

```
python grade_night.py        # 1. grade last night (off the FINAL re-assembled board) into season.json
python build15.py             # 2. score today's field  (SLATE_DATE env or today ET)
python regen15.py             # 3. assemble tickets + inject into index.html
python calibrate.py           # 4. (idempotent) log finalized nights -> calibration.jsonl
```

To pin a specific slate (e.g. rebuilding after midnight so the date can't drift):

```
SLATE_DATE=2026-06-29 python build15.py && python regen15.py
```

On GitHub the Action `pull-slate.yml` runs the whole pipeline (grade → build →
assemble → calibrate-backfill) and commits the rebuilt `index.html`. Then open
`index.html` — it runs live on its own from there, no server needed.

**Frozen boards:** the Action's verify step checks the slate's game states. When
every game is already **final**, it marks the board frozen and skips the
score/assemble/commit steps entirely — so a locked, graded board is never
re-drafted by a later scheduled run (the slate only advances when you commit a new
day's `cards_<date>.json`).

---

## Inputs (per slate date)

| File | What it holds |
|---|---|
| `cards_<date>.json` | Kasper matchup cards (zone, form, pulled-barrel %, hard-hit %, launch angle, `test`) |
| `kasper_extras_<date>.json` | full Kasper stat sidecar, incl. **`khr`** (display-only HR projection) + fly-ball%, sample size, etc. |
| `lineups_<date>.json` | projected lineups + schedule (times, starters, park, weather, batter hands) |
| `odds_<date>.json` | consensus HR odds, `{name: american}` |
| `pitchers_<date>.json` | opposing-starter allowed contact `{name:{brl, pbrl, hh, fb}}` |
| `iso_<date>.json` | **legacy / unused** — ISO is no longer scored or displayed |
| `hr9_<date>.json` | opposing-pitcher HR/9 — legacy/optional (live HR/9 is fetched at build time) |

**`cards`, `lineups`, and `odds` are REQUIRED; `kasper_extras` and `pitchers` are
optional (though `pitchers` is now built every slate for all ~30 starters).** All five are **manual inputs you commit** — `cards`/`extras`/`pitchers`
from the Kasper matchup pages, `odds` from VegasInsider HR props, `lineups` from
RotoWire. `fetch_mlb.py` (in the Action) does **not** generate `lineups_<date>.json`;
it only writes `slate_auto` (weather + HR/9).

⚠️ **A missing required file falls back to the PRIOR day and breaks the build** — e.g. a
missing `lineups_<date>.json` makes `build15` iterate yesterday's games and
`KeyError` on a matchup today's cards don't have. Don't skip `lineups`.

⚠️ **Every file must use suffix-LESS names** (`Vladimir Guerrero`, not `… Jr.`).
`build15`'s `norm()` does not strip `Jr./Sr./II/III`, so a suffix on one file and not
another silently drops that player's odds/khr. Team codes: **AZ / ATH / CWS** (not
ARI/OAK/CHW), matching the cards' matchup keys.

⚠️ **`gn` must be UNIQUE per game (1, 2, 3, … N).** `build15` keys games by
`gn` (`gamemeta[gn]=g`) and stamps every bat `game = gn`. If two games share a `gn`
(e.g. you hardcode `gn:1` everywhere) they collapse into one game and the `GAME_CAP=4`
per-game pool cap throttles the WHOLE board to 4 bats/4 tickets. Number the games
sequentially. (`gn` is only 1/2 for a genuine doubleheader of the same matchup.)

`build15` also pulls **live weather (Open-Meteo) and opposing-pitcher HR/9 (StatsAPI)**
at build time and bakes them into TOTAL, so the shipped board matches the browser's
live re-draft. Both fetches fail gracefully — no network just falls back to the
lineup's wind/temp and a neutral pitcher term.

## Outputs

| File | What it is |
|---|---|
| `D_<date>.json` | the scored + assembled board data for that slate |
| `index.html` | the live board (self-contained; the only thing you open) |
| `season.json` | the running ledger (history, per-category units, graded nights) |
| `calibration.jsonl` | one row per scored bat per night: every model input + outcome (the fitting dataset) |

---

## Scripts

- **`grade_night.py`** — auto-grader. Reads `season.json`, finds the last graded
  night, and folds every fully-final night since then into the ledger off real
  play-by-play home runs. It grades the **baked board that actually shipped** —
  it loads `D_<date>.json` and grades those tickets **directly**; it does **not**
  import `assemble_tickets` and does **not** re-draft (a fresh re-assemble would
  diverge from the live board). It builds a `played` set from the play-by-play, so
  a carded leg who never took a plate appearance (benched / late scratch) **voids
  (refund), not a loss** — but the ticket list itself is graded as-baked. Postponed
  games void (refund). Never grades a night that isn't final yet, never
  double-grades. (Its only import from `calibrate` is `build_rows`/`load_extras`,
  which are currently unused here — calibration logging lives in `calibrate.py`.)
- **`build15.py`** — the scorer. Turns the carded field into a `TOTAL` per bat via
  the **additive 50/50 z-score blend** below (**no base, no multiplier stack** —
  the old multiplicative lambdas are still computed but vestigial). Also attaches
  display-only `khr`.
- **`regen15.py`** — assembles the tickets (via `assemble_tickets.py`) and injects
  `const D = …` into `index.html`. A **same-slate rebuild ALWAYS preserves the prior
  draft** (carries `prevD['tickets']` forward untouched — the live client handles
  confirm / scratch / refill), so a live, confirmed board is never re-drafted out from
  under a placed bet. It also applies one idempotent client patch: the **doubleheader
  ET time-match fix** (strips the `" ET"` suffix so a DH's in-progress game is graded
  live — see the 2026-07-11 note in `HANDOFF.md`). *(An older version used a
  `RULES_VERSION` lever to force a re-draft; it was removed after force-re-drafting a
  confirmed 07-09 board and swapping a bet leg.)*
- **`assemble_tickets.py`** — the ticket rules engine (pool gate, chalk routing,
  moons/salami/builders, lunch/nightcap, pricing).
- **`calibrate.py`** — per-bat outcome logger → `calibration.jsonl`. Logs every
  model input (power, zone, form, pitcher term, park, weather, **slot, platoon,
  market**), the full Kasper `k_*` extras, opposing-pitcher `p_*` allowed contact,
  and did-he-homer. Self-healing idempotent `backfill()` runs every build.
- **`cardnotes.py`** — per-card prose write-ups. `build15_legacy.py` — old scorer,
  retained only as an offline fallback.

---

## Scoring (build15)

There is **no base score.** `TOTAL` is an **additive 50/50 z-score blend** of the
market and an edge basket, each half standardized to unit variance so neither can
dominate:

```
edge_z = standardized( Σ w_i · z(signal_i) )   # the 3 edge signals below
mkt_z  = standardized( z(market implied prob) )
blend  = 0.5·mkt_z + 0.5·edge_z
baseTotal = 100 + 30·blend                      # weather-free blend score, centered ~100
TOTAL  = baseTotal · wxMult(wf)                 # × live Open-Meteo park factor (±10% cap)
```

The **market half** (`mkt_z`) is the standardized market implied probability and
**nothing else** — no other feature feeds it (the rationale for keeping the edge
half thin is that the books' price already reflects power, park, pitcher, weather,
platoon, slot, etc., so those don't need to be re-added). The **edge half** is a
weighted sum of exactly **three** z-scored signals — this is the live `_SIG` list
in `build15.py`, **refit 2026-07-31** via grouped-CV logistic regression on the
calibration log (16 clean nights, 7/9–7/28):

| signal | key | weight |
|---|---|---|
| expected power (park-neutral xISO, raw) | `_zxpow` | `0.13` |
| expected contact quality (Kasper xwOBAcon if the sidecar is populated, else Savant xwOBAcon) | `_zxwcon` | `0.50` |
| pitch-arsenal matchup (batter RV/100 × pitcher pitch mix, raw) | `_zars` | `0.37` |

(These were `.45/.35/.20` reasoned guesses before the 7/31 refit — xISO was
over-weighted and shifted onto xwOBAcon + arsenal. Weights sum to 1.0.)

⚠️ **The nine-signal edge basket described in older revisions is DEAD.** `_zbg`
(bullpen game), `_zxptr` (power trend), `_zpvel` (perceived velo), `_zspray`,
`_zpvd` (velo decline), `_zbtrk` (ball-tracking), `_zpark` (park eye) are all still
**computed and logged** but are **not** in `_SIG`, so none of them touch `TOTAL`
(and `W_BTRK`, `W_PVDECL`, `W_XPTREND` are hard-set to `0.0`). Only the three above
feed the score.

Both halves are re-standardized before the 0.5/0.5 blend, so the edge bites as
hard as the market even when it's thin. There is no `MKT_EXP` exponent anymore.

ISO is **gone** from the math. So is the **power index** as a scoring input:
`powidx`/`powraw` and the old multiplicative lambdas (`powT`, `zoneT`, `fF`,
`parkT`, `pM`, `mktT`) and the `_mm` term are all still computed in `build15.py`
but **no longer feed TOTAL** — vestigial. `powidx` survives only to drive display
and notes. The live StatsAPI HR/9 and bullpen pulls likewise feed display chips
only, never the score.

Batter handedness comes from the lineups (`away_hands`/`home_hands`, one L/R/S per
bat).

**Live-weather re-score.** After the blend, `TOTAL` is scaled by a bounded park-factor
term: `TOTAL = baseTotal · wxMult(wf)`, where `baseTotal` is the weather-free blend
score and `wxMult(wf) = clamp(1 + K·(wf−1), 1−CAP, 1+CAP)` (`K=1.0`, `CAP=0.10` → ±10%
max). `wf` is the Open-Meteo park factor (wind + temp + elevation). The server
(`build15.py`) and the client (`index.html`) compute `wxMult` identically, and the
client re-scores `TOTAL` from `baseTotal · wxMult(live wf)` on every ~6-min refresh
before re-drafting, so the draft reacts to weather as Open-Meteo updates. The pool
**gate** stays on the weather-free `blend` — weather moves the draft (ordering/roles),
not pool membership. Opposing-pitcher HR/9 remains a display chip only.

### Card display

- **`Model` chip** = the bat's `TOTAL` (our actual model score; drives every pick).
- **🧱 brick badge** = `khr` (Kasper's HR projection) — **display-only reference**, not in the math.
- **`Pitcher` chip** = 0–100 hittability of the opposing arm (50 = neutral, higher = more HR-prone), derived from the opposing-pitcher term — **display-only; it does not feed `TOTAL`.**
- **`POWER` / `Zone` / `Park`** chips = the respective inputs.

---

## Grading

`grade_night.py` grades the **baked `D_<date>.json` tickets directly** — it does **not** re-draft.
From the source: *"Grade the board that ACTUALLY SHIPPED (the baked D_<date>.json tickets). A fresh
server re-draft here diverges from the live board you bet (different builders), so grade the shipped
tickets directly."* Whatever is in `D_<date>.json` when it runs is what the ledger books, so the last
auto build of the night is the one that counts. (`HANDOFF.md` claimed a re-draft; that was stale and is
corrected there.)

## Ticket rules

- **Eligible field** = priced bats in the posted lineup, not scratched/voided,
  under 70% rain.
- **Rain bands** — `<40%` full eligibility (can anchor); **`40–49%` barred from
  anchoring** but still usable as a parlay leg or builder single; `50–69%` builder
  single only (no parlay legs); `70%+` out of the pool entirely.
- **Pool gate** — z-THRESHOLD on the blended score: keep every eligible bat whose
  `blend` z-score is **`>= Z_GATE` (0.75) SDs above the slate mean**
  (`assemble_tickets.py`). Scale/slate-independent — survives any weight change.
  Then trim to **at most 4 per GAME** (best by model, both teams combined — per-team
  would allow 6/game). No fixed size, no backfill. (`FLOOR=130` and the fixed-40 rank
  cut are dead fallbacks, used only if a board is missing `blend`.) The 4-per-game cap
  (raised from 3 on 2026-07-04) adds z-gate-passing depth so a scratched parlay leg can
  refill *in-gate* instead of starving the slip; one bat/game per **ticket** still holds,
  so no single ticket over-concentrates on one game.
- **Chalk / Chef's Table — the two engines DIFFER here, and the client is the one that ships.**
  `assemble_tickets.py` has `chalk = set()` and builds **no chef ticket at all**, so on the
  server the top favourites draft into moons/salami/builders like any other bat.
  `index.html` — the engine `regen15.py` actually runs — reserves the **`CHALK_N` (4) strongest
  bats by `strength`, one per game**, as the **Chef's Table** (a 4-leg round robin) and bars them
  from moons, salami and builders. Chef seats lock **per-leg**, at their own first pitch, and a
  sitting seat only changes hands if a challenger beats it by `CHEF_HYST` (0.02) of normalised
  strength. A bat already on a **placed** (frozen or clock-locked) parlay is **not chef-eligible**
  — a placed bet is a fact and the chef seat is still open, so the open one moves (2026-08-13).
  Lunch special and nightcap take the highest-model **non-chalk** bat not already on a parlay in
  their time windows, `<= +600`.
- **Anchors** — 4 total (3 moon anchors + 1 salami anchor), the strongest *fittable*
  bats by model `TOTAL`. **UP TO `ANCH_PER_GAME` (2) ANCHORS PER GAME** (2026-08-13, owner decision;
  this replaced the one-per-game rule added 2026-08-10 after Olson *and* Baldwin both anchored in
  NYM@ATL). Two strong bats in one game may each lead their own pair of moons — no ticket may still
  carry two bats from one game (`fits()`), so each slip is one anchor's worth of exposure, and
  `GAME_CAP` still bounds pool bats per game. **The candidate list is built in ROUNDS** — every game's
  best bat first, then every game's second — because a flat top-20 by strength fills up with *pairs*
  from time-isolated games, every 4-set then starves, and the board collapses (14 → 8 with 2 moons when
  this was first tried). The 4 are chosen to maximize clean moons → salami → combined strength, subject
  to `MOON_SLACK`.
- **Moons** — **2 per anchor** across 3 anchors = up to **6** moons. Each = an
  anchor + 2 longshots in distinct games, leg span ≤ `WIN` (120 min). An anchor
  ships both its moons or none; on a thin slate the **weakest anchor** demotes
  rather than ship a lopsided board.
- **Salami** ("biggest") — **MOONS WIN, THE SALAMI IS LEFTOVER.** The moons fill first and the
  all-or-none demote loop settles; the salami is then built from what they left behind, seed-based
  (try each candidate as a start seed, strongest first, and complete it to 4 distinct games inside
  one `WIN`). It ships **only as a full 4-leg set** — never a stub — and its **anchor is its
  strongest leg**, always: role rank must be monotone in strength *within* a slip, because the
  anchor seat is what earns the mirrored builder single (2026-08-13). If no 4-game in-window set
  exists among the leftovers, no salami ships.
- **Builders** (our straight singles) — the **parlay anchors only**, emitted as singles (no odds
  cap), in **both** engines. The conviction **"snubs"** (unused strong bats) were removed from the
  server on 2026-07-09 (over the ledger window snubs graded **−57u** vs anchors **+9u**). The
  client's snub arm is gone too: its header comment and the `lf` / `usedN` / `lnp` variables
  survive but the loop that used them does not, so builders == anchors on both sides. **The
  divergence this bullet used to warn about no longer exists** (verified 2026-08-13). Practical
  consequence: a strong bat in a game too time-isolated to carry a parlay reaches the board only
  as the lunch special or the nightcap — otherwise not at all.
- **Completability** — a partner is only taken if the ticket can still be *finished*: enough distinct
  in-window games must remain for the legs it still needs. `fits()` alone validates a ticket as it
  stands and will happily strand it — on 2026-08-13 a 3:07 anchor took a 4:05 partner on both moons,
  which pinned the window and put every 1:10/1:35 game out of reach, so both slips stalled at two legs
  and the anchor was demoted. Same failure the salami was given seed-based filling for on 2026-07-04.
- **No TOTAL floor on parlay legs.** `ge75()` keeps the name but its body is
  `a.filter(n => !pending(n))` — it excludes carried/resuming bats and nothing else. The pool
  gate (`Z_GATE`) is the only quality bar.

Key knobs: `Z_GATE=0.75` (pool gate), `GAME_CAP=4`, `WIN=120`, `NIGHT_WIN=60`,
`MOONS_PER_ANC=2`, `ANCH_PER_GAME=2`, `MOON_SLACK=2`, `CHEF_HYST=0.02`, `ANCH_HYST=0.02`.
`CHALK_N=4` is the Chef's Table in `index.html`; `assemble_tickets.py` has `chalk=set()` and builds no
chef ticket at all. `FLOOR=130` (server) is a dead fallback; the client's `FLOOR=41` is likewise unused
under `Z_GATE`. `strength()` = **normalized `TOTAL` alone, no market term** (2026-08-08 — `TOTAL`
already carries the market via `mktT`, so an odds weight double-counts).
⚠️ **Edge weights: the code does NOT match the documented refit.** `build15.py` `_SIG` is
`_zxpow 0.45 / _zxwcon 0.35 / _zars 0.20` with the comment *"edge rebuilt 2026-07-09 … bg/xptrend/pvel/
spray/pvd/btrk/park zeroed (calibration AUC<=0.51)"*, and `W_ARS=0.10`. The `xISO 0.13 / xwOBAcon 0.50 /
arsenal 0.37` refit described above as 2026-07-31 **was never applied to the source** (verified
2026-08-13). Reconcile deliberately — that is a modelling call, not a doc fix. Market is a flat 0.5 of
the blend (`blend = 0.5*mz + 0.5*ez`), which is current. Parlay stakes: moon round-robin
`risk=2.0u`, salami round-robin `risk=5.5u` (singles/builders stake `1u`).

---

## Live engine (index.html)

Every ~6 minutes the board: refreshes weather + opposing-pitcher HR/9 → updates the
weather/pitcher **chips** and **re-scores each bat's `TOTAL` from `baseTotal ·
wxMult(live wf)`** (the weather-free `baseTotal` and `wxMult` are baked/mirrored
server+client, so the client re-score matches the server bake) → pulls posted lineups
(confirm / scratch) and results (HRs / finals) → re-drafts on the re-scored numbers →
grades.

Behavior that's load-bearing:

- **Lock = whole ticket confirmed.** A ticket locks only when *every* leg is in the
  posted lineup (or its game is underway) and none is scratched. A locked ticket is
  emitted verbatim and never moves; a scratched leg drops it out of "confirmed" and
  the re-draft replaces just that leg while confirmed legs stay pinned. A scratched
  single with no replacement is dropped, never re-shown (`singleAlive` filter — a
  benched builder/lunch/nightcap single disappears rather than showing as a SOLD loss).
- **Benched/DNP legs VOID (refund), never a loss.** A leg whose batter took no plate
  appearance in a completed game is a refund, not a miss — in the persistent ledger
  (`grade_night.py`, off a play-by-play "played" set) and both client graders
  (`gradeTicket` tonight, `priorGrade` yesterday). Only *postponed* games voided before.
- **Doubleheaders.** When a matchup plays twice, the live grader picks the correct half
  by matching the board's expected game time to each schedule game's ET start time
  (`regen15.py` bakes in the ET-suffix fix so `"12:05 PM ET"` matches `"12:05 PM"` — without
  it BOTH halves were skipped and a HR in the game being played never registered). Note
  `gamePk` order does **not** track game order — game 1 can have the higher pk; use
  `gameNumber`. The nightly grader reads every game's play-by-play by name, so the ledger
  counts a DH HR regardless; the fix is about the live board.
- **Top-4 per GAME holds everywhere** — the pool and the span-fill fallback, so a
  game can never put a 5th bat on the regular board (chalk in lunch/nightcap exempt).
- **Builders = parlay anchors only**, on **both** engines. Conviction snubs were removed from the
  server on 2026-07-09 (over the ledger window snubs graded **−57u** vs anchors **+9u**) and the
  client's snub arm is gone too — its header comment and the `lf`/`usedN`/`lnp` variables survive but
  the loop that used them does not. **The server/client builder divergence this bullet used to warn
  about no longer exists** (verified 2026-08-13).
- **Moon pairing is enforced live.** After the refill, any anchor left with fewer than
  `MOONS_PER_ANC` (2) moons is repaired from the free pool, or demoted whole (never a
  single-moon anchor). A scratched-anchor moon **re-anchors to one replacement** for the
  whole pair; a `spanOk` guard drops any kept leg outside the replacement's game-time
  window, so a re-anchored moon **never exceeds `WIN`** — it refills in-window or demotes.
- **Salami is leftover — built (or rebuilt) client-side.** The Grand Salami runs *last*,
  after the moons are final, from the bats they leave behind (the broader eligible field,
  priced/in-lineup/<70% rain). It covers both a baked salami that lost a leg to a live
  scratch **and** a slate where the server's fresh draft shipped no salami at all (its
  salami rides a pre-chosen anchor a deep pool can absorb into a moon). The build is
  **seed-based** — it tries each candidate as a starting seed (strongest first) and
  completes a 4-leg, distinct-game, in-`WIN` set; greedy-by-strength alone would grab a
  time-isolated bat and strand the slip. Running last, it can never cannibalize a moon leg.
  ⚠️ *Grading caveat:* a client-built salami the server didn't bake is **not** in the
  graded ledger (`grade_night.py` reads the server board) — the same live-redraft/grading
  divergence that already applies to refilled legs. To make the ledger match exactly,
  rework the server salami to build from leftovers too.
- **Badges** read one way: 🔒 *confirmed* · `N/M confirmed` (partial) · *projected*.
- **No midnight rollover.** Once the calendar passes the slate date, the board
  freezes on that day with its locked/graded tickets and does not reset to projected.

---

## Ledger (season.json)

`season.json` is the source of truth for the running tracker; `grade_night.py` is
the only thing that writes its history. Current epoch is **since 2026-06-30**
(running **≈ +331u through 2026-07-31** — moons carry it at ≈ +362u, the salami
round-robin bleeds at ≈ −44u), rolling forward each morning as the prior night
settles. Per-category units, win counts, and the history curve are baked into
the board as `D.meta.season`.

> ⚠️ **The board's big "+Nu" season number is the SUM of the category `units`
> (`builder/moon/biggest/lunch/late`), not `history[-1]`.** `history` only feeds the
> sparkline. To correct the displayed total, edit the category `units` and add the
> same delta to `history[-1]` to keep the curve consistent.

> **Reality check.** Backtesting on the calibration data shows the model does **not**
> out-predict the HR-prop market (AUC ≈ 0.58 vs the market's ≈ 0.61). Builder singles
> bleed and the salami round-robin is unproven; moons are roughly break-even and the
> most plausible — but not proven — place for an edge. Treat th
