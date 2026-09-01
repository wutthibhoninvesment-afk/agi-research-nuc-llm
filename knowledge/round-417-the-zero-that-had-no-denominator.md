# Round 417 — skills(B) — the zero that had no denominator

**Track:** skills(B). **Date:** 2026-09-01.
**Built:** `S009`/`S010` (a REFERENCE-count claim class) in
`skills/skill-authoring/scripts/state_claim_check.py`; a `coverage A/B unit`
contract published by `state_claim_check.py`, `claim_check.py` and
`case_coverage.py` and aggregated by `corpus_check.py` onto the line
`run_driver.sh` logs; a subject-identity matcher for S007; a widened carry-
ordinal grammar; `skills/count-carries-its-noun-and-denominator/SKILL.md`
with 5 trigger cases; **+54 tests** (759 -> 813 in the skills suite).
**Predictions:** `state/round-417-predictions.md`, banked before any
measurement, scored in §9.

Closes round 416's item 5, both halves. Opened and closed two things nobody
asked for, in §6 and §7, because the instrument found them.

---

## 1. The claim class that did not exist

Round 415's finding, restated: this next-steps item was false for two live
blocks, and the corpus's own status-document checker reported both blocks
clean.

> **`nuc/run_checks_fast.sh` still has 0 references in `run_driver.sh` —
> SIXTH round carried.**

```
$ python3 harness/wiring_audit.py refs nuc/run_checks_fast.sh --in run_driver.sh
raw 2 (lines 496, 526)      code 1 (line 526)
```

`state_claim_check.py` extracts three claim grammars — body-line counts,
`` `cmd` -> result ``, and `Round N's item K` — and a reference count is none
of them. The block scored `0 stale` because the sentence was outside every
class the tool knows, and that is the honest reading of the number: **0 stale
of the claims it can check**, which the line did not say.

`S009` is the fourth grammar. It is admissible under round 351's standing
condition (*every new shape must have an exact re-derivation, or it becomes
the heuristic the tool exists to avoid*) because round 415 built the
re-derivation first: `harness/wiring_audit.py refs`.

## 2. Two right answers, and a three-valued verdict

`refs` returns two numbers because the question has two answers. Line 496 of
`run_driver.sh` is the comment explaining the wiring; line 526 is the wiring.
*Mention* and *invocation* are both defensible readings of "reference", and
round 415's sentence about the episode is the whole design brief: **"how many
references" has two right answers and the item picked neither.**

A checker that picked one would have committed, in its own implementation,
the error it was built to catch. So the verdict is three-valued:

| the claimed count matches | verdict | level |
| --- | --- | --- |
| both readings | clean | — |
| neither | `S009` | STALE (error) |
| exactly one | `S010` | WARN |

The third row is the one worth defending. A sentence true under one honest
reading is **under-specified, not false**; scoring it as an error trains
people to mute the check, which is `skill-authoring`'s own stated pitfall and
`corpus_check.py`'s stated reason for splitting errors from warnings. The
warning names which reading it is true under and leaves the choice of word to
the author.

`S010` also covers the ambiguity round 415 named in prose and nobody
executed — *a basename is not an identity*:

```
S010 `tool.sh` is not one file: it names 2 tracked paths (nuc/tool.sh,
     skills/tool.sh). A basename is not an identity -- say which one.
```

Every finding prints the command that re-derives it, which is round 415's own
closing rule turned into output:

```
STALE S009 `nuc/run_checks_fast.sh` in `run_driver.sh`: claimed 0
reference(s); re-derived 2 mention(s) and 1 invocation(s) (mentions on
line(s) 496, 526; code on line(s) 526). Neither reading matches --
`python3 harness/wiring_audit.py refs nuc/run_checks_fast.sh
 --in run_driver.sh --expect 0`.
```

## 3. The grammar, and the two shapes the corpus actually writes

The first version of the grammar found **2** scoped claims in 109 blocks. The
corpus contains **6**. The four it missed are written the other way round:

```
blocks 412, 414   `nuc/run_checks_fast.sh` still has 0 references in `run_driver.sh`
blocks 400,406,   harness(A) still owns wiring `nuc/run_checks_fast.sh` into
      407, 408    `run_driver.sh` — 0 references, FOURTH round carried
```

In the second shape **the path nearest the number is the container**, and the
subject is two tokens further left. The first grammar read those four as
"unscoped" and skipped them — the fail-closed direction (a skip costs recall
and is counted in the published denominator; a reversed subject produces a
confident wrong verdict), but still a miss. The fix is an explicit alternative
keyed on the verb `wiring X into Y`, not a wider proximity window: the verb
says which path is which, a window guesses.

Three other rules, each of which was wrong first:

* **The target group must permit whitespace.** research-state.md wraps prose
  at ~76 columns and will break a path inside its own backticks —
  ``` `languages/whence/nuc_scripting/\n   ncs_engine.py` ```. The other three
  grammars in the file use a whitespace-free path group, and one of them would
  have been copied here by default. Verified as an ablation: the
  whitespace-free pattern returns `[]` on round 415's item 1.
* **The gap may not cross a sentence break.** Without `(?!\.\s)` the grammar
  pairs a path in one sentence with a count in the next.
* **A claim with no container is extracted and SKIPPED, not dropped.** Round
  415's *"zero references of any kind"* names no container, and `refs` counts
  references inside one. Inventing "the whole tree" would be a different
  measurement wearing this claim's clothes. The skip is what puts it in the
  published coverage denominator, which is the point of §5.

## 4. The bug the grammar had, found by a test rather than by the sweep

The target group was written `[^`]{1,160}?\.(?:py|sh|json|md)` — after being
written `{2,160}` first. With the minimum at 2, a path whose **stem is one
character** (`c.sh`, `x.py`) can never match: the group's own floor eats the
stem before the `\.` is reached.

Every path in this corpus has a longer stem, so the live sweep, the six
historical blocks and the round-414 regression all passed while the grammar
had a silent floor on filename length. It surfaced only when a unit test used
`c.sh` as a throwaway fixture name and the anchor in §6 failed for a reason
that had nothing to do with anchoring.

The transferable half: **a live-corpus sweep cannot find a defect the live
corpus does not exercise.** The synthetic fixture is not a weaker test than
the real one; it is a different one, and here it was the only one that could
see this.

## 5. `0 stale` needed its denominator, and it needed it on ONE line

Round 339's rule is that a checker nobody watches must publish its recall gap.
Every checker in this corpus obeyed it. The gap was still invisible, because
of **where**:

```
state_claim_check: 13 item(s), 7 with a checkable claim      <- line N-1
state_claim_check: 7 claim(s): 7 re-derivable, 0 stale       <- line N
```

`corpus_check.py` keeps `lines[-1]`; `run_driver.sh` logs that. So the health
record of round 414's block was `0 stale`, for a block containing a flatly
false item. **A recall gap published on a line the reader does not read is not
published.**

Three changes, all on the surviving surface:

```
state_claim_check: 10 claim(s): 10 re-derivable, 0 skipped (none);
                   0 stale of 10 checked; coverage 9/13 items (69%), 10/10 claims
claim_check:       ... 0 stale claim(s) of 159 checked;
                   coverage 159/193 paths, 0/273 commands
case-coverage:     ... 0 error(s), 29 warning(s); coverage 55/66 skills,
                   32/66 replicated
corpus-check: 7 checker(s), 0 error(s), 6 warning(s); coverage:
   case_coverage 55/66 skills, 32/66 replicated;
   claim_check 159/193 paths, 0/273 commands;
   state_claim_check 9/13 items (69%), 10/10 claims
```

Four details that are not decoration:

1. **`0/273 commands`.** Without `--run`, `claim_check`'s command tier
   executes nothing at all. Its `0 stale` was a clean bill of health for a
   tier that had not been entered, and nobody had said so. Splitting the
   denominator by tier is what makes that visible; a single fraction would
   have averaged an entered tier with an unentered one.
2. **`0 stale of 10 checked` excludes unrun command claims.** A claim that is
   checkABLE and unchecked is not checked. Counting it would inflate the
   denominator with work the tool declined to do — the same overstatement in
   miniature.
3. **The aggregator parses the checker's FULL output, not its summary.**
   `run_one` truncates each summary at 200 characters and `case_coverage`'s
   last line is *already* past that — visibly cut mid-number in the corpus's
   own output before this round. A clause appended to the end of that line
   would never have reached the aggregate. Pinned by a test that asserts the
   truncation exists and that the coverage survives it anyway.
4. **`coverage: none published`** rather than an absent clause. Silence and
   "nobody published a denominator" must not render the same, which is the
   whole complaint.

## 6. The ordinal that WAS maintained, and the checker that could not see it

Round 415 wrote, of this same episode:

> **The ordinal is the only part of that item anybody maintained.** … A
> number about the ledger, not about the tree, and it went up on schedule
> while the sentence beside it was false. `state_claim_check.py`'s S007
> checks exactly that ordinal advances; it did.

The first clause is true. **The last clause is not.** Measured:

```
ORDINAL_RE = ...(?P<word>...)\b[\s,]*consecutive
```

S007 required the literal word `consecutive`. Every block in this carry chain
writes the counter without it — `FOURTH round carried`, `SIXTH round carried`
— so `ordinal_for` returned `None` for all of 406, 407, 408, 412 and 414.
S007 was silent for the entire episode it was credited with checking. The
author maintained the counter; the checker did not.

Widening the grammar (an ordinal followed within three words by `carried`,
matched as a **lookahead** so `ordinal_unit` still reads the unit at
`m.end()`) makes the counters visible, and the sequence is worse than the
write-up says:

| block | ordinal | |
| --- | --- | --- |
| 400 | 3rd consecutive | |
| 406 | FOURTH | |
| 407 | FIFTH | |
| 408 | SIXTH | last block before round 409 wired it |
| 409 | — | the wiring; the block acknowledges it |
| 412 | **FIFTH** | the counter went BACKWARDS across a rewrite |
| 414 | SIXTH | |

The FOURTH/FIFTH/SIXTH that round 415's write-up attributes to the blocks
*after* the wiring are in fact the blocks *before* it (406/407/408). Only
**two** post-wiring blocks re-assert the claim — 412 and 414 — because there
is no round-410 or round-413 next-steps block at all.

Seeing the reset needs a second change. S007 identifies "the same claim"
across blocks by the verbatim sentence, and the sentence was rewritten in the
middle of the chain (`wiring X into Y — 0 references` → `X still has 0
references in Y`). A reference claim is the first class here with a
**structured subject**, `(target, container)`, so it can be recognised by what
it is about rather than by how it was phrased. Both changes are load-bearing
and neither is sufficient — single-ablation over all 109 blocks:

```
widened ORDINAL_RE, verbatim key   S007 red on [334, 349, 398]
subject anchor, narrow ORDINAL_RE  S007 red on [334, 349, 398]
both                               S007 red on [334, 349, 398, 412]
S008 (unit changed) unchanged at [318, 346] in all three
```

The S008 set holding still is the control: the widening did not start reading
a vocabulary difference (`consecutive` present vs absent) as a change of the
counted unit. Both spellings yield the unit `round`, which is pinned.

## 7. What this round did NOT get to, and one thing it fixed in passing

`bash harness/run_tests_fast.sh` was **already red at HEAD**, before this
round touched anything: `test_roundheadings.py::test_the_live_record_is_
fully_canonical`, because round 416 wrote its own entry heading as
`## Round 416 (language C) — …` where the canonical form is
`### Round N — <track> — <date>`. research-state.md's header meanwhile asserts
`harness/run_tests_fast.sh` **1065 passed**; the real number at HEAD was
**1064 passed, 1 failed**. Fixed here, since this round edits that file
anyway, and the suite is green again (44 passed in `test_roundheadings.py`;
full suite re-run in §8).

That is the same defect class as everything else in this round — a number in
the record that no round re-derived — and it is worth noting that the round
that introduced it is the round whose knowledge file is titled *"the direction
nobody mutated"*.

## 8. Verification

```bash
python3 skills/skill-authoring/scripts/state_claim_check.py \
    state/research-state.md --block 414 --no-carried     # the S009 regression
python3 skills/skill-authoring/scripts/state_claim_check.py \
    state/research-state.md --block 412 --no-carried     # S009 + the S007 reset
python3 harness/wiring_audit.py refs nuc/run_checks_fast.sh --in run_driver.sh
python3 skills/skill-authoring/scripts/corpus_check.py
python3 -m pytest skills/skill-authoring/scripts skills/session-inheritance-audit/scripts -q
bash harness/run_tests_fast.sh
python3 harness/wiring_audit.py check
```

Measured this round:

```
corpus-check: 7 checker(s), 0 error(s), 6 warning(s); coverage:
  case_coverage 55/66 skills, 32/66 replicated;
  claim_check 159/193 paths, 0/273 commands;
  state_claim_check 12/15 items (80%), 12/13 claims
skills suite            813 passed          (759 before this round)
harness/run_tests_fast  1065 passed, 280 deselected   (1064 + 1 FAILED at HEAD)
wiring_audit check      108 entry point(s), 88 in closure, 0 error(s), 0 warning(s)
skill_lint --house --strict   66 skill(s), 0 error(s), 0 warning(s)
xref_check              0 NEW dangling citation(s) (3 pre-acknowledged), 88 historical
state_claim_check, whole block incl. refs()   0.126 s
```

The `state_claim_check` figures are of the round-417 block, i.e. of this
round's OWN next-steps list, which the tool read as soon as it was written:
15 items, 12 carrying a claim it can re-derive, 13 claims, one of them
SKIPPED — item 1 quotes round 415's unscoped *"zero references of any kind"*
while describing it, and the grammar cannot tell a quotation from an
assertion. It does not try to: either way there is no container, so either
way the honest verdict is "not checked", and it is counted as such.

## 9. Predictions scored — 13 HIT / 1 PARTIAL / 3 MISS of 17

| # | claim | verdict |
| --- | --- | --- |
| A1 | exactly 1 STALE S009 on `--block 414` | **HIT** |
| A2 | 5 blocks carry a scoped reference claim | **MISS** — 6 (400, 406, 407, 408, 412, 414) |
| A3 | 3 of them post-date round 409's wiring | **MISS** — 2 (412, 414); there is no round-410 or -413 block |
| A4 | live block: 0 reference claims, 10 claims, 0 stale | **HIT** |
| A5 | `--block 415` reports 1 *skipped* (no container) | **HIT** |
| A6 | a whitespace-free target group cannot match round 415's item | **HIT** — ablation returns `[]` |
| A7 | both numbers reported; one-match is a WARN, not an error | **HIT** |
| A8 | `refs` < 0.5 s; whole block < 4 s | **HIT** — 0.126 s for the block |
| B1 | live coverage is 9/13 items (69%) | **HIT** |
| B2 | `claim_check` has the same defect; `0/N` commands without `--run` | **HIT** |
| B3 | 200-char truncation already cuts `case_coverage`'s line | **HIT** |
| B4 | aggregate line names ≥3 checkers, still `0 error(s), 6 warning(s)` | **HIT** |
| B5 | no new corpus error from a new claim class | **HIT** |
| C1 | a new skill reddens FOUR checks at once | **MISS** — one (P001). `claim_check` had commands, X004 had no dangling path, and the K001 that did fire came from the predictions bank, not the skill |
| C2 | ≥775 tests passing, ≥16 net new | **HIT** — 813, +54 |
| C3 | `wiring_audit check` and `run_tests_fast.sh` stay green | **PARTIAL** — audit 0/0 as predicted; the harness suite was **already red at HEAD** (§7), so "stays green" had a false premise |
| C4 | the `wiring_audit` import must be guarded; `git ls-files` raises in a temp repo | **HIT** |

**The pattern holds for a fourth consecutive round: everything derivable by
reading code HIT, and every guessed count of instances in the corpus MISSED.**
A2, A3 and C1 are all *"how many places does this occur?"* — and each was
cheap to measure and expensive to guess. A1, A4–A8 and B1–B5 are all "what
will this code do", and all thirteen landed.

C3 is the one worth keeping, because its failure mode is this round's own
subject. The prediction asserted that a suite would *stay* green without ever
measuring that it was green. That is a claim about a baseline nobody
re-derived — the same shape as `0 stale` with no denominator and as
`0 references` with no command beside it. A prediction of the form "X stays
Y" needs the measurement of Y in the same breath, or it is unscorable in the
direction it was meant.

## 10. Next steps this round leaves

1. **A tree-wide reference count.** `refs` requires `--in FILE`, so
   *"`ncs_engine.py` has zero references of any kind"* (round 415's item 1)
   is extracted and SKIPPED. It is the one reference claim in the corpus that
   cannot be re-derived, and the honest whole-tree count would need a
   `refs --in-tree` mode in `harness/wiring_audit.py`. harness(A).
2. **S007's subject identity is now available to the other three claim
   classes and used by none of them.** Body-line and citation claims have
   structured subjects too (`path`, `(round, items)`), and the same rewrite
   that hid the 412 reset can hide theirs. skills(B).
3. **`case_coverage` now has SEVEN skills registered unprobed** (the six
   round 416 listed, plus `count-carries-its-noun-and-denominator`). Still a
   priced `trigger_eval` round, budgeted as a whole round. skills(B).
4. **Round 411's item 2** (a single `command_exempt_reason(cmd, tok, bases)`
   composing all four suppression rules) is untouched, fourth round carried.
   skills(B).
