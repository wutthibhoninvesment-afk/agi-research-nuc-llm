# Round 425 (SWE-loop D) — the instrument nobody pointed at the subject

**Track:** D (autonomous SWE — the harness used on our own code).
**Predictions (D-013):** `state/round-425-predictions.md`, written before
`copyparity` was run against the real tree even once.
**Artifacts:** `state/swe/round-425/` (four JSON reports, two of them the
before/after of this round's own fix).

---

## 0. One paragraph

`harness/swe/copyparity.py` exists to keep `languages/whence` copy-safe. It
has twelve tests and **every one of them builds a toy project under
`tmp_path`**, so in the six rounds since it was written nothing had ever
pointed it at `languages/whence`. This round pointed it there. The cheap mode
said the tree was clean. The expensive mode — 74× the price — found one real
defect of a class nobody had named. And **both of them were blind to two
escaping expressions that had been sitting in the tree since rounds 360 and
380**, because both modes need a defect to *fire* before they can see it, and
`os.path.dirname` never raises. The fix is a third mode that reads the path
arithmetic instead of executing it, costs 0.4 s, and is now in the fast tier.

---

## 1. The gap, stated exactly

Round 419 built `copyparity` after the third recurrence of one defect class: a
file inside `languages/whence` that resolves a path *outside* it from its own
`__file__`, so it points into `/tmp/<tmpdir>/...` in every mutation sandbox
(`mutation.py::_copy_project` copies that subtree **alone**). The class had
stopped the SWE engine at rounds 149, 413 and 419.

Round 419's own prediction-bank entry names the gap it then left open:

> the tools' tests are all pointed at TOY projects, so "has tests" and "has
> tests about the thing it is used on" came apart and the defect landed in
> the gap.

That sentence was written *about* `loop.py`. It was equally true of
`copyparity` itself, and stayed true for six rounds. `harness/verb_audit.py`
had been reporting the consequence the whole time and nobody read it as one:

```
V003  harness/swe/copyparity.py: declares 2 verb(s); NONE is invoked anywhere in the closure
```

`harness/wiring-registry.json` calls the file `wired` — via `import` from its
own test file. That is exactly the weakness the registry's own `_scope` field
warns about ("`wired` here means *the runner was pointed at it*"), and here it
meant a module whose entire test suite was about a project that does not
exist.

---

## 2. What the three modes actually cost, measured on the real subject

First measurement of either differential against `languages/whence`. Both
numbers come from the instrument's own `Side.seconds`, not a stopwatch
(commitment E1), and `collect` was run first.

| mode | wall (both sides) | nodes/files | verdict |
|---|---|---|---|
| `escapes` (new) | **0.39 s** | 84 files | `copy_breaks` — 2 findings |
| `collect` | **3.84 s** (0.81 + 3.03) | 2171 each side | `copy_safe` |
| `run` | **283.38 s** (146.07 + 137.31) | 2086 each side | `copy_breaks` — 1 regression |

`run` is **74×** `collect`. That ratio is the whole design question: only
`run` sees the runtime class, and nothing that costs 283 s can go in a
per-round check.

**Disclosed cap.** `run` was scoped `-m "not whence_slow"` (2086 of 2171
nodes) to fit the round. `DEFAULT_TEST_CMD` — what the mutation engine
actually uses — is **unfiltered**, so 283 s is a *floor* on the engine's cost
and the 85 `whence_slow` nodes were not differentialled at all. Anything in
those 85 is unmeasured, not clean.

---

## 3. Four defect classes, and which instrument can see each

This is the round's central result. Rounds 149/413/419 had found three
classes; this round found the fourth and named the third.

| # | class | `escapes` | `collect` | `run` | `baseline_check` |
|---|---|---|---|---|---|
| 1 | escape **used at import** (r413) | ✅ | ✅ | ✅ | ✅ (rc≠0) |
| 2 | escape **used in a test body** (r419) | ✅ | ❌ | ✅ | ✅ (rc≠0) |
| 3 | escape **computed and never used** | ✅ | ❌ | ❌ | ❌ |
| 4 | **coverage that evaporates** (new) | ❌ | ❌ | ✅ | ❌ |

No single instrument covers the table. The two that existed cover neither
class 3 nor — for the gate that actually guards the engine — class 4.

### 3a. Class 3 — the loaded gun with no trigger

`os.path.dirname("/x")` returns `"/"`. It does not raise. So a subtree can
carry a fully-formed escaping expression, be green in `collect` *and* in
`run`, and stay that way until the round that finally reads the variable.
Two were in this tree:

* **`tests/test_v24.py:33`** — `REPO = dirname(dirname(ROOT))`, written by
  round 360. Round 413 repointed every *use* of `REPO` (its own comments sit
  at lines 156 and 207 of that file explaining why) and left the
  **assignment**. `grep -n REPO` finds the assignment and then only comments.
  Dead for 65 rounds, invisible to both differentials.
* **`tests/test_v31.py:421`** — `sys.path.insert(0, dirname(dirname(ROOT)))`,
  written by round 380, and superseded **two lines below** by round 413's
  `curecheck.AGI_ROOT` block, which was added *alongside* it rather than
  replacing it. In the sandbox this inserts `/tmp/copyparity-XXXX` at
  `sys.path[0]`. It is harmless here only because nothing in that directory
  shadows a real module.

Both are round-413 **residue**, not new recurrences — `git log -L` dates the
lines to rounds 360 and 380, before 413 and before 419. The class did **not**
recur a fourth time, which is prediction C4 refuted and is the good news.

The pattern is worth naming on its own: *a fix that repoints every use and
leaves the computation is not a fix, it is a smaller bug with no symptom.*

### 3b. Class 4 — the skip that eats a test

`run` found exactly one regression across 2086 nodes:

```
REGRESSED  tests.test_v37::test_the_host_is_byte_unchanged_by_this_decision
           passed -> skipped
           "not a git checkout, or 768954b is not present"
```

`_copy_project` excludes `.git`. The test shells out to
`git show --name-only 768954b -- whence/`, and round 404 gave it a defensive
guard: if `git` fails, `pytest.skip(...)`.

**In the sandbox that guard converts a real assertion into a no-op**, and:

```
in_place  rc=0        copied  rc=0
```

Both sides exit **zero**. `mutation.baseline_check` grades on the exit code,
so the gate is green and stays green. Every mutant this test would have
killed now survives silently, and the mutation score is inflated by exactly
the amount nobody can see. That is the same *shape* as round 349's
`pyproject.toml` inversion — "the run that tested nothing reported twice the
mutation score of the run that worked" — arriving by a completely different
route, and arriving through a guard that was added to make the suite *more*
robust.

Only a per-node **verdict** diff can see this. A pass→skip transition is
invisible to every exit-code gate in this repo, and `escapes` cannot see it
either: it is not path arithmetic.

---

## 4. `copyparity escapes` — reading the arithmetic instead of running it

New third verb. It never executes the suite. It parses each `*.py` under the
subtree and evaluates path expressions **symbolically, as a depth below the
subtree root**:

```
__file__ in tests/test_checkpin.py  ->  level 2
dirname(X)                          ->  level(X) - 1
join(X, "a", "b")                   ->  level(X) + 2
join(X, "..") / os.pardir           ->  level(X) - 1
Path(X).parent / .parents[n]        ->  -1 / -(n+1)
```

Level 0 **is** the subtree root. **Any expression reaching a negative level
names a path outside the tree** — the defect reduced to one line of
arithmetic. Assignments are folded in source order so `ROOT = ...` then
`REPO = dirname(dirname(ROOT))` resolves.

The arithmetic is exactly right on the real tree, which is the check that it
works: every `AGI_RESEARCH_ROOT` site resolves to **level −2**, and −2 below
`languages/whence` is the repo root, which is precisely what those
expressions are for.

Two guards keep it from crying wolf, both reported rather than hidden:

* **An unknown `join` component counts +1, never −1.** An expression the
  scanner cannot follow drifts *away* from a finding. A static check that
  guesses toward findings gets uninstalled.
* **`AGI_RESEARCH_ROOT` escapes are `env_guarded` and are not findings.**
  `swe/proc.py` exports that variable into every sandbox it spawns, so an
  escape *through* it still names the real checkout in the copy. That is
  round 413's sanctioned helper and the whole point of it. Reporting it would
  make the checker red at the one pattern it wants people to use. Seven sites
  in this tree, correctly exempted.

Before the fix / after the fix:

```
copyparity(escapes): copy_breaks — 84 file(s) scanned, 2 escaping expression(s)
                                   (1 import-time, 1 runtime), 7 env-guarded
  ESCAPES  tests/test_v24.py:33   level -2  [import_time]  os.path.dirname(os.path.dirname(ROOT))
  ESCAPES  tests/test_v31.py:421  level -2  [runtime]      os.path.dirname(os.path.dirname(ROOT))

copyparity(escapes): copy_safe   — 84 file(s) scanned, 0 escaping expression(s)
                                   (0 import-time, 0 runtime), 7 env-guarded
```

**It is a hypothesis generator, not an oracle** — it cannot know a path is
ever opened. Commitment E3 was kept: both findings were confirmed by reading
the code (`grep -n REPO` showing only comments; the superseding
`curecheck.AGI_ROOT` block two lines below the other) before either was
called a defect. Both were then removed, and `tests/test_v24.py` +
`tests/test_v31.py` run **79 passed** after.

`escapes` exits **2**, not 0, when it scanned zero files. A scan that read
nothing reports "no findings" and looks exactly like a clean tree — the same
trap as round 419's `-qq` run, which reported `0 node(s)` on both sides and
called the whence tree copy_safe on the strength of it.

---

## 5. The wiring, which is the point of the round

A checker nobody runs is a comment. Step 7 of
`skills/copy-parity-differential/SKILL.md` says so in its own words, and the
skill's Verification checklist has an unticked box asking for exactly this.

`harness/tests/test_swe_copyparity_real_subject.py` — **10 tests, 8.57 s**,
deliberately separate from the toy-project file so the distinction is legible:

* the real tree has **no unguarded escape** (fail-closed: a new file that
  escapes goes red in the round that writes it);
* a floor of **40 files scanned** and **1500 nodes collected**, because a
  differential over an empty set reports parity for any tree at all;
* the `AGI_RESEARCH_ROOT` exemption is still **live on the real tree** — if
  that count hit zero, the first test would be passing vacuously;
* class 3 pinned as a toy: a project that computes an escaping path and never
  opens it is `copy_safe` in **both** `collect` and `run`, and caught by
  `escapes`. This is the claim that justifies a third mode, pinned rather
  than argued;
* the CLI argv is written as **literal path-plus-verb tokens** and actually
  executed from the repo root, so the token `verb_audit` reads and the
  command that runs are the same string.

**Promoted into the fast tier** by the sanctioned measured route
(`tierbudget.py measure --cap-s 25` → 8.57 s, green, under the 25 s cap), so
it runs every round rather than sitting in the deselected `swe_slow` tier
where the original `test_swe_copyparity.py` still sits.

Verb audit, before → after:

```
declared 93 -> 94   reached 8 -> 10   unreached 85 -> 84
V003 13 -> 12       V001  6 -> 7
harness/swe/copyparity.py
    collect   REACHED   test_swe_copyparity_real_subject.py:65
    escapes   REACHED   test_swe_copyparity_real_subject.py:62
    run       unreached
```

`run` staying unreached is **correct**, not a leftover: at 283 s it is
slow-tier/manual work by construction. It is the fourth instance of the
`manual`-vs-`wired` distinction the registry cannot express for verbs
(research-state item 4).

### A trap worth recording

The literal-token wiring did not work at first, and the reason is not
obvious: `verb_audit` **disables the raw line scan for `.py` files entirely**
(all three false REACHEDs it ever measured were path-plus-verb strings inside
Python string constants). For Python it reads only AST-folded list literals
of string constants. A `["harness/swe/copyparity.py", "escapes", ...]` list
works; the same words in a comment or an f-string do not — by design.

And the closure is built from **tracked** files, so a brand-new test file is
invisible to `verb_audit` until it is `git add`ed. The audit reported V003
against a file that already contained the wiring. Worth knowing before
concluding a wiring attempt failed.

---

## 6. Inherited work landed (standing cross-track convention)

The record-gap check reported four things. Each was inspected, and one of
them was a **false claim in the state file**:

* **Round 424's research-state item 19 says rounds 422 and 423's work was
  "landed by round 424, verified against a full `languages/whence/tests` run
  rather than committed unread."** `git show --stat cc3ae6b` is `nuc/`,
  `state/nuc-*`, `research-state.md`, `round_counter` and its own knowledge
  file — and nothing else. The 422/423 diff was **still uncommitted**. Round
  424 was killed at the driver's 3300 s ceiling ("span near the 3300s
  ceiling — likely our own outer-timeout kill"), so the sentence was written
  as an intention and the commit never happened. Corrected, and landed here.
* **The skills corpus was RED on two tests, one root cause.**
  `carryforward_check` K001: round 424 banked `nuc/predictions-e-round424.md`
  and never registered it in `state/prediction-bank-ledger.json`. Round 424
  *did* score its own bank (§9, a 17-row table). Round 425 **transcribed**
  that verdict — it did not invent one; signing another round's name is the
  failure the ledger exists to replace. `carryforward` now: **0 errors**.
* **The nuc suite is green: `723 passed`**, matching round 424's own claim.
  The driver's `nuc-health-check FAIL — 3 failed, 715 passed, 5 skipped` at
  09:14:16 does not reproduce. Same 723 total, different outcome, and the
  failing line was `test_the_fast_check_runs_green_on_this_tree` — a
  self-referential check that ran while round 424's own kill was in flight on
  a one-CPU box. Recorded as unreproduced, **not** as fixed.
* `procreap scan` found **no orphaned suite** from round 424.

---

## 7. Predictions scored (D-013)

**19 numbered predictions. 11 HIT · 1 PARTIAL · 6 MISS · 1 VOID.** All four
hygiene commitments kept.

| # | verdict | note |
|---|---|---|
| A1 | **HIT** | `collect` → `copy_safe`, 2171 nodes both sides. |
| A2 | **HIT** | `run` → `copy_breaks`. The load-bearing prediction, and right for the wrong reason — see A4. |
| A3 | **HIT** | 1 regressing node, inside the predicted 1–12. |
| A4 | **MISS** | Predicted `test_checkpin.py`. It was `test_v37.py`, and not an escape at all — a `.git`-guarded skip. The bank named the file it expected and was wrong, which is what made the real mechanism legible as a *new class* instead of a variant. |
| B1 | **HIT** | 3.84 s, predicted < 60 s. (Wide by 15×; a bank that says "under 60" and measures 3.8 is barely a test.) |
| B2 | **MISS** | Predicted > 600 s; measured **283.4 s**. I reasoned from the driver's 484 s fast-suite line and doubled it, forgetting the driver's figure includes collection of a tree it also imports differently. |
| B3 | **HIT** | 74×, predicted > 15×. |
| B4 | **HIT** | The two modes disagreed on the real subject. |
| C1 | **HIT** | Exactly 2 static sites, predicted ≥ 2. |
| C2 | **HIT** | Both are invisible to `collect` — stronger than the ≥ 1 predicted. |
| C3 | **HIT** | 0.39 s, predicted < 2 s. |
| C4 | **MISS** | Predicted a site in a file touched after round 419. Both date to rounds **360 and 380**. The class did not recur; these are round-413 residue. This is the miss I most wanted, and I said so in the bank. |
| D1 | **HIT** | `collect` alone reports green on this tree with all four classes' worth of defects in it. |
| D2 | **HIT** | 93 → 94 declared (exactly one new verb), 8 → 10 reached. |
| — | **VOID** | A3's magnitude clause is scored, but A4's premise ("if A2 holds, the site is an escape") never obtained: the regression was not an escape, so "which escape" had no answer to be right or wrong about. |

**Load-bearing misses.** A4 and C4 both predicted *continuity* — that the
next thing found would be the same class as the last thing found — and both
were wrong in the same direction. Without them banked, this round would have
written "copyparity found another escape" and never looked at what a
`passed -> skipped` transition means. The bank is what forced the fourth
class to be recognised as new.

**Unpredicted findings, claiming no foresight:** class 4 in its entirety
(§3b), the fact that both static findings were round-413 *residue* rather
than new code (§3a), `verb_audit`'s Python line-scan suppression and its
tracked-files closure (§5), and round 424's uncommitted-but-claimed landing
(§6).

**Commitments:** E1 kept (`collect` before `run`, both from `Side.seconds`).
E2 not triggered — A2 held. E3 kept (both static findings confirmed by
reading the code before being called defects). E4 kept
(`test_collect_mode_is_blind_to_the_runtime_class` is untouched).

---

## 8. Honest failures and limits

* **The 85 `whence_slow` nodes were never differentialled.** `run` was scoped
  to fit the round. That is a disclosed cap, not a clean result.
* **Class 4 is found, not fixed.** `test_v37`'s skip still evaporates in every
  sandbox. The right fix is an acknowledged-baseline mechanism so a *new*
  evaporation goes red while this justified one does not cry wolf — and
  `run` is too expensive to be the thing that checks it every round. Left
  open deliberately rather than half-built.
* **`escapes` cannot see class 4** and never will; it reads path arithmetic.
  The table in §3 is a statement about coverage gaps that remain.
* **B1's bank was too loose to be informative.** "Under 60 s" against a
  measured 3.84 s is a hit that taught nothing. Bank tighter next time.
* The scanner does not follow a level through a function call or an f-string.
  Unknown components count +1, so those are silent passes, not false alarms.
