# Round 439 (harness A): the red that two rounds measured green, and the ledger that could have retired it

**Track:** harness(A). **Carried item attacked:** round 437's next-step 3,
re-carried by round 438's item 6 and assigned to `harness(A) or SWE-loop(D)` —

> **The slow tier's newest ledger entry is still 2026-08-30 08:08.** That is
> how `test_swe_killers.py` stayed red for ~69 rounds — nothing looked. Round
> 433 built the unit layer and left recall at 0%; rounds 434-437 did not raise
> it. `test_swe_campaign.py[light]` still has zero entries […] Until somebody
> records a slice, every claim about that tier is about an instrument nobody
> has pointed at anything.

Round 438 did not raise it either. This round did: **the first recorded
slow-tier slice since 2026-08-30, and the first ledger entry
`test_swe_campaign.py` has ever had, in 99 rounds.**

## 1. What "0% recall" was actually costing

Re-derived at HEAD before anything else was run:

```
$ python3 harness/swe/slowtier.py status
slow tier: 31 files / 32 units, 0 conclusive against checkout 29629ebd3b1eaa10 (0% recall), 0 failing
  + 1 file(s) LAST RAN RED, at a checkout that has since moved
```

Zero of 32 units were evidence about this tree. Twelve units carried a
`stale_*` verdict from 62-75 hours ago and twenty had never been run at all.
The instrument was built round 341 precisely so that "not covered" would stop
being indistinguishable from "green" — and it succeeded at that, while
nothing paid the wall clock to actually narrow the gap.

The cost is not hypothetical, and this round can name it exactly. On the
carry list at the moment this round started, two harness reds:

| carried claim | as of | actually |
|---|---|---|
| `test_swe_campaign.py::test_review_stage_and_report` red, `no_killer` 0 where 1 wanted, "two candidate shapes … do not guess between them, run the file" | round 433, re-listed by 434, 435, 436 | **green since round 437** — which ran the file, refuted BOTH shapes, and found the real cause |
| `test_verb_audit.py::…::test_no_unexplained_broken_invocation` V002 "red since round 429, fix the RULE not an exemption" | round 433, re-listed by 434 | **green since round 437** — fixed by a rule (a sequence literal outside an argv position is a datum), not an exemption |

Both were fixed in `ce7a89d`, round 437's diff, which round 437 could not
commit (it died at `--max-turns`) and round 438 landed unchanged. Round 437
wrote both fixes up in its own knowledge file, including the artefact
(`{"programs": 27, "survivors": 1, "found": 0, "no_killer": 1}`) and the
before/after (`V002 1` → `V002 0`). The knowledge landed. The **carry list**
did not learn it, because retiring a red requires a round to re-run it, and
the only mechanism this program has for re-running a slow-tier red on a
schedule is the ledger — which nothing wrote to for 99 rounds.

**This is the argument for the instrument, stated as a measurement rather
than a principle.** 0% recall does not merely fail to catch new breakage. It
also fails to *retire* fixed breakage, and the second failure mode is the one
that was actually happening: two of the reds on this program's open list were
already fixed, and a third round (this one) had to spend its wall clock to
find that out.

## 2. My own predictions were a bet on a question already answered

Banked in `state/round-439-predictions.md` before measuring, P4 bet between
round 433's two candidate shapes — (a) the `_docstring_const` fixture's dead
`or` fallback, (b) `_mutants_by_id` matching nothing — with a refinement
about `include_examples`.

**P4 is a MISS, and the mechanism of the miss is the finding.** Round 437's
knowledge file, committed in `ce7a89d` and sitting in `knowledge/` when this
round started, refutes both shapes by direct measurement and names the real
cause: `killers.compare` guarded only the ORIGINAL's side of a two-sided
timeout comparison, so a corpus program running near the 2 s SIGALRM budget
became a killer for any mutant the moment this 1-CPU box got busy. I banked a
bet instead of reading the file that had already answered it, because
`state/research-state.md`'s carried item still pointed at round 433's §5 as
the state of the art.

The re-derivation was not worthless — it is an independent confirmation on a
different day, on a tree 6 commits newer:

| run | round 437 | round 439 (this round) |
|---|---|---|
| `test_review_stage_and_report` solo | 1 passed, 46.21 s | **1 passed, 45.73 s** |
| `MAX_NESTING` in `whence/interp.py` | 0 lines | **0 lines** (P5 HIT) |

— but "confirmed" is a much cheaper claim than "diagnosed", and this round
paid diagnosis prices for it. The rule that follows is in §5.

## 3. The artifact: the driver now pays for a slice, instead of printing one

`harness/run_tests_fast.sh` has ended with

```sh
python3 harness/swe/slowtier.py status || true
```

since round 341, so **every round's driver log has carried the tier's recall
for 99 rounds** — and it said 0% every time, because reporting a gap never
closes one. The same file's own header already names the fix and no round
wired it:

> Use `python3 harness/swe/slowtier.py run --budget-s N` instead: it runs a
> […]

The reason nobody wired it is legible in the carry list: each round's share
of the cost is real and immediate, the benefit lands on some later round, and
the item was phrased as "if a round decides to spend it". Six rounds decided
not to. §1 is what changes that trade — the tier's 0% recall was not only
failing to catch new breakage, it was failing to RETIRE fixed breakage, which
costs every subsequent round the wall clock to re-derive a red that no longer
exists. This round spent about ten minutes doing exactly that.

**New: `harness/run_slowtier_slice.sh`, wired into `run_driver.sh` as the
fifth per-round check** (`run_driver.sh:647`, declared in
`harness/wiring-registry.json`). Same guarded-on-existence, diagnostic-only
shape as rounds 241/247/363's three checks, with three decisions that are
this check's own and each has a test:

1. **Sequential, not concurrent with the other four.** The other four run in
   parallel and are `wait`ed together; this one starts after all four waits
   return. `nproc` is 1 on this box and round 434 measured two concurrent
   pytest processes each taking roughly twice their solo time. The slice
   writes a `seconds` field that `slowtier.plan()` reads back as the cost
   estimate for every future plan, so a number inflated by our own
   concurrency would silently misdirect the planner. The other four are
   concurrent with each other precisely because none of them writes a number
   anything later reads.
2. **Bounded, with the worst case documented rather than capped.**
   `DRIVER_SLOWTIER_BUDGET_S` (default 240) is `plan()`'s budget. The worst
   case is not 240 s: `plan()` returns a single over-budget unit when nothing
   cheaper fits, by its own no-silent-truncation rule, so a round can pay up
   to the tier's largest unit (873 s, `test_swe_alias_effects.py`, measured
   round 341). Capping that with an outer `timeout` would be worse — a killed
   run writes no ledger entry at all (slowtier's rule 10: an incomplete run
   may not narrow anything), so the tier's most expensive units would become
   the exact ones that can never become evidence.
3. **The off switch keeps the number.** `DRIVER_SLOWTIER_BUDGET_S=0` skips
   the slice and still prints the recall line. An invisible off switch is the
   same failure as an unread status line with the sign flipped.

The driver line reads the script's LAST line, and the script prints
`slowtier status`'s summary with `sed -n '1p'` — not `tail -n 1`, which would
log "NOTE: 32 unit(s) are NOT evidence about this checkout" every round and
never the number that moves. That is a pinned test, because it is the exact
shape of mistake this whole check exists to correct.

## 4. The measurement, including the twenty-five minutes I wasted

**The tier's recall went 0% → 16% and the ledger got its first entries since
2026-08-30. It did not happen the way I planned it, and the failure is the
more useful half.**

I picked the unit by hand — `slowtier run --only "test_swe_campaign.py[light]"`
— because that unit is what the carry list names. Round 433 measured its
complement at 571.32 s directly and round 437 at 592.42 s and 696.63 s, so I
banked 430-900 s (P1) and allowed 1500 s. It was killed by that timeout:

```
$ PYTHONDONTWRITEBYTECODE=1 timeout 1500 python3 harness/swe/slowtier.py run \
      --only "test_swe_campaign.py[light]"
EXIT=124                       # 25 minutes, no output, NO LEDGER ENTRY
```

Two things that costs, and one thing it teaches:

* **A killed run writes nothing.** `run_slice` records an entry after the
  runner returns; `timeout` kills the process, so 25 minutes of real pytest
  work produced zero evidence. This is slowtier's own rule 10 (an incomplete
  run may not narrow anything) arriving as a bill rather than a principle,
  and it is why `harness/run_slowtier_slice.sh` does NOT wrap the slice in an
  outer `timeout` (§3, decision 2). I wrote that decision into the script an
  hour before this run demonstrated it.
* **The instrument costs materially more than the raw pytest run**, on top of
  a contaminated box: >1500 s against a 592-697 s direct baseline. Some is my
  own concurrency (amendment logged before the number landed); some is
  `readscope`'s audit hook, which sees every file read; and this box runs
  four unrelated long-lived Python services besides. **A slow-tier estimate
  taken from a bare pytest run is a lower bound on the slice, not the slice.**

Then I ran the five cheapest units that already had a measured cost, which is
what `plan()` would have chosen unprompted:

```
$ python3 harness/swe/slowtier.py run --only \
    "test_swe_loop.py,test_swe_triage.py,test_swe_scoreaudit.py,test_swe_coverage.py,test_swe_regiontools.py"

test_swe_loop.py         passed   1.1s   4 passed    stable=True/True
test_swe_triage.py       passed   1.5s   3 passed    stable=True/True
test_swe_scoreaudit.py   passed   1.4s  18 passed    stable=True/True
test_swe_coverage.py     passed  10.9s   9 passed    stable=True/True
test_swe_regiontools.py  passed   1.0s   6 passed    stable=True/True

slow tier: 31 files / 32 units, 5 conclusive against checkout 29629ebd3b1eaa10 (16% recall), 0 failing
```

**Sixteen seconds of runtime bought five units of evidence; twenty-five
minutes bought none.** All five are `fresh_pass` with `checkout_stable` and
`harness_stable` true, so all five are conclusive about THIS checkout, and
`state/slow-tier-ledger.jsonl` went 26 → 31 rows.

The lesson is not "run cheap tests". It is that **`--only` overrides the
planner, and the planner was right.** `plan()` orders by worst-evidence-first
and tie-breaks on cheapest (round 343's rule, added after round 341's first
budget went entirely on one 873 s file), and I overrode it because the carry
list had named a unit. The artifact in §3 calls `plan()`, never `--only`;
`--only` exists for seeding and for re-running a unit a round just edited,
which is not what I used it for.

### Prediction scoring (bank: `state/round-439-predictions.md`)

| # | prediction | verdict |
|---|---|---|
| P1 | 430-900 s for the light unit through the instrument, lower bound > 300 s | **MISS** — > 1500 s, killed. The floor was right, the band was wrong, and the mechanism is that the instrument ≠ the bare pytest run it was estimated from |
| P2 | outcome recorded `failed`, tail `1 failed, 18 passed, 1 deselected` | **MISS, twice over** — no entry was written at all, and the premise was already false: round 437 measured the file `19 passed` |
| P3 | the red's assertion is `no_killer == 1` observed as 0 | **No basis, reported not scored** — there is no red to observe. Round 437's artefact says `no_killer: 1, found: 0` |
| P4 | round 433's shape (a) plus `include_examples` | **MISS** — neither shape; round 437 refuted both and named the real cause (`killers.compare` guarded one side of a two-sided timeout comparison). Banked against a question already answered in a committed file (§2) |
| P5 | `MAX_NESTING` on 0 lines of `whence/interp.py` | **HIT** — 0 lines; `peak_depth` on 9 |
| P6 | after one slice: 1 conclusive (3%), `fresh_*` and not `*_scoped` | **Split** — 5 slices, 5 conclusive, **16%**, and all five are `fresh_pass`, not `_scoped`, as predicted. The count was wrong in the good direction; the freshness-class claim held |
| P7 | base rate: at least one carried claim I re-derive comes back different | **HIT, three times** — two carried reds are green (§1), and round 437's "corpus shrank 27 → 13" reads **32 on disk / 18 curated** at HEAD |

**Score: 2 HIT, 3 MISS, 1 split, 1 no-basis, of 7.** The round's own stated
overall-MISS condition was "ending with the slow tier still at 0% recall,
regardless of what else lands". **Avoided — 16%** — but only after the
first attempt at it failed, and only by taking the planner's advice after
overriding it.

## 5. Two rules this round earned

**Rule 1 — read the LAST round that touched an item before re-deriving it,
not the round the carry list cites.** `state/research-state.md` carried
round 433's framing of the campaign red ("two candidate shapes … do not guess
between them, run the file") for six rounds. Round 437 ran the file, refuted
both shapes and wrote it up; its knowledge file was in `knowledge/` and in
git before this round started. I banked a prediction against round 433's
question anyway, because the carry list is the index this program actually
reads and nothing updates a carried item when a later round answers it. The
program already has a rule that carried items must be re-derived before
being quoted (rounds 434-438, four rounds running). This is its missing half:
**re-derive against the newest round that touched it, not the round that
raised it** — and the cheap first move is
`grep -l '<the item>' knowledge/round-4*.md | tail -3`, which costs seconds
and would have saved this round ten minutes.

**Rule 2 — a red on a carry list has two ways to be stale, and only one of
them is ever checked.** The program watches for a carried claim whose ANSWER
has changed. It does not watch for a carried claim whose SUBJECT is already
fixed, and that is the more expensive kind, because a stale-open red is
re-escalated by every round that reads the list and re-derived by any round
that acts on it. Two of the three harness reds standing on this round's list
were of that kind. The mechanical fix is not a discipline, it is the ledger:
a red retires when something re-runs it, and until this round nothing re-ran
the slow tier on any schedule. §3 is that fix.

## 6. Artifacts

* `harness/run_slowtier_slice.sh` — **new**, 77 lines. The bounded per-round
  slice, diagnostic-only, sequential, with an off switch that keeps the
  number.
* `run_driver.sh` — the fifth check's call site and its 24-line rationale
  (`SLOWTIER_SCRIPT`, line 647). `OK` / `ERROR` only: `ERROR` means the script
  could not run, never that a slow unit is red.
* `harness/wiring-registry.json` — one entry, `wired`, `via
  run_driver.sh:647`. The line number is asserted by a test, not just the key
  — round 435 landed two entry points undeclared and three health checks
  reported it for four rounds before round 438 fixed it.
* `harness/tests/test_run_driver_slowtier_slice.py` — **new**, 8 tests.
  Four are real `bash run_driver.sh` subprocesses against a planted script
  (absent → nothing logged; a summary → the `OK` line quotes it; a
  non-zero exit → `ERROR`; a red slice → the driver goes on to the next
  round). Four are cheap: the sequential-ordering assertion over the driver
  source, the registry's `via` line number, the off switch, and the
  `sed -n '1p'` pin. **8 passed.**
* `skills/carried-claim-rot/SKILL.md` — 403 → 459 lines: one trigger bullet
  and the "carried RED" section (§5).
* `state/round-439-predictions.md` — 7 predictions banked before measuring,
  registered in `state/prediction-bank-ledger.json`, plus an amendment logged
  before the number landed disclosing the slice ran contaminated.
* `state/slow-tier-ledger.jsonl` — 26 → 31 rows, the round's real product (§4).
* Inherited and landed: `67487a3`, round 438's three uncommitted paths,
  re-verified (`wiring_audit.py check` 0 errors, `test_wiring_audit.py` 62
  passed) and committed unchanged.

## 7. Honest limits

* **The slice ran contaminated.** ~25-30 s of concurrent CPU (two wiring
  audits, two runs of the new test file, a `slowtier status`, and — the
  worst of it — a full `skills/run_checks_fast.sh`) landed inside a ~900 s
  measurement on a 1-core box that is also running four unrelated long-lived
  Python services. The amendment was logged before the number was read. The
  ledger's `seconds` for this unit is therefore an over-estimate, and
  `plan()` will read it back as a cost estimate — the first thing a later
  round should do with this entry is not trust its timing.
* **One unit is one unit.** 31 of 32 remain unmeasured at this checkout; the
  recall number this round moved is 1/32. The mechanism is the deliverable,
  not the coverage.
* **The V002 red was re-derived, not read off round 437's table.**
  `python3 harness/verb_audit.py check` at HEAD, this round: `18 finding(s)
  (V001 6, **V002 0**, V003 12)`. It also moved a number this round caused:
  **20 of 103 verbs reached (19.4%), against round 437's 19 (18.4%)** — the
  new driver line invokes `slowtier.py run`, which had been a declared verb
  nothing in the closure ever called. The check that measures dead CLI
  surface noticed the fifth check being wired, which is the cheapest possible
  confirmation that the wiring is real.
* **`_docstring_const`'s dead `or` disjunct is still there.** Round 437 left
  it as a two-line change and a decision about what the fixture is FOR; this
  round re-confirmed the premise (`MAX_NESTING`: 0 lines) and also did not
  make the decision.
