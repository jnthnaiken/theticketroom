# The Ticket Room

A daily MLB home-run–prop handicapping board. It scores every carded bat with
**our own multiplier stack** (power + zone + opposing pitcher + park + weather +
market + lineup slot + platoon), drafts the day's tickets (moons, salami
round-robin, builder singles, lunch/nightcap), and ships a single self-contained
`index.html` that updates itself live as lineups post and games finish.

There is **no base/projection score** — the model is purely the product of our
own signals (see Scoring). Kasper's `khr` projection is still shown on each card
as a display-only reference, but it does **not** feed the math.

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

Missing a given day's file falls back to the prior day's automatically.

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

There is **no base score.** `aT` is a flat `100` (a scale constant, identical for
every bat — it changes nothing about ranking), so `TOTAL` is purely the product of
our own signal multipliers:

```
TOTAL = 100                # flat scale constant (NO base / projection)
      × powT(powidx)       # power: pulled-barrel% × hard-hit% × launch window   (±25%)
      × zoneT(zone)        # zone / contact quality                              (±5%)
      × fF(form)           # recent form                                         (±6%)
      × phr9(pitcher)      # opposing SP allowed pull-barrel%/hard-hit%/fly-ball% (±25%)
      × parkT(home,hand)   # park HR factor, handedness-aware (deviation ×0.6)
      × pM(weather)        # wind / temp / dome                                  (±18%)
      × mktT(odds)         # market implied prob                                 (±22%)
      × slotT(order)       # lineup slot / PA volume                             (±8%)
      × platT(hand)        # platoon vs opposing SP                              (±8%)
```

Weights were re-tuned to the calibration data (market is the strongest single
predictor, so it carries the most; weather/park/form were trimmed toward a floor
because the market already prices them — but nothing is zeroed). `slot` and
`platoon` are unchanged pending more logged data.

The **pitcher term** uses the opposing starter's **allowed pulled-barrel% /
hard-hit% / fly-ball%** (the pitcher mirror of our batter power trio) for arms in
`pitchers_<date>.json` (`psrc='brl'`, clamped 0.75–1.25); for everyone else the
client applies the opposing-pitcher **HR/9** live (`psrc='hr9'`, ±15%).

ISO is **gone** — dropped from scoring and display (it added no predictive value
and was ~0.88-redundant with the power index).

The last several multipliers are baked into TOTAL server-side, so the client's live
re-draft inherits them via `baseTotal = TOTAL / (weather × pitcher)`. Batter
handedness comes from the lineups (`away_hands`/`home_hands`, one L/R/S per bat).

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
- **Pool gate** — the pool is **every eligible bat whose model `TOTAL` clears
  `FLOOR` (130)** — one pool for the whole draft. Re-sort by odds, **ban the 4
  shortest-odds** ("chalk") to the lunch/nightcap, and trim the rest to **at most 3
  per GAME** (best by model, both teams combined — per-team would allow 6/game).
  No fixed size, no backfill.
- **Chalk** (the 4 banned favorites) are eligible **only** in the lunch special and
  the nightcap, in their time windows. Never in moons, salami, or builders.
- **Anchors** — 4 total (3 moon anchors + 1 salami anchor), the strongest *fittable*
  bats by model `TOTAL`. **Multiple anchors from the same game are allowed** (two
  strong bats in one game can both anchor, each leading tickets whose legs come from
  *other* games); the `≤3/game` pool cap still bounds total game exposure. The 4 are
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

Key knobs: `CHALK_N=4`, `FLOOR=130` (pool gate), `GAME_CAP=3`, `WIN=120`,
`NIGHT_WIN=60`, `MOONS_PER_ANC=2`. Scoring weights: `W_MKT=0.18`/`MKT_CLAMP=0.22`,
power/pitcher `±0.25`, `W_WEATHER=0.18`, park deviation `×0.6`, form `0.002`,
`W_SLOT=W_PLAT=0.08`. Parlay stakes: moon round-robin `risk=2.0u`, salami
round-robin `risk=5.5u` (singles/builders stake `1u`).

---

## Live engine (index.html)

Every ~6 minutes the board: refreshes weather → recomputes each bat's `TOTAL` on
live HR/9 + weather → pulls posted lineups (confirm / scratch) and results
(HRs / finals) → re-drafts on the live numbers → grades.

Behavior that's load-bearing:

- **Lock = whole ticket confirmed.** A ticket locks only when *every* leg is in the
  posted lineup (or its game is underway) and none is scratched. A locked ticket is
  emitted verbatim and never moves; a scratched leg drops it out of "confirmed" and
  the re-draft replaces just that leg while confirmed legs stay pinned. A scratched
  single with no replacement is dropped, never re-shown.
- **Top-3 per GAME holds everywhere** — the pool and the span-fill fallback, so a
  game can never put a 4th bat on the regular board (chalk in lunch/nightcap exempt).
- **Builders = anchors + conviction snubs** (unused bats ≥ the weakest drafted leg),
  emitted live from the drafted tickets, matching the server rule.
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
