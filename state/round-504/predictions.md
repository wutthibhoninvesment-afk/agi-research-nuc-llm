# Round 504 (language C) — predictions banked BEFORE measuring (D-013)

Subject: round 503's next-step #5 — *"The scope-audit has never been run on
`languages/whence/`. The whole-repo sweep reports 37 not-live defs in
`whence/interp.py` ... Treat those 37 as unverified until someone reads the
names."*

## 0. DISCLOSED — already observed at the moment this bank was written

These are NOT predictions. They were read off disk before any of the numbers
below were written, and are recorded so that nothing here can be scored as a
prediction that was in fact a lookup:

- `state/swe/round-503/sweep-repo.json` reports 294 `not_live` defs
  repo-wide (`totals`: live 4794, test_only 191, unreferenced 103) over 253
  subjects, and 37 of them are in `languages/whence/whence/interp.py`:
  30 `unreferenced`, 7 `test_only` (`b_fold`, `b_reasons`, `b_get`,
  `b_typed`, `b_sure`, `b_diverge`). All 37 have the qualname prefix
  `_make_builtin_table.`.
- `whence/interp.py:3594 _make_builtin_table()` builds the table with a
  `register(name, arity, sig)` DECORATOR factory; every `b_*` def carries
  `@register(...)` and its Python name is never spelled again.
- `SPEC.md`'s `## Builtins` table documents exactly 37 names, and
  `tests/test_spec_builtins.py` already cross-checks that table against the
  live `@register` registry.
- Round 503's sweep also lists 30 not-live defs in each of
  `state/swe/round-137/{orig-proj,snapshot}/whence/interp.py`, 8 in
  `languages/whence/curecheck.py`, 8 in `depthcensus.py`, 1 each in
  `whence/values.py` and `whence_qwen_bridge.py`.
- `depthcensus.harvest_tests()` exists and returns `(programs, stats)` over
  `tests/test_*.py`.

## A. The instrument (scopecall's decorator blindness)

The claim under test: `scopecall.py` counts a reference to a def BY NAME, and
a decorated def is used by its decorator at definition time, not by its name.
A def with a decorator therefore cannot honestly be called `unreferenced`
under this module's own stated bias ("every ambiguity resolves toward live").

| id | prediction |
|---|---|
| **A1** | Adding a `decorator` reference kind to `LIVE_KINDS` takes `languages/whence/whence/interp.py` from 37 not-live defs to **0** — all 30 `unreferenced` AND all 7 `test_only` flip to `live`. |
| **A2** | The same rule moves the whole-repo `not_live` total from 294 to somewhere in **240–285** (i.e. between 9 and 54 defs elsewhere in the repo are decorator-registered and mis-verdicted today). |
| **A3** | `harness/tests/test_swe_scopecall.py` is green after the change, at **≥ 76** tests (73 today plus the new ones). No other harness test file changes verdict. |
| **A4** | Both `state/swe/round-137/orig-proj/whence/interp.py` and `.../snapshot/whence/interp.py` (30 each) are the same builtin-table shape and both go to **0** not-live. |
| **A5** | At least one repo file OUTSIDE the whence tree loses ≥ 2 not-live defs to this rule. |
| **A6** | `languages/whence/curecheck.py`'s 8 and `depthcensus.py`'s 8 are NOT decorator-shaped and are **unchanged** by the fix (they are module-level plain defs). |

## B. The question at the right level — is a builtin live *in Whence*?

New artefact `languages/whence/builtinlive.py`: parse every Whence program in
the repo (examples/*.lang plus the guest programs harvested out of
`tests/test_*.py`) with Whence's own parser, walk the AST, and count call
sites per builtin NAME, resolving shadowing (a local `let`/`fn` binding of the
same name is not a builtin call).

| id | prediction |
|---|---|
| **B1** | Of the 37 documented builtins, the number never called by any `examples/*.lang` file is between **3 and 10**. |
| **B2** | The number never called by ANY Whence program in the repo (examples + harvested test programs) is between **0 and 3**. |
| **B3** | `contrast` and `is_guess` are each called at **≤ 2** sites in `examples/`. |
| **B4** | `print` is the most-called builtin across the whole corpus, by call sites. |
| **B5** | The Python-level verdict and the Whence-level verdict **disagree for ≥ 30 of the 37** — i.e. `unreferenced`-vs-`test_only` at the Python level carries essentially no information about whether the language's users call the builtin. |
| **B6** | At least one of the 7 defs scopecall called `test_only` (`fold`, `reasons`, `get`, `typed`, `sure`, `diverge`) is called by a shipped `examples/*.lang` program. |
| **B7** | The three most-used builtins account for **≥ 40 %** of all call sites in the corpus. |

## C. Corpus mechanics

| id | prediction |
|---|---|
| **C1** | `harvest_tests()` yields between **400 and 1500** distinct guest programs. |
| **C2** | Between **2 % and 20 %** of harvested programs fail to parse (the suite deliberately holds parse-error fixtures). Any unparseable program is reported, never silently dropped. |
| **C3** | The whole census (examples + harvest, parse + walk, no execution) completes in under **60 s** wall clock on this box. `nproc` is 1. |

## D. Shadowing

| id | prediction |
|---|---|
| **D1** | At least **1** corpus program binds a name that collides with a builtin (`let get = ...`, `fn at(...)`, a parameter named `str`, …), so a grep-shaped count differs from the AST-resolved count for at least one builtin. |
| **D2** | If D1 holds, the naive/grep count is **higher** than the resolved count for that builtin (shadowing can only remove call sites, never add them). |

## E. Regression floor

| id | prediction |
|---|---|
| **E1** | `bash run_tests_fast.sh` (the whence fast tier) is green before AND after this round's whence-side changes. |
| **E2** | The two reds named in this round's briefing (`harness/tests/test_redattrib.py::TestThisTree::{test_the_cli_audit_exits_zero_on_this_tree, test_the_registry_is_fail_closed_over_the_live_logs}`) reproduce when run directly, i.e. they are NOT runner artefacts. |
