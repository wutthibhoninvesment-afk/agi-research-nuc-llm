# Round 462 (language C) — the residual that was not a residual

**Subject.** Round 458's next-step 2: *"The harvester's residual is 257
programs and nothing narrows it. 127 unresolved names … and 130 non-constant
source nodes (BinOp 120, List 38, Call 23, Subscript 9, IfExp 1). … The
cheapest next slice is the BinOp class."*

**Result.** The residual was wrong in **both** directions at once, and the
direction round 458 named is the smaller one.

* **Precision.** 51 of the 131 non-constant entries — 39% of that class, 20%
  of the whole declared residual — are call sites that are not Whence runners
  at all. `subprocess.run([sys.executable, RUN, path])` (45 calls, 43 in the
  residual, first argument an argv **list**) and `interp.exec_stmt(
  prog.stmts[0], env)` (17 calls, 8 in the residual, first argument an
  already-parsed **statement**). The instrument was overstating its own blind
  spot.
* **Recall.** The classes that really were missing are the ones where *the
  right answer is more than one program*. A `str | None` folder reports
  "several answers" as "no answer", which is the same overstatement in a
  different place.
* **The corpus was never contaminated — only the self-report.** 0 harvested
  programs come from a `subprocess` or `exec_stmt` site, before or after. The
  fix loses **zero** of round 458's 488 programs and adds 71.

**Artefacts.** `depthcensus.py` (+~350, `_SRC_ARG0_ATTRS`, `_imported_modules`,
`_receiver`, `_literal`, `_const_strs`, `_cross`, `_product`, `--tests`),
`tests/test_testcorpus_census.py` 18 → 30 tests, `SPEC.md` **decision 56**,
`skills/residual-audited-both-ways/SKILL.md`,
`state/whence/round-462/{PREDICTIONS.md,test-census-suite.json,census-suite.txt}`.
Predictions banked at `02606e7`, **after** the baseline was measured and
**before** any code changed.

---

## 0. Housekeeping, and the baseline that refuted its own citation

`git status` opened with one line, `languages/whence/SECURITY.md` — the
acknowledged shape-5 escalation, content unchanged, not this program's, and
still the operator's. Not touched, and no carry count is copied here.
`state/slow-tier-ledger.jsonl` was **not** dirty: round 457's fix has now
held for four consecutive rounds, and the seven-round streak of rounds
landing their predecessor's ledger row is over.

The baseline was **measured, not quoted** — round 460's item 5 and round
461's P1–P4 are the same lesson twice, and this is the first round to apply
it. `harvest_tests()` at `508b95f`:

    files 62   calls 985   programs 488 (499 before dedup)
    unresolved_args 127   nonconstant_programs 131   forwarded_args 81
    parse_only 73   unparsed 3   ambiguous_scopes 22
    executing_runners 69   parse_only_runners 29

and the non-constant class re-derived node by node:

    38 List       35 BinOp:Add   25 BinOp:Mod   18 Call:join
     9 Subscript   4 Call:read     1 IfExp        1 Call:replace   = 131

Round 458 published `BinOp 120, List 38, Call 23, Subscript 9, IfExp 1`.
**That breakdown sums to 191 against its own stated total of 130.** The BinOp
class is **60**, not 120; the total is **131**, not 130. Two of the five
numbers in the next-step were wrong before anything ran — the sixth
consecutive round in this program where re-deriving a carried number changed
its answer, and the first where the refutation came out of the *baseline*
rather than out of the work.

The classification is what found the real defect, and it took twenty lines.
The counter alone (`nonconstant_programs: 131`) says only "widen the folder".
One row per entry, with a file:line and a node kind, says "a third of these
are `subprocess`".

---

## 1. One predicate, two questions

    _EXEC_ATTRS = ("run", "exec_stmt", "exec_src", "eval_src")

answered both of:

* *does this call execute guest source?* — the seed of the runner fixed
  point, which decides whether a helper is an executing runner; and
* *is this call's first argument a source string?* — what puts a node in a
  source position, and therefore what puts it in the residual when it does
  not fold.

They disagree on real code. `exec_stmt` **executes** — a function containing
it really is a runner — but takes an `ast`-level statement. Under one tuple,
every `exec_stmt` call was a program the harvester "could not reach" where
there was no program to reach. `test_v09.py:277-281` is three of them in
three consecutive lines, and they are the whole `Subscript` class:
`prog.stmts[0]` is a subscript because it is an AST index, not because a
source string was computed.

    _EXEC_ATTRS     = ("run", "exec_stmt", "exec_src", "eval_src")   # executes
    _SRC_ARG0_ATTRS = ("run",              "exec_src", "eval_src")   # arg0 is source

`test_exec_stmt_takes_a_statement_and_not_a_source_string` pins both halves:
the synthetic runner is still in `executing_runners`, its program is still
harvested from the outer call site, and `stmt_node_args == 1`.

## 2. `.run` is not owned by Whence

`subprocess.run` is 45 of the 985 calls. The exclusion is derived from the
module's **own imports**:

```python
def _imported_modules(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):            # NOT ImportFrom
            for a in node.names:
                out.add(a.asname or a.name.split(".")[0])
    return out
```

A denylist `{"subprocess", "sp", "os"}` would have passed exactly the same
tests and been a guess about a corpus rather than a fact about a file.
`ImportFrom` is excluded on purpose and it is the near miss: `from
whence.interp import Interpreter` binds a **class**, and a class is exactly
what a legitimate receiver may be. `test_an_imported_module_is_not_confused_
with_an_imported_class` pins it.

**Both exclusions are counted, and printed above the corpus.**

    excluded: 45 module calls + 22 statement-node args
              (not residual -- not source positions)

A call dropped for a stated reason and a call that defeated the walk are
different facts. Sharing a counter is *how* the overstatement happened, so
the repair is a second counter, not a smaller first one. The arithmetic
reconciles against the old number and that reconciliation is a test:
**918 + 45 + 22 = 985**, exactly.

## 3. `str | None` cannot say "two programs"

The remaining residual classes are decidable, and the reason round 458 could
not decide them is a type:

    val("let result = [f] == [f]\nfn f(x) { x }\n" if False else
        "fn f(x) { x }\nlet result = ([f] == [f] rescue \"miss\")")

is two programs. So is

    for spec, want in NAME_SLOT_CASES:                    # 8 rows
        host_reason('let r = typed(1, %s, "L")' % spec)

`_const_str` returns one string or `None`, so both are misses. `_const_strs`
returns the **list** of strings a node can denote: a literal, a name (every
binding), a `+` chain, an f-string, a `%` template, a constant `.join`, a
`.replace`, and both arms of an `IfExp`.

`%` needed a second environment. Its right operand is not a string, so the
string folder cannot reach it; `_literal(node, lits)` returns the Python
object a node denotes (with `_NOLIT` as the sentinel, because `None` is
itself a legal literal), and the same environment is what lets the binding
pass unpack `for spec, want in NAME_SLOT_CASES:` over a module-level table of
tuples. That one shape is 25 of the 131.

The product is capped at `MAX_FOLD = 32` per node **and the cap is a
counter**: `A + B` with five bindings each is twenty-five programs, and a
harvester that expands that silently reports a corpus larger than the suite
runs. At HEAD the cap fires 0 times; the counter exists so that the next
widening cannot hide behind it.

## 4. The measurement

    harvested programs        488 -> 559     (+71, strict SUPERSET: 0 lost)
    runner calls              985 -> 918     (= 918 + 45 + 22, exactly)
    unresolved names          127 ->  94
    non-constant nodes        131 ->  72
    declared residual         258 -> 166     (-36%)
    excluded, counted           0 ->  67
    multi-valued nodes          -    30
    fold capped                 -     0
    parse-only programs        73 -> 145     (folding reaches parse-only
                                              runners too; counted, not run)

Where the 71 came from, by file: `test_v29.py` 26, `test_self_eval.py` 11,
`test_contract_message_differential.py` 8 (the `%` table), `test_v33.py` 6,
`test_v05.py`/`test_v20.py`/`test_v44.py` 4 each, `test_v06.py` 3,
`test_fuzz_regressions.py` 2 (the `IfExp`, both arms), `test_v27.py` 2,
`test_v31.py` 1.

**The superset property is the proof that the precision fix was not too
wide**, and it is a set difference against the module at `508b95f`, not an
argument: `old_keys - new_keys == set()`. If an exclusion had eaten a real
program that difference would be non-empty, and a "conservative" fix would
have deleted evidence.

### 4.1 The census, at the depths the suite really uses

559 programs, suite mode, **0 errors, 0 not-ok, 28.1 s of interpreter time**.
0 of 559 alloc-tracker disagreements; 0 allocation caps hit.

    20000  test_testcorpus_census.py:41   md=20000  N=120043
     3001  test_v04.py:259                md=3000   N=9050
     2501  test_trampoline.py:72          md=20000  N=17548
     2501  test_v04.py:264                md=20000  N=30054
     1502  test_fuzz_regressions.py:61    md=20000  N=18061   (recovered here)

    depths: 20000 x492, 500 x50, 300 x5, 50 x4, and one each of
            5000 600 3000 100 60 10 2 1

**The champion does not move: still 20000, still second at 3001.** Decision
55 survives its instrument getting 15% larger, which is the strongest thing
that can be said for it.

### 4.2 But the champion's NAME moved, and not because of this round

Round 458 published the deepest program as `test_v44.py:332`. At HEAD the
census names `test_testcorpus_census.py:41`, and `test_v44.py:332` is not in
the corpus at all — the harvest dedups on `(src, max_depth)` **across files**,
and `sorted(os.listdir())` puts `test_testcorpus_census.py` first.

Re-run the **round-458 module** against HEAD's tree and it names
`test_testcorpus_census.py:41` too. So this round's fold did not move it:
round 458 ran its census, then wrote a test file containing the same program,
and its published attribution was stale against its own commit before the
round ended. **Writing a test about the champion moved the champion's name.**
Round 458's own lesson — *a depth is a property of the runner, not of the
program* — has a second half: **an attribution is a property of the dedup
order, not of the program.** The depth is the durable fact; the file:line is
not, and a SPEC that cites one had better cite the other.

## 5. Wiring (round 458's item 1), and it was worse than "unscheduled"

Round 458's next-step 1 said `depthcensus.py` "is STILL not wired into any
tier or health check". It understated it. `main()` parsed
`--json/--roots/--no-alloc/--program/--max-nodes` and called `census()` over
`examples/` — **there was no command line that could reach `harvest_tests` or
`census_tests` at all**, by a tier or by a person. A schedule cannot be
argued about before the entry point exists.

    python3 depthcensus.py --tests [suite|default] [--limit N]
                           [--harvest-only] [--json OUT]

`--harvest-only` is the cheap one (**1.6 s**, AST only) and prints the
residual, the exclusions and the fold counters on stderr *before* the corpus,
because an instrument whose coverage line is below a hundred rows of output
is an instrument whose coverage nobody reads. Whether it gets a *tier* is
still open (next-steps item 1) — but it is now a schedulable command rather
than a library function.

## 6. Predictions: 10 HIT, 3 MISS, 1 PARTIAL of 14

Banked at `02606e7` in `state/whence/round-462/PREDICTIONS.md`.

| | claim | outcome |
|---|---|---|
| P1 | precision, not recall, is the larger defect; >25% of the 131 are not runners | **HIT** — 51/131 = 39% |
| P2 | `subprocess.run` is 35–50 of the 131 | **HIT** — 43 |
| P3 | `exec_stmt` is 5–12 of the 131 | **HIT** — 8 |
| P4 | 0 harvested programs from those sites | **HIT** — 0, and 0 lost programs confirms it |
| P5 | the split does not shrink the corpus; runners stay 69 | **HIT** — 559 ⊃ 488, 0 lost; 69 unchanged |
| P6 | the fold recovers 40–120 programs (528–608) | **HIT** — +71, 559 |
| P7 | the champion does not move | **PARTIAL** — the depth does not (20000, 3001); the **file:line does**, for a reason that is not this round's (§4.2) |
| P8 | `unparsed_programs` rises above 3 | **MISS** — still exactly 3. Every folded template produced legal Whence; the ill-formed cases go through parse-only runners, and `parse_only_programs` 73→145 is where they went |
| P9 | ≥10 recovered programs come from a multi-valued node | **HIT** — 30 |
| P10 | residual falls ≥60 and does not reach zero | **HIT** — 258→166 (−92), both counters positive |
| P11 | harvest <20 s; one census <200 s | **HIT** — 1.6 s and 28.1 s |
| P12 | no `SPEC.md` constant changes | **HIT** — decision 56 added, 53/54/55 unamended |
| P13 | `src` is 70–95 of the 127 and halves | **MISS on the second half** — `src` was 82 of 127 (in range), but the total fell only 127→94. The `src` class is dominated by `"".join(parts)` over a loop-built list, which is the honest residual, not a folding gap |
| P14 | the test census has no CLI path at all | **HIT** — `main()` never called `census_tests` |

**The split that matters:** every prediction derived from code already read
(P1–P5, P12, P14) held, and the three that missed or partialled are all
predictions about a *population* — how many templates are ill-formed (P8),
how much of one name's class is foldable (P13), which file wins a dedup
(P7). This is round 458's own P1/P2-vs-P3/P4/P8/P9 split, reproduced exactly
one language round later. **Derive from the artefact or bank a wider band;
do not bank a point estimate about a population nobody has counted.**

## 7. Tests

* `tests/test_testcorpus_census.py` **18 → 30 passed in 2.27 s** (round 458's
  knowledge file calls this file "25 tests"; it collects 18 at HEAD, 0
  deselected — a third stale carried number, recorded and not built on).
* `tests/test_depthcensus.py` **45 passed, 3 deselected in 0.37 s**.
* whence fast tier — see §7.1.

Twelve new tests, one per finding: the two exclusions and their counters, the
import-vs-import-from distinction, the reconciliation `918+45+22 == 985`, the
superset property, the residual staying positive, the `IfExp`, the `%` table,
the f-string, the constant-vs-loop-built `.join` boundary, and the `MAX_FOLD`
cap.

## 7.1 Fast tier

    ./run_tests_fast.sh
    2392 passed, 3 skipped, 103 deselected in 227.90s (0:03:47)   rc=0

Started solo after the census had finished (`nproc` is 1). Green.

## 8. What this round did NOT do

* The `whole-tree` and `shared-corpus` health checks (round 461's items 4
  and 5) were not run by any rule; this round ran only the whence tier.
* The remaining 166 residual entries are not narrowed further and two classes
  are argued to be undecidable rather than measured to be.
* Round 458's items 3 and 5 (`FULL_SHOW_NODES` vs `DEFAULT_MAX_DEPTH` being
  the same number; `self_eval.lang`'s `reify` depth bound) are untouched.
