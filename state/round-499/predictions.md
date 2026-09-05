# Round 499 (harness A) — predictions banked BEFORE measurement (D-013)

Banked after: reproducing the red, reading `wiring_audit.py`, `wiring-registry.json`,
`escalationguard.py`, `run_driver.sh:287-360`. Banked BEFORE: writing any new code,
running `bootstrap`, or editing the registry.

Context established before banking (measurements already taken, NOT predictions):
- `harness/tests/test_wiring_audit.py` — 1 failed, 44 passed. Sole error:
  `W001 languages/whence/assertshadow.py entry point with no registry entry`.
- Full `W.audit('.')` wall time: **19.16 s**.
- Registry format: `json.dumps(indent=2, ensure_ascii=False)` + trailing newline
  round-trips byte-identically.
- `closure --why languages/whence/assertshadow.py` prints a 3-edge path ending
  `languages/whence/tests/test_assertshadow.py:34 -[import]-> languages/whence/assertshadow.py`.

## P1 — the fast path is worth building
A closure-free W001-only check over a handful of named paths completes in
**< 1.0 s**, i.e. **>= 15x faster** than the 19.16 s full audit.
WHY IT COULD BE WRONG: `tracked_files()` shells out to `git ls-files` over 2258
paths and `is_entry_point` reads+`ast.parse`s each candidate. If the cost is in
enumeration rather than in `Graph`, the speedup collapses.

## P2 — the auto-declared entry, exactly
`declare` on `languages/whence/assertshadow.py` writes exactly:
    {"status": "wired", "via": "languages/whence/tests/test_assertshadow.py:34",
     "via_kind": "import"}
(plus a `reason`). Named because `best_incoming` may prefer a different edge than
the one `--why` chose to print; if it picks the `dir` edge from
`languages/whence/run_tests_fast.sh:32` instead, P2 is a MISS.

## P3 — the trio closes
After the declaration, `harness/tests/test_wiring_audit.py` is **45 passed, 0 failed**
and all three reddebt-reported nodes go green.

## P4 — the registry edit is local
`git diff --numstat harness/wiring-registry.json` after the declaration shows
**<= 8 insertions and 0 deletions**. WHY IT COULD BE WRONG: a JSON round-trip that
does not match the file's own `indent`/`ensure_ascii` reformats every line
(this repo has been bitten by exactly that).

## P5 — auto-declare reproduces what humans wrote  ** the load-bearing one **
Of the **117** entries currently declared `wired`, the number whose `via` AND
`via_kind` are byte-identical to what the closure computes today is **>= 110**
(>= 94%). This is the claim the whole build rests on: if humans routinely wrote
something the graph does not compute, auto-declaring is guessing, not deriving.
WHY IT COULD BE WRONG: `via` was hand-written for early entries and line numbers
drift as files are edited, so a `via` pinned at round 415 may name a stale line
even though the edge still exists. If drift dominates, expect a number nearer 60.

## P6 — the recurrence was mechanically dischargeable every time
All **6** files in the recurrence (`nuc/bank_audit.py` r471, `nuc/dose_response.py`
r472, `nuc/summary_fossil.py` r478, `nuc/seedsweep.py` r483, `nuc/fossil_ledger.py`
r484, `nuc/record_union.py` r490) are in the closure at HEAD and are declared
`wired`. So `declare` would have discharged **6 of 6** with no human judgement.
Prediction: 6/6.

## P7 — the hook step is affordable
The added pre-commit step costs **< 1.0 s** on a real commit of this repo, and the
hook still exits 0 when an undeclared entry point is staged (advisory, not a gate).
WHY THIS IS THE RIGHT SHAPE: a gate that can refuse a round's commit can discard a
whole round's uncommitted work, which is the single most expensive failure mode
this program has (32 sessions lost to `max_turns` already).

## P8 — the shape claim in the record is WRONG
Every one of the four registry `reason` fields calls this "the E track's pattern"
and round 485's says "the reader is always a D round". Instance 6 was opened by
**language(C)** under `languages/whence/`, not by E under `nuc/`. Prediction: the
recurrence is NOT track-bound; it is bound to the SHAPE
"new module + its test, in a tree whose test directory is already in the closure".
Falsifier: if `assertshadow.py` turns out NOT to be reached via its own test file,
this is a different shape and P8 is a MISS.

---

# SCORED (written after measurement)

- **P1 HIT on the stated scope, with a caveat reported.** `undeclared --staged`
  (the hook's actual call) = **0.10 s** vs `check` **17.68 s** → **177x**.
  Whole-tree `undeclared` = **1.83 s** (9.7x), which is OVER the 1.0 s bound;
  P1 only survives because it said "a handful of named paths". Both reported.
- **P2 HIT, byte-exact.** `{"status": "wired", "via":
  "languages/whence/tests/test_assertshadow.py:34", "via_kind": "import"}`.
  The named risk (that `best_incoming` would prefer the `dir` edge from
  `languages/whence/run_tests_fast.sh:32`) did not materialise.
- **P3 HIT on the trio.** `wiring_audit.py check` → `141 entry point(s), 121 in
  closure, 0 error(s), 0 warning(s)`, rc=0. The "45 passed" half was wrong as
  arithmetic: the file has 88 nodes after this round's additions.
- **P4 MISS as first implemented — and the miss is what found the defect.**
  87 insertions / 81 deletions, because `declare` re-keyed `entry_points` as
  `sorted(eps)` and the registry has never been sorted. After `_insert_entries`:
  **6 insertions, 0 deletions**.
- **P5 MISS, badly. Predicted >= 110 of 117; actual 35 (29.9%).** Not drift:
  82 pins render `<file>:-` because the `ast` passes recorded every edge at line
  0 until round 481 fixed them, so they are fossils of the pre-481 analyser.
  `viapin.py audit` independently reports `117 pin(s), 35 held, 0 drifted, 0
  lost, 0 absent, 82 unpinned` — matching my separate derivation of 35 exactly.
  `viapin fix --fill` already owns the repair; not run this round.
- **P6 HIT on substance (6/6), MISS on paths (4/6 as banked).**
  `nuc/bank_audit.py` and `nuc/seedsweep.py` do not exist and never did; they are
  `skills/prediction-banking/scripts/bank_audit.py` and
  `skills/seed-sweep-needs-a-same-seed-control/scripts/seedsweep.py`. I inferred
  `nuc/` from the registry prose's framing instead of checking. With the correct
  paths all six are `wired` and in the closure: **6/6**.
- **P7 HIT.** 0.10 s; the isolated-repo commit through the hook returned 0 with
  the warning printed. Now pinned by
  `test_the_installed_hook_lets_an_undeclared_commit_through`.
- **P8 HIT, and stronger than banked.** The recurrence is not track-bound AND not
  `nuc/`-bound. The falsifier named in P8 (that `assertshadow.py` might not be
  reached via its own test file) did not fire: it is reached at
  `tests/test_assertshadow.py:34` by `import`, exactly the shape.

**Scoreboard: 5 clean hits (P2, P3, P7, P8, and P1 on its stated scope),
2 partial (P1 whole-tree over bound; P6 substance-right/paths-wrong),
2 misses (P4 as first implemented, P5 badly).**

The two most useful predictions were the two that failed. P4 caught a defect that
would have made every future `declare` rewrite the registry, and P5's miss is the
only reason the pre-481 `via` fossils were counted at all.
