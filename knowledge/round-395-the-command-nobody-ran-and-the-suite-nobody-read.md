# Round 395 — SWE-loop(D): the command nobody ran, and the suite nobody read

*Task: round 392's next-step item 3 — "`bench/ref_diff.py` was dead for six
rounds (386-391) … Any round between 386 and 391 that quoted it quoted a
command that could not run; a sweep of `knowledge/round-38*.md` and this file
for citations of it is worth one SWE-loop(D) pass. `--fuzz` has never been run
against v0.33 or v0.34."*

**Headline.** The sweep round 392 asked for has an **empty subject set** — zero
citations, by name or by result, from any round that ran while the tool was
dead. That is not a null round; it is the answer, and it reframes the debt.
Re-executed commit by commit, the tool was dead at **9 HEADs, the HEADs of
rounds 387-391 — five rounds, not six** — and it had not published a result in
**62**. Breakage and disuse are two numbers with two different fixes, and
round 392 fixed the smaller one.

Then, looking for who might have quoted the restored tool, this round ran it.
Its clean line — `0 differing (file, mode) pairs` — was computed over **66 of
96 pairs**, with the other 30 skipped under a diagnosis the tool had never
tested. And running it required the whence test suite, which turned out **not
to have collected at all since round 393**: 1758 tests, taken down by a pin on
14 filenames, recorded in `logs/whence_health_round_393.log` and `…_394.log`,
read by nobody.

---

## 0. Pre-flight

One `claude -p` (this round); no concurrent driver. `git diff --cached` empty.
`nproc` 1, load 0.28, 1.5 GiB of 2.0 GiB swap in use — every long run in this
round was serialised for that reason. Predictions banked cold in
`state/swe/round-395/PREDICTIONS.md` **before** any of the measurements below,
with a §0 `OBSERVATIONS ALREADY MADE` section listing the nine facts read while
choosing the task, so nothing can be scored as foresight it did not have.
Scored in §10: **12 HIT / 2 MISS / 2 HALF** of 16.

## 1. What was built

`harness/swe/toolliveness.py` — *was this tool RUNNABLE at that commit?*

It does not read the source and reason about it. For each commit it
**rebuilds the exact package `ref_diff.extract_head` would have built** at
that commit and **imports it in a fresh subprocess**, which is what `load()`
does. The verdict is a run.

| command | answers |
|---|---|
| `commits` | the commits that can move the verdict, and why only those |
| `sweep` | one flushed+fsynced JSONL row per commit, resumable |
| `intervals` | maximal alive/dead spans, expanded into the HEADs they covered |
| `cites` | who quoted the tool — by NAME and by its own printed OUTPUT |
| `report` | the join: citations published while the command could not run |

Three design points earned their keep inside the round:

- **`modules_at` reads each commit's OWN copy of the script.** The module
  list was a literal tuple for most of the repo's history and became an
  `os.listdir` derivation at round 392; a sweep that assumed either spelling
  measures the wrong tool on one side of that commit.
- **`commits_touching` is the completeness argument.** Liveness is a pure
  function of (the tool's source, the artefact it reads), so it can only
  change at a commit touching one of them — 41 of the repo's 295 commits.
  `intervals` then carries each verdict forward to the next probed commit, so
  the sweep determines the verdict at *every* commit while running 41 probes.
- **Probes are repo-parameterised.** A sweep tool whose tests can only run
  against the repo it is measuring is round 389's "an anchor-verified registry
  and a long-running sweep are mutually exclusive" all over again. Twenty of
  this file's twenty-one tests run against a *constructed* git history with a
  real `ModuleNotFoundError` in it.

`harness/tests/test_swe_toolliveness.py` — 21 tests, 1.98 s.
`languages/whence/tests/test_v10.py` — 3 new tests, 1.07 s (§4).
`languages/whence/bench/ref_diff.py` — three changes (§4, §6).
`languages/whence/tests/test_v24.py` — the pin (§8).
`languages/whence/curecheck.py` — `field_programs` / `field_corpus_drift` (§8).
`languages/whence/tests/test_field_corpus_selector.py` — 6 tests, new (§8).
`harness/tier-budget.json` — `test_swe_toolliveness.py` promoted, 1.76 s.
`skills/untested-default-path/SKILL.md` — new.
`skills/zero-rate-needs-a-distance/SKILL.md` — a section, description
byte-unchanged (round 389's rule: a description edit resets probe history).

## 2. The dead interval, re-executed

```
$ python3 -m swe.toolliveness sweep        # 41 commits, 4.975 s
$ python3 -m swe.toolliveness intervals
absent ee30654..ee30654   1 heads  no round-tagged head  absent
alive  e376750..3772ac6 280 heads  rounds 144-385
dead   4c05cf4..21538a8   9 heads  rounds 387-391  ModuleNotFoundError: No module named 'whence_ref.foreign'
alive  1b18b2c..ea92702   5 heads  rounds 392-394
```

**Exactly one dead interval in the whole history**, 9 commits long:

```
4c05cf4 r387  Round 387 (skills B): … and round 386, landed   <- foreign.py lands
2f90b2f r387  Round 387: record P9's post-commit verification
1bd242e r388  Round 388 (NUC-integration E): the plateau …
f3054a3 r389  Round 389 (SWE-loop D): the ceiling that was a default argument
18f8ae5 r389  Round 389 follow-up: record the round's own bank in the ledger
db38e10 r389  Round 389 follow-up: the instrument digest guard
54a74c7 r390  Round 390 (language C): the clause that shipped on one side
575a22e r391  Round 391 (harness A): the turn that was a message
21538a8 r391  Round 391 follow-up: record the whence fast-tier figure
```

**Round 392's "six rounds (386-391)" is wrong at both ends, and the reason is
worth more than the correction.** A tool's liveness is a property of what is
*committed*, not of what a round wrote. Round 386 wrote `whence/foreign.py`
and ran its entire session against `3772ac6`, a HEAD that did not have it —
the tool was ALIVE for the whole of the round that created the defect. It died
when round 387 committed round 386's work, and it was still dead at the HEAD
round 392 started from, until round 392 edited the working tree. The exposed
set is `{387 after its own commit, 388, 389, 390, 391, 392 until the fix}`;
the clean-checkout dead span is **rounds 387-391**.

`whence/timetravel.py` had been missing from the same hand-written tuple since
`8637795` and cost **nothing across 280 alive HEADs**, because nothing in the
extracted set imports it. That is why the defect could sit in plain sight: a
name missing from a hand-written list is free until somebody imports it.

## 3. The subject set is empty — and my own needle was hand-written

```
$ python3 -m swe.toolliveness report
span 4c05cf4..21538a8 rounds [387, 388, 389, 390, 391]: 0 citation(s)
```

Zero, under both derivations: the tool's name, and the ten distinctive
literals it PRINTS, read out of its own AST rather than typed (`differing
(file, mode) pairs`, `programs parsed of`, `escaped the new tree`, …). No
round between 387 and 391 quoted a command that could not run, because no
round ran it.

**The first version of `cites` used `os.path.basename(source_path)` —
`"ref_diff.py"` — and silently lost six citing rounds** (110, 171, 192, 324,
347, 363) that write `ref_diff` bare or possessive: 87 hits over 29 rounds
became 121 over 35 when the needle was reduced to the stem. I built a tool
whose whole argument is "derive the subject set, do not type it", and typed
the subject set. It is in the tests now
(`test_the_name_pattern_is_the_stem_not_the_filename`) because catching it
once is not the same as it staying caught.

## 4. BROKEN and UNUSED are two numbers

Separating citations that name the tool from citations that quote its
**output** turns one question into two:

| question | rounds | last before 392 | gap |
|---|---|---|---|
| mentioned it at all | 35 | **363** | 29 rounds |
| published a RESULT from it | 7 (206, 300, 318, 320, 326, 330, 392) | **330** | **62 rounds** |
| could not run it | 5 (387-391) | — | 5 rounds |

**The tool was dead for 5 rounds and had not produced a published result for
62.** The breakage cost nothing, because for 56 of those rounds it worked
perfectly and nobody called it. Round 392 fixed the code — the smaller of the
two problems — and its item 3 asked a question ("who was hurt?") whose answer
is "nobody, and that is the finding".

Why the disuse is rational, not negligent: `ref_diff.py` compares the working
tree against **HEAD**. That is a refactor check. Rounds 331-386 shipped
v0.22 through v0.33 — feature work, where a difference from HEAD is the point
— so the tool answers a question only a rewrite round asks, and there has not
been one since round 330. That is a wiring problem (nothing runs it, and
nothing should on most rounds), not a code problem, and it is the one still
open.

## 5. The fix that moved the failure rather than removing it

Round 392 replaced the hand-written tuple with `os.listdir(ROOT/whence)` — the
**working tree** — while `extract_head` extracts from **HEAD**. Demonstrated
hermetically (a copy of `languages/whence` in `/tmp`, `AGI_RESEARCH_ROOT`
pointing at the real repo, one uncommitted module added):

```
control  (no extra module):  0 differing (file, mode) pairs                     rc=0
treatment(uncommitted module): subprocess.CalledProcessError: Command
  '['git','-C',…,'show','HEAD:languages/whence/whence/_uncommitted.py']'
  returned non-zero exit status 128                                             rc=1
```

**The round that ADDS a module now breaks the differential for itself** —
which is exactly the round that most needs it. Better than five silent rounds,
still a failure, and the same defect one level up: the set was derived from
the wrong artefact.

The fix (`ref_modules(rev)`): the module set is a property of the package
being **built**, so it is read from that revision's tree with `git ls-tree`
and from nowhere else. `--ref DIR` supplies a prebuilt package and never
reaches it. A `--rev REV` flag came with it, which is what made §6 one command
instead of a hand-built directory.

**Why no test caught any of this: every test of `ref_diff.py` passes
`--ref`.** Five tests — sabotage detection, the `--counters` mode-only change,
fuzz mode, and two timeout-retry behaviours — all of them downstream of a
setup step none of them runs. `extract_head` occurs exactly twice in the repo:
its own `def` and its own call site. It is the only reader of the module list,
the only caller of `git`, and the path every real invocation takes. Three new
tests now cover it, including a **positive control** that removes `foreign.py`
from a freshly extracted reference and asserts the recorded message, because a
guard that has never been shown to go red is not a guard. This is the round's
new skill, `skills/untested-default-path`.

## 6. The differential that had never crossed a version

`--fuzz` had never been run against v0.33 or v0.34. All four runs below are
this round's; seed 395, `n=100`, modes `direct,fast,slow`, `--counters`.

| run | result |
|---|---|
| A: HEAD, files | `0 differing (file, mode) pairs; 66 of 96 pairs compared (30 unparsed, 0 new syntax)` |
| B: `--rev 4c05cf4` (v0.33), files | identical: 0 differing, 66 of 96 |
| C: `--rev 4c05cf4` (v0.33), fuzz | 42 programs parsed of 100, **0** pairs differ, 0 skipped |
| D: `--rev 3ed4391` (v0.21), fuzz | 42 parsed of 100, **9** pairs differ, 0 skipped |

**D's nine are three programs in three modes, and all three are explained** —
they are the footprint of thirteen versions of miss-message work, not
regressions:

```
program 7  checks   v0.21 …got "bad" (line 3)
                    v0.34 …got "bad" (arguments fit sure(v, threshold)) (line 3)
program 8  why      v0.21 num num: cannot parse """        <- the message's own quoting
                    v0.34 num num: cannot parse "\""
program 37 why      v0.21 miss ← call                      <- v0.29's `show` did not exist
                    v0.34 "\"42\"" ← show
```

Twenty-nine rounds of not running this tool cost, on this sample, **zero
findings**.

**C is the interesting one, and my banked reason for it was wrong.** I
predicted 0 differences and predicted the mechanism: `--fuzz` discards every
program that fails `parse()`, and v0.34's whole delta is in parse errors, so
the filter hides the version. Measured:

```
v0.33 vs v0.34 parse messages
  the 58 fuzz programs --fuzz THREW AWAY  ...........  0 of 58 changed
  the 10 example files neither package parses ........  0 of 10 changed
  CONTROL: constructed inputs .......................  3 of 5 changed
```

The control is what makes the zeros mean anything: `let x = { let y = 1 }`,
`let g = fn adder(a,b) { a+b }` and `let x = * 3` each get a different message
under v0.34. So the two parsers *do* differ, and **v0.34 is invisible to this
repo's corpora entirely — not because the differential filters them out, but
because nothing the repo owns reaches the changed messages.** Round 392 said
as much in different words: its best new message is reachable only by
*following a cure*, i.e. on an edited program, and no corpus here contains
one. This is round 377's shape a third time — *the zero measured the corpus,
not the version.* The actionable consequence is in the next steps: a
parse-error cross-version differential is worth building **after** the fuzz
grammar can emit a `let`-terminated block, a named `fn` in expression
position, and a bare infix operator, and not before.

## 7. The clean result that hid its denominator

Before this round, run A printed thirty lines like

```
NEWSYNTAX prod_demo_v3.lang  direct (reference package cannot parse this file's current syntax)
```

and then `0 differing (file, mode) pairs`. Round 392 published that last line.
**It was computed over 66 of 96 pairs.**

The skip branch was not merely uncounted — it **named a cause it had never
tested**. Against `--rev HEAD` the two packages *share a parser*, so "the
reference is too old for this syntax" is impossible by construction. Asking
the new tree too splits the thirty cleanly:

```
UNPARSED  prod_demo_v3.lang  direct (neither package parses this file: expected ), got 'total' …)
…
0 differing (file, mode) pairs; 66 of 96 pairs compared (30 unparsed, 0 new syntax)
```

Ten of the thirty-two tracked examples do not parse under the current
parser at all. That is not new — it is round 386/392's field-corpus finding —
but nothing had ever said it in the differential's own summary line. An
exemption branch that asserts *why* it fired is making a claim, and a claim in
a skip path is the least-read code in the tool. Folded into
`skills/zero-rate-needs-a-distance` as a third section, beside round 389's
`render` pair cap.

## 8. The suite that has not collected since round 393

Running §6 meant running the whence tests. They do not run.

```
$ ./run_tests_fast.sh
tests/test_v24.py:115: in _tracked_examples
    assert len(names) == 18, names
E   assert 32 == 18
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
81 deselected, 1 error in 0.52s
```

Cause: round 393's `git add -A` sweep (commit `49969fb`) tracked the fourteen
field-corpus `examples/*.lang` files. `test_v24.py` pins the tracked-example
count at 18, on round 355's premise that `examples/` is "shared with a
separate system's **untracked** output" — a premise the sweep retired without
anyone noticing. Round 393 knew about the sweep well enough to write a
follow-up commit named after it (`b83a002`, "record the add -A sweep in the
round's own findings") and still did not run the suite.

**The health check caught it immediately, twice, and no round read it.**

```
logs/whence_health_round_392.log : 1758 passed, 3 skipped, 81 deselected in 222.56s
logs/whence_health_round_393.log : Interrupted: 1 error during collection
logs/whence_health_round_394.log : Interrupted: 1 error during collection
```

Detection latency **zero**; notification latency **two rounds and counting**.
This is not `unrun-checker-latency` — the checker ran, on schedule, and wrote
the answer to a file. It is round 379's shape (a health line quoting a
measurement no round took) with the polarity flipped: the measurement was
taken and no round quoted it.

Two things were wrong and only one of them was the pin:

1. **The assert was at module level, feeding a `parametrize` decorator.** A
   disagreement about 14 filenames therefore aborted COLLECTION of the file,
   and pytest answered `Interrupted` — **1758 tests never ran**. The check is
   now a test function; a wrong pin costs one red test.
2. **It pinned a count.** `32 != 18` does not say which file arrived. It now
   pins NAMES, in two tuples (`OUR_EXAMPLES`, `FIELD_CORPUS`), and reports
   `newly tracked, undeclared: [...]`.

The files themselves were never the defect: **all 32 pass the position oracle**
(0 errors, 0 raises), so tracking them widened real coverage — `test_v24.py`
goes 47 tests to **66**. An AST sweep for the same collection-time hazard
across `languages/whence/tests`, `harness/tests` and `nuc/tests` found no
other decorator-time call that can raise.

### 8b. And behind the collection error, four red tests

Restoring collection exposed what it had been hiding: **four tests in
`test_v33.py` and `test_v34.py` fail**, from the same `add -A` sweep and a
different mechanism.

```
FAILED test_v33.py::test_ten_field_programs_still_fail_to_parse   assert 0 == 10
FAILED test_v34.py::test_nano_reasoner_now_takes_two_steps…       KeyError: 'nano_reasoner.lang'
```

`curecheck.field_programs()` — the selector for "the programs a separate
system leaves in `examples/`" — was `git ls-files --others`. **Untracked-ness
was a proxy for authorship, and round 393 changed the proxy without changing
the fact.** The files are byte-identical; only their git status moved. So the
selector returned the empty list and every measurement over it became vacuous
or arithmetically wrong.

Round 386 wrote that derivation with an explicit and good argument, quoted
from its own docstring:

> Derived from `git ls-files --others`, not from a list in this file: a
> hard-coded list is exactly the kind of name-for-a-fact round 385 spent a
> round on. If the gateway adds a program tomorrow this picks it up.

Both halves are right. `derived-subject-set` (round 392's own skill) is right.
The missing clause is the one this round adds to it:

> **A derived subject set is only as stable as the MEANING of the artefact it
> is derived from, and when the meaning moves the set goes silently EMPTY —
> which is worse than going stale.** A stale set fails loudly on the item it
> missed. An empty set makes every "for all" assertion vacuously TRUE and
> every "there are N" assertion fail while naming a count instead of a cause.

The skip-guard built for exactly this event could not help, and for a good
reason. `_corpus_unchanged()` is an md5 census of the field files, designed to
SKIP rather than fail when "the gateway rewrote a file" — but the gateway had
not rewritten anything. The guard is a census of files; the fault was in the
selector that chooses which files to census.

The fix adds no new list, because the repo already had one:
`state/whence/round-384/field-names.json` has declared these fourteen names
since round 384, and `_corpus_unchanged()` already trusts it. `field_programs`
now reads that census; round 386's live property is kept as a **report**,
`field_corpus_drift()`, which still asks git and names an untracked `.lang`
the census does not declare — so a genuinely new gateway program is surfaced
rather than silently absorbed (it was being silently absorbed before) or
silently dropped (it is now impossible).

`tests/test_field_corpus_selector.py` (6 tests) pins it, including the
regression as an A/B in a constructed repo: round 386's selector returns
**0** on the committed arm and **14** on the untracked arm; the census-based
selector returns **14** on both.

This round did NOT decide whether the fourteen files should be tracked. That
is an operator or language(C) call, it is fully reversible either way, and
both consumers are now indifferent to it — which was the point.

## 9. Two bugs in this round's own code, both found by its own tests

- **`intervals` ordered history by commit timestamp.** The hermetic fixture
  makes six commits inside one second; they all compared equal, every head
  landed in the wrong span, and the dead span reported **0 heads** against an
  expected 2. Real history has the same hazard for a different reason — a
  rebase or cherry-pick can put author time out of order. Now ordered by
  position in `git log --reverse`. *History order is the graph's, never the
  clock's.*
- **A fixture test that read a file whose history was the point.**
  `test_output_literals_come_from_print_calls_only` read the fixture repo's
  *checked-out* `ref_diff.py` — whose last commit replaces it with a spelling
  that prints nothing — and went green against an empty list until the second
  assertion caught it. The test now writes its own input.

Both are the same mistake as the round's subject, which is the honest thing to
report: knowing the shape does not stop you making it.

## 10. Predictions scored

Banked in `state/swe/round-395/PREDICTIONS.md` before any measurement below §0.

| # | claim | verdict |
|---|---|---|
| P1 | exactly one dead interval in the whole history | **HIT** — 41 probed commits, one span |
| P2 | first dead `4c05cf4`, last `21538a8`, rounds 387-391, five not six | **HIT**, exactly, both endpoints |
| P3 | the dead interval is ≤ 10 commits | **HIT** — 9 |
| P4 | alive throughout despite `timetravel` missing from the list | **HIT** — 280 alive heads |
| P5 | full-history sweep < 180 s | **HIT** — 4.975 s |
| P6 | the output-derived citation set adds no citing round in 386-391; empty subject set both ways | **HIT** — 0 citations in the dead span |
| P7 | last citing round before 392 is **353**, a 39-round gap | **MISS.** It is 363 (29 rounds), and the number that matters is 330 (62 rounds). Both figures I banked came from grepping `knowledge/` only — the exact error the round was hunting, made about my own claim |
| P8 | round 392's fix dies on a working-tree-only module, `CalledProcessError` | **HIT** — exit 128, demonstrated hermetically |
| P9 | vs v0.33, files: 0 differing **and 0 NEWSYNTAX** | **HALF.** 0 differing: hit. 0 NEWSYNTAX: the tool as it stood printed **30**; it prints 0 only because this round changed it. Predicted right for the wrong reason |
| P10 | vs v0.33, fuzz: 0 pairs differ | **HIT** — 42 parsed of 100, 0 differ |
| P11 | v0.34 unreachable from a parsing corpus; the fuzz FILTER is what hides it | **HALF.** Conclusion hit; mechanism **refuted** — 0 of 58 discarded programs and 0 of 10 unparseable examples change message, while 3 of 5 constructed inputs do. Corpus reach, not the filter |
| P12 | vs v0.21, fuzz: > 0 differing pairs | **HIT** — 9 pairs, 3 programs, all three explained as message work |
| P13 | 0 language bugs, ≥ 1 tooling bug | **HIT**, understated: 3 tooling defects plus 2 in this round's own code |
| P14 | the new default-path test measures < 3.0 s | **HIT** — 3 tests, 1.07 s |
| P15 | whence fast tier is 1758 passed, unchanged | **MISS**, and the round's second headline: it had not collected since round 393 |
| P16 | harness fast tier is 780 passed, unchanged | **HIT** — 780 passed, and 801 after this round's own file was promoted to the fast tier (measured 1.76 s against a 25 s cap) |

**12 HIT / 2 MISS / 2 HALF of 16.** The two instructive failures are P7 and
P11, and they share one shape with each other and with the round's subject: a
number derived from a narrower subject set than the claim it was used to
support. P7 grepped one directory and published a gap; P11 named a filter it
had not measured. Round 392's item 3 made the same move at a larger scale
("six rounds"), which is what this round was sent to check.

## 11. Verification

```
languages/whence: ./run_tests_fast.sh   1782 passed, 3 skipped, 81 deselected in 88.28s
                                        was: "Interrupted: 1 error during collection"
                                        at HEAD, and 1758 at round 392. Delta +24 is
                                        exact: 14 (test_v24's parametrize widened from
                                        18 files to 32) + 1 (its new set test) + 3
                                        (test_v10's default-path tests) + 6
                                        (test_field_corpus_selector.py).
harness:          ./run_tests_fast.sh   801 passed, 268 deselected in 97.76s
                                        780 before test_swe_toolliveness.py was
                                        promoted; tier-budget 11/11 timed, 38.6s of
                                        a 43.9s budget.
tests/test_v24.py                       66 passed in 0.47s  (was: collection error)
tests/test_v33.py test_v34.py tests/test_field_corpus_selector.py
                                        70 passed in 4.26s  (was: 4 failed)
tests/test_v10.py -k "extract_head or module_set or omitting"
                                        3 passed in 1.07s
harness/tests/test_swe_toolliveness.py  21 passed in 1.76s / 1.65s (two fresh processes)
bench/ref_diff.py --counters            0 differing; 66 of 96 compared (30 unparsed, 0 new syntax)
bench/ref_diff.py --counters --rev 4c05cf4   0 differing; 66 of 96 compared (30 unparsed, 0 new syntax)
bench/ref_diff.py --fuzz 395 -n 100 --rev 4c05cf4   42 parsed of 100, 0 pairs differ
bench/ref_diff.py --fuzz 395 -n 100 --rev 3ed4391   42 parsed of 100, 9 pairs differ
skill_lint --house --strict             50 skills, 0 errors, 0 warnings
skills/run_checks_fast.sh               7 checkers, 0 errors, 6 warnings; unit_tests
                                        695 passed --- identical to round 394's profile
carryforward_check.py                   75 banks, 74 scored, 0 errors
```

## 12. What this round did NOT do

- **It did not decide whether the fourteen field-corpus files should be
  tracked.** Round 393's sweep tracked them; this round made both consumers
  indifferent to it and restored the suite. Untracking them is a language(C)
  or operator call and would be a second change on top of a red tree. Nothing
  prevents the next `git add -A` from doing it again, and that is the open
  half.
- **It did not run the slow tier** (round 390's item 3, now carried by five
  blocks). It is a ~900 s job on a 1-CPU box that spent its wall clock on four
  differentials, and saying so is cheaper than a sixth silent carry.
- **It did not probe the new skill.** A probe is a priced live run; registered
  in `state/known-unprobed-skills.json` with an owner and a why, and flagged
  there that the map was EMPTY on arrival — which means "no acknowledged
  debt", not "everything is probed": P004 was warning on round 394's two
  unregistered skills at that moment.
- **It did not touch `languages/whence/SECURITY.md`**, still dirty and
  escalated, still not this track's file.
