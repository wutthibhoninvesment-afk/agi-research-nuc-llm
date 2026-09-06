# Round 520 (NUC-integration E) — the number that had no verb

**Date:** 2026-09-06 · **Track:** E (NUC integration) · **Box:** DOWN.

Two tailnet ssh probes, `2026-09-06T02:00:36Z` (`ConnectTimeout 25`) and
`02:01:14Z` (`ConnectTimeout 30`), both rc 255 `Connection timed out`;
CLAUDE.md's two-SSH-failures rule fired after the second and no further box
contact was attempted. ICMP to `100.78.44.111`: 2 packets, 100% loss. LAN path
NOT tried — `~/.ssh/id_ed25519_nuc` still does not exist on this host
(re-verified: `No such file or directory`), so a third probe would be theatre.
`tailscale status --json` banked at
`state/nuc-capture-r520/tailscale-status-r520.json`: `Online false`,
`LastSeen 2026-09-04T02:14:05.1Z`, relay `sin`, tx 2184 rx 0.

That `LastSeen` is **byte-identical to rounds 490, 496, 502 and 508**, so this
is the SAME continuous outage — ~47.8 h at first probe — and the **sixth**
consecutive down E-window (490, 496, 502, 508, 514, 520).

**Zero ssh sessions succeeded. Port 8001 was never contacted. No engine
request of any kind was made. No mission ticked: E1–E5 are all `[x]` and the
two open NUC items (the E3 KV-reuse A/B, the OLMoE on-box NVMe decode
measurement) both need a restart on a shared box and operator sign-off.**

---

## 1. The assignment: round 514's own §8, item 1

> **The other 82 remapped mutants are not re-scored at HEAD.** … until those
> 82 are scored the new report's survivor set is a lower bound.

**Population re-derived from the ledger, not from the report.** Round 514's
headline was that a prediction's DENOMINATOR is a carried claim, and it missed
six of nine predictions by taking "32 standing survivors" from a report that
had been wrong about it for twelve rounds. So:

```sh
python3 -c "
import json, collections
rows=[json.loads(l) for l in open('state/swe/perturbation-mutation-ledger.jsonl')]
OLD='8082749f713ee07f05e1f9187324280156c547673e35fa39017ef67200173ea1'
lw={}
for r in rows: lw[(r['id'], r['subject_digest'])]=r
print(collections.Counter(lw[k]['status'] for k in lw if k[1]==OLD))"
# -> Counter({'killed': 82, 'survived': 5})      87 distinct ids
```

**82**, confirmed against `mutant-remap-all87.json`'s 87 pairs, of which 81
`moved` and 6 `matched`. The 82 new-digest ids were derived from the pairs
whose OLD id last-wins to `killed`, and 0 of them already had a HEAD row.

## 2. The measurement

```sh
.venv/bin/python -m harness.swe.nodecampaign --root . --lines all \
    --budget 1500 --timeout 180 \
    --only "$(cat state/nuc/round-520/rescore-82.ids)" \
    --out state/nuc/round-520/rescore-82.json
```

| field | value |
|---|---|
| `n_selected` / `n_run_this_slice` / `n_left_unrun_by_budget` | 82 / 82 / **0** |
| `by_status` | `{"killed": 82}` |
| `kill_rate` | **100.0** |
| `seconds` / `seconds_per_mutant` | **213.6** / 2.61 |
| `oracle` | `{"subset": 82, "full": 0}` |
| `median_units_selected` | 43.0 (old digest: 39) |
| `map_is_stale` | false |
| `mutants_scored_against_a_drifted_master` | `[]` (82 sandboxes, 0 drift events) |

**All 82 kills hold at HEAD. Not one verdict moved.** Round 514's five
survivors were not a lower bound after all — they are the whole set. That is
the null result the round was asked for, and it is now measured rather than
assumed.

## 3. THE FINDING: a published number with no verb that reaches it

The slice report carries, and has carried since round 497:

```
n_ledger_rows_scored_under_another_suite   55
survivors_scored_under_another_suite       []
```

Fifty-five ledger rows whose grading suite no longer exists — and the list of
the ones anything can do about is **empty**. `harness/swe/nodecampaign.py`:

```python
stale = [r for r in done.values()
         if r.get("suite_digest") not in (suite, None) or "suite_digest" not in r]
stale_survivors = sorted(r["id"] for r in stale if r.get("status") == "survived")
```

`--stale`, the only verb that can pay that number down, selects
`stale_survivors`. On this subject the split is:

| stale rows by status | count | reachable by `--stale`? |
|---|---|---|
| `killed` | **55** | no |
| `survived` | 0 | yes (vacuously) |

by suite digest: **40 rows carry no `suite_digest` at all** (they predate round
497, which introduced the field) and **15 were graded by `2cd94b15`**, the
round-497 suite. Only 27 of the 82 kills were produced by the live suite
`7ac31f49`. So 55 of 87 verdicts in this ledger were, until this round, claims
no suite in the tree had ever made — and the report printed the count next to
an empty repair list without saying they were the same rows.

### 3a. The premise under the restriction, checked rather than assumed

Round 502's comment justifies the survivor-only rule: "a SURVIVED verdict is
exactly the one a stronger suite overturns." True **if the suite only grows**.
Nothing enforces that. Checked, on this subject's own history:

```sh
for c in $(git log --format=%H -- nuc/tests/test_perturbation.py); do
  git show $c:nuc/tests/test_perturbation.py | sha256sum; done
```

| suite digest | commit | round | test nodeids | removed vs previous |
|---|---|---|---|---|
| `0d950d27` | `036cbb3` | 491 | 239 | — |
| `2cd94b15` | `3895e48` | 497 | 245 | **0** |
| `7ac31f49` | `6ee44a7` | 502 | 257 | **0** |
| HEAD | — | — | 257 (identical set) | 0 |

The premise **holds** on this history, monotonically, three digests deep. It is
still a premise: one `git rm` of a test turns every kill it produced into a
claim nothing supports, and no test in the tree said so. §2's 82/82 is the
independent confirmation, at a subject digest 243 lines newer.

### 3b. And the verb could not have reached them anyway

A ledger row is keyed `(id, subject_digest)`. Round 514's finding was that ids
MOVE: 81 of 87 changed when round 508 edited the subject. So a stale row from
an older digest names a mutant that is not a mutant of this subject at all, and
no widening of the *status* filter makes it selectable. That is a second,
independent limit on the same number, and the report never distinguished them.

### The fix

`harness/swe/nodecampaign.py`:

* `rep["stale_by_status"]` — the published count, split by the status the
  repair verb keys on. `{"killed": 55}` here is the whole finding in one field.
* `rep["kills_scored_under_another_suite"]` — the ids, so a round can act.
* `rep["n_stale_rows_selectable_at_this_digest"]` — how many of the stale rows
  any `stale_scope` could reach *in principle*, i.e. which of the two limits is
  biting.
* `STALE_SCOPES = ("survivors", "kills", "all")` and
  `--stale-scope {survivors,kills,all}`; `--stale` is unchanged shorthand for
  `survivors` and `stale_survivors_only=True` still means exactly what it meant
  (a negative-control test pins this, and it is the one new test that passes
  against the PRE-fix module).

## 4. Second defect, found by a prediction that missed

P3 predicted `verdict_changes == []`. It came back with **82 entries**, every
one `{"was": null, "now": "killed"}`. `verdict_changes` compared each result
against `done.get((id, digest))` and called an **absent** row a change — and
`--only` is precisely how a round scores ids for the first time. A field whose
docstring calls it "the number the round quotes … how wrong the old figure was"
reported **82 of 82 corrections on a slice where 0 verdicts moved**.

Narrowed to rows with a prior verdict at this digest; first scorings counted
separately as `n_first_scored_at_this_digest`, because dropping them silently
would hide that the slice was almost entirely new work.

## 5. Third defect: the row that signed round 454's name

Round 514 left `state/nuc-reachability-log.jsonl` a row short —
`coverage --strict` reported `missing: [514]`. `reachability_recover.py` reads
the round's own `logs/round-<N>.json` transcript, and round 514's carries four
ssh probes with the deciding one at `2026-09-05T19:05:32Z`. It recovered
cleanly. The row it produced said:

> Recovered by round **454** from this round's own transcript
> logs/round-514.json, **which round 310's prose backfill never read.**

Both clauses were a fixed string. Round 520 wrote the row, not round 454; and
round 310's backfill could not have read a transcript written 204 rounds after
it ran. The attribution read as provenance and was a template.

Worse, it was **self-blocking**: `rewrite_plan` re-derives every recovered row
to check the log still agrees with its transcripts, and it re-derived under the
same constant — so the first row written by any other round showed up as a
`notes` change and made `rewrite` refuse the whole batch.
`nuc/tests/test_reachability_recover.py::test_the_live_log_is_currently_in_sync_with_its_transcripts`
went red the moment the row landed.

Fixed: `DEFAULT_RECOVER_ROUND = 454` (so all seven existing rows re-derive
byte-identically), `BACKFILL_HORIZON_ROUND = 448` (the round-310 clause is a
fact about round 454's own bracket and is dropped above it), a `--by-round`
flag, and — the part that makes it reproducible — the row now carries
`recovered_by_round`, which `rewrite_plan` reads back so each row re-derives
under **its own** author. `rewrite --apply` added the field to the seven
round-454 rows (add-only, `safe: true`, 0 blocking changes).

## 6. The reachability log at HEAD

```
rows 71 (69 -> 70 recovered r514 -> 71 live r520)
coverage --strict                        0   n_owed 61, n_covered 61, missing []
coverage --strict --no-allow-in-flight   0
precision-audit --strict                 0
lastseen-drift --strict                  1   (documented, pre-existing)
status: verdict down, streak start 2026-09-04T11:00:11Z (round 490),
        elapsed 39h14m53s confirmed / 47h51m upper, exceeds the longest
        completed same-verdict streak by 2h13m
```

`missing: []` for the first time in this log's recorded history of the
in-flight population.

## 7. Predictions scored — 8 HIT, 3 MISS of 11

Banked at `nuc/predictions-e-round520.md`, commit `1041141`, **before** the
slice ran and before any test in this round was executed (D-013).

| | claim | outcome |
|---|---|---|
| P1 | 82 run, 0 left unrun, budget 1500 s | **HIT** — 82 / 82 / 0 |
| P2 | >= 78 of 82 killed at HEAD | **HIT** — 82 |
| P3 | 0 flip to `survived`; `verdict_changes == []` | **PARTIAL** — 0 flipped, but the field returned 82 entries. §4 |
| P4 | wall clock 350–800 s | **MISS** — 213.6 s, below the range |
| P5 | `oracle == {subset: 82, full: 0}` | **HIT** |
| P6 | report still `n_survivors_standing == 5`, `moves_published_number == []` | **HIT** — §9, byte-equal in every measured field |
| P7 | stale count stays exactly 55 | **HIT** — 55 |
| P8 | 0 nodeids removed across the suite digests | **HIT** — 239 → 245 → 257, 0 removed |
| P9 | `missing: [514]` persists after row 520 is appended | **MISS** — §5 |
| P10 | the new guards fail against HEAD before the fix | **HIT** — 8 failed, 1 passed (the negative control), then 34 passed after |
| P11 | `median_units_selected` != 39 | **HIT** — 43.0 |

**The three misses are worth more than the eight hits.**

* **P4 (213.6 s vs 350–800 s).** I built the range from the old digest's 310 s
  of *mutant* time and added overhead. The 310 s was measured on a run whose
  per-mutant cost included round 491's byte-copy sandboxes; round 497 put the
  campaign on hardlinks and this slice paid **0.17 s per sandbox**. I carried a
  duration across an optimisation that the ledger itself records. Same class of
  error as round 514's: a number re-derived from the artefact, but from an
  artefact produced under a configuration that no longer exists. **Re-deriving
  a number is not enough; re-derive the conditions it was measured under.**
* **P9.** I predicted an ABSENCE — "round 514's hole needs its own backfill,
  which appending 520 does not touch" — because I had read `backfill --help`,
  seen `--tailscale-json` was required, and knew round 514 banked no capture.
  I never ran `reachability_recover.py show --round 514`. It needed no capture:
  it reads the round's own transcript, which had been on disk since 19:36 the
  previous evening. **Grep before predicting an absence** — the tool that
  refutes you may be in the same directory.
* **P3.** Scored honestly as a partial rather than a hit: the substantive half
  (0 killed→survived) was right, the literal half was wrong, and the literal
  half is what found §4's defect. A prediction that is wrong about the
  instrument is more useful than one that is right about the subject.

## 8. What this round did NOT do

* **The box was not reached.** Sixth consecutive down E-window. No mission
  ticked; nothing on the NUC was read, written or restarted.
* **The full blast radius was not run.** `python3 harness/readset.py blast`
  named ~30 suites for this diff, including `harness/tests/test_wiring_audit.py`
  (266 s alone at round 514) and `harness/tests/test_tiering.py`. Run this
  round: `harness/tests/test_swe_nodeid_selection.py` (34),
  `nuc/tests/test_reachability_recover.py` (47),
  `nuc/tests/test_reachability_check.py` (258),
  `nuc/tests/test_survivor_impact.py` + `nuc/tests/test_mutant_remap.py` (52).
  The rest is named here rather than silently skipped.
* **The three carried reds** (`test_redattrib.py` ×2, `test_viapin.py`) were
  not touched. Two are DERIVED from
  `harness/tests/test_tiering.py::test_the_slow_tier_is_exactly_the_unpromoted_swe_files`,
  owner harness(A), and the debt line says not to look for a defect in the
  host. The third is owned by harness(A) and opened by skills(B).
* **`--stale-scope kills` was not RUN on this subject.** It cannot help here:
  §3b — every one of the 55 stale rows names an id that no longer exists at
  this digest, which `n_stale_rows_selectable_at_this_digest` now reports. The
  flag exists for the next subject whose ids did not move.

## 9. The report at HEAD, and what the 82 bought

```sh
.venv/bin/python nuc/survivor_impact.py --strict --quiet \
    --out state/nuc/round-520/survivor-impact.json     # exit 0, no STRICT: line
```

| field | round 514 | round 520 |
|---|---|---|
| `subject_digest` | `3b3923df…` | `3b3923df…` |
| `n_survivors_standing` | 5 | **5** |
| `n_survivors_at_another_digest` | 5 | 5 |
| `n_lines_executed_by_battery` | 1319 | 1319 |
| `by_verdict` | `{reached_but_identical: 3, unreached_by_battery: 2}` | identical |
| `by_reason` | `{branch_not_taken: 2}` | identical |
| `moves_published_number` | `[]` | `[]` |
| `battery` (7 verbs) / `results` | — | **byte-equal** |

**The report did not move.** That is the point: round 514 published it with an
explicit caveat that its survivor set was a lower bound because 82 verdicts
behind it had never been checked at this digest. Those 82 are now checked and
the number is the same. The caveat is discharged, not restated.

`nuc/tests/test_survivor_impact.py` resolves `REPORT` to the NEWEST
`state/nuc/round-*/survivor-impact.json` (round 514's un-pinning), so all
three of round 514's gates now grade round 520's report:

```
.venv/bin/python -m pytest nuc/tests/test_survivor_impact.py \
    nuc/tests/test_mutant_remap.py -q      -> 52 passed in 0.29s
```

## 10. Commands, for re-derivation

```sh
# the population — from the ledger, not from any report
python3 -c "import json, collections; \
rows=[json.loads(l) for l in open('state/swe/perturbation-mutation-ledger.jsonl')]; \
lw={}; [lw.__setitem__((r['id'],r['subject_digest']),r) for r in rows]; \
print(collections.Counter(lw[k]['status'] for k in lw \
  if k[1]=='8082749f713ee07f05e1f9187324280156c547673e35fa39017ef67200173ea1'))"
#   -> Counter({'killed': 82, 'survived': 5})

# the slice (213.6 s)
.venv/bin/python -m harness.swe.nodecampaign --root . --lines all \
    --budget 1500 --timeout 180 \
    --only "$(cat state/nuc/round-520/rescore-82.ids)" \
    --out state/nuc/round-520/rescore-82.json

# the stale split the report now carries
python3 -c "import json; d=json.load(open('state/nuc/round-520/rescore-82.json')); \
print(d['n_ledger_rows_scored_under_another_suite'], d['survivors_scored_under_another_suite'])"
#   -> 55 []        (the finding, in one line, at the OLD report shape)

# the monotone-suite premise (P8)
for c in $(git log --format=%H -- nuc/tests/test_perturbation.py); do \
    git show $c:nuc/tests/test_perturbation.py | sha256sum | cut -c1-8; done

# the guards, against the PRE-fix module (P10)
cp harness/swe/nodecampaign.py /tmp/fixed.py
git show HEAD:harness/swe/nodecampaign.py > harness/swe/nodecampaign.py
.venv/bin/python -m pytest harness/tests/test_swe_nodeid_selection.py -q \
    -k "stale_count or stale_scope or MOVED or FIRST_scoring or real_verdict_change"
#   -> 8 failed, 1 passed        (the 1 is the negative control)
cp /tmp/fixed.py harness/swe/nodecampaign.py

# the suites, with the fix in
.venv/bin/python -m pytest harness/tests/test_swe_nodeid_selection.py -q   # 34 passed, 53.61s
.venv/bin/python -m pytest nuc/tests/test_reachability_recover.py -q       # 47 passed, 1.30s
.venv/bin/python -m pytest nuc/tests/test_reachability_check.py -q         # 258 passed, 1.39s
.venv/bin/python -m pytest nuc/tests/test_survivor_impact.py \
    nuc/tests/test_mutant_remap.py -q                                      # 52 passed, 0.29s

# the reachability gates
python3 nuc/reachability_check.py coverage --strict                        # 0, missing []
python3 nuc/reachability_check.py coverage --strict --no-allow-in-flight   # 0
python3 nuc/reachability_check.py precision-audit --strict                 # 0
python3 nuc/reachability_check.py lastseen-drift --strict                  # 1, documented
python3 nuc/reachability_recover.py rewrite                                # n_changes 0
```

## 11. The rule this round earns

**A number a report publishes needs a verb that can reach the rows it counts,
and the report has to say when there isn't one.**
`n_ledger_rows_scored_under_another_suite: 55` sat beside
`survivors_scored_under_another_suite: []` for eighteen rounds. Both fields
were true. Read together they say "fifty-five problems, none of them
actionable" — and nothing in the report said those were the *same* rows, or
which of the two independent limits (`status` filter, moved id) was doing it.
The fix is not a bigger verb; `--stale-scope kills` still selects 0 here. The
fix is that the report now states the shortfall as a field
(`stale_by_status`, `n_stale_rows_selectable_at_this_digest`) instead of
leaving it to be inferred from two numbers that never appeared in the same
sentence.

Same shape as §4's `verdict_changes` (a count whose population was wider than
its name) and §5's `Recovered by round 454` (a provenance string that was a
constant). Three instruments, one round, one failure mode: **the artefact
described itself from a template rather than from what it had actually done.**
