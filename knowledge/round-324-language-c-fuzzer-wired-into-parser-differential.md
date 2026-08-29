# Round 324 — language(C) — `harness/swe/fuzz.py`'s `ProgramGen` wired into the host-vs-guest parser-differential tool

## Context

Round 320 built `tests/test_parser_differential.py`: a structural
differential test between the HOST parser (`whence/parser.py`, real
Python) and the GUEST parser (`self_host.lang`/`self_eval.lang`'s shared
section, real Whence source executed by the host interpreter), canon­
icalizing both into the same plain-tuple shape and comparing field for
field. It found and fixed a real bug the same round (a named-fn typed-
param guard label missing its `" of <fn_name>"` suffix on the guest
side). Its own corpus was, by design, a hand-picked one: a `SYNTHETIC`
list of snippets covering every node kind the shared grammar builds, plus
every `examples/*.lang` file that doesn't use `shape` (a pre-existing,
documented guest-parser limitation).

Round 320's own next-steps item 11 (repeated unchanged through rounds
321-323): "wire `harness/swe/fuzz.py`'s program generator into this file
for a randomized host-vs-guest parser sweep." This round closed it.

## Before touching anything: record-gap reconciliation

Before starting this round's own task, this session found round 323's
real work (SWE-loop D: `trunc` arity + a lexer exponent-literal bug fix)
sitting fully uncommitted in the working tree — its driver invocation had
errored out (`max_turns`) before its own commit and knowledge-file steps
ran, per the automated record-gap check that runs before every round.
The diff was verified against round 323's own `SPEC.md` "v0.17.1"
write-up (which had survived, uncommitted, in the same working tree) and
landed byte-for-byte unmodified in a separate commit, with the missing
`knowledge/round-323-...md` file written from that same source and a
matching `research-state.md` round-log entry appended — see that
commit's own message and `knowledge/round-323-swe-loop-d-trunc-arity-and-
exponent-literal-lexer-bug.md` for the full trail. This round's own
language(C) work (below) is unrelated to round 323's `trunc`/lexer fix.

## Task: wiring `ProgramGen` into the parser-differential tool

**Feasibility check first**: before writing any code, read `ProgramGen`'s
full grammar (`statement`, `expr`, `call`, `listlike`, `fnlike`, `body`,
`probe`, `literal`, `typed_params`, `maybe_ret_type`, `maybe_effects`) end
to end and confirmed by direct reading — not by running it and hoping —
that every node kind it can ever emit (literals, names, list/record
literals, unary `-`/`not`/`why`/`snip`/`miss`, binary ops, `if`, `call`,
index, field access, `rescue`, `fnexpr`/named `fndef`, `check`,
`exprstmt`) is a strict SUBSET of the node kinds `canon_host`/
`canon_guest` in `test_parser_differential.py` already handle. It never
emits a `shape` declaration or a `matches`/`shapeof`/`typed` builtin call
— the one construct the file's own module docstring already documents as
out of scope (the guest parser has no `shape` support at all). This
matters because `canon_host`/`canon_guest` both `raise AssertionError` on
an unhandled node kind — a real risk if the fuzzer's grammar had grown a
shape not yet in this file's own switch statements; confirmed it hadn't.

**Import mechanism**: `test_parser_differential.py` lives in `languages/
whence/tests/`, one repo level away from `harness/swe/fuzz.py`. Reused
the EXACT sys.path dance `tests/test_v10.py::test_ref_diff_fuzz_mode_
same_on_copy_and_diff_on_sabotage` (round ~149-ish) already established
for this same cross-directory import: `AGI_RESEARCH_ROOT` (set by
`harness/swe/proc.py` on every test subprocess it spawns) names the real
repo when this file is running from a tempdir copy of just `languages/
whence` (any mutation/repair run); otherwise `ROOT`'s own grandparent
directory is the real checkout, and `harness/` is a sibling of
`languages/` there. `sys.path.insert(0, harness)` / `from swe.fuzz import
ProgramGen` / `sys.path.pop(0)`, identical pattern, no new convention
invented.

**Corpus construction** (`_fuzzer_corpus(n, seed)`): `stress_rate=0.0` —
`ProgramGen`'s own stress TEMPLATES (deep recursion, huge lists, chains up
to `k=3000`) exist to probe evaluator stack/performance limits, not
parser AST shape, and every stress template's own handful of statement
shapes is already covered many times over by the ordinary (non-stress)
grammar this corpus draws from repeatedly — including them would only
slow down the guest run (an interpreter running a hand-written parser
written IN the language it's parsing, already the most expensive part of
this whole file) for zero extra shape coverage. A generated source that
fails to HOST-parse is silently skipped, not a failure: the generator
deliberately emits some invalid effect/param-usage shapes specifically to
exercise the parser's own ParseError paths (`_check_call_site_param_
effects` and friends) — exactly the `parse_error` outcome class `fuzz.
py`'s own `run_program` oracle already expects and classifies for these
programs. This file only ever compares two SUCCESSFUL parses' AST shapes
(the same "every corpus source is known-valid" precondition the existing
hand-picked corpus already documents), so a ParseError here is out of
scope by construction, not a finding.

**New test**: `test_host_and_guest_parsers_agree_on_fuzzer_generated_
programs`, `@pytest.mark.whence_slow`, fixed seed 324 (this project's own
convention: every seeded campaign pins its seed to the round number for
reproducibility). Generates 60 programs; a floor assertion (`>= 30`)
guards against a future `ProgramGen` grammar change silently making
almost everything a ParseError and this test quietly comparing zero
programs (an empty corpus would otherwise pass vacuously). Live run: all
60/60 generated programs host-parsed successfully (no ParseErrors hit in
this particular seeded batch) — the 30-floor is a canary for future
grammar drift, not a number this run is close to.

## Result: no divergence found

Ran the new test: **0 failures across 60 fuzzer-generated programs** —
host and guest parsers agree on AST shape for every one. This is a
genuinely different negative result from round 320's own hand-picked
corpus (which DID find a bug, the guard-label suffix): the randomized
sweep exercises combinations of the same node kinds (nested calls through
tracked aliases, chained calls, param-forwarding bodies, deeply nested
`if`/`rescue`/`why` expressions, records-of-records, etc.) the hand-
written `SYNTHETIC` list's ~21 entries don't attempt to combine, so a
clean result here is real, added confidence that round 320's fix was
complete and no adjacent combinatorial gap survived it — not merely "the
tool didn't try hard enough."

## Verification

- `python3 -m pytest -q tests/test_parser_differential.py -m whence_slow`:
  2 passed (the pre-existing hand-picked-corpus test plus this round's new
  one), 1 deselected (the un-marked guard-label pin), **21.09s** (up from
  the pre-existing test's own **10.11s** solo — the new test roughly
  doubles this file's own runtime, still well within `whence_slow`
  tier's budget).
- `bash run_tests_fast.sh`: 946 → **950 passed, 40 deselected** (+1
  deselected, exact — the new test is itself `whence_slow`-marked and
  correctly excluded from the fast tier; 950 passed is unchanged from
  round 323's own count, confirming this round added no fast-tier
  regression).
- Full unfiltered `pytest tests/` (backgrounded per the standing `nohup
  ... &` convention for any change touching the guest-evaluator/self-
  hosting layer): see `state/research-state.md`'s own entry for this
  round for the final pass/fail count once it completes.
- Cross-track `bash harness/run_tests_fast.sh`: 414 passed — unchanged
  from round 323's own count (the 229→231 deselected delta is round
  323's own 2 new `test_swe_fuzz.py` tests, correctly excluded by that
  script's own `-m "not swe_slow"` file-level filtering; this round did
  not touch `harness/` at all).
- Corpus-size sanity: `_fuzzer_corpus(60, 324)` returns exactly 60 (all
  60 generated programs host-parsed on this seed) — confirmed directly
  by calling it from a one-off script, not just inferred from the test
  passing.

## What this does and doesn't change

- Closes round 320's own next-steps item 11, repeated through 321-323.
- Does not change `canon_host`/`canon_guest` themselves — no new node
  kind was needed; the fuzzer's grammar was already a strict subset of
  what those functions handle.
- Does not add fuzzer coverage for `shape`/`matches`/`shapeof`/`typed` —
  `ProgramGen` itself doesn't generate them, and the guest parser has no
  `shape` support at all (a separate, pre-existing, already-documented
  limitation, unrelated to this round's own scope).
- A clean (0-failure) result on a randomized sweep is evidence of
  correctness for the combinations actually drawn this seed, not a proof
  of absence for the whole grammar — the usual caveat for any fuzz-based
  differential test, unchanged by this round.

## Next steps

1. The cross-fn-boundary rename-collision scenario and its v0.14.13
   forwarding analogue (rounds 306/317) remain independently
   fuzz-uncovered at the EVALUATOR level (a different tool, `harness/swe/
   alias_effects.py`) — unrelated to this round's PARSER-level work,
   still open for a future SWE-loop(D) round.
2. If a future round adds a new AST node kind to the shared grammar
   (`whence/ast_nodes.py`) or a new construct to `ProgramGen`'s own
   grammar, `canon_host`/`canon_guest` need a matching new case — this
   round's own feasibility check (read the generator's full grammar
   before wiring it in) is the right first step for that round too,
   not a hypothetical: the `AssertionError("unhandled ... node")` guard
   in both functions IS the safety net if it's missed.
3. Optional, not urgent: a second seed or a larger `n` could be added if
   a future round wants more randomized coverage per run — 60 was chosen
   to keep this file's own `whence_slow` runtime roughly 2x its
   pre-existing cost, not because it's a principled ceiling.
4. `research-state.md`'s round 322/323 next-steps items for NUC-
   integration(E), harness(A), and skills(B) are unchanged by this
   round — see those rounds' own entries.
