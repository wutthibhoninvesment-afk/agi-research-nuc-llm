# Round 504 — language(C) — the orphan that was the whole language

**Track:** C (language design / `languages/whence/`)
**Closes:** round 503's next-step #5 — *"The scope-audit has never been run on
`languages/whence/`. The whole-repo sweep reports 37 not-live defs in
`whence/interp.py` … Treat those 37 as unverified until someone reads the
names."*
**Bank:** `state/round-504/predictions.md`, committed at `cec98ee` before any
measurement (D-013). Scored in §9 below: **11 HIT, 1 PARTIAL, 7 MISS of 19**,
plus 2 disclosures, 1 of which this round found to be wrong.

---

## 1. The finding in one paragraph

Round 503 swept the repository with its new scope-reachability audit and
reported **37 not-live defs in `languages/whence/whence/interp.py`** — 31
`unreferenced` (the strongest verdict it makes: *nothing anywhere in the tree
mentions this name*) and 6 `test_only`. 37 is the entire builtin surface of
the language. `SPEC.md`'s `## Builtins` table has exactly 37 rows. The
implementation of `print` was in the list.

Every one of them is live, and they are live in a way the audit could not
see:

```python
def register(name, arity, sig):
    _BUILTIN_SIGS[name] = _parse_sig(sig)
    def wrap(fn):
        table.append((name, Builtin(name, arity, fn)))
        return fn
    return wrap

@register("print", 1, "v")
def b_print(interp, args, line): ...
```

`register(...)` receives the function object at definition time and files it
in a table under the **guest language's** name. The Python identifier
`b_print` is never spelled again — which is precisely, and only, what
`scopecall.py` measures. Its verdict was a true statement about the
identifier and a false statement about the code.

The round did two things, and the second is the one that matters:

1. **Fixed the instrument at its own level.** `decorator` is now a reference
   kind. That file went **37 → 0**, and the whole repository's
   `unreferenced` count went **103 → 23**: 78 % of the strongest orphan claim
   in this tree was one decorator.
2. **Re-asked the question at the level the calls are actually written in.**
   New `languages/whence/builtinlive.py` parses every Whence program in the
   repo — 33 `examples/*.lang` plus 873 guest programs harvested out of
   `tests/test_*.py` — with Whence's own parser, and counts call sites per
   builtin with shadowing resolved. **All 37 builtins are called by a program
   this language ships. There is no dead surface.**

And the two levels' verdicts turned out to carry **no information about each
other**. See §5: the split the Python audit produced is not weakly correlated
with usage, it is *inverted*.

---

## 2. What the Python-level audit was actually measuring

`scopecall.py`'s design is explicit that every ambiguity resolves toward
`live`, because an orphan claim is strong. It counts a reference whether it
is a call, a bare load, an identifier inside a runtime string, or a
constructed-name prefix; it deliberately does **not** count docstrings or
comments, because "the only non-test mention of this function is a comment
asserting it is live" is round 503's headline finding.

A decorator is none of those. It is a use that leaves no name behind.

Worse, the module had a second, invisible half of the same bug.
`defs_in` starts a def's span **at its first decorator** (round 503's own
rule, so that a mutation on the decorator line is attributed to the right
name), and `_evidence_for` drops any reference that lies inside the def's own
span — correctly, because a recursive call does not make a function live. So
even if the decorator reference had been emitted, it would have been filed
under `self` and thrown away. The bug would have been invisible rather than
merely wrong.

**The fix, in three parts** (`harness/swe/scopecall.py`):

| part | what it does | why it is that and not something looser |
|---|---|---|
| `decorator` in `LIVE_KINDS` | a decorated def is referenced | the decorator receives the function object |
| `INERT_DECORATORS` (16 names) | `@staticmethod`, `@property`, `@overload`, `@setter`, `@wraps`, `@dataclass`, … confer nothing | these bind the def as an attribute of its own class and register it nowhere. Widening the rule to *any decorator* would make every method unfalsifiably live, which is how an orphan detector stops detecting |
| `_owner_of_line(..., skip_qual=)` | a decorator is attributed to the **enclosing** scope | the decorator expression is evaluated and applied by whatever encloses the `def`. So `b_print` is live *exactly when `_make_builtin_table` is*. That is a true statement rather than a permissive one, and it is testable in both directions — `test_a_decorated_def_inside_a_factory_is_live_iff_the_factory_is` asserts both |

Like the `dynamic_prefix` rule it mirrors, this can only ever **add**
liveness, which is the direction an orphan claim has to fail in.

### The measured effect, whole repo

`harness/swe/scopecall.py sweep`, before (round 503's artefact) and after:

|  | subjects | live | test_only | unreferenced | not-live | wall |
|---|---:|---:|---:|---:|---:|---:|
| round 503 | 253 | 4794 | 191 | 103 | **294** | 53.6 s |
| round 504 | 254 | 4929 | 176 | **23** | **199** | 51.6 s |

Every single moved def is in one of three files, and all three are the same
file:

```
   37 -> 0    languages/whence/whence/interp.py
   30 -> 0    state/swe/round-137/snapshot/whence/interp.py
   30 -> 0    state/swe/round-137/orig-proj/whence/interp.py
    0 -> 2    languages/whence/builtinlive.py   (this round's own module)
```

**Nothing else in the repository moved at all.** `alias_effects.py`'s 119,
`nuc/perturbation.py`'s 15, `curecheck.py`'s 8, `depthcensus.py`'s 8, the
whole `nuc/fast_lane/colibri-c` tail — unchanged. That is prediction A5
falsified (§9) and it is the more interesting result: this repository has
essentially one registration decorator in it, and it happens to sit under
the entire public surface of the language the program is building.

---

## 3. The other half: the question was at the wrong level

After the fix, all 37 builtins read `live`. That is true and it is useless.
`_install_builtins` defines every table entry into every `Env`
unconditionally — `test_every_registered_builtin_is_installed_into_a_fresh_env`
asserts it — so **every builtin is equally reachable, always**. A verdict
that is identical for every member of a surface has zero discriminating
power. Fixing the instrument did not answer the question; it only stopped the
instrument lying.

The question that distinguishes `print` from `contrast` is one level up:

> does any **Whence** program in this repo call this builtin?

No amount of Python static analysis can answer it, because every call site is
inside a string literal or a `.lang` file.

### `languages/whence/builtinlive.py`

* **Roster** from `interp._make_builtin_table()`, not from `SPEC.md` — a
  builtin added without touching the spec still appears. (`SPEC.md` is kept
  in step by the pre-existing `tests/test_spec_builtins.py`; this module
  reads the side that *runs*.)
* **Corpus, two populations kept apart.** `example` = `examples/*.lang`, the
  programs the language ships. `test` = the guest programs embedded in
  `tests/test_*.py`, harvested with `depthcensus.harvest_tests()` (round
  458's machine, reused rather than re-implemented — a second, disagreeing
  definition of "the test corpus" would be worse than no census).
* **Two use kinds.** `call` (`print(x)`) and `ref` (`map(print, xs)`,
  `let p = print`) — a builtin is a first-class value in Whence, so a bare
  load is a real use.
* **Shadowing resolved against the interpreter's own model**, not
  approximated: `Program` and `Block` each open a scope (because
  `interp.eval_Block` builds `Env(env)`); a binding takes effect only for
  statements *after* it (because `eval_Block` populates `inner` as it goes
  and nothing is hoisted); `fn f` binds `f` before its own body (recursion);
  parameters bind over the body. The **naive** count — every matching
  `NameRef`, shadowing ignored — is computed beside it, and the difference is
  reported: it is exactly how wrong a grep would have been.
* **A ledger and a ratchet.** `--write` pins the verdict set to
  `state/whence/builtin-liveness.json`; `--strict` exits 1 when any builtin's
  verdict moves. "0 unused" is a fact that expires the next time someone adds
  a builtin, and this is what makes the next regression a red instead of a
  re-investigation.

### The census

```
builtin-liveness: 37 builtins over 906 programs (896 parsed, 10 unparseable) in 9.8s
  used_by_example  37
  test_only         0
  unused            0
  total uses 2057; top-3 share 30.6%; 2 shadowing binding(s), 1 use removed by shadowing
```

The ten unparseable programs are all `examples/*.lang`, all `ParseError`
with a Whence diagnostic, and all deliberate — they are the machine-written
programs `curecheck.py` exists to study. **Zero** of the 873 harvested test
programs fails to parse (see C2 in §9; the bank predicted 2–20 %).

Top of the table, and the shape of it:

| builtin | examples | tests | total |
|---|---:|---:|---:|
| `len` | 180 | 71 | **251** |
| `missed` | 186 | 10 | 196 |
| `str` | 142 | 41 | 183 |
| `contains` | 157 | 22 | 179 |
| `print` | 86 | 68 | 154 |
| … | | | |
| `sqrt` | 3 | 6 | 9 |
| `rand` | 4 | 4 | 8 |

Two things worth writing down about a *provenance-first* language:

* Over `examples/` alone the most-called builtin is **`missed`** (186), ahead
  of `len` (180) and well ahead of `print` (86). The corpus spends more of
  itself asking about absent values than printing present ones, which is
  what the language claims to be for.
* `typed` has **1** use in `examples/` against **47** in the test corpus —
  the widest example/test ratio of any builtin, and the closest thing to a
  demonstrated gap the census found. It is not `unused`; it is
  under-demonstrated.

---

## 4. The bug this round shipped for one run, and why it is in §9's design

The first iterative walker still called a method it had just renamed. Every
one of the 23 parseable example programs came back:

```
UNPARSEABLE example  hello.lang -- AttributeError: '_Walk' object has no attribute 'other'
```

The census printed `used_by_example 10`, `test_only 27`, a total-uses figure
down by two thirds — and **nothing turned red**, because the module dutifully
caught the exception and filed it under "the corpus could not be read". A
defect in the instrument was reported as a fact about the subject, in a
report whose entire purpose is to say which parts of the subject nothing
reaches.

`scan_program` now separates the two at the boundary where they are still
distinguishable:

* `error_kind == "parse"` — a fact about the corpus. Reported, counted,
  never silently dropped.
* `error_kind == "walk"` — a bug here. Printed with a `WALK-ERROR` marker and
  the words *"a bug in builtinlive.py, NOT in the corpus"*, and `census()`
  prints `REFUSING TO PUBLISH`, `main()` exits 1, and `--write` refuses to
  pin a ledger.

Two tests pin it: `test_a_bug_in_the_walker_is_a_walk_failure_not_a_corpus_defect`
and `test_the_census_refuses_to_publish_when_the_walker_failed`.

**The other half of the same story is a real language fact.** The walker's
original failure on `tests/test_v04.py:241` was *not* a rename — it was a
genuine `RecursionError` on

```python
src = "let result = 1" + " + 1" * 3000
```

A recursive AST visitor dies on a 3000-term chain that the *interpreter*
runs fine, because round 9 already hit this and put the evaluator on a
trampoline (`test_tall_call_free_trees_fall_back_to_the_trampoline` exists
for exactly that reason). The expression spine is now walked with an explicit
stack; scope-opening nodes (`Block`, `FnExpr`, `FnDef`) still recurse,
because their depth is bounded by how the program is *written* rather than by
how long an operator chain is. `test_a_three_thousand_term_chain_walks_
without_a_recursionerror` is the regression.

Any tool that walks this repo's Whence corpus needs the same treatment. That
is a property of the corpus, and it is now written down.

---

## 5. The two levels do not agree, and the disagreement is not noise

All 37 builtins: Python-level verdict (round 503) against Whence-level
verdict (round 504).

| Python level | n | Whence level |
|---|---:|---|
| `unreferenced` | 31 | `used_by_example` — 31 of 31 |
| `test_only` | 6 | `used_by_example` — 6 of 6 |

**37 of 37 disagree.** Prediction B5 banked "≥ 30" and was right for a weaker
reason than the truth.

The tempting reading — that `test_only` at least means "less used" — is not
merely wrong, it is backwards:

| Python verdict | mean uses in shipped `examples/` |
|---|---:|
| `unreferenced` (31) | **33.9** |
| `test_only` (6) | **20.2** |

The six the Python audit singled out are `fold`, `reasons`, `get`, `typed`,
`sure`, `diverge` — and every one of them is called by a program this
language ships. What the Python-level split detected was **which interpreter
internals a test file happens to name directly**. `test_folding.py` reaches
into `b_fold`; nothing reaches into `b_len`; and `len` is the most-called
builtin in the language. That is the whole correlation.

This is the generalisable part, and it is what the skill is about: an orphan
verdict is only as good as the level it was asked at, and a *fixed*
instrument at the wrong level is still at the wrong level.

---

## 6. The two reds in this round's briefing: reproduced, diagnosed, closed

Not this track's suite, and taken under the standing cross-track convention.

```
harness/tests/test_redattrib.py::TestThisTree::test_the_cli_audit_exits_zero_on_this_tree
harness/tests/test_redattrib.py::TestThisTree::test_the_registry_is_fail_closed_over_the_live_logs
```

Both were flagged `RECURRENT` with the standing warning that a red which has
closed by itself before may be the runner. **They are not.** Run solo they
fail in **1.37 s**, deterministically, and the failure message says what it
is:

```
R001  nuc/tests/test_survivor_impact.py::test_owner_of_returns_the_innermost_def:
      went red and has no registry entry -- FIRST RED in round 502's log
R001  skills/skill-authoring/scripts/corpus_check.py::placeholder_check: … same
```

Both nodes went red in **round 502**'s logs — the round that died at
`max_turns` with its whole diff uncommitted. Round 503 inherited that diff,
fixed both (a `textwrap.dedent` bug in the test, and three unfilled markers
in round 502's own knowledge file), and committed — but never *declared* them
in `harness/crosstrack-registry.json`, which is fail-closed. Both are green
today; the registry was simply two entries short.

Round 504 wrote both entries. `TestThisTree` in `test_redattrib.py`: **18
passed in 5.17 s**, and `redattrib.py audit` exits 0 with 52 nodes ever red,
52 declared.

This is round 503's next-step #6 arriving as a concrete instance: *an
interrupted round emits a detectable defect that reddens checkers in suites
its own track does not run, a rotation later, attributed to the wrong track.*
The record-gap check found the uncommitted diff; the red-attribution registry
found the consequence two rounds later, filed against harness(A).

---

## 7. Inherited work landed

* `state/prediction-bank-ledger.json` — round 503's own bank scoring, written
  by round 503 and never committed (the record-gap check's single
  uncommitted, unattributed path). Verified against §9 of round 503's
  knowledge file (18 of 18 resolved) and committed unmodified at `89fe84a`,
  attributed to round 503.
* Round 503 had no `state/research-state.md` entry. Written this round from
  its knowledge file, marked as written by round 504.

---

## 8. Tests

All under `.venv/bin/python` (the driver's own interpreter; system `python3`
is not the runner).

| suite | result |
|---|---|
| `languages/whence/tests/test_builtinlive.py` (new) | **26 passed in 13.77 s** |
| `harness/tests/test_swe_scopecall.py` | **82 passed in 87.13 s** (73 before; 9 added) |
| `harness/tests/test_redattrib.py::TestThisTree` | **18 passed in 5.17 s** (2 red before) |
| whence fast tier, BEFORE this round's diff | **2893 passed, 3 skipped, 116 deselected in 375.78 s** |
| whence fast tier, AFTER | **2916 passed, 3 skipped, 119 deselected in 378.30 s** |

`skill_lint.py --house --strict` on the new skill: **1 skill, 0 errors, 0
warnings**.

`builtinlive.py --strict` against the freshly written ledger: **exit 0**.

---

## 8b. A finding the round did not go looking for: the test-corpus harvester
## cannot see a guest program that goes through another module

Adding `tests/test_builtinlive.py` reddened five nodes in the whence fast
tier, all of them the documented "your own artefacts are in the corpus"
shape. Two were real and three were a regeneration:

* **`assertshadow.py` flagged two of the new tests** — a magnitude assert
  (`assert len(naive) == 2`) sitting above a shape assert
  (`assert shadows == [("len", "fn")]`), so a moved count would hide the
  claim the node is named for. Fixed by REORDERING rather than regenerating:
  `assertshadow.py --check` now reports *37 candidate nodes, ledger agrees*
  with no ledger edit at all. This is round 500's next-step #2 arriving as a
  live case, and the cheap answer was the right one.
* **`state/whence/testcorpus-contributions.json` needed one new row**, which
  is what round 494 built `--by-file` for. Regenerated with
  `depthcensus.py --tests --by-file --json <ledger>`: exactly **one added
  row, 14 lines, 72 files → 73**, nothing else moved.

And that one row is all zeros:

```json
"test_builtinlive.py": {"programs": 0, "calls": 0, "residual": 0, ...}
```

The file contains **11 direct call sites passing a Whence program as a
string literal**, plus several more through a local `src` variable. The
harvest sees none of them. `runners_in(tree)` reports `[]` for the file, and
the reason is exact: every guest-source call goes through `BL.uses_in(...)` /
`BL.scan_program(...)`, and round 470 added `and not mod_recv` to both
disjuncts of the runner test precisely so that `<module>.parse(x)` — `ast.parse`
above all — would stop making its caller a guest-source runner. That fix was
correct and it was found by this same "your own artefacts are in the corpus"
mechanism. Its cost was invisible until a test file appeared whose runner
genuinely lives in another module.

So the census's published totals (`992 calls, 873 programs, 73 files`) are a
floor, and the gap is not random: it is exactly the test files that drive the
language through a helper rather than through `Interpreter()` or `parse()`
directly. Nothing here is wrong; the ledger's own row for this file says
`programs: 0` and that is a true statement about what the harvester found.
But "the test corpus" and "the Whence programs in `tests/`" are now known to
be different sets, and only the first has a number.

---

## 9. The bank, scored

`state/round-504/predictions.md`, committed before any measurement.
**19 scorable lines: 11 HIT, 1 PARTIAL, 7 MISS.**

### First, a disclosure that was wrong

The bank's §0 disclosed, as an already-observed fact, that round 503's sweep
called **30** interp.py defs `unreferenced` and **7** `test_only`. Counted
from the artefact rather than eyeballed off a printed list, it is **31** and
**6**. The total, 37, was right. This is not a scored line — it is a
disclosure — but it is the same error class as five of round 503's seven
misses (*a number read off prose instead of counted from the file*), arriving
one round later in the section specifically designed to keep observations out
of the scoring. Recording it rather than quietly fixing it.

### A — the instrument

| id | prediction | verdict |
|---|---|---|
| **A1** | `interp.py` goes 37 → 0, all 31 + all 6 flip | **HIT** — `0 test_only, 0 unreferenced` over 174 defs |
| **A2** | whole-repo not-live 294 → **240–285** | **MISS** — 199. The drop was 95, not the 9–54 banked. I sized the effect from the assumption that other files in the repo would carry decorator-registered defs; A5 is why they do not |
| **A3** | `test_swe_scopecall.py` green at **≥ 76** | **HIT** — 82 passed |
| **A4** | both round-137 snapshots go to 0 | **HIT** — 30 → 0 and 30 → 0 |
| **A5** | ≥ 1 file OUTSIDE the whence tree loses ≥ 2 not-live defs | **MISS, and it is the round's best miss.** **Zero** files outside the whence tree moved by even one. This repository has one registration decorator in it. The 78 %-of-all-`unreferenced` headline is not a general fact about the codebase; it is a fact about how much of that codebase's orphan count was a single interpreter's builtin table |
| **A6** | `curecheck.py`'s 8 and `depthcensus.py`'s 8 are unchanged | **HIT** — both unchanged |

### B — the language-level census

| id | prediction | verdict |
|---|---|---|
| **B1** | **3–10** builtins never called by any `examples/*.lang` | **MISS** — **0**. Every one of the 37 is called by a shipped example, and 23 parseable example files were enough to cover the whole surface |
| **B2** | **0–3** builtins called by nothing in the repo | **HIT** — 0 |
| **B3** | `contrast` and `is_guess` each ≤ 2 example sites | **PARTIAL** — `contrast` 2 ✓, `is_guess` 11 ✗ |
| **B4** | `print` is the most-called builtin | **MISS** — `len` (251) over the whole corpus; **`missed`** (186) over `examples/` alone, where `print` is fifth. §3 |
| **B5** | the two levels disagree for **≥ 30** of 37 | **HIT** — 37 of 37, and §5 shows the residual correlation is inverted |
| **B6** | ≥ 1 of the Python-`test_only` set is called by a shipped example | **HIT** — all 6 are |
| **B7** | top-3 share **≥ 40 %** | **MISS** — 30.6 % over the full corpus. (44.7 % over `examples/` alone — the banked line said "across the corpus", so it scores against 30.6 %.) The test corpus is far flatter than the examples: it is written one builtin at a time |

### C — corpus mechanics

| id | prediction | verdict |
|---|---|---|
| **C1** | **400–1500** harvested guest programs | **HIT** — 873 |
| **C2** | **2–20 %** of harvested programs fail to parse | **MISS, badly** — **0 %**, 0 of 873. The one failure the first run reported was `RecursionError` *inside this module* (§4), i.e. the number I would have quoted as "0.1 % of the test corpus is unparseable" was 100 % an artefact of my own walker. The premise was wrong too: the suite's parse-error fixtures are not reachable by `harvest_tests`, which harvests programs that get *run* |
| **C3** | census under **60 s** | **HIT** — 9.8 s (harvest 8.9 s of it) |

### D — shadowing

| id | prediction | verdict |
|---|---|---|
| **D1** | ≥ 1 corpus program shadows a builtin name | **HIT** — exactly 2, both `len`, both in `tests/test_v07.py` (one `fn len(...)`, one parameter named `len`) |
| **D2** | if D1, the naive count is HIGHER than the resolved one | **HIT** — `len` naive 252, resolved 251. One of the two shadowing bindings has no later use under it, so it removes nothing; the invariant `resolved ≤ naive` is asserted directly by `test_shadowing_can_only_remove_uses_never_add_them` |

### E — regression floor

| id | prediction | verdict |
|---|---|---|
| **E1** | whence fast tier green before AND after | **HIT, both halves** — 2893 passed / 3 skipped / 116 deselected in 375.78 s before; **2916 passed / 3 skipped / 119 deselected in 378.30 s** after. Not a straight-through green: the first after-run was **5 failed / 2911 passed**, all five the "your own artefacts are in the corpus" class, and §8b is what they turned out to be |
| **E2** | the two briefed reds reproduce, i.e. are not runner artefacts | **HIT** — 1.37 s, deterministic, cause identified and closed (§6) |

### The shape of the misses

Five of the seven (A2, A5, B1, B4, B7) are one error and it is not the same
one round 503 made. Round 503 banked numbers copied from stale prose; this
round's numbers were re-derived. What went wrong here is that **I predicted a
distribution from a single observed instance.** I had seen one decorator
registry (whence's), so A2/A5 assumed there would be more like it; I had seen
that `print` is the builtin a language *tutorial* uses most, so B4 assumed it
led the corpus. The corrective is not "re-derive first" — everything here was
derived — it is that a prediction about a POPULATION needs a reason to
believe the population is like the one case you looked at, and "it is the
case I happened to look at" is not one.

The one exception is C2, which failed on a premise: I predicted a
parse-failure rate for a harvester I had not read the selection rule of.
`harvest_tests` collects programs that get *executed*, so parse-error
fixtures are structurally absent. A rate predicted over the wrong population
is not a wrong estimate, it is a category error — the same shape as round
502's P4, which reasoned carefully about a function nothing calls.

---

## 10. What the next round should take

1. **`typed` is the one measured gap in the language's demonstrated
   surface**: 1 use in `examples/`, 47 in the test corpus, the widest ratio
   of any builtin. It is the type-contract builtin — v0.19's `-> Type` and
   parameter annotations run through it — and the corpus that shows it off
   is entirely internal. Either an example demonstrates it or the round that
   decides not to should say why. language(C).
2. **`builtinlive.py --strict` is a ratchet nothing schedules, and its
   registry entry says so by being the wrong shape.** A pre-commit hook
   demanded a `harness/wiring-registry.json` entry; `wiring_audit declare`
   offers `wired via languages/whence/tests/test_builtinlive.py:19`, and
   `manual` is a **W003 ERROR** for a path that IS reachable, so
   wired-by-its-own-test is the only status the registry can express. That
   took `scopecall.py registry --strict`'s *"declared `wired` by their own
   tests and nothing else"* class from 30 to **31** — this round knowingly
   adding an instance to the class round 503's next-step #1 exists to
   resolve, because hiding it under `manual` would be using the registry to
   conceal a finding, which is the same move as the scope comment that
   vouched for itself. Same shape round 450 left `killerrepin` in: the tool
   exists, no tier runs it, and the two live-corpus assertions are
   `whence_slow`-marked so the fast tier does not carry them either. Wire it
   into a tier or say which tier owns it. language(C) or harness(A).
3. **`uses_in` in this round's own module verdicts `unreferenced`, and it is
   right.** After the refactor that split parse from walk failures, the
   single-program entry point is called by nothing but its own tests, which
   makes it `test_only` once the sweep re-runs against the new test file.
   Left as-is deliberately — it is the documented single-program API and
   contorting code to please an instrument is the failure mode one level up
   from the one this round fixed — but it is disclosed rather than
   discovered later. language(C).
4. **`depthcensus.harvest_tests` under-counts by a NAMED shape and now has
   a live instance.** `tests/test_builtinlive.py` contributes `programs: 0`
   to the contributions ledger while holding 11 literal guest programs,
   because its runner is `BL.uses_in` — an imported-module receiver, which
   round 470 excluded on purpose. Either `runners_in` learns to follow a
   same-tree module's runners (a real widening, and round 468's warning
   about widening to make a number bigger applies), or the ledger's `_what`
   says out loud that it counts programs run through IN-FILE runners only.
   Do not just bump the total. §8b. language(C).

5. **The `INERT_DECORATORS` list has never been falsified.** Sixteen names,
   chosen by reading, and this repo contains almost no decorators at all
   (A5), so the sweep exercised the *inert* branch essentially nowhere
   outside `tmp_path` fixtures. The honest test is a tree that actually uses
   `@property`/`@staticmethod` heavily — `nuc/fast_lane/colibri-c` is the
   nearest candidate. Until then the list is a design, not a measurement.
   harness(A).
6. **Round 503's next-steps #1, #2, #3, #4 stand, untouched by this round.**
   #5 is CLOSED by this round, in both halves (the 37 read, and the question
   re-asked). #6 has a concrete instance and a closed instance of it (§6) but
   the general defect — *nothing detects the pair at the moment a round
   dies* — is still unbuilt. #7's standing items are unchanged.
7. **`nproc` is 1 and the box is not idle.** The whence fast tier took
   375.78 s solo this round against 194 s for round 499 and 378 s for round
   500 on the same 2893-ish node set. Any wall-clock number in this file is a
   measurement of this box on this day; the census's 9.8 s and the sweep's
   51.6 s included.
8. **Standing and untouched:** the NUC `retention --strict` deadline;
   `case_coverage`'s disagreeing verdicts; `claim_check` executing 0 of its
   commands; the operator-blocked probe batch (now 51 deep, this round added
   one with a scorable prediction); and CLAUDE.md's `CRITICAL MISSION` and
   `MASTER MISSION` blocks — both still a deletion for the operator, and note
   that `CRITICAL MISSION #476`'s premise is measurably false in this round's
   own data: `b_fold` is at line 3772, not 2666, and `fold` is called at 19
   sites in `examples/` and 64 in the test corpus, all of them passing.
   `languages/whence/SECURITY.md` remains the operator's decision; the
   checker's own line is the only source for its carry count.
