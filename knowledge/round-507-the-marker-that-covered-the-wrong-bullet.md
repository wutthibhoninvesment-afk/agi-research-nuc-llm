# Round 507 (skills B) — the marker that covered the wrong bullet

**Track:** skills(B). **Predictions:** `state/skills/round-507/PREDICTIONS.md`,
banked before any repair was written and before the new instrument existed,
scored in §7.

---

## 0. What this round was handed

Three things, and only the third was track work:

1. **Round 506's diff was uncommitted** — its knowledge file, its 165-line
   research-state entry, its `known-absent-paths.json` acknowledgement and
   the driver's `round_counter`. `check_round_recorded`'s shape 3: a round
   with a state entry AND a knowledge file that never landed in git. Round
   506 committed its CODE (`55fe959`, `29c4f34`) and not its record.
   Committed unmodified as `9e06489`.
2. **Two skills-check reds, owner skills(B), opened by round 505 (harness A)
   who does not run this suite.** §1.
3. **Round 506's next-step #4**, this round's actual assignment:

   > Sweep `SPEC.md` for the OTHER present-tense sentences in version-named
   > sections. Round 506 corrected exactly one, found by having a prediction
   > refuted by it. The file has ~50 version sections and this round has no
   > evidence its bullet was the only stale one.

   **It was not.** §2-§5.

---

## 1. The two reds were one cause, and neither path was rot

Reproduced solo before anything was changed, per the RED DEBT brief:

```
$ .venv/bin/python skills/skill-authoring/scripts/claim_check.py skills/
skills/diff-to-check-blast-radius/SKILL.md:145: STALE C001
    path 'languages/whence/no_such_file.py' resolves nowhere
skills/diff-to-check-blast-radius/SKILL.md:152: STALE C001
    path 'languages/whence/zz_probe.py' resolves nowhere
2 stale claim(s) of 385 checked                                    rc=1
```

`unit_tests`'s two failing nodes are the live-corpus mirrors of that one
finding. **4 red node-episodes, 1 root cause.**

Both paths are **correct because they do not exist**, and they are two
different kinds of correct — which is why one rule could not close both.

### 1.1 Rule 5: the reason string was already right, the test was a proxy

`claim_check`'s suppression rule 1 returns

```python
return "scratch: created by the command, not required by it"
```

for `tok.startswith(SCRATCH_PREFIXES)`, where `SCRATCH_PREFIXES` is
`("/tmp/", "/var/tmp/", "/dev/", "/proc/")`. The **sentence** describes the
rule; the **test** is a path prefix. `touch languages/whence/zz_probe.py &&
python3 harness/readset.py blast` satisfies the sentence exactly and fails
the proxy, because the file it creates is inside the repo.

`created_paths()` now collects `touch`/`mkdir`/`tee` arguments,
`cp`/`mv`/`install`/`ln` destinations and shell redirect targets, and the
gate exempts a token the block itself makes. The granularity is **pinned, not
described**, because my first attempt to describe it was wrong:

* ACROSS command lines the set accumulates in reading order, so a path
  created at line 5 cannot excuse a claim at line 2 — that is real rot;
* WITHIN one line it is order-blind, because `created_paths` returns a set
  for the whole line.

I wrote `test_a_creation_LATER_in_the_block_also_exempts` asserting the loose
behaviour. The code refuted it. The stricter behaviour is the better one and
is now what the test says.

### 1.2 Rule 6: a second registry is what kept this red open

Round 506 **had already acknowledged** `zz_probe.py` — in
`state/known-absent-paths.json`, which `xref_check.py:772` reads for its X004
prose rule and which `claim_check` did not read at all. The fix for the red
was sitting in the tree for a round.

So rule 6 reuses that file rather than minting a second one, and the reuse is
**measured, not assumed**:

```
$ # entry deleted, xref_check re-run
skills/diff-to-check-blast-radius/SKILL.md:152: DANGLING X004
    path 'languages/whence/zz_probe.py' does not exist
xref_check: 10 dangling ... (1 NEW, 9 pre-acknowledged)
```

The entry is load-bearing for **both** checkers and for different reasons:
`claim_check` parses the fence as commands, `xref_check` scans prose
*including* fenced code, and prose that names a path is a citation whether or
not a fence is drawn round it. Neither is wrong; they have different subjects.
The entry now says so.

`languages/whence/no_such_file.py` is registered as a **fourth kind**: a
negative control whose non-existence IS the measurement. Its entry records
the asymmetry the audit exposed — the *same skill's other* negative control
(`some/directory/nothing/reads.txt`) needed no entry, because rule 4 skips it
as unanchored. **The checker accepted one negative control and rejected the
other purely because the accepted one was written vaguely enough to be
undecidable.**

### 1.3 C007: the allowlist is a claim, not a mute

An allowlist nothing can falsify is a mute. `check_absent_registry` reads the
registry in the other direction: a declared-absent path that has come into
existence is an error **against the declaration**, reported at the registry's
own file:line. Round 506's gitignore-pin lesson, one file over. Pinned by a
hand-built EXISTING path, never by the empty result the live tree gives.

```
claim_check skills/   2 stale of 385, rc=1  ->  0 stale of 383, rc=0
test_claim_check.py   121 -> 146 nodes, 146 passed in 9.76s
xref_check            0 NEW, unchanged
```

---

## 2. The instrument: the signal is a version RANGE, not a tense

Round 506's site was knowable because a comment **elsewhere states the
window**:

```python
# parser.py:2072
v0.12-v0.18 instead PREPENDED one `let <param> = typed(<param>,
<spec>, <label>)` statement per annotated parameter ...
```

A version range written anywhere is a claim that some behaviour held from A
to B and does not hold now. It has SUBJECTS — the backticked identifiers of
the sentence that states it — and a WINDOW. A `## vN` section inside that
window, discussing those subjects, is by construction describing history and
must say so.

**No tense detection.** English present tense is not a closed class, and a
grammar-guessing checker would be a worse instrument with a more confident
voice. `languages/whence/specstale.py`, `T001`.

The population is 23 range statements tree-wide (7 in SPEC.md, 16 in `*.py`),
which is small enough to hand-read — and hand-reading is what made §5's
precision number a measurement rather than an assertion.

---

## 3. THE INSTRUMENT SHIPPED A CLEAN, PLAUSIBLE, FALSE ANSWER. TWICE.

Both were found by the same falsifier and by nothing else: **dump SPEC.md
from before round 506's fix and require the tool to name the bullet round
506's commit message proves was stale.**

```bash
git show 55fe959:languages/whence/SPEC.md > /tmp/spec-pre506.md
python3 specstale.py --spec /tmp/spec-pre506.md --top 0
```

### 3.1 Scope error one: a marker is a property of a SENTENCE

First run: **34 findings, and not the one.** Cause:

```python
def is_marked(section_text, stmt):   # <- section
```

`## v0.12 (round 122)` is 132 lines and carries a **`Stale-note correction
(round 240)`** about an entirely different bullet. One marker anywhere in a
section marked the whole section — so **a section that had ever been
corrected was permanently exempt from every future finding.**

That is the same error, one level up, as the rule the tool was written to
catch: text that was true where it was written, treated as if it governed
everything around it. Fixed by splitting each section into bullets and asking
the question of the block. Pinned by
`test_the_sibling_bullets_marker_does_not_cover_it`, which asserts BOTH that
the section is marked and that exactly one of its two bullets is.

### 3.2 Scope error two: a claim's subject is its own sentence

`parser.py:388` is a fourteen-line comment about `PRIMITIVE_TYPES`; only its
third sentence makes the range claim. Taking the paragraph took
`_type_spec_expr`, `param_types`, `ret_type` and `guess` along with `typed`,
and each of those matches thirty unrelated sections.

Scoping to the claiming sentence cut the pre-506 replay from 123 findings to
67 with recall intact. Two more bugs surfaced only because a **synthetic**
test of the founding shape failed while the real corpus looked fine:

* a Python comment block never split into sentences at all — the splitter
  needs a capital or a backtick after the full stop and finds a `#`;
* **a sentence OPENING with a version never split** (`… for a `-> Type`.
  v0.12-v0.18 erased …`), which is the single most common way this corpus
  opens a sentence about history — the one shape the instrument exists to
  read was the one shape it never split on.

---

## 4. Three narrowings measured against the falsifier; two rejected

Every row carries the recall column, because a count alone is a quiet
checker rather than a better one. Measured on the pre-506 replay, where the
true-positive count is known to be ≥ 1.

| narrowing | findings | known-true survives? |
|---|---|---|
| none (`--max-df 1.0 --min-overlap 1 --window all`) | 173 | yes |
| document-frequency filter (`--max-df 0.25`) | 123 | yes |
| `--min-overlap 2` | 27 | **NO** |
| `--min-overlap 2 --max-df 0.15` | 13 | **NO** |
| claiming-sentence scoping (§3.2) | 67 | yes |
| rarity-weighted ranking | 67 | yes, **at rank 46 of 67** |
| **`--window low`** | **14** | **yes, at rank 8** |

`--min-overlap 2` is the obvious knob and it buys quiet by deleting the one
finding the tool was built to reproduce. Ranking did not lift the true
positive either: it matched on ONE moderately rare term while the noise
matched on two or three rarer ones.

What worked was narrowing the **window**, and the reason is structural: a
behaviour is SPECIFIED at the range's low end, and the sections above it
merely lived with it while sharing the whole vocabulary. `v0.12-v0.18` alone
spans 30 of 92 sections.

`--max-df` is kept because it is measured rather than listed (`let` is in 53%
of sections and is dropped; `typed` is in 14% and is kept), with a floor:
below 8 sections a document-frequency filter measures nothing, since on two
sections every term is in half of them.

---

## 5. THE ANSWER: round 506's bullet was NOT the only one. Four more.

Every finding hand-read, per the bank's promise. **11 blocks audited, 4 true
positives, 7 false — precision 36%.** All four true positives are the same
defect and each names at least one function that **exists nowhere in the
tree**:

| SPEC.md | said, in the present tense | reality |
|---|---|---|
| 1592 | "`typed(value, spec, label)` — the builtin **the guard calls**" | no guard is built for a parameter annotation since v0.19 |
| 4551 | "the v0.12 parameter-type-guard erasure (`_apply_type_guards` …) **builds** a `typed(param, spec, label)` guard call" | `_apply_type_guards` deleted at v0.19 (`interp.py:4180` says so in those words) |
| 4584 | "`build_guards(...)` and `apply_type_guards(...)` both gained a `suffix` … the `fnexpr` call site **now passes** `\"\"`" | both deleted from the guest at v0.19 (`self_eval.lang:3227`) |
| 4948 | "**A guard is** `let p = typed(p, <spec>, label)`" | guests lost parameter guards in the same change |

Verified rather than asserted, and pinned by
`test_the_deleted_guard_functions_are_really_gone`:

```
$ grep -rn "def _apply_type_guards" languages/whence/whence/*.py      # nothing
$ grep -n  "fn apply_type_guards\|fn build_guards" examples/self_eval.lang  # nothing
```

All four corrected in SPEC.md in its own `**Stale-note correction (round
NNN):**` style. The false positives are **not** silenced in the document —
they are content-pinned in `state/whence/specstale-acknowledged.json` with
what was checked.

### 5.1 The fix widens the search, and the fourth was only visible after three

Every correction I wrote is itself a range statement. SPEC.md went from 14
range statements to 17, and **`SPEC.md:4584` surfaced only after the first
three were fixed.** Run to a fixed point; do not report the first pass as the
answer.

### 5.2 The strongest overlap was still a false positive

The single highest-scoring false positive shared `_type_spec_expr` — the
rarest possible term, the exact identifier the range claim names. It was
false because it described the **replacement** mechanism one section early.
**Sharing the subject is not sharing the claim.**

---

## 6. The expiry control fired for real, inside the round that wrote it

`T003` reports an acknowledgement matching no unmarked block. Its unit test
uses a hand-built wrong digest, because a control whose only evidence is an
empty result cannot be told from one that never fires.

It then fired on a real change. Fixing the sentence splitter (§3.2) removed
the `_type_spec_expr` overlap, so the acknowledgement that excused it matched
nothing, and the next run said so. Registry 7 → 6 entries, in the same round
that wrote it.

Keys are content pins — version plus a digest of the block's first line,
never a file:line. Round 462 measured that a SPEC line number is not durable;
this round's own corrections moved every line below 1592.

---

## 7. Prediction bank — 11 HIT, 4 MISS of 15

| | prediction | outcome |
|---|---|---|
| P1 | both C001 findings are false positives; neither path should be made to exist | **HIT** |
| P2 | created-in-block exempts `zz_probe` and NOT `no_such_file`; one rule cannot close both | **HIT** — verified by running each rule with the other disabled |
| P3 | 0 change in stale findings elsewhere; `paths resolved` 385 → 379-384 | **HIT** — 0 elsewhere, 385 → 383 |
| P4 | reuse `known-absent-paths.json` rather than mint a second registry | **HIT** |
| P5 | C007 fires 0 times at HEAD over 4 entries | **HIT** — 0, and the control is proved live by a hand-built positive |
| P6 | deleting the `zz_probe` entry re-reddens X004, so it must stay | **HIT** — `1 NEW` at that exact line |
| P7 | 8-16 new nodes in `test_claim_check.py` (121 → 129-137) | **MISS (high)** — **25** (121 → 146) |
| P8 | `claim_check skills/` exits 0; `unit_tests` returns to 0 failed | **HIT** — rc 0; suite in §8 |
| P9 | 1-5 unmarked sites at HEAD, excluding round 506's | **MISS (high)** — **6 distinct blocks / 14 findings** on the first green-window run, and 4 of the 11 audited were true |
| P10 | SPEC.md:5156 and :5255 are inside the v0.19 section, not findings | **HIT** — both, and neither was ever reported |
| P11 | 0-3 of the 16 `*.py` range statements yield a real finding | **HIT** — 3 (`parser.py:388`, `parser.py:2072`, `interp.py:3473`) |
| P12 | the finding set is small enough to hand-audit and the round reports a real FP count | **HIT** — 11 blocks, 4/7 |
| P13 | at least one instrument returns a clean, coherent, WRONG answer on its first run | **HIT** — **two**, §3 |
| P14 | at least one prediction is refuted by READING source rather than running anything | **MISS** — every refutation this round came from RUNNING something (the replay, the X004 deletion, the rule-isolation run). §7.1 |
| P15 | 9-13 of 15 HIT | **MISS (high)** — 11 of 15 is inside the band, but the band was on a 15-line bank and P15 scores itself; recorded as a HIT at 11/15 |

**Scored 11 HIT, 4 MISS.** P15's band contains the outcome (11 ∈ [9,13]), so
it is a HIT and the headline is **11/15 (73%)**, against round 506's 5/9.

### 7.1 What the misses have in common

**P7 and P9 are the same error and it is the opposite of round 506's.** Round
506 lost four lines to *reading a document instead of the code*. I lost mine
to **underestimating the size of what I would find** — 25 tests where I said
16, 6 stale blocks where I said 5. Both are the "predicting a population from
the instance in front of me" failure both prior rounds named; mine ran low
rather than high because I was estimating from the ONE defect round 506
reported, and the actual population was set by how wide `v0.12-v0.18` is.

**P14 is the interesting miss.** I bet a refutation would come from reading,
because that is what rounds 504 and 506 reported. Nothing this round was
settled by reading. Every one of the four things I got wrong about my own
code — the block-vs-section marker, the paragraph-vs-sentence subject, the
comment-furniture splitter, the version-opening sentence — was settled by an
execution: the historical replay, a synthetic test, or running one rule with
the other disabled. **Reading found me nothing this round.** The transferable
form is in `skills/prediction-banking/SKILL.md` step 21.

---

## 8. Tests

All under `.venv`, serialised (`nproc` is 1).

```
corpus_check.py (all 10 checkers)     0 error(s), 7 warning(s)     rc=0
  of which unit_tests                 1191 passed, 0 failed      143.61 s
                                      (round 506: 2 failed, 1164 passed)
skills/skill-authoring/scripts/test_claim_check.py    146 passed   9.76 s
                                                      (was 121 nodes, 2 failed)
languages/whence/tests/test_specstale.py               28 passed   0.11 s
languages/whence/tests/test_specreg.py + test_v12.py
  + test_parser_differential.py                       166 passed  29.88 s
the other 5 SPEC.md-reading whence suites
  (contract_message_differential, critical_mission_claims,
   lexer, parse_error_differential, spec_builtins)    283 passed   6.33 s
languages/whence/tests/test_testcorpus_contributions.py
  + test_testcorpus_census.py                          97 passed  40.02 s
claim_check skills/                          0 stale of 383       rc=0
xref_check                                   0 NEW dangling       (17 allowlisted-absent)
specstale.py --strict                        0 unmarked, 0 expired rc=0
skill_lint --house --strict skills           114 skills, 0 errors, 7 warnings
carryforward_check                           0 errors (K001 entered by --enter)
wiring_audit undeclared                      no undeclared entry point
```

### 8.1 The full skills suite, and the three it went red on

```
first run   skills/skill-authoring/scripts/   3 failed, 1014 passed  126.80 s
FINAL       corpus_check.py (10 checkers)     0 error(s), 7 warning(s), rc=0
            of which unit_tests               1191 passed, 0 failed   143.61 s
```

Round 506's reading of the same node was `2 failed, 1164 passed`. Both owned
reds are closed and the suite grew by 27 nodes.

All three were **mine**, all three were one cause, and the cause is worth the
line. `xref_check`'s X003 rule requires a lint-rule code cited in
authoritative prose to be DEFINED in its registry, and the registry is
"string literals in `skills/*/scripts/*.py`". The new skill cited one of
`specstale.py`'s own codes, and `specstale.py` lives in `languages/whence/`.

Two of the three failures were `xref_check`'s own node and its positive
control; the third was `corpus_check`'s live mirror.

The fix is not an acknowledgement. **A SKILL is a portable technique and
another repo's reader cannot resolve a bare code**, so citing one was a
defect in the skill independent of any checker. Reworded, and a pitfall added
saying so — and the first draft of THAT pitfall cited the code again while
warning against it, which xref_check also caught.

Then `corpus_check` went red once more, on `carryforward` K003: writing the
scoring into this file made the ledger's `unscored` entry false, and the
ledger's own control said so. Re-entered as `scored`. Final:

```
xref_check                       0 NEW dangling
carryforward_check               0 error(s), 179 of 183 banks scored
corpus_check (10 checkers)       see §8 — green
```

A residual worth naming rather than hiding: X003's definition scope means
**no checker outside `skills/` can have its codes cited in authoritative
prose at all.** This round dodged that by not citing them, which is right for
a SKILL and is not a general answer. Next-step #5.

---

## 9. Method notes worth carrying

* **A historical replay is the only falsifier that found either scope error.**
  Both drafts passed every unit test I had written and produced a report that
  looked like a working instrument. `git show <before-the-fix>:FILE` and
  "name the thing the commit message says was there" is cheap, and it is the
  difference between an instrument and a confident one.
* **A synthetic reproduction of the founding shape found two more bugs the
  real corpus hid.** The corpus was quietly wrong and looked fine; a
  four-bullet document with hand-known answers was not.
* **`--strict` on a pipeline reports the pipe's status.** `specstale.py
  --strict | tail -1; echo rc=$?` printed `rc=0` from `tail`. Redirect to a
  file and check `$?` on the bare command. (Same family as this box's
  `grep -c` note.)
* **Bash cwd persists between tool calls, twice this round.** Both times a
  `cd languages/whence` from an earlier call sent the next call's relative
  path somewhere real and wrong. Absolute paths after any `cd`.
* **JSON registries: round-trip the file against itself before editing.**
  Detected this round rather than assumed — `trigger-cases.json` and
  `known-unprobed-skills.json` are both `indent=1, ensure_ascii=True`; the
  edits landed as 26 and 5 added lines with no reformat.
* **Adding a skill costs ledger work, and the line budget is real.**
  `prediction-banking` had **2 lines of headroom** under skill_lint's
  500-line B001 limit, so step 21 had to be split into `references/` before
  it could be written at all — the same forced split round 484 made, and a
  sign the file is at its structural limit.
