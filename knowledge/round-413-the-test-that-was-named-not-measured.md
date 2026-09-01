# Round 413 (SWE-loop D) — the guardian that was named, not measured

**Track:** D (autonomous SWE: the harness turned on our own code)
**Subject:** `harness/swe/guardpin.py` (new), `state/swe/guard-pins.json` (new),
`harness/swe/mutation.py`, `languages/whence/curecheck.py`,
`languages/whence/tests/{test_lexer_guest_parity,test_v03,test_v24,test_v26,test_v32}.py`

`state/research-state.md`'s next-step item 6 has carried since round 411:

> a mutation-style check that deletes a pinned call and requires a specific
> test to go red (harness A or SWE-loop D)

with two motivating instances one abstraction layer apart — round 411's
`claim_check` door that never asked the gate, and round 412's test that
asserted the right verdict string while the branch it was named after was
unreachable. This round built it, pointed it at eleven load-bearing calls in
this repo, and the run produced three things: a **confirmation** of what the
instrument was built to see, a **survivor** with a real behavioural
differential behind it, and a **blocked harness** nobody had noticed.

---

## 0. Headlines

1. **A structural pin and a behavioural pin give opposite verdicts on the
   same call, and which one you get is decided by whether the call's TEXT
   survives your edit.** Round 411's `test_every_c001_site_consults_the_
   exemption_gate` is GREEN when the gate call still runs and only its
   ANSWER is discarded (`misattributed` — five other tests in the same file
   go red), and RED when the identifier is removed (`guarded`). Its own
   docstring said "Deliberately coarse — it cannot prove the call is on the
   right path." That sentence is now measured rather than asserted.

2. **A survivor with a real differential: `mark_tails(body)` on the Whence
   parser's ANONYMOUS-fn branch can be deleted and the entire file named
   after it stays green.** `test_parser_marks_tails_only_inside_fn_bodies`
   parses only `fn name(...)`. Deleting the other call:

   ```
   let go = fn(i, acc) { if i == 0 { acc } else { go(i - 1, acc + i) } }
     intact   peak_depth  1   tail_calls 300
     deleted  peak_depth 50   tail_calls   0     (the named-fn form: unchanged)
   ```

   Two doors, one behaviour, one named guardian — round 411's shape, caught
   before it was a bug rather than 71 rounds after. Killer written, test
   added, pin re-measured.

3. **`mutation_test` against `languages/whence` — this track's primary
   target, and `DEFAULT_TEST_CMD`'s exact command — was RED at the baseline
   gate and had been silently unusable.** Not a mutation result: the
   pre-flight raised `BaselineNotGreen` before generating a single mutant.
   Cause: the whence suite asks "what does git track in `examples/`?" in five
   independent places, each deriving its own root from `__file__`, and none
   of them consults `AGI_RESEARCH_ROOT` — the variable `harness/swe/proc.py`
   exports into every such subprocess for precisely this, and which four
   other files in the same tree already read.

4. **The instrument's own first draft was wrong, and `locate` caught it
   before a single test ran.** `_stmt_parents` kept the FIRST enclosing
   statement `ast.walk` yielded; `ast.walk` is breadth-first, so "first" is
   "outermost". A two-token edit re-unparsed whole `for` loops, deleting
   eleven lines of comment and renormalising every string. Not a wrong
   answer — a wrong EXPERIMENT, since a source-grep pin reads exactly the
   text the edit destroyed.

---

## 1. What a guard pin is, and why it is not mutation testing

`harness/swe/mutation.py` has asked one question since round 5: **did the
suite go red?** That is the right question for coverage and the wrong one
for the failure this program keeps finding, which is never "nothing covers
this line" but *"the test we NAME for this is not the thing that catches
it"*. Its six operators (cmp/bool/not/const/arith/ifneg) also contain no
operator that removes a call at all.

A **guard pin** is a declaration with three parts:

```json
{
  "id": "GP02",
  "path": "skills/skill-authoring/scripts/claim_check.py",
  "func": "check_paths",
  "edit": "call_value", "target": "token_exempt_reason",
  "becomes": "none", "keep_call": true,
  "test": "…/test_claim_check.py::TestExemptionGateHasOneHome::test_every_c001_site_consults_the_exemption_gate",
  "why": "…"
}
```

a **site**, a **falsifying edit**, and **the test that is claimed to catch
it**. The runner applies the edit in a throwaway copy and requires that test
to go RED.

### Located symbolically, never by line

`path` + `func` + `target` + `occurrence`. A line number rots silently and
would have the tool confidently mutating whatever moved into its place; a
symbol that moved raises `PinUnlocatable` and the pin reports `unlocatable`.
`find_function` refuses an ambiguous name outright rather than taking the
first definition `ast.walk` reaches — `Class.method` disambiguates.

### The verdicts

| verdict | meaning |
|---|---|
| `guarded` | the named test went red. The claim holds. |
| `misattributed` | the named test stayed GREEN and the wider suite went red. Something guards it; not what the record says. |
| `unguarded` | named test green AND suite green. Nothing in the declared scope notices. |
| `wrong_reason` | red, but the failure text does not contain the pin's declared `expect_in_failure`. Round 412's shape. |
| `nonviable` | the pin's own test is RED on the UNMUTATED copy. Round 349's rule, per pin. |
| `inconclusive` | pytest exited 2–5: the suite never ran. |
| `unlocatable` | the site is gone. |
| `equivalent` | the declared edit provably cannot change behaviour (see §3). |

`score` is `guarded / (guarded + findings)`. Errors are excluded from the
denominator and reported separately on purpose: an unlocatable pin is a fact
about the registry, not about the suite, and averaging the two hides both.

### It is cheap when the pin holds

A `guarded` verdict costs the named test twice — one baseline, one mutant —
and never runs the suite. Only a pin whose named test stays green pays for
the wider scope. Baselines are memoised per (target, args), so a registry
with thirteen pins over six files runs six baselines, not thirteen.

---

## 2. The knob the whole instrument turns on: `keep_call`

| edit | source text | behaviour |
|---|---|---|
| `keep_call: false` — replace the call with the literal | the name is **gone** | changed |
| `keep_call: true` — `(CALL, LITERAL)[1]` | the name is **still there**, the call still runs | value discarded |

A test that greps the source for `gate(` passes the second and fails the
first. A test that exercises the behaviour fails both. Running the same pin
both ways is therefore a *measurement of what a structural pin buys*, and
the two verdicts differing is not a bug in either — it is the answer.

Round 411 fixed a real bug (`check_paths`'s `cd` branch had its own regex and
never asked the exemption gate) and pinned it with a structural test that
says, in its own docstring:

> Deliberately coarse — it cannot prove the call is on the right path. What
> it does prove is that a new C001 site cannot be added in ignorance of the
> gate's existence.

GP02 and GP03 are the same call and the same test, differing only in
`keep_call`:

```
GP02  keep_call=true    exempt = (token_exempt_reason(target), None)[1]
      -> the NAMED test stayed green; 5 other tests in the same file went red
         (test_a_false_cd_positive_used_to_mask_every_token_behind_it,
          test_the_live_corpus_line_that_provoked_this,
          test_the_old_cd_branch_called_a_placeholder_target_stale,
          test_the_old_cd_branch_called_a_scratch_target_stale, +1)
      -> misattributed

GP03  keep_call=false   exempt = None
      -> the named test went RED
      -> guarded
```

Both verdicts are correct. The docstring's claim is now measured rather than
asserted, and the record can say which test actually stands between this
repo and round 411's bug returning: not the structural one.

The mirror pin GP01 — the same gate call at the *first* door, inside
`path_tokens` — is `guarded` by `test_skips_placeholder_tokens`, and
`check_sole` reports four other tests catch it too. The two doors round 411
reconciled are now measurably in different states with respect to their pins.

---

## 3. Three ways this instrument could have manufactured its own findings

All three were closed before the first verdict was read. They are the most
transferable part of the round.

### (a) The splice that was minimal in intent and maximal in effect

`_stmt_parents` maps every node to its enclosing statement so `apply_edit`
can re-render the smallest thing containing the call. The first draft wrote

```python
if child is not node and id(child) not in out:      # keep the FIRST seen
    out[id(child)] = node
```

and `ast.walk` is **breadth-first**, so the first statement seen is the
*outermost* one. Every call in the registry resolved to its enclosing `for`
loop or `if`, and `apply_edit` faithfully re-unparsed that whole block. The
diff for GP02 — a two-token edit — deleted eleven lines of comment and
renormalised every string quote in `check_paths`.

That is not a wrong answer. It is a **wrong experiment**: this module's
entire job is telling a source-grep pin from a behavioural one, and an edit
that deletes the file's comments changes the very text a source-grep pin
reads. It would have produced findings shaped exactly like real ones.

Caught by reading `guardpin locate`'s diffs before running a single test,
which is what that mode is for. Overwriting instead of keeping-the-first
leaves the deepest statement as each node's parent, and the fix is one
`and`-clause.

Then a second pass went further. For `call_value` the edit now replaces the
**call's own source span**, computed from `lineno/col_offset/end_lineno/
end_col_offset`, and `keep_call`'s replacement is built from the ORIGINAL
text — so not one byte outside the call itself changes. No `ast.unparse` runs
at all on that path. `col_offset` is a UTF-8 **byte** offset and this repo's
sources are full of em-dashes, so the slice is done on the encoded line and
decoded back; `test_the_span_slice_is_utf8_byte_correct` pins it.

Before and after, on GP05:

```
-    if is_pytest_cmd(cmd):                    ← statement splice: also ate
-        # Whitelist, not blacklist. Under pytest exactly one positive code     the 4-line comment
-        # means "a test failed"; treating any OTHER code as a kill is the
-        # assumption that produced this whole defect, so an undocumented
-        # code (a plugin's own, say) is no evidence rather than a free kill.
-        return "killed" if returncode == _PYTEST_TESTS_FAILED else "error"
+    if (is_pytest_cmd(cmd), False)[1]:
+        return 'killed' if returncode == _PYTEST_TESTS_FAILED else 'error'

-    if is_pytest_cmd(cmd):                    ← span splice: one line, and
+    if (is_pytest_cmd(cmd), False)[1]:          nothing else in the file moves
```

### (b) The equivalent mutant that would have read as a finding

`keep_call: true` on a **bare** `f(x)` statement is `(f(x), None)[1]`: the
same call, the same side effects, a discarded value nobody read. Every test
stays green and the tool would report `unguarded` about a perfectly guarded
call. `apply_edit` now raises `EquivalentEdit` for that shape and the verdict
is `equivalent`, an ERROR rather than a finding, with the message naming
`drop_stmt` as the edit that was meant.

> An equivalent mutant reported as a finding is worse than no instrument: it
> is a finding-shaped artefact of the tool's own edit.

### (c) The timeout that would have been scored as a kill

`classify_mutant_run` maps a signal death to `killed` — correct for
mutation, where a segfaulting mutant IS a caught behavioural difference. For
a guard pin run under a wall-clock cap it is not: `languages/whence/tests`
holds a 926-second slow tier, and a 300-second cap firing on it would be
recorded as "the suite went red", i.e. **as the pin holding**. Pins therefore
carry a `timeout_s` floor and a `suite_args` list (`-m "not whence_slow"`),
and `suite_args`' docstring states the reason:

> A cap that turns "we did not look" into "we looked and it was caught" is
> the round-349 failure with a different clock.

---

## 4. The run: eleven pins over four subsystems

Registry `state/swe/guard-pins.json`, `--workers 2`, one CPU, **162 s total**
for the eleven. Every pin names a call some round's write-up already
described as load-bearing, and every `why` field quotes that round.

```
GP01  guarded        claim_check.path_tokens      token_exempt_reason -> none, call kept   sole=False
GP02  misattributed  claim_check.check_paths      token_exempt_reason -> none, call kept   —
GP03  guarded        claim_check.check_paths      token_exempt_reason -> none, text gone   sole=False
GP04  guarded        mutation.mutation_test       drop `raise BaselineNotGreen`            sole=False
GP05  guarded        mutation.classify_mutant_run is_pytest_cmd -> false, call kept        sole=False
GP06  guarded        campaign._run_one            drop `self._require_baseline()`          —
GP07  guarded        perturbation.power_floor     drop `raise … needs N > 0`               sole=True
GP08  guarded        perturbation.attribution_…   best_case_p -> false, call kept          sole=False
GP09  guarded        perturbation.attribution_…   power_floor -> none, call kept           sole=False
GP10  guarded        parser.Parser.statement      drop `mark_tails(body)`                  sole=False
GP11  unguarded      parser.Parser.primary        drop `mark_tails(body)`                  —

11 pins, 9 guarded, 2 findings, 0 errors, score 82%
```

Two things in that table are worth more than the score.

**`sole=True` appears exactly once.** `check_sole` re-runs the suite with the
named test *deselected*, which answers a question `guarded` cannot:
`power_floor`'s `N > 0` guard is held up by one test and nothing else in
`nuc/tests/test_perturbation.py`. The other eight guarded pins each have
between one and nine additional tests that also go red — including
`best_case_p`, where **nine** others catch it. `guarded` says the named test
caught it; it does not say the named test is load-bearing, and those are
different facts about a suite.

**The two findings are the two pins whose named guardian was chosen for its
NAME.** GP02's guardian greps the source; GP11's guardian is called
`test_parser_marks_tails_only_inside_fn_bodies` and parses only one of the
two forms that have fn bodies. Nine pins whose guardian was chosen for what
it *exercises* all held. That is a small sample and not a law, but it points
the same way as rounds 411 and 412: the failures cluster where the name did
the work.

---

## 5. The survivor, the killer, and the differential

GP11 is the finding. `mark_tails(body)` appears twice in
`languages/whence/whence/parser.py`:

* line 1282, `Parser.statement` — the `fn name(...) {...}` branch (v0.3);
* line 2433, `Parser.primary` — the anonymous `fn(...) {...}` literal
  (v0.14.10, round 302).

`test_parser_marks_tails_only_inside_fn_bodies` parses
`fn f(n) { if n { f(1) } else { g(2) } }` and reaches the first. Deleting the
second left every one of the 28 tests in `test_v03.py` green.

**The differential, measured rather than argued.** `guardpin`'s own
`apply_edit` produced the mutated parser; two temp trees, same program:

```
let go = fn(i, acc) { if i == 0 { acc } else { go(i - 1, acc + i) } }
let result = go(300, 0)

  intact    peak_depth  1   tail_calls 300
  deleted   peak_depth 50   tail_calls   0     ← 50 is max_depth: the cap

fn go(i, acc) { if i == 0 { acc } else { go(i - 1, acc + i) } }
  intact    peak_depth  1   tail_calls 300
  deleted   peak_depth  1   tail_calls 300     ← untouched, as GP10 says
```

Real tail-call elimination, on the form Whence programs actually use for a
let-bound helper, with no test observing it — for eleven rounds since the
branch was written. Uncaught, a regression there would not show as a wrong
answer but as a depth `Miss` on a program that used to work.

Two tests were added to `test_v03.py`, next to the one they extend:

* `test_the_parser_marks_tails_in_an_anonymous_fn_body_too` — the parser-level
  mirror of the existing pin, on `Let -> FnExpr -> Block`;
* `test_a_let_bound_anonymous_fn_is_a_tail_loop_like_a_named_one` — the
  behavioural half, asserting `peak_depth == 1 and tail_calls == 300`, which
  is the assertion the differential above shows is load-bearing.

`test_v03.py`: **28 -> 30 passed**.

---

## 6. The blocked harness: five copies of one question, five different roots

Widening GP11 from `test_v03.py` to the whole whence fast tier is the obvious
next question — *does anything at all notice?* — and it produced a different
finding instead:

```
nonviable  GP12  the named test is green under the edit and the wider suite
                 languages/whence/tests is not green UNMUTATED (killed), so
                 misattributed/unguarded cannot be told apart
```

The instrument refused to report `unguarded` against a red baseline. Round
349's rule, in a place round 349 never looked, and it was right to refuse:
the suite was red for a reason that has nothing to do with the pin.

Pulling that thread found something bigger.

```python
>>> baseline_check("languages/whence", DEFAULT_TEST_CMD)
rc 1  secs 0.55
E   FileNotFoundError: '/tmp/state/whence/round-384/field-names.json'
ERROR tests/test_field_corpus_selector.py
1 error in 0.21s
```

**`mutation_test` against `languages/whence` — the primary target of this
whole track, and `DEFAULT_TEST_CMD`'s exact command — raises
`BaselineNotGreen` before generating a single mutant.** It is not a bad
mutation score; it is no mutation run at all. `campaign.py`'s
`_require_baseline` gate (GP06's subject) is the same door.

### The cause, and it is a census

`harness/swe/proc.py` exports `AGI_RESEARCH_ROOT` into every subprocess it
starts, for exactly this — round 149 found 7 of 78 "kills" in a round-137
campaign were `__file__`-based path math pointing at the tempdir. Four files
in `languages/whence/` already read it (`bench/ref_diff.py`,
`bench/reserve_probe.py`, `tests/test_v10.py`,
`tests/test_parser_differential.py`).

Five *other* sites ask "what does git track in `examples/`?", each deriving
its own root from `__file__`, and **none of them read it**. Under a mutation
copy they degrade three different ways:

| site | root | failure in a copy |
|---|---|---|
| `curecheck.FIELD_CENSUS` | grandparent of `_HERE` | `FileNotFoundError` at IMPORT time → collection of the whole suite aborts |
| `tests/test_lexer_guest_parity.py` (the pin test) | `ROOT`, `check=True` | `CalledProcessError: git ls-files … exit 128` |
| `tests/test_v24.py::_tracked_examples` | `REPO`, no `check` | empty stdout read as **"nothing is tracked"** → *"declared but no longer tracked: [every example]"* |
| `tests/test_v26.py` | `ROOT`, `check=True` | `CalledProcessError` |
| `tests/test_v32.py` | `ROOT`, no `check` | empty tracked set |

The duplication of the *question* is deliberate and governed — the whence
suite must not import `harness/`, and
`harness/tests/test_pristine_check.py::test_the_curated_corpus_rule_is_
duplicated_only_where_declared` censuses the copies of the literal on
purpose. What was duplicated by **accident** is the ROOT each copy runs git
in, and that has no governance at all.

> A duplication that a checker guards is a decision. The undeclared thing
> travelling *inside* it is the defect — here, five `__file__` derivations
> that agree in the checkout and disagree everywhere else.

### The fix

One home for the root, in `curecheck.py` (same tree, so no `harness/`
dependency, and no new copy of the pinned literal):

```python
_AGI_ROOT = os.environ.get("AGI_RESEARCH_ROOT") or os.path.dirname(os.path.dirname(_HERE))
REPO_GIT_ROOT   = _AGI_ROOT
WHENCE_GIT_ROOT = os.path.join(_AGI_ROOT, "languages", "whence")
```

Outside a `run_capped` subprocess the variable is unset and both values are
byte-identical to what each site computed before, so a plain
`pytest languages/whence/tests` is unchanged. All five sites now take their
`cwd` from these two names. The FILES still come from each site's own root:
it is the tracked-SET question that has to be asked of the real checkout, and
the copy holds byte-identical examples.

And `test_lexer_guest_parity` got the round-411 treatment for its own second
door. `_example_files()` had a graceful `git`-fails-to-glob fallback; the test
that *pins* it re-derived the same `git ls-files` with its own
`subprocess.run(..., check=True)` and no fallback at all. Both now go through
one `git_tracked_examples()`. The pin did not get weaker — a `None` return
still fails loudly, because in any checkout git can answer and a silent pass
is precisely what round 355's fix exists to prevent.

**Measured progress of the baseline, one blocker at a time:**

```
before                      1 error,     0 passed, exit 1 in 0.2 s  (collection died)
after curecheck fix         1 failed,  362 passed, exit 1 in 87 s
after the git-root fixes    see §8
```

---

## 7. "Red" has grades, and the first run's own output said so

Reading *why* each guarded pin went red — the failure tails are in the run's
JSON — turned up round 412's shape one layer out. Two of the nine did not go
red on the assertion they are named for; they went red by **crashing before
reaching it**:

```
GP07  test_power_floor_rejects_an_impossible_record_shape
      expected:  DID NOT RAISE PerturbationError
      got:       E   ZeroDivisionError: division by zero

GP09  test_the_swap_channels_power_collapses_to_zero_and_commits_does_not
      expected:  an assertion about n_testable_units
      got:       E   TypeError: 'NoneType' object is not subscriptable
                     (inside channel_sweep — the test evaluates NONE of its
                      four assertions)
```

GP09 is the sharp one. That test's whole subject is a pair of
`n_testable_units` lists; under the edit the pipeline dies upstream and the
test never gets to look. It IS red, and a `guarded` verdict credits it — but
if a later change made `power_floor` return something wrong-but-subscriptable,
this test's `guarded` status would tell you nothing, because the thing that
went red was the crash and not the claim.

That is what `expect_in_failure` is for, and it is the field round 412
motivated: **a declaration of what the failure should SAY.** Both pins now
carry one, and both consequently report `wrong_reason` rather than `guarded`.

> A verdict of "the named test went red" is two claims stacked: the test
> noticed, and it noticed *this*. Only the second one survives a refactor.

This is not an argument for deleting either test. It is an argument for the
registry recording the weaker fact honestly rather than the stronger one by
default — and for `expect_in_failure` being the cheapest way this program has
found to keep round 412's lesson enforced rather than remembered.
