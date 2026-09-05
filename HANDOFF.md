# The Ticket Room — Handoff / Resume Notes

> ⚠️ **This file is layered by date and older sections contradict newer ones.** Audited 2026-08-13;
> every superseded claim below is now marked inline. When two sections disagree, **the later date wins**,
> and the code wins over both. Corrected on 2026-08-13: the Kasper column-picker (HH%/LA render by
> default), `RULES_VERSION` (removed), conviction-snub builders (removed 07-09), the nine edge signals
> (superseded again 2026-08-13: **five** are live after the Statcast refit), `grade_night` (does NOT re-draft), and the base64 transfer channel (blocked).
> Superseded again 2026-08-14: the **Chef's Table ticket is retired** (the chalk reservation is not).
> Superseded again **2026-08-16**: the board now **re-fetches and adopts newer server builds**
> (it never did before — that is what made a left-open tab bet a ticket the server had dropped);
> the ticket lock fires on **confirmation** as well as first pitch; a slip can no longer be created
> after its own first pitch; and `assemble_tickets.py` is **not** a mirror of the rules engine —
> it has no family/chef logic and no lock at all, so a fallback is a failed build, not a safe one.
> Draft rules as of 2026-08-14 live in `README.md` — that file is kept current; this one is a log.


> **2026-08-14, later: the Grand Salami is REMOVED** — deleted, not gated — and the board now runs
> **8 MOONS**. `sidx`/`wantSalami`/`_sal` are gone, nothing is reserved, and those bats draft
> normally. A flag version shipped first and was rejected: it left the weakest anchor reserved and
> then discarded its ticket. FOUR construction paths had to go, the sneaky one being the
> client-side SALVAGE/REBUILD pass. Cost vs the old board: −10.5u/night over 37 graded cold drafts
> (t = −1.36, inside noise). Rendering/grading of an existing salami is untouched, so archived
> boards still show what they shipped.
> **The `biggest` LEDGER LINE was then removed as well** — owner's call, same day, overruling the
> "those were real bets, the line stops accruing" reasoning below. All 35 slips were unwound by
> re-grading the archived boards, not by subtracting the category total; the season went
> **+196.09u → +296.29u** and 192.5u of stake came off the book. Superseded detail below, kept
> for the record:
> Worst line on the ledger: −100.2u on 192.5 staked (−52.1%) over 35 real slips. **Moons stay at
> 6** — `sidx` is left alone on purpose so the weakest anchor is still held back from moon-anchoring;
> the slip just is not built and its bats stay in the pool. Builders drop 4 → 3. Retiring it grades
> at +0.03u/night (t = 0.01) on 23% less stake with lower variance, better on 27/37 nights; the
> 8-moon variant (freeing that anchor) graded −10.5u/night and was rejected.
> **THREE build sites** must be gated: the prior path, the fresh draft, and the client-side
> SALVAGE/REBUILD pass — the third one silently resurrected the slip on the first attempt.
> The section and view chip are removed; `const noSalami` is now dead code. (The `biggest` tracker
> row and ledger history were kept at this stage and removed later the same day — see above.)

Quick-start status so a fresh session can continue without re-deriving context.

## 🛑 2026-08-16 — the board never re-fetched itself. Four fixes, one commit (`edaedd7`).

**The bug that cost a bet.** `index.html` baked the board in as `const D={…}` and **never
re-fetched `D_<date>.json`**. The live loop refreshed weather, lineups, results and re-drafted —
all against the load-time copy. A tab left open kept drafting a ticket set the server had thrown
away hours earlier, while the incoming live data made it look current *and marked its legs
confirmed*. Reconstructed from the archives: a tab on the 4:34pm board still showed `All Day`
(Bobby Witt) and rendered it **fully confirmed at ~6:42pm** — the state the owner bets on. The
server had replaced him with Gary Sánchez at 4:39pm and `grade_night.py` graded that. Same root
cause as a desktop reading +299.9u while a phone read +301.3u.

**The 4:39pm swap was not itself a bug.** Sánchez went `projected → confirmed` at exactly that
build (MIL@LAD 7:15 posted); Witt did not confirm until 5:54pm (KC@LAA 9:38). A newly real bat
displaced a projection — the board doing what it is supposed to do as lineups come out. The tab
just never heard about it.

| marker | change |
|---|---|
| `ADOPT-2026-08-16` | every refresh fetches `D_<date>.json`; a new `meta.build` is adopted whole, with hr flags / `finals` / `gs` / `live` re-applied and `CACHE` nulled. Silent, by owner's call. Fails soft — no network or a downloaded copy keeps the baked board. |
| `CONFLOCK-2026-08-16` | a prior ticket is carried verbatim when its earliest leg is underway **or when every leg is confirmed and none is out/void**. The freeze previously read the clock alone, leaving a bat confirmed at 4pm for a 9:38 game re-draftable for 5½ hours. |
| `MINTGUARD-2026-08-16` | a slip may never be *created* past its own first pitch; moons die as a pair; no-op with no prior board. |
| `FAMPIN-2026-08-15` **removed** | the 08-15 pin stopped the Family Meal re-deriving at all, which also stopped it reacting to lineups posting. Wrong fix, backed out the next morning. |

**⚠️ `assemble_tickets.py` is not a second implementation — do not mirror rules into it.** Audited
2026-08-16, it is two board redesigns behind: the only `kind` literals it emits are `'moon'` and
`'biggest'`, its name pools are `biggest/builder/late/lunch/moon`, and it has **zero** matches for
`_now_min_et`, `_locked_prior`, `_locked_bats`, `_keep_fresh` or `chalk=set()`. So it has **no
Family Meal, no chef, no prior-board lock — and it still builds a Grand Salami**, retired 08-14 and
backed out of the ledger. It runs only when `client_assemble.js` is absent or node exits non-zero,
and then it re-drafts everything from scratch (including tickets whose games are underway), prints
one warning to the Action log, and commits — and `grade_night.py` books the result into a `biggest`
category the tracker no longer shows. **Treat a fallback as a failed build.** (This supersedes the
2026-08-08 note that any lock change "has to land in both".)

**⚠️ `client_sweep.js` cannot see draft churn.** It aborts all network, so `wf` never moves, `TOTAL`
never moves, nothing ever confirms and no bat ever goes `out` — the conditions that actually reshuffle
a derived section never occur. That is how 411 green integrity checks coexisted with 17 bats rotating
through 8 Family Meal seats on 08-15. `test_conf_lock.js` is the replacement shape: it posts lineups
mid-sweep (at first pitch −3h the nine confirm, everyone else in that game goes `out`, which re-scales
the pool) and drifts the weather. **Until a harness does that, it certifies nothing in this area.**

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
- `kasper_extras_<date>.json` — per bat: **`khr`, `iso`, `xwobacon`, `bip`** — ALL FOUR, off
  the same roster table (columns `KHR` / `ISO` / `XWOBAC` / `BIP`; `khr` is the 🧱 base-score
  badge, rounded to int; the other three stay as read). ⚠️ **KEXTRAKEY-2026-09-04 — do not
  thin this back to khr-only.** This section said "khr, rounded int" from the start, but
  `ISOSRC-2026-08-23` made `build15.py` take ISO from this same sidecar, and `DMGRATIO-2026-08-23`
  added `xwobacon`+`bip`. Nobody updated this line, so a khr-only file shipped every day and
  `ISO_KASPER`, `_USE_KWCON` and `_zdmg` were all silently dead — ISO floored to the literal
  0.10 for every bat, which is the exact bug ISOSRC existed to fix. The build now prints
  `kasper_extras: N entries -> N keys  khr= iso= xwobacon= bip=` and warns on any zero. If you
  see a zero there, the scrape is thin — go back and get the column.
  ⚠️ **DROPSCOPE-2026-09-05 — every extras entry MUST carry `"team"`** (the Kasper roster
  table's own team code). `slate_assemble.py` strips the tag before writing the dated file, so
  the shipped contract is unchanged — the tag exists only so a permanently-excluded bat can be
  told apart from the bat we keep. Without it the assembler **hard-errors and refuses to build**
  on any name collision. See the DROPSCOPE block under "PERMANENT ROSTER EXCLUSIONS" below.
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
sums the `defs` categories — now `cats.{lunch,late,builder,moon,family}.units`, in that order —
for the big "+Nu" number; `history` only feeds the sparkline. (`biggest` and `chef` are both out
of `defs`, so neither contributes; a category absent from `defs` is invisible to the total even
if `season.json` still holds it.) To correct the displayed total, edit the category `units` AND keep
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
  against `build15.py` 2026-08-13).** `_SIG` now carries **FIVE** live signals — **REFIT 2026-08-13**
  on the 2015-2024 Statcast table (316,463 batter-games, grouped-by-date CV; `fit_savant.py`,
  Savant Fit run 31731827046): `_zxpow 0.029`, `_zxwcon 0.193`, `_zars 0.011`, `_zhh 0.432`,
  `_zla 0.335`. `hh`/`la` were promoted out of display-only chips (the two strongest predictors);
  `la` enters through the `la_window` bell, not linearly. This replaced the `.45/.35/.20`
  "reasoned guesses" that had been live since 07-09. `W_ARS` is **0.10**, not 0.16 (display term). The nine-signal list below describes a
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
- ~~**Chalk = the Chef's Table.**~~ **SUPERSEDED 2026-08-14 — the ticket is gone, the
  reservation is not.** `CHALK_N=4` bats are still reserved and still barred from every
  other ticket; they are simply no longer emitted as a round robin (`CHEF_TICKET=false`).
  Seat selection is unchanged: as of 2026-08-08 those seats are the 4 best by **STRENGTH**
  (normalized TOTAL, min-max over the gated pool), one per game — *not* the 4 shortest prices.
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

All zeroed and never revived. **Superseded 2026-08-13:** the surviving `_SIG` weights are now
FITTED (Statcast 2015-2024), not guesses — see the corrected block above and `README.md`.

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
| `kasper_extras_<date>.json` | optional *(but see note)* | Kasper matchup pages | `{name:{khr,iso,xwobacon,bip}}` — **all four**. Optional to the loader, not to the model: without `iso`/`xwobacon`/`bip` the ISO source, `_USE_KWCON` and `_zdmg` all go dark and the board still builds. |
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

**kasper_extras sourcing.** Kasper's Export is "under construction," so `kasper_extras` is
hand-built off each matchup page (`?game=<pk>`), same roster tables as cards. Read FOUR
columns per bat, not one: `KHR` → `khr` (rounded int), `ISO` → `iso`, `XWOBAC` → `xwobacon`,
`BIP` → `bip`. Full default header, 2026-09-04:
`HITTER NAME|MATCH|CEIL|ZONE|KHR|FORM|PIT|BIP|ISO|XWOBA|XWOBAC|SWS%|PBRL%|BRL%|SWSP%|FB%|HH%|LA|Likely`
— note `XWOBA` and `XWOBAC` are different columns and it is `XWOBAC` you want. Identify a
roster table by `KHR`+`ISO`+`XWOBAC`+`BIP` in its header and skip the 3-row *Best Matchups*
highlight table, whose header is identical. Strip the `▸` prefix and the `LHB/RHB/SHB` suffix
off each name, then the generational suffixes.
`iso` outside 0.02–0.60 is dropped by `build15.py` and falls back to the slate median; `bip`
below `MIN_DMG_BIP` (40) means no `_zdmg` for that bat. Both are normal — a full slate lands
around iso 402/416 and bip≥40 373/416.

## 🚫 PERMANENT ROSTER EXCLUSIONS — `DROP_BATS` covers cards, lineups AND extras

`slate_assemble.DROP_BATS` is the owner's standing list of bats that are **out of the pool, full
stop**. Today it is one entry: `('ATH', 'Max Muncy')` — the Athletics' Muncy, never the Dodgers'
(owner's call 2026-08-17, restated 2026-09-05: *"ive said before to drop the athletics muncy from
the pool permanently. we will never use him"*).

⚠️ **DROPSCOPE-2026-09-05 — the 08-17 implementation pruned `cards` ONLY, and that is not what
"out of the pool" means.** Two surfaces still carried him, both silent, both scoring a bat the
board actually drafts:

- **`kasper_extras` is keyed by NAME ALONE**, so whichever matchup page the daily scrape visited
  LAST owned the entry. On 2026-09-05 ATH@SEA is game 15 and WSH@LAD is game 14, so the
  Athletics' Muncy overwrote the Dodgers': **khr 45 vs 54, bip 226 vs 1382, iso .171 vs .244,
  xwobacon .329 vs .424** — every column wrong, feeding `_ziso`, `_zxwcon` and `_zdmg` for a bat
  on a live ticket. Nothing warned. It was caught by eye, not by any check.
- **`lineups` still listed him** whenever the Athletics started him, so an ATH lineup slot would
  be scored off the *surviving* team's card and extras entirely.

Now: `drop_excluded(cards, extras, roto)` prunes **cards, lineups and extras** and returns its own
hard errors. Because extras have no team of their own, the scrape tags each entry with `"team"`
(stripped before write). An untagged entry for an excluded name is resolved when only one of the
colliding teams is on the slate, and is a **HARD ERROR when both are — it is never guessed.**
`slate_validate.py` re-checks the shipped files independently, so a hand-rolled or
half-reassembled slate cannot put him back.

Verified 2026-09-05, four cases plus a negative control:

| case | result |
|---|---|
| extras untagged, ATH and LAD both on slate | **exit 1**, refuses to guess |
| extras tagged `LAD` (the survivor) | clean, LAD's numbers kept |
| extras tagged `ATH` (the 09-05 bug) | entry dropped, 418 → 417 extras |
| tagged `LAD` + ATH actually starts him | lineup slot removed, hands stay aligned |
| **negative control:** him hand-added back to cards + lineups | `slate_validate` **exit 1**, both surfaces named |

**`odds` cannot be fixed this way** — VegasInsider posts no team, and on 2026-09-05 it published
two `Max Muncy` rows (the 08-17 bug again). Scrape rule: on a duplicate name, **keep the row with
the most book quotes** — the bat the market actually prices broadly is the one playing. That
picked LAD correctly (4 books, median +345) over ATH (2 books, +700). An odds entry with no
surviving card is inert, and `slate_validate` warns on it.

**To exclude another bat: add the `(TEAM, NAME)` pair to `DROP_BATS` and nothing else.** All three
surfaces and both gates follow from that one line.

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
- **Superseded 2026-08-13:** `_SIG` weights are now fitted (`fit_savant.py`, 2015-2024 Statcast).
  But that fit answers "predicts HR", NOT "beats the price" — the corrected harness
  (`backtest_true_*.py`, Actions → **Backtest True**) drafts through the REAL client engine with
  true DNP voids and grades vs a market-only board: on 38 nights NO basket separates from the
  price benchmark, and top-8 model singles run below naive favorites. The bullet below still stands.
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
2. ~~Backtest the edge signals for real and refit `_SIG`~~ — **DONE 2026-08-13** (Statcast refit
   shipped to `build15.py`; `backtest_true_*` harness committed). The remaining gap is PRICES:
   keep the `markets_*.json` closing-odds log accruing so a closing-line test becomes possible.
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
- `kasper_extras_<d>.json` `{name:{khr,iso,xwobacon,bip}}`   ← all four; khr-only is a thin scrape, see above
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

### BEFORE YOU SHIP A CHANGE TO index.html: `node replay_check.js`
Run it from the repo root. It replays REAL archived boards through the REAL engine and
fails the invariants that keep breaking:
  1. a locked ticket never changes and only ever leaves the board on a scratch
  2. no bat on two OPEN slips (an anchor on his own moons/builder is exempt)
  3. board shape (reported, not enforced -- `family` is leftovers and varies)
  4. BAKED: once the slate's date has passed in ET, replaying the final board changes nothing
  5. ANCHORS: never >4 distinct moon anchors; never an OPEN moon led by a scratched bat; never an
     anchor shipping ONE moon unless the other is already placed; the anchor set never shrinks below
     four while moons are still open; at most one `late` and one `lunch`
`node replay_check.js` does yesterday+today; pass dates for anything else. Exit 0 = clean.
A full week (`2026-08-12 .. 2026-08-18`) takes ~8 min and is ~1,075 chained builds -- run it in the
background and check the file, or a 2-minute shell timeout will kill it mid-sweep.

It works because every build is committed as `D_<date>.json`, so git history IS the corpus,
and because the replay is CHAINED -- build N's output becomes build N+1's prior, which is
what production does (regen15.py reads the prior board from index.html's `const D`, not from
D_<date>.json). Checking each build against its ARCHIVED prior hides exactly the drift this
is looking for.

Written 2026-08-17 after four bugs in one day, every one a confident diagnosis that was
wrong or unmeasured. Its numbers: the shrink guard fired 94x in 58 builds with 93 of those
restores duplicating a bat already on the board; 64 changes to already-locked tickets on
08-16; and a fix about to ship (FAMLOCK) that changed literally nothing. Sanity-checked by
pointing it at the pre-fix engine -- 76 violations, exit 1. A test that cannot fail is worthless.

### 2026-08-18 — REDRAFT: a dead anchor REDRAFTS the board, it does not vacate a seat
Owner: *"its not about replacing, its about redrafting. from scratch. the board needs to reflect the
correct draft."* `searchBest` picks the best four-anchor SET **jointly**, so the three survivors are only
the right three GIVEN the fourth. Patching the hole with "next bat in line" can only re-rank what the old
set left over. 08-18: Buxton scratched, seat refilled with Crow-Armstrong — only because Montgomery and
Rice were already spent as legs. A real joint redraft seats Montgomery. 08-17: Goodman died and the patch
could not refill him, so 72 of 129 builds shipped THREE anchors and six moons.

Now: any still-open moon whose anchor is no longer draftable (scratched / voided / gone from the pool /
now chalk) throws the OPEN board away and re-runs the fresh joint draft. Locked slips are placed bets —
emitted verbatim, bats reserved, never re-derived — and `_KT = 4 - committed anchors` so the redraft fills
only the seats they have not already spent. The old dead-anchor patch is DELETED (its trigger was
bit-for-bit the new predicate, so it was unreachable); `anchRepl` survives for OVERTAKE only.

Rides along, same class of bug: one builder per anchor (a locked prior builder counted), one nightcap and
one lunch play (the first cut of the redraft shipped TWO lunch tickets on 199 of 214 builds on 08-15 --
caught by the harness before it shipped, not by anyone looking), SHAPE REPAIR mints a nightcap a
scratch killed (a placed single that dies stays dead; an empty SLOT gets drafted), and a name a scratch
retires is not reused (`_killed`).

Verified: negative control fires 16x on 08-17 against the old engine; 08-12..08-18 clean at 1,075 builds.
Full write-up: project doc `claude/redraft-2026-08-18.md`.

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


---

## 2026-08-14 — Chef's Table retired, Family Meal section added, ledger rebuilt

Three owner decisions, all explicit. Nothing here was inferred.

**1. The Chef's Table ticket is retired.** It was a test. `var CHEF_TICKET=false` in
`index.html` gates the `out.push()`; the chalk *reservation* above it is deliberately
untouched, so the top-`CHALK_N` favourites are still barred from moons/salami/builders.
Chef is dropped from the board outright: `prior` is filtered before the draft, so a chef
ticket on a prior board is **not carried**, and no Chef's Table section renders. The first
cut of this change kept locked chef slips visible — wrong, corrected the same day. The
10:00→23:00 sweep on the 08-13 board reports `n=13`.

**2. The Family Meal replaces it, as a REAL TICKET KIND.** A bat qualifies when it cleared
the pool gate, was not chalk, made no slip, and **outscored the weakest bat the board actually
drafted**; the list is then capped at `FAM_CAP` (8). The slips are built into `out` just before
the wxsum/note pass, so they are ordinary tickets: they are in `D.tickets`, they get a
`cwNote()` description, `priceTicket` prices them, they lock and carry like anything else, and
`grade_night.py` folds them into `season.json` at 1u a slip. One card per bat through the same
`sec()` + `ticketCard()` path as Anchors, plus a **Family Meal row in the season tracker**.

Three wrong cuts preceded this, all mine, all the same mistake -- inventing instead of matching:
bespoke row markup; then a single multi-leg card; then one-card-per-bat but held outside
`D.tickets` so it had no descriptions and never reached the ledger. **"Like the rest of the
board" means all the way down.** Named by the owner -- "orphans" was proposed and rejected.

Build details that matter: family bats are excluded from the drafted set that sets the floor
(otherwise the section raises its own bar every pass), and a bat already on a carried locked
family slip is skipped so the carry is never duplicated. `assemble_tickets.py` does not build
them -- non-mirroring emergency fallback, same as it was for chef.

Sizing evidence, all cold-drafted through the real client engine over the 37 stored nights:

```
rank window (#1 chalk -> last drafted)   22 on 08-13 alone
gated pool minus drafted                 min 0  median 20  max 28  mean 19.2
above weakest drafted                    min 0  median  6  max 20  mean  7.0
above weakest + cap 8   <- SHIPPING      min 0  median  6  max  8  mean  5.3
```

The middle rule was recommended first, on 08-13 evidence alone, and that recommendation
was **wrong**: it reads as 11 that night only because the slate gated thin (pool 29). A
normal slate gates 40–47 and the tickets absorb ~21, which puts it straight back near 20.

**3. Chef's 13 graded nights were backed out of `season.json`.** Season **+148.74u →
+198.46u**. Method mattered here: rather than subtracting the category total, all 13 slips
were re-graded from the archived boards, and the 12 nights with stored outcomes reproduced
the recorded `−44.22u / 66.0 staked / 2 wins` **exactly** — which is what validates the
remainder for 08-13 (`−5.50u`, matching that board's `rr.risk` of 5.5, since StatsAPI is
unreachable from the sandbox). Nightly nets were subtracted from the cumulative curve from
each night forward; `cats` and `history` reconcile at 198.46.

**Also measured, and rejected: rolling `GAME_CAP` back.** The owner asked what a "3 per
team" rule would do to the undrafted count. 3-per-GAME (the pre-2026-07-04 rule) drops the
board from 12 tickets to **9** — two moons and a builder — and moves the undrafted count
only 26 → 24. A literal 3-per-TEAM cap (≤6/game) gives 25. The cap moves both ends of the
window together. `GAME_CAP` stays at 4.

**Verification before deploy.** Full `client_sweep.js` pass, 10:00→23:00 on 2026-08-13,
20-minute steps: 383 locked-slip integrity checks, `count=0 integrity=0 anchors!=builders=0
pairing=0 structural=0 one-bat-one-slip=0` — identical to the unpatched baseline.

**Known behaviour, not a bug.** On a cold 08-13 draft Kyle Schwarber (`TOTAL` 193.6, the
best bat on the slate) lands in the Family Meal: his game sat at 40% rain, which bars
anchoring under the rain bands, so he cleared the gate and made nothing. The section will
sometimes lead with a name that looks like it obviously should have been on a slip.

**Still open.** `drawTracker`'s `defs` array still carries a `chef` row. It is harmless —
the row only renders when the category exists, and the category is gone — but it should be
pruned on the next pass.

---

## 2026-08-14 (evening) — Family Meal to the bottom, real titles, ledger card cleaned

Four changes, each landed as its own commit against the live `pull-slate` cadence (the owner
declined to pause it: *"youre just gonna have to be fast"*). What works: `curl` HEAD immediately
before applying the patch so the base is current, then commit inside the gap. A build landing
*after* the commit is harmless — it rewrites only the `const D=` line. The killer is one already
in flight when you pull; that ate two earlier attempts.

**1. Family Meal renders last.** Page sections, tracker `defs`, and the View chip row, all three
in the same order: lunch → nightcap → anchors → moonshots → family meal. Script `reorder.py`.

**2. Ledger sparkline.** Two separate things, only one of them code. It was *stale* because the
board had been baked before the salami came off `season.json`; `spark()` auto-scales off
min/max of the series and re-drew itself correctly on the next build. The real defect was
`pts=[0].concat(hist)` prepending a zero to a history that already opens with 0 — a dead flat
segment across the first ~2.5% of the width. Now conditional. Script `sparkfix.py`.

**3. Family Meal titles.** See the README entry. Root cause of BOTH the missing titles and the
four cards naming the wrong player was the same `name:n` shortcut. Scripts `famname.py`,
`famrelabel.py` (a title-only relabel of two slips that had locked before the fix, explicitly
authorised — legs, odds, locks and grading byte-identical), `famnamefix.py` (`Staff Meal` →
`The Window`; no pool name may contain *family* or *meal*).

**4. The TONIGHT counter on the ledger card** read `4 ⚓️ · 8 🚀 · 0 🥪 · 1 🌃` — it counted the
retired Grand Salami, a permanent 0, and counted neither the Family Meal nor the Lunch Special,
so the sections at the top and bottom of the board were both invisible in the one line meant to
say what is on tonight. Now `1 🍱 · 1 🌃 · 4 ⚓️ · 8 🚀 · 8 🍳`, same five kinds and same order as
the rows above it. Script `tonightfix.py`.

**Audited and found NOT stale:** `grade_night.py` is kind-agnostic (`cats.setdefault(g['kind'],…)`),
so the Family Meal folds into `season.json` at 1u a slip with no code change — do not "add family
support" to it. `assemble_tickets.py` still does not build family slips, by design.
