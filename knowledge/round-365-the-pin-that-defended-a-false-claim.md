# Round 365 (SWE-loop D) — the pin that defended a false claim, and the seed that never returns

**Track:** D (autonomous SWE — the harness used on our own code).
**Handoff taken:** round 361's items 1 and 2, both left explicitly for this track.

---

## 0. Pre-flight reconciliation

The record-gap check reported two unattributed paths. One is
`languages/whence/SECURITY.md`, carried unchanged for a **tenth** consecutive
round — escalated to the operator since round 349, a TRACKED file a separate
system rewrote, deliberately not in `state/known-standing-dirty-paths.json`
(which models untracked leftovers only). Nothing in-tree resolves it.

The other, `logs/skills_health_round_364.log`, was a REAL gap and is fixed
(commit `ae41e21`). Round 363 wired a third per-round health check
(`skills/run_checks_fast.sh`) into `run_driver.sh` but did not extend
`.gitignore`, whose two sibling patterns `logs/health_round_*.log` and
`logs/whence_health_round_*.log` have covered exactly this class since rounds
241/247. It is a `.gitignore` fix, **not** a standing-dirty-paths entry:
that registry models files a SEPARATE system leaves behind, and allowlisting
a file our own driver writes every round would grow it by one path per round
forever.

*Generalisable:* when a round adds a per-round generated artifact, the
`.gitignore` entry is part of the same change. The latency here was one
round; it is only that short because the record-gap check exists.

---

## 1. The finding: a pin can defend a claim that was never true

`harness/tests/test_swe_guest.py::test_no_shape_declaration_reaches_the_guest_generator`
(round 347):

```python
"""`GuestGen` inherits `ProgramGen`'s grammar; the guest parser has no
`shape` support at all, so a generated declaration would be a one-sided
parse failure."""
for i in range(200):
    assert not pat.search(G.generate_guest_program(i)), i
```

**Round 338 — nine rounds EARLIER — taught the guest the `shape` statement.**
`self_eval.lang`'s shared parser section implements `is_shape_head`,
`shape_close`, `shape_rel_depth`, `shapes_before`; the guest evaluator
resolves `-> Shape` at closure-creation time. `GuestGen`'s own class
docstring says so, **two hundred lines above the test that denied it**.

The test passed for fourteen rounds anyway, because the grammar happened not
to reach `_shape_decl` from the guest seeds in `range(200)`. When it started
to, round 361's slow-tier sweep found it red and reported it as a red test.
It is not a red test. It is a **red claim**, and it was red on the day it was
written.

Round 361 framed the fix as a design call — "a generator override, or teach
the guest `shape` (round 335's item 2)". Both options accept the docstring's
premise. Neither was needed.

**The generalisable shape.** This is round 321 item 14 / round 333 item 4's
class ("any line asserting a number that no round re-executes") widened one
notch: *any line asserting a CAPABILITY that no round re-executes*. A number
goes stale when the code changes under it. A capability claim in a test
docstring is worse — it is the justification for the assertion, so when it
goes stale the test keeps passing and actively defends the wrong behaviour.
Nothing in the corpus checks a docstring against the code it describes.

Measured after the correction:

| quantity | value |
|---|---|
| guest seeds in `range(400)` declaring a `shape` | **141 (35.2%)** |
| guest seeds in `range(200)` declaring a `shape` | **70 (35.0%)** |
| of those 70, using the shape name as a `: TAG` / `-> TAG` | **39** |
| hand-written shape cases compared host-vs-guest (flat/empty/nested/list-tag) | **4/4 agree** |

---

## 2. The real gap the stale pin was hiding

`shape S1 = @{a: num}` is pure sugar on **both** sides: it desugars to
`let S1 = @{__shape: "S1", a: "num"}`. So a declaration produces an ordinary
top-level RECORD BINDING the differential can compare like any other.

It never compared it. `_shape_decl` registers only its optional WITNESS
binding in `self.scope`; the shape name goes to `self.shapes`, which
`generate_guest_program` did not read:

```python
names = []
for n in g.scope + [f for f, _ in g.fns]:      # <-- no g.shape_names()
    ...
return src + scrub_record_line(names[:max_names])
```

**From round 347 to round 365, ~35% of generated guest programs declared a
shape and not one of them compared the record the declaration produced.**
The programs ran and agreed; the agreement was simply never about the shape.

The fix appends shape names **after** the `max_names` cut rather than
merging them into it. Merging is the tempting one-liner and it is wrong:
`max_names` is 8, a program with 8+ ordinary bindings is common, and a shape
name losing that tie-break looks exactly like coverage. The set is bounded
(1–2 declarations, 35% of programs), so this widens the compared record by at
most two fields.

Three positive pins replace the negative one:

- `test_shape_declarations_reach_the_guest_generator` — rate pin, deliberately
  loose (40–120 of 200). It exists to catch declarations falling OUT of guest
  programs entirely, not to freeze a rate.
- `test_every_declared_shape_binding_reaches_the_compared_record` —
  **structural**, not statistical. If one declared shape name is missing from
  `__result`, coverage is silently back to zero and both other tests still
  pass. This is the guard that matters.
- `test_shape_declaring_guest_programs_agree` — the differential, bounded.

---

## 3. Second finding: a generated program the HOST does not finish

`generate_guest_program(31)`:

```
shape S1 = @{b: fn, a: str}
let w2 = @{b: fn(a) { a }, a: "3O"}
fn tl3(p4) -> num { if p4 == 0 { 0.5 } else { tl3(p4 - 1) } }
let tr5 = tl3(3)
100
let v6 = (tr5 > tl3(@{b: w2}))
let v7 = tl3(tr5)
let v8 = fn(p9: S1, p10) effects [net, random] { p10(tl3(w2)) }
let v11 = 10.x
let v12 = []
check "q_tr5": tr5 == tr5
contains([v12], v12)
check "q_v6": v6 == v6
```

(saved verbatim, with its `__result` record, as
`state/swe/round-365/seed31_hang.lang`)

`O._run_ast(pkg, ast, max_depth=2000)` did not return in **>90 s** on a run
where `load_whence` and `_parse` of the same program each took **0.0 s** and
the other 140 shape-emitting seeds averaged **1.2 s**. So it is not the box
(which was genuinely loaded — see §5) and not parse cost.

What it is NOT, all measured:

- **not the guest** — the HOST alone hangs.
- **not this round's `__result` change** — the sweep run BEFORE the change
  stopped at the same seed. Two independent runs, same stopping point; that
  is what turned "the background job died" into "seed 31 is deterministic".
- **not the obvious minimization** — `fn tl3(p4) -> num { if p4 == 0 { 0.5 }
  else { tl3(p4 - 1) } }` recursing on a record argument terminates
  instantly at `max_depth` 50/100/200/400/800, and so do three other hand
  variants (record-containing-closure, nested record, untyped fn). The
  trigger is something else in the program.

Pinned as `test_seed31_does_not_terminate_under_the_default_budget`, which
asserts only what is measured — that a 25 s budget is exceeded — and no
timing, so it cannot become a flake on a loaded box. **If a future round
fixes the hang this test goes red; that is the intended signal.** Flip it to
assert termination and record the fix.

---

## 4. The methodological finding: this round repeated round 185's root cause

The first sweep script called `G.oracle_self_eval(pkg, src, harness=h)`
directly. That function **has no timeout** — the SIGALRM lives in
`O.run_oracle`. Seed 31 therefore ate the whole run: **131 of 141 seeds
lost**, twice, and both times the backgrounded job reported **exit code 0**
with a truncated result file, because the pipeline's status was `tail`'s.

This is round 185's root cause verbatim ("a bare
`G.oracle_self_eval(pkg, src, harness=h)` call that skips `run_oracle`'s
SIGALRM timeout entirely... ran for 2912s"), and it is already pinned **in
the same test file** by `test_run_oracle_kwargs_bounds_a_shared_harness_hang`,
whose docstring tells the whole story. The pin was there. It was not enough,
because a pin proves the mechanism works — it does not make the next
scratch script use it.

Both the sweep script and the new differential test now go through
`run_oracle` with an explicit `timeout_s`.

*Generalisable:* **a scratch/one-off script is exactly where a suite's hard-won
safety rail gets skipped**, because scratch code is written to be thrown away
and so is written from the API, not from the tests. Cheap mitigation, not
implemented this round: make `oracle_self_eval` take a `timeout_s` of its own
rather than leaving the only bounded entry point one layer up.

**Also: a truncated backgrounded job reporting exit 0 is not evidence of
success.** Two runs here did exactly that. This is adjacent to round 310's
item 5 (the `tail`/EOF backgrounded-pipe silent-drop mechanism, unconfirmed
since round 296) but is **not** a confirmation of it — the cause here was a
hang plus a pipeline exit status, not a dropped write. Item 5 remains open;
this round deliberately does not claim it.

---

## 5. Round 361's item 2 is checkout drift, not pollution — partially settled

`test_run_oracle_forwards_kwargs_to_the_oracle_fn` failed **in-file** and
passed **alone** at round 361. At HEAD it passes **both** ways
(`1 failed, 66 passed` here vs round 361's `2 failed, 65 passed`, same 67
tests, same deterministic order — `pytest-randomly` is not installed).

The two files `test_swe_guest.py` reads through `readscope` — `whence/interp.py`
and `examples/self_eval.lang` — are **exactly** the two changed between
round 361's commit and HEAD (round 362's `9d198b8`), which is what
`slowtier`'s own `stale_subject / moved in scope: examples, whence` said.

The confirming experiment — a `git worktree` at `52dcde1` running the file —
was launched and **killed by the box before it produced a line** (`exit 143`
after 10 min at load 25–42). So: strong circumstantial evidence, **not
proof**. Recorded as such, and left as a next step with the exact command.

---

## 6. Environment note, and why it matters for the figures above

The box sat at **load average 25–42 on 1 CPU** for this round, with
`/proc/pressure/io some avg300=39%` and `cpu some avg300=67%`, and no single
process above 3% CPU — i.e. saturated I/O wait, not compute. Three
backgrounded jobs were SIGTERM'd out from under this round.

Every figure quoted above was therefore taken from a run that printed its own
setup cost (`loaded 0.0s / parsed 0.0s`) so the reader can see the box was
responsive at the moment of measurement. That is the practice round 364's
measured-budget lesson implies and this round found a second use for: **on a
shared box, publish the control alongside the measurement**, or a reviewer
cannot tell a real hang from a starved process. It is precisely what makes
§3's ">90 s" a finding rather than noise.

---

## 7. Predictions (D-013), banked in `state/swe/round-365/PREDICTIONS.md`

| # | prediction | result |
|---|---|---|
| P1 | 0 of the 62 remaining shape seeds mismatch | **UNRESOLVED** — the sweep died on seed 31 twice; 10/10 measured seeds `ok`, 4/4 hand cases `ok`, but the 400-seed sweep never completed. Recorded as unresolved rather than scored from the partial run. |
| P2 | ≥60 of 70 `ok` outcomes are REAL comparisons, not skips | **HIT** — `compare_behaviours` returns `("ok","")` only after comparing `__result` and `checks`; every measured `ok` had empty detail (a skip carries `"depth_skew (exempt)"`). |
| P3 | shape rate over 400 seeds within 28–42% | **HIT** — 35.2% (141/400). |
| P4 | round 361's item 2 does NOT reproduce at HEAD | **HIT on the observation, UNPROVEN on the cause** — passes at HEAD; the worktree control was killed. See §5. |
| P5 | `test_shape_needs_three_adjacent_tokens_on_both_sides` still red at HEAD | **UNRESOLVED** — not re-run; the whence slow tier is ~590 s and this round spent its budget on §1–§4. |
| P6 | ≥20 of 200 guest programs use a shape name as a tag | **HIT** — 39. |
| P7 | the positive pin costs ≤~90 s | **MISS** — the bounded differential is 25 seeds at ~1.2 s plus seed 31's 20 s timeout, and the separate hang pin costs 25 s: ~75 s + 25 s ≈ **100 s**. The miss is seed 31, which P7 did not know about when it was written. |
| P8 | the `.gitignore` fix leaves SECURITY.md as the only unattributed path | pending round 366's record check. |

Two UNRESOLVED and one MISS, all recorded rather than quietly dropped. P1 is
the one that stings: the headline claim of §1 rests on 10 sweep seeds + 4 hand
cases + 39 tag-using programs that parse, **not** on the 141-seed sweep the
prediction was written against.

---

## 8. Verification

| what | result |
|---|---|
| `pytest -k "shape_declarations_reach or compared_record"` | **2 passed** in 0.41 s |
| `pytest -k seed31` | **1 passed** in 27.51 s (the hang pin fires) |
| `generate_guest_program(1)` `__result` fields | `tr4 v8 v9 v10 tl2 f5 f11 f13 S1` — `S1` present, was absent |
| host+guest agreement, hand cases (flat/empty/nested/list-tag) | **4/4 `ok`** |
| host+guest agreement, sweep seeds 1,3,4,7,8,13,14,18,21,28 | **10/10 `ok`**, 0.26–2.52 s |
| shape rate | 70/200 (35.0%), 141/400 (35.2%) |
| seed 31, `_run_ast(max_depth=2000)` | **did not return in >90 s** (load 0.0 s, parse 0.0 s) |
| seed 31 via `run_oracle(timeout_s=25)` | `timeout` |
| full `test_swe_guest.py` | see §9 — run after the commit |

---

## 9. What is NOT done, honestly

- **The 141-seed sweep never completed.** `state/swe/round-365/sweep.py` is
  fixed (it now uses `run_oracle`) but was not re-run inside this round's
  budget. It is a single command and the first thing round 366+ should do on
  this track.
- **Seed 31 is not minimized and not diagnosed.** Four hand variants failed to
  reproduce it. The repro is deterministic and saved.
- **Round 361's item 2 has evidence, not proof** (§5).
- **P5's whence-slow red is untouched.**
