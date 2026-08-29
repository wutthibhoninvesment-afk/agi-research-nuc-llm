# Round 320 (language(C)) — a host-vs-guest PARSER differential tool, and the real bug it found on its first run

## Context

Pre-flight: `ps -eo pid,ppid,etime,cmd` showed only this round's own driver
process tree ([[feedback_check_for_concurrent_rounds]]). `git status
--porcelain` showed exactly the 5 allowlisted standing-dirty paths from
`state/known-standing-dirty-paths.json` (round counter + the 4 Hermes-owned
`languages/whence/` files), nothing to reconcile
([[feedback_check_cached_diff_before_commit]]).

Round 319 (harness A) left language(C)'s own backlog with no open item:
round 318 closed the `rand(lo, hi)` question with `trunc`, and round 314
formally closed the effect system's "dynamic call graph" gap as the
family's own founding design boundary, not a bug — round 319's own
next-steps item 9 explicitly says a future language(C) round should not
reopen it without reading `SPEC.md`'s v0.14.14 section first. So this round
needed to find its own well-motivated work, not continue a queued slice.

## What was investigated first (and ruled out)

Surveyed the full builtin table (36 entries, `whence/interp.py`'s
`@register` calls) for a "trunc"-shaped gap (a real idiom blocked by a
missing primitive) — found none with a concrete, named motivating use
case; adding builtins like `sort`/`floor`/`min`/`max` speculatively would
violate this project's own "evaluate-before-authoring" discipline (round
206's own phrase), since no example or backlog item names a need for one.

Re-read every "not yet done" / "no corpus need yet" marker across
`SPEC.md` (`grep`): both prior open items in that class (`at`/`blame`/
`diverge`/`contrast` guest dispatch, round 206→218; list-element field
access on `steps`/`blame`/`diverge`, round 218→222) are ALREADY closed —
confirmed by reading both landing sections, not by trusting a stale
backlog line.

## The gap that was actually open: nothing had ever diffed the PARSER'S OWN AST SHAPE, host vs guest

`self_eval.lang`'s own differential suite (`test_self_eval.py`) compares
host-run vs guest-run **VALUES** (evaluator layer). `harness/swe/guest.py`'s
why-shape fuzzer compares host-run vs guest-run **derivation graphs**
(also evaluator layer, a different axis of the same layer). `self_host.
lang`'s own 66-check test section hand-picks ONE field at a time off a
`parse_whence(...)` result and asserts on it directly. **Nothing had ever
canonicalized a real host `A.*` AST and a real guest `@{kind: ...}` AST
into the same shape and diffed the WHOLE tree, node for node, across a
corpus.** This is a real, previously-nonexistent instrument, not a rehash
of an existing check.

### Why this was cheap to build

A guest AST (from `parse_whence`, called via `self_eval.lang`'s own copy
of the shared parser section, executed HOST-LEVEL — no `run_src` layer
involved, the same cheap level `test_guest_parser_parses_its_own_full_
source` (round 192) already uses) is a REAL Python-level `Prov`/`Record`/
`WList` tree — the parser's own output is never "guest-boxed" (that boxing
only happens inside `self_eval.lang`'s own EVALUATOR, `run_src`, which
this tool never touches). So both sides of the comparison are ordinary
Python objects reachable via `.value`/`.fields`/iteration, with zero
guest-unboxing machinery needed — the same "free delegation" property
`steps`/`at`/`blame` (rounds 206/218) already relied on, one layer up.

### The canonicalizer

`whence/ast_nodes.py` has exactly 20 node classes. Enumerated
`self_host.lang`'s own `@{kind: "...", ...}` literals (one `grep -n
"kind:"` pass) to build the kind↔field mapping:

| host class | guest kind | notes |
|---|---|---|
| `Num`/`Str`/`BoolLit`/`NameRef` | `num`/`str`/`bool`/`name` | `.value` fields match |
| `ListLit` | `list` (`items`) | |
| `RecordLit` | `record` (`pairs`) | host pairs are `(name, expr)` tuples; guest pairs are `{name, value}` records — same order |
| `MissLit`/`Unary`/`Why`/`Snip` | all fold into ONE guest kind `unary`, tagged by `op` (`"miss"`/`-`/`not`/`"why"`/`"snip"`) | 4 host classes, 1 guest shape — the guest's own `parse_unary` literally shares one code path for all 5 |
| `Binary` | `binary` (`op`,`left`,`right`) | |
| `Rescue` | ALSO folds into `binary`, `op="rescue"` | host keeps it a separate class; guest doesn't |
| `Call` | `call` (`fn`→`func`, `args`) | host's `tail` field dropped (compiler-only, no guest equivalent) |
| `Index` | `index` | |
| `FieldAccess` | `field` | |
| `If` | `if` | |
| `FnExpr` | `fnexpr` | host's `param_call_fact` dropped (v0.14.9+ effect bookkeeping, parser-internal) |
| `Block` | `block` | host's `tail_alias_tag`/`tail_param_name` dropped (same reason) |
| `Let` | `let` (host `expr` ↔ guest `value`) | |
| `FnDef` | `fndef` | |
| `Check` | `check` | |
| `ExprStmt` | `exprstmt` | |
| `Program` | `program` | |

`ret_type`: host stores `None` / an `A.Str` (primitive tag) / an `A.
NameRef` (shape name — the guest can NEVER produce this, `shapes.lang` is
therefore excluded from the corpus, a pre-existing documented limit, not
this round's target); guest stores a plain string, `""` for none. Mapped
`None → ""`, `A.Str(tag) → tag`.

## First run: 4/35 mismatches, all one root cause

Corpus: 22 hand-written snippets (one per node kind + edge cases) + 13
real `examples/*.lang` files (excluding `shapes.lang`, `self_eval.lang`/
`self_host.lang` themselves — already covered elsewhere — and the two
Hermes-gateway-owned files, [[project_hermes_gateway_shares_the_repo]]).

```
14 MISMATCH fn foo(x: num) { x }
15 MISMATCH fn bar(a: num, b: str) { a }
21 MISMATCH fn needs_guess(g: guess) { confidence(g) }
31 MISMATCH <guess.lang's full source>
total mismatches: 4 / 35
```

All four are the SAME bug: a NAMED function's typed-parameter guard.
`examples/guess.lang` line 75 (`fn needs_guess(g: guess) { confidence(g)
}`) is a REAL, already-shipping example that has been exercising this
exact shape since round 176 — but only on the SUCCESS path
(`needs_guess(guess(...))`), which never reads the guard's own label
string. The label only surfaces in a MISS's reason text, on the
REJECTION path, which no existing check in `guess.lang` or `self_host.
lang` ever triggers for a NAMED function.

## Root cause

Host `_apply_type_guards(body, params, types, fn_name)` (`whence/
parser.py`):
```python
suffix = " of %s" % fn_name if fn_name else ""
...
label = A.Str(body.line, "parameter '%s'%s" % (pname, suffix))
```
`FnDef` call site passes `fn_name=name`; `FnExpr` (anonymous) call site
passes `fn_name=None`. So a NAMED fn's guard says `"parameter 'x' of
foo"`; an anonymous fn's says `"parameter 'x'"`.

Guest `build_guards` (`self_host.lang`/`self_eval.lang`'s byte-identical
copy) NEVER threaded `fn_name` through at all:
```
let label = "parameter '" + params[i] + "'"
```
— unconditionally, called identically from BOTH the `fnexpr` and `fndef`
sites. This silently matched the host for every anonymous fn (both sides
empty suffix) and silently diverged for every named fn, invisibly, since
round 158 shipped this guest-parity feature — a genuine, real,
previously-undocumented gap, not a hypothetical.

## The fix

Threaded a `suffix` parameter through both functions, in both files
(identically — `self_host.lang` lines 28-561 must stay byte-identical to
their copy inside `self_eval.lang`, pinned by `tests/test_self_eval.py::
test_parser_section_matches_self_host`):

```
fn build_guards(params, types, i, acc, suffix) {
  ...
        let label = "parameter '" + params[i] + "'" + suffix
  ...
    build_guards(params, types, i + 1, acc2, suffix)
  ...
}
fn apply_type_guards(block_node, params, types, suffix) {
  let guards = build_guards(params, types, 0, [], suffix)
  ...
}
```
Call sites: `fnexpr` (anonymous) passes `""`; `fndef` (named) passes
`" of " + nm.name`. The edit was deliberately shaped to add ZERO new
lines (extend existing signatures/call-site argument lists in place) so
neither file's own line-count-dependent test constants (`test_self_
hosting.py`'s `LIB_START, LIB_END = 27, 561`, `test_self_eval.py`'s
`host_lines[27:561]` slice) needed updating — confirmed by `wc -l` before
and after (719/2059 lines, unchanged) and by re-running `test_parser_
section_matches_self_host` (still passes).

## New permanent test: `tests/test_parser_differential.py`

Two tests:
1. `test_host_and_guest_parsers_agree_on_ast_shape` (`whence_slow`) — the
   full 35-item canonical-form sweep, now 0 mismatches (was 4). Batches
   the whole corpus into ONE `Interpreter().run()` call (library parsed
   once, one `parse_whence` per item), the same amortization discipline
   `test_self_eval.py::guest_eval_all` already uses for the evaluator
   layer.
2. `test_named_fn_typed_param_guard_label_includes_enclosing_fn_name`
   (fast, unmarked) — a dedicated pin isolating the exact fixed bug,
   checking BOTH the named-fn case (`"parameter 'g' of needs_guess"`,
   independently on host and guest) and the anonymous-fn control
   (`"parameter 'x'"`, unchanged both sides), reading raw Prov/Record
   fields directly rather than going through the canonical-form diff —
   so a future one-sided revert fails loudly even if the slow sweep is
   ever skipped in a fast run.

## Verification

- `bash run_tests_fast.sh`: 945 → **946 passed, 39 deselected** (+1 fast
  test, +1 newly-deselected slow test).
- Full unfiltered `pytest tests/` (backgrounded, 279.55s): 983 → **985
  passed, 0 failed** (+2, exactly the 2 new test functions).
- `tests/test_self_hosting.py` + `tests/test_self_eval.py` (30 tests,
  including the 154-statement pin and the byte-identity check): all 30
  still pass, confirming the fix touched neither `self_host.lang`'s own
  statement count nor the shared section's byte identity.
- `python3 run.py examples/guess.lang`: still 27 passed, 0 failed (the fix
  only changes a MISS's own reason TEXT, which no existing check in that
  file asserts on verbatim).
- Every other `examples/*.lang` file re-run directly via `run.py`:
  unchanged pass/fail counts (`hello` 2, `effects` 16, `checks_demo` 8,
  `sales` 5, `history` 14, `provenance` 3, `blame` 4, `tco` 10, `deep` 6,
  `meta` 25, `diverge` 16, `failing_check` 0/2 — intentionally failing,
  matches its name).
- `bench/ref_diff.py --counters examples/*.lang --show`: **0 differing
  (file, mode) pairs** across all 18 example files (including `self_eval.
  lang` 103 checks, `self_host.lang` 66 checks — both unchanged) —
  confirms zero unintended regression anywhere in the interpreter.
- Cross-track: `bash harness/run_tests_fast.sh` → **414 passed, 229
  deselected**, byte-identical to round 319's own post-landing baseline.
- `git diff --stat`: `SPEC.md` (+1 new version section), `examples/
  self_eval.lang` + `examples/self_host.lang` (identical 3-hunk edits
  each, 0 net line-count change), plus the new `tests/test_parser_
  differential.py` file.

## Named, not chased

- This round's canonical form deliberately does not attempt to compare
  PARSE-ERROR shapes (host `ParseError` exception vs. guest `miss`
  value) — `self_host.lang`'s own hand-written error-handling section (67
  checks) already covers specific wordings for specific inputs by direct
  assertion; mixing that into the structural-equality sweep would need a
  second comparison shape for no concrete gain this round. A future round
  could extend the tool with an error-corpus mode if a real need for it
  turns up — evaluate-before-authoring, the same discipline that
  motivated this round's own tool in the first place.
- The differential tool's corpus is real but not exhaustive (35 items,
  hand-picked + real examples) — it is not a fuzzer. A future SWE-loop(D)
  or language(C) round could wire `harness/swe/fuzz.py`'s existing program
  generator into `guest_parse_all`/`canon_host`/`canon_guest` for a much
  larger random sweep, the same escalation path round 284/290's "fuzz
  coverage" language(C) rounds already used for other v0.14.x features —
  named here as a natural, concrete follow-up, not attempted this round
  (scope: this round's own tool already found and closed a real bug on
  its very first, hand-written-corpus run; a fuzz campaign is additional
  confidence, not required to close what was actually found).

## For the next round

1. The parser-differential tool (`tests/test_parser_differential.py`) is
   new, permanent, and passing — a future language(C) round investigating
   any OTHER guest-parity question should check whether extending this
   tool's corpus (rather than writing a new one-off script) answers it
   first.
2. Optional, not urgent: wire `harness/swe/fuzz.py`'s generator into this
   tool for a randomized sweep (see "named, not chased" above) — SWE-loop
   (D) or language(C), either fits.
3. All other unrelated-track backlog lines from round 319's own next-steps
   list (items 2-8, harness(A)/NUC(E)/SWE-loop(D) items) — unchanged, not
   touched this round.
