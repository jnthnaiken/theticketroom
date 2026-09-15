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

On GitHub the Action `pull-slate.yml` runs the whole pipeline and commits the rebuilt
`index.html`. The real order is **grade → calibrate-backfill → fetch_mlb → fetch_odds →
build15 → savant_gate → regen15**. Two of those are easy to miss: `fetch_odds.py --auto`
refreshes prices on **every** build (so the hand-committed odds file is only a morning seed),
and **`savant_gate.py` can discard the board outright** if the Savant pull came back thin —
see HANDOFF for `MIN_BASE`. Then open
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
optional (though `pitchers` is now built every slate for all ~30 starters).** `cards`/`extras`/`pitchers` come from the Kasper matchup pages and `lineups` from
RotoWire; both are **manual inputs you commit**. `odds` is a **seed, not the source of
record** — `fetch_odds.py --auto` runs before `build15.py` on every build and merges fresh
VegasInsider prices in (it never replaces the file wholesale), so hand-scraping prices
mid-afternoon just gets overwritten five minutes later. `fetch_mlb.py` (in the Action) does **not** generate `lineups_<date>.json`;
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
(e.g. you hardcode `gn:1` everywhere) they collapse into one game and the `GAME_CAP`
per-game pool cap (6) throttles the WHOLE board to that many bats/tickets. Number the games
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
- **`regen15.py`** — assembles the tickets by **running the client engine server-side**
  (`node client_assemble.js <D.json> index.html`, so the archive is drafted by the same code the
  browser runs) and injects
  `const D = …` into `index.html`. A **same-slate rebuild ALWAYS preserves the prior
  draft** (carries `prevD['tickets']` forward untouched — the live client handles
  confirm / scratch / refill), so a live, confirmed board is never re-drafted out from
  under a placed bet. It also applies one idempotent client patch: the **doubleheader
  ET time-match fix** (strips the `" ET"` suffix so a DH's in-progress game is graded
  live — see the 2026-07-11 note in `HANDOFF.md`). *(An older version used a
  `RULES_VERSION` lever to force a re-draft; it was removed after force-re-drafting a
  confirmed 07-09 board and swapping a bet leg.)*
- **`assemble_tickets.py`** — ⚠️ **NOT the rules engine and not a mirror of one.** It runs only
  when `client_assemble.js` is missing or node exits non-zero. Audited 2026-08-16 and it is two
  board redesigns behind:
  - **no Dingers and no chef** — both retired, neither reachable here either;
  - **no Grand Salami** as of `NOSALAMI-2026-09-13`. It built one until then, which was a real
    divergence: the live engine dropped the salami on 2026-08-14, this file kept minting them,
    and `regen15.py` reaches for this file whenever Node or the client engine is unavailable —
    so the rare fallback published a kind the board had retired a month earlier. All four
    anchors now lead moons here exactly as they do in `index.html`, and a smoke run against
    `D_2026-09-13.json` returns the identical shape: 8 four-leg moons, 4 builders, lunch,
    nightcap;
  - **no prior-board lock of any kind** — `_now_min_et` / `_locked_prior` / `_locked_bats` /
    `_keep_fresh` are all absent. (It *does* still carry `chalk = set()`, line 174 — that is
    deliberate, and it is the divergence `CHALKUNBAN-2026-09-04` closed by taking the live
    `CHALK_N` to 0.)

  So a fallback does not ship "the same board with weaker semantics". It ships a board with the
  Dingers missing, a retired salami restored, and every ticket re-drafted from scratch
  including ones whose games are underway — and `grade_night.py` books it, into a `biggest`
  category the tracker no longer displays. `regen15.py` prints one warning to the Action log and
  commits anyway. **Do not mirror engine rules into it; treat a fallback as a failed build.**
- **`calibrate.py`** — per-bat outcome logger → `calibration.jsonl`. Logs every
  model input (power, zone, form, pitcher term, park, weather, **slot, platoon,
  market**), the full Kasper `k_*` extras, opposing-pitcher `p_*` allowed contact,
  and did-he-homer. Self-healing idempotent `backfill()` runs every build.
- **`cardnotes.py`** — per-card prose write-ups.

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
weighted sum of exactly **seven** z-scored signals. This is the live `_SIG` list in
`build15.py` **as of `ISOREAL-2026-09-13`** — read it off the source, not off this
table, if the two ever disagree again:

| signal | key | weight |
|---|---|---|
| **career HR per game** (StatsAPI, `cg >= MIN_CAREER_G` = 30) | `_zhrc` | `0.4489` |
| hard-hit rate (Kasper `HH%`) | `_zhh` | `0.2086` |
| launch angle via the `la_window` bell, `exp(-((la-25)/14)^2)` (Kasper `LA`) | `_zla` | `0.1313` |
| **playing time** — games played this season (StatsAPI) | `_zpt` | `0.1051` |
| opposing starter's SwStr%, **negated** (higher = more hittable), platoon split | `_zpsw` | `0.0664` |
| **actual-vs-expected damage** — Kasper `ISO` ÷ `xwOBAcon` | `_zdmg` | `0.0309` |
| pitch-arsenal matchup (batter RV/100 × pitcher pitch mix, raw) | `_zars` | `0.0088` |

Weights sum to **exactly 1.0000** and every one fitted **positive**.

**All seven were fitted together** (`CAREERHR-2026-09-13`, refitted `ISOREAL-2026-09-13`)
on the 2015-2024 Statcast table **in this basket's own feature space** — the exact columns
this loop scores with, per-slate z, grouped-CV by slate, 315,937 usable rows / 11.80% HR /
1,839 slates. So they transpose directly instead of being scaled by eye off a different
feature set, which is what every earlier refit did. Lab 15 runs `34762337729` (career terms)
and `34772500739` (real-ISO refit).

**`_zhrc` is the story.** Career HR rate takes **45% of the basket on its own**, ahead of
`_zhh` — who hits home runs beats how the ball comes off the bat — and it needs no Kasper,
no Savant and no odds. Adding `_zhrc` + `_zpt` took the basket from AUC **0.5893 → 0.6225**,
the largest single gain on record for this board. `_zdmg` and `_zla` fall hard (0.2818 →
0.0309 and 0.2834 → 0.1313) because career rate absorbs most of what they were carrying.

`_zhh` / `_zla` / `_zars` carried their **2026-08-13 fitted values** until this refit
(3-signal AUC 0.5773 → 5-signal 0.5962; repro `fit_savant.py`, Savant Fit run
`31731827046`). `HH%` and `LA` were display-only chips until that refit and turned out to
be the two strongest predictors in the table — which held right up until career rate was
tested against them.

⚠️ **`_zhrc` and `_zpt` are 55.4% of the basket and they can go dark silently.**
`fetch_career` fails soft by design, and a `None` signal scores at the slate mean, so a dead
pull costs the basket weight and throws nothing. That is exactly what happened on
2026-09-13: `CAREER` was keyed by StatsAPI's **int** `id` while every id in `build15.py`
comes from Savant's `player_id` column as a **string**, so the lookup missed on all 419 bats
and the other five terms silently renormalised to ~`.02/.47/.29/.07/.15` (`CAREERKEY-2026-09-13`).
The build now prints `(career: N/M batters carry career HR rate)` every run and shouts if
`N == 0`. **If that line reads 0, the board is not running this basket.**

**`_zdmg` (`DMGRATIO-2026-08-23`) — owner's call, and it OVERRODE a measurement.**
*(Weight since cut to `0.0309` by the fit above; the reasoning below is why the term exists
at all, and still stands.)*
`_zxwcon` (xwOBAcon) and `_zxpow` (park-neutral xISO) came **out** of the basket and
were replaced by the single ratio `_zdmg = ISO / xwOBAcon`, which inherits their
combined weight plus `_ziso`'s: `0.0245 + 0.1633 + 0.0940 = 0.2818`. Rationale: this
is the read Kasper actually makes — hard-hit and launch angle first, then
actual-vs-expected damage — and carrying the two *levels* **and** the *comparison*
double-counts the same two columns.

⚠️ **Do not "fix" this back on the strength of `claude/kasper-screen-2026-08-23.md`.**
That document measures the ratio at standalone AUC **0.5749** against **0.5948** (ISO)
and **0.5963** (xwOBAcon), and concludes the pair beats the ratio in a fitted basket
(0.6002 vs 0.5967). It is right, and it was overruled deliberately. The cost is on the
record too, from the `_SIG` comment itself — 23 nights / 5,454 bats / 563 HR: blend AUC
**0.6176 → 0.6150**, top-30 hit rate **18.99% → 18.55%**, top-30 ROI **−17.6% → −19.6%**.
All of it sits inside noise at 563 HR, and none of it tests the proposition the owner
actually holds, which is that the market half is contaminated by public money and so
ROI-against-price is the wrong scoreboard. **Revert** = restore
`('_zxpow',0.0245),('_zxwcon',0.1633),('_ziso',0.0940)` and drop `_zdmg`.

**Sample guard.** `_zdmg` requires `xwOBAcon > 0.05` **and** `bip >= MIN_DMG_BIP` (40
batted balls); `ISO` outside `0.02–0.60` is rejected as a scrape artifact. A bat that
fails any guard gets `None` and therefore scores at the **slate mean** — the same safe
fallback an unmatched bat gets, so it is not pushed down. Unguarded on 08-21 the top of
this signal was Will Banfield at 1.392 off **five** batted balls. The ratio form (not
the subtraction) is used because xwOBAcon exceeds ISO for 99.56% of bats, so the
quotient is well-behaved in (0,1] — and it measures better than the gap, 0.5749 vs 0.5170.

⚠️ **`_zpsw` is the one UNFITTED weight in `_SIG`** (`PSWSTR-2026-08-23`). It could not
be fitted: pitcher SwStr% exists on 3 archived nights (08-02…04, 410 rows / 48 HR) and
Savant is unreachable from the sandbox. `0.06` was set by **blast radius** — ~1.7 of the
top 30 and ~0.7 of the top 8 change per night, max rank shift ~10. It degrades exactly:
if no arm on the slate carries SwStr%, every bat is `None`, the edge sum is uniformly
scaled by `(1-W)`, and standardization makes that a no-op to 4.4e-16 — a stale scrape
reverts to the previous board rather than corrupting it. Revisit once ~3 weeks of slates
carry `p_swstr` in `calibration.jsonl`.

⚠️ **The nine-signal edge basket described in older revisions is DEAD.** `_zbg`
(bullpen game), `_zxptr` (power trend), `_zpvel` (perceived velo), `_zspray`,
`_zpvd` (velo decline), `_zbtrk` (ball-tracking), `_zpark` (park eye) are all still
**computed and logged** but are **not** in `_SIG`, so none of them touch `TOTAL`
(and `W_BTRK`, `W_PVDECL`, `W_XPTREND` are hard-set to `0.0`). **Since
`DMGRATIO-2026-08-23`, `_zxwcon`, `_zxpow` and `_ziso` are on that list too** — computed
and logged every build so a refit can put them back without a re-scrape, but **not
scored**. Only the five in the table above feed the score.

Both halves are re-standardized before the 0.5/0.5 blend, so the edge bites as
hard as the market even when it's thin. There is no `MKT_EXP` exponent anymore.

ISO is back in the math, but only as the **numerator of `_zdmg`** — it has not been a
standalone signal since `DMGRATIO-2026-08-23`, and `iso_<date>.json` is still dead
(the live value comes off the Kasper sidecar, `ISOSRC-2026-08-23`). Gone for good is
the **power index** as a scoring input:
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
before re-drafting, so the draft reacts to weather as Open-Meteo updates. The pool **gate is on
`TOTAL`, weather included** (`index.html`, 2026-08-18): weather moves pool membership too.
It used to sit on the weather-free `blend` on the argument that weather should only reorder
— that was abandoned when Freddie Freeman missed the pool at Coors on a boost night. Opposing-pitcher HR/9 remains a display chip only.

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
  under 70% rain, **and at least `MIN_CARD_BIP` (40) batted balls on the Kasper card**.
- **Thin bats are never drafted (`THINBAT-2026-09-15`).** `build15.py` stamps `thin: true` on any
  bat whose card `test` (batted-ball count) is under `MIN_CARD_BIP`. `CARDBIP-2026-09-12` only
  neutralised such a bat's card rates, so he still scored on price/park/slot and could top the
  slate — Josue De Paula (1 BIP) anchored the board on 09-12 and again on 09-15. The engine now
  refuses a thin bat everywhere it drafts: the eligible field (so the gated pool, reserve tier and
  nightcap), the shape-repair candidates, the prior-leg keep, `anchorAlive` and both moon-refill
  passes. An **open** moon anchored by a thin bat triggers the full joint redraft. **Locked**
  slips are placed bets and are still carried verbatim. Thin bats still show on the Players tab.
  `regen15.py` prints a `::error::THINBAT` annotation if a built board still carries one (e.g.
  the `assemble_tickets.py` fallback, which knows nothing about the rule).
- **Rain bands** — `<40%` full eligibility (can anchor); **`40–49%` barred from
  anchoring** but still usable as a parlay leg or builder single; `50–69%` builder
  single only (no parlay legs); `70%+` out of the pool entirely.
- **Pool gate** — z-THRESHOLD on **`TOTAL`** (weather included): keep every eligible bat whose
  `TOTAL` z-score is **`>= Z_GATE` SDs above the slate mean**. Both drafters now read that from
  `board_config.json`; neither keeps a copy. Scale/slate-independent — survives any weight change.
  Then trim to **at most `GAME_CAP` per GAME** (best by model, both teams combined).
  No fixed size, no backfill. (`FLOOR` and `GATE_N` are **dead constants** — declared and read
  nowhere, which is why they are deliberately kept out of the config file. `Z_GATE` is the only
  gate.)
  The per-game cap
  (raised from 3 on 2026-07-04) adds z-gate-passing depth so a scratched parlay leg can
  refill *in-gate* instead of starving the slip; one bat/game per **ticket** still holds,
  so no single ticket over-concentrates on one game.
  **Rolling this back was tested and rejected (2026-08-14.)** Cold-drafted on 08-13:
  3-per-GAME gives pool 23 and **9 tickets** (down from 12) — it costs two moons and a
  builder — while leaving the undrafted count essentially flat (26 → 24). A literal
  3-per-TEAM cap (≤6/game, looser than today) gives pool 32 and 25. The cap moves both ends
  of the board together: tighten the pool and the tickets cannot reach as deep, so the floor
  rises with the ceiling. That test was run at 3-vs-4; the cap was subsequently **raised to 6**
  (owner, 2026-08-18).

  ⚠️ **That raise is the cautionary tale this config file exists for.** Only `index.html` got it.
  `assemble_tickets.py` kept a literal `4` under a comment saying it mirrored the engine, and
  `index.html` carried a *second*, bare `6` under a comment reading *"these two must agree or the
  pool and the gate disagree about who is in"* — an invariant enforced by a sentence. The cap binds
  on **25 of the last 25 boards**, so the two drafters gated different pools every night for 26
  days and nothing was ever red. All three sites read `board_config.json` now.

  The reserve-tier fill is a **separate, tighter cap** — `RESERVE_GAME_CAP`, also a bare `4` until
  BOARDCFG. It is not a stale `GAME_CAP`: it bounds how many bats one game may contribute when a
  moon has to reach *below* the z-gate, and being tighter than `GAME_CAP` is the point.
- **Chalk and the Chef's Table — both OFF, and the code is inert.**
  `CHALK_N = 0` since `CHALKUNBAN-2026-09-04` and `CHEF_TICKET = false` since 2026-08-14.
  With `CHALK_N` at zero the fill loop never iterates, so `chalk` is provably always `{}` and
  every `!chalk[n]` test on the board is a no-op: **nothing is reserved and nothing is barred.**
  Roughly 250 lines in `index.html` still describe the ban (price key, one-per-game, `CHEF_HYST`
  hysteresis, `CHALKOFF`/`CHALKLOCK`/`LOCKEVICT`, the localStorage eviction latch) and none of it
  can fire. The Chef's Table adds ~115 more; `CHEF_TICKET` is a `var` inside a closure, so it is
  not reachable from `window` and there is no way to switch it back on at runtime.
  ⚠️ **Two things inside that dead region are load-bearing — do not delete the block wholesale:**
  `nonchalk` (misleading name) is the draft pool itself, and `HYST_TOTAL` sits between two dead
  chef IIFEs while being read by the live **anchor-overtake deadband**.
  Lunch special and nightcap take the highest-model bat not already on a parlay in their time
  windows, `<= +600` — that part is live, and it never depended on chalk.

- **Dingers / Family Meal — RETIRED 2026-08-25, and unreachable.** `DINGERS = false`; the whole
  mint block returns on its first statement. It ran 11-80 for **−33.34u** and was backed out of
  the ledger, so there is no `family` row in `season.json` and no Dingers row in the tracker.
  ⚠️ `FAM_CAP = 8` is **not a knob** — it is declared *inside* the block, after the early return,
  so changing it does nothing. Only the render path survives, for archived boards that carry one.

- **Anchors** — 4 total, and since 2026-08-14 **all four lead moons** (8 moons a night); no seat
  is reserved any more, the salami having been removed. The strongest *fittable*
  bats by model `TOTAL`. **UP TO `ANCH_PER_GAME` (2) ANCHORS PER GAME** (2026-08-13, owner decision;
  this replaced the one-per-game rule added 2026-08-10 after Olson *and* Baldwin both anchored in
  NYM@ATL). Two strong bats in one game may each lead their own pair of moons — no ticket may still
  carry two bats from one game (`fits()`), so each slip is one anchor's worth of exposure, and
  `GAME_CAP` still bounds pool bats per game. **The candidate list is built in ROUNDS** — every game's
  best bat first, then every game's second — because a flat top-20 by strength fills up with *pairs*
  from time-isolated games, every 4-set then starves, and the board collapses (14 → 8 with 2 moons when
  this was first tried). The 4 are chosen to maximize clean moons, then combined strength, subject
  to `MOON_SLACK`. (The salami tiebreak that used to sit between those two went with the salami.)
- **Moons** — **2 per anchor across all 4 anchors = 8 moons.** Each is an anchor + **3** partners
  (`MOON_LEGS`, `MOON4-2026-09-13`) in `MOON_LEGS` distinct games, leg span ≤ `WIN`,
  staked as an 11-bet round robin at 0.25u = **2.75u** (see *Round robins* below). An anchor ships
  both its moons or none; on a thin slate the weakest anchor demotes rather than ship a lopsided
  board, and both repair passes break rather than emit a short moon.
- **Salami ("biggest") — REMOVED 2026-08-14. Deleted, not gated.** It was the worst line on the
  ledger: **−100.2u on 192.5 staked (−52.1%) over 35 real slips**, all of which were unwound from
  `season.json` by re-grading the archived boards. Nothing reserves an anchor for it any more.
  Two things are worth keeping from the removal, because a partial attempt failed once:
  **(1)** it had **four** construction paths, and the one that hides is the **client-side
  SALVAGE/REBUILD pass**, which rebuilt the slip from leftovers even when the draft never made one.
  **(2)** flag-gating only the build is the worst of both worlds — `sidx` went on reserving the
  weakest anchor for a ticket that was then thrown away.
  `assemble_tickets.py`, the fallback drafter, kept minting salamis until `NOSALAMI-2026-09-13`.
  **Kept deliberately:** everything that renders or grades an *existing* salami, so archived boards
  still show and settle what they shipped. Only new ones are impossible.

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

### Key knobs — `board_config.json`

**They are not listed here, on purpose.** Run `python3 boardcfg.py` to print them, or
`python3 state.py --check` to confirm the code and the last shipped board agree with them.

This paragraph used to spell out eleven values. `WIN=120` survived in it for a full day after the
window moved to 150, and `GAME_CAP` was quoted as 6 while the fallback drafter ran on 4 for
26 days. A number written into prose is a copy, and every copy in this repo has eventually gone
stale. `board_config.json` is the only place these exist now: `build15.py` stamps it into
`D.meta.cfg`, `index.html` reads it from there, `assemble_tickets.py` imports it, and
`state.py --check` fails the build if any of them drift apart.

`LUNCH_CUT_MIN` (minutes past local midnight) splits lunch from night; it was widened on
2026-08-13, because a 4:05 PM game is a matinee, and the old cut left a 150.7 bat in a
time-isolated 4:05 game with nowhere legal to go, missing lunch by five minutes. `CHEF_HYST=0.02` and `ANCH_HYST=0.02` are hysteresis deadbands that
live in `index.html` and are not board shape, so they are not in the config.
`CHALK_N=0` — the chalk reservation is **off**: it used to bar the four
**shortest-priced** bats (2026-08-20; `strength` before that) from every ticket, and since
2026-08-14 they were no longer bundled into a Chef's Table round robin (`CHEF_TICKET=false`)
either. With `CHALK_N=0` the fill loop never runs and no Chef's Table is built, so every
round robin on the board is a moon of `MOON_LEGS` legs (`MOON4-2026-09-13`).
`assemble_tickets.py` never built one (and no longer carries the `chalk=set()` line older revisions quote). `FLOOR` is a dead fallback on both sides, and unused
under `Z_GATE`. `strength()` = **normalized `TOTAL` alone, no market term** (2026-08-08 — `TOTAL`
already carries the market via `mktT`, so an odds weight double-counts).
**Edge weights: code and docs agree** (re-verified against `main` on 2026-09-13).
`build15.py` `_SIG` is
`_zhrc 0.4489 / _zhh 0.2086 / _zla 0.1313 / _zpt 0.1051 / _zpsw 0.0664 / _zdmg 0.0309 / _zars 0.0088`
— seven terms, sums to exactly 1.0000. See the Scoring section above for how the career
terms were fitted and why `_zdmg` fell so far. ⚠️ **This README has now been stale twice.**
It carried the pre-`DMGRATIO` five-signal basket (`_zxpow .029 / _zxwcon .193 / _zars .011 /
_zhh .432 / _zla .335`) for a day after the code moved — corrected 2026-08-24 — and then
carried the `DMGRATIO` five-signal basket for the whole of `CAREERHR` and `ISOREAL`,
corrected 2026-09-13. The lesson is written up in
`claude/wrongbasket-correction-2026-09-13.md`: **read `_SIG` out of the running source, never
off this table.** The 08-13 refit itself resolved an
older three-way split: `.45/.35/.20` was live in the source, an
`xISO .13 / xwOBAcon .50 / arsenal .37` refit was documented here but **never applied**,
and `.346/.288/.366` lived only in `backtest_*.py`. `W_ARS=0.10` is a display term, unrelated. Market is a flat 0.5 of
the blend (`blend = 0.5*mz + 0.5*ez`), which is current. Parlay stakes: a moon is an 11-bet round robin at 0.25u
a bet = **2.75u** (derived, never hard-coded — see *Round robins* below); singles and builders
stake `1u`. The 5.5u salami/chef stake survives only on archived tickets.

### Round robins (`RRUNIT-2026-09-13`)

**A round robin buys every combination from doubles up to the full parlay** — `2^L - L - 1`
bets. 3 legs → 4, **4 legs → 11**, 5 legs → 26.

**The owner sets the per-BET unit, not the ticket total.** `risk` is derived:

```
RR_UNIT = {2: 2.00, 3: 0.50, 4: 0.25, 5: 0.10}      risk = combos(L) x RR_UNIT[L]
  3 legs ->  4 bets x 0.50u = 2.00u
  4 legs -> 11 bets x 0.25u = 2.75u      <- every moon on the board
  5 legs -> 26 bets x 0.10u = 2.60u
```

Since 3 legs derives to exactly the 2.0u moons were hard-coded to, **no archived night
re-grades differently** — and archived tickets carry their own recorded `risk` anyway, so the
59 four-leg Chef's Tables in the archive keep their 5.5u.

One definition, five implementations kept in lockstep: `rrCombos/rrUnit/rrRisk/rrStruct` in
`index.html`, `rr_combos/rr_unit/rr_risk/rr_struct` in `assemble_tickets.py`, `sizes` in
`grade_night.py` and `soccer/soccer_grade.py`, and `combos()/UNIT` in `daily15.py`/`sim15.py`.
`struct` and `risk` are **derived from the legs a ticket actually shipped with**, in ONE place
per drafter, after every draft and repair pass has finished — so a repaired or short-filled
slip can never carry a stake belonging to a different leg count.

Two bugs closed in the same pass. Every enumeration **stopped at four**, so a five-leg slip
was split across 25 bets instead of 26 and its own five-fold paid nothing. And `RRSTAKE-2026-08-28`
had never reached `assemble_tickets.py`: its `_rrmax` still priced 1u on every combination,
roughly doubling every max-profit figure that drafter printed.

---

## Live engine (index.html)

Every ~6 minutes the board: **re-fetches `D_<date>.json` and adopts it if the build stamp
moved** → refreshes weather + opposing-pitcher HR/9 → updates the weather/pitcher **chips** and
**re-scores each bat's `TOTAL` from `baseTotal · wxMult(live wf)`** (the weather-free `baseTotal`
and `wxMult` are baked/mirrored server+client, so the client re-score matches the server bake) →
pulls posted lineups (confirm / scratch) and results (HRs / finals) → re-drafts on the re-scored
numbers → grades.

Behavior that's load-bearing:

- 🛑 **The board adopts newer server builds** (`ADOPT-2026-08-16`). Until this shipped, `index.html`
  baked the board in as `const D={…}` and **never re-fetched it** — the live loop refreshed weather,
  lineups and results against a load-time copy forever. A tab left open kept drafting a ticket set
  the server had thrown away while the incoming live data made it look current *and marked its legs
  confirmed*. On 2026-08-15 a tab on the 4:34pm board showed `All Day` (Bobby Witt) as fully
  confirmed at ~6:42pm; the server had swapped him for Gary Sánchez at 4:39pm and graded that. Same
  root cause as a desktop and a phone disagreeing on the season total. Adoption replaces players /
  pool / tickets / familyFloor / meta and re-applies locally derived state (hr flags, `finals`,
  `gs`, `live`) on top, then nulls `CACHE`. It is **silent** by owner's call — safe because
  `CONFLOCK` freezes anything confirmed, so an adoption can only move what is not yet bettable.
  Fails soft: no network, or a downloaded shareable copy of the page, keeps the baked board.
- **A slip is never created after its own first pitch** (`MINTGUARD-2026-08-16`). The lock rule
  froze slips that already existed; nothing stopped the drafter minting a new one whose lock had
  passed — a bet nobody could have placed, which `grade_night.py` then books. Moons die as a pair,
  so a late moon takes its anchor's whole run with it. No prior board → no-op.

- **Lock = whole ticket confirmed.** A ticket locks when *every* leg is in the posted lineup and
  none is scratched, **or** when its earliest leg's game is underway — whichever comes first
  (`CONFLOCK-2026-08-16`). Until that change the freeze read the clock alone, so a bat confirmed
  at 4pm for a 9:38 game stayed re-draftable for five and a half hours; 🔒 on the board now means
  🔒 in the draft. A locked ticket is
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
- **The per-game cap is 6 in the pool, 4 in the span-fill fallback.** They disagree by design
  now rather than by accident; don't "fix" one to match the other without re-testing depth.
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
- ~~**Salami is leftover — built (or rebuilt) client-side.**~~ ⚠️ **DELETED 2026-08-14.** It was
  the least obvious of the four build sites: removing the two draft sites alone leaves this one
  rebuilding the slip from leftovers. Recorded here so nobody re-adds a partial removal.
  It used to run *last*,
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
- **The saved-board snapshot only comes back once the slate is final** (`ODDSHOLD-2026-08-15`).
  The live loop writes `localStorage['hr_ticket_odds']` on every refresh — HR flags, `finals`, and
  the whole price table — and `loadOdds()` re-applied all of it over the fresh board on the next
  page load, which the loop then re-saved. Self-perpetuating: a tab opened on the 9:31am build held
  9:31am prices until the next morning's date change. On 2026-08-15 that put one cashed single at
  +388 on a desktop and +529 on a phone, 1.4u apart, off the same ticket. Now **nothing is restored
  until every game on the slate is final** — while games are live a load uses the fresh bake alone;
  once the slate completes the hold carries the settled board across refreshes until the next
  morning. Completeness is judged on the union of the baked `meta.finals` and the snapshot's own,
  because the Action freezes a fully-final slate and may never bake the last game in. The slate-date
  check now gates the price restore too (it previously guarded only the results, so a stale blob
  with a colliding `sig` could reprice a different slate). ⚠️ There is **no exemption for
  hand-entered odds** — the admin bulk-paste box does not survive a mid-slate reload, by owner's
  instruction ("i will never hand write the odds").
- **Badges** read one way: 🔒 *confirmed* · `N/M confirmed` (partial) · *projected*.
- **No midnight rollover.** Once the calendar passes the slate date, the board
  freezes on that day with its locked/graded tickets and does not reset to projected.

---

## Ledger (season.json)

`season.json` is the source of truth for the running tracker; `grade_night.py` is the only
thing that writes its history. Current epoch is **since 2026-06-30**, rolling forward each
morning as the prior night settles.

**Through 2026-09-12: +444.89u on 1,265.0u staked — 819 graded, 145 won (17.7%), +35.2% ROI.**

**Four categories**, in board order (these are also the `defs` rows in the tracker):

| | record | units | staked |
|---|---|---|---|
| 🍱 Lunch | 9–41 | −4.34 | 50 |
| 🌃 Nightcap | 15–50 | +3.55 | 65 |
| ⚓️ Anchors | 63–195 | −14.05 | 258 |
| 🚀 Moonshots | 58–388 | +459.73 | 892.0 |

`history` holds 70 points; `graded_nights` holds 98, because it is the full dedupe log back to
06-01, not the ledger window. Numbers above are read straight out of `season.json` — **regenerate
them rather than hand-editing this table**, which is how it came to be four weeks stale.

Three categories have been **backed out** of the ledger, each by re-grading the archived boards
with `grade_night.grade_ticket` rather than subtracting a category total:

| category | record | removed | when |
|---|---|---|---|
| `chef` (Chef's Table) | 2–11, −49.72u on 71.5 | 2026-08-14 | never returned |
| `biggest` (Grand Salami) | −100.2u on 192.5 (35 slips) | 2026-08-14 | code deleted |
| `family` (Dingers) | 11–80, −33.34u | 2026-08-25 | code retired |

> ⚠️ **The board's big "+Nu" season number is the SUM of the `defs` category `units`, not
> `history[-1]`.** `history` only feeds the sparkline. A category absent from `defs` is invisible
> to the total even if `season.json` still holds it. To correct the displayed total, edit the
> category `units` and apply the same delta to `history[-1]` so the curve stays consistent.

> **Reality check.** Backtesting says the model does **not** out-predict the HR-prop market on
> ranking alone. The honest summary, as of the 15-season work on 2026-09-13: the shipped basket
> measures **AUC 0.6225** against outcomes, and ranking skill is concentrated at **+450 to +650**
> and is indistinguishable from zero above +650. Builder singles bleed (−14.05u over 258); the
> moon line carries the whole book (+459.73u over 446), which on 58 winners is a distribution
> with a long right tail rather than a demonstrated edge. Nothing here is proof of an edge; treat
> the tracker as a record of what happened, not as a forecast.
