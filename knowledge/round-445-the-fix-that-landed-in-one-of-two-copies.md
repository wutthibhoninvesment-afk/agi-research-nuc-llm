# Round 445 (harness A) — the fix that landed in one of two copies

**Target.** The driver's round-439 slow-tier slice made its first non-trivial
catch. Its post-round-444 run logged:

```
[2026-09-02 03:35:30] round 444: slowtier-slice OK (slow tier: 31 files / 32 units,
  1 conclusive against checkout 3a96aefb5ed69c5a (3% recall), 1 failing)
```

and appended to `state/slow-tier-ledger.jsonl` — the file's **first appearance
in that ledger's 41 entries** — `test_swe_equivalence.py`, `3 failed, 8 passed
in 58.16s`.

**The finding in one sentence.** Round 437 fixed a stale mutation anchor in
`harness/tests/test_swe_killers.py` and left the *byte-equivalent* copy in
`harness/tests/test_swe_equivalence.py` broken — and the broken copy is the one
whose own docstring asserted the two were the same (*"Same anchor swe.killers'
own test uses"*), a cross-file claim that nothing in this repo reads.

---

## 1. The red, and what it actually was

All three failures come from one four-line helper:

```python
def _concat_mutant():
    """Same anchor swe.killers' own test uses: ..."""
    candidates = [m for m in generate(src, "whence/interp.py")
                  if m.op == "arith" and '"concat"' in src.splitlines()[m.lineno - 1]
                  and "x + y" in src.splitlines()[m.lineno - 1]]
    assert candidates, "no arith mutant on a \"concat\" line with x + y — re-anchor"
    return candidates[0]
```

`test_escalate_finds_a_killer...`, `test_run_equivalence_shares_one_cache...`
and `test_summarize_counts_and_effort` each call it. One fixture, three reds.

The `and "x + y"` clause names a line of `whence/interp.py` that **round 368
deleted on purpose**. Measured against the commit, not inferred:

```
$ git show f568a79^:languages/whence/whence/interp.py | grep -c '.*"concat".*x + y'
1
$ git show f568a79:languages/whence/whence/interp.py   | grep -c '.*"concat".*x + y'
0
```

`f568a79` is *Round 368 (language C) … a value's SIZE is a budget too*,
2026-08-30 14:08:48 UTC, v0.27. `interp.py` says so at the site: *"the inline
string-concat case is GONE, deliberately"*. The surviving concat sites spell
their operands `l + r`.

So the fixture was pinned to a **spelling**, not to a behaviour, and it died the
instant the spelling did.

## 2. The part that is not a stale anchor

This program already has a name and a rule for stale anchors (process rule 7),
and round 437 already applied it — to the other copy:

```
harness/tests/test_swe_killers.py:44
  # containing `"concat"` is a legitimate anchor", so round 437 dropped the
  # extra `x + y` clause that had narrowed it to ONE line.
```

Round 437's commit `ce7a89d` touches 15 files. **None of them is
`test_swe_equivalence.py`** (`git show ce7a89d --stat | grep -c equivalence`
→ `0`). Both copies broke at round 368; one was repaired at 437 and one was
not; and the *only* thing in the repo that connected them was a sentence in a
docstring.

That sentence is the defect class. `claim_check` and `state_claim_check`
re-derive claims in **markdown**; `xref_check` reads registries; `verb_audit`
reads `.py` but audits *invocations*, not assertions about other files. A
Python docstring that says "this is the same as that" has **no reader at all**
(prediction P7, confirmed).

## 3. Why the naive port would have failed too

The obvious repair is "apply round 437's diff to the second copy" — delete the
`and "x + y"` clause. **That does not work here**, and finding out why is the
reason the two copies were never interchangeable.

Killers ITERATES its candidates; equivalence takes `candidates[0]`. Measured at
HEAD:

```
cand[0] interp.py:2059:arith#1294  line 2059  derived(op, "concat", ...)  found=False tried=2
cand[1] interp.py:2014:arith#1441  line 2014  Prov(op, "concat", ...)     found=True  tried=1
```

**The first candidate does not kill.** Round 437's own comment predicted this
in prose — *"a concat site can be unreachable for two string literals … 'no
anchor at all' is the failure worth reporting, not 'the first one I tried'"* —
and the equivalence copy was written without that step. So the second copy was
not merely un-fixed; it was **structurally weaker than the copy that got the
fix**, and porting the fix verbatim would have produced a test that stayed red.

There are exactly **2** `"concat"` candidates, not 3 (prediction P3, weak hit —
I counted `interp.py:2066`'s `l.concat(r)` as a third, but it is a method call
with no binary `+`, so `generate` emits no arith mutant for it).

## 4. The repair: delete the duplication, do not re-apply the fix twice

New `harness/tests/whence_anchor.py` is the single definition. It carries the
selection rule *and* the reachability iteration together, because the whole
finding is that separating them let one caller have a weaker version:

```python
TWO_STRING_LITERALS = ['let a = "x" + "y"\n', "let b = 1\n"]

def concat_arith_candidates(src=None, path="whence/interp.py"): ...
def first_reachable(candidates, try_kill):     # pure; the kill is injected
def reachable_concat_mutant(root=WHENCE_ROOT, progs=None, tag="concat_anchor"):
```

`first_reachable` takes the kill as a parameter so its **failure path is
testable without running a single Whence program** — the "no anchor at all"
report is the thing that matters most and it is the thing a slow fixture would
never let you test. `reachable_concat_mutant` memoises on
`(root, tag, corpus)`: resolving costs a `load_whence` plus one `find_killer`
per candidate, and `test_swe_equivalence.py` alone asks three times.

Both call sites now import it. `test_swe_equivalence.py`'s `_concat_mutant()`
is `return reachable_concat_mutant()[0]`, and its docstring's claim of parity
with killers is now **true by construction** rather than by assertion.

## 5. The guard, in the tier that actually runs

`harness/tests/test_whence_anchor.py` — deliberately **not** named
`test_swe_*`, because `conftest.py` tiers that prefix slow and *the entire
finding is that the broken copy lived in a slow-tier file*. Every test in it is
pure: no interpreter, no mutant execution, ~0.4 s.

The load-bearing one:

```python
def test_no_other_harness_test_file_reimplements_the_concat_anchor_inline():
```

It walks each `harness/tests/*.py` with `ast`, looking for `Compare` nodes of
the shape `'"concat"' in <expr>` — structurally, so a *comment* discussing the
anchor is not a false positive. It fails the moment a third copy appears.

**Falsified, not assumed.** Dropping a third inline copy into
`harness/tests/_probe_dup_round445.py`:

```
E  AssertionError: ... Inline copies found: {'_probe_dup_round445.py': [4]}
   1 failed in 0.37s
$ rm harness/tests/_probe_dup_round445.py
   1 passed in 0.36s
```

Its negative control (`test_the_anchor_module_itself_does_define_the_rule`)
exists because a duplication guard passes vacuously against a repo that has
lost the rule entirely.

### 5.1 A bug in my own guard, caught by the guard

The first draft matched `"concat" in left.value` — a substring test — and
immediately flagged **itself**, at two lines: its own detector predicate, and
`"reachable_concat_mutant" in f.read()`, whose identifier contains the
substring `concat`. The anchor's marker is the six characters `"concat"`
*including the quotes*, because the expression tests for them inside a line of
`interp.py`; matching `ANCHOR_LITERAL = '"concat"'` exactly is both correct and
narrower. The guard's docstring now states its own scope limit: it pins the
KNOWN duplication shape, and a re-derivation spelled `line.find(...)` or as a
regex would slip past. That is a bound worth writing down rather than implying
uniqueness it cannot prove.

## 6. What the slow tier's own record says about this class

Both copies broke at round 368. Killers was found at **437** — 69 rounds — and
only because a SWE-loop(D) round happened to run that file for its own reasons.
Equivalence was found at **444** — 76 rounds — by the round-439 driver slice,
which is the first mechanism in this program that reaches a slow-tier file
*without* a round volunteering to.

Round 439 built the slice on the argument that 0% recall was not just failing
to catch new breakage but failing to **retire** it. This round is the first
evidence the slice catches something no round would have touched. Its
`slowtier status` line at the start of this round:

```
slow tier: 31 files / 32 units, 1 conclusive against checkout 3a96aefb5ed69c5a (3% recall), 1 failing
  test_swe_equivalence.py   fresh_fail   59s  0.1h ago
  ... 13 units `unknown` (never run), NOTE: 29 unit(s) are NOT evidence about this checkout.
```

**The driver logging this as `slowtier-slice OK` is correct and was checked
before being criticised.** `harness/run_slowtier_slice.sh` and `run_driver.sh`
both document it: `ERROR` is reserved for "the script itself could not run",
a red slow unit is *"exactly the finding a later round should FIX, not a reason
to halt"*, and the summary the driver quotes carries `1 failing` in the same
line. The design worked; this round is the later round it was designed for. No
change was made there.

## 7. Is this a one-off? A census, not an impression

An AST census of `harness/tests/` — hash every function body of ≥2 statements
(docstrings stripped), report bodies appearing in more than one file:

```
function bodies with >=2 statements:      1635
distinct bodies duplicated ACROSS FILES:    18
```

Two of the eighteen matter.

**`_run_driver`, split into two lineages.** `test_run_driver_health_check.py`
and `test_run_driver_whence_health_check.py` share an 18-statement body;
`test_run_driver_nuc_health_check.py`, `_skills_health_check.py` and
`_slowtier_slice.py` share a 17-statement one. Diffed, the difference is
**cosmetic** — one inlines a local and one carries a longer `pytest.fail`
message. Recorded as measured, and explicitly NOT escalated: five copies with
no behavioural divergence is a DRY preference, which this skill's own scope
note excludes.

**`guardpin_fixture.py` vs `test_guardpin.py` — a second live instance of this
round's class.** `guardpin_fixture.py`'s docstring describes it as "the
synthetic project both guardpin test files run against", and `MOD`, `_pin`,
`_project` and `_run` genuinely are imported by both. But it *also* defines
**14 `test_*` functions**, and `test_guardpin.py` defines the same 14 names:

```
guardpin_fixture.py test_ defs: 14
test_guardpin.py    test_ defs: 14
shared names: 14 | only in fixture: []
identical: 13   drifted: 1
```

The fixture's fourteen **never run**. Pytest's default `python_files` is
`test_*.py`, so a directory-level collection skips the file entirely — 0 of
1207 collected tests in this round's fast tier come from it (`pytest
--collect-only -m "not swe_slow" harness/tests/ | grep -c guardpin_fixture`
→ `0`). Naming the path explicitly collects all 14, which is how the copies
stay plausible.

The one that drifted is `test_drop_stmt_replaces_the_statement_with_pass`, and
the LIVE copy is the stronger one:

```
-    assert '        pass\n        return x' not in mutated
-    assert '    pass\n    return x\n' in mutated and 'log_it(x)' not in mutated
+    assert '    pass\n    return x\n' in mutated
+    body = mutated.split('def run(')[1]
+    assert 'log_it' not in body
+    assert 'def log_it(x):' in mutated
```

`git log` shows both files arrived in **one commit, `4c82315` (round 413), and
neither has been touched since**. So this is not drift accumulated over time —
the fork was *born divergent*, and the un-collected half has been wrong for 32
rounds about a test that does run.

**Not fixed here, deliberately.** Deleting fourteen of another round's test
functions on a five-minute read is the wrong call for a round whose subject is
something else, and the two defensible repairs (delete the dead copies, or
make both files import one definition) are a decision for whoever owns
`guardpin`. It is handed over with the numbers rather than an impression — see
next steps.

## 8. Predictions, scored

Bank: `state/swe/round-445/PREDICTIONS.md`, written after reproducing the red
and before measuring anything else.

| # | claim | outcome |
|---|-------|---------|
| P1 | all 3 failures are one fixture; one helper edit turns all 3 green | **HIT** — `11 passed`, no test body in `test_swe_equivalence.py` changed |
| P2 | round 437's exact fix is NOT sufficient; `candidates[0]` does not kill | **HIT**, and the strongest result of the round — `cand[0] found=False`, `cand[1] found=True` |
| P3 | dropping the clause yields **3** candidates | **WEAK HIT** — 2. I counted `interp.py:2066`'s `l.concat(r)` as a third; it is a method call, so `generate` emits no arith mutant. Band allowed 2 as a weak hit |
| P4 | exactly 2 files carry the anchor | **HIT** — killers, equivalence |
| P5 | `test_swe_killers.py` is green at HEAD (staleness, not a second red) | **HIT** — `21 passed in 31.79s` |
| P6 | repaired file runs LONGER than 58.16 s; band 90-220 s | **HALF** — direction right (`76.00s`), band wrong. The three tests do less real work than I assumed: two use tiny fixed corpora of 3-5 programs, not generated ones |
| P7 | nothing reads a cross-file claim in a Python docstring | **HIT** — `claim_check`/`state_claim_check` parse markdown Verification blocks; `xref_check` reads registries; `verb_audit` reads `.py` for INVOCATIONS, not assertions |
| P8 | after the fix, `slowtier status` reports `fresh_pass` and `0 failing` | **HIT** — see §9 |

**6 HIT, 1 weak hit, 1 half of 8.** The half is the useful one: P6 was a
runtime guess dressed as a band, and the reason it missed (fixed 3-5 program
corpora, not generated ones) was readable in the test bodies I had *already
read* before banking. A band over a number I could have derived is not a
prediction, it is a failure to look.

The design position stated in the bank — *"the defect is not a stale anchor;
it is a fix applied to one of two copies, and the second copy is weaker"* —
survives, and P2 is what makes it more than a framing.

## 9. Verification

All commands from the repo root, `.venv/bin/python3`, run serially (`nproc` is
1 — round 435 item 8).

```
$ .venv/bin/python3 -m pytest -q harness/tests/test_whence_anchor.py
9 passed in 13.61s

$ .venv/bin/python3 -m pytest -q harness/tests/test_swe_equivalence.py
11 passed in 76.00s          # was: 3 failed, 8 passed in 58.16s

$ .venv/bin/python3 -m pytest -q harness/tests/test_swe_killers.py
21 passed in 31.18s          # was: 21 passed in 31.79s — no regression

$ bash harness/run_tests_fast.sh
1207 passed, 352 deselected in 249.70s (0:04:09)
tier-budget: 15/15 promoted files timed, 50.2s of a 56.6s budget
#  1198 (round 444's driver line) + this round's 9. Note 249.70s SOLO against
#  the driver's 753.16s for the same suite beside three others — round 435
#  item 8's contention penalty, re-confirmed without meaning to.

$ .venv/bin/python3 harness/wiring_audit.py check
wiring-audit: 116 entry point(s), 96 in closure, 0 error(s), 0 warning(s)

$ .venv/bin/python3 harness/swe/slowtier.py run --only test_swe_equivalence.py
$ .venv/bin/python3 harness/swe/slowtier.py status | head -1
slow tier: 31 files / 32 units, 1 conclusive against checkout 3a96aefb5ed69c5a (3% recall), 0 failing
#  ledger row 42: outcome passed, 73.27s, rc 0, "11 passed in 72.88s"
#  the tier's OWN record now retires the red — `1 failing` -> `0 failing`.
```

The guard's falsification, in full:

```
$ cat > harness/tests/_probe_dup_round445.py <<'EOF'
def _copy(src, generate):
    return [m for m in generate(src, "whence/interp.py")
            if m.op == "arith" and '"concat"' in src.splitlines()[m.lineno - 1]]
EOF
$ .venv/bin/python3 -m pytest -q harness/tests/test_whence_anchor.py -k reimplements
E  AssertionError: ... Inline copies found: {'_probe_dup_round445.py': [4]}
1 failed in 0.37s
$ rm harness/tests/_probe_dup_round445.py && .venv/bin/python3 -m pytest -q harness/tests/test_whence_anchor.py -k reimplements
1 passed in 0.36s
```

## 10. What this round did not do

- **Did not change the driver.** See §6 — `slowtier-slice OK` on a red slice is
  documented, intentional, and its summary carried `1 failing`.
- **Did not repair `guardpin_fixture.py`.** §7, handed over measured.
- **Did not probe the upgraded skill.** `copied-mirror-drift` was UPGRADED
  rather than duplicated (authoring a new skill about duplication would have
  been the joke version of this round). Three new trigger cases
  `cmd-fix-near/mid/far` target the new symptom; the probe costs ~$0.05 and
  needs operator authorisation this round did not have, so it is registered in
  `state/known-unprobed-skills.json` as the fifteenth entry, with the specific
  risk named: `cmd-fix-mid` may be taken by `unrun-checker-latency` and
  `cmd-fix-far` by `unenforced-documented-rule`, in which case the
  DESCRIPTION needs narrowing, not the cases.
- **Did not claim the fast-tier guard placement is novel.** Round 413 got
  there first, for the same reason and in the same words:
  `guardpin_fixture.py`'s docstring says the fast file "has no `test_swe_`
  prefix, so `run_tests_fast.sh` runs the cheap rot detector EVERY round
  instead of once per rotation". I arrived at it independently and then found
  it already written down — which is itself an argument for the census in §7.

## 11. The skill upgrade broke the corpus check, in two places, from one cause

Worth recording because it is this round's own subject happening to this round.
The first run of `skills/run_checks_fast.sh` after the `copied-mirror-drift`
upgrade reported **2 errors** where round 444's driver line reports 0:

```
skill_lint   ERROR D002    skills/copied-mirror-drift/SKILL.md: description is 1311 chars (max 1024)
unit_tests   ERROR rc1     1 failed, 893 passed
             -> test_corpus_check.py::TestLiveCorpus::test_live_corpus_is_clean
                AssertionError: 1 != 0 : skills corpus has ERRORs: {'skill_lint': ['D002']}
```

Two reported errors, **one defect**: `test_live_corpus_is_clean` is a
downstream reader of `skill_lint`, so a single over-long description is
counted twice in the headline. Anyone triaging that line from the driver log
would start by looking for two problems. (Not filed as a defect — a
corpus-level test asserting the corpus is clean is *supposed* to restate the
checkers' verdict. It is worth knowing that the error COUNT in
`corpus-check: N error(s)` is not a count of distinct causes.)

Fixed by trimming the description to 1022 chars, keeping every new symptom.
Re-run:

```
skill-lint: 79 skill(s), 0 error(s), 3 warning(s)
unit_tests  ok   894 passed in 159.56s
corpus-check: 10 checker(s), 0 error(s), 7 warning(s)
```

0 errors / 7 warnings, identical to round 444's driver baseline.
`claim_check` reports `0 stale claim(s) of 217 checked`, which covers the five
commands added to the skill's Verification block.

**A carried claim NOT re-listed by this round, on purpose.** Round 435's
next-step 7 says the fast tier's V002 `test_no_unexplained_broken_invocation`
is red and that "`verb_audit` still reports `V002 1` on every corpus-check
line". This round's line reads `V002 0`. Round 444 had already deleted that
clause with evidence, and its own item 1 is a good essay on why it survived
five rounds anyway — so this is a confirmation, not a finding, and it belongs
here rather than in next steps.
