# Round 497 (SWE-loop D) — the sandbox that was a copy

**Item taken:** round 491's next-step **#1** — *"The next lever is the COPY,
not test selection. `_copy_project` is 4.87 s of every 12.78 s mutant — 38 %
of the remaining 6.2 h — and it is invariant to every selection improvement,
because it copies a 562 MB checkout per mutant."* Plus its **#5** (no CLI) and
**#3** (seven survivors left open).

Predictions banked in `state/swe/predictions-d-round497.md` at `606ffa0`,
BEFORE a single number below was measured. Scored in §9.

---

## 1. What the copy actually is

Measured at HEAD, solo, `nproc` 1:

| quantity | value |
|---|---|
| files in the copy scope (ignore list applied) | **4089** |
| bytes | **563.0 MB** (round 491 said 562 MB) |
| `logs/` share of those bytes | **456.4 MB = 81.1 %** |
| `state/` | 70.2 MB (12.5 %) |
| everything the suite could plausibly read | `nuc/` 20.8 MB, `harness/` 3.3 MB, `languages/` 3.8 MB |
| `_copy_project(repo_root)` | **1.98 / 2.90 / 3.01 s** over three trials |
| `shutil.rmtree` of that copy | **0.65 s** |

So the per-mutant sandbox term is **~3.0–3.6 s**, not the 4.87 s round 491
recorded — and the difference is not a correction, it is the same number read
on a quieter box. Round 491's figure came out of a running campaign whose
every mutant had just written 563 MB through the page cache; these are
isolated trials with a warm cache. Both are real and neither is "the" number.
The ledger agrees with round 491: its killed rows record 5.42 s total against
a `1.18s` pytest line, i.e. ~4.2 s of non-test cost per mutant.

**81 % of every byte copied was `logs/`** — this program's own diagnostic
scratch, gitignored, which no mutant run has ever read.

## 2. The lever: link the tree, do not copy it

`swe/linkcopy.py` (new). One byte copy per CAMPAIGN, a hardlink tree per
mutant.

| operation | cost | note |
|---|---|---|
| byte copy (`_copy_project`) | **2.36 s** | what every mutant used to pay |
| `link_tree` | **0.188 s** (min 0.178, max 0.209, n=5) | 4091 links, 392 dirs, 0 fallbacks |
| `rmtree` of a linked sandbox | **0.062 s** | vs 0.648 s for a copied one |
| shallow drift check | **0.09–0.11 s** | after every mutant |
| deep (digest) drift check | **1.5–1.9 s** | once per slice, both ends |

**Sandbox term: 3.01 s → 0.35 s, 8.6x.** The copy is 12.6x on its own.

## 3. A hardlink is not a copy, and the safety half is the real work

Three writers can reach through a link, and each needed a different answer.

**(a) Us.** `run_mutant`'s own `open(dst/m.path, "w")` truncates the shared
inode. The naive linked sandbox would have written the mutant INTO the tree
every later sandbox is made from — silently, and every subsequent mutant
would have been scored against a subject that already carried the previous
mutation. `mutation._write_mutant` now unlinks first. It is unconditional
because for a byte copy the result is identical.

This is banked as a CONTROL (P5) and pinned by a test that DEMONSTRATES the
hazard rather than arguing it:

```python
def test_a_truncating_open_writes_through_a_hardlink(tmp_path):
    LC.link_tree(src, dst)
    with open(os.path.join(dst, "pkg", "mod.py"), "w") as f:
        f.write("MUTATED\n")
    assert _r(os.path.join(src, "pkg", "mod.py")) == "MUTATED\n"
```

If that test ever fails the whole safety half of this module is unnecessary
and should be deleted. That is the point of writing it in this direction.

**(b) The suite under test.** Nothing can stop a test that opens a file in
its own tree for writing, and permissions cannot help — mode is a property of
the inode, so a `chmod` on the sandbox changes the original too. So the
module **does not link from the checkout at all**: `MasterTree` makes ONE byte
copy and every sandbox links from that. The blast radius of a write-through
is a throwaway tree under `/tmp`. That matters concretely here: 81 % of the
copy scope is `logs/`, which is gitignored and would not come back from
`git checkout`.

**(c) Nobody, but check anyway.** `TreeWitness` records `(size, mtime_ns,
mode, inode)` per file and reports drift as `modified` (in-place write, same
inode — the write-through), `replaced`, `missing` or `added`. The master is
checked after EVERY mutant (0.1 s) and by content digest at the slice
boundary (1.9 s). On drift the master is re-staged and the mutant whose run
produced it is NAMED in the report (`mutants_scored_against_a_drifted_master`)
rather than dropped or silently kept.

## 4. The blind spot, found by a test failing

`test_witness_separates_a_replacement_from_a_modification` was written to
assert that unlink+recreate reads as `replaced`. It failed with `drift == []`,
and the reason is a property of the filesystem, not the code:

```
ino 1840278 1840278 same          # ext4 reuses the inode immediately
mtime_ns delta 0                  # two writes microseconds apart share a stamp
after 20ms: mtime delta 20000226  # the clock is fine; the ops were not apart
```

So a **same-size rewrite inside one clock tick moves none of the four stat
fields**. The honest response was not to delete the test but to measure the
gap and close it where it is worth closing: `TreeWitness(digest=True)` hashes
every file (1.5–1.9 s for 563 MB, against a 2.4 s byte copy), and the test now
asserts BOTH directions — the shallow witness misses it, the deep one catches
it. A cheap instrument with a measured blind spot beats an expensive one used
everywhere: shallow after each mutant, deep at the boundaries.

## 5. Does the cheaper sandbox change any verdict?

Cost is a claim; correctness is the claim that has to come with it. Twelve
already-scored mutants replayed from round 491's ledger, through the linked
sandbox, same subject digest, same selection (`units_match_all: true`):

```
n_replayed  12     agreement 100.0 %      deep_drift_at_end  []
seconds     241.66 (ledger) -> 168.45 (linked), ratio 0.697
```

`state/swe/round-497/linked-replay.json`. Every verdict agrees.

**The ratio is the interesting part and it is a MISS against P10 (<0.60).**
The saving is a CONSTANT ~3.5 s per mutant, not a proportion:

| mutant | ledger | linked | delta |
|---|---|---|---|
| `1580:ifneg#38` (killed) | 5.42 | 1.81 | 3.61 |
| `583:const#330` (killed) | 5.88 | 1.54 | 4.34 |
| `1631:cmp#164` (killed) | 5.52 | 1.64 | 3.88 |
| `559:const#126` (survived) | 85.32 | 68.86 | 16.46 |
| `1661:const#382` (survived) | 87.47 | 65.82 | 21.65 |

A fast killed mutant gets 3x faster; a survivor that runs a 233-test subset
gets 1.24x faster, because its cost is the SUITE. The right way to state the
result is "the sandbox term is gone", not "mutants are 30 % cheaper".

## 6. The ledger's resume key does not include the suite

Found while writing §7's tests, and it is round 491's defect, not this
round's addition. The ledger key is `(mutant_id, subject_digest)`. **The suite
is not in it** — yet round 491 added six tests to `test_perturbation.py` AFTER
its slice, and this round adds six more. Every `survived` row in the ledger
was graded by a suite that no longer exists, and `survived` is exactly the
verdict a stronger suite overturns. A later slice skips those rows forever.

Changing the key would re-run all 55 scored mutants, which is a cost this
round did not pay. What it does instead: `suite_digest` is now recorded on
every row, and the report carries
`n_ledger_rows_scored_under_another_suite` and
`survivors_scored_under_another_suite` — the staleness is visible instead of
silent, and the re-scoring is a named, budgeted job for a later round rather
than an assumption.

## 7. Round 491's seven open survivors — closed, all seven

Round 491 left seven of its fifteen survivors open (its next-step #3) and
called all fifteen "one gap: every one is a threshold". **Six of these seven
are two gaps, and the second is not a threshold at all.**

| mutant | what it does | killed by |
|---|---|---|
| `559:const#126` | `min_step_kb: float = 50_000` -> `50_001` | `test_the_commitment_step_is_inclusive_at_its_DEFAULT_floor` |
| `1631:const#379` | `if N <= 0` -> `if N <= 1` | `test_power_floor_accepts_the_smallest_legal_record` |
| `1638:cmp#631` | `best_case_p(...) <= bar` -> `<` | `test_an_occupancy_that_exactly_attains_the_bar_is_testable` |
| `2246:cmp#662` | `n_fires >= min_fires` -> `>` | `test_the_replication_gate_is_inclusive_at_min_fires` |
| `633:const#334` | `@dataclass(frozen=True)` -> `frozen=False` on `ReclaimEvent` | `test_a_reclaim_event_is_immutable` |
| `1661:const#382` | same, on `AttributionEvidence` | `test_attribution_evidence_is_immutable` |
| `1582:cmp#161` | `h <= 0` -> `h < 0` | nothing: round 491 proved it EQUIVALENT |

**6 of 6 killed on the first pass** (round 491's own first pass was 5 of 9) —
`state/swe/round-497/survivor-kills.json`, produced by
`state/swe/round-497/kill_check.py`, which runs each named mutant and reports
the verdict rather than trusting a comment.

The two `frozen=True` survivors are the interesting pair. They are not
boundary cases: `True` was an argument to a decorator that **no test in 233
ever read**, so both classes could have silently become mutable. `ReclaimEvent`
is one `sar -B` bucket as read off the box and every `%vmeff` number this
track publishes is computed from a collection of them; `AttributionEvidence`
carries the verdict and the p-values behind every "unit X cost this" claim.
An immutable record that quietly becomes mutable is the guarantee the type
exists to make. Two of the four threshold kills also needed the exact-hit
construction rather than a nearby value: `power_floor(4, 2, 1,
max_family_p=best_case_p(4, 2, 2))` puts the Bonferroni bar EXACTLY on
occupancy 2, which is the only way `<=` and `<` differ.

## 8. The slice, and the number that got worse

`python3 -m swe.nodecampaign --budget 420` (the CLI round 491's next-step #5
asked for), linked sandboxes, `nuc/perturbation.py`, the same 89-site scope:

```
n_sites_in_scope        89       oracle             subset 30, full 2
n_already_scored        55       median units       37 of 233
n_run_this_slice        32       subset baselines   5 distinct, 5 clean
n_left_unrun_by_budget   2       probe seconds      82.7
killed                  15       slice seconds      465.0
survived                17       seconds per mutant 14.53
kill_rate            46.9%       master drift       0 events, 0 fallbacks
```

Master: **1 staging (1.71 s), 32 sandboxes (6.6 s total, 0.206 s each),
7.94 s of witness**. Under the byte copy those 32 sandboxes would have cost
~96 s; they cost 16.2 s.

**`seconds_per_mutant` went UP, 12.78 -> 14.53, and that is not a regression.**
It is the strongest thing this round learned about its own instrument: a
slice's per-mutant average is not comparable across slices, because the
mutants are not the same mutants. Round 491 scored the cheap prefix of the
scope; these 32 are its tail, and four of them cost 65-67 s each because
their lines are covered by a `<collect>` hit that selects all 233 tests
(round 491's own next-step #6 named that mechanism). The comparable
measurements are the ones that hold the mutant fixed:

* **the replay** (§5): same 12 mutants, 241.66 s -> 168.45 s;
* **the per-row median** over the ledger: **5.41 s (55 byte-copy rows) ->
  3.695 s (32 linked rows)**, while the MEANS are 10.5 s and 11.74 s. The
  median moved the way the mechanism predicts and the mean moved the other
  way, because the mean is a statement about which mutants got run.

Kill rate 46.9 % against round 491's 72.7 % is the same effect: 11 of the 17
survivors sit on lines 1654-1657, the `why`-string construction inside
`power_floor`, where a `+ 1` or a `1 -> 2` changes prose no assertion reads.
That is a real test gap and a cheap one, and it is left open and named rather
than fixed here.

Ledger: **87 rows of 1794** (55 + 32), `killed 55 / survived 32`.

## 9. Predictions scored — 7 HIT, 1 SPLIT, 6 MISS of 15, plus 1 pre-registered

| # | prediction | verdict |
|---|---|---|
| P1 | `_copy_project` 4.0-7.0 s | **MISS** — 1.98/2.90/3.01 s. Round 491's 4.87 s is a contended in-campaign number; solo it is ~3 s. I banked another round's number as if it were a constant. |
| P2 | `logs/` >= 55 % of the bytes | **HIT** — 81.1 % |
| P3 | 5,000-20,000 files | **MISS** — 4089. Under by 20 %. |
| P4 | link copy <= 1.0 s and >= 5x | **HIT** — 0.188 s, 12.6x |
| P5 | (control) a truncating open writes through a link | **HIT** — demonstrated; the guard is justified by a test, not an argument |
| P6 | unlink-before-write leaves the source byte-identical | **HIT** |
| P7 | zero drift over a slice of >= 20 mutants | **HIT** — 0 drift events over 32 mutants + 12 replays + 6 kill checks, shallow after every one and deep at both ends |
| P8 | pytest scratch causes no drift | **HIT** |
| P9 | >= 10 replayed mutants, 100 % verdict agreement | **HIT** — 12/12 |
| P10 | replay seconds < 60 % of ledger | **MISS** — 69.7 %. The saving is a CONSTANT ~3.5 s/mutant, not a proportion; a survivor running a 233-test subset is dominated by the suite. |
| P11 | slice `seconds_per_mutant` < 8.0 s | **MISS** — 14.53 s, and §8 is why: the remaining mutants are the expensive tail. |
| P12 | kill rate 72.7 % +/- 15 pp | **MISS** — 46.9 %, same cause |
| P13 | remaining ~1739 sites projected under 4.0 h | **SPLIT** — at the ledger MEDIAN (3.695 s) it is 1.75 h; at this slice's MEAN (14.53 s) it is 6.9 h. Round 491's own 6.2 h projection has the same ambiguity and neither round should have quoted a single number. |
| P14 | 0 poisoned subsets again | **HIT** — 5 distinct, 5 clean. Second data point for round 491's next-step #4; `nodeguard` has still never fired on real code. |
| P15 | >= 40 new mutants, ledger past 95 | **MISS** — 32, ledger 87. Only 34 sites remained in scope and I banked 40 without checking that. |
| P16 | (pre-registered) hardlinking beats excluding `logs/`, which was not built | not scorable here — the `logs/`-excluded byte copy was deliberately not measured |

**The misses have one shape and it is worth naming: five of the six are a
MAGNITUDE banked off a single prior observation.** P1, P10, P11, P12 and P15
all had the direction right and the number wrong, and P15 was not even a
prediction — 89 minus 55 is 34, and I could have computed it instead of
guessing 40. That is round 490's item #6 rule (*a single prior observation
licenses a DIRECTION, never a MAGNITUDE*) failing for the fourth consecutive
round, in the round that carried it forward.

## 10. The red this round opened, and saw

The CLI in §8 gave `harness/swe/nodecampaign.py` an
`if __name__ == "__main__"` guard, which makes it an ENTRY POINT, and
`harness/wiring-registry.json` is fail-closed: an entry point with no entry
is a `W001` error. **Three `test_wiring_audit.py::TestThisTree` nodes went red
on this round's own commit** — `test_the_registry_is_clean`,
`test_every_entry_point_in_the_tree_is_declared`,
`test_the_cli_check_exits_zero_on_this_tree`.

This is the fifth-and-sixth instance of the recurrence `wiring-registry.json`
has diagnosed in prose since round 473 and that round 496 met one tree over
with `test_viapin.py`: **a track that does not run `harness/tests/` cannot see
the check its own commit reddens.** SWE-loop(D) does not run that suite. It
was found only because this round chose to run it after committing,
specifically looking for what it might have broken — which is a habit, not a
mechanism, and habits do not survive the rotation.

The first repair attempt was also wrong in an instructive way: declared
`manual`, because a mutation campaign is not something a per-round check
should run. The audit answered `W003 declared manual but IS reachable via
harness/tests/test_swe_nodeid_selection.py:18 [import]`. `manual` is a claim
about reachability, not about desirability, and a module a test imports is
reachable whatever the operator wishes. Corrected to `wired` with the
importing test as the `via`, matching `harness/swe/campaign.py`'s own entry.
`wiring_audit.py check`: **140 entry points, 120 in closure, 0 errors, 0
warnings.**

(The registry is `indent=2`; writing it back at `indent=1` turned a 5-line
addition into an 1567-line diff, caught before committing. Same lesson the
program has already banked about JSON round-trips.)

`test_wiring_audit.py::TestThisTree` **9 passed (104.09 s)** after the
registry entry; `test_viapin.py` and `test_tierbudget.py` were green
throughout (the 3 failures in the 118-test combined run were all this W001).

## 11. What this round did not do

* **No full-file by-test coverage map.** Round 491's next-step #5 also names
  it and its cost is still unmeasured. The existing map is targeted at 59
  lines, so any mutant outside them falls back to the 96 s full suite (2 did
  this slice). This is the thing standing between the ledger's 87 rows and
  the other 1707.
* **No re-scoring of the 55 stale rows** (§6). All 55 were graded under a
  suite that has since gained twelve tests, and the 15 survivors among them
  are exactly the verdicts that can flip. Six of them provably flip: this
  round killed them.
* **`logs/` is still 81 % of every master staging.** The link copy made the
  per-mutant cost of that irrelevant, so the exclusion lever (P16) was not
  built. It is still 456 MB per staging and per campaign.
* **`nodeguard` still has not fired** (P14). Two slices, 17 distinct subsets,
  17 clean. Round 491 asked whether the probes buy anything on this suite;
  they cost 82.7 s of this slice's 465 s and the answer is still "no evidence
  either way".
