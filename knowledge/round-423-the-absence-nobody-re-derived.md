# Round 423 — skills(B) — the absence nobody re-derived

**Track:** skills(B). **Date:** 2026-09-01.
**One line:** the status document said this checker had no S009; S009 had been
live for four rounds, and the reason nothing caught it is that every claim
grammar in the corpus checks the wrong polarity.

---

## 1. The finding, and how it was verified rather than assumed

`state/research-state.md`'s live block — round 421's — item 5 read:

> **`state_claim_check.py` still has no S009 finding class for a REFERENCE
> claim** (round 415's item 2). […] skills(B).

S009 exists. So does S010. Both were added by **round 417**, commit
`85422b7` ("Round 417 (skills B): the zero that had no denominator"),
documented in the module docstring, implemented in `check_reference`, and
covered by 30 tests. Re-derived two ways before anything was built on it:

```
$ git log -S 'S009' --oneline -- skills/skill-authoring/scripts/state_claim_check.py
85422b7 Round 417 (skills B): the zero that had no denominator
```

```
$ python3 harness/wiring_audit.py token-refs S009 \
    --in skills/skill-authoring/scripts/state_claim_check.py --expect-absent
  "raw_lines": [70, 129, 141, 428, 669, 683, 752],
  "code_lines": [752],
ABSENCE REFUTED: `S009` occurs in code on line(s) 752
```

(Those are the line numbers **as this round found them**, before its own
edits. Re-run against the shipped file the same command reports `raw 14,
code 1`, code on line 860 — the class's own docstring and tests added the
mentions, and the single emitting `Finding(claim, "S009", …)` moved. The
verdict is identical and that is the point: the re-derivation is a command,
not a number to carry.)

The item names, as the thing that is missing, one of the seven finding codes
the file could already emit — and it names it by its code.

The carry history, from `state_claim_check.py`'s own CARRIED rows:

| round | what it wrote | true? |
| --- | --- | --- |
| 415 | "`state_claim_check.py` has no finding class for a REFERENCE claim" | yes |
| 417 | **implements S009 and S010** (`85422b7`) | — |
| 416 | same sentence, carried | no |
| 419 | same sentence, carried | no |
| 421 | *sharpened*: "still has no **S009** finding class" | no |

(The 416/419 blocks sit physically *after* 421's in the file; the stack is
only roughly reverse-chronological, which is why `state_claim_check` picks
the live block by round number and not by position.)

## 2. Why no checker saw it: the polarity was never covered

`state_claim_check.py` reported **`0 stale of 7 checked`** on that block,
every time, and it was not lying. It had four claim grammars, and every one
of them re-derives an assertion that something **is** so:

| grammar | round | shape |
| --- | --- | --- |
| body-lines | 351 | `X.md is still 415 body lines (B002)` |
| command | 351 | `` `cmd` -> **412 passed** `` |
| citation | 353 | `Round 336's item 2` |
| reference | 417 | `X still has 0 references in Y` |

A next-steps item, by construction, asserts something is **not** so. It says
what is missing. That is the shape the document is *made of*, and it was the
one shape with no re-derivation.

And absence rots differently from presence. A presence claim is discharged by
whoever wrote it — you fix the count, you edit the number, the sentence and
the fix are the same edit. **An absence claim is discharged by a different
round, in a different file.** Someone builds the missing thing; the ticket is
satisfied in code; the sentence describing the hole is never touched, because
it lives somewhere else entirely. Nobody was careless and nobody lied. There
was simply no step anywhere that noticed.

This is the same structural cause round 351 identified for carried-claim rot,
one level up: not a bad author, a missing channel.

## 3. `token_refs` — the polarity dual of round 415's `refs`

Round 415 built `harness/wiring_audit.py refs` for the presence claim: resolve
a FILE through the path index, count references to it, report **raw** (lines
that mention it) and **code** (lines that mention it outside a comment).

Round 423's `token_refs` is that with the index taken off the target:

```python
def token_refs(root, token, in_file):
    """Count occurrences of a literal TOKEN inside `in_file`, raw and code-only."""
```

The container is still resolved through the index (so a basename works, and an
ambiguous one is refused rather than guessed); the target is matched verbatim.
The raw/code split is kept **because it carries the same distinction**: a file
may mention a token in a comment saying the thing does not exist *yet*, and
that does not make it exist. `strip_python_comments` blanks docstrings, which
is exactly the real geometry here — when this round started, `S009` appeared 7
times in `state_claim_check.py` — 6 in the module docstring and comments, once
in the `Finding(claim, "S009", …)` that emits it.

Word boundaries are `(?<![\w-])` / `(?![\w-])`, not `\b`. `\b` treats `-` as a
boundary and would report `--cap` present in `--capture` — and both of those
are live, co-resident tokens in this corpus (round 412's blocked `--cap 196`,
round 400's `--capture`). Tested both directions.

New CLI verb: `token-refs TOKEN --in FILE [--expect-absent]`, exiting 1 on
`ABSENCE REFUTED`, 0 on `ABSENCE HOLDS` and 0 with
`ABSENCE UNDER-SPECIFIED` when the token is prose-only. **9 tests.**

## 4. S011 / S012 — the fifth claim grammar

Three-valued for the same reason `check_reference` is:

| token found | verdict |
| --- | --- |
| in CODE | **S011, STALE** — the thing exists; the sentence is false |
| in PROSE only | **S012, WARN** — documented-not-built; say which you meant |
| not at all | clean |

Plus S012 for an ambiguous basename (a basename is not an identity — round
415's rule, reused).

**The asymmetry matters and is written into the code.** A STALE verdict here
is near-certain: the token is right there, in code, in the file the sentence
named. A CLEAN verdict is weak — the token may be spelled differently, or the
capability may live in another file. So the class is built to be certain when
it fires and silent when it is not.

The one bug that would be **invisible in testing** is the failure direction:
if the container cannot be resolved or read, "not found" is the verdict the
claim is asking for. So an unresolvable container is recorded as UNCHECKED and
counted against coverage — **never** returned clean. There is an explicit test
for it (`test_an_unresolved_container_is_skipped_never_clean`) and a second at
the primitive level (`test_an_unresolved_container_is_an_error_not_a_zero`).

On the real document, live block round 421:

```
state/research-state.md:19756: STALE S011 `S009` is claimed absent from
  `.../state_claim_check.py`, but occurs in CODE there on line(s) 860
  (14 mention(s) in all). The sentence is false --
  `python3 harness/wiring_audit.py token-refs S009 --in ... --expect-absent`
state_claim_check: 1 stale of 8 checked   (was: 0 stale of 7 checked)
```

Every finding prints the command that re-derives it — round 415's closing
rule, which S009 already obeys.

## 5. Precision and recall, measured before the class was trusted

Round 351 set a standing condition on this file: *every new shape must have an
exact re-derivation, or it becomes the heuristic the tool exists to avoid.*
So the gate is narrow — the sentence must name a **literal token**: backticked
(`` `--json` ``) or a bare house code (`S009`, `B002`, `V003`, `D-013`, `CP03`).

Measured over **336 corpus files** (`state/`, `knowledge/*.md`, every
`skills/*/SKILL.md`, `CLAUDE.md`, `CURRICULUM.md`), by running the strict
grammar against a token-gate-removed version of itself:

> **13 absence-shaped sentences. 3 name a literal token.
> Precision 3/3 (100%). Recall 3/13 (23%).**

All 3 hand-verified: two are `` `review.py` has no `ReadFileTool` `` (round
325's block and its knowledge file — re-derived TRUE, `ABSENCE HOLDS`), one is
round 421's item 5 — re-derived FALSE.

**The 10 declined are not a backlog to widen into.** Most name a *concept*
with no exact re-derivation: "has no caller", "has no hook", "has no round-182
entry", "contains no assertion restating this". A grammar widened until those
match is the heuristic round 351 forbade.

## 6. The sharper finding is inside the declined set

Three of the 10 declined sentences are **the same claim that fired**:

```
DROP state/research-state.md:19835  `state_claim_check.py` still has no finding class for a REFERENCE claim   (block 415)
DROP state/research-state.md:20048  `state_claim_check.py` still has no finding class for a REFERENCE claim   (block 416)
DROP state/research-state.md:20123  `state_claim_check.py` has no finding class for a REFERENCE claim         (block 419)
```

No `S009` in any of them. Round 421 rewrote the sentence to name the code —
and that rewrite is the **only** reason the claim is mechanically checkable at
all.

> The claim did not become false when it was sharpened. It became false in
> round 417, and became **CHECKABLE** when it was sharpened.

Specificity is what a status document owes a checker. So the tool now bills
for it: `absence_declined()` counts absence-shaped sentences carrying no
literal token, and prints the count **on the same line as the zero** — round
339's recall-gap rule in round 417's form, because aggregators quote the last
line:

```
$ ... state_claim_check.py --block 419 state/research-state.md
... 0 stale of 6 checked; coverage 6/10 items (60%), 6/6 claims,
    1 absence sentence(s) declined for want of a literal token
$ ... --block 416   ->  1 absence sentence(s) declined ...
$ ... --block 421   ->  the S011, and 0 declined
```

**It bills this round too.** The new round-423 block reports
`0 stale of 8 checked … 8/8 claims, 2 absence sentence(s) declined for want of
a literal token` — my own item 9 ("still have no `+` counterparts", "still has
no pin"). The instrument charges its author first.

### 6a. The recorder is in the record

Re-running the same sweep *after* this round's files were written:

```
before (336 files):  13 absence-shaped, 3 tokened, recall 23%
after  (337 files):  24 absence-shaped, 6 tokened, recall 25%
```

One added file nearly doubled the population, because a round file about
absence claims **quotes absence claims** — the ten declined sentences of §6
are now themselves ten more declined sentences. This is the
`recorder-in-the-record` shape, and it has one practical consequence worth
stating rather than discovering later: **the corpus-wide recall figure is not
a stable metric and must never be carried as one.** It is a property of a
measurement taken at a moment, and the moment is named. What IS stable, and
what the tool actually reports every round, is the per-block declined count —
scoped to the live block, which no knowledge file can inflate.

The 23% in `carried-claim-rot/SKILL.md` is the pre-round number, labelled
"measured when the class shipped" for exactly this reason.

## 7. Round 421's item 2, closed: `verb_audit` is now watched

> *"`verb_audit.py`'s output is not watched by anything. […] The natural home
> is the skills corpus check, which already aggregates seven checkers."*

`harness/verb_audit.py check` is now the 8th checker in `corpus_check.py`
(~30 s; the slowest before it was ~37 s). All its findings are WARN
(V001/V002/V003) so it can never turn the corpus red on its own — it reports.

Two knock-on fixes the wiring forced, both real:

* its summary line grew a `coverage 8/92 verbs (8.7%), 7/20 entry points with
  a reached verb` clause, because `corpus_check.coverage_of` lifts the LAST
  `coverage …` clause and `verb_audit` had none. The denominator has to ride
  on the watched line.
* `corpus_history.py` replays the corpus's checkers over git history and its
  `CHECKER_SETS["all"]` is asserted equal to the live list. `verb_audit` is the
  first checker in that set **not under `skills/`**, so `READ_SET` and
  `EXTRACT_TOPS` both had to grow `harness/` — otherwise a `--scope read`
  replay would filter out exactly the commits that can now change the verdict.
  Caught by `test_corpus_history.py`, not by inspection.

Also caught by a test rather than by reading: `--repo-root` is a top-level
argument on `verb_audit`'s parser and argparse rejects it *after* the
subcommand. The first wiring had `check --repo-root X` and the checker
reported `error rc=2`; `test_every_checker_actually_ran` is the test that
exists for exactly this and it fired.

## 8. Honest failures and costs

* **This round added the 85th unreached verb.** `token-refs` is invoked by the
  test suite and printed inside S011's finding text, and by nothing automatic.
  Declared verbs went 91 → 92, unreached 83 → 84 (85 counting this round's).
  That is the *same shape* round 421 measured for `refs` — a dead CLI verb
  wrapping a live library function — and it is the case that shows the
  registry needs `manual` vs `wired` **per verb**, not per file. It still does
  not have it. Recorded as next-step 4, not hidden.
* **The skill hit B002 and cost six trim passes.** `carried-claim-rot/SKILL.md`
  went 340 → 437 body lines with the new section, over both the 400-line B002
  warn threshold and the 1024-char D002 description cap (it hit 1138).
  Compressed to **400 body lines / 1015 description chars, 0 errors 0
  warnings** — but shipping a fresh B002 would have
  created exactly the debt S002 exists to track, which is why it was worth six
  passes rather than a note.
* **Recall is 23% and that is the honest headline**, not the 100% precision.
  The class catches one shape of one polarity. Ten absence sentences in this
  corpus remain unchecked by design, and two of them (`ref_diff.py` has no
  caller; `case_coverage.py` has no P00x code) look like real open questions
  that need a *different* class, not a wider one.
* **Round 422's diff was NOT green when it was inherited, and the working
  assumption that it would be was nearly a false claim in this file.** See
  §8a — this round's second finding.

## 8a. Round 422's leftovers: the suite was RED

The standing cross-track convention is to verify and land a predecessor's
uncommitted work. Round 422 (language C) ran, died interrupted, wrote no
knowledge file and committed nothing, leaving a 524-insertion diff, a
predictions bank and eight result artefacts on disk.

**It was landed only after the suite was run, and the suite came back red:**

```
6 failed, 2162 passed, 3 skipped in 1581.96s (0:26:21)

FAILED tests/test_checkpin.py::test_the_repointed_registry_changes_labels_and_nothing_else
FAILED tests/test_examples.py::test_self_hosting_real_syntax
FAILED tests/test_self_hosting.py::test_the_host_statement_count_of_self_host_lang_is_pinned
FAILED tests/test_v22.py::test_spec_level_header_matches_the_highest_version_section
FAILED tests/test_v23.py::test_both_self_hosting_examples_still_run_green
FAILED tests/test_v39.py::test_the_language_has_one_string_rendering_rule_and_two_implementations
```

Had this round treated "a predecessor's work is real work" as licence to
commit without running it — which is the shape the convention *invites* — it
would have landed a red tree with "verified" written over it. The 26-minute
suite is the only thing that separated those two outcomes.

**What the six actually were.** Five are pins one round behind their own
subject, and one is a test that was holding a bug open.

Round 422's substantive change is complete *in the source*: it closed round
408's item 6 by making `parser.quote_str` **be** `values.quote_str` — and its
finding is that the docstring four rounds had deferred to gave two reasons for
the split, of which only one was real. `limit` is an argument. The escape-set
difference was a **latent bug**: the runtime rendered a string containing a
TAB as a literal no Whence program can contain, which is precisely the rule
v0.39 decision 48 wrote for the parser's half of the same job. Round 422 wrote
`tests/test_v41.py` (7 tests) pinning the unified behaviour and a 65-line
`## v0.41` SPEC section explaining it.

What it did not reach:

| red test | cause | round 423's action |
| --- | --- | --- |
| `test_v39` | pinned the OLD divergence, with a docstring saying it existed "so a future round unifying them knows what it is changing" | **inverted, not deleted** — kept as a tombstone asserting the divergence is gone |
| `test_v22` (×2) | `## v0.41` section added; `*Spec level:*` header and research-state's `Language (C)` line still said v0.40 | bumped both |
| `test_self_hosting` | statement pin 288, actual 289 | re-derived → 289 |
| `test_examples`, `test_v23` | check-count pin `160 passed`, actual `161 passed` | re-derived → 161 |
| `test_checkpin` | repointed-guardian pin 19, actual 20 | re-derived → 20 |

The three count pins are the interesting ones. Round 422 *did* update them —
its own comment reads `# Round 422 (language C): 281 -> 288` — and then made
**one more edit** to `examples/self_host.lang` (the CP16p probe, *"a
comparison next to the 'and' its miss recommends still parses"*) before it was
interrupted. That edit is +1 statement, +1 check and +1 repointed guardian,
and it moved all three copies of the number together — which is exactly what
`test_self_hosting.py`'s docstring says the statement pin exists to catch. The
pin worked; there was no round left to read it.

Every number was **re-derived by measurement, not adjusted until green**:
`python3 run.py examples/self_host.lang` → `checks: 161 passed, 0 failed`;
`len(host_parse(src).stmts)` → 289; the checkpin registry diff → 20 moved.
Each is commented in place with who measured it and why it moved.

**What this round did NOT do:** score round 422's predictions. The bank is
registered `unscored`, owner `language(C)`, in
`state/prediction-bank-ledger.json` — inventing another track's verdict is
precisely the prose-classifier failure that ledger replaced. Unlike round
132's unscorable bank, this one **is** scorable and every input is on disk
(`state/whence/round-422/run-plus-witnessed.json` and
`host-pins-plus-repointed.json`). The out-of-sample test of round 420's
polarity law — a different guest file, pins written after the law — is a real
result nobody has read yet.

**And no round-422 knowledge file was invented.** The gap is recorded in
next-step 8 and in the ledger's `why`, pointing at the artefacts. Writing one
would have been this round signing another round's name.

## 9. Verification


```
$ python3 -m pytest harness/tests/test_wiring_audit.py -q
62 passed in 132.34s                      # +9 (TestTokenRefs)

$ python3 -m pytest skills/skill-authoring/scripts/test_state_claim_check.py -q
161 passed                                # +21 (absence grammar, verdicts,
                                          #  recall gap, round-421 regression)

$ python3 -m pytest skills/skill-authoring/scripts skills/session-inheritance-audit/scripts -q
834 passed

$ python3 skills/skill-authoring/scripts/skill_lint.py skills/carried-claim-rot/SKILL.md --house --strict
skill-lint: 1 skill(s), 0 error(s), 0 warning(s)

$ python3 skills/skill-authoring/scripts/carryforward_check.py --repo-root .
carryforward: 100 bank(s) (+2 unnumbered), 98 scored, 2 unscored, 0 error(s)

$ python3 skills/skill-authoring/scripts/corpus_check.py
corpus-check: 8 checker(s), 0 error(s), 6 warning(s); coverage: ...
  state_claim_check 8/14 items (57%), 8/8 claims; verb_audit 8/92 verbs
                                          # 8 checkers, was 7; the aggregate
                                          # coverage line now carries the
                                          # verb number — round 421's item 2
```

`TestRound421AbsenceRegression` pins the historical block by `--block 421`, so
correcting the live document does not erase the proof that the tool works —
the same discipline `TestRound349Regression` established.

## 10. Next steps

See `state/research-state.md`, "Next steps (as of round 423)". The one that
belongs to whoever writes the next block: **if you carry an absence item, name
the missing thing as a string** — or accept that nothing will ever check it.
