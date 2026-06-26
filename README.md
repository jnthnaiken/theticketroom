# The Ticket Room

A daily MLB home-run–prop handicapping board. It scores every carded bat with a
"Kasper" blend (matchup + power + form + park + opposing pitcher + weather),
drafts the day's tickets (parlays, round-robin, singles, lunch/nightcap), and
ships a single self-contained `index.html` that updates itself live as lineups
post and games finish.

---

## Daily workflow

Drop the day's input files in this folder (named with the slate date,
`YYYY-MM-DD`), then run the pipeline in order:

```
python grade_night.py        # 1. grade last night into season.json
python build15.py             # 2. score today's field  (SLATE_DATE env or today ET)
python regen15.py             # 3. assemble tickets + inject into index.html
```

To pin a specific slate (e.g. rebuilding after midnight so the date can't drift):

```
SLATE_DATE=2026-06-23 python build15.py && python regen15.py
```

Then open `index.html`. It runs live on its own from there — no server needed.

---

## Inputs (per slate date)

| File | What it holds |
|---|---|
| `cards_<date>.json` | Kasper matchup cards (zone, form, barrels, hard-hit, launch, etc.) |
| `lineups_<date>.json` | projected lineups + schedule (times, starters, park, weather, batter hands) |
| `odds_<date>.json` | consensus HR odds, `{name: american}` |
| `iso_<date>.json` | ISO sheet, `{name: iso}` |
| `pitchers_<date>.json` | top-pitcher barrel data `{name:{brl, pbrl}}` — optional |
| `hr9_<date>.json` | opposing-pitcher HR/9 — legacy/optional |

Missing a given day's file falls back to the prior day's automatically.

`build15` also pulls **live weather (Open-Meteo) and opposing-pitcher HR/9 (StatsAPI)**
at build time and bakes them into TOTAL, so the shipped board matches the browser's
live re-draft. Both fetches fail gracefully — no network just falls back to the
lineup's wind/temp and a neutral pitcher term, exactly as before.

## Outputs

| File | What it is |
|---|---|
| `D_<date>.json` | the scored + assembled board data for that slate |
| `index.html` | the live board (self-contained; the only thing you open) |
| `season.json` | the running ledger (history, per-category units, graded nights) |

---

## Scripts

- **`grade_night.py`** — auto-grader. Reads `season.json`, finds the last graded
  night, and folds every fully-final night since then into the ledger off real
  play-by-play home runs. Postponed games void (refund). Never grades a night
  that isn't final yet, never double-grades. Keeps the tracker current *before*
  the new slate builds.
- **`build15.py`** — the scorer. Turns the carded field into a `TOTAL` per bat.
- **`regen15.py`** — assembles the tickets (via `assemble_tickets.py`) and
  injects `const D = …` into `index.html`.
- **`assemble_tickets.py`** — the ticket rules engine (pool gate, chalk routing,
  moons/salami/builders, lunch/nightcap, pricing).
- **`calibrate.py`** — nightly per-bat outcome logger → `calibration.jsonl`. The
  dataset for eventually *fitting* the weights instead of hand-tuning them.
- **`cardnotes.py`** — card-note helper. `build15_legacy.py` — old scorer kept as
  an ISO fallback.

---

## Scoring (build15)

```
TOTAL = aT
      × powT(powidx)     # power index            (±18%)
      × isoT(iso)        # isolated power          (±12%)
      × zoneT(zone)      # zone/contact
      × fF(form)         # recent form     (clamp 0.92–1.08)
      × pitcher-term     # barrel-against (listed arms) OR live HR/9
      × parkT(home,hand) # park HR factor, handedness-aware (pull-side tilt)
      × pM(weather)      # wind/temp/dome
      × mktT(odds)       # market implied prob     (±14%) — independent info, not just drafting
      × slotT(order)     # lineup slot / PA volume (±8%, top of order up)
      × platT(hand)      # platoon vs opposing SP  (same −8% / opposite +5.6% / switch +2.4%)
```

The last three multipliers are baked into TOTAL server-side, so the client's live
re-draft inherits them automatically via `baseTotal = TOTAL / (weather × pitcher)`.
Batter handedness comes from the lineups (`away_hands`/`home_hands`, one L/R/S per bat).

The pitcher term uses **barrel-against** (`Brl/BIP%` + `PulledBrl%`) for arms
listed in `pitchers_<date>.json` (`psrc='brl'`); for everyone else the client
applies the opposing-pitcher **HR/9** live (`psrc='hr9'`).

---

## Ticket rules

- **Eligible field** = priced bats in the posted lineup, not scratched/voided,
  under 70% rain.
- **Rain bands** — `<40%` full eligibility (can anchor); **`40–49%` barred from
  anchoring** but still usable as a parlay leg or builder; `50–69%` builders only
  (no parlay legs at all); `70%+` out of the pool entirely.
- **Pool gate** — the pool is **every eligible bat whose model `TOTAL` clears
  `FLOOR` (85)** — one pool for the whole draft. Re-sort it by odds, **ban the 4
  shortest-odds** ("chalk") to the lunch/nightcap, and trim the rest to **at most 3
  per team** (best by model). No fixed size and no backfill: a thin slate just makes
  a smaller board.
- **Chalk** (the 4 banned favorites) are eligible **only** in the lunch special
  and the nightcap, in their time windows. Never in moons, salami, or builders.
- **Moons** — **2 per anchor** across 3 anchors = up to **6** moons. Each = an
  anchor + 2 longshots in distinct games, leg span ≤ `WIN` (120 min). An anchor
  ships **both** its moons or **none**: if the slate is too thin to fill them, the
  **weakest anchor** (moon *or* salami) and its stranded legs demote to builders
  rather than ship a lopsided 2/2/1.
- **Salami** ("biggest") — the 4th anchor leads four longest shots, full
  round-robin. It's a demotion candidate too — if it's the weakest anchor on a
  thin slate, it drops and its legs free up for the moons.
- **Builders** — every remaining pool bat as a single.
- **75 TOTAL floor** on our parlay picks (anchors, partners, salami legs).

Key knobs: `CHALK_N=4`, `FLOOR=85` (pool gate), `WIN=120`, `NIGHT_WIN=60`,
`TEAM_CAP=3`, `MOONS_PER_ANC=2`. Parlay stakes: moon round-robin `risk=2.0u`,
salami round-robin `risk=5.5u` (singles/builders stake `1u`).

---

## Live engine (index.html)

Every ~6 minutes the board: refreshes weather → recomputes each bat's `TOTAL` on
live HR/9 + weather → pulls posted lineups (confirm / scratch) and results
(HRs / finals) → re-drafts on the live numbers → grades.

Behavior that's load-bearing:

- **Lock = whole ticket confirmed.** A ticket locks only when *every* leg is in
  the posted lineup (or its game is underway) and none is scratched — builders
  and parlays alike. A locked ticket is emitted verbatim and never moves. A leg
  that scratches drops the ticket out of "confirmed," and the re-draft replaces
  just that leg while the confirmed legs stay pinned. So a confirmed slip never
  moves, and no board ever shows a scratched leg.
- **Top-3 per team holds everywhere.** The 3-per-team cap applies to the pool
  *and* the #42+ span-fill fallback that fills short parlays, so a team can never
  put a 4th bat on the regular board. (Chalk in the lunch/nightcap is exempt —
  a favorite there can sit on top of a team's 3.)
- **Badges** read one way: 🔒 *confirmed* (locked) · `N/M confirmed` (partial) ·
  *projected*. A full count always shows the lock.
- **No midnight rollover.** Once the calendar passes the slate date, the whole
  slate counts as played: the board freezes on that day, keeps its locked/graded
  tickets, and does **not** roll forward or reset to projected. It stays on that
  slate until you build the next one.

---

## Notes

- The board is one static file — opening `index.html` is all the user does. A
  build stamp (`build M/D h:mmam`) shows in the header next to the slate date so
  you can confirm a fresh load; it's the *build* time, not the slate date.
- `season.json` is the source of truth for the ledger; `grade_night.py` is the
  only thing that should write to its history.
