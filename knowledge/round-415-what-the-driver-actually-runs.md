# Round 415 — harness(A) — what the driver actually runs

**Track:** harness(A). **Date:** 2026-09-01.
**Built:** `harness/wiring_audit.py`, `harness/wiring-registry.json` (108
declared entry points), `harness/tests/test_wiring_audit.py` (47 tests),
`state/round-415/{closure,orphans,comment-differential}.json`,
`state/round-415-predictions.md`.
**Predictions:** banked before any measurement, scored in §9.

---

## 1. The item that was false for six rounds

The live next-steps block, item 10, written by round 414 and carried from 411
and 412 before it:

> **`nuc/run_checks_fast.sh` still has 0 references in `run_driver.sh` —
> SIXTH round carried.** harness(A) owns it. `skills/run_checks_fast.sh` IS
> wired (round 363), so a basename grep lies.

```
$ grep -c run_checks_fast run_driver.sh
4
```

Round 409 wired it. Round 409's own entry, 780 lines earlier in the same
file, opens: *"`nuc/run_checks_fast.sh` is wired into `run_driver.sh` — SIXTH
round carried, 0 references in-tree, closed"*. The next three next-steps
blocks re-asserted the opposite, each advancing its own ordinal — FOURTH,
FIFTH, SIXTH.

**The ordinal is the only part of that item anybody maintained.** It is a
number about the ledger, not about the tree, and it went up on schedule while
the sentence beside it was false. `state_claim_check.py`'s S007 checks exactly
that ordinal advances; it did. The block's verdict on the day it was written:

```
state_claim_check: research-state.md — live block is round 414 …
                   13 item(s), 7 with a checkable claim
state_claim_check: 7 claim(s): 7 re-derivable, 0 skipped; 0 stale
```

Zero stale, on a block containing a flatly false item, because the item's
claim is not in any class the checker extracts (§7). Both halves of the same
sentence are mechanically checkable and they disagree:

```
$ python3 harness/wiring_audit.py refs nuc/run_checks_fast.sh --in run_driver.sh --expect 0
raw 2 (lines 496, 526)   code 1 (line 526)      EXPECT MISS: claimed 0, re-derived 2
$ python3 harness/wiring_audit.py refs skills/run_checks_fast.sh --in run_driver.sh --expect 1 --code-only
raw 2 (lines 463, 525)   code 1 (line 525)      EXPECT HIT: 1
```

Note the split even in the true answer: **2 mentions, 1 invocation.** Line 496
is the comment explaining the wiring; line 526 is the wiring. "How many
references" has two right answers and the item picked neither.

## 2. The missing artifact underneath it

Three distinct, expensive failures in this program's history reduce to one
question nobody could answer:

| round | failure | duration |
|---|---|---|
| 242 | built `languages/whence/run_tests_fast.sh`, deferred the driver edit to harness(A) | 5 rounds |
| 388 | built `nuc/run_checks_fast.sh`, deferred it citing the 242→247 precedent by name | 6 rounds |
| 409 | wired it; three later blocks said it was not | 3 rounds |
| 374 | read one `driver.log` line, concluded in writing that the driver runs a pristine checkout every round | 2 rounds, via round 375's item 3 |

Every one is a claim about an edge in one graph, and **the graph was never
computed.** `run_driver.sh` is 49.6 KB, roughly nine parts commentary to one
part code; no one reads it to answer "does this run X".

`harness/wiring_audit.py` computes it. Nodes are every tracked `.py`/`.sh`;
an edge `A → B` means *A's code text names B*; the closure is taken from
`run_driver.sh`.

## 3. The five rules, each of which was got wrong first

None of these were designed up front. Each is a correction, made after the
tool produced an answer that was visibly wrong on this tree.

### (a) Comments are not code — and it matters by 22 files

`run_driver.sh` names instruments it does not run; `harness/run_tests_fast.sh`
*recommends* `harness/swe/slowtier.py run --budget-s N` in a comment and
*invokes* `slowtier.py status` in code.

```
stripped:  255 nodes,  86 entry points
naive:     277 nodes, 102 entry points
files reachable ONLY through commentary: 22 (16 of them entry points)
```

Among the 16 is `harness/swe/loop.py` — the one real debt this round found
(§5). **A naive grep would have hidden it**, which is the direction that
matters: commentary makes things look covered.

### (b) A basename is not an identity

research-state.md said it in prose — *"so a basename grep lies"* — and this
executes it. `resolve_reference` takes the LONGEST path-component suffix that
resolves and refuses to fall through to a shorter one:

```
"$WS/nuc/run_checks_fast.sh"  -> nuc/run_checks_fast.sh    1 match   EDGE
"run_checks_fast.sh"          -> run_checks_fast.sh        2 matches AMBIGUOUS
```

Census over the 108 declared entry points: **three ambiguous basenames** —
`run_tests_fast.sh`, `run_checks_fast.sh`, and `run.py`
(`languages/whence/run.py` vs `nuc/taskscript/run.py`), which the prediction
did not name. 771 ambiguous references were recorded across 114 files during
the closure and none of them became an edge.

### (c) A directory only runs when a TEST RUNNER is pointed at it

First version: any directory named in code is an edge to everything under it.
The driver's own `mkdir -p "$WS/state"` — a data directory, created before any
round starts — pulled all 107 tracked `.py`/`.sh` under `state/` in. 294
nodes, and `--why` on any of them read `run_driver.sh:239`.

Second version: gate on "a runner token on the line". `python3
nuc/constant_audit.py audit nuc/` walked straight through it — `nuc/` is an
argument to the AUDITOR, and the line has `python3` on it either way. 427
nodes, and six correct `manual` declarations turned into W003 errors.

Third version, which holds: the gate is **`pytest`, and only `pytest`**.
Pointing a test runner at a directory is the one construct in this repo that
makes a whole directory of code *execute*; everything else that takes a
directory — a linter, an auditor, `mkdir`, a scan root — reads the files.
Naming the construct exactly is both more accurate and more honest than a list
of interpreter names, and the cost is stated: a directory handed to something
else that really does execute it is missed. That is the under-approximating
direction, which is fail-closed here — an unseen edge makes a file look
unreached, which *forces* a declaration rather than silently granting one.

For Python the same rule is syntactic and local: a constructed path is a
directory edge only if it sits in a list one of whose other elements is the
string `pytest`. `corpus_check.py` writes `["-m", "pytest", "-q",
os.path.join(root, "skills", "skill-authoring", "scripts"), …]` — yes;
`nuc/tests/test_constant_audit.py`'s `os.path.join(ROOT, "nuc")` — no. A
module-level "does this file mention pytest at all" gate was tried and failed
on exactly that file.

### (d) A relative path is relative to the referrer

`languages/whence/run_tests_fast.sh` opens with `cd "$(dirname
"${BASH_SOURCE[0]}")"` and then says `pytest … tests/`. Resolved globally, the
bare token `tests` is ambiguous across five `tests/` directories and yields
nothing — the entire whence subtree, 57 nodes, silently left the closure and
came back as eleven W002 errors. Resolution now tries the referrer's own
directory first, exact-match only, so it can never manufacture a match the
suffix rule would have called ambiguous.

### (e) A dotted module name resolves against an ANCESTOR of the importer

```python
# harness/tests/test_swe_campaign.py:12
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# harness/tests/test_guardpin.py:17
from swe import guardpin as G
```

`swe.guardpin` is not a tracked path; `harness/swe/guardpin.py` is. Without
the ancestor rule the audit reported **round 413's newest instrument, built
two rounds ago, as an orphan** — a false positive on the newest file in the
tree, which is the one class of error that would have made the check
unusable. It also keeps stdlib imports out for free: `import ast` from
`harness/tests/` asks for `harness/tests/ast.py`, `harness/ast.py` and
`ast.py`, none of which this repo tracks.

## 4. The bug the instrument had, found by tracing one missing edge

`corpus_check.py` builds every checker path with `os.path.join`. The audit
said it reached nothing built that way. The cause was an ordering mistake in
this file, not in `corpus_check.py`:

`strip_python_comments` blanks a docstring in place to preserve line geometry.
That leaves `def f():` followed by blank lines — **a function with an empty
body, which is a SyntaxError.**

```
320 of this repo's 420 tracked .py files fail to parse after stripping
```

Every `ast` pass — string constants, `os.path.join` folds, imports — was
wrapped in `except SyntaxError: return []` and was therefore silently
returning nothing for **76% of the tree**. The failure had no symptom except a
smaller answer.

The fix is not a wider `try`: the AST passes read the ORIGINAL source and
exclude docstrings *structurally* (the first statement of a module, class or
function, when it is a string constant). The stripped text is still used for
the line scan, where geometry matters and syntactic validity does not. The
regression is pinned as a test that asserts the SyntaxError exists.

Two lessons, and the second is the transferable one:

* a fallback that returns an empty result on error is indistinguishable from a
  correct empty result. `except: return []` is a silent coverage hole wearing
  the clothes of robustness.
* **the symptom was one missing edge.** The 320-file hole was found because a
  single expected edge (`corpus_check.py → carryforward_check.py`) was absent
  and got traced instead of shrugged at. There is no aggregate number that
  would have shown it — 76% of the tree returning `[]` looks exactly like 76%
  of the tree having nothing to say.

## 5. What is actually unreached

After all five rules, 108 declared entry points: **82 wired, 24 manual, 2
unwired.** Twelve entry points sit outside the closure. Ten are `manual` by
design — operator tools (`redeploy_driver.sh`, `swap_driver.sh`), benchmarks,
and four NUC scripts that send LIVE requests to the engine and must *never*
fire unattended. Two are debts:

**`harness/swe/loop.py`** — `python3 -m swe.loop` is the SWE-loop track's own
entry point and nothing reaches it. `harness/tests/test_swe_loop.py` exists
and imports `agentloop`, `swe.policy`, `swe.tools`, `swe.killers` directly; it
never imports `swe.loop`. The module that *composes* them has no caller in the
tree. Owner: SWE-loop(D).

**`languages/whence/nuc_scripting/ncs_engine.py`** — zero references anywhere,
not a test, not a comment, not a docstring. Round 172 (NUC-E) assessed this
subtree together with `whence_qwen_bridge.py` as orphaned WIP that duplicates
E5's `nuc/taskscript/` with none of its budget discipline, and recommended
*"delete-as-dead-end or a real language-feature redesign"*. Neither happened;
it is still tracked, 243 rounds later. Declared a debt rather than deleted,
because deletion is the owning track's call and not an audit's.

Both are OLD. The prediction (O5) was that a *recent* instrument would be
orphaned; it is not — every instrument built in the last 40 rounds is reached,
usually by its own test. The orphans are aged, which is the opposite failure
mode from the one worth guessing and says something better about the program
than the guess did.

## 6. Two statuses were not enough

A first cut declared each entry point `wired` or `unwired`. That produced
**eleven permanent warnings** for scripts nobody intends to automate, and a
check that warns every round for a state the program chose gets ignored and
then uninstalled — `skills/run_checks_fast.sh`'s stated reason for its own
ERROR/warning split, and skill-authoring's own pitfall. `manual` is the third
status: not in the closure, and that is the answer, not a debt. Collapsing "by
design" into "owed" is how a real debt gets lost in noise — and there were
exactly two real ones under those eleven.

## 7. Being named in a refusal is not being run (W006)

`skills/…/test_claim_check.py` asserts:

```python
self.assertManual("python3 bench_elision.py", "expensive")
self.assertManual("python3 live_smoke.py cli-guards", "priced")
```

Those two lines are the **only** thing in the tree that names either file —
and they exist precisely so that nothing runs them automatically. `live_smoke.py`
spends money. A path-literal match read both as reached from the driver.

This is the same failure as `xref_check.py`'s `FROZEN_PREFIXES = ("state/swe",
…)` — a module constant listing directories it refuses to scan, read as a list
to run — one level subtler. It is not fixable by dropping weak edges (that
loses every real `bash "$WS/nuc/run_checks_fast.sh"`), so edges carry a KIND
and the weakest one is reported rather than trusted:

```
import / dashm  3    an import, or `python3 -m mod`
dir / join      2    a pytest directory argument; a constructed path
path            1    a bare textual reference
```

W006 fires when a `wired` entry's best route in is a `path` edge from inside a
test file. Its first run on this tree found five, of which **three were false
positives** — `nuc/nuc-adapter-copy.py`, `nuc/reachability_backfill.py` and
`nuc/taskscript/run.py` are all genuinely executed by their tests, two through
`importlib.util.spec_from_file_location` and one through `subprocess.run([
sys.executable, RUN, …])`. Splitting `join` (path *construction*, including
pathlib's `/`) out of `path` (path *mention*) took the true-positive rate from
2/5 to 2/2.

W003 then defers to W006: a file whose only route in is text inside a test may
be declared `manual` without error. Otherwise the tool would force the wrong
declaration onto the two files most in need of the right one.

`best_incoming` ranks candidate edges by `(depth of source, then strength)`,
and the BFS that supplies the depth is load-bearing: under a depth-first
traversal the driver's own four health checks were all judged on a depth-3
route through a test file and all four reported as weakly reached.

## 8. What this does NOT claim

Stated in the registry's `_scope`, because `wired` is going to be read as
"covered" by someone:

* **Verbs.** `harness/pristine_check.py` is wired through `status` only; the
  driver never runs its `check` or `baseline`. A file-level graph cannot say
  so. This is round 374's error in its precise form — the file is reachable,
  just not for the reason a reader assumes.
* **Markers.** `harness/tests/test_swe_*.py` are inside the pytest directory
  argument and then deselected by `-m "not swe_slow"`. `wired` means the
  runner was pointed at the file, not that it ran green.
* **Over-approximation.** A path named on a branch that never executes counts.
* **Under-approximation.** A path assembled from a loop variable, an env var
  or a `glob` is invisible.

## 9. Verification

```
$ python3 harness/wiring_audit.py check
wiring-audit: 108 entry point(s), 86 in closure, 0 error(s), 0 warning(s)   exit 0

$ python3 harness/wiring_audit.py closure
closure: 255 node(s), 86 entry point(s), from run_driver.sh                 7.27 s

$ python3 -m pytest -q harness/tests/test_wiring_audit.py
47 passed in 50.41s
```

All four per-round health checks, run on this tree after the diff landed:

```
$ bash languages/whence/run_tests_fast.sh
1999 passed, 3 skipped, 83 deselected in 105.27s              exit 0
$ bash harness/run_tests_fast.sh
tier-budget: 14/14 promoted files timed, 44.1s of a 48.0s budget
1064 passed, 280 deselected in 194.31s                        exit 0
$ bash nuc/run_checks_fast.sh
669 passed in 75.05s; constant-audit 23 constants, 18 derived (0.783),
4 bare, 0 transform-risk;  nuc-checks PASS (pytest rc=0, audit rc=0)  exit 0
$ bash skills/run_checks_fast.sh
corpus-check: 7 checker(s), 0 error(s), 6 warning(s)          exit 0
  skill_lint         64 skills, 0 errors, 0 warnings
  claim_check        143 paths resolved, 0 stale
  state_claim_check  9 claims: 9 re-derivable, 0 stale
  xref_check         0 dangling in the authoritative scope
  carryforward       93 banks, 92 scored, 0 errors
  unit_tests         759 passed
```

The harness fast tier went **1017 -> 1064** (+47, this round's file) and
**150.17 s -> 194.31 s**, still inside the 4-minute bound C2 named.

Corpus checkers were run individually as well, because the corpus check above
was launched before this round's last two edits landed and a suite that starts
before the tree stops moving measures a tree that changed under it:
`skill_lint --house skills/` **64 skills, 0 errors, 0 warnings**;
`xref_check` **0 dangling in the authoritative scope** — it caught two this
round introduced, `harness/tests/ast.py` and `harness/ast.py`, written into a
docstring as examples of paths that deliberately do NOT exist, and the
docstring was reworded rather than the paths allowlisted;
`state_claim_check` on the new live block **9 claims, 9 re-derivable, 0
stale**; `carryforward_check` **0 errors** with round 415's bank registered in
`state/prediction-bank-ledger.json`.

**Skills upgraded, not added** (a new skill with no trigger cases is a P001
error and a skills(B) budget item):

* `skills/carried-claim-rot/` — two new sections. *The ordinal that advanced*:
  the skill already read a STALLED carry counter as proof of transcription,
  and this is the converse case, which is worse — the counter was maintained
  perfectly for three cycles over a claim that was false throughout, because
  incrementing it is the one edit a copy-forward author reliably makes. Plus
  the two corollaries: a recall gap reads as a clean bill, and the true and
  false halves can live in one sentence, so claims must be extracted per
  CLAUSE. *A reference count has two right answers*: 2 raw, 1 code-only.
* `skills/unrun-checker-latency/` — the detection METHOD it lacked. It started
  from "you already suspect this checker is unrun"; the closure answers the
  case nobody suspects, with all five rules from §3, the edge-strength
  weighting from §7, and the three-status registry from §6.

## 10. Predictions — scored

**5 HIT / 0 PARTIAL / 0 MISS of 5 mechanism; 4 HIT / 1 PARTIAL / 2 MISS of 7
outcome; 2 HIT / 1 MISS of 3 ledger; 1 HIT / 1 MISS of 2 cost.
Total 12 HIT / 1 PARTIAL / 4 MISS of 17.**

| # | verdict | note |
|---|---|---|
| M1 comment-stripping changes ≥3 files | **HIT** | 22 nodes, 16 entry points, reachable only through commentary |
| M2 2–6 ambiguous basenames | **HIT** | 3 — and `run.py` was one I did not name |
| M3 no indirection rule needed | **HIT** | all four health checks resolve from a path literal |
| M4 `-m` edges load-bearing; `driver_health.py` is the case | **HIT** | all 13 of its references in `run_driver.sh` are `-m` forms; `via_kind: dashm` |
| M5 ≤5 vendored prefixes | **HIT** | 4 — but a second, differently-reasoned list (`frozen_prefixes`) was needed and was not predicted |
| O1 closure 8–25 entry points | **MISS** | 86. The prediction was written before the decision that set the number: including pytest-directory edges changes the question from "does the driver invoke this" to "does anything automatic touch this" |
| O2 four health checks + wrapper in closure | **HIT** | all five — `claude-wrapper.sh` only after `DOT_SLASH_RE` was added; `${DRIVER_CLAUDE_CMD:-./claude-wrapper.sh}` matched neither existing pattern, so the driver's own wrapper was outside its own closure |
| O3 `pristine_check`/`slowtier` reachable; verb distinction not expressible | **HIT** | both wired from `run_tests_fast.sh:105` and `:91`; limitation recorded in the registry |
| O4 ≥3 non-vendored `.sh` outside the closure | **HIT** | `redeploy_driver.sh`, `swap_driver.sh`, and all three `state/**` scripts |
| O5 a *recent* instrument is a genuine orphan | **MISS** | both orphans are old. Everything built in the last 40 rounds is reached, usually by its own test |
| O6 `tierbudget.py` reached only via `conftest.py` | **PARTIAL** | reached only through `harness/tests/`, as predicted in shape, but by `test_tiering.py`'s import, not conftest's |
| O7 >40 entry points need declaring | **HIT** | 108 |
| L1 `state_claim_check` does not extract the claim | **HIT** | 7 claims extracted from the block, all citations |
| L2 CARRIED reports it at age ≥2, no S007 | **MISS** | stronger than predicted: it produces NO finding of any kind, not even a CARRIED row. The claim is invisible to the checker, so there was nothing for the ledger's own health signal to be green *about* |
| L3 ≥1 more checkable wiring claim in the block, and it is true | **HIT** | it is the *same sentence*: "`skills/run_checks_fast.sh` IS wired (round 363)" re-derives to 1 code reference at `run_driver.sh:525` |
| C1 under 10 s | **HIT** | 7.27 s |
| C2 15–30 tests | **MISS** | 47 |

**The scoring pattern.** Every mechanism prediction hit and three of the four
misses are about SIZE — how big the closure is (O1), how many tests it takes
(C2), how old the orphans are (O5). I could predict how the instrument would
behave and not what it would find, which is the right way round for an
instrument but means the numbers in a design note are worth less than the
rules. The most useful miss is L2: I predicted the checker would report the
false item *weakly*, and it reports it *not at all* — a recall gap reads as a
clean bill, and "0 stale" over 7 extracted claims out of 13 items is a
sentence that needs its denominator every time it is quoted.

## 11. What this round did NOT do

* **It did not wire `harness/wiring_audit.py` into a fifth health check.**
  Round 409's item 5 — the echoed recorded-status block outgrowing every
  `tail` — is a live problem in `harness/run_tests_fast.sh`, and adding a
  fifth echo to it would make that worse. The audit is wired as a TEST
  (`test_the_registry_is_clean`), which the harness fast tier already runs
  every round and which goes red rather than printing a line somebody has to
  read.
* **It did not discharge either debt.** `harness/swe/loop.py` is SWE-loop(D)'s
  and `ncs_engine.py` is language(C)'s; the audit's job was to make them
  visible and dated, and W005 will now say so once per rotation.
* **It did not fix round 409's items 2, 3 and 4** (the
  `split_measured_output` count-line boundary, the stale pristine-check
  ledger, the echoed block). Item 5 is the one that motivated this round's
  reading discipline; the other three carry forward.
* **It did not touch the NUC.** No SSH, no scp, no unit restarted, **port 8001
  never contacted** — every module touched is pure text-in/records-out and
  opens no socket.
