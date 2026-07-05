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
python grade_night.py        # 1. grade last night into season.json
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
optional.** All five are **manual inputs you commit** — `cards`/`extras`/`pitchers`
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
  play-by-play home runs. Postponed games void (refund). Never grades a night
  that isn't final yet, never double-grades.
- **`build15.py`** — the scorer. Turns the carded field into a `TOTAL` per bat
  (our multiplier stack; **no base**). Also attaches display-only `khr`.
- **`regen15.py`** — assembles the tickets (via `assemble_tickets.py`) and injects
  `const D = …` into `index.html`. Preserves the prior draft across same-input
  rebuilds; a `RULES_VERSION` bump forces a one-time re-draft when rules change.
  Also applies the idempotent display patches (Pitcher chip, Model chip, khr badge).
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
edge_z = standardized( Σ w_i · z(signal_i) )   # the 9 edge signals below
mkt_z  = standardized( z(market implied prob) )
blend  = 0.5·mkt_z + 0.5·edge_z
baseTotal = 100 + 30·blend                      # weather-free blend score, centered ~100
TOTAL  = baseTotal · wxMult(wf)                 # × live Open-Meteo park factor (±10% cap)
```

The **market half** (`mkt_z`) carries everything the books already price — power,
opposing pitcher, park, weather, platoon, slot, zone, form. The **edge half** is
only signals the books miss or are late on. Edge weights (`build15.py` `_SIG`,
all reasoned guesses pending fitted outcomes):

| signal | key | weight |
|---|---|---|
| bullpen-game / opener flag | `_zbg` | `W_BG = 0.20` |
| expected power (park-neutral xISO) | `_zxpow` | `W_XPOW = 0.18` |
| pitch-arsenal matchup (batter RV/100 × pitcher pitch mix) | `_zars` | `W_ARS = 0.16` |
| recent expected-power trend (14d xwOBAcon vs season) | `_zxptr` | `W_XPTREND = 0.12` |
| perceived velo (effective_speed, falls back to raw velo) | `_zpvel` | `W_PVEL = 0.10` |
| spray-angle × park pull-side × wind | `_zspray` | `W_SPRAY = 0.09` |
| pitcher velo decline (recent raw velo vs season) | `_zpvd` | `W_PVDECL = 0.08` |
| ball-tracking (whiff / zone-contact) | `_zbtrk` | `W_BTRK = 0.04` |
| park hitter's-eye (hand-set `PARK_TRK` dict) | `_zpark` | `W_PARKTRK = 0.03` |

Both halves are re-standardized before the 0.5/0.5 blend, so the edge bites as
hard as the market even when it's thin. There is no `MKT_EXP` exponent anymore.

ISO is **gone** — dropped from scoring and display (no predictive value,
~0.88-redundant with the power index). The old multiplicative lambdas (`powT`,
`zoneT`, `fF`, `parkT`, `pM`, `mktT`) and the `_mm` term are still computed in
`build15.py` but no longer feed TOTAL — vestigial. `powidx` still drives display
and notes.

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
- **`Pitcher` chip** = 0–100 hittability of the opposing arm (50 = neutral, higher = more HR-prone), derived from the same pitcher multiplier that scores the bat.
- **`POWER` / `Zone` / `Park`** chips = the respective inputs.

---

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
- **Chalk ban is removed.** `CHALK_N` is still defined but `chalk = set()`, so the
  top-4 favorites now draft into moons/salami/builders like any other bat. The
  lunch special and nightcap simply take the highest-model bat not already on a
  parlay in their time windows.
- **Anchors** — 4 total (3 moon anchors + 1 salami anchor), the strongest *fittable*
  bats by model `TOTAL`. **Multiple anchors from the same game are allowed** (two
  strong bats in one game can both anchor, each leading tickets whose legs come from
  *other* games); the `≤4/game` pool cap still bounds total game exposure. The 4 are
  chosen to maximize clean moons → salami → combined strength.
- **Moons** — **2 per anchor** across 3 anchors = up to **6** moons. Each = an
  anchor + 2 longshots in distinct games, leg span ≤ `WIN` (120 min). An anchor
  ships both its moons or none; on a thin slate the **weakest anchor** demotes
  rather than ship a lopsided board.
- **Salami** ("biggest") — led by the **best** anchor and **drafts inside the snake**
  with the moons (no premium first-pick). The draft snakes **weakest-anchor-first**,
  reverses each round, so the best anchor picks back-to-back at the turn. If the best
  anchor can't fill 4 legs in its window it's re-tasked to moons. Demotion candidate
  on a thin slate.
- **Builders** (our straight singles) — the **actual anchors**, **plus** the
  conviction **"snubs"**: strong bats that landed on **no** parlay at all (neither
  anchor nor a drafted leg) — typically bats stuck in time-isolated late games no moon
  window could reach. Concretely: the anchors **+ any unused pool bat at least as
  strong as the weakest bat actually used on a leg**, at ≤ +600. Bats already on a
  moon/salami aren't re-listed; sub-leg-strength dregs are dropped. Self-adjusts each
  slate to catch whoever falls through the cracks.
- **75 TOTAL floor** on parlay legs (anchors, partners, salami legs).

Key knobs: `Z_GATE=0.75` (pool gate), `GAME_CAP=4`, `WIN=120`, `NIGHT_WIN=60`,
`MOONS_PER_ANC=2` (`CHALK_N=4` defined but the ban is off; `FLOOR=130` is a dead
fallback). Edge weights: `W_BG=0.20`, `W_XPOW=0.18`, `W_ARS=0.16`, `W_XPTREND=0.12`,
`W_PVEL=0.10`, `W_SPRAY=0.09`, `W_PVDECL=0.08`, `W_BTRK=0.04`, `W_PARKTRK=0.03`
(market is a flat 0.5 of the blend). Parlay stakes: moon round-robin `risk=2.0u`,
salami round-robin `risk=5.5u` (singles/builders stake `1u`).

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
- **Top-4 per GAME holds everywhere** — the pool and the span-fill fallback, so a
  game can never put a 5th bat on the regular board (chalk in lunch/nightcap exempt).
- **Builders = anchors + conviction snubs** (unused bats ≥ the weakest drafted leg),
  emitted live from the drafted tickets, matching the server rule.
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
the only thing that writes its history. It was **reset to start on 2026-06-27**,
reflecting the current model graded over 6/27–6/28 only, and rolls forward from
6/29 like usual. Per-category units, win counts, and the history curve are baked
into the board as `D.meta.season`.

> **Reality check.** Backtesting on the calibration data shows the model does **not**
> out-predict the HR-prop market (AUC ≈ 0.58 vs the market's ≈ 0.61). Builder singles
> bleed and the salami round-robin is unproven; moons are roughly break-even and the
> most plausible — but not proven — place for an edge. Treat the board as a ranking/
> research tool, not a guaranteed-profit system.

---

## Notes

- The board is one static file — opening `index.html` is all you do. A build stamp
  (`build M/D h:mmam`) shows in the header next to the slate date so you can confirm
  a fresh load; it's the *build* time (in **US Eastern**), not the slate date. (The
  Action runs in UTC, so `build15.py` stamps ET as UTC−4 — fixed so an afternoon
  build no longer reads as a late-night time.)
- Display changes (Pitcher chip, Model chip, khr badge, builder rule, FLOOR) are
  applied as idempotent patches in `regen15.py`, so they survive every rebuild
  regardless of the template state.
