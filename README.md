# Kasper — Ticket Room

A daily MLB home-run-prop handicapping board. It scores every hitter on the slate through a power model, gates the field down to a betting pool, builds a structured set of tickets (anchored 3-leg parlays, a salami round robin, bankroll builders, a nightcap and a lunch special), and renders an interactive HTML "ticket room" with live grading and a season ledger.

Daily numbers come from a free, keyless auto-pull (with a hand-vetted fallback). Live results are pulled from the sports-data feed at grading time.

## How it works

The board is produced by a four-stage pipeline:

```
fetch_mlb.py        ->  slate_auto_<date>.json   # data pull: games, SPs, lineups, ISO, HR/9, weather
build15.py          ->  D_0615.json              # scoring brain: raw slate -> scored rows + season
assemble_tickets.py ->  (tickets in D)           # ticket builder: gates the pool, assembles tickets
regen15.py          ->  index.html               # injector: reads index.html as its own shell, swaps in D in place
```

1. **fetch_mlb.py** is step one and the only piece the GitHub Action runs on a schedule. With no API key and no account it pulls the day's games and probable starters, posted lineups, each hitter's season ISO and each starter's HR/9 from the MLB StatsAPI, plus per-ballpark wind/temp/precip from Open-Meteo (domes -> neutral), and writes `slate_auto_<date>.json`. Re-running just overwrites that file, so lineups, HR/9 and weather all sharpen through the day.

2. **build15.py** is the scoring brain. It holds the day's row data (ISO, the games and their starting pitchers, consensus odds) and reads `slate_auto_<date>.json` so weather and posted lineups override the hardcoded fallbacks. It converts a raw power term to a percentile across the full field, blends in park, weather, form and ISO factors, and writes the scored rows plus season metadata to `D_0615.json`.

3. **assemble_tickets.py** exposes `assemble(D)`. It consumes the scored `D`, gates the field to the betting pool (see **Pool gating**), and writes every ticket back into `D['tickets']`. `carryover()` rolls any game left suspended on the prior slate into today's field before assembly.

4. **regen15.py** is the injector: `index.html` is its own shell/template — it reads `index.html`, swaps in `D`, rolls the date, applies the layout/badge patches, and writes the finished board back to `index.html` in place. The Action commits that file.

The published `index.html` also carries a client-side engine that **re-drafts the board live** in the browser using the same gating and window rules as `assemble_tickets.py`, regrades legs as results post, and writes each ticket's short note (see **Notes**).

## The model

Each hitter's score (`TOTAL`) combines a raw power term (recent power x hard-hit x a launch-angle window) converted to a percentile across the entire field, then adjusted for the ballpark, weather, form, and ISO. `TOTAL` is the number shown on each card and the one that gates the field down to the pool.

Role assignment runs on a second number — **strength** — that blends `TOTAL` with the market: `strength = 0.65 x TOTAL + 0.35 x implied-probability` (from the HR odds), each min-max normalized across the pool. Anchors, the salami pick, the snake draft, and moon/builder ordering all sort by strength, so a long-odds bat the model loves can't outrank a likelier, nearly-as-strong one. We don't out-predict the market, so likelihood gets a real vote; projection still leads at 65%, so a short-odds weak-projection bat can't float to the top either. `TOTAL` is unchanged and still drives the display; strength only drives which bats get which role.

**Confirmed-lineup status** is driven by the posted lineup in the slate pull: once a team's card is posted, its listed bats are marked `confirmed` and any carded bat not in it is dropped as `out`. Until a team's card posts, it falls back to the hand-kept reconciliation (`CONFIRMED` / `SCRATCHED`) in `build15.py`.

## Pool gating

Eligible bats are the priced, in-lineup hitters that aren't voided or scratched. **Rain gate first:** a game whose first-pitch precip is **≥70%** is dropped from the pool entirely (none of its bats appear in the field, any ticket, or the counts); a game at **50–69%** keeps its bats in the pool but bars them from every parlay leg — they can only surface as builder singles; **<50%** is normal. From the surviving bats, ranked by odds (shortest first):

- **The ban-8** — the 8 shortest-odds bats (`CHALK_N`). These are reserved for the **nightcap and lunch special only**; they never appear in moons, the salami, or builders.
- **The pool** — the next `GATE_N` (33) by odds *below* the ban-8, plus any bats tied on the cut line. This is the field every parlay and builder draws from.
- **Extra** — bats at #42 and beyond, used only as a last resort when the 33 can't supply a distinct game for a parlay leg.

The pool cut (which 33 bats make the board) is still by model `TOTAL`; **strength** decides roles within it. There is no `TOTAL` *floor* on any pick and no implied-probability *floor* — anchors, moon/salami legs, and builders all backfill uniformly from the top 33 (a low-`TOTAL` bat is replaced like a scratch, not blocked). Implied probability is folded into anchor selection through strength. Anchors are drawn from the *non-chalk* pool by strength, one per game, never a suspended game — and the final four are the set whose draft actually fills every parlay (see **Ticket types**), not simply the four strongest on paper.

## Window / timing

Parlay legs are kept close in start time. `WIN` (150 minutes) is the span past which a ticket trips the lineup-timing flag, and no parlay's legs may straddle more than that. Within the window, legs are drafted by **strength** (one bat per distinct game) — the window is a hard constraint, not the sort key. The live client re-draft will reach past the 33 to #42+ only as a last resort when it otherwise can't field enough distinct games; the baked board never does.

## Ticket types

- **Salami** — a four-leg round robin (by 2s, 3s & 4s). It goes to whichever anchor can reach the strongest three partners it can legally pair with: the strongest reachable bat **per distinct game**, inside one `WIN` window (`fitpool`). Legs are the strongest reachable bats by strength, not longshots. (The dedup-by-game matters — without it an anchor sitting next to a same-game cluster looks artificially well-supported.)
- **Moons** — clean three-leg parlays at 1u each: **two per non-salami anchor** (`MOONS_PER_ANC`, default 2), so three moon anchors yield six moons. Each is an anchor plus two distinct-game partners drafted from the pool by strength (weakest-anchor-first snake). The four anchors are chosen as the set whose moons + salami all fill; if none can fill cleanly, unfillable parlays dissolve to builders rather than ship short.
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
regen15.py            # HTML injector: rewrites index.html in place
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
python3 regen15.py            # rewrites index.html in place (commit it)
```

`index.html` is rewritten in place by step three; commit it to publish.

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
- `MOONS_PER_ANC` — moons built on each non-salami anchor (default 2).
- `FLOOR` — retained as a constant (75) but **no longer gates any pick**; the pool backfills uniformly from the top 33, so a low-`TOTAL` bat is replaced rather than floored out.
- `LUNCH_CUT_MIN` — the lunch/night cutoff in minutes (default `16*60`, i.e. 4:00 PM).
- The strength blend (0.65 `TOTAL` / 0.35 implied-prob) lives in the `strength()` helper in both engines; change the 0.65 there to retune projection-vs-market.

In the `index.html` client engine: the same `CHALK_N` / `GATE_N` / `MOONS_PER_ANC` / `WIN`, the rain thresholds (≥70 out of pool, 50–69 parlay-barred), plus its own `strength()` blend. The server assembler and the client engine must keep these rules — and the strength weight — in sync so a baked ticket and its live re-draft agree.

> There is no implied-probability *floor* and no separate top-N-chalk lever: the ban-8 reservation *is* the chalk exclusion (it lives in the gating step of `assemble_tickets.py`, mirrored in `index.html`), and implied probability enters role selection through the 35% term in `strength()`, not a hard cutoff.
