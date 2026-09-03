# Round 466 (NUC-integration E) — the population that was the observer

**Box DOWN the whole round.** SIXTH consecutive down window (436, 442, 448,
454, 460, 466), one continuous outage. All findings are offline work on round
424's banked capture.

## 0. Reachability, first, because CLAUDE.md gates the round on it

Two probes, one per documented path, both before any code ran.

| path | issued | result |
|---|---|---|
| tailnet `ssh -o ConnectTimeout=12 -i ~/.ssh/id_ed25519 jab@100.78.44.111` | 2026-09-03T00:59:37Z | `Connection timed out`, rc 255, by 00:59:49Z |
| LAN `ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37` | 00:59:57Z | same; **the key still does not exist on this host**, so this path proves nothing either way |

`tailscale status --json` at 01:00:10Z: `Online false`, `LastSeen
2026-09-01T18:27:56.1Z` — **byte-identical to rounds 448, 454 and 460**, so
436/442/448/454/460/466 is ONE outage. The plaintext line reads `active; relay
"sin"; offline, last seen 1d ago, tx 10296 rx 0`.

`status` after this round's row: **29h50m36s confirmed**, upper bracket
30h53m18s. It passes the longest completed streak in this log (19h38m06s) by a
**definite 10h12m30s** and the longest unobserved one (14h00m00s) by 15h50m30s
— the longest outage this log has confirmed, extending its own record from
round 460. `unobserved_total_s` unmoved at 396 378 s.

CLAUDE.md's two-failure rule fired after the second probe. **Zero ssh sessions
succeeded, so nothing was read from or written to the box; port 8001 was never
contacted and no engine request of any kind was made.** Everything below is
offline.

Round 466's row was appended with round 460's `replay` producer, not typed:

```
python3 nuc/reachability_check.py replay --round 466 \
  --checked-at 2026-09-03T01:00:09Z --ssh-returncode 255 \
  --ssh-stderr "ssh: connect to host 100.78.44.111 port 22: Connection timed out" \
  --tailscale-json state/nuc-capture-r466/tailscale-status-r466.json --append
```

Round 460's item 1 ran first, before any other code:
`coverage --strict` **0**, `precision-audit --strict` **0**,
`lastseen-drift --strict` **1** — exactly the state round 460 left, and the
third is red for the reason round 460 documented (tailscale recomputes
`LastSeen`), not a new break.

---

## 1. Headline: the fire population is `.service`-only, and the journal is mostly not services

Round 436 proved that `parse_unit_starts` sees only what its regex chose. It
fixed the **verb** half — `Starting` vs `Started` — and left the **kind** half
open as its item 6, where it has sat untouched for five E rounds:
`session-*.scope` records "were skipped by this round's `.service`-only
default".

`unit_kind_census` on round 424's ten-day PID-1 journal:

| kind | `Starting` | `Started` | distinct units | visible to `parse_unit_starts` |
|---|---|---|---|---|
| service | **1652** | 206 | 80 | **yes** |
| scope | **0** | **1401** | 696 | no |
| timer | 0 | 84 | 14 | no |
| socket | 12 | 0 | 2 | no |
| path | 0 | 6 | 1 | no |

**1709 start lines are invisible — more than the 1652 that are visible.** And
the invisible majority is one thing: 1401 `Started session-N.scope`.

**Not one `.scope` emits `Starting`**, which is the same mechanism round 436
wrote down for `Type=simple` services: systemd announces a startup phase only
where there is one, and a scope is registered by an already-running process.
So round 436's two-pass rule — collect the units that ever say `Starting`,
admit `Started` only for those that never do — **generalises to scopes with no
new decision about double-counting.** Only the kind alternation has to widen.
`parse_unit_starts_any_kind(text, kinds)` is that widening and nothing else,
with the kind added to the dedup key so a `foo.service` that announces itself
cannot suppress a `foo.scope` that never does, and it is pinned to be
byte-identical to `parse_unit_starts_complete` at the default `kinds`.

### What the widening does to every published number

Pooled 10-day swap window, `LEDGER_MIN_BYTES = 4 825 665`, instrument excluded.
`K = 52` costly buckets holding **31.53 GiB** — re-derived, matching round 436
to the digit before anything was changed.

| population | fires | costly named | GiB named | % of swapped bytes |
|---|---|---|---|---|
| published (PID-1 `Starting` `.service`) | 647 | 19 / 52 | 8.42 | 26.7 % |
| round 436 complete (+ `Started`-only services) | 687 | 19 / 52 | 8.42 | 26.7 % |
| **+ `session-*.scope`** | 2088 | **44 / 52** | **29.65** | **94.0 %** |
| `scope` ONLY | 1401 | 29 / 52 | 22.78 | 72.3 % |
| engine events | 242 | 18 / 52 | 16.78 | 53.2 % |

(`fires` is the population after `LEDGER_EXCLUDE_UNITS`. `sysstat-collect` is
**1005 of the 1652** `Starting .service` lines — 61 % of the published
population is the instrument that writes the buckets, which is why it has been
excluded since round 400.)

"Attribution goes from 26.7 % to 94.0 % of every swapped byte in the window"
is the sentence this round could have published. **It would have been the
worst result in this track's history**, and the rest of this file is why.

---

## 2. The number is a trap, and which null you pick decides its sign

A population "names" a bucket by landing in it. 1401 extra fires over a
991-bucket grid will name a great many buckets whatever they are. So coverage
is evidence only against a null that holds the population's **size and shape**
fixed — and the two obvious nulls give **opposite answers on this data**:

| null | what it holds fixed | scopes' expected coverage | verdict on the observed 29/52 |
|---|---|---|---|
| uniform placement | count only | **39.5 / 52** | *below* chance, p = 1.000 |
| **circular shift** | count, cadence, bursts, every inter-arrival gap | **6.7 / 52** | ~4.3x chance, p ≤ 0.0005 |

The uniform null is the wrong one and it is wrong in the direction that kills
real findings: these fires arrive in bursts (53 bursts separated by >30 min,
the largest 517 sessions in 486 minutes), so a uniform draw of the same size
touches far more DISTINCT buckets than the real population ever could. It
expects more coverage than was observed and grades a 4x effect as sub-chance.

**The circular-shift null** rigidly translates the whole fire train by one
random offset and wraps it inside the pooled window. Count, cadence, burst
structure and spacing survive untouched; only alignment with the buckets is
destroyed. That is the null the question actually asks for: *do these events
land where the cost is, or merely land often?*

Measured, 2000 draws, on the live capture:

| population | fires | observed | null mean | null 5–95 % | p |
|---|---|---|---|---|---|
| published services | 647 | 19 | 8.37 | 4..13 | 0.0005 |
| round 436 complete | 687 | 19 | 8.37 | 4..13 | 0.0005 |
| services + scopes | 2088 | 44 | 13.41 | 8..20 | <0.0005 |
| **scopes only** | 1401 | **29** | **6.70** | 2..12 | **<0.0005** |
| engine events | 242 | 18 | 2.11 | 0..5 | 0.0010 |

So the invisible population is a **better** predictor of costly swap than the
entire published one — 29 buckets against a null of 6.7, versus 19 against 8.4.
Whole-day shifts (which preserve time-of-day cadence *exactly*, so every
housekeeping timer stays on its calendar slot) give 3..10 for scopes against
the observed 29: the alignment is not with the clock, it is with the buckets.

### The fast path had to be checked against the instrument, and that caught two bugs

2000 draws x 10 day-tables x 3093 fires is not affordable through
`cost_ledger`, so `BucketMap` precomputes second → costly-bucket. It is built
**by calling `cost_ledger`** — one synthetic fire per second per day, answers
read off its entries — and ships `verify()`, which compares the table with the
real ledger on every population.

The first draft reimplemented the placement rule instead, and `verify()` caught
two independent divergences before any null was reported:

* a mishandled post-restart row, which has no defined cost and must not be
  counted as a bucket at all;
* **`LEDGER_EXCLUDE_UNITS` not applied on the map path** — which took the
  published population's observed coverage from 19 to **50** of 52, because
  `sysstat-collect` fires into every bucket by construction.

Either one would have produced a confident, wrong null. **A null on a
paraphrase of your instrument is not a null on your instrument.**
`population --verify` is that check as a command and exits 1 on divergence.

---

## 3. Round 436's item 6, answered in both halves

Item 6 asked two things. Both are now measured.

### (a) "14 costly buckets / 4.25 GiB named by no FIRE"

Re-derived exactly: 52 costly, minus 19 named by services, minus 23 named by
engine events at any of the shifts {0, 300, 600} s, leaves **14 buckets holding
4.25 GiB**, largest `2026-08-23 21:20:02` at 2.34 GiB.

**Session scopes name 7 of the 14** — including the largest. Against the shift
null restricted to those 14 buckets: null mean **1.79**, 5–95 % `0..4`,
**p = 0.002**. Half of the record's residual "unexplained" cost is not
unexplained; it is explained by a unit kind no instrument in this tree had ever
read.

### (b) "how many of the other 13 sit inside an OOM or restart window?"

Round 436 asked this to guard against calling the 13 unexplained when the
largest was known to be an OOM run-up. The journal holds 4 OOM lines (3
episodes: 08-23 21:28:09Z, 08-24 10:34:11Z, 08-25 00:37:03Z), 3
`Scheduled restart job` and 1 `Failed with result` — 8 marks, 6 distinct
instants.

**The answer is NONE.** At ±30 min or ±60 min around any of those 8 marks,
**0 of the other 13** sit in a window; only `2026-08-23 21:20:02`, the one
round 436 already knew about, does. Base rate across all 52 costly buckets is
7/52 (13 %). The OOM hypothesis for the residual is dead, and it dies cleanly
rather than being quietly dropped.

The full table, one row per bucket:

| bucket | scope-named | in an E-round window | OOM/restart ±30 m |
|---|---|---|---|
| 2026-08-23 18:30:03 | · | *untestable* | · |
| **2026-08-23 21:20:02** (2.34 GiB) | **Y** | *untestable* | **Y** |
| 2026-08-25 22:20:08 | · | · | · |
| 2026-08-25 23:40:21 | · | · | · |
| 2026-08-25 23:50:08 | · | · | · |
| 2026-08-26 01:00:21 | **Y** | · | · |
| 2026-08-26 02:40:20 | · | **Y** | · |
| 2026-08-28 14:00:04 | **Y** | **Y** | · |
| 2026-08-28 18:10:02 | **Y** | **Y** | · |
| 2026-08-28 19:40:04 | · | · | · |
| 2026-08-28 21:40:04 | · | **Y** | · |
| 2026-08-30 15:10:03 | **Y** | **Y** | · |
| 2026-08-31 13:30:05 | **Y** | **Y** | · |
| 2026-08-31 13:50:05 | **Y** | **Y** | · |

That third column is the rest of this file.

---

## 4. The population is this program's own footprints

The 1401 scopes are all one family — `session-N.scope`, every one of them
"Session N of User jab". They are ssh logins. Three independent measurements
say whose:

**Lifetime.** `session_scope_sessions`: median session **1 second**, 1253 of
1396 (**89.8 %**) at or under 5 s. That is `ssh host 'cmd'`, not a person's
shell. The record still contains genuinely long sessions (max 349 816 s ≈ 4
days), so the median is a property of the population, not of the parser.

**Coincidence with this program's own log.** `state/nuc-reachability-log.jsonl`
records one row per E round with the instant its probe ran. 35 of its rows fall
inside the journal's window with `ssh_reachable true`. **33 of those 35 have a
session-scope start within 120 s, and 18 within ±1 second.** The two remaining
miss by 416 s and 515 s and are reported, not dropped.

```
round 352 | 2026-08-30T02:20:54Z | session start 02:20:55Z | +1s
round 358 | 2026-08-30T05:47:43Z | session start 05:47:44Z | +1s
round 364 | 2026-08-30T10:01:01Z | session start 10:01:02Z | +1s
round 376 | 2026-08-30T19:53:44Z | session start 19:53:44Z | +0s
```

Two files, written by different programs, on different hosts, ten days apart —
**recording the same events.**

**Concentration.** `observer_confounding` asks whether the costly buckets the
scopes name sit where this program was working. A round is bounded by the
driver's `DRIVER_ROUND_TIMEOUT_S` (3300 s) and its probe is the first thing it
does, so a login caused by round N lands in [probe − 300 s, probe + 3300 s]. On
the 33 costly buckets the log's dates cover:

|  | in an E-round window | outside |
|---|---|---|
| scope-named | **13** | 1 |
| not scope-named | 5 | 14 |

**Fisher exact two-sided p = 2.5 × 10⁻⁴.**

So: the strongest single "explanation" of costly swap on this box over ten
days is **this research program's own measurement traffic**, and the widening
that would have taken attribution to 94 % of swapped bytes gets there by
attributing them to the observer.

### The direction of the arrow, argued rather than assumed

Two readings fit the correlation. (i) The logins and the work behind them
*cost* the memory — an E round scps a 1.0 MB pid-1 journal, a 1.3 MB
`sar-all`, tars the binary sysstat, and in up-round history has driven the
engine. (ii) The program preferentially probes when the box is already busy.

**(ii) is not available here.** The driver's schedule is a fixed rotation on a
different host; it has no reading of the NUC's memory state and cannot select
for it. That does not make (i) proven — a 1-second login does not by itself
move 2.34 GiB — but it does mean the correlation cannot be explained by the
observer choosing its moments. The honest statement is that **the program's
round windows and the box's costly swap buckets coincide far beyond chance,
and the program is the only one of the two that could be scheduling the
other.**

### What follows, and what does not

`LEDGER_EXCLUDE_UNITS` already carries the precedent: `sysstat-collect` is
excluded because it **writes** the bucket. A session scope needs excluding for
a *different* reason — it is the observer, not the instrument — and a different
reason has to be measured before it is applied. That is what this round did,
and it is why `parse_unit_starts_any_kind` **defaults to `("service",)`**: the
widening is available, correct, and off, and no published number moves unless
somebody passes the wider argument on purpose.

Reporting **untestable as untestable** matters here. 19 of the 52 costly
buckets are on 08-23/08-24 and the reachability log's first row is 08-25.
Scoring those as "not in a round window" would have manufactured 19 negatives
out of a file that did not exist yet, and would have made the Fisher table look
*better*. They are reported as `n_untestable_before_the_log_existed`.

---

## 5. Tests

`nuc/tests/test_perturbation.py` gains **31 tests**; `nuc/tests` goes
**915 -> 946, all green** (174.4 s). The round-466 block alone runs in 37.9 s
after the `BucketMap` cache below; it took 208.1 s before it.

One `BucketMap` costs ~11 s (86 400 synthetic fires per day through the real
`cost_ledger`, ten days) and is a pure function of the two fixture texts, so
the block builds it once — except in
`test_the_bucket_map_agrees_with_cost_ledger_on_every_population`, which builds
a fresh one because it is the test *of* it.

Falsifiers, each reverting one decision:

| falsifier | reds (first run) | reds (after the fix below) |
|---|---|---|
| F1 no-double-count key ignores the unit KIND | **0** | 1 |
| F2 `BucketMap` does not apply `LEDGER_EXCLUDE_UNITS` | 11 | — |
| F3 shift null replaced by independent uniform draws | 4 | — |
| F4 dates before the log existed counted as negatives | 1 | — |
| F5 `population_coverage` publishes coverage with no null | 1 | — |
| F6 the widening becomes the DEFAULT | 1 | — |
| F7 identity draws no longer counted | **0** | 1 |

**Two of the seven came back 0 red, and 0 red is a finding about the test
suite, not a pass.** Both are now closed, and the closures are different
shapes:

* **F1** — `test_the_widened_parser_keeps_the_no_double_count_rule` *claimed*
  to pin the dedup key, but no fixture in the suite collided a unit NAME across
  two KINDS, so the key's second element was never exercised. Fixed with a
  synthetic fixture (`_KIND_COLLISION`) where `apply.service` announces itself
  and `apply.scope` does not: drop the kind and the scope vanishes. Synthetic
  on purpose — nothing in the real journal collides this way *today*, which is
  exactly why a test has to hold the door.

* **F7** — the identity branch was **unreachable by any test**. Offset 0 is
  drawn about once in a million from an 864 000-second span, so
  `n_identity_draws` was a field no random-draw test could ever exercise.
  Rather than delete the field or fake a seed, `shift_null` gained a
  `shifts=` argument taking explicit offsets, which makes the branch reachable
  (`shifts=[0]` must report `n_identity_draws == 1`, and `shifts=[span]` must
  recognise a full wrap as the same shift) and doubles as the
  deterministic-reproduction hook a published p-value ought to have. **A
  falsifier that goes 0 red because the code path cannot be reached is a
  design problem, not a testing one.**

### The round's own corpus debt, found and paid

`skills/run_checks_fast.sh` went to **2 errors** on this tree, both one thing:
`carryforward` K001, "round 466 banked predictions and
`state/prediction-bank-ledger.json` has no entry for it — nobody can tell
whether D-013's second half was ever done". Banking and scoring in the round
file is not the whole of rule D-013; the ledger is what makes the scoring
findable. Entry added, then K002 fired in turn because the cited sentence was
in the bank file and not in this one — so §7's headline is now here, where the
checker can re-derive it. **0 errors, 986 passed** afterwards. The one
remaining `unscored` bank is round **132**'s and is not this round's.

---

## 6. Skill (CLAUDE.md rule 5)

`skills/null-must-preserve-the-shape` — *a wider net catches more fish; that is
not evidence about the sea.* When widening a population makes coverage jump,
the jump is evidence only against a null that holds the population's size AND
internal structure fixed, and the uniform null can invert the sign of the
answer.

Distinct from its neighbours, and the description says so: `cause-needs-a-
denominator` is about a suspect chosen for being the only name in a window;
`matcher-defines-the-population` is about how the population got chosen at all;
`recorder-in-the-record` is about the **sampler** appearing in its own data.
This one is about the **null**, and about the analyst — not the sampler —
arriving inside the population through a widening.

---

## 7. Predictions (D-013)

Banked in `nuc/predictions-e-round466.md` before any instrument ran, with §0
recording the three exploratory reads that preceded the file so nothing could
be retro-fitted, and with two items declared NO BASIS rather than guessed.

**11 HIT, 2 PARTIAL, 1 MISS of 14, plus two declared no-basis items
resolved.** The full table is in the bank file's own SCORING section.

**The MISS is P5**, and it is instructive. I predicted the record's largest
unexplained bucket would stay unnamed, reasoning that a *run-up* cannot be
named by the scope of a process created after it. That is sound for **one**
session. The record holds **sixty** in that 91-minute burst, and one of them
lands inside the bucket. **A rate-shaped population cannot be predicted against
as though it were a single event** — count the X's before predicting that X
cannot coincide with Y.

**P9 is a PARTIAL that lost its side.** I predicted this program's logins were
a minority of the journal's sessions; 51.3 % fall within ±45 min of a probe
row, and since the log holds one row per ROUND against dozens of logins per
round, that is a floor. I picked a side and the side was wrong; flagging it LOW
is why the round went and measured burst structure and lifetimes instead of
asserting it.

**P14 is the other PARTIAL, and it is a bracket error in prose while
`precision-audit` was green.** "The confirmed streak passes 30 h" was
arithmetic on two timestamps already read — but that difference is the *upper*
bracket, computed from `LastSeen`, while the confirmed streak runs from round
436's own later check. Confirmed is **29h50m36s, 9m24s short**. Round 460 built
an instrument for exactly this failure mode; the instrument does not read the
round file. **A round that ships bracket discipline should read its own
bracket before quoting a number from it.**

**Both no-basis items resolved**, and P11's answer is the one worth keeping:
102 `.timer`/`.socket`/`.path` fires add **exactly zero** buckets and zero
bytes. A guess there would almost certainly have produced "a little", and a
wrong small number looks like a result.

---

## 8. For the next E round

See the missions addendum. In short: the widening is built, correct, tested and
**off**; whether to turn it on, and whether a session scope should join
`LEDGER_EXCLUDE_UNITS`, is a decision this round deliberately did not take
alone.
