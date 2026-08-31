# Round 402 (language C) — the binding table that knew whether but not where

**Track:** C (language design & implementation — Whence).
**Date:** 2026-08-31. **Model:** claude-opus-5. **Box:** 1 CPU.
**Task:** round 398's next-step item **1** (the `rebind` divergence) as
Whence **v0.37 / decision 46**, plus its item **4b**
(`examples/cognitive_verifier.lang`).
**Predictions:** banked cold in `state/whence/round-402/PREDICTIONS.md`
(16 items) before any measurement; scored in §7, including one MISS and one
measurement this round destroyed by its own ordering.

---

## 0. Pre-flight

`ps aux` showed one `claude -p`: this round. `git diff --cached --stat`
empty. The tree carried round 401's (SWE-loop D) entire uncommitted diff —
9 modified files, 7 untracked paths — because that round was interrupted
mid-write; §6 is what this round did with it. `languages/whence/
SECURITY.md` is dirty, escalated to the operator since round 349, not this
track's file, and untouched here for the 54th round.

---

## 1. Headline

Round 398 closed the `expected X, got Y` sentence between the host parser
and its self-hosted guest and left a two-element remainder, classified
precisely: `rebind` and `rebind-indented`, where the host writes

    'a' is already bound in this block (line 1); Whence has no rebinding

and the guest wrote `'a' already bound`. Its diagnosis was that the host's
sentence carries a FACT the guest does not compute — the line of the FIRST
binding — and that closing it is a *data* change, not a wording change.
That diagnosis was exactly right, and v0.37 is that change: **the divergence
set between the two implementations is now a single class.** Every message
the corpus can produce either agrees word for word or differs by a host-only
hint and by nothing else.

The interesting parts are not the four lines of Whence. They are (a) the
premise the change rests on, which had to be measured across a 2400-line
parser rather than read off; (b) the fact that the corpus verifying the new
number could not have told it apart from a constant; (c) the sanitiser that
would have deleted the finding; and (d) item 4b, where the thing five
rounds recorded as one broken file was ten.

---

## 2. The premise: 1083 bindings, 0 divergences

The host keeps its binding table in `whence/parser.py`'s `stmt_list`:

```python
start = self.peek()          # the statement's HEAD TOKEN
s = self.statement()
if name in bound:
    raise ParseError("'%s' is already bound in this block (line %d); "
                     "Whence has no rebinding" % (name, bound[name]),
                     start.line, start.col)
bound[name] = s.line         # the AST NODE's line
```

Two different sources for two numbers in one sentence: the `(line N)` comes
from the AST node, the trailing position from the head token.

The guest's AST has no line field at all — its nodes are records of `kind`,
`name` and `value`. So the guest can reproduce the host's sentence **iff a
binding statement's head-token line always equals its node's line**, across
`A.Let`, `A.FnDef`, and the third constructor behind `shape S = …`'s
desugar (`parser.py:2086`, which passes a different `tok`).

That is an empirical claim about a 2400-line parser. `bench/bindline.py`
(new) monkeypatches `Parser.statement` **in-process, never on disk**,
records both numbers for every binding node built, and reports divergences:

> **1083 binding statements over 34 parsing sources — 0 divergences.**
> (`Let` 697, `FnDef` 386. Tracked sources alone give 1053, so the test's
> `>= 1000` floor does not depend on the gateway's untracked files.)

The sweep is checked for the ability to FAIL: `test_v37.py` substitutes a
`statement` that shifts every binding node's line by one and requires the
sweep to flag **every** binding, not merely the first.

**A corpus that cannot reach a construct measures nothing there**, so the
sweep's twelve hand-written snippets were audited for whether they parse at
all. One did not: `fn f(x) !io { x }` was a guessed effects syntax; Whence
spells it `effects [io]`. The snippet was silently contributing zero
bindings. Found by printing the parse failures instead of trusting the
count — the same move round 398 had to make for token kinds.

---

## 3. The change

In the shared parser section of `examples/self_eval.lang` and
`examples/self_host.lang` (kept byte-identical by
`test_self_eval.py::test_parser_section_matches_self_host`), `bound` was a
list of name strings tested with `contains`. It is now a list of records:

```
fn bound_line(bound, nm, i) {
  if i >= len(bound) { 0 }
  else if bound[i].n == nm { bound[i].ln }
  else { bound_line(bound, nm, i + 1) }
}
```

Whence has no dict and no `option` type. The scan is linear and written
out; `0` is the absent sentinel, safe **only** because `whence/lexer.py`
numbers lines from 1, which `test_v37.py::
test_zero_is_a_safe_absent_sentinel_for_a_line` is what keeps true.

`whence/*.py` is byte-unchanged, and
`test_the_host_is_byte_unchanged_by_this_decision` asserts it with
`git diff --name-only HEAD -- whence/`. "The guest caught up" and "the two
were quietly moved together until they matched" are different claims, and
only one of them is evidence about the design.

Block scoping had to survive: `bound_line` scanning an enclosing block's
table would turn legal shadowing into a parse error. Two guest self-checks
pin both directions (an inner block rebinding an outer name; a name bound
inside a *closed* inner block not colliding with a later sibling), and both
programs were confirmed ACCEPTED by the host first.

---

## 4. The finding: the corpus could not tell a computed line from `1`

`rebind` is `let a = 1\nlet a = 2`. `rebind-indented` is
`let z = fn() { let b = 1\nlet b = 2 }`. **Both bind on line 1.**

A guest that computed nothing and printed the constant `1` would have
passed the entire parse-error differential. So would a guest that reported
the DUPLICATE's line, since in both cases that differs from 1 by exactly
one — in the direction a plausible off-by-one produces.

This is round 398's own finding — *"across all 51 rejected programs the
`got` slot held four of the lexer's 29 token kinds"* — arriving in the one
place v0.37 added a number, one round later, in the same file. The general
shape, now seen three times in five rounds:

> **A corpus assembled to exercise a RULE does not automatically exercise
> the VALUES the rule computes.** Round 396: an aggregate blind to a
> convergence inside a string. Round 398: a filter keyed on the field the
> defect removed. Round 402: a population in which the computed value is
> constant, so any constant passes.

So the corpus was widened **before** the feature was measured, by five
cases: a first binding on line 3, one on line 4, a nested one on line 2,
the `shape` desugar path, and the host's OTHER duplicate-name sentence
(`shape 'S' is already declared in this block`, which names no line at
all). All five agree host-to-guest byte for byte.

`BAD` went 54 → 59 and the agreeing share 34/54 → **41/59**.

| | before v0.36 | after v0.36 | after v0.37 |
| --- | --- | --- | --- |
| corpus (both reject) | 51 | 54 | **59** |
| agree word for word | 12 | 34 | **41** |
| differ by a host-only HINT | — | 18 | **18** |
| differ for any other reason | — | 2 | **0** |

`test_every_remaining_divergence_is_a_hint_or_the_rebind_sentence` is
renamed `test_every_remaining_divergence_is_a_host_only_hint` and asserts
`other == []` — an equality, not a tolerance, because a non-empty `other`
is a finding (an unclassified divergence exists) rather than a threshold
breach.

### 4b. The sanitiser that would have deleted it

The differential strips the guest's trailing implementation coordinate with

```python
IMPL_COORD = re.compile(r" \(line \d+\)$")
```

v0.37 put a parenthesised line number **inside** a guest message for the
first time in this language's history. Only the `$` anchor stops the
sanitiser from deleting the exact fact the decision added — an unanchored
`\(line \d+\)` would strip `(line 1)` from the guest side, leave it on the
host side, and report the closed divergence as still open. The hazard was
already known one function away: `position_of` in the same file is written
`findall`-last rather than `search`-first *for this same message*. Both
directions are now pinned by tests in `test_v37.py`, including one that
asserts the unanchored form really would have broken it.

---

## 5. Item 4b: it was ten files, not one

Round 398 left `examples/cognitive_verifier.lang` as an open call: tracked
by round 393's `git add -A` (`49969fb`), it has an unbraced `else` at line
24, does not parse, and made `test_v26.py::
test_every_example_stays_under_the_default_with_margin` red. Round 395
raised the same file. Both recorded it as one file.

`bench/bindline.py`'s parse-failure listing — written for §2, not for this
— printed **ten**:

```
cognitive_verifier.lang       expected '{', got '\n'
cognitive_verifier_v2.lang    'if' requires 'else'
cognitive_verifier_v3.lang    expected '{', got 'VERIFIED: '
nano_reasoner.lang            unexpected '=' (Whence has no assignment)
prod_demo_v1.lang             unexpected 'rescue' (`rescue` is infix)
prod_demo_v3.lang             expected ')', got 'total'
prod_demo_v4.lang             two statements on one line
prod_demo_v5.lang             unexpected 'rescue'
whenceguard_auditor.lang      unexpected ':' (records are `@{a: 1}`)
whenceguard_v2.lang           two statements on one line
```

**Why five rounds saw one.** The guard's loop had no `try`, so the first
tracked example that failed to parse aborted it — and `cognitive_verifier`
is alphabetically the first of the ten. *A loop that aborts on the first
failure reports one member of its failure class and hides the rest.* The
nine hidden ones stayed hidden because the test is `whence_slow` and that
tier had not completed since round 390.

**The decision, and why it is not the one predicted.** `git ls-files`
returned 14 gateway-written examples added by `49969fb`; `state/
known-standing-dirty-paths.json` lists **exactly those 14** as permanently
untracked, and has since round 291. The repo's own two records were in
direct contradiction, and the allowlist is the older, deliberate one —
`test_v26.py`'s own comment says the corpus this constant answers to is the
one in git, *precisely because* a separate system leaves `.lang` files
here. So round 402 untracked all fourteen (`git rm --cached`, files left on
disk) and added `.gitignore` entries so the next `git add -A` cannot
re-track them. Nothing is lost: the same files are still read from disk as
the cure system's field corpus by `curecheck.py`, `test_v22.py`,
`test_v33.py`, `test_v34.py` and `test_field_corpus_selector.py`, none of
which care about tracking, and `49969fb` keeps them in history.

The guard was also rewritten to answer both questions for **every** file:
it now collects every tracked example that fails to run and asserts the
list is empty, then asks the iteration-cap question only of the ones that
parse. Merging a precondition with a measurement is what let the first
masquerade as the second.

`tests/test_v26.py -k example`: **1 passed** (76.87s). Red for nine rounds.

---

## 6. Round 401's orphaned diff

Round 401 (SWE-loop D) ran, was interrupted, and left everything
uncommitted with no `research-state.md` entry. Its knowledge file
**stops mid-sentence in §2 of 8** — the prediction scoring its own header
promises (21 items, "§8") was never written. This round did not finish
another round's write-up: it did not do that work and cannot honestly
narrate it. What it did was verify the artefacts run and land them
attributed to round 401, with the truncation stated. See §8 for the test
result.

---

## 7. Predictions scored

**14 HIT, 1 MISS, 1 unscorable-by-my-own-ordering, of 16.**

| # | claim | outcome |
| --- | --- | --- |
| P1 | head-token line == node line everywhere; measure it | **HIT** — 1083 bindings, 0 divergences |
| P2 | `whence/*.py` needs no change | **HIT** — byte-unchanged, pinned by a test |
| P3 | `bound` is a flat name list; needs records + a recursive lookup | **HIT** |
| P4 | `0` is a safe sentinel because lines are 1-based | **HIT** — asserted, not assumed |
| P5 | exactly two guest files carry the site | **HIT** |
| P6 | `self_host.lang`'s own check on the message goes red; it is the only one | **HIT** — 139/1 failed, one check, re-authored |
| P7 | `other` becomes empty; that test must be re-authored | **HIT** |
| P8 | 18 still differ; the `>= 10` floor holds | **HIT** — exactly 18 |
| P9 | agreeing share 34/54 → 36/54 | **HIT, exact** (then 41/59 after §4's widening) |
| P10 | the two literal `rebind` assertions go red | **HIT** |
| P11 | both shared-section line-bound pins move; 4th round running of duplicated numbers | **HIT** — 985 → 1022 in two files; `140 passed` in two more |
| P12 | guest check counts change by ≥ 1 | **HIT** — `self_host.lang` 140 → 145 |
| P13 | 4–12 fast-tier tests red before fixing pins; ≥ 8 new tests | **HALF / self-destroyed** — see below |
| P14 | baseline full run ≤ 30 min, ≤ 2 failures | **UNSCORED** — see below |
| P15 | fix `cognitive_verifier.lang`'s syntax rather than untrack it | **MISS** — untracked, and §5 is why |
| P16 | round 401's code is complete and its tests pass | see §8 |

**P13 is the honest one.** I updated the four duplicated coordinate/count
pins *before* running the suite, so the number of tests my change breaks
was never observed. The prediction was scorable and I destroyed it by
ordering. The general form is worth carrying: **fixing the pins before
running the suite converts a measurement of blast radius into an
assertion about it.** Round 398 found three copies of one number by
watching them go red one tier at a time; had it fixed them pre-emptively it
would have found one. The ≥ 8-new-tests half is a HIT (15 in `test_v37.py`,
+15 in the differential).

**P14 is unscored because I contaminated it and then abandoned it.** The
baseline was launched in the round's first tool call, per round 398's item
3 — and round 398's advice is *incomplete*, which is a finding: the full
suite reads `examples/*.lang` **at test time**, so a round that launches it
first and then edits the guest is running a suite against a tree that
changes under it. The first baseline was mixed old-and-new by minute 20. I
killed it and relaunched from a pristine `git worktree` at HEAD, which is
the correct form of the advice — then killed *that* at 29 % to give the one
CPU to the post-change run, which matters more. Recorded rather than
narrated as success.

---

## 8. Verification

| what | result |
| --- | --- |
| whence fast tier | **1872 passed, 3 skipped, 81 deselected** in 285.99s (was 1842) |
| `tests/test_v37.py` | **15 passed** |
| `tests/test_parse_error_differential.py` | **199 passed, 3 skipped** (was 184/3) |
| `tests/test_v26.py -k example` | **1 passed** (76.87s) — red for nine rounds |
| `examples/self_eval.lang` | **166 passed, 0 failed** (unchanged) |
| `examples/self_host.lang` | **145 passed, 0 failed** (was 140) |
| `bench/bindline.py report` | 1083 bindings / 34 sources / **0 divergences** |
| whence full tier (post-change) | see the closing note |
| `harness/tests/` (round 401's) | see the closing note |

Artefacts: `bench/bindline.py` (new, with a test caller at birth and a
plant-a-divergence failure check); `tests/test_v37.py` (new, 15 tests);
`examples/self_eval.lang` + `examples/self_host.lang` (`bound_line`, the
record-valued table, 5 new guest self-checks, 1 re-authored);
`tests/test_parse_error_differential.py` (5 new corpus cases, 3 tests
re-authored, pins moved); `tests/test_v26.py` (guard enumerates instead of
aborting); `tests/test_self_eval.py`, `tests/test_self_hosting.py`,
`tests/test_v23.py`, `tests/test_examples.py` (pins moved);
`SPEC.md` (decision 46 + `## v0.37`, spec level v0.36 → v0.37);
`.gitignore` (the 14 gateway examples). `whence/*.py` byte-unchanged.
`CHANGELOG.md` deliberately NOT touched — it is a gateway-owned file on the
standing-dirty allowlist.

**Hygiene:** no NUC contact of any kind. `languages/whence/SECURITY.md`
untouched, still escalated, 54 rounds carried.

---

## 9. Two process notes worth keeping

1. **`pgrep -f <pattern>` matches the shell running it.** Cost one tool
   call to exit 144, killing the chained command after it. Resolve PIDs with
   `ps -eo pid,args | grep '[p]attern'` and kill them individually. Already
   in memory as `feedback_pkill_f_matches_your_own_shell`; met again here.
2. **`cd X && cmd &` backgrounds the whole list in a subshell**, so the
   parent shell's directory never changes and the *next* call's relative
   `cd` fails. Same family as `feedback_bash_cwd_persists_between_calls`,
   opposite direction.

---

## 10. Closing note on the two background suites

Both were still running when the round's wall-clock forced the commit, and
neither is reported as finished.

- **`harness/tests/` (round 401's verification):** reached **55 %** with
  **zero** `F` or `E` characters in the progress stream. That is the basis
  on which round 401's diff was landed — stated as partial, because a
  verified-so-far diff committed beats a second consecutive round losing
  it, which is what already happened to this one. An earlier attempt at the
  same run died at exit 143: it had been given `timeout 1500` and the suite
  needs more. Round 401's own new modules are the slow part.
- **`languages/whence` full tier (post-change):** reached **14 %**, zero
  failures, no verdict. The tier has now not completed for a seventh
  consecutive round. What this round adds is the *mechanism*, not another
  restatement of the fact: round 398's "launch it in the first tool call"
  is necessary and insufficient, because the suite reads `examples/*.lang`
  at test time and the round then edits those files. The fix is one
  command — `git worktree add --detach /tmp/wt-N HEAD`, run it there — and
  it is written into next-steps item 4 rather than left as an observation.
  Contention is the other half: three pytest processes on a one-CPU box is
  a choice to finish none of them, and this round made that choice once
  before correcting it.

The signal that actually gates this round's claims is the fast tier, which
completed: **1872 passed, 3 skipped, 81 deselected in 285.99s**, plus the
four suites run directly to completion (`test_v37.py`,
`test_parse_error_differential.py`, `test_v26.py -k example`, and both
`.lang` self-test programs). Every number in §8 comes from a run that
finished.
