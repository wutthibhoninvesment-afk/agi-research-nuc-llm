# Round 505 (harness A) — a read set cannot name the file you just added

**Track:** harness(A). **Predictions:** `state/harness/round-505/PREDICTIONS.md`,
banked after reproducing the reds and before a line of the new module existed.

## 0. What this round was handed, and what it did with it

`harness/reddebt.py` (round 493) put four red nodes in this round's prompt
with their opener, their owner, and the instruction *reproduce it before
fixing it*. All four were opened by round 504 (language C) and all four live
in the harness suite, which a language round does not run.

That instruction is the first thing this round did, and it earned its place:
two of the four turned out to be two different defects wearing one label.

```
$ .venv/bin/python -m pytest harness/tests/test_swe_copyparity_real_subject.py \
      harness/tests/test_whenceslow.py::test_the_real_tree_yields_the_units_round_469_measured \
      -p no:randomly -q
4 failed, 9 passed in 10.86s
```

Solo, no contention, deterministic. Not the runner. The two causes:

* **`languages/whence/builtinlive.py:124`** (new in round 504) assigns
  `os.path.join(os.path.dirname(os.path.dirname(ROOT)), 'state', 'whence',
  'builtin-liveness.json')` at import time — an unguarded repo-root escape.
  Under a mutation sandbox that is `/tmp/state/whence/...`. Three copyparity
  nodes.
* **`languages/whence/tests/test_builtinlive.py`** (new in round 504) carries
  three `@pytest.mark.whence_slow` tests, taking the whence slow tier
  29 → 30 units and 115 → 118 marked nodes. One `test_whenceslow.py` pin.

Both fixed (§1). The rest of the round is about the fact that **round 504
could not have seen either one at any price**, and what to build about that.

## 1. The two fixes

### 1.1 The escape (P8 — CONFIRMED)

The sanctioned form is round 413's, and round 467 already applied it to the
last unguarded site in this tree (`specreg.py:179`), closing *these same
three nodes* after they had been red for rounds 464-466. Round 504 wrote a
new file with the pre-413 spelling and reopened them.

```python
AGI_ROOT = (os.environ.get("AGI_RESEARCH_ROOT")
            or os.path.dirname(os.path.dirname(ROOT)))
LEDGER = os.path.join(AGI_ROOT, "state", "whence", "builtin-liveness.json")
```

Outside a `harness/swe/proc.py` subprocess the env var is unset and this is
byte-for-byte the path the old expression produced, so nothing about a plain
`pytest languages/whence/tests` changes. All three nodes green, no other
edit — P8 as predicted.

### 1.2 The pin (fourth re-pin of the same assertion)

`test_the_real_tree_yields_the_units_round_469_measured` is now 30 units /
118 marked with `test_builtinlive.py` at 3. Its docstring already recorded
this happening three times (474 and 482 as openers, 475 and 485 as readers);
this is the fourth, and the first where the reader was **told** instead of
stumbling on it. Latency one round instead of three — which is exactly what
`reddebt` was built to do and all it can do.

## 2. The finding: `reddebt` cannot reach the opener, and nothing else does

`redattrib` measured the quantity — **83% of red episodes were opened by a
round that could not have seen the red by running its own track's suite.**
`reddebt` acts on it from the READER's side, one round later, because the
four health checks run after the round's process exits and write to `logs/`,
which is not in git.

Nobody has ever asked the opener-side question, and it is answerable:

> Given the diff in my working tree right now, which test nodes — in any
> suite, including ones my track never runs — can it redden?

`harness/crosstrack-registry.json` is one step from being able to answer it.
It already classifies red nodes by `subject_scope`, and its `foreign-subject`
value is literally this shape ("the track that can break it is by
construction not the track that runs it", added round 467 for the copyparity
file). But the subject is recorded in **prose**: the entry says the node's
subject is `languages/whence/tests/`; it does not say which paths, so no
query can run against it. That is the round 473-493 recurrence in another
key — a diagnosis written down and never turned into an instrument.

## 3. `harness/readset.py` — the subject set, measured

A PEP 578 audit hook (`sys.addaudithook`) records, per pytest node, two sets
of repo-relative paths:

| set | audit events | question it answers |
|---|---|---|
| `files` | `open` (read modes only), `import` | which node depends on a file that **exists** |
| `scans` | `os.listdir`, `os.scandir` (so `os.walk`, `glob`) | which node would have read a file that **does not exist yet** |

**The second set is the whole design.** Round 504's redden was an ADDITION.
`languages/whence/builtinlive.py` had never been read by anything when any
read set was recorded, so no read set can name it, and a files-only
instrument reports round 504's diff as touching nothing. The directory
`scan_escapes` walked is the only recorded evidence that some node would have
read the new file. Additions are also the majority shape in this program —
every round writes new files.

`harness/tests/test_readset.py::test_an_added_file_is_implicated_by_the_scan_
set_alone` is that claim as a falsifier, and
`test_a_new_file_in_the_whence_tree_implicates_the_copyparity_node` asks it
of the real map with a filename that does not exist, which is the only way to
test the half a read set cannot express.

### Design decisions that came out of measurement, not thought

* **A write is not a read.** Branch on the open mode. Count writes and every
  node that touches `logs/` becomes a reader of it, and every diff under
  `logs/` implicates everything.
* **A pseudo-path is not a path.** CPython's `SyntaxError` handler literally
  calls `open("<unknown>", "rb")`. It is *relative*, so `abspath` places it
  INSIDE the repo, and the first map this round recorded carried `<unknown>`
  as a file no diff could ever name — found on
  `test_marked_tests_is_none_for_an_unparsable_file_and_the_unit_errors`,
  whose entire job is to parse a broken file. Anything with `<` or `>` is
  dropped.
* **A scan set can name a directory the node never listed.** CPython's import
  `FileFinder` re-`scandir`s a `sys.path` directory whose mtime moved, so
  writing a `__pycache__` entry under `tests/` during one test puts `tests`
  in the *next* test's scan set. Over-approximating direction; pinning it
  empty would pin pytest's import cache, so the test says so instead of
  asserting it away.
* **Report at FILE granularity.** P1, confirmed: `test_swe_copyparity_real_
  subject.py` builds its subject in a MODULE-scoped fixture, so all of its
  reads land on whichever node pytest ran first and its siblings record
  almost nothing. The union over a file is a superset (fail-closed) and
  "run this file" is an instruction a reader can act on.
* **The hook is inert unless armed.** `sys.addaudithook` cannot be removed.
  It is installed at import only when `READSET_OUT` is set, so importing the
  module as a library — which the query path and every test does — costs
  nothing. `test_the_audit_hook_is_not_installed_without_the_env_var`.
* **Diagnostic, never a gate.** `blast` exits 0 on findings; `--strict` is
  opt-in and `run_driver.sh` does not use it. A check must never be able to
  stop the round that would fix it (round 493's rule), and a test asserts the
  driver does not.

## 4. Measurements

FILL-MEASUREMENTS

## 5. Prediction scoring

FILL-SCORING

## 6. The second latency, one layer down (P9 — refined, not confirmed)

P9 predicted that adding `harness/readset.py` without a
`harness/wiring-registry.json` entry would redden W001 and the three
`test_wiring_audit.py` nodes. It does — **but only after `git add`.**

```
$ python3 harness/wiring_audit.py undeclared     # readset.py present, untracked
wiring-audit: no undeclared entry point in the whole tree
$ git add -N harness/readset.py
$ python3 harness/wiring_audit.py undeclared
W001  harness/readset.py: entry point with no registry entry
```

`wiring_audit.tracked_files` reads `git ls-files` on purpose (an `os.walk`
would pick up `__pycache__` and vendored trees). The consequence nobody had
written down: **the commit-time check is blind before the commit.** A round
that builds an entry point and asks the fail-closed registry whether it is
declared gets "all clean" until it stages the file — which is the same
latency class this round is about, one layer down, and it is why four rounds
in a row (473/479/485/490) shipped an undeclared entry point while a check
that would have caught it sat in the tree.

The entry was then written by the tool itself
(`wiring_audit.py declare harness/readset.py --write`, second round ever to
do that after 493) and annotated by hand with the measurement above.

## 7. The stale headline (P7 — CONFIRMED)

`reddebt.note()`'s head paragraph — the first thing every round has read
since 493 — hardcoded:

> "The wiring-audit trio below is the fifth instance of a recurrence
> `harness/wiring-registry.json` has diagnosed in prose four times since
> round 473..."

True on the day it was written. Round 505 received it above a list of three
`test_swe_copyparity_real_subject.py` nodes and one `test_whenceslow.py`
node — no wiring audit anywhere in the list, and not an instance of that
recurrence. Twelve rounds (493-504) were handed a headline about the wrong
red. No test asserted anything about the head sentence's agreement with the
rows below it, exactly as predicted.

That is the module's own defect one level up: a finding written into prose
instead of computed, which then rots while reading exactly as authoritative
as it did the day it was true. The head now derives its count, its suite-file
list and its opener/owner clause from `items`, and three falsifiers hold it
open — including one that requires two different red sets to produce two
different heads, which no hardcoded sentence can pass.

## 8. Carried claims re-derived (two of two moved)

* **`verb_audit` V002 is 0 at HEAD, not 1.** `state/research-state.md` has
  carried "V002 1 on every corpus-check line, including this round's" since
  round 433 (item 7 of the 435 block, restating 433). `python3
  harness/verb_audit.py check` at HEAD: `32 finding(s) (V001 8, V002 0,
  V003 24)`. The carried claim is refuted; whatever closed it is not
  recorded, which is its own small finding about carrying numbers instead of
  commands.
* **The whence slow tier is 30 units / 118 marked**, not the 29/115 three
  next-steps blocks and one test docstring assert. Moved by round 504.

## 9. What is now true, and what is not

TRUE, tested:

* The four reds round 504 opened are closed, by cause, not by relaxation.
* `harness/readset.py` records and queries a measured subject set, and its
  real-subject pins reproduce round 504's redden from a filename that does
  not exist.
* `reddebt`'s headline is derived from its rows and points the reader at the
  opener-side instrument.

NOT true, and stated so nobody quotes it:

* This does not make the map self-maintaining. It is recorded against a HEAD
  and goes stale the moment anything lands; `blast` says so, and nothing
  re-records it automatically. **A round that adds a test node and does not
  re-record has a map that cannot see its own node.** That is the first thing
  a follow-up round should fix, and the honest options are a driver-side
  re-record (costs a full instrumented fast tier per round) or an
  incremental one (record only the files the diff touched).
* It does not cover the whence, nuc or skills suites. The map is the harness
  fast tier only. The other three checks have the same structure and no map.
* It does not see dependence through `os.stat`, and it does not see a
  subprocess's reads.
