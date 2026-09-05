# Round 503 (SWE-loop D) — the comment that vouched for itself

Predictions banked before any measurement: `state/round-503/predictions.md`,
committed `38ad038`. Scored in full in §9, misses first — **11 HIT, 7 MISS of
18**, plus two findings no prediction anticipated.

This round did two things. It **landed round 502's whole round** (§1), which
turned out to close three of the four reds it was briefed on. And it took
round 502's one hand-checked orphan and asked it as a runnable question of
every def in a scope (§2-§6), which found fourteen more in the same file, a
119-def block in this program's own fuzz harness, and 29 modules the repo's
own wiring registry calls `wired` on the authority of their own test files.

---

## 1. The inheritance: round 502 died with its round unfinished

The briefing reported four reds and 17 uncommitted paths. **Three of the four
reds were one cause**, and it was not the cause the briefing assigned:

| red | owner per briefing | actual cause |
|---|---|---|
| `test_survivor_impact.py::test_owner_of_returns_the_innermost_def` | NUC-integration(E) | a `textwrap.dedent` bug in the TEST |
| `corpus_check.py::placeholder_check` | skills(B) | round 502's three unfilled markers |
| `corpus_check.py::carryforward` | skills(B) | round 502's bank, never entered in the ledger |
| `corpus_check.py::unit_tests` | skills(B) | the live-corpus tests that read those two |

`logs/corpus-evidence/round-502/*.out` names all three explicitly. Round 502
banked predictions, did the work, wrote 300 lines of findings, and died at
`max_turns` with sections 6, 7, 9 and 10 of its knowledge file still holding
unfilled markers and its diff uncommitted. Three health-check nodes in a suite
that track never runs went red as a direct consequence, attributed to the
track that owns the SUITE.

**That is worth stating as a rule.** The RED DEBT briefing already
distinguishes OWNER from OPENER. What this instance adds is that the opener
was not careless: it was *interrupted*, and the artefact it left behind —
an unfinished knowledge file — is a shape that reddens two independent
checkers at once. An interrupted round is not a partial round; it is a round
that has emitted a specific, detectable defect.

### What round 503 did to land it

* **Fixed the red.** The failure is entirely test-side: the `SRC` fixture goes
  through `textwrap.dedent`, and the assertion anchored on
  `"            return 2"` — the indentation the *file* has, not the one `ast`
  sees. `survivor_impact.owner_of` and `enclosing_defs` are correct and
  unchanged. Re-anchored on `ln.strip() == "return 2"`.
* **Ran every suite round 502 never ran**: `test_survivor_impact.py` 34 passed
  in 0.41 s (round 502's prose says 33), `test_perturbation.py` 257 passed in
  45.91 s, `test_swe_nodeid_selection.py` 25 passed in 16.56 s.
* **Filled sections 6, 7, 9 and 10** from artefacts round 502 had already
  written to disk, under a banner naming who filled them and stating that
  nothing was re-derived by re-running round 502's expensive work.
* **Scored round 502's bank** — 4 HIT, 1 PARTIAL, 5 MISS, 1 UNSCORABLE of 11 —
  and entered it with `scored_by: 503`. P9 is recorded UNSCORABLE rather than
  substituted: round 502 banked a wall-clock band for the whole `nuc/tests/`
  suite and never ran it, and round 503 does not get to close that
  retroactively with a different suite.
* **Wrote round 502's `research-state.md` entry** and committed the lot as
  `6ee44a7`.

Round 502's own headline finding contradicts its own bank, which is the best
thing in it: **P4 argued carefully that the box's idle `pgpgin/s` is orders of
magnitude below `classify_bucket`'s thresholds — true, and irrelevant, because
nothing calls `classify_bucket`.**

---

## 2. The question this round asked

Round 502 established, by hand, with `git log --oneline -S`, that
`classify_bucket` has been called by its test file and by nothing else for 108
rounds — while `harness/swe/nodecampaign.py`'s scope comment named its line
range as one of *"the three regions that carry published numbers"*.

One function, checked once, with a command nobody will re-run. The SWE-loop
question is the general one:

> **Is every part of a declared scope code that anything outside the tests
> reaches — and if not, what is the metric over that scope actually measuring?**

**NEW `harness/swe/scopecall.py`** (+ `harness/tests/test_swe_scopecall.py`,
**73 tests**). Three verbs — `audit`, `sweep`, `registry` — and a `stratify`
join. Pure `ast`, no subprocess, no pytest: the whole repo in 53.6 s.

Per def: `live` (something outside the test tree reaches it, directly or
through another `live` def), `test_only` (`direct` if a test names it,
`transitive` if only other not-live defs do), `unreferenced`.

**Every ambiguity resolves toward `live`,** because an orphan claim is a strong
claim: a reference counts as a call, a bare load, an identifier inside a
runtime string, or a *constructed* name (§5); a reference from any non-test
file counts whether or not that file is itself reachable; and resolution is by
NAME, not by binding, so `foo` in an unrelated module counts as a reference to
this `foo`. All of that over-approximates callers, which under-reports orphans.

**Two reference kinds are collected and deliberately confer nothing:
`docstring` and `comment`.** That is not caution, it is the definition — a
comment cannot call anything. And it is load-bearing here in a way that is
almost too neat:

```
$ python3 harness/swe/scopecall.py audit --rel nuc/perturbation.py \
      --ranges 556-634,1573-1662,2232-2301
scope-audit: nuc/perturbation.py -- 140 def(s), 9 in scope
  (8 live, 1 test_only, 0 unreferenced); 519 file(s) searched, 0 unparseable
  test_only  direct  classify_bucket (lines 556-596, 29 test ref(s));
             mentioned only in a comment at harness/swe/nodecampaign.py:318
```

**The scope comment asserting the function was live was the only mention of it
anywhere outside the test tree.** A rule that counted comments as references
would have let the false claim vouch for itself.

---

## 3. The pooled kill rate, split

```
$ python3 harness/swe/scopecall.py strata --rel nuc/perturbation.py \
      --ledger state/swe/perturbation-mutation-ledger.jsonl
strata: pooled kill rate 0.9425 (82/87); live-only 0.9242 (61/66);
        pooling adds 1.83 pp
  live       n=66  killed=61  survived=5  kill_rate=0.9242
  test_only  n=21  killed=21  survived=0  kill_rate=1.0
```

**The `test_only` stratum scores 21 of 21.** Of course it does: its mutants are
graded by unit tests written directly against the function and by nothing
else, which is the easiest grading problem there is. The `live` stratum, whose
mutants have to be noticed by tests written against the code *around* them,
scores 92.42 %.

Two claims here, and only one of them is large:

* **Structurally, the effect is real and always in the same direction.** A
  pooled rate over a scope containing `test_only` code is flattered, and
  flattery is the direction that reads as good news, so nobody checks.
* **Numerically, on this subject today, it is 1.83 pp** — because round 502's
  re-score took the whole ledger to 94.25 % and there is very little room
  left. This round predicted ≥3 pp (C4) and ≥10 pp of stratum gap (C3), and
  **both are misses.** The effect was much bigger before round 502: at the
  63.2 % the ledger published for five rounds, a quarter of the sites were
  `test_only`. Saying "1.83 pp" without saying "measured after the very round
  that closed 27 survivors" would be the same kind of stale pin this program
  keeps finding.

Wired into `nodecampaign.run_slice`: every report now carries `scope_strata`,
`scope_verdicts` and `scope_not_live`. It runs unconditionally rather than
behind a flag, because it is pure `ast` and a flag nobody sets is not a gate.

**The scope was NOT narrowed.** `classify_bucket`'s mutants are real test gaps
and 21 of 21 are killed today. What changed is that `R491_RANGES`'s comment no
longer asserts something false, and no report can publish the pooled rate
without publishing what it pooled.

---

## 4. `classify_bucket` was an instance, not the exception

Same instrument, whole file:

```
scope-audit: nuc/perturbation.py -- 140 def(s), 140 in scope
  (125 live, 15 test_only, 0 unreferenced)
```

**Fifteen.** Three clusters:

| lines | defs | what it is |
|---|---:|---|
| 556-596 | 1 | `classify_bucket` |
| 813-1022 | 4 | `sadc_reclaim_literals`, `parse_vmstat_fields`, `steal_double_count_evidence`, `scan_undercount_evidence` |
| **4018-4443** | **10** | `lead_lag_profile`, `_bucket_at`, `_block_seconds`, `_profile_from_blocks`, `_summarise_profile`, `gap_blocks`, `effective_cells`, `block_lead_lag_profile`, `block_shift_null_lead_lag`, `_profile_stats` |

The third cluster is ~425 lines. Four of the fifteen are `transitive`: zero
direct test references, reached only from other `test_only` defs.
`sadc_reclaim_literals` is called twice, from lines 854 and 986, and both
callers are themselves `test_only` — a cluster whose only entry point is a
test. Counting direct test references alone would have called it live.

**And here is the part that must not be over-claimed.** `block_lead_lag_profile`
and `gap_blocks` and `effective_cells` **did** produce published numbers —
round 490's knowledge file quotes them, `state/nuc-missions.md` quotes them.
They are `test_only` because **no committed caller invokes them**. A round that
ran the function inline from a `python3 -c` is a real caller that left no
trace in the repository.

So `test_only` here does not mean "never ran". It means: *the only way to
re-derive those numbers from the record is for a human to remember the
command.* That is a worse finding than dead code, not a milder one, and it is
why §6's verdict is named `no_committed_caller` and never `dead`.

---

## 5. The instrument was wrong first, and the shape of the wrongness is the tell

The first sweep of `harness/swe/` reported **40 `unreferenced` defs**, 38 of
them in `alias_effects.py`, with names like `_stmt_let_record`,
`_stmt_call_alias`, `_stmt_shadow_param`.

They arrived as a **same-prefix family**, which is the signature of a dispatch
and not of dead code. `alias_effects.py:226`:

```python
return getattr(self, "_stmt_" + kind)(depth)
```

Every one was false. A name scan cannot see a name that does not exist until
runtime.

Fixed by treating any string literal that is concatenated, `%`-formatted,
`.format`ed or f-string-interpolated as a **name prefix**: every def whose name
starts with it counts as referenced. All four spellings are tested. The rule
can only add liveness, never remove it — which is the direction an orphan claim
has to fail in — and there is a floor of three characters, because a prefix of
`"_"` would vouch for every private def in the tree, which is not conservatism
but silence.

**Measured, before and after, on `harness/swe/`:**

| | live | test_only | unreferenced |
|---|---:|---:|---:|
| without the prefix rule | 889 | 83 | **40** |
| with it | 892 | 123 | **0** |

The 40 became `test_only transitive`, which is the correct answer: the
dispatch reaches them, and the dispatcher is reached only from its own tests.

**What caught it was not a test.** It was reading the list and noticing the
names rhymed. The general form: *if your orphans arrive as a family, suspect
the instrument.*

### The other conservative rule, measured too

`live_only_via_string` asks the same question of the runtime-string rule:
which defs are `live` **only** because their name appears inside a string?
On `nuc/perturbation.py` the answer is **one** (`attribute`), and on
`harness/swe/` **one** (`Attribution.attributed`). The prediction (D5) said at
least two per file, and missed. Both rules are load-bearing; the prefix rule
carries forty times the weight of the string rule, which is the opposite of
what I expected.

---

## 6. The repo's own wiring registry calls 29 modules `wired` on the authority of their own tests

Committing round 502's work tripped a pre-commit warning:

```
W001  nuc/survivor_impact.py: entry point with no registry entry
```

and the suggested fix worked:

```
$ python3 harness/wiring_audit.py declare nuc/survivor_impact.py --write
declared  nuc/survivor_impact.py  {"status": "wired",
          "via": "nuc/tests/test_survivor_impact.py:16", "via_kind": "import"}
```

**`wired`, via its own test file.** That is the exact shape §2 exists to name,
in the gate that is supposed to catch it.

The RED DEBT briefing says the wiring-audit recurrence *"`harness/wiring-registry.json`
has diagnosed in prose four times since round 473 without anything ever being
built from it."* So this round built it:

```
$ python3 harness/swe/scopecall.py registry
registry-audit: 143 entry(s), 133 checked (10 not an existing .py);
  112 wired, 65 of those via a TEST file; 69 with no committed caller
  declared `wired` by their own tests and nothing else: 29
```

The join is deliberately narrow. An entry is flagged only when **all** of:
its registry `status` is `wired`; its recorded `via` is a test file; no
non-test `.py` in the tree references the module by name; and **no shell
script or config does either**. That last clause matters — a third of this
repo's entry points are reached from `run_driver.sh` and from nothing in
Python, so a `.py`-only scan would call every one of them an orphan. Without
it the count is 82 and is mostly wrong.

**And it did it again, in this round, on this round's own module.**
`harness/swe/scopecall.py` is imported by `harness/swe/nodecampaign.py` — a
non-test file, wired into the campaign in §3 — and `declare` still recorded
`via: harness/tests/test_swe_scopecall.py:21`. The cross-check correctly puts
it in `has_committed_caller` on the strength of the `nodecampaign` import, so
the two disagree on the same file for the reason §6 gives: `via` is the first
caller found, not the only one.

The 29 span every track: `harness/swe/nodecampaign.py`, `harness/viapin.py`,
`languages/whence/checkpin.py`, `languages/whence/assertshadow.py`,
`nuc/record_union.py`, `nuc/survivor_impact.py`,
`skills/derived-subject-set/scripts/pattern_vs_enum.py`, and 22 more.

**This is not a bug in `wiring_audit.py`.** Its question is "is this file
reached at all", and for that question a test file is a legitimate answer.
The defect is that the answer is spelled `wired`, and `wired` gets read as
"something other than its own tests runs this". 65 of 143 entries are `wired`
with a test-file `via`; for 36 of those the registry simply recorded the first
caller it found and there are others (`harness/swe/coverage.py` is heavily
used and recorded `via` a test). For **29** there are no others.

---

## 7. Tests

Everything below was run on this box, under `.venv`, serialised — `nproc` is 1.

```
$ .venv/bin/python -m pytest harness/tests/test_swe_scopecall.py -q
73 passed in 73.41s

$ cd harness && ../.venv/bin/python -m pytest tests/test_swe_nodeid_selection.py \
      tests/test_swe_scopecall.py -q
90 passed in 79.60s

$ .venv/bin/python -m pytest nuc/tests/test_survivor_impact.py -q
34 passed in 0.41s

$ .venv/bin/python -m pytest nuc/tests/test_perturbation.py -q -p no:cacheprovider
257 passed in 45.91s
```

**The full `harness/tests/` suite did NOT land inside this round.** It was
launched at 06:12 UTC (`.venv/bin/python -m pytest harness/tests/ -q -p
no:cacheprovider`, `timeout 2400`) and was still running 23 minutes later when
the round's own 3300 s wrapper timeout came due. It is reported as UNRUN, not
as green — this file does not get to claim a result nobody saw. The targeted
suites above cover every file this round touched: `test_swe_scopecall.py` (new),
`test_swe_nodeid_selection.py` (the campaign this round wired into),
`test_survivor_impact.py` and `test_perturbation.py` (round 502's inheritance).
The one file this round changed that is NOT covered by them is
`harness/swe/nodecampaign.py`, and `test_swe_nodeid_selection.py` is that
module's own test file. Whoever runs the full suite next should say so.

`test_swe_scopecall.py` carries four `TestThisTree` cases and one
`TestThisTreeRegistry` case that read the live repo on purpose — the findings
as standing assertions. If a real caller for `classify_bucket` ever lands,
`test_classify_bucket_is_test_only_in_the_campaigns_own_scope` goes red and
the finding retires itself, which is correct behaviour and not a maintenance
burden. The registry case asserts `>= 20` rather than `== 29`: it is a claim
that the class is non-empty and substantial, not a pin every new module moves.

**Three of the module's own defects were found by wiring it into something,
not by testing it:**

1. `stratify` crashed on a ledger row with no `line` field (hand-written rows,
   and rows from before the field existed). Such a row now gets its own
   `no_line` stratum — dropping it silently would shrink a published
   denominator, and crashing would make the campaign unrunnable against its
   own history.
2. The `registry` subcommand read `a.search`, which only two of the four
   subparsers define.
3. §5's forty false orphans.

---

## 8. Skill

**NEW `skills/no-pooled-rate-without-its-strata/SKILL.md`** — a scope is a
CLAIM about reachability; verdict it before publishing a rate over it, and
report per stratum, never pooled. Twelve numbered steps, nine pitfalls (the
first being "a same-prefix family of orphans is a dispatch, not dead code"),
four runnable verification commands. `skill_lint --house --strict`:
**1 skill, 0 errors, 0 warnings.**

Three positive trigger cases in `skills/trigger-cases.json` (`nprws-near`,
`nprws-mid`, `nprws-far`) and a `state/known-unprobed-skills.json` entry with
owner `skills(B)` and a **scorable prediction**: that `nprws-mid` misfires,
because its surface reads as a dead-code question and the pooled-rate framing
that is this skill's actual hook never appears in its words. Round 434's
next-step #9 is the reason all three obligations are discharged here rather
than left as a `known-unprobed-skills.json` line, which silences a WARNING and
says nothing about either ERROR.

---

## 9. Predictions, scored

**11 HIT, 7 MISS of 18.** Misses first. D1 and D2 were disclosed in the bank
as already-observed and are not scored.

| | claim | verdict |
|---|---|---|
| **C1** | pooled kill rate is **70-88 %** | **MISS, high** — 94.25 %. I reasoned from 63.2 % plus round 502's re-score without reading how many the re-score flipped: 27 of 32, not the ~8 the previous round had aimed at. |
| **C3** | the two strata differ by **≥ 10 pp** | **MISS** — 7.58 pp (100 % vs 92.42 %). Right sign, right shape, too big a number. |
| **C4** | dropping `test_only` lowers the rate by **≥ 3 pp** | **MISS** — 1.83 pp. Same cause as C1: I sized the effect against the OLD kill rate. §3 says so rather than quoting 1.83 pp as if it were timeless. |
| **A2** | `test_survivor_impact.py` holds **33** tests | **MISS** — 34. I copied round 502's own prose instead of counting, which is precisely the error this program's carry-forward rules exist to stop. |
| **A4** | `test_swe_nodeid_selection.py` holds **14-22** tests | **MISS** — 25. |
| **D3** | the new test file holds **25-45** tests | **MISS, high** — 73. Two subcommands (`sweep`, `registry`) did not exist when the bank was written. |
| **D5** | **≥ 2** defs in `nuc/perturbation.py` are live only via the STRING rule | **MISS** — exactly 1 (`attribute`). The conservative rule that turned out to be load-bearing was a different one, which no prediction named at all (§5). |
| **A1** | the red test is entirely test-side; `owner_of` unchanged | **HIT** |
| **A3** | `test_perturbation.py` green at **257** tests | **HIT** — 257 passed in 45.91 s |
| **A5** | filling round 502's markers and entering its bank turns all three skills-check reds green with no other change | **HIT** — `placeholder_check` 3 errors -> **0**; `carryforward` K001 -> the only remaining K001 is round 503's own bank, closed at the end of this round; `unit_tests`' three failing nodes are the live-corpus readers of those two. |
| **B1** | the campaign scope covers **6-12** named defs | **HIT** — 9 |
| **B2** | exactly one is `test_only`, and it is `classify_bucket` | **HIT** |
| **B3** | none of the scoped defs is `unreferenced` | **HIT** — 0 |
| **B4** | whole-file, **≥ 3 more** `test_only` defs; total **8-30** | **HIT** — 15 |
| **B5** | `harness/swe/` holds **≥ 1** `test_only` public def | **HIT, and it is the uncomfortable one I said it would be** — `ExtendedEffectGen` and `check_one_ext` in `alias_effects.py` (119 defs), plus `guest_safe`, `row_stamp`, `union_probe_units`, `both_at_ceiling_program`. `fuzz.py` mentions `ExtendedEffectGen` three times, all in comments. |
| **C2** | the `test_only` stratum's kill rate is **higher** than `live`'s | **HIT** — 1.0 vs 0.9242 |
| **D4** | whole-repo sweep under **90 s** | **HIT** — 53.6 s for 253 subjects over 520 files |
| **D6** | no new red in `harness/tests/` or `nuc/tests/` | **PARTIAL / UNRESOLVED** — no red in any targeted suite this round ran (73 + 25 + 34 + 257 all green), but the full `harness/tests/` sweep did not finish inside the round (§7). Carried to next steps as an open item rather than scored. |

**The shape of the misses.** Five of the seven (C1, C3, C4, A2, A4) are the
same error, and it is not a reasoning error: **I banked numbers copied from
prose instead of counted from files.** A2 took "33 tests" from round 502's own
sentence; C1 took 63.2 % from a ledger the previous round had just rewritten.
Round 434's next-step #9 says exactly this — *"re-derive FIRST"* — and it
applies to writing a prediction, not only to quoting a result. A prediction
whose *premise* is stale is not a wrong prediction about the world; it is a
correct prediction about a world that no longer exists.

**Two findings no prediction anticipated**, both in §5 and §6: the constructed-
name dispatch (40 false orphans, and the general rule that a same-prefix family
is a dispatch) and the wiring-registry cross-check (29 entries declared `wired`
by their own tests). Both were found by *using* the instrument rather than by
testing it — §7's three-of-three record.

---

## 10. What the next round should take

1. **The 29 `no_committed_caller` registry entries are a decision, not a
   bug list.** Each is one of three things and only reading tells you which:
   a CLI a round runs by hand (wire the command into a script, or accept that
   the numbers are not re-derivable); a module superseded and never deleted;
   or a genuine gap. `python3 harness/swe/scopecall.py registry --strict`
   exits 1 on the class. Do not fix it by widening the definition of `wired`.
   harness(A).
2. **`nuc/perturbation.py`'s lead-lag block (4018-4443, 10 defs, ~425 lines)
   published numbers through a caller nobody committed.** Round 490's
   `effective_cells` / `gap_blocks` / `block_lead_lag_profile` figures are in
   two state files and a knowledge file with no committed way to re-derive
   them. That is the highest-value single item this round found.
   NUC-integration(E).
3. **`harness/swe/alias_effects.py`'s `ExtendedEffectGen` is 119 defs reached
   only by its own test file**, and `fuzz.py` mentions it three times in
   comments — the same "a comment asserting it is live" shape as
   `classify_bucket`, in the harness this track owns. Either wire it into
   `fuzz.py` or record why it is test-only on purpose. SWE-loop(D) or
   harness(A).
4. **Re-derive C1/C4's numbers when the ledger next moves.** §3's 1.83 pp is a
   property of a ledger that round 502 rewrote four hours before it was
   measured. The structural claim (pooling flatters, always upward) does not
   need re-deriving; the pp figure does, every time.
5. **The scope-audit has never been run on `languages/whence/`.** The
   whole-repo sweep reports 37 not-live defs in `whence/interp.py` and 8 each
   in `curecheck.py` and `depthcensus.py`, entirely unexamined — and
   `interp.py` is exactly the kind of visitor-dispatch shape §5 shows this
   instrument getting wrong first. Treat those 37 as unverified until someone
   reads the names. language(C).
6. **An interrupted round emits a detectable defect.** §1: unfilled markers in
   a knowledge file plus an unentered bank redden two independent checkers in
   a suite the interrupted track does not run. Nothing detects the pair at the
   moment the round dies; the record-gap check finds the uncommitted diff, and
   the skills check finds the consequence a rotation later, attributed to the
   wrong track. harness(A) or skills(B).
7. **Standing, and untouched by this round:** the NUC `retention --strict`
   deadline; `case_coverage`'s disagreeing verdicts; `claim_check` executing 0
   of its commands; CLAUDE.md's `CRITICAL MISSION` and `MASTER MISSION`
   blocks, both still a deletion for the operator; and
   `languages/whence/SECURITY.md`, still the operator's decision — the
   checker's own line is the only source for its carry count.
