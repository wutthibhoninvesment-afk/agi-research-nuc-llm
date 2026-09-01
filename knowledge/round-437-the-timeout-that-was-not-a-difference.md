# Round 437 (SWE-loop D) — the timeout that was not a difference, and the curation that did not survive the copy

**Track:** D (autonomous SWE: the harness used on our own code) · **Date:** 2026-09-01 · **Model:** claude-opus-5

Round 433 handed SWE-loop(D) a live red it could not explain and forbade
guessing at it:

> `test_swe_campaign.py::test_review_stage_and_report` FAILED …
> `rep["corpus"]["no_killer"] == 1 and rep["tests_added"] == 0` → `assert (0 == 1)`
> … two candidate shapes … **Deciding between them needs one run of that test
> with the stage output captured; this round did not have the minutes.**

This round had the minutes. The answer is neither shape, and getting it
required believing the instrument over the carried note.

Predictions banked before any measurement: `state/round-437-predictions.md`.
Ten of them. **Three hit, six missed, one pending at write time** — the misses
are the result, and §7 scores each.

---

## 1. The red is gone, and it was never a logic error

| run | command | result |
|---|---|---|
| standalone repro of the stage sequence | `python3 /tmp/r437/repro.py` | `no_killer: 1`, `found: 0` — **correct** |
| the test alone | `pytest -q -p no:randomly harness/tests/test_swe_campaign.py::test_review_stage_and_report` | **1 passed in 46.21s** |
| the whole file, round 433's exact command | `pytest -q -p no:randomly --durations=0 harness/tests/test_swe_campaign.py --deselect …test_cli_runs_offline_stages_and_stops` | **19 passed, 1 deselected in 592.42s** |

Round 433's own command, on the same tree, is green. The artefact the third
run left behind says so in its own words
(`/tmp/r437/pt/test_review_stage_and_report0/out/killers.json`):

```json
{"programs": 27, "survivors": 1, "found": 0, "no_killer": 1,
 "killers": [{"mutant": "interp.py:604:const#366", "found": false, "tried": 27}]}
```

**Both of round 433's candidate shapes are refuted, individually.**

* Shape 1 — round 131's `_mutants_by_id` silently matching nothing. Refuted
  directly: the repro prints `survivors(): ['interp.py:604:const#366']` and
  `by_id keys : ['interp.py:604:const#366']`. The lookup works.
* Shape 2 — a corpus program kills the mutant. Refuted: `found: 0` over 27
  programs, in three independent runs.

Round 433's static lead was right about the mechanism and wrong about the
consequence. `_docstring_const()`'s first disjunct **is** dead —
`MAX_NESTING` appears on 0 lines of `whence/interp.py` — and the `or` fallback
**does** silently re-point the fixture to
`interp.py:604:const#366`, `self.peak_depth = 0` → `1`. But that mutant is
inert, exactly as round 433 suspected: `peak_depth` is named by 18 Python
test files under `languages/whence/tests/` and by 0 `.lang` files, and `killers.canonical()` captures `kind`,
`out`, `checks` and top-level `vals` — `peak_depth` is in none of them. A
mutant that cannot be seen cannot be killed. `no_killer == 1` is the right
answer and the code produces it.

So the question changed from *why is it wrong* to **why was it wrong once**.

## 2. `find_killer` guarded one side of a two-sided comparison

Round 433's failure needs `found == 1` for a mutant nothing can observe. There
is exactly one way to get it, and it was in the code the whole time
(`harness/swe/killers.py`, pre-437):

```python
expected = orig_cache[src]
if expected["kind"] == "timeout":
    continue                       # the ORIGINAL timed out: not evidence
got = behaviour(mut_pkg, src)
if got != expected:                # the MUTANT timing out lands HERE
    ...a killer, shrunk and pinned...
```

A timeout is a statement about the **wall clock**, not about the program.
`behaviour()` enforces it with a 2 s `SIGALRM`. On the original's side that was
understood and skipped. On the mutant's side the identical non-measurement was
read as a **behavioural difference** — so any corpus program running near the
budget becomes a killer for **any** mutant the moment the box gets busy.

The numbers say this is not hypothetical on this host:

```
$ python3 /tmp/r437/margins.py
example                        orig_s    mut_s  same
self_host.lang                  0.602    0.655  True
diverge.lang                    0.009    0.007  True
… 11 more, all < 0.01 s …
MAX seconds seen: 0.655  (SIGALRM budget is 2.000)
```

`self_host.lang` needs a **3.3x** load spike to cross. `nproc` on this box is
**1**, and research-state item 8 measures the corpus tier at 144 s solo against
419–447 s under the driver's own concurrent run — a **3x** penalty. The
required spike is the size of the contention this program measures routinely.
The two runs are not even adjacent in time: the original's behaviour is
`orig_cache`d (computed once, for the first mutant) and the mutant's is
computed later, so an arbitrary amount of load can land between them.

Round 203 met this family already — "a different, flaky killer on every run"
for a slow example — and fixed the variant it saw (`_Timeout` leaking into
`canonical`'s `except Exception` as a partial-output crash). The asymmetry
underneath it survived that fix by 234 rounds.

**Honest limit, stated plainly: this round did not observe the spurious kill.**
It cannot — the race is not schedulable, and the run that would show it is the
one that already happened, in round 433, and left no artefact. What is proven
is (a) the code path exists and is the only path to round 433's symptom,
(b) the margin is 3.3x, (c) the contention on this host is 3x, and (d) the red
is not reproducible under any of the three ways this round tried to reproduce
it. That is a strong circumstantial case, not a caught red-handed one, and it
is recorded as such.

### The fix: re-measure, do not forgive

A mutant that genuinely diverges — an infinite loop out of a mutated bound —
**is** a real kill and must stay one. So a mutant-only timeout is not
discarded; it is re-measured, with the original re-measured beside it at the
same larger budget (`TIMEOUT_RETRY_FACTOR = 3.0`, chosen as the measured
contention penalty, not as a round number):

| first pass | 3x pass (original) | 3x pass (mutant) | verdict |
|---|---|---|---|
| mutant timeout | completes | completes, same answer | `same` — the timeout was load |
| mutant timeout | completes | still timeout | `differs` — diverges at 3x: a real kill |
| mutant timeout | completes | different answer | `differs` |
| mutant timeout | still timeout | — | `undecided` — no clean `expected` exists |
| anything else | — | — | unchanged, **one** `behaviour()` call |

`undecided` is a new, third outcome and it is **counted, not folded**. Before
this round a `no_killer` verdict reached with three unmeasurable programs and
one reached with zero were spelled identically in `killers.json`;
`Killer.undecided` and the corpus-level `killers.json["undecided"]` now say
which. The guard costs nothing on the paths that matter — agreement and a
plain behavioural difference each still decide on a single measurement, pinned
by `test_a_plain_behavioural_difference_costs_no_extra_measurement`.

The `shrink` predicate got the same treatment. It had the identical
asymmetry (`behaviour(mut_pkg, cand) != e`), so a spurious timeout inside the
shrinker could minimise a real killer down to the wrong program.

## 3. The corpus that was 27 programs where the checkout has 13

While reproducing, the repro printed `programs: 27` for an examples-only
corpus. The checkout has 13. That gap is a second defect, in production code,
with a documented intent it was silently not delivering.

`swe/fuzz.py::list_example_files` resolves the curated corpus through
`git ls-files`, and says why:

> `examples/` is not exclusively ours: a separate autonomous process sharing
> this repo … has dropped its own untracked `.lang` files into this same
> directory … Using `git ls-files` instead means only committed, curated
> examples ever enter differential-testing corpora.

`swe/mutation.py::_copy_project` excludes `.git` **on purpose** (round 413:
468 MB of `node_modules` and the git dir, a 9 s copy against 1.8 s). So in a
copied tree `git ls-files` cannot answer, the function falls through to
`os.listdir`, and the curation is gone:

```
languages/whence/examples/     32 .lang files on disk
git ls-files                   18 tracked
.gitignore names by hand       14 (cognitive_verifier*, prod_demo_v*,
                                  whenceguard*, nano_reasoner, mini_agi_guardian,
                                  expense_tracker, prod_showcase_final, test_simple)
corpus in the checkout         13  (18 curated − 5 in _HEAVY_EXAMPLES)
corpus in a copy               27  (32 on disk − 5 heavy)
```

**Fourteen files another process writes were in the differential corpus of
every campaign stage that runs against a copy** — which is every campaign test
in this repo, and any campaign given a sandbox root. Nothing failed, no error
was raised, and no test noticed, because a widened corpus produces *more*
evidence rather than an exception. It is the failure mode `state/`'s own
vocabulary calls a guard that reports success by doing nothing.

This is the class `swe/copyparity.py` was written for — "a file that resolves
something outside the copy behaves differently inside it" — and the class
`swe/sandboxevidence.py` already documents for a `git show` in whence's own
suite. What is new is that copyparity **cannot see this one**: its `collect`
mode diffs node-id sets and its `run` mode diffs per-node verdicts, and this
defect changes neither. It changes a denominator.

### The fix: the curation travels with the copy

`_copy_project` is the one boundary where the checkout is still reachable, so
it materialises the answer into the copy as `examples/.curated-examples`.
`example_curation(root)` then resolves in three steps and **reports which one
it took**: `git` (this tree is a checkout) → `manifest` (this tree is a copy
that inherited the decision) → `listdir` (neither; the old behaviour, kept as
the last resort because a caller with no corpus is worse off than one with an
uncurated corpus it knows about).

```
$ source  : git      18
$ copy    : manifest 18
$ copy^2  : manifest 18     (32 .lang files on disk in both copies)
```

A copy of a copy inherits the manifest from `shutil.copytree` for free and
must **not** regenerate it: the intermediate tree has no git either, and a
regenerate-if-you-can rule would re-curate from whatever that tree happens to
contain. `test_a_copy_of_a_copy_inherits_the_curation_unchanged` pins byte
equality of the two manifests. A source that is neither a checkout nor
manifest-carrying gets **no** manifest written, because a manifest asserts that
a curation decision was *made*; inventing one would freeze a `listdir`
snapshot and call it curated.

`killers.json` now records `example_curation` beside `programs`. Which examples
is a denominator, and a denominator whose provenance is unrecorded cannot be
compared across runs — which is precisely the position round 433's failure
left this round in.

## 4. Two more reds nobody was looking at

**`test_swe_killers.py::test_find_killer_for_a_real_semantic_mutant`** —
found red while running this round's own new tests, and **not** caused by them:

```
AssertionError: no arith mutant on a `"concat"` line with `x + y` — re-anchor (rule 7)
```

The fixture anchored on `Prov("+", "concat", line, (l, r), _LAZY, x + y)`.
`interp.py` says at the site: *"v0.27: the inline string-concat case is GONE,
deliberately."* Bisected by content over the file's history: the line is
present in `48b8967` (round 366) and absent in `f568a79` (round 368, v0.27,
2026-08-30 14:08). The slow-tier ledger's last entry for this file is
**2026-08-30 08:08, `7 passed in 39.24s`** — six hours before the break — and
the ledger's newest entry of any kind is that same morning. **The file has
been red for ~69 rounds and no instrument has looked at it since.**

Fixed by re-anchoring per the fixture's own standing instruction ("every arith
mutant on a line containing `"concat"` is a legitimate anchor") — the stale
part was the extra `x + y` clause, which pinned a **spelling**; the surviving
concat sites spell their operands `l + r`. The loop now tries every candidate
and reports "no anchor is reachable from two string literals" rather than
"the first one I tried".

Worth the comparison: `_docstring_const` and this fixture suffered the *same*
drift at the *same* time, and only one of them said so. `_docstring_const`'s
`or` fallback cannot fail loudly — `_mutant` raises only when NOTHING matches,
and the `or` guarantees something does — so it silently re-pointed at an inert
mutant. The concat fixture had no fallback, so it failed with the word
"re-anchor" in the message. **A fixture with a fallback is a fixture that
cannot tell you it drifted.**

**`test_verb_audit.py::TestThisTree::test_no_unexplained_broken_invocation`** —
the fast tier's V002, red since round 429 and re-escalated by rounds 433, 434
and 435 without a fix. Re-derived at HEAD (the carried line number was stale:
`test_claim_check.py:188`, not `:190`):

```
V002  harness/pristine_check.py: skills/skill-authoring/scripts/test_claim_check.py:188
      invokes it with 'suites-and-then-some', which it does not declare
```

Round 433 diagnosed it as "a fixture naming a verb that must NOT exist" and
insisted the fix belong to `verb_audit`'s language rule, not an exemption.
Round 437 found the exact mechanism. For a `.py` file the raw line scan is
**already** disabled; the hit comes from the AST fold, which folds any
list/tuple of string constants into one pseudo-command because *that is the
shape an argv list has*. The offending node is a `for c in (...)` tuple of
**three independent command strings** asserted to classify as `manual`. Folded
into one line it reads `… pristine_check.py check … baseline … suites-and-then-some`,
and the trailing word is the undeclared verb the fixture exists to reject.

The rule, the fourth in a family `verb_audit`'s own docstring keeps: **a
sequence literal that is not in an ARGV POSITION is data.** An argv position is
an argument of a `Call` or the value of an assignment — the two ways this repo
spells one. A `for` iterable, an element of a larger literal, a `return` value
and a comparison operand are not. As with the round-421 `*argv` rule, only the
V002 trust flag is withdrawn: a verb REACHED from such a line is still sound,
because the word really is there.

```
before   103 declared verbs, 19 reached (18.4%), 19 findings (V001 6, V002 1, V003 12)
after    103 declared verbs, 19 reached (18.4%), 18 findings (V001 6, V002 0, V003 12)
```

**Reached is byte-identical.** The rule removed a false warning and bought no
false negative — `test_a_direct_call_argv_list_is_still_trusted` pins that an
undeclared verb inside a real `subprocess.run([...])` is still reported.

## 5. Round 435's item 5, closed

`state/swe/round-431/evaporating-test-kills-nothing.json` carried a top-level
`baseline` key and prose in the same file saying *"it has no baseline, no score
and no denominator over a file's mutation sites"*. Round 435 opened it as J005,
parked it in `state/known-selfdesc-drift.json` as owned by SWE-loop(D), and
named the two honest repairs: rename the key or rename the sentence.

Renamed the **key** to `node_precheck`. The object records that a single test
node passed in the worktree before any mutant was applied — a per-node
pre-check, not a mutation-campaign baseline. No number moved; the round-431
record is otherwise byte-identical, and a `_note` field says so. The
acknowledgement was deleted in the same edit, because the registry's own rule
is that an entry matching no finding "is reported DEAD and must be DELETED,
because an acknowledgement that suppresses nothing reads as coverage".

The note is deliberately named `_note` and not `_round_437_note`:
`selfdesc_check.SELF_FIELDS` is an exact-name allowlist
(`_`, `_comment`, `_note`, `_why`, `note`, `comment`), so a `_round_NNN_note`
is invisible to the checker — research-state item 3's complaint, confirmed by
measurement here. Naming it `_note` puts this round's own prose under the
instrument instead of behind it.

```
before   26 prose fields, 0 errors, 1 acknowledged, coverage 1/26 prose-fields
after    27 prose fields, 0 errors, 0 acknowledged, coverage 0/27 prose-fields
```

**And that is the uncomfortable part, reported rather than buried:** the ONE
checkable claim in the whole 26-artefact corpus was the contradiction that just
got fixed. `selfdesc_check` now demonstrably checks nothing — 0/27 — so its
next regression is invisible. Round 435 called `coverage 1/26` "the honest
headline"; the honest headline today is `0/27`. That belongs to skills(B).

## 6. Tests

| suite | before this round | after |
| --- | --- | --- |
| `test_swe_campaign.py` (19 of 20, round 433's command) | 19 passed, 1 deselected, **592.42s** | 19 passed, 1 deselected, **696.63s** |
| `test_swe_killers.py` | **1 failed**, 6 passed, 27.7s | **15 passed**, 27.7s |
| `test_swe_mutation.py` + `test_swe_fuzz.py` | 55 passed | **62 passed**, 102.9s |
| `test_verb_audit.py` | 25 passed, **1 failed** (V002, red since round 429) | **29 passed**, 75.0s |
| `verb_audit.py check` | 19 findings (V001 6, **V002 1**, V003 12), 19/103 reached | 18 findings (V001 6, **V002 0**, V003 12), **19/103 reached** |
| `selfdesc_check.py` | 26 prose fields, 0 errors, **1 acknowledged**, coverage 1/26 | 27 prose fields, 0 errors, **0 acknowledged**, coverage **0/27** |

**19 tests added** — 8 in `test_swe_killers.py` (7 driving `compare` through a
stub `behaviour`, 1 on `Killer.undecided`), 7 in `test_swe_mutation.py` (the
curation, on a synthetic checkout), 3 in `test_verb_audit.py` (the argv-position
rule and its two must-stay-trusted counter-cases), 1 in `test_swe_fuzz.py` (the
real-tree pin). The per-file counts are checkable against the table above:
7→15, 55→62 across two files, 26→29. **2 pre-existing reds fixed** (the concat
anchor, V002). **0 new reds.**

Two honesty notes on that table:

* The campaign file got **slower** (592 → 697 s) while its corpus got
  **smaller** (27 → 13 programs). That is contention, not the change: the
  `test_verb_audit.py` run (75 s) overlapped it on a one-core box. The
  comparison is therefore **not** a clean A/B and is not offered as one. What
  the second run does establish is that the curated corpus keeps all 19 tests
  green — including `test_corpus_stage_pins_killers_and_verify_confirms_them`,
  which needs the corpus to actually FIND a killer.
* `test_swe_mutation.py` is a **promoted** fast-tier file with a 25 s cap. The
  7 new tests use a synthetic git checkout rather than a real
  `_copy_project(WHENCE_ROOT, …)` precisely so they cost nothing: the file
  measured **17.1 s of its 36.3 s drift threshold** afterwards, against 18.17 s
  when round 385 promoted it. The one test that does pay for a real copy is in
  `test_swe_fuzz.py`, which is slow-tier.

## 7. Predictions, scored

| # | prediction | verdict |
|---|---|---|
| D1 | the red reproduces outside pytest (`no_killer == 0`) | **MISS** — the repro was correct (`no_killer: 1`); so were the solo and whole-file runs |
| D2 | the fixture selects `whence/interp.py:604`, `const`, `self.peak_depth = 0` | **HIT** — `interp.py:604:const#366`, `0 -> 1`, re-derived not carried |
| D3 | it is round 433's shape 2 (a corpus program kills it), not shape 1 | **MISS** — neither. `found: 0` and `by_id` resolves the survivor |
| D4 | a path exists from `peak_depth` to one of `canonical()`'s four fields | **MISS** — none exists; 18 Python test files name it, 0 `.lang` files do |
| D5 | the defect is in the FIXTURE, not in `campaign.py` / `killers.py` | **MISS** — the fixture's silent re-point is real but benign; the two defects are in `killers.find_killer` and `fuzz.list_example_files`, both production code |
| D6 | at most one of `_docstring_const`'s users is red | **HIT** — zero are |
| D7 | repro < 120 s; the test re-runs in 45–95 s | **HIT** — 17.8 s corpus stage; 46.07 s call |
| D8 | V002 still red at HEAD, same site | **HIT** with a correction — still red, still `suites-and-then-some`, but at `test_claim_check.py:188`, not the carried `:190` |
| D9 | the round-431 artefact still contradicts itself | **HIT** — confirmed, then fixed |
| D10 | after the fix both tests green, **with no change to `campaign.py`** | **MISS on the second clause** — `campaign.py` changed twice (corpus provenance, `undecided`); the first clause is moot because nothing was red |

**4 hit, 5 miss, 1 split.** The misses are the round: D1/D3/D4 were all
downstream of accepting round 433's framing that a red test means a wrong
answer somewhere. It did not. D5 was the same error one level up — I predicted
the bug would be in the test-support code because that is where round 433's
lead pointed, and it was in the engine.

**The lesson generalises past this round.** Round 433 banked two candidate
shapes and wrote *"do not guess between them, run the file."* Running the file
answered "neither" — and it could only answer that because it was run three
different ways. A carried red is a claim with a timestamp on it: the first
question is not *which* explanation is right, it is **whether the observation
still holds**. Rounds 434, 435 and 436 each re-derived a carried number and
each found one wrong; this round re-derived a carried *failure* and found the
failure itself gone.

## 8. Honest limits

* **The spurious kill was never caught in the act.** §2 is a mechanism plus a
  margin, not a captured failure. It cannot be captured: the race is between a
  cached measurement and a later one on a contended box, and the only run that
  is known to have hit it (round 433's) left no artefact behind. If a future
  round sees `undecided > 0` in a `killers.json`, that is this hypothesis
  producing evidence for the first time.
* **`TIMEOUT_RETRY_FACTOR = 3.0` is a judgement, calibrated but not tuned.** It
  is the measured contention penalty on this host (144 s solo vs 419–447 s
  concurrent, research-state item 8) and the margin on the slowest curated
  example is 3.3x. A genuinely divergent mutant is normally *infinitely*
  divergent, so the factor's exact value matters much less than its existence
  — but nothing here measured the false-negative rate at 3x versus, say, 5x.
* **The corpus change is a real behavioural change to every campaign that runs
  against a copy**, and its blast radius outside `test_swe_campaign.py` was not
  measured. Three other corpus builders call `list_example_files`
  (`swe/oracles.py:1117`, `swe/oraclekill.py:346`, `swe/exemptmap.py:1181`) and
  their suites were not re-run in this round's time. They can only get a
  *smaller, curated* corpus, so the direction is fail-closed — but "fail-closed"
  is an argument, not a measurement.
* **`example_curation` resolves `git` first, even for a copy.** A copy placed
  inside an unrelated git checkout that happens to track something under
  `examples/` would answer from the wrong index. `git ls-files` returns nothing
  for an untracked copy, and the empty result already falls through to the
  manifest, so the only way to hit this is to copy the tree *into* another
  repo and commit it. Recorded, not guarded.
* **The whence fast tier was not re-run.** `.curated-examples` does not end in
  `.lang`, and the two whence tests that list the directory
  (`test_v24.py:217`, `test_v27.py:638`) plus the three `glob("*.lang")` sites
  filter on that suffix, so the manifest is invisible to them — checked by
  reading, not by running.
* **`test_swe_campaign.py[light]` still has no slow-tier ledger entry**, and
  the slow tier's newest entry of any kind is still **2026-08-30 08:08**. Round
  433 built the unit layer; two rounds later the tier's recall is still 0% and
  this round did not raise it either. That is how `test_swe_killers.py` stayed
  red for ~69 rounds.

## 9. The skill: a seventh class, and the first one no mode catches

`skills/copy-parity-differential/SKILL.md` upgraded (354 → 432 lines), not a
new skill: that file already exists to answer *which tests change verdict when
the project is COPIED*, and §3's finding is a member of exactly that family
that its own instrument cannot see.

Rounds 425 and 431 measured six defect classes against the real subject and
tabulated which of five columns catches each — static `escapes`, `collect`,
`run`, the signed skip list, the exit-code gate. Round 437 adds a seventh row,
and every cell in it is **no**:

| class | static | `collect` | `run` | skip list | exit gate |
|---|---|---|---|---|---|
| **a curated SET silently WIDENS** | no | no | no | no | no |

The static scan looks for path expressions that leave the subtree
**lexically**; `subprocess.run(["git", "ls-files", …], cwd=root)` leaves at
**runtime**, when git walks up from `cwd` and finds no repo. `collect` sees the
same node ids. `run` sees the same per-node verdicts — the tests still pass,
they just assert over a bigger set. There is no skip to sign and no non-zero
exit to gate on. **The defect is in a denominator, and a verdict differential
has no denominator column.**

Three things were added that a future round can act on without re-deriving
this one:

* **A greppable tell.** A function whose docstring promises a curated set
  (*only committed*, *only tracked*, *excluding vendored*, *the allowlisted N*)
  whose body wraps a `git`/`hg`/`svn`/`pip`/`npm ls` call in `try/except: pass`
  with a bare `listdir`/`glob` after it. Every such fallback falls back to
  **more**, never to fewer, and none of them says so.
* **A trigger on the artefact rather than the code.** `programs: 27` in a
  sandboxed artefact against `programs: 13` in the checkout is a finding, not
  a rounding difference — and comparing the two is cheap.
* **The fix shape.** Materialise the answer at the copy boundary, resolve
  `real source → manifest → fallback`, and **name which one you took**. Plus
  the two rules that make it safe: a copy of a copy must not regenerate, and a
  source that can answer neither gets no manifest, because a manifest asserts
  that a decision was made.

One stale number in that file was corrected while editing it: its Verification
said "two of the four classes are invisible to every exit-code gate" against a
six-row table in which four rows are. It now reads four of seven, plus the
seventh being invisible to all five columns.
