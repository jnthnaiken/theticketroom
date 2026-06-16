# Kasper — Ticket Room

A daily MLB home-run-prop handicapping board. It scores every hitter on the slate through a power/matchup model, gates the field down to a betting pool, builds a structured set of tickets (anchored 3-leg parlays, a salami round robin, bankroll builders, and a nightcap), and renders an interactive HTML "ticket room" with live grading and a season ledger.

All inputs are supplied by hand each day from a vetted snapshot — the system never invents numbers. Live results are pulled from the sports-data feed at grading time.

## How it works

The board is produced by a three-stage pipeline, run in order:

```
build15.py   ->  D_0615.json        # scoring brain: turns the raw slate into scored rows
regen15.py   ->  (tickets in D)      # ticket builder: gates the pool and assembles tickets
inject15.py  ->  ticket_room.html    # injector: renders D into the shell, patches the view
```

1. **build15.py** holds the day's hardcoded data — roughly 171 hitters with ISO, pitcher HR9, the ten games and their starting-pitcher matchups, ballpark/weather flags, and consensus odds. It computes a power index as a percentile across the full field, blends in matchup and park factors, and writes the scored rows plus metadata to `D_0615.json`.

2. **regen15.py** gates the scored field to the betting pool (top 33 by implied probability, with a low-end longshot floor and tie expansion at the cut line), then assembles every ticket and writes them back into `D`.

3. **inject15.py** loads the shell HTML, swaps in `D`, fixes the date, and applies the layout/badge patches. The finished board lands in the outputs directory as `ticket_room.html`.

## The model

Each hitter's score combines a raw power term (recent power, hard-hit, launch-angle window) converted to a percentile across the entire field, then adjusted for the opposing pitcher, the ballpark, weather, and confirmed-lineup status. Benched or scratched bats are dropped. The same scored field feeds every ticket type, so a bat's standing in the pool reflects one consistent number.

## Pool gating

The pool is the top 33 hitters ranked by implied probability (derived from consensus odds), subject to two adjustments:

- A longshot floor removes bats below roughly 10% implied probability.
- If a tie sits exactly on the cut line, the pool expands to keep every tied bat rather than dropping one. (This is why a given night can settle at 34 instead of 33.)

The chalkiest bats are kept and used as anchors — they are not excluded from the pool.

## Ticket types

- **Moons** — clean three-leg straight parlays at 1u each. Each is built around an *anchor* (top chalk, one per game), and an anchor recurs across several of its own parlays. The two non-anchor legs ("the duo") are chosen snake-draft style so each parlay pairs a stronger bat with a longer shot rather than stacking studs.
- **Salami** — the four longest shots in distinct games inside one time window, played as a full round robin (by 2s, 3s, and 4s).
- **Builders** — the top leftover chalk as single-leg bankroll plays, 1u each.
- **Nightcap** — the strongest late bat as a single.

Staking is flat: 1u per bet. There are no hard caps on the number of anchors, duos, or tickets — the counts fall out of the gated pool.

## Output

`ticket_room.html` is a self-contained interactive board: ticket cards with per-leg power bars, parlay/round-robin odds and payouts, dome/boost/suppress badges, a nightcap dropdown, and a season ledger with a running net and sparkline. Legs grade live (win / loss / void-refunded) once results are available.

## Repository layout

```
slate0615/
  build15.py          # scoring brain -> D_0615.json
  regen15.py          # ticket builder (gating, ticket assembly, grader)
  inject15.py         # HTML injector
  shell_0614.html     # base shell/template the board renders into
  D_0615.json         # scored field + tickets (generated)
outputs/
  ticket_room.html    # final rendered board (generated)
```

## Running

```
cd slate0615
python3 build15.py      # writes D_0615.json
python3 regen15.py      # builds tickets into D
python3 inject15.py     # writes outputs/ticket_room.html
```

Then open `ticket_room.html`.

## Conventions

- Inputs are hand-supplied from a vetted daily snapshot; numbers are never fabricated.
- Always rebuild against the latest snapshot and regenerate the whole board when the slate changes.
- On a tie at the cut line, expand the pool — never drop a tied bat.
- The live sports-data feed is the source of truth for grading.

## Configuration knobs

Defined in `regen15.py`:

- `GATE_N` — pool size before tie expansion (default 33).
- `MIN_IMP` — longshot floor on implied probability (default 0.10).
- `WIN` — the time-window span, in minutes, used to keep parlay/salami legs compatible.

> Note: there is currently no "exclude the top-N chalk" lever. The chalk is used as anchors, not removed. Adding a top-N-chalk exclusion would be a change to the gating step in `regen15.py`.
