# Kasper — Ticket Room

A daily MLB home-run-prop handicapping board. It scores every hitter on the slate through a power/matchup model, gates the field down to a betting pool, builds a structured set of tickets (anchored 3-leg parlays, a salami round robin, bankroll builders, a nightcap and a lunch special), and renders an interactive HTML "ticket room" with live grading and a season ledger.

Daily numbers come from a free, keyless auto-pull (with a hand-vetted fallback). Live results are pulled from the sports-data feed at grading time.

## How it works

The board is produced by a four-stage pipeline:

```
fetch_mlb.py        ->  slate_auto_<date>.json   # data pull: games, SPs, lineups, ISO, HR/9, weather
build15.py          ->  D_0615.json              # scoring brain: raw slate -> scored rows + season
assemble_tickets.py ->  (tickets in D)           # ticket builder: gates the pool, assembles tickets
regen15.py          ->  ticket_room.html         # injector: renders D into the shell, patches the view
```

1. **fetch_mlb.py** is step one and the only piece the GitHub Action runs on a schedule. With no API key and no account it pulls the day's games and probable starters, posted lineups, each hitter's season ISO and each starter's HR/9 from the MLB StatsAPI, plus per-ballpark wind/temp/precip from Open-Meteo (domes -> neutral), and writes `slate_auto_<date>.json`. Re-running just overwrites that file, so lineups, HR/9 and weather all sharpen through the day.

2. **build15.py** is the scoring brain. It holds the day's row data (ISO, the games and their starting-pitcher matchups, consensus odds) and reads `slate_auto_<date>.json` so weather, HR/9 and posted lineups override the hardcoded fallbacks. It converts a raw power term to a percentile across the full field, blends in matchup, park, weather, form and ISO factors, and writes the scored rows plus season metadata to `D_0615.json`.

3. **assemble_tickets.py** exposes `assemble(D)`. It consumes the scored `D`, gates the field to the betting pool (see **Pool gating**), and writes every ticket back into `D['tickets']`. `carryover()` rolls any game left suspended on the prior slate into today's field before assembly.

4. **regen15.py** is the injector: it loads the shell HTML, swaps in `D`, rolls the date, and applies the layout/badge patches. The finished board lands in the outputs directory as `ticket_room.html`, which is published as `index.html`.

The published `index.html` also carries a client-side engine that **re-drafts the board live** in the browser using the same gating and window rules as `assemble_tickets.py`, regrades legs as results post, and writes each ticket's short note (see **Notes**).

## The model

Each hitter's score combines a raw power term (recent power x hard-hit x a launch-angle window) converted to a percentile across the entire field, then adjusted for the opposing pitcher's HR/9, the ballpark, weather, form, and ISO. The same scored field feeds every ticket type, so a bat's standing reflects one consistent number.

**Confirmed-lineup status** is driven by the posted lineup in the slate pull: once a team's card is posted, its listed bats are marked `confirmed` and any carded bat not in it is dropped as `out`. Until a team's card posts, it falls back to the hand-kept reconciliation (`CONFIRMED` / `SCRATCHED`) in `build15.py`.

## Pool gating

Eligible bats are the priced, in-lineup hitters that aren't voided or scratched. From those, ranked by odds (shortest first):

- **The ban-8** — the 8 shortest-odds bats (`CHALK_N`). These are reserved for the **nightcap and lunch special only**; they never appear in moons, the salami, or builders.
- **The pool** — the next `GATE_N` (33) by odds *below* the ban-8, plus any bats tied on the cut line. This is the field every parlay and builder draws from.
- **Extra** — bats at #42 and beyond, used only as a last resort when the 33 can't supply a distinct game for a parlay leg.

There is no implied-probability floor. Anchors are the four best *non-chalk* bats by model TOTAL, one per game, never a suspended game.

## Window / timing

Parlay legs are kept close in start time. `WIN` (165 minutes, in the client engine) is the span past which a ticket trips the lineup-timing flag. Partners are chosen **tightest-first**: each parlay takes the minimum-time-span set of distinct-game legs available, expanding from the 33 to #42+ only if it can't otherwise field enough distinct games. It never reaches across the day for a leg when a closer one exists.

## Ticket types

- **Salami** — the anchor A4 plus the three longest shots in distinct games inside one tight window, as a full round robin (by 2s, 3s & 4s). It is **drafted first** so it keeps the tightest window before the moons consume the shared longshots.
- **Moons** — five clean three-leg parlays at 1u each, on a 2/2/1 anchor split (A1x2, A2x2, A3x1). Each is an anchor plus two min-span partners from the pool.
- **Builders** — every remaining non-chalk bat as a single-leg bankroll play, 1u each (not capped).
- **Nightcap** — the shortest-odds ban-8 bat in the latest game.
- **Lunch special** — the shortest-odds ban-8 bat in a pre-4pm game.

Staking is flat: 1u per bet. Counts fall out of the gated pool; the ban-8 only ever surfaces in the nightcap and lunch.

## Notes

Ticket notes are generated **client-side** in `index.html` (`cwNote` / `microRanked` / `microPick`) — terse, two-line tags drawn from the hidden info a card doesn't already show (opposing HR/9, hard-hit, launch window, ISO, park). The longer prose write-up lives on each player card. The assembler itself sets `note=""`; it does not write copy.

## Output

`index.html` is a self-contained interactive board: ticket cards with per-leg power bars (sized to TOTAL vs the field max), parlay/round-robin odds and payouts, dome/boost/suppress badges, a nightcap dropdown, and a season ledger with a running net and sparkline. Legs grade live (win / loss / void-refunded) once results are available.

## Repository layout

```
fetch_mlb.py          # step 1: free auto data pull -> slate_auto_<date>.json   (run by the Action)
build15.py            # scoring brain -> D_0615.json
assemble_tickets.py   # ticket builder: assemble(D), gating + ticket assembly + carryover()
regen15.py            # HTML injector -> ticket_room.html
index.html            # published board (baked D + client re-draft/grading engine + notes)
inject15.py           # legacy duplicate of an earlier scorer (not in the live path)
.github/workflows/pull-slate.yml   # schedules fetch_mlb.py and commits slate_auto_<date>.json
CNAME                 # theticketroom.live
```

## Running

The GitHub Action runs only the data pull:

```
python3 fetch_mlb.py          # writes slate_auto_<date>.json (also the manual "Run workflow" button)
```

Build the board from a scored slate:

```
python3 build15.py            # writes D_0615.json
python3 -c "import json,assemble_tickets as A; D=json.load(open('D_0615.json')); A.assemble(D); json.dump(D,open('D_0615.json','w'))"
python3 regen15.py            # writes ticket_room.html
```

Then publish `ticket_room.html` as `index.html`.

## Conventions

- The auto-pull is the daily source; the hardcoded rows are a fallback when a value isn't pulled.
- Confirmed status comes from posted lineups; keep rebuilding through the day as cards post.
- On a tie at the pool cut line, expand rather than drop a tied bat.
- The ban-8 is never used outside the nightcap and lunch special.
- The live sports-data feed is the source of truth for grading.

## Configuration knobs

In `assemble_tickets.py`:

- `CHALK_N` — size of the ban-8 reserved for nightcap/lunch (default 8).
- `GATE_N` — parlay/builder pool size below the ban-8, before tie expansion (default 33).
- `MOON_PLAN` — anchor indices per moon (default `(0,0,1,1,2)` -> A1x2, A2x2, A3x1).
- `LUNCH_CUT_MIN` — the lunch/night cutoff in minutes (default `16*60`, i.e. 4:00 PM).

In the `index.html` client engine: the same `CHALK_N` / `GATE_N` / `MOON_PLAN`, plus `WIN` (timing-window minutes; a wider span trips the timing flag). The server assembler and the client engine must keep these rules in sync so a baked ticket and its live re-draft agree.

> There is no implied-probability floor (`MIN_IMP`) and no separate top-N-chalk lever: the ban-8 reservation *is* the chalk exclusion, and it lives in the gating step of `assemble_tickets.py` (mirrored in `index.html`).
